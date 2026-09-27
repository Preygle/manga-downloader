"""Merge per-chapter PDFs into per-volume PDFs.

The chapter -> volume mapping is resolved online (see volume_map.py). Run it
straight after a download, or point it at any folder of chapter PDFs you
already have:

    mangabinder merge example.com_pdf
    mangabinder merge example.com_pdf --dry-run
    mangabinder merge example.com_pdf --title "Monster"

The resolved mapping is written to volume_map.json inside the output folder.
Edit that file and re-run to correct anything the online source got wrong -
an existing map file is always preferred over a fresh lookup.
"""

import json
import os
from collections import defaultdict

from pypdf import PdfWriter

from mangabinder.volume_map import (
    format_chapter_number,
    get_volume_map,
    guess_series_title,
    parse_chapter_number,
)

MAP_FILENAME = "volume_map.json"


def collect_chapter_pdfs(input_dir):
    """[(chapter_number, path)] sorted by chapter number."""
    found = []
    for name in os.listdir(input_dir):
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path) or not name.lower().endswith(".pdf"):
            continue
        num = parse_chapter_number(name)
        if num is None:
            print(f"[!] Skipping (no chapter number in name): {name}")
            continue
        found.append((num, path))
    return sorted(found, key=lambda item: item[0])


def safe_filename(name):
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name.strip().rstrip(".") or "manga"


def load_map_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"[!] Could not read {path}: {exc}")
        return None, None
    mapping = {str(k): int(v) for k, v in (data.get("mapping") or {}).items()}
    return mapping, data.get("info", {})


def save_map_file(path, mapping, info):
    payload = {
        "_comment": "Edit 'mapping' (chapter -> volume) and re-run to override the online lookup.",
        "info": info,
        "mapping": {k: v for k, v in sorted(mapping.items(), key=lambda kv: float(kv[0]))},
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def merge_volume(chapter_pdfs, output_path):
    """Merge chapter PDFs into one volume, bookmarking each chapter."""
    writer = PdfWriter()
    page_total = 0
    for num, path in chapter_pdfs:
        start = page_total
        try:
            writer.append(path, import_outline=False)
        except Exception as exc:
            print(f"    [!] Failed to append {os.path.basename(path)}: {exc}")
            continue
        page_total = len(writer.pages)
        if page_total > start:
            writer.add_outline_item(f"Chapter {format_chapter_number(num)}", start)
    if page_total == 0:
        return 0
    with open(output_path, "wb") as fh:
        writer.write(fh)
    writer.close()
    return page_total


def merge_into_volumes(input_dir, output_dir=None, title=None, series_id=None,
                       source=None, dry_run=False, use_cache=True, overwrite=False,
                       verbose=True):
    """Resolve the volume mapping and merge. Returns the list of files written."""
    input_dir = os.path.abspath(input_dir)
    if not os.path.isdir(input_dir):
        print(f"[!] Not a folder: {input_dir}")
        return []

    chapters = collect_chapter_pdfs(input_dir)
    if not chapters:
        print(f"[!] No chapter PDFs found in {input_dir}")
        return []

    output_dir = output_dir or (input_dir.rstrip("/\\") + "_volumes")
    chapter_numbers = [num for num, _ in chapters]

    if not title:
        title = guess_series_title([os.path.basename(p) for _, p in chapters])
    if not title:
        title = os.path.basename(input_dir)
    print(f"[+] {len(chapters)} chapter PDFs in {input_dir}")
    print(f"[+] Series title: '{title}'")

    # An existing map file always wins - it is the user's manual override.
    map_path = os.path.join(output_dir, MAP_FILENAME)
    mapping, info = (None, None)
    if os.path.exists(map_path):
        mapping, info = load_map_file(map_path)
        if mapping:
            print(f"[+] Using existing mapping from {map_path} ({len(mapping)} chapters)")

    if not mapping:
        mapping, info = get_volume_map(title, chapter_numbers, series_id=series_id,
                                       source=source, use_cache=use_cache, verbose=verbose)
    if not mapping:
        print("[!] Could not determine a chapter -> volume mapping. Nothing merged.")
        print("    Try --title \"Exact Series Name\", or write volume_map.json by hand.")
        return []

    by_volume = defaultdict(list)
    unmapped = []
    for num, path in chapters:
        volume = mapping.get(format_chapter_number(num))
        if volume is None:
            unmapped.append(num)
            continue
        by_volume[int(volume)].append((num, path))

    if info.get("approximate"):
        print("[!] NOTE: volume boundaries are APPROXIMATE (source had no per-chapter")
        print(f"    volume data). Check/edit {MAP_FILENAME} in the output folder.")
    if unmapped:
        preview = ", ".join(format_chapter_number(n) for n in unmapped[:10])
        print(f"[!] {len(unmapped)} chapters have no volume and were skipped: {preview}")

    print(f"\n--- Plan: {len(by_volume)} volumes ---")
    for volume in sorted(by_volume):
        nums = sorted(n for n, _ in by_volume[volume])
        print(f"  Volume {volume:02d}: {len(nums):3d} chapters  "
              f"({format_chapter_number(nums[0])}-{format_chapter_number(nums[-1])})")

    if dry_run:
        print("\n[dry-run] Nothing written.")
        return []

    os.makedirs(output_dir, exist_ok=True)
    save_map_file(map_path, mapping, info)

    written = []
    safe_title = safe_filename(title)
    print()
    for volume in sorted(by_volume):
        out_path = os.path.join(output_dir, f"{safe_title} v{volume:02d}.pdf")
        if os.path.exists(out_path) and not overwrite:
            print(f"  [=] Skipping existing: {os.path.basename(out_path)}")
            written.append(out_path)
            continue
        ordered = sorted(by_volume[volume], key=lambda item: item[0])
        pages = merge_volume(ordered, out_path)
        if pages:
            print(f"  [OK] {os.path.basename(out_path)}  "
                  f"({len(ordered)} chapters, {pages} pages)")
            written.append(out_path)
        else:
            print(f"  [!] Volume {volume} produced no pages - skipped.")

    print(f"\n[+] {len(written)} volume PDFs in {output_dir}")
    print(f"[+] Mapping saved to {map_path}")
    return written
