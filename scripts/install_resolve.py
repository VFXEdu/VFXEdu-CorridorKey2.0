#!/usr/bin/env python3
"""One-click DaVinci Resolve Integration Installer & Uninstaller for CorridorKey 2.0.

Installs both:
1. Native Fusion Fuse Node (CorridorKeyer.fuse) for 100% zero-popup Inspector node usage in the Fusion page.
2. Edit / Color Page Script Launcher (CorridorKeyer.py) under Workspace -> Scripts.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import sys


def get_resolve_script_dirs() -> list[Path]:
    """Return list of standard DaVinci Resolve script directories on Windows/macOS/Linux."""
    dirs: list[Path] = []

    # Windows AppData (User path)
    appdata = os.environ.get("APPDATA")
    if appdata:
        base_user = Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts"
        dirs.append(base_user / "Edit")
        dirs.append(base_user / "Color")
        dirs.append(base_user / "Utility")

    # Windows ProgramData (System path)
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        base_sys = Path(programdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts"
        dirs.append(base_sys / "Edit")
        dirs.append(base_sys / "Color")
        dirs.append(base_sys / "Utility")

    # macOS
    mac_base = Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Scripts"
    if mac_base.parent.exists():
        dirs.append(mac_base / "Edit")
        dirs.append(mac_base / "Color")
        dirs.append(mac_base / "Utility")

    # Linux
    linux_base = Path("/opt/resolve/Fusion/Scripts")
    if linux_base.parent.exists():
        dirs.append(linux_base / "Edit")
        dirs.append(linux_base / "Color")
        dirs.append(linux_base / "Utility")

    return dirs


def get_resolve_fuse_dirs() -> list[Path]:
    """Return list of standard DaVinci Resolve Fuses directories."""
    dirs: list[Path] = []

    # Windows AppData
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Fuses" / "Keyer")
        dirs.append(Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Fuses")

    # Windows ProgramData
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        dirs.append(Path(programdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Fuses" / "Keyer")
        dirs.append(Path(programdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Fuses")

    # macOS
    mac_base = Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Fuses"
    if mac_base.parent.exists():
        dirs.append(mac_base / "Keyer")

    # Linux
    linux_base = Path("/opt/resolve/Fusion/Fuses")
    if linux_base.parent.exists():
        dirs.append(linux_base / "Keyer")

    return dirs


def create_launcher_script_content(repo_root: Path) -> str:
    """Generate the contents of CorridorKeyer.py launcher stub."""
    norm_root = repo_root.resolve().as_posix()
    return f"""# -*- coding: utf-8 -*-
# VFXEdu CorridorKey 2.0 - DaVinci Resolve Launcher Stub
import os
import sys
from pathlib import Path

CORRIDORKEY_ROOT = Path(r"{norm_root}")
os.environ["CORRIDORKEY_ROOT"] = str(CORRIDORKEY_ROOT)

resolve_dir = CORRIDORKEY_ROOT / "resolve"
if str(resolve_dir) not in sys.path:
    sys.path.insert(0, str(resolve_dir))

try:
    import corridorkey_resolve
    corridorkey_resolve.main()
except Exception as e:
    import traceback
    print(f"[CorridorKey] Error launching DaVinci Resolve bridge: {{e}}")
    traceback.print_exc()
"""


def install(repo_root: Path) -> bool:
    """Deploy CorridorKeyer to DaVinci Resolve (both Fusion Fuses and Scripts)."""
    repo_root = repo_root.resolve()
    fuse_src = repo_root / "resolve" / "fusion" / "CorridorKeyer.fuse"
    if not fuse_src.is_file():
        print(f"[ERROR] 'resolve/fusion/CorridorKeyer.fuse' not found in {repo_root}")
        return False

    installed_paths = []

    # 1. Install Fusion Fuse Node (.fuse)
    fuse_content = fuse_src.read_text(encoding="utf-8")
    norm_root = repo_root.as_posix()
    fuse_content = fuse_content.replace(
        "K:/________________VFXEdu_Script/CorridorKeyer2.0",
        norm_root
    )

    for fd in get_resolve_fuse_dirs():
        try:
            fd.mkdir(parents=True, exist_ok=True)
            target_fuse = fd / "CorridorKeyer.fuse"
            target_fuse.write_text(fuse_content, encoding="utf-8")
            installed_paths.append(target_fuse)
        except Exception:
            pass

    # 2. Install Edit/Color Workspace Script Launcher (.py)
    script_content = create_launcher_script_content(repo_root)
    for sd in get_resolve_script_dirs():
        try:
            sd.mkdir(parents=True, exist_ok=True)
            target_script = sd / "CorridorKeyer.py"
            target_script.write_text(script_content, encoding="utf-8")
            installed_paths.append(target_script)
        except Exception:
            pass

    if not installed_paths:
        print("[ERROR] Could not write to DaVinci Resolve directories.")
        return False

    print("\n" + "=" * 65)
    print(" [SUCCESS] CorridorKey 2.0 has been successfully linked to DaVinci Resolve!")
    print("=" * 65)
    print("  Installed Components:")
    for p in installed_paths:
        print(f"   - {p}")
    print("=" * 65)
    print("  1. Fusion Page: Press 'Shift + Space' and search for 'CorridorKeyer'")
    print("                  (100% Zero-Popup Inspector Node!)")
    print("  2. Edit/Color : Menu 'Workspace' -> 'Scripts' -> 'CorridorKeyer'")
    print("=" * 65)
    return True


def uninstall() -> bool:
    """Remove CorridorKeyer from DaVinci Resolve Fuses and Scripts."""
    removed = 0

    # 1. Remove Fuses
    for fd in get_resolve_fuse_dirs():
        target_fuse = fd / "CorridorKeyer.fuse"
        if target_fuse.is_file():
            try:
                target_fuse.unlink()
                print(f"[*] Removed Fuse: {target_fuse}")
                removed += 1
            except Exception:
                pass

    # 2. Remove Scripts
    for sd in get_resolve_script_dirs():
        target_script = sd / "CorridorKeyer.py"
        if target_script.is_file():
            try:
                target_script.unlink()
                print(f"[*] Removed Script: {target_script}")
                removed += 1
            except Exception:
                pass

    print("\n" + "=" * 65)
    if removed > 0:
        print(f" [SUCCESS] Removed CorridorKeyer from {removed} Resolve location(s).")
    else:
        print(" [*] No CorridorKeyer files found in DaVinci Resolve directories.")
    print("=" * 65)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--install", action="store_true", help="Install to DaVinci Resolve")
    ap.add_argument("--uninstall", action="store_true", help="Uninstall from DaVinci Resolve")
    ap.add_argument("root", nargs="?", default=".", help="CorridorKey repository root")

    args = ap.parse_args()
    root_path = Path(str(args.root).strip('"\'')).resolve()

    if args.uninstall:
        uninstall()
    else:
        install(root_path)


if __name__ == "__main__":
    main()
