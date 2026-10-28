#!/usr/bin/env python3
"""One-click DaVinci Resolve Integration Installer & Uninstaller for CorridorKey 2.0."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
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


def create_launcher_script_content(repo_root: Path) -> str:
    """Generate the contents of CorridorKeyer.py launcher stub."""
    norm_root = repo_root.resolve().as_posix()
    return f"""# -*- coding: utf-8 -*-
# VFXEdu CorridorKey 2.0 - DaVinci Resolve Launcher Stub
import os
import sys
from pathlib import Path

CORRIDORKEY_ROOT = Path(r"{norm_root}")

# Set environment variable so child processes locate root
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
    """Deploy CorridorKeyer.py launcher script to DaVinci Resolve script directories."""
    repo_root = repo_root.resolve()
    if not (repo_root / "resolve" / "corridorkey_resolve.py").is_file():
        print(f"[ERROR] 'resolve/corridorkey_resolve.py' not found in {repo_root}")
        return False

    script_content = create_launcher_script_content(repo_root)
    target_dirs = get_resolve_script_dirs()

    installed_paths = []
    for d in target_dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            target_file = d / "CorridorKeyer.py"
            target_file.write_text(script_content, encoding="utf-8")
            installed_paths.append(target_file)
        except Exception as e:
            # Skip read-only directories like ProgramData if not running as admin
            pass

    if not installed_paths:
        print("[ERROR] Could not write to any DaVinci Resolve script directories.")
        return False

    print("\n" + "=" * 65)
    print(" [SUCCESS] CorridorKey 2.0 has been successfully linked to DaVinci Resolve!")
    print("=" * 65)
    for p in installed_paths:
        print(f"  Installed: {p}")
    print("=" * 65)
    return True


def uninstall() -> bool:
    """Remove CorridorKeyer.py launcher from DaVinci Resolve script directories."""
    target_dirs = get_resolve_script_dirs()
    removed = 0
    for d in target_dirs:
        target_file = d / "CorridorKeyer.py"
        if target_file.is_file():
            try:
                target_file.unlink()
                print(f"[*] Removed: {target_file}")
                removed += 1
            except Exception:
                pass

    print("\n" + "=" * 65)
    if removed > 0:
        print(f" [SUCCESS] Removed CorridorKeyer script from {removed} Resolve directory(ies).")
    else:
        print(" [*] No CorridorKeyer script found in DaVinci Resolve directories.")
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
