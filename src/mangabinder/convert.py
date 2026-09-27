"""Convert downloaded chapter folders (one folder of images per chapter) into PDFs."""

import os
import re
import time
from concurrent.futures import ProcessPoolExecutor

from PIL import Image, ImageFile
from tqdm import tqdm

ImageFile.LOAD_TRUNCATED_IMAGES = True

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_WORKERS = max(1, (os.cpu_count() or 2) // 2)


def _page_key(name):
    # Sort 1, 2, ... 10 numerically rather than 1, 10, 2
    stem = os.path.splitext(name)[0]
    return (0, int(stem), "") if stem.isdigit() else (1, 0, name)


def chapter_images(folder):
    return sorted((f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXTENSIONS)), key=_page_key)


def is_up_to_date(pdf_path, folder, images):
    if not os.path.exists(pdf_path):
        return False
    newest = max(os.path.getmtime(os.path.join(folder, name)) for name in images)
    return os.path.getmtime(pdf_path) >= newest


def convert_chapter(args):
    folder, output_folder, overwrite = args
    name = os.path.basename(os.path.normpath(folder))
    output_pdf = os.path.join(output_folder, f"{name}.pdf")

    images = chapter_images(folder)
    if not images:
        return f"{name}: no images"
    if not overwrite and is_up_to_date(output_pdf, folder, images):
        return f"{name}: up to date"

    pages = []
    for image_name in images:
        path = os.path.join(folder, image_name)
        if os.path.getsize(path) == 0:
            print(f"Skipping 0-byte file: {name}/{image_name}")
            continue
        try:
            image = Image.open(path).convert("RGB")
            image.load()  # surface truncated files here rather than at save time
            pages.append(image)
        except Exception as exc:
            print(f"Error reading {name}/{image_name}: {exc}")

    if not pages:
        return f"{name}: no valid images"

    pages[0].save(output_pdf + ".part", format="PDF", save_all=True, append_images=pages[1:])
    os.replace(output_pdf + ".part", output_pdf)
    return f"{name}: {len(pages)} pages -> PDF"


def convert_folder(input_folder, output_folder=None, workers=DEFAULT_WORKERS, overwrite=False):
    """Build <input>_pdf/<chapter>.pdf for every chapter folder. Returns the output folder."""
    input_folder = os.path.normpath(input_folder)
    if not os.path.isdir(input_folder):
        raise FileNotFoundError(f"Input folder '{input_folder}' does not exist.")
    output_folder = output_folder or input_folder + "_pdf"
    os.makedirs(output_folder, exist_ok=True)

    chapters = sorted(
        (os.path.join(input_folder, d) for d in os.listdir(input_folder)
         if os.path.isdir(os.path.join(input_folder, d))),
        key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", os.path.basename(p))],
    )
    if not chapters:
        raise FileNotFoundError(f"No chapter folders found in '{input_folder}'.")

    started = time.perf_counter()
    tasks = [(folder, output_folder, overwrite) for folder in chapters]
    with ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
        results = list(tqdm(executor.map(convert_chapter, tasks), total=len(tasks), desc="Chapters"))

    converted = sum(r.endswith("-> PDF") for r in results)
    current = sum(r.endswith("up to date") for r in results)
    for line in results:
        if not line.endswith(("-> PDF", "up to date")):
            print(f"[!] {line}")
    print(f"[+] {converted} chapter PDFs written, {current} already up to date "
          f"({time.perf_counter() - started:.1f}s)")
    print(f"[+] PDFs saved to: {output_folder}")
    return output_folder
