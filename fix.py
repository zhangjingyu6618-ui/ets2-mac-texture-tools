#!/usr/bin/env python3
"""Batch-convert ETS2 DDS textures for macOS/CrossOver compatibility.

This script preserves the workflow used in the original project:
- scan a mod directory recursively for DDS files;
- read dimensions with ImageMagick when possible;
- fall back to macOS `sips` for DDS files ImageMagick cannot read;
- round texture dimensions up to multiples of four when needed;
- re-encode textures as DXT5 DDS files with mipmaps.

The script modifies files in place. Use --backup-dir if you want it to save a
copy of every file before replacement, and --dry-run to inspect what would be
processed without writing anything.
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


def run_command(command: list[str], *, env: Optional[dict[str, str]] = None) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture text output."""
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def get_image_size_magick(file_path: str) -> tuple[int, int]:
    """Return image dimensions using ImageMagick, or (0, 0) on failure."""
    try:
        result = run_command(
            ["magick", "identify", "-format", "%w,%h", file_path]
        )
        width, height = map(int, result.stdout.strip().split(","))
        return width, height
    except (subprocess.CalledProcessError, ValueError, OSError):
        return 0, 0


def get_image_size_sips(file_path: str) -> tuple[int, int]:
    """Return image dimensions using macOS sips, or (0, 0) on failure."""
    if shutil.which("sips") is None:
        return 0, 0

    try:
        result = run_command(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", file_path]
        )
        width = None
        height = None

        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("pixelWidth:"):
                width = int(stripped.split(":", 1)[1].strip())
            elif stripped.startswith("pixelHeight:"):
                height = int(stripped.split(":", 1)[1].strip())

        if width is None or height is None:
            return 0, 0
        return width, height
    except (subprocess.CalledProcessError, ValueError, OSError):
        return 0, 0


def create_backup(file_path: str, relative_path: str, backup_dir: str) -> None:
    """Copy the original file into the backup directory, preserving structure."""
    destination = Path(backup_dir) / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, destination)


def process_file(task: tuple[str, str, Optional[str], bool]) -> tuple[str, str, str]:
    """Process one DDS file and return (status, relative_path, details)."""
    file_path, relative_path, backup_dir, dry_run = task

    width, height = get_image_size_magick(file_path)
    using_sips_fallback = False

    if width == 0 or height == 0:
        width, height = get_image_size_sips(file_path)
        if width > 0 and height > 0:
            using_sips_fallback = True
        else:
            return ("failed", relative_path, "Could not read DDS dimensions")

    target_width = (width + 3) // 4 * 4
    target_height = (height + 3) // 4 * 4
    resize_needed = (width != target_width) or (height != target_height)

    if dry_run:
        details = []
        if using_sips_fallback:
            details.append("requires sips fallback")
        if resize_needed:
            details.append(
                f"resize {width}x{height} -> {target_width}x{target_height}"
            )
        if not details:
            details.append("re-encode as DXT5")
        return ("dry-run", relative_path, "; ".join(details))

    source_file = file_path
    temp_png: Optional[str] = None
    temp_output = f"{file_path}.ets2fix-{os.getpid()}.dds"

    try:
        if using_sips_fallback:
            temp_png = f"{file_path}.ets2fix-{os.getpid()}.png"
            subprocess.run(
                ["sips", "-s", "format", "png", file_path, "--out", temp_png],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            source_file = temp_png

        command = ["magick", source_file]
        if resize_needed:
            command.extend(["-resize", f"{target_width}x{target_height}!"])

        command.extend(
            [
                "-define",
                "dds:compression=dxt5",
                "-define",
                "dds:cluster-fit=true",
                "-define",
                "dds:mipmaps=8",
                temp_output,
            ]
        )

        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = "1"
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

        if using_sips_fallback and resize_needed:
            details = (
                f"Recovered with sips; resized {width}x{height} -> "
                f"{target_width}x{target_height}; encoded as DXT5"
            )
            status = "rescued"
        elif using_sips_fallback:
            details = f"Recovered with sips ({width}x{height}); encoded as DXT5"
            status = "rescued"
        elif resize_needed:
            details = (
                f"Resized {width}x{height} -> {target_width}x{target_height}; "
                "encoded as DXT5"
            )
            status = "resized"
        else:
            details = "Encoded as DXT5"
            status = "converted"

        return (status, relative_path, details)

    except (subprocess.CalledProcessError, OSError, shutil.Error) as exc:
        return ("failed", relative_path, str(exc))
    finally:
        for temporary_file in (temp_png, temp_output):
            if temporary_file and os.path.exists(temporary_file):
                try:
                    os.remove(temporary_file)
                except OSError:
                    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recursively re-encode ETS2 DDS textures as DXT5, using macOS sips "
            "as a fallback for files ImageMagick cannot read."
        )
    )
    parser.add_argument("mod_path", help="Path to the extracted ETS2 mod directory")
    parser.add_argument(
        "--backup-dir",
        help="Optional directory in which to save originals before replacement",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report planned actions without modifying any files",
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

    if shutil.which("sips") is None:
        print(
            "Warning: macOS `sips` was not found. Files that ImageMagick cannot "
            "read will be reported as failed."
        )

    tasks: list[tuple[str, str, Optional[str], bool]] = []
    for root, _, files in os.walk(mod_path):
        for file_name in files:
            if file_name.lower().endswith(".dds"):
                full_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(full_path, mod_path)
                tasks.append((full_path, relative_path, backup_dir, args.dry_run))

    print(f"Mod directory: {mod_path}")
    print(f"DDS files found: {len(tasks)}")
    if args.dry_run:
        print("Mode: dry run (no files will be modified)")
    elif backup_dir:
        print(f"Backup directory: {backup_dir}")
    else:
        print("Warning: files will be replaced in place and no backup was requested.")

    if not tasks:
        return 0

    with Pool(processes=args.workers) as pool:
        results = list(pool.imap_unordered(process_file, tasks, chunksize=5))

    counts: dict[str, int] = {}
    for status, _, _ in results:
        counts[status] = counts.get(status, 0) + 1

    print("\nSummary")
    print("-------")
    for status in ("converted", "resized", "rescued", "dry-run", "failed"):
        if counts.get(status, 0):
            print(f"{status:>10}: {counts[status]}")

    failures = [result for result in results if result[0] == "failed"]
    if failures:
        print("\nFailed files")
        print("------------")
        for _, relative_path, details in failures:
            print(f"{relative_path}: {details}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
