"""Local web interface: run downloads and conversions from the browser.

Each job runs the mangabinder command line in a subprocess, its output is
streamed to the page, and the finished PDFs / CBZs are served so they can be
opened straight from the browser.

    mangabinder web                      # opens http://127.0.0.1:8765
    mangabinder web --library D:\\Manga --port 9000 --no-browser

The server only listens on 127.0.0.1 and is meant for local use.
"""
import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from mangabinder import REPO_URL, __version__
from mangabinder.convert import IMAGE_EXTENSIONS
from mangabinder.downloader import STATE_FILE, site_folder

IS_WINDOWS = os.name == "nt"
OUTPUT_SUFFIXES = ("_pdf", "_volumes", "_cbz")
SERVED_TYPES = {".pdf": "application/pdf", ".cbz": "application/vnd.comicbook+zip"}
MAX_LOG_LINES = 2000
PROGRESS_RE = re.compile(r"\d+%\|")  # tqdm progress bar lines
DEFAULT_THREADS = 16

LIBRARY = os.getcwd()  # set by serve()
ALLOW_IP_HOSTS = False  # set by serve() when listening beyond loopback


def host_name(header):
    """'localhost:8765' -> 'localhost', '[::1]:8765' -> '::1'."""
    header = header.strip()
    if header.startswith("["):
        return header[1:header.find("]")] if "]" in header else ""
    return header.rsplit(":", 1)[0] if header.count(":") == 1 else header


def is_ip(name):
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def is_loopback(host):
    return host == "localhost" or (is_ip(host) and ipaddress.ip_address(host).is_loopback)


def natural_key(name):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def self_command():
    """How to invoke the mangabinder CLI from a subprocess (works for the .exe too)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "mangabinder"]


# ---------------------------------------------------------------- job runner

class Job:
    """One job at a time; its output is kept for the page to poll."""

    def __init__(self):
        self.lock = threading.Lock()
        self.lines = []
        self.version = 0
        self.status = "idle"  # idle | running | done | failed | stopped
        self.title = ""
        self.proc = None
        self.stop_requested = False

    def log(self, text):
        with self.lock:
            # Collapse consecutive progress-bar updates into a single line
            if self.lines and PROGRESS_RE.search(text) and PROGRESS_RE.search(self.lines[-1]):
                self.lines[-1] = text
            else:
                self.lines.append(text)
                del self.lines[:-MAX_LOG_LINES]
            self.version += 1

    def snapshot(self, since_version):
        with self.lock:
            data = {"status": self.status, "title": self.title, "version": self.version}
            if since_version != self.version:
                data["lines"] = list(self.lines)
            return data

    def start(self, title, cmd):
        with self.lock:
            if self.status == "running":
                return False
            self.status = "running"
            self.title = title
            self.lines = []
            self.version += 1
            self.stop_requested = False
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()
        return True

    def _run(self, cmd):
        try:
            ok = self.run_command(cmd)
            result = "stopped" if self.stop_requested else ("done" if ok else "failed")
        except Exception as exc:  # keep the server alive whatever happens
            self.log(f"[web] Error: {exc}")
            result = "failed"
        self.log(f"[web] {self.title}: {result}")
        with self.lock:
            self.status = result
            self.proc = None

    def run_command(self, cmd):
        self.log("$ mangabinder " + " ".join(cmd[len(self_command()):]))
        kwargs = {}
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen(cmd, cwd=LIBRARY, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, env=env, **kwargs)
        with self.lock:
            self.proc = proc

        # Split on \r as well as \n so progress bars show up as they update
        buf = b""
        for chunk in iter(lambda: proc.stdout.read1(4096), b""):
            buf += chunk
            *complete, buf = re.split(rb"[\r\n]", buf)
            for raw in complete:
                if raw.strip():
                    self.log(raw.decode("utf-8", "replace").rstrip())
        if buf.strip():
            self.log(buf.decode("utf-8", "replace").rstrip())

        code = proc.wait()
        with self.lock:
            self.proc = None
        if code != 0 and not self.stop_requested:
            self.log(f"[web] Command exited with code {code}")
        return code == 0

    def stop(self):
        with self.lock:
            if self.status != "running":
                return False
            self.stop_requested = True
            proc = self.proc
        if proc and proc.poll() is None:
            self.log("[web] Stopping...")
            if IS_WINDOWS:
                # /T also kills the converter's worker processes
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(proc.pid, signal.SIGTERM)
        return True


JOB = Job()


# ---------------------------------------------------------------- library

def subdirs(path):
    if not os.path.isdir(path):
        return []
    return [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]


def is_download_folder(path):
    if os.path.exists(os.path.join(path, STATE_FILE)):
        return True
    for name in subdirs(path)[:5]:
        if any(f.lower().endswith(IMAGE_EXTENSIONS) for f in os.listdir(os.path.join(path, name))):
            return True
    return False


def output_files(folder):
    path = os.path.join(LIBRARY, folder)
    if not os.path.isdir(path):
        return []
    files = [f for f in os.listdir(path) if os.path.splitext(f)[1].lower() in SERVED_TYPES]
    return sorted(files, key=natural_key)


def list_library():
    names = set()
    for name in subdirs(LIBRARY):
        if name.startswith("."):
            continue
        if name.endswith("_pdf"):
            names.add(name[:-len("_pdf")])
        elif not name.endswith(OUTPUT_SUFFIXES) and is_download_folder(os.path.join(LIBRARY, name)):
            names.add(name)

    library = []
    for name in sorted(names, key=natural_key):
        pdf_dir, vol_dir = name + "_pdf", name + "_pdf_volumes"
        volumes = output_files(vol_dir)
        cbz_dir = vol_dir + "_cbz" if output_files(vol_dir + "_cbz") else pdf_dir + "_cbz"
        library.append({
            "folder": name,
            "chapters": len(subdirs(os.path.join(LIBRARY, name))),
            "pdf_dir": pdf_dir,
            "chapter_pdfs": output_files(pdf_dir),
            "vol_dir": vol_dir,
            "volumes": volumes,
            "cbz_dir": cbz_dir,
            "cbz": output_files(cbz_dir),
        })
    return library


def open_in_file_manager(path):
    if IS_WINDOWS:
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = f"mangabinder/{__version__}"

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def _host_ok(self):
        # Rejects DNS-rebinding requests, which reach us under a foreign *domain name*.
        # When serving beyond loopback (--host 0.0.0.0) plain IP addresses are fine too.
        name = host_name(self.headers.get("Host") or "")
        if name in ("127.0.0.1", "localhost", "::1"):
            return True
        return ALLOW_IP_HOSTS and is_ip(name)

    def _send(self, code, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden host"})
        url = urlparse(self.path)
        if url.path == "/":
            page = PAGE.replace("{{VERSION}}", __version__).replace("{{REPO_URL}}", REPO_URL)
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if url.path == "/api/status":
            since = parse_qs(url.query).get("v", ["-1"])[0]
            return self._send(200, JOB.snapshot(int(since) if since.lstrip("-").isdigit() else -1))
        if url.path == "/api/library":
            return self._send(200, {"library": list_library(), "path": LIBRARY,
                                    "defaults": {"threads": DEFAULT_THREADS}})
        if url.path.startswith("/files/"):
            return self._serve_file(unquote(url.path[len("/files/"):]))
        self._send(404, {"error": "not found"})

    def _serve_file(self, rel):
        folder, _, name = rel.partition("/")
        ext = os.path.splitext(name)[1].lower()
        if (not folder.endswith(OUTPUT_SUFFIXES) or name != os.path.basename(name)
                or ext not in SERVED_TYPES or folder != os.path.basename(folder)):
            return self._send(404, {"error": "not found"})
        path = os.path.join(LIBRARY, folder, name)
        if not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        self.send_response(200)
        self.send_header("Content-Type", SERVED_TYPES[ext])
        self.send_header("Content-Length", str(os.path.getsize(path)))
        # PDFs open in the browser's viewer; CBZ files download
        disposition = "inline" if ext == ".pdf" else "attachment"
        self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{name}")
        self.end_headers()
        with open(path, "rb") as fh:
            try:
                shutil.copyfileobj(fh, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden host"})
        # Requiring JSON forces a CORS preflight, so other sites can't trigger jobs
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._send(415, {"error": "expected application/json"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, {"error": "invalid JSON"})

        path = urlparse(self.path).path
        if path == "/api/run":
            return self._run(body)
        if path == "/api/stop":
            return self._send(200, {"stopped": JOB.stop()})
        if path == "/api/open":
            folder = str(body.get("folder", ""))
            target = os.path.join(LIBRARY, folder) if folder else LIBRARY
            if folder != os.path.basename(folder) or not os.path.isdir(target):
                return self._send(404, {"error": "folder not found"})
            open_in_file_manager(target)
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def _run(self, body):
        action = body.get("action")
        title = str(body.get("title") or "").strip()
        cmd = self_command()

        if action in ("pipeline", "download"):
            base_url = str(body.get("base_url") or "").strip()
            pattern = str(body.get("pattern") or "").strip()
            start = str(body.get("start") or "").strip()
            if not re.match(r"^https?://[^/\s]+", base_url):
                return self._send(400, {"error": "Enter the full series page URL, starting with https://"})
            if start and not re.fullmatch(r"\d+(\.\d+)?", start):
                return self._send(400, {"error": "Start chapter must be a number"})
            try:
                threads = min(64, max(1, int(body.get("threads") or DEFAULT_THREADS)))
            except ValueError:
                return self._send(400, {"error": "Threads must be a number"})
            cmd += ["download", base_url, "--library", ".", "--threads", str(threads)]
            if pattern:
                cmd += ["--pattern", pattern]
            if start:
                cmd += ["--start", start]
            if not body.get("resume", True):
                cmd.append("--fresh")
            label = f"Download {site_folder(base_url)}"
            if action == "pipeline":
                cmd.append("--volumes" if body.get("merge") else "--convert")
                label += " + convert" + (" + merge volumes" if body.get("merge") else "")
                if body.get("merge") and title:
                    cmd += ["--title", title]
        elif action in ("convert", "merge", "cbz"):
            folder = str(body.get("folder") or "")
            item = next((i for i in list_library() if i["folder"] == folder), None)
            if not item:
                return self._send(400, {"error": f"Unknown folder: {folder}"})
            if action == "convert":
                cmd += ["convert", folder]
                label = f"Convert {folder}"
            elif action == "merge":
                cmd += ["merge", item["pdf_dir"]]
                if title:
                    cmd += ["--title", title]
                if body.get("overwrite"):
                    cmd.append("--overwrite")
                if body.get("dry_run"):
                    cmd.append("--dry-run")
                label = f"{'Preview volumes for' if body.get('dry_run') else 'Merge volumes for'} {folder}"
            else:
                source = item["vol_dir"] if item["volumes"] else item["pdf_dir"]
                cmd += ["cbz", source]
                label = f"Make CBZ for {folder}"
        else:
            return self._send(400, {"error": f"Unknown action: {action}"})

        if not JOB.start(label, cmd):
            return self._send(409, {"error": "Another job is already running"})
        self._send(200, {"ok": True})


def serve(library, port=8765, open_browser=True, host="127.0.0.1"):
    global LIBRARY, ALLOW_IP_HOSTS
    LIBRARY = os.path.abspath(library)
    os.makedirs(LIBRARY, exist_ok=True)
    ALLOW_IP_HOSTS = not is_loopback(host)

    server = None
    for candidate in range(port, port + 10):
        try:
            server = ThreadingHTTPServer((host, candidate), Handler)
            break
        except OSError:
            continue
    if server is None:
        print(f"[!] No free port between {port} and {port + 9}")
        return 1

    url = f"http://127.0.0.1:{server.server_port}/"
    print("==========================================")
    print(f" MangaBinder {__version__} running at {url}")
    print(f" Library: {LIBRARY}")
    if ALLOW_IP_HOSTS:
        print(f" Listening on {host}: anyone who can reach this machine on port")
        print(f" {server.server_port} can use the page (there is no login).")
    print(" Press Ctrl+C to stop")
    print("==========================================")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        JOB.stop()
        server.server_close()
    return 0


# ---------------------------------------------------------------- page

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MangaBinder</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect x='3' y='3' width='26' height='26' rx='6' fill='%233b5bdb'/%3E%3Cpath d='M10 9h5v14h-5zM17 9h5v14h-5z' fill='white'/%3E%3C/svg%3E">
<style>
  :root {
    --bg: #f4f5f7; --card: #ffffff; --text: #1d2330; --muted: #677084; --border: #dde1e8;
    --accent: #3b5bdb; --accent-soft: #edf2ff; --accent-text: #ffffff; --log-bg: #11151c; --log-text: #d6dbe4;
    --ok: #2b8a3e; --bad: #c92a2a; --warn: #e67700;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #12151b; --card: #1b1f27; --text: #e4e7ec; --muted: #939bab; --border: #2c323d;
      --accent: #5c7cfa; --accent-soft: #1f2640; --log-bg: #0b0d11; --log-text: #cfd5df;
      --ok: #51cf66; --bad: #ff6b6b; --warn: #ffa94d;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 1000px; margin: 0 auto; padding: 24px 16px 40px; display: grid; gap: 16px; }
  header { display: flex; align-items: center; gap: 12px; }
  .logo { width: 40px; height: 40px; border-radius: 10px; background: var(--accent); flex: none;
          display: grid; place-items: center; }
  h1 { font-size: 20px; margin: 0; }
  h2 { font-size: 15px; margin: 0 0 12px; }
  .sub { color: var(--muted); margin: 0; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
  label { display: grid; gap: 4px; font-weight: 500; }
  label small { color: var(--muted); font-weight: 400; }
  input[type=text], input[type=number] {
    width: 100%; padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--bg); color: var(--text); font: inherit; }
  .wide { grid-column: 1 / -1; }
  .checks { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 12px; }
  .checks label { display: flex; align-items: center; gap: 6px; font-weight: 400; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  button { font: inherit; padding: 7px 14px; border-radius: 6px; cursor: pointer;
           border: 1px solid var(--border); background: var(--card); color: var(--text); }
  button:hover:not(:disabled) { border-color: var(--accent); }
  button.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-text); }
  button.danger { color: var(--bad); }
  button:disabled { opacity: .5; cursor: not-allowed; }
  .row { border-top: 1px solid var(--border); padding: 12px 0; }
  .row:first-child { border-top: 0; padding-top: 0; }
  .name { font-weight: 600; word-break: break-all; }
  .stats { color: var(--muted); font-size: 13px; }
  .row .actions { margin-top: 8px; }
  .row button { padding: 5px 10px; font-size: 13px; }
  details { margin-top: 8px; }
  summary { cursor: pointer; color: var(--muted); }
  .files { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .files a { padding: 3px 8px; border: 1px solid var(--border); border-radius: 5px; background: var(--accent-soft);
             color: var(--accent); text-decoration: none; font-size: 13px; }
  .files a:hover { border-color: var(--accent); }
  .bar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px;
         margin-bottom: 10px; }
  .bar h2 { margin: 0; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600;
           border: 1px solid currentColor; }
  .badge.running { color: var(--warn); } .badge.done { color: var(--ok); }
  .badge.failed, .badge.stopped { color: var(--bad); } .badge.idle { color: var(--muted); }
  pre { margin: 0; background: var(--log-bg); color: var(--log-text); border-radius: 8px; padding: 12px;
        height: 300px; overflow: auto; font: 12px/1.45 ui-monospace, Consolas, monospace; white-space: pre-wrap;
        word-break: break-all; }
  .error { color: var(--bad); margin-top: 10px; min-height: 1em; }
  .empty { color: var(--muted); }
  .path { font: 12px ui-monospace, Consolas, monospace; color: var(--muted); word-break: break-all; }
  footer { color: var(--muted); font-size: 12px; text-align: center; }
  footer a { color: inherit; }
</style>
</head>
<body>
<main>
  <header>
    <div class="logo"><svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
      <path d="M3 3h7v16H3zM12 3h7v16h-7z" fill="white"/></svg></div>
    <div>
      <h1>MangaBinder</h1>
      <p class="sub">Download chapters, convert them to PDF, bind volumes and export CBZ.</p>
    </div>
  </header>

  <section class="card" id="download-card">
    <h2>Download</h2>
    <div class="grid">
      <label class="wide">Series page URL <small>The page that links to every chapter</small>
        <input type="text" id="base_url" placeholder="https://example.com/manga/series-name/">
      </label>
      <label>Chapter link pattern <small>Optional: text every chapter link contains</small>
        <input type="text" id="pattern" placeholder="auto-detect (.../chapter-12)">
      </label>
      <label>Start from chapter <small>Leave empty for all chapters</small>
        <input type="text" id="start" inputmode="decimal" placeholder="all">
      </label>
      <label>Threads <small>Chapters downloaded in parallel</small>
        <input type="number" id="threads" min="1" max="64">
      </label>
      <label>Series title <small>For the volume lookup; blank = guess</small>
        <input type="text" id="title" placeholder="auto">
      </label>
    </div>
    <div class="checks">
      <label><input type="checkbox" id="resume" checked> Resume (skip finished chapters and pages)</label>
      <label><input type="checkbox" id="merge"> Merge chapters into volume PDFs</label>
    </div>
    <div class="actions">
      <button class="primary" data-run="pipeline" id="run-pipeline">Download + convert to PDF</button>
      <button data-run="download">Download only</button>
    </div>
    <div class="error" id="form-error"></div>
  </section>

  <section class="card" id="activity-card">
    <div class="bar">
      <h2>Activity</h2>
      <div><span id="job-title" class="stats"></span> <span id="badge" class="badge idle">idle</span>
        <button class="danger" id="stop" disabled>Stop</button></div>
    </div>
    <pre id="log">Nothing running yet.</pre>
  </section>

  <section class="card" id="library-card">
    <div class="bar">
      <div><h2>Library</h2><div class="path" id="library-path"></div></div>
      <div><button id="open-library">Open folder</button> <button id="refresh">Refresh</button></div>
    </div>
    <div id="library" class="empty">Loading...</div>
  </section>

  <footer>MangaBinder {{VERSION}} · <a href="{{REPO_URL}}" target="_blank" rel="noopener">GitHub</a></footer>
</main>

<script>
const $ = (id) => document.getElementById(id);
const FIELDS = ["base_url", "pattern", "start", "threads", "title", "resume", "merge"];
let logVersion = -1, lastStatus = null, running = false;

function store(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }
function recall(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }

function formValues() {
  const v = {};
  for (const f of FIELDS) v[f] = $(f).type === "checkbox" ? $(f).checked : $(f).value;
  return v;
}

function restoreForm(defaults) {
  let saved = {};
  try { saved = JSON.parse(recall("form") || "{}"); } catch (e) {}
  for (const f of FIELDS) {
    const value = f in saved ? saved[f] : defaults[f];
    if (value === undefined) continue;
    if ($(f).type === "checkbox") $(f).checked = !!value; else $(f).value = value;
  }
}

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function run(payload) {
  $("form-error").textContent = "";
  try { await api("/api/run", payload); poll(); }
  catch (e) { $("form-error").textContent = e.message; }
}

document.querySelectorAll("[data-run]").forEach((btn) => btn.addEventListener("click", () => {
  const values = formValues();
  store("form", JSON.stringify(values));
  run({ action: btn.dataset.run, ...values });
}));
$("stop").addEventListener("click", () => api("/api/stop", {}).catch(() => {}));
$("refresh").addEventListener("click", loadLibrary);
$("open-library").addEventListener("click", () => api("/api/open", { folder: "" }).catch(() => {}));

function setRunning(isRunning) {
  running = isRunning;
  document.querySelectorAll("[data-run], [data-job]").forEach((b) => b.disabled = isRunning);
  $("stop").disabled = !isRunning;
}

async function poll() {
  try {
    const s = await api("/api/status?v=" + logVersion);
    if (s.lines) {
      const log = $("log");
      const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
      log.textContent = s.lines.length ? s.lines.join("\n") : "Starting...";
      if (atBottom) log.scrollTop = log.scrollHeight;
    }
    logVersion = s.version;
    $("badge").textContent = s.status;
    $("badge").className = "badge " + s.status;
    $("job-title").textContent = s.title;
    setRunning(s.status === "running");
    if (lastStatus === "running" && s.status !== "running") loadLibrary();
    lastStatus = s.status;
  } catch (e) {
    $("badge").textContent = "server offline";
    $("badge").className = "badge failed";
  }
}

function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  Object.assign(node, attrs);
  if (text !== undefined) node.textContent = text;
  return node;
}

function fileList(dir, files) {
  const wrap = el("div", { className: "files" });
  for (const f of files) {
    wrap.append(el("a", { href: "/files/" + encodeURIComponent(dir) + "/" + encodeURIComponent(f),
                          target: "_blank", rel: "noopener" }, f.replace(/\.(pdf|cbz)$/i, "")));
  }
  return wrap;
}

function jobButton(label, payload) {
  const b = el("button", {}, label);
  b.dataset.job = payload.action;
  b.disabled = running;
  b.addEventListener("click", () => run({ ...payload, title: $("title").value }));
  return b;
}

function section(label, dir, files, open) {
  const d = el("details", { open });
  d.append(el("summary", {}, `${label} (${files.length})`), fileList(dir, files));
  return d;
}

async function loadLibrary() {
  let data;
  try { data = await api("/api/library"); } catch (e) { return; }
  $("library-path").textContent = data.path;
  const box = $("library");
  box.replaceChildren();
  box.className = data.library.length ? "" : "empty";
  if (!data.library.length) { box.textContent = "No downloads yet - start one above."; return; }

  for (const item of data.library) {
    const row = el("div", { className: "row" });
    row.append(el("div", { className: "name" }, item.folder),
               el("div", { className: "stats" },
                  `${item.chapters} chapters downloaded · ${item.chapter_pdfs.length} chapter PDFs · ` +
                  `${item.volumes.length} volumes · ${item.cbz.length} CBZ`));

    const actions = el("div", { className: "actions" });
    if (item.chapters) actions.append(jobButton("Convert to PDF", { action: "convert", folder: item.folder }));
    if (item.chapter_pdfs.length) {
      actions.append(jobButton("Preview volumes", { action: "merge", folder: item.folder, dry_run: true }),
                     jobButton("Merge volumes", { action: "merge", folder: item.folder }),
                     jobButton("Make CBZ", { action: "cbz", folder: item.folder }));
    }
    const openTarget = item.volumes.length ? item.vol_dir : item.chapter_pdfs.length ? item.pdf_dir : item.folder;
    const open = el("button", {}, "Open folder");
    open.addEventListener("click", () => api("/api/open", { folder: openTarget }).catch(() => {}));
    actions.append(open);
    row.append(actions);

    if (item.volumes.length) row.append(section("Volumes", item.vol_dir, item.volumes, true));
    if (item.chapter_pdfs.length) row.append(section("Chapter PDFs", item.pdf_dir, item.chapter_pdfs, false));
    if (item.cbz.length) row.append(section("CBZ", item.cbz_dir, item.cbz, false));
    box.append(row);
  }
}

api("/api/library").then((d) => restoreForm(d.defaults)).catch(() => {});
loadLibrary();
poll();
setInterval(poll, 1000);
</script>
</body>
</html>
"""
