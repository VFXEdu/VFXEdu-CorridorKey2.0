#!/usr/bin/env python3
"""CorridorKey 2.0 In-App & Standalone Auto-Updater.

Enables 1-click version checking and fast incremental code updating from GitHub.
Safely updates application scripts, UI components, Nuke gizmos, and Resolve tools
WITHOUT redownloading heavy model weights (~5GB) or virtual environments.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_REPO = "VFXEdu/VFXEdu-CorridorKey2.0"

# Directories and files to NEVER touch or overwrite during an update
PROTECTED_PATTERNS = {
    "weights",
    "vfms",
    "venv",
    ".venv",
    "python_embed",
    "outputs",
    "tmp",
    ".git",
    "gui_config.json",  # Preserve user language and preferences
}

EXCLUDE_EXTENSIONS = {
    ".safetensors",
    ".pth",
    ".pt",
    ".npz",
    ".tar",
    ".f16",
    ".f32",
    ".mp4",
    ".mov",
    ".exr",
}


def get_local_app_version() -> str:
    """Read local APP_VERSION from gui.py without importing GUI dependencies."""
    gui_file = ROOT / "gui.py"
    if gui_file.is_file():
        try:
            content = gui_file.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
            if m:
                return m.group(1)
        except Exception:
            pass
    return "v0.1.1"


def get_configured_github_repo() -> str:
    """Retrieve owner/repo from git remote or fallback to DEFAULT_REPO."""
    try:
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        url = res.stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return DEFAULT_REPO


def parse_version_tuple(v_str: str) -> tuple[int, ...]:
    """Parse a version string (e.g. 'v0.1.2' or '0.1.1') into an integer tuple."""
    clean = re.sub(r"^[vV]", "", v_str.strip())
    nums = []
    for part in clean.split("."):
        try:
            nums.append(int(re.match(r"^\d+", part).group(0)))
        except Exception:
            nums.append(0)
    return tuple(nums) if nums else (0, 0, 0)


def is_newer_version(latest_tag: str, current_tag: str) -> bool:
    """Check if latest_tag is strictly newer than current_tag."""
    return parse_version_tuple(latest_tag) > parse_version_tuple(current_tag)


def check_for_updates(current_version: str, repo: str | None = None, timeout: float = 4.0) -> dict:
    """Check GitHub Releases API for new version.

    Returns:
        dict: {
            "update_available": bool,
            "latest_version": str,
            "current_version": str,
            "release_name": str,
            "release_notes": str,
            "release_url": str,
            "zipball_url": str,
            "error": str | None
        }
    """
    repo = repo or get_configured_github_repo()
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"

    req = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "VFXEdu-CorridorKeyer-AutoUpdater",
        },
    )

    result = {
        "update_available": False,
        "latest_version": current_version,
        "current_version": current_version,
        "release_name": "",
        "release_notes": "",
        "release_url": f"https://github.com/{repo}",
        "zipball_url": "",
        "error": None,
    }

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

            latest_tag = data.get("tag_name", "").strip()
            if not latest_tag:
                latest_tag = current_version

            result["latest_version"] = latest_tag
            result["release_name"] = data.get("name") or latest_tag
            result["release_notes"] = data.get("body") or "No release notes provided."
            result["release_url"] = data.get("html_url") or f"https://github.com/{repo}/releases"
            result["zipball_url"] = data.get("zipball_url") or f"https://github.com/{repo}/archive/refs/tags/{latest_tag}.zip"

            if is_newer_version(latest_tag, current_version):
                result["update_available"] = True

    except urllib.error.HTTPError as e:
        if e.code == 404:
            # No releases published yet on this repo; check raw master gui.py
            raw_url = f"https://raw.githubusercontent.com/{repo}/master/gui.py"
            try:
                raw_req = urllib.request.Request(raw_url, headers={"User-Agent": "VFXEdu-CorridorKeyer"})
                with urllib.request.urlopen(raw_req, timeout=timeout) as rresp:
                    content = rresp.read().decode("utf-8")
                    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
                    if m:
                        latest_raw = m.group(1)
                        result["latest_version"] = latest_raw
                        result["zipball_url"] = f"https://github.com/{repo}/archive/refs/heads/master.zip"
                        if is_newer_version(latest_raw, current_version):
                            result["update_available"] = True
                            result["release_notes"] = f"New master build ({latest_raw}) available."
            except Exception as raw_e:
                result["error"] = f"No releases found and raw check failed: {raw_e}"
        else:
            result["error"] = f"GitHub API HTTP error {e.code}: {e.reason}"
    except Exception as e:
        result["error"] = f"Connection error: {e}"

    return result


def apply_code_update(
    zip_url: str | None = None,
    target_dir: Path | None = None,
    repo: str | None = None,
    progress_callback=None,
) -> tuple[bool, str]:
    """Download the latest code archive from GitHub and incrementally update local files.

    Returns:
        tuple[bool, str]: (Success, status_message)
    """
    target_dir = (target_dir or ROOT).resolve()
    repo = repo or get_configured_github_repo()
    zip_url = zip_url or f"https://github.com/{repo}/archive/refs/heads/master.zip"

    staging_dir = Path(tempfile.gettempdir()) / "ck_update_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    zip_file = staging_dir / "update.zip"

    if progress_callback:
        progress_callback(10, "Downloading update package from GitHub...")

    try:
        # 1. Download ZIP
        req = urllib.request.Request(
            zip_url,
            headers={"User-Agent": "VFXEdu-CorridorKeyer-AutoUpdater"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp, open(zip_file, "wb") as f:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and progress_callback:
                    pct = int(10 + (downloaded / total_size) * 40)
                    progress_callback(min(50, pct), f"Downloading ({downloaded // 1024} KB)...")

        if progress_callback:
            progress_callback(55, "Extracting update package...")

        # 2. Extract ZIP
        extract_dir = staging_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(extract_dir)

        # GitHub zipballs have a single top-level directory (e.g. repo-master/ or repo-v0.1.2/)
        subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
        source_root = subdirs[0] if subdirs else extract_dir

        if progress_callback:
            progress_callback(75, "Applying code updates...")

        # 3. Incrementally copy files, respecting PROTECTED_PATTERNS
        updated_count = 0
        for src_path in source_root.rglob("*"):
            if not src_path.is_file():
                continue

            rel_path = src_path.relative_to(source_root)
            parts = rel_path.parts

            # Check protected top-level directories
            if parts and parts[0] in PROTECTED_PATTERNS:
                continue

            # Check protected filename
            if rel_path.name in PROTECTED_PATTERNS:
                continue

            # Check forbidden extensions (never download raw models via code updater)
            if rel_path.suffix.lower() in EXCLUDE_EXTENSIONS:
                continue

            dest_path = target_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                if rel_path.suffix.lower() in {".bat", ".cmd"}:
                    raw_b = src_path.read_bytes()
                    crlf_b = raw_b.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                    dest_path.write_bytes(crlf_b)
                else:
                    shutil.copy2(src_path, dest_path)
                updated_count += 1
            except Exception as copy_err:
                print(f"[Warning] Could not update {rel_path}: {copy_err}")

        # Auto-refresh DaVinci Resolve Fuse and Nuke if integrations exist
        try:
            from scripts.install_resolve import install as install_resolve
            install_resolve(target_dir)
        except Exception:
            pass

        try:
            from scripts.install_nuke import get_nuke_dir, install as install_nuke
            nuke_init = get_nuke_dir() / "init.py"
            if nuke_init.is_file():
                install_nuke(target_dir)
        except Exception:
            pass

        if progress_callback:
            progress_callback(100, f"Update complete! ({updated_count} files updated)")

        # Cleanup staging
        shutil.rmtree(staging_dir, ignore_errors=True)

        return True, f"Successfully updated {updated_count} files from GitHub."

    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        return False, f"Update failed: {exc}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Check for available updates")
    ap.add_argument("--apply", action="store_true", help="Download and apply latest update")
    ap.add_argument("--repo", default=None, help="Target GitHub repository (owner/repo)")

    args = ap.parse_args()

    # Read current app version safely via regex without importing GUI dependencies
    APP_VERSION = get_local_app_version()

    repo = args.repo or get_configured_github_repo()
    print("=" * 65)
    print("  VFXEdu CorridorKey 2.0 - Auto-Update Manager")
    print(f"  Current Version : {APP_VERSION}")
    print(f"  GitHub Repo     : {repo}")
    print("=" * 65)

    info = check_for_updates(APP_VERSION, repo=repo)

    if info["error"]:
        print(f"[-] Check status: {info['error']}")
    elif info["update_available"]:
        print(f"[+] NEW VERSION AVAILABLE: {info['latest_version']} (Current: {APP_VERSION})")
        print(f"[+] Release Title       : {info['release_name']}")
        print(f"[+] Release Notes:\n{info['release_notes']}\n")
    else:
        print(f"[*] You are up to date! ({APP_VERSION})")

    if args.apply:
        if info["update_available"] or not info["error"]:
            print("[*] Applying fast incremental update...")
            ok, msg = apply_code_update(zip_url=info.get("zipball_url"), repo=repo)
            print(f"[*] Result: {msg}")
            if ok:
                print("\n[SUCCESS] Update applied! You may now launch CorridorKeyer 2.0.")
            else:
                sys.exit(1)
        else:
            print("[-] Cannot apply update due to check error.")


if __name__ == "__main__":
    main()
