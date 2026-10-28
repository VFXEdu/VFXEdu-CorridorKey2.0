#!/usr/bin/env python3
"""Build a clean, lightweight portable distribution ZIP for CorridorKeyer 2.0 (Option A).

Includes:
- Full CorridorKeyer 2.0 workbench codebase & CLI tools
- Embedded Python 3.12 (Zero-install portable runtime + standalone pip)
- Standalone FFmpeg binary in bin/ffmpeg.exe
- One-click Setup_GUI.bat and Launch_GUI.bat launchers

Excludes large model weights (~4.9 GB) and cache/temp files, producing a ~70-95 MB package.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
DIST_DIR.mkdir(parents=True, exist_ok=True)

# Weight file extensions and large binaries to exclude
EXCLUDE_EXTENSIONS = {
    ".safetensors",
    ".pth",
    ".pt",
    ".npz",
    ".tar",
    ".f16",
    ".f32",
    ".pyc",
    ".part",
    ".tmp",
    ".mp4",
    ".mov",
    ".exr",
    ".lnk",
    ".log",
}

# Directories to completely ignore
EXCLUDE_DIRS = {
    "venv",
    ".venv",
    "env",
    "tmp",
    "outputs",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "dist",
}

# Explicit essential empty folders that must exist (with .gitkeep)
PLACEHOLDER_DIRS = [
    "weights",
    "vfms/cradio",
    "vfms/moge",
    "vfms/rvm",
    "outputs",
    "tmp",
    "bin",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def should_include(rel_path: Path) -> bool:
    parts = rel_path.parts

    # Check directory exclusion
    for d in EXCLUDE_DIRS:
        if d in parts:
            return False

    # Check extension exclusion
    if rel_path.suffix.lower() in EXCLUDE_EXTENSIONS:
        return False

    # Ignore hidden files except .gitkeep
    if rel_path.name.startswith(".") and rel_path.name != ".gitkeep":
        return False

    # For python_embed: retain base embedded Python & pip, exclude bulky site-packages if present
    if len(parts) >= 3 and parts[0] == "python_embed" and parts[1] == "Lib" and parts[2] == "site-packages":
        pkg_name = parts[3] if len(parts) > 3 else ""
        allowed_prefixes = ("pip", "setuptools", "wheel", "_distutils", "distutils")
        if pkg_name.endswith(".pth"):
            return True
        if pkg_name and not pkg_name.startswith(allowed_prefixes) and pkg_name != ".gitkeep":
            return False

    return True


def create_release_zip(output_name: str = "CorridorKeyer2.0_Portable_Setup.zip") -> Path:
    # Ensure embedded python & ffmpeg are prepared
    ffmpeg_bin = ROOT / "bin" / "ffmpeg.exe"
    python_embed = ROOT / "python_embed" / "python.exe"

    if not ffmpeg_bin.is_file() or not python_embed.is_file():
        print("[*] Embedded Python or bin/ffmpeg.exe missing. Running prepare_embedded_python.py...")
        from prepare_embedded_python import main as prep_main
        prep_main()

    zip_path = DIST_DIR / output_name
    if zip_path.exists():
        zip_path.unlink()

    print(f"[*] Packaging CorridorKeyer 2.0 (Option A) from: {ROOT}")
    print(f"[*] Target release ZIP: {zip_path}")

    file_count = 0
    total_uncompressed = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1. Walk and add source files
        for root_str, dirs, files in os.walk(ROOT):
            root_p = Path(root_str)
            rel_dir = root_p.relative_to(ROOT)

            # Skip excluded dirs early
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

            for f in files:
                file_p = root_p / f
                rel_file = file_p.relative_to(ROOT)

                if should_include(rel_file):
                    arcname = str(rel_file).replace("\\", "/")
                    zf.write(file_p, arcname=arcname)
                    file_count += 1
                    total_uncompressed += file_p.stat().st_size

        # 2. Ensure placeholder directory .gitkeeps are added
        for pdir in PLACEHOLDER_DIRS:
            keep_arc = f"{pdir}/.gitkeep".replace("\\", "/")
            if keep_arc not in zf.namelist():
                zf.writestr(keep_arc, "")
                file_count += 1

    zip_size = zip_path.stat().st_size
    checksum = sha256_file(zip_path)
    (DIST_DIR / f"{output_name}.sha256").write_text(f"{checksum} *{output_name}\n", encoding="utf-8")

    print("\n" + "=" * 65)
    print(" [SUCCESS] Option A Portable Package Created Successfully!")
    print("=" * 65)
    print(f"  Package File  : {zip_path.name}")
    print(f"  Location      : {zip_path}")
    print(f"  Total Files   : {file_count} files")
    print(f"  Uncompressed  : {total_uncompressed / (1024 * 1024):.2f} MB")
    print(f"  ZIP Size      : {zip_size / (1024 * 1024):.2f} MB")
    print(f"  SHA-256       : {checksum}")
    print("=" * 65)

    return zip_path


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", default="CorridorKeyer2.0_Portable_Setup.zip", help="Output zip filename")
    args = ap.parse_args()
    create_release_zip(args.name)


if __name__ == "__main__":
    main()
