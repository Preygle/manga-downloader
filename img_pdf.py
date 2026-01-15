import os
import time
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm

PARENT_FOLDER = "readoshino.com"      # folder containing chapter folders
OUTPUT_FOLDER = PARENT_FOLDER + "_pdf"         # PDFs will be saved here

MAX_WORKERS = max(1, os.cpu_count() // 2)  # SAFE parallelism

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def convert_folder_to_pdf(folder_path):
    folder_name = os.path.basename(os.path.normpath(folder_path))
    output_pdf = os.path.join(OUTPUT_FOLDER, f"{folder_name}.pdf")

    # File name sorting 1 -> 2 and not 1 -> 10 
    images = sorted(
        [
            f for f in os.listdir(folder_path)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        ],
        key=lambda x: int(os.path.splitext(x)[0])
    )

    if not images:
        return f"{folder_name}: no images"

    pil_images = []

    for img_name in tqdm(
        images,
        desc=f"Converting {folder_name}",
        position=0,
        leave=False
    ):
        img_path = os.path.join(folder_path, img_name)
        img = Image.open(img_path).convert("RGB")
        pil_images.append(img)

    pil_images[0].save(
        output_pdf,
        save_all=True,
        append_images=pil_images[1:]
    )

    return f"{folder_name}: {len(images)} images → PDF"


def main():
    start_time = time.perf_counter()

    folders = [
        os.path.join(PARENT_FOLDER, d)
        for d in os.listdir(PARENT_FOLDER)
        if os.path.isdir(os.path.join(PARENT_FOLDER, d))
    ]

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(tqdm(
            executor.map(convert_folder_to_pdf, folders),
            total=len(folders),
            desc="Folders processed"
        ))

    end_time = time.perf_counter()
    elapsed_ms = int((end_time - start_time) * 1000)

    print("\n--- Summary ---")
    for r in results:
        print(r)

    print(f"\nTotal time: {elapsed_ms} ms")


if __name__ == "__main__":
    main()
