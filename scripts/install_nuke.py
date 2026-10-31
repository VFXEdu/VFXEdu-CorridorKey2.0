#!/usr/bin/env python3
"""One-click Foundry Nuke Integration Installer & Uninstaller for CorridorKey 2.0."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys

START_TAG = "# === VFXEdu CorridorKey 2.0 Start ==="
END_TAG = "# === VFXEdu CorridorKey 2.0 End ==="


def get_nuke_dir() -> Path:
    """Get the user's .nuke directory (~/.nuke)."""
    nuke_dir = Path.home() / ".nuke"
    nuke_dir.mkdir(parents=True, exist_ok=True)
    return nuke_dir


def install(repo_root: Path) -> bool:
    """Register CorridorKey Nuke plugin in ~/.nuke/init.py."""
    nuke_plugin_dir = (repo_root / "nuke").resolve()
    if not nuke_plugin_dir.is_dir():
        print(f"[ERROR] 'nuke' directory not found in {repo_root}")
        return False

    nuke_plugin_path = nuke_plugin_dir.as_posix()
    nuke_dir = get_nuke_dir()
    init_file = nuke_dir / "init.py"

    content = ""
    if init_file.is_file():
        try:
            content = init_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = init_file.read_text(encoding="cp949", errors="replace")

    block = (
        f"{START_TAG}\n"
        f"import nuke\n"
        f"nuke.pluginAddPath(r\"{nuke_plugin_path}\")\n"
        f"{END_TAG}\n"
    )

    if START_TAG in content and END_TAG in content:
        pattern = re.compile(rf"{re.escape(START_TAG)}.*?{re.escape(END_TAG)}\n?", re.DOTALL)
        new_content = pattern.sub(block, content)
        status_msg = f"[*] Updated existing CorridorKey registration in: {init_file}"
    else:
        new_content = content.rstrip() + ("\n\n" if content.strip() else "") + block
        status_msg = f"[*] Added CorridorKey registration to: {init_file}"

    init_file.write_text(new_content, encoding="utf-8")

    # If user previously placed direct copies of CorridorKeyer files into ~/.nuke, update them too
    import shutil
    for fname in ["CorridorKeyer.gizmo", "corridorkey_nuke.py", "menu.py"]:
        dest = nuke_dir / fname
        src = nuke_plugin_dir / fname
        if dest.is_file() and src.is_file():
            try:
                shutil.copy2(src, dest)
                print(f"[*] Updated existing file in ~/.nuke: {fname}")
            except Exception as e:
                print(f"[Warning] Could not update {dest}: {e}")

    print("\n" + "=" * 65)
    print(" [SUCCESS] CorridorKey 2.0 has been successfully linked to Nuke!")
    print("=" * 65)
    print(status_msg)
    print(f"  Target Plugin Path: {nuke_plugin_path}")
    print("=" * 65)
    return True


def uninstall() -> bool:
    """Remove CorridorKey registration from ~/.nuke/init.py."""
    nuke_dir = get_nuke_dir()
    init_file = nuke_dir / "init.py"
    if not init_file.is_file():
        print("[*] ~/.nuke/init.py not found. Nothing to uninstall.")
        return True

    try:
        content = init_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = init_file.read_text(encoding="cp949", errors="replace")

    if START_TAG in content and END_TAG in content:
        pattern = re.compile(rf"\n?{re.escape(START_TAG)}.*?{re.escape(END_TAG)}\n?", re.DOTALL)
        new_content = pattern.sub("\n", content).strip() + "\n"
        init_file.write_text(new_content, encoding="utf-8")
        print("\n" + "=" * 65)
        print(" [SUCCESS] CorridorKey 2.0 was successfully uninstalled from Nuke.")
        print(f"  Modified: {init_file}")
        print("=" * 65)
    else:
        print("[*] CorridorKey 2.0 is not currently registered in ~/.nuke/init.py.")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--install", action="store_true", help="Install to ~/.nuke/init.py")
    ap.add_argument("--uninstall", action="store_true", help="Uninstall from ~/.nuke/init.py")
    ap.add_argument("root", nargs="?", default=".", help="CorridorKey repository root")

    args = ap.parse_args()

    root_path = Path(str(args.root).strip('"\'')).resolve()

    if args.uninstall:
        uninstall()
    else:
        install(root_path)


if __name__ == "__main__":
    main()
