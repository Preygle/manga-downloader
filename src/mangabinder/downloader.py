"""Scrape a manga site's chapter list and download every chapter's images in parallel.

Works with the common "reader" layout: the start page links to each chapter with
<a href>, and each chapter page shows its pages as <img> tags (lazy-load
attributes such as data-src are understood too).

Progress is recorded in <folder>/download_state.txt, so an interrupted run can
resume without fetching finished chapters again.
"""

import html as html_lib
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from mangabinder import __version__
from mangabinder.volume_map import parse_chapter_number

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              f"(KHTML, like Gecko) Chrome/124.0 Safari/537.36 mangabinder/{__version__}")
STATE_FILE = "download_state.txt"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

_HREF_RE = re.compile(r"""<a\s[^>]*?\bhref\s*=\s*["']([^"']+)["']""", re.I)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
_IMAGE_URL_RE = re.compile(r"\.(jpe?g|png|webp)\b", re.I)
_AUTO_CHAPTER_RE = re.compile(r"chapter[-_/]?\d", re.I)
# Site furniture that shares the page with the manga pages (comment avatars, emoji, logos)
_NOT_A_PAGE_RE = re.compile(r"avatar|gravatar|emoji|smilies|favicon|/logo", re.I)
# Lazy-loading readers keep the real URL in a data-* attribute and a placeholder in src
_IMG_ATTRS = ("data-src", "data-lazy-src", "data-original", "src")


class DownloadError(Exception):
    pass


@dataclass
class DownloadResult:
    folder: str
    found: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0


def site_folder(base_url):
    """'https://www.example.com/manga/x' -> 'example.com' (the download folder name)."""
    host = re.sub(r"https?://(www\.)?([^/]+).*", r"\2", base_url.strip())
    return re.sub(r'[<>:"/\\|?*]', "_", host)  # a port can't be in a folder name: localhost:8080 -> localhost_8080


def fetch(url, referer=None, timeout=30, retries=3):
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise  # a 404/403 won't fix itself
            last_error = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        time.sleep(1 + attempt * 2)
    raise last_error


def find_chapter_links(page_html, page_url, pattern=""):
    """Chapter URLs on a series page, in page order.

    With a pattern, keep links containing it (e.g. '/manga/monster-chapter-').
    Without one, keep same-site links whose path looks like '.../chapter-12'.
    """
    host = urlparse(page_url).netloc
    links, seen = [], set()
    for href in _HREF_RE.findall(page_html):
        href = html_lib.unescape(href).strip()
        url = urljoin(page_url, href)
        if pattern:
            if pattern not in href and pattern not in url:
                continue
        elif urlparse(url).netloc != host or not _AUTO_CHAPTER_RE.search(urlparse(url).path):
            continue
        key = url.split("#")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            links.append(url)
    return links


def find_images(page_html, page_url):
    """Image URLs on a chapter page, in reading order."""
    images, seen = [], set()
    for tag in _IMG_TAG_RE.findall(page_html):
        src = None
        for attr in _IMG_ATTRS:
            match = re.search(r"""(?:^|\s)%s\s*=\s*["']([^"']+)["']""" % re.escape(attr), tag, re.I)
            if match and not match.group(1).strip().startswith("data:"):
                src = match.group(1).strip()
                break
        if not src or _NOT_A_PAGE_RE.search(tag):
            continue
        url = urljoin(page_url, html_lib.unescape(src))
        if _IMAGE_URL_RE.search(url) and url not in seen:
            seen.add(url)
            images.append(url)
    return images


def chapter_name(url):
    segments = [s for s in urlparse(url).path.split("/") if s]
    name = segments[-1] if segments else "chapter"
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def image_extension(url):
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext if ext in IMAGE_EXTENSIONS else ".jpg"


def read_state(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return {line.strip().rsplit(":", 1)[0] for line in fh if line.strip().endswith(":COMPLETED")}


def download(base_url, pattern="", library=".", threads=16, start=None, resume=True, log=print):
    """Download every chapter linked from base_url into <library>/<site folder>."""
    result = DownloadResult(folder=os.path.normpath(os.path.join(library, site_folder(base_url))))
    os.makedirs(result.folder, exist_ok=True)
    state_path = os.path.join(result.folder, STATE_FILE)
    if not resume and os.path.exists(state_path):
        os.remove(state_path)

    log(f"Fetching chapter links from {base_url} ...")
    page = fetch(base_url).decode("utf-8", "replace")
    chapters = find_chapter_links(page, base_url, pattern)
    if not chapters:
        raise DownloadError("No chapters found - check the URL, or pass the chapter pattern "
                            "(the part every chapter link shares, e.g. /manga/title-chapter-).")
    result.found = len(chapters)

    completed = read_state(state_path) if resume else set()
    todo = []
    for url in chapters:
        name = chapter_name(url)
        if start is not None:
            number = parse_chapter_number(name)
            if number is not None and number < start:
                continue
        if name in completed:
            result.skipped += 1
            continue
        todo.append((url, name))

    summary = f"Found {result.found} chapters, {len(todo)} to download"
    if result.skipped:
        summary += f", {result.skipped} already done"
    log(summary + ".")

    cancel = threading.Event()
    state_lock = threading.Lock()

    def download_chapter(url, name):
        out_dir = os.path.join(result.folder, name)
        os.makedirs(out_dir, exist_ok=True)
        log(f">>> Downloading {name}")
        images = find_images(fetch(url, referer=base_url).decode("utf-8", "replace"), url)
        if not images:
            raise DownloadError("no images found on the chapter page")
        for index, image_url in enumerate(images, 1):
            if cancel.is_set():
                return False
            path = os.path.join(out_dir, f"{index}{image_extension(image_url)}")
            if resume and os.path.isfile(path) and os.path.getsize(path) > 0:
                continue
            data = fetch(image_url, referer=url)
            # Write to a temp name first so a crash never leaves a truncated page behind
            with open(path + ".part", "wb") as fh:
                fh.write(data)
            os.replace(path + ".part", path)
        with state_lock, open(state_path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}:COMPLETED\n")
        log(f"<<< Finished {name} ({len(images)} pages)")
        return True

    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        futures = {pool.submit(download_chapter, url, name): name for url, name in todo}
        try:
            for future in as_completed(futures):
                try:
                    if future.result():
                        result.downloaded += 1
                except Exception as exc:
                    result.failed += 1
                    log(f"[!] {futures[future]}: {exc}")
        except KeyboardInterrupt:
            cancel.set()
            pool.shutdown(wait=False, cancel_futures=True)
            raise

    log(f"Done: {result.downloaded} downloaded, {result.skipped} skipped, {result.failed} failed.")
    log(f"Saved under: {result.folder}")
    return result
