#!/usr/bin/env python3
"""Apply the manually identified R/B channel correction for RBGW sky textures.

This is intentionally NOT a general ETS2 texture detector. The built-in target
list contains 68 RBGW DDS files that were manually identified through in-game
inspection during the original debugging process. The script only searches for
those exact filenames and swaps their red and blue channels.

Use this script only with the matching RBGW texture set, or review/edit the
target list first. Use --backup-dir to save originals and --dry-run to verify
which files would be touched before making changes.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Optional


# These 68 entries were manually identified during in-game testing.
MANUAL_TARGETS = [
    "c2", "c6", "d3", "d7", "f1", "f12", "g6", "g7", "g11", "g12",
    "i3", "i7", "i8", "i15", "i16", "i17", "i18", "i20", "i24", "i27",
    "i28", "i29", "i30", "k2", "k3", "m1", "m2", "m3", "m4", "m5",
    "m6", "m7", "m9", "m10", "m11", "m12", "m13", "m14", "ppz1",
    "ppz2", "ppz3", "ppz5", "ppz8", "ppz10", "ppz12", "ppz13", "ppz17",
    "ppz19", "ppz20", "ppz21", "ppz23", "ppz24", "ppz26", "ppz27",
    "ppz28", "r4", "r9", "r11", "r13", "w1", "w2", "w7", "w20", "w23",
    "w27", "w28", "x3", "x12",
]

TARGET_FILENAMES = {f"rbw_{name}.dds".lower() for name in MANUAL_TARGETS}


def create_backup(file_path: str, relative_path: str, backup_dir: str) -> None:
    """Copy the original file into the backup directory, preserving structure."""
    destination = Path(backup_dir) / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, destination)


def fix_sky_texture(task: tuple[str, str, Optional[str], bool]) -> tuple[str, str, str]:
    """Swap red and blue channels in one manually identified RBGW texture."""
    file_path, relative_path, backup_dir, dry_run = task

    if dry_run:
        return ("dry-run", relative_path, "R/B channel swap")

    temp_output = f"{file_path}.rbgwfix-{os.getpid()}.dds"
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"

    command = [
        "magick",
        file_path,
        "-channel",
        "RGBA",
        "-separate",
        "-swap",
        "0,2",
        "-combine",
        "-define",
        "dds:compression=none",
        "-define",
        "dds:mipmaps=0",
        temp_output,
    ]

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        if backup_dir:
            create_backup(file_path, relative_path, backup_dir)

        os.replace(temp_output, file_path)
        return ("fixed", relative_path, "R/B channels swapped")

    except (subprocess.CalledProcessError, OSError, shutil.Error) as exc:
        return ("failed", relative_path, str(exc))
    finally:
        if os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except OSError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply an R/B channel swap to the 68 RBGW textures that were "
            "manually identified during the original debugging process."
        )
    )
    parser.add_argument("mod_path", help="Path to the extracted RBGW mod directory")
    parser.add_argument(
        "--backup-dir",
        help="Optional directory in which to save originals before replacement",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matching target files without modifying them",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=cpu_count(),
        help="Number of parallel worker processes (default: CPU count)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mod_path = os.path.abspath(os.path.expanduser(args.mod_path))

    if shutil.which("magick") is None:
        print("Error: ImageMagick 7 (`magick`) was not found in PATH.", file=sys.stderr)
        return 2

    if not os.path.isdir(mod_path):
        print(f"Error: mod directory does not exist: {mod_path}", file=sys.stderr)
        return 2

    if args.workers < 1:
        print("Error: --workers must be at least 1.", file=sys.stderr)
        return 2

    backup_dir = None
    if args.backup_dir:
        backup_dir = os.path.abspath(os.path.expanduser(args.backup_dir))
        os.makedirs(backup_dir, exist_ok=True)

    tasks: list[tuple[str, str, Optional[str], bool]] = []
    found_names: set[str] = set()

    for root, _, files in os.walk(mod_path):
        for file_name in files:
            lower_name = file_name.lower()
            if lower_name in TARGET_FILENAMES:
                full_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(full_path, mod_path)
                tasks.append((full_path, relative_path, backup_dir, args.dry_run))
                found_names.add(lower_name)

    missing = sorted(TARGET_FILENAMES - found_names)

    print(f"RBGW directory: {mod_path}")
    print(f"Built-in manually identified targets: {len(TARGET_FILENAMES)}")
    print(f"Matching target files found: {len(tasks)}")
    if args.dry_run:
        print("Mode: dry run (no files will be modified)")
    elif backup_dir:
        print(f"Backup directory: {backup_dir}")
    else:
        print("Warning: matching files will be replaced in place and no backup was requested.")

    if missing:
        print(f"Missing target filenames: {len(missing)}")
        for name in missing:
            print(f"  {name}")

    if not tasks:
        return 1 if missing else 0

    with Pool(processes=args.workers) as pool:
        results = list(pool.imap_unordered(fix_sky_texture, tasks))

    fixed = [result for result in results if result[0] == "fixed"]
    dry_run = [result for result in results if result[0] == "dry-run"]
    failed = [result for result in results if result[0] == "failed"]

    print("\nSummary")
    print("-------")
    if fixed:
        print(f"     fixed: {len(fixed)}")
    if dry_run:
        print(f"   dry-run: {len(dry_run)}")
    if failed:
        print(f"    failed: {len(failed)}")

    if args.dry_run:
        print("\nMatched files")
        print("-------------")
        for _, relative_path, _ in sorted(results, key=lambda item: item[1].lower()):
            print(relative_path)

    if failed:
        print("\nFailed files")
        print("------------")
        for _, relative_path, details in failed:
            print(f"{relative_path}: {details}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
