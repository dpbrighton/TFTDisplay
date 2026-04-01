#!/usr/bin/env python3
"""
audit_photo_orientation.py

Scans a photo library and reports EXIF orientation status.
Run this on your Mac with the NAS mounted, or on the NAS directly.

Usage:
    python3 audit_photo_orientation.py /Volumes/Photos
    python3 audit_photo_orientation.py /Volumes/Photos --csv report.csv

Requires: Pillow  (pip3 install pillow)
Optional: opencv-python  (pip3 install opencv-python)
          — needed for face-detection-based orientation checking
"""

import argparse
import csv
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps, ExifTags, UnidentifiedImageError
except ImportError:
    sys.exit("Pillow not installed. Run: pip3 install pillow")

SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
ORIENTATION_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "Orientation")

# Orientation values that actually rotate the image (not upright/normal)
NON_UPRIGHT = {2, 3, 4, 5, 6, 7, 8}  # 1 = normal/upright


def get_exif_orientation(img):
    """Return EXIF orientation value, or None if absent."""
    try:
        exif = img._getexif()
        if exif:
            return exif.get(ORIENTATION_TAG)
    except Exception:
        pass
    return None


def classify(path):
    """
    Returns a dict with info about one image file.
    category is one of:
        'exif_upright'    — has EXIF orientation = 1 (already upright in pixels)
        'exif_rotated'    — has EXIF orientation 2-8 (server will auto-correct)
        'no_exif_portrait'— no EXIF orientation, pixel dimensions already portrait
        'no_exif_landscape'— no EXIF orientation, landscape pixels — SUSPECT
        'no_exif_square'  — no EXIF orientation, roughly square
        'error'           — could not open
    """
    try:
        with Image.open(path) as img:
            orientation = get_exif_orientation(img)
            w, h = img.size

        ratio = w / h if h > 0 else 1.0

        if orientation is not None:
            category = "exif_rotated" if orientation in NON_UPRIGHT else "exif_upright"
        else:
            if ratio < 0.9:
                category = "no_exif_portrait"
            elif ratio > 1.1:
                category = "no_exif_landscape"
            else:
                category = "no_exif_square"

        return {
            "path": str(path),
            "category": category,
            "width": w,
            "height": h,
            "orientation_tag": orientation,
        }

    except (UnidentifiedImageError, Exception) as e:
        return {
            "path": str(path),
            "category": "error",
            "width": 0,
            "height": 0,
            "orientation_tag": None,
            "error": str(e),
        }


def scan(root):
    results = []
    root = Path(root)
    files = [
        p for p in root.rglob("*")
        if p.suffix.lower() in SUPPORTED and p.is_file()
    ]
    total = len(files)
    print(f"Found {total} image files. Scanning…")
    for i, path in enumerate(files, 1):
        if i % 500 == 0 or i == total:
            print(f"  {i}/{total}", end="\r", flush=True)
        results.append(classify(path))
    print()
    return results


def print_report(results):
    from collections import Counter
    counts = Counter(r["category"] for r in results)
    total = len(results)

    print("\n── Audit Report ─────────────────────────────────────")
    print(f"  Total images scanned          : {total:>6}")
    print(f"  EXIF orientation present")
    print(f"    Already upright (tag=1)     : {counts['exif_upright']:>6}  (no action needed)")
    print(f"    Rotated (tag 2-8)           : {counts['exif_rotated']:>6}  ✓ server will auto-correct")
    print(f"  No EXIF orientation tag")
    print(f"    Portrait pixels (h > w)     : {counts['no_exif_portrait']:>6}  (probably fine)")
    print(f"    Square pixels               : {counts['no_exif_square']:>6}  (probably fine)")
    print(f"    Landscape pixels  ← SUSPECT : {counts['no_exif_landscape']:>6}  (may be sideways portraits)")
    print(f"  Errors (unreadable)           : {counts['error']:>6}")
    print("─────────────────────────────────────────────────────\n")

    suspect = [r for r in results if r["category"] == "no_exif_landscape"]
    if suspect:
        print(f"  Suspect files (landscape pixels, no EXIF) — first 20:")
        for r in suspect[:20]:
            print(f"    {r['width']}x{r['height']}  {r['path']}")
        if len(suspect) > 20:
            print(f"    … and {len(suspect) - 20} more (use --csv to export full list)")
    else:
        print("  No suspect files found — all landscape images have EXIF or are genuinely landscape.")


def write_csv(results, csv_path):
    fieldnames = ["path", "category", "width", "height", "orientation_tag"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"Full results written to: {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Audit photo EXIF orientation")
    parser.add_argument("path", help="Root folder to scan (e.g. /Volumes/Photos)")
    parser.add_argument("--csv", metavar="FILE", help="Export full results to CSV")
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        sys.exit(f"Not a directory: {args.path}")

    results = scan(args.path)
    print_report(results)

    if args.csv:
        write_csv(results, args.csv)


if __name__ == "__main__":
    main()
