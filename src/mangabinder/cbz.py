"""Convert PDFs into CBZ comic archives for e-readers and comic apps.

Two-page spreads (pages much wider than tall) are split into their halves in
right-to-left manga order, with a blank page inserted where needed so that
spreads stay on facing pages.
"""

import gc
import io
import os
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image


def _write_page(cbz, image, page_number, quality):
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    cbz.writestr(f"page_{page_number:04d}.jpg", buffer.getvalue())


def pdf_to_cbz(pdf_path, cbz_path, dpi=150, split_spreads=True, ratio_threshold=1.3, jpeg_quality=85):
    """Render every PDF page to JPEG inside a CBZ. Returns the seconds taken."""
    started = time.time()
    part_path = str(cbz_path) + ".part"
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        # JPEGs don't compress further, so store them as-is
        with zipfile.ZipFile(part_path, "w", zipfile.ZIP_STORED) as cbz:
            page_number = 1
            for index in range(len(pdf)):
                page = pdf[index]
                image = page.render(scale=dpi / 72).to_pil().convert("RGB")
                page.close()
                width, height = image.size
                if split_spreads and width > height * ratio_threshold:
                    if page_number % 2 != 0:
                        # Keep the spread on facing pages
                        _write_page(cbz, Image.new("RGB", (width // 2, height), "white"),
                                    page_number, jpeg_quality)
                        page_number += 1
                    # Right half first: manga reads right to left
                    _write_page(cbz, image.crop((width // 2, 0, width, height)), page_number, jpeg_quality)
                    _write_page(cbz, image.crop((0, 0, width // 2, height)), page_number + 1, jpeg_quality)
                    page_number += 2
                else:
                    _write_page(cbz, image, page_number, jpeg_quality)
                    page_number += 1
                image.close()
                gc.collect()
    finally:
        pdf.close()
    os.replace(part_path, cbz_path)
    return time.time() - started


def _worker(args):
    pdf_path, cbz_path, options = args
    try:
        return pdf_path, pdf_to_cbz(pdf_path, cbz_path, **options), None
    except Exception as exc:
        return pdf_path, None, str(exc)


def cbz_folder(input_dir, output_dir=None, workers=2, overwrite=False, **options):
    """Convert every PDF in input_dir to <output_dir>/<name>.cbz. Returns the output folder."""
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Not a folder: {input_dir}")
    output_dir = Path(output_dir) if output_dir else input_dir.with_name(input_dir.name + "_cbz")
    output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found in {input_dir}")

    tasks = []
    for pdf in pdfs:
        cbz = output_dir / (pdf.stem + ".cbz")
        if cbz.exists() and not overwrite:
            print(f"[=] Skipping existing: {cbz.name}")
            continue
        tasks.append((str(pdf), str(cbz), options))
    if not tasks:
        print("[+] Nothing to do - every PDF already has a CBZ.")
        return str(output_dir)

    print(f"[+] Converting {len(tasks)} PDFs to CBZ with {workers} worker(s)")
    with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        for future in as_completed([pool.submit(_worker, task) for task in tasks]):
            pdf_path, elapsed, error = future.result()
            if error:
                print(f"[!] {Path(pdf_path).name}: {error}")
            else:
                print(f"[OK] {Path(pdf_path).stem}.cbz ({elapsed:.1f}s)")
    print(f"[+] CBZ files saved to: {output_dir}")
    return str(output_dir)
