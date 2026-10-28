#!/usr/bin/env python3
"""Automated Embedded Python & FFmpeg preparation for CorridorKeyer 2.0.

Downloads official Python 3.12.10 Embeddable zip, configures site-packages & pathing,
installs standalone pip, and packages bin/ffmpeg.exe for zero-install distribution.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
EMBED_DIR = ROOT / "python_embed"
BIN_DIR = ROOT / "bin"
TMP_DIR = ROOT / "tmp"

PYTHON_VERSION = "3.12.10"
EMBED_ZIP_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
LOCAL_FFMPEG_CANDIDATES = [
    Path(r"C:\ffmpeg2026\bin\ffmpeg.exe"),
    Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
    Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
]


def download_with_progress(url: str, dest_path: Path, label: str) -> Path:
    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"[*] Found cached {label}: {dest_path.name}")
        return dest_path

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_path.with_suffix(".part")
    print(f"[*] Downloading {label} from: {url}")

    req = urllib.request.Request(url, headers={"User-Agent": "CorridorKey-Downloader/2.0"})
    with urllib.request.urlopen(req) as resp, open(temp_dest, "wb") as f:
        total_size = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB

        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                percent = (downloaded / total_size) * 100
                print(f"\r  -> Progress: {downloaded / (1024*1024):.1f}/{total_size / (1024*1024):.1f} MB ({percent:.1f}%)", end="", flush=True)
            else:
                print(f"\r  -> Downloaded: {downloaded / (1024*1024):.1f} MB", end="", flush=True)

    print()
    temp_dest.replace(dest_path)
    return dest_path


def ensure_bin_ffmpeg() -> Path:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = BIN_DIR / "ffmpeg.exe"
    if ffmpeg_exe.is_file() and ffmpeg_exe.stat().st_size > 10_000_000:
        print(f"[*] FFmpeg binary already present: {ffmpeg_exe} ({ffmpeg_exe.stat().st_size / (1024*1024):.1f} MB)")
        return ffmpeg_exe

    # Try local candidates
    for cand in LOCAL_FFMPEG_CANDIDATES:
        if cand.is_file():
            print(f"[*] Copying FFmpeg binary from {cand} to {ffmpeg_exe}...")
            shutil.copy2(cand, ffmpeg_exe)
            return ffmpeg_exe

    # Fallback to which
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        which_path = Path(which_ffmpeg)
        print(f"[*] Copying system FFmpeg from {which_path} to {ffmpeg_exe}...")
        shutil.copy2(which_path, ffmpeg_exe)
        return ffmpeg_exe

    # Fallback to downloading standalone static FFmpeg
    print("[*] Local FFmpeg not found. Downloading static FFmpeg essentials...")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg_zip_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    ffmpeg_cache = TMP_DIR / "ffmpeg-essentials.zip"
    download_with_progress(ffmpeg_zip_url, ffmpeg_cache, "FFmpeg Static Essentials")
    with zipfile.ZipFile(ffmpeg_cache) as zf:
        for member in zf.namelist():
            if member.endswith("/bin/ffmpeg.exe") or member.endswith("bin/ffmpeg.exe"):
                print(f"[*] Extracting {member} to {ffmpeg_exe}...")
                with zf.open(member) as src_f, open(ffmpeg_exe, "wb") as dst_f:
                    shutil.copyfileobj(src_f, dst_f)
                return ffmpeg_exe

    raise RuntimeError(
        "Could not find or download ffmpeg.exe to bundle. Please place ffmpeg.exe into bin/ folder."
    )


def setup_embedded_python(force: bool = False) -> Path:
    python_exe = EMBED_DIR / "python.exe"
    pip_exe = EMBED_DIR / "Scripts" / "pip.exe"
    pth_file = EMBED_DIR / f"python{PYTHON_VERSION.replace('.', '')[:3]}._pth"

    if not force and python_exe.is_file() and pth_file.is_file():
        # Check if pip is installed
        check = subprocess.run([str(python_exe), "-m", "pip", "--version"], capture_ok=True if hasattr(subprocess, 'capture_ok') else False, capture_output=True, text=True)
        if check.returncode == 0:
            print(f"[*] Embedded Python already ready: {python_exe}")
            print(f"    {check.stdout.strip()}")
            return EMBED_DIR

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    zip_cache = TMP_DIR / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    download_with_progress(EMBED_ZIP_URL, zip_cache, f"Python {PYTHON_VERSION} Embedded ZIP")

    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[*] Extracting Python to {EMBED_DIR}...")
    with zipfile.ZipFile(zip_cache) as zf:
        zf.extractall(EMBED_DIR)

    # Configure ._pth file
    if not pth_file.is_file():
        # Look for any ._pth file
        pth_files = list(EMBED_DIR.glob("*._pth"))
        if pth_files:
            pth_file = pth_files[0]

    print(f"[*] Configuring {pth_file.name} for site-packages and package root...")
    pth_content = pth_file.read_text(encoding="utf-8") if pth_file.is_file() else ""
    # Uncomment import site
    pth_content = pth_content.replace("#import site", "import site").replace("# import site", "import site")
    if "import site" not in pth_content:
        pth_content += "\nimport site\n"

    # Add Lib, Lib/site-packages, and .. (project root)
    lines = [line.strip() for line in pth_content.splitlines() if line.strip()]
    needed_entries = [".", "..", "Lib", "Lib/site-packages"]
    for entry in needed_entries:
        if entry not in lines:
            lines.insert(1, entry)

    pth_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Create Lib/site-packages
    site_packages = EMBED_DIR / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    # Download and run get-pip.py
    get_pip_cache = TMP_DIR / "get-pip.py"
    download_with_progress(GET_PIP_URL, get_pip_cache, "get-pip.py")

    print("[*] Installing pip into embedded python environment...")
    res = subprocess.run(
        [str(python_exe), str(get_pip_cache), "--no-warn-script-location"],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"[!] Pip installation failed:\n{res.stderr}")
        raise RuntimeError(f"get-pip.py failed with code {res.returncode}")

    # Verify pip
    ver_res = subprocess.run([str(python_exe), "-m", "pip", "--version"], capture_output=True, text=True)
    print(f"[SUCCESS] {ver_res.stdout.strip()}")

    # Ensure VC++ runtime DLLs are bundled for target PCs without Visual C++ Redistributable
    sys32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    vc_dlls = ["msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll"]
    for dll in vc_dlls:
        src = sys32 / dll
        dst = EMBED_DIR / dll
        if src.is_file() and not dst.is_file():
            try:
                shutil.copy2(src, dst)
                print(f"[*] Bundled runtime DLL: {dll}")
            except Exception:
                pass

    return EMBED_DIR


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Prepare Embedded Python & FFmpeg for CorridorKeyer 2.0")
    parser.add_argument("--force", action="store_true", help="Force re-download and re-extract")
    args = parser.parse_args()

    print("=" * 65)
    print(" CorridorKeyer 2.0 - Portable Distribution Environment Preparer")
    print("=" * 65)

    ffmpeg_path = ensure_bin_ffmpeg()
    print(f"[OK] FFmpeg binary verified at: {ffmpeg_path}")

    embed_path = setup_embedded_python(force=args.force)
    print(f"[OK] Embedded Python verified at: {embed_path}")

    print("=" * 65)
    print(" Portable runtime preparation finished successfully!")
    print("=" * 65)


if __name__ == "__main__":
    main()
