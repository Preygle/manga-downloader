import os
import time
import argparse
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm

MAX_WORKERS = max(1, os.cpu_count() // 2)  # SAFE parallelism

def convert_folder_to_pdf(args):
    folder_path, output_folder = args
    folder_name = os.path.basename(os.path.normpath(folder_path))
    output_pdf = os.path.join(output_folder, f"{folder_name}.pdf")

    # File name sorting 1 -> 2 and not 1 -> 10 
    images = sorted(
        [
            f for f in os.listdir(folder_path)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        ],
        key=lambda x: int(os.path.splitext(x)[0]) if os.path.splitext(x)[0].isdigit() else x
    )

    if not images:
        return f"{folder_name}: no images"

    pil_images = []

    for img_name in images: # Removed inner tqdm to keep output clean with parallel exec
        img_path = os.path.join(folder_path, img_name)
        try:
            img = Image.open(img_path).convert("RGB")
            pil_images.append(img)
        except Exception as e:
            print(f"Error reading {img_name}: {e}")

    if not pil_images:
        return f"{folder_name}: no valid images"

    pil_images[0].save(
        output_pdf,
        save_all=True,
        append_images=pil_images[1:]
    )

    return f"{folder_name}: {len(images)} images -> PDF"


def main():
    parser = argparse.ArgumentParser(description="Convert manga images folder to directory of PDFs")
    parser.add_argument("--input_folder", type=str, default="readoshino.com", help="Input folder containing chapter subfolders")
    args = parser.parse_args()

    parent_folder = args.input_folder
    output_folder = parent_folder + "_pdf"

    if not os.path.exists(parent_folder):
        print(f"Error: Input folder '{parent_folder}' does not exist.")
        return

    os.makedirs(output_folder, exist_ok=True)

    start_time = time.perf_counter()

    folders = [
        os.path.join(parent_folder, d)
        for d in os.listdir(parent_folder)
        if os.path.isdir(os.path.join(parent_folder, d))
    ]

    # Prepare arguments for mapper (folder_path, output_folder)
    task_args = [(f, output_folder) for f in folders]

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(tqdm(
            executor.map(convert_folder_to_pdf, task_args),
            total=len(folders),
            desc="Folders processed"
        ))

    end_time = time.perf_counter()
    elapsed_ms = int((end_time - start_time) * 1000)

    print("\n--- Summary ---")
    for r in results:
        print(r)

    print(f"\nTotal time: {elapsed_ms} ms")
    print(f"PDFs saved to: {output_folder}")


if __name__ == "__main__":
    main()
