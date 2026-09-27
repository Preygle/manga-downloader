"""Offline end-to-end run: chapter images -> chapter PDFs -> volumes -> CBZ."""

import json
import zipfile

from PIL import Image
from pypdf import PdfReader

from mangabinder.cbz import cbz_folder
from mangabinder.convert import convert_folder
from mangabinder.volumes import MAP_FILENAME, merge_into_volumes


def make_library(root, chapters=4, pages=3):
    folder = root / "example.com"
    for chapter in range(1, chapters + 1):
        chapter_dir = folder / f"demo-chapter-{chapter}"
        chapter_dir.mkdir(parents=True)
        for page in range(1, pages + 1):
            Image.new("RGB", (60, 90), (chapter * 40, page * 60, 120)).save(chapter_dir / f"{page}.jpg")
    # One two-page spread in the last chapter
    Image.new("RGB", (180, 90), "gray").save(folder / f"demo-chapter-{chapters}" / f"{pages + 1}.png")
    # Empty files from a broken download are skipped, not fatal
    (folder / "demo-chapter-1" / "9.jpg").write_bytes(b"")
    return folder


def test_convert_merge_cbz(tmp_path):
    folder = make_library(tmp_path)

    pdf_dir = convert_folder(str(folder), workers=1)
    pdfs = sorted(p.name for p in (tmp_path / "example.com_pdf").iterdir())
    assert pdfs == [f"demo-chapter-{n}.pdf" for n in range(1, 5)]
    assert len(PdfReader(tmp_path / "example.com_pdf" / "demo-chapter-4.pdf").pages) == 4

    # Converting again skips chapters whose PDF is newer than their images
    first_mtime = (tmp_path / "example.com_pdf" / "demo-chapter-1.pdf").stat().st_mtime
    convert_folder(str(folder), workers=1)
    assert (tmp_path / "example.com_pdf" / "demo-chapter-1.pdf").stat().st_mtime == first_mtime

    # A hand-written map takes priority over the online lookup, so this stays offline
    volume_dir = tmp_path / "example.com_pdf_volumes"
    volume_dir.mkdir()
    (volume_dir / MAP_FILENAME).write_text(json.dumps({"mapping": {"1": 1, "2": 1, "3": 2, "4": 2}}))
    written = merge_into_volumes(pdf_dir, title="Demo")
    assert [p.split("\\")[-1].split("/")[-1] for p in written] == ["Demo v01.pdf", "Demo v02.pdf"]
    reader = PdfReader(volume_dir / "Demo v02.pdf")
    assert len(reader.pages) == 7
    assert [item.title for item in reader.outline] == ["Chapter 3", "Chapter 4"]

    cbz_dir = cbz_folder(str(volume_dir), workers=1, dpi=36)
    with zipfile.ZipFile(tmp_path / "example.com_pdf_volumes_cbz" / "Demo v02.cbz") as cbz:
        # 3 + 3 plain pages, then the spread: blank filler + right half + left half
        assert len(cbz.namelist()) == 9
    assert cbz_dir.endswith("example.com_pdf_volumes_cbz")
