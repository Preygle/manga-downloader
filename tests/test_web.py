import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from PIL import Image

from mangabinder import web


@pytest.fixture
def server(tmp_path, monkeypatch):
    chapter = tmp_path / "example.com" / "demo-chapter-1"
    chapter.mkdir(parents=True)
    Image.new("RGB", (10, 10)).save(chapter / "1.jpg")
    (tmp_path / "example.com_pdf").mkdir()
    (tmp_path / "example.com_pdf" / "demo-chapter-1.pdf").write_bytes(b"%PDF-1.4 test")
    (tmp_path / "venv").mkdir()  # unrelated folders are not listed

    monkeypatch.setattr(web, "LIBRARY", str(tmp_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def request(url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {})
    if body is not None and "Content-Type" not in (headers or {}):
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_page_and_library(server):
    status, body = request(server + "/")
    assert status == 200 and b"MangaBinder" in body
    status, body = request(server + "/api/library")
    library = json.loads(body)["library"]
    assert [item["folder"] for item in library] == ["example.com"]
    assert library[0]["chapters"] == 1
    assert library[0]["chapter_pdfs"] == ["demo-chapter-1.pdf"]


def test_serves_output_files_only(server):
    status, body = request(server + "/files/example.com_pdf/demo-chapter-1.pdf")
    assert status == 200 and body.startswith(b"%PDF")
    assert request(server + "/files/..%2Fsecret.pdf")[0] == 404
    assert request(server + "/files/example.com/1.jpg")[0] == 404


def test_rejects_foreign_hosts_and_form_posts(server):
    assert request(server + "/api/library", headers={"Host": "evil.example"})[0] == 403
    status, _ = request(server + "/api/run", body={"action": "download"},
                        headers={"Content-Type": "text/plain"})
    assert status == 415


def test_validates_run_requests(server):
    status, body = request(server + "/api/run", body={"action": "download", "base_url": "not a url"})
    assert status == 400 and b"https://" in body
    status, body = request(server + "/api/run", body={"action": "convert", "folder": "../etc"})
    assert status == 400


def test_ip_hosts_only_allowed_when_serving_beyond_loopback(server, monkeypatch):
    assert web.host_name("[::1]:8765") == "::1"
    assert web.host_name("localhost") == "localhost"
    assert web.is_loopback("127.0.0.1") and not web.is_loopback("0.0.0.0")

    assert request(server + "/api/library", headers={"Host": "192.168.1.20:8765"})[0] == 403
    monkeypatch.setattr(web, "ALLOW_IP_HOSTS", True)  # as with --host 0.0.0.0
    assert request(server + "/api/library", headers={"Host": "192.168.1.20:8765"})[0] == 200
    # Domain names are still refused, which is what blocks DNS rebinding
    assert request(server + "/api/library", headers={"Host": "evil.example:8765"})[0] == 403
