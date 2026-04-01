#!/usr/bin/env python3
"""
fix_photo_orientation.py

For photos that have NO EXIF orientation tag and landscape pixel dimensions,
uses face detection to determine the correct orientation and writes it back
as an EXIF orientation tag.

Run audit_photo_orientation.py first to understand the scope.

Usage:
    # Dry run — shows what would change, writes nothing
    python3 fix_photo_orientation.py /Volumes/Photos

    # Apply changes — writes EXIF orientation tags
    python3 fix_photo_orientation.py /Volumes/Photos --apply

    # Save a report of all decisions
    python3 fix_photo_orientation.py /Volumes/Photos --apply --csv ~/Desktop/orientation_fixes.csv

Requires: pillow, opencv-python, piexif
    pip install pillow opencv-python piexif

Notes:
    - Only modifies files with NO existing EXIF orientation and landscape pixels
    - Writes EXIF orientation tag only — does NOT re-encode/rotate image pixels
    - The photo server already calls ImageOps.exif_transpose so it will pick up the tag
    - Photos where no face is detected are left untouched and reported separately
"""

import argparse
import csv
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ExifTags, UnidentifiedImageError
except ImportError:
    sys.exit("Pillow not installed. Run: pip install pillow")

try:
    import cv2
    import numpy as np
except ImportError:
    sys.exit("OpenCV not installed. Run: pip install opencv-python")

try:
    import piexif
except ImportError:
    sys.exit("piexif not installed. Run: pip install piexif")


SUPPORTED = {".jpg", ".jpeg"}  # EXIF writing only reliable on JPEG
ORIENTATION_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "Orientation")
NON_UPRIGHT = {2, 3, 4, 5, 6, 7, 8}

# OpenCV face cascade — bundled with opencv-python
CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)

# EXIF orientation values for rotations (assuming no flip needed)
# 1 = upright, 6 = 90° CW (phone held portrait, stored landscape), 3 = 180°, 8 = 90° CCW
ROTATION_TO_EXIF = {
    0:   1,   # already correct
    90:  8,   # rotate 90° CCW to fix → EXIF says image is rotated 90° CW
    180: 3,   # rotate 180° to fix
    270: 6,   # rotate 90° CW to fix → EXIF says image is rotated 90° CCW
}


def get_exif_orientation(img):
    try:
        exif = img._getexif()
        if exif:
            return exif.get(ORIENTATION_TAG)
    except Exception:
        pass
    return None


def is_suspect(path):
    """Return True if file has no EXIF orientation and landscape pixel dimensions."""
    try:
        with Image.open(path) as img:
            orientation = get_exif_orientation(img)
            if orientation is not None:
                return False
            w, h = img.size
            return w > h * 1.1
    except Exception:
        return False


def detect_faces_count(img_array):
    """Return number of faces detected in an OpenCV image array."""
    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
        flags=cv2.CASCADE_SCALE_IMAGE
    )
    return len(faces) if isinstance(faces, np.ndarray) else 0


def best_rotation(path):
    """
    Try all 4 rotations, return (rotation_degrees, face_count) for the best one.
    rotation_degrees is how many degrees to rotate the image to make it upright.
    Returns (0, 0) if no faces found in any rotation.
    """
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img_array = np.array(img)
            # OpenCV uses BGR
            img_bgr = img_array[:, :, ::-1]

        best_rot = 0
        best_count = 0

        for rot in [0, 90, 180, 270]:
            if rot == 0:
                candidate = img_bgr
            else:
                # numpy rotation: rot degrees CCW
                k = rot // 90
                candidate = np.rot90(img_bgr, k)
            count = detect_faces_count(candidate)
            if count > best_count:
                best_count = count
                best_rot = rot

        return best_rot, best_count

    except Exception as e:
        return None, 0


def write_exif_orientation(path, rotation_degrees):
    """
    Write EXIF orientation tag to a JPEG file.
    rotation_degrees: how much to rotate the image to make it upright.
    """
    exif_value = ROTATION_TO_EXIF[rotation_degrees]

    try:
        # Load existing EXIF or start fresh
        try:
            exif_dict = piexif.load(str(path))
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

        exif_dict["0th"][piexif.ImageIFD.Orientation] = exif_value
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(path))
        return True
    except Exception as e:
        print(f"  ERROR writing EXIF to {path}: {e}")
        return False


def scan_and_fix(root, apply_changes, csv_path):
    root = Path(root)
    files = [
        p for p in root.rglob("*")
        if p.suffix.lower() in SUPPORTED and p.is_file()
    ]

    suspects = [p for p in files if is_suspect(p)]
    total_suspects = len(suspects)
    print(f"Found {len(files)} JPEG files, {total_suspects} suspect (landscape, no EXIF orientation)")

    if total_suspects == 0:
        print("Nothing to do.")
        return

    results = []
    fixed = 0
    skipped_upright = 0
    no_face = 0
    errors = 0

    for i, path in enumerate(suspects, 1):
        print(f"  [{i}/{total_suspects}] {path.name}", end=" … ", flush=True)

        rot, face_count = best_rotation(path)

        if rot is None:
            print("ERROR reading image")
            errors += 1
            results.append({"path": str(path), "result": "error", "rotation": "", "faces": 0})
            continue

        if face_count == 0:
            print("no faces detected — skipped")
            no_face += 1
            results.append({"path": str(path), "result": "no_face", "rotation": "", "faces": 0})
            continue

        if rot == 0:
            print(f"upright ({face_count} face(s)) — no change needed")
            skipped_upright += 1
            results.append({"path": str(path), "result": "already_upright", "rotation": 0, "faces": face_count})
            continue

        action = f"rotate {rot}° ({face_count} face(s))"
        if apply_changes:
            ok = write_exif_orientation(path, rot)
            if ok:
                print(f"FIXED — {action}")
                fixed += 1
                results.append({"path": str(path), "result": "fixed", "rotation": rot, "faces": face_count})
            else:
                print(f"WRITE ERROR — {action}")
                errors += 1
                results.append({"path": str(path), "result": "write_error", "rotation": rot, "faces": face_count})
        else:
            print(f"DRY RUN — would {action}")
            fixed += 1
            results.append({"path": str(path), "result": "would_fix", "rotation": rot, "faces": face_count})

    print("\n── Summary ───────────────────────────────────────────")
    print(f"  Suspect images processed    : {total_suspects}")
    if apply_changes:
        print(f"  Fixed (EXIF written)        : {fixed}")
    else:
        print(f"  Would fix (dry run)         : {fixed}  ← re-run with --apply to write")
    print(f"  Already upright             : {skipped_upright}")
    print(f"  No faces detected (skipped) : {no_face}  ← review these manually if needed")
    print(f"  Errors                      : {errors}")
    print("──────────────────────────────────────────────────────\n")

    if no_face > 0:
        print("Tip: photos with no faces detected were left unchanged.")
        print("     These may be genuine landscapes, or portraits of objects/scenery.")
        print("     Use --csv to export the list for manual review.\n")

    if csv_path:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["path", "result", "rotation", "faces"])
            writer.writeheader()
            writer.writerows(results)
        print(f"Full results written to: {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Fix photo orientation using face detection")
    parser.add_argument("path", help="Root photo folder (e.g. /Volumes/Photos)")
    parser.add_argument("--apply", action="store_true", help="Write EXIF changes (default is dry run)")
    parser.add_argument("--csv", metavar="FILE", help="Save results to CSV")
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        sys.exit(f"Not a directory: {args.path}")

    if not apply_mode_warned(args.apply):
        return

    scan_and_fix(args.path, args.apply, args.csv)


def apply_mode_warned(apply):
    if not apply:
        print("=" * 54)
        print("  DRY RUN — no files will be modified")
        print("  Re-run with --apply to write EXIF changes")
        print("=" * 54)
        print()
    else:
        print("=" * 54)
        print("  APPLY MODE — EXIF orientation tags will be written")
        print("=" * 54)
        print()
    return True


if __name__ == "__main__":
    main()
