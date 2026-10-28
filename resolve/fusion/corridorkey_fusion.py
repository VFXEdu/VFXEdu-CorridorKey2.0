#!/usr/bin/env python3
"""CorridorKey 2.0 Fusion Page Controller.

Communicates with DaVinci Resolve's Fusion page to execute AI keying directly from
the CorridorKeyer Fuse node without any popups, and automatically loads the result into the Flow.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


def get_resolve_fusion():
    """Connect to DaVinci Resolve and Fusion API."""
    api_paths = [
        r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        "/opt/resolve/Developer/Scripting/Modules",
    ]
    for p in api_paths:
        if os.path.exists(p) and p not in sys.path:
            sys.path.append(p)

    resolve = None
    fusion = None

    try:
        import DaVinciResolveScript as dvr_script
        resolve = dvr_script.scriptapp("Resolve")
        if resolve:
            fusion = resolve.Fusion()
            return resolve, fusion
    except Exception:
        pass

    try:
        import bmd
        resolve = bmd.scriptapp("Resolve")
        fusion = bmd.scriptapp("Fusion")
        return resolve, fusion
    except Exception:
        pass

    return None, None


def _has_torch(py_path: Path | None) -> bool:
    if not py_path or not py_path.is_file():
        return False
    parent = py_path.parent
    site_dirs = [
        parent / "Lib" / "site-packages" / "torch",
        parent.parent / "Lib" / "site-packages" / "torch",
    ]
    return any(d.is_dir() for d in site_dirs)


def find_corridorkey_root() -> Path:
    env_root = os.environ.get("CORRIDORKEY_ROOT")
    if env_root and Path(env_root).is_dir():
        return Path(env_root).resolve()

    candidates = [
        Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v0.1.1"),
        Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v1.1.1"),
        Path(r"K:\________________VFXEdu_Script\CorridorKeyer2.0"),
        Path(__file__).resolve().parent.parent.parent,
    ]
    for p in candidates:
        if p and p.is_dir() and (p / "infer.py").is_file():
            return p.resolve()
    return Path(".").resolve()


def find_python_executable(ck_root: Path) -> Path | None:
    venv_py = ck_root / "venv" / "Scripts" / "python.exe"
    if _has_torch(venv_py):
        return venv_py.resolve()

    embed_py = ck_root / "python_embed" / "python.exe"
    if _has_torch(embed_py):
        return embed_py.resolve()

    fallbacks = [
        Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v0.1.1\python_embed\python.exe"),
        Path(r"K:\________________VFXEdu_Script\CorridorKeyer2.0\venv\Scripts\python.exe"),
    ]
    for f in fallbacks:
        if _has_torch(f):
            return f.resolve()
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--node", required=True, help="CorridorKeyer node name in Fusion comp")
    ap.add_argument("--despill", type=float, default=0.5, help="Despill strength")
    ap.add_argument("--fmt", type=int, default=0, help="0: ProRes 4444, 1: EXR, 2: MP4")
    ap.add_argument("--low-vram", type=int, default=0, help="Force low vram")
    ap.add_argument("--auto-vram", type=int, default=1, help="Auto vram")

    args = ap.parse_args()

    resolve, fusion = get_resolve_fusion()
    if not fusion:
        print("[CorridorKey Fusion] Error: Could not connect to DaVinci Resolve Fusion.")
        return

    comp = fusion.GetCurrentComp()
    if not comp:
        print("[CorridorKey Fusion] Error: No active Fusion composition.")
        return

    # Find CorridorKeyer tool
    tool = comp.FindTool(args.node)
    if not tool:
        print(f"[CorridorKey Fusion] Error: Tool '{args.node}' not found in comp.")
        return

    # 1. Update Inspector Status
    try:
        tool.InStatus[comp.CurrentTime] = "Analyzing source media..."
    except Exception:
        pass

    # 2. Resolve source file path
    source_path = ""
    try:
        in_conn = tool.Input.GetConnectedOutput()
        if in_conn:
            src_tool = in_conn.GetTool()
            if src_tool:
                # If Loader node
                if hasattr(src_tool, "Clip"):
                    source_path = src_tool.Clip[comp.CurrentTime]
                # If MediaIn node
                elif hasattr(src_tool, "MediaID"):
                    source_path = src_tool.MediaID[comp.CurrentTime]

        # If not resolved from node, query active timeline clip from Resolve API
        if (not source_path or not os.path.exists(source_path)) and resolve:
            pm = resolve.GetProjectManager()
            proj = pm.GetCurrentProject()
            if proj:
                timeline = proj.GetCurrentTimeline()
                if timeline:
                    item = timeline.GetCurrentVideoItem()
                    if item:
                        mp_item = item.GetMediaPoolItem()
                        if mp_item:
                            source_path = mp_item.GetClipProperty("File Path") or ""
    except Exception as e:
        print(f"[CorridorKey Fusion] Warning resolving source path: {e}")

    if not source_path or not os.path.exists(source_path):
        print(f"[CorridorKey Fusion] Error: Source file not found: {source_path}")
        try:
            tool.InStatus[comp.CurrentTime] = "Error: Source file missing!"
        except Exception:
            pass
        return

    # 3. Setup output folder
    ck_root = find_corridorkey_root()
    py_exe = find_python_executable(ck_root)

    clip_stem = Path(source_path).stem
    out_dir = Path(source_path).parent / "CorridorKey_Renders" / f"{clip_stem}_keyed"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        out_dir = Path(tempfile.gettempdir()) / "CorridorKey_Renders" / f"{clip_stem}_keyed"
        out_dir.mkdir(parents=True, exist_ok=True)

    # 4. Determine format & outputs
    if args.fmt == 0:
        out_fmt = "video"
        outputs = ["cutout"]
        expected_ext = ".mov"
    elif args.fmt == 1:
        out_fmt = "exr"
        outputs = ["cutout", "alpha", "fg"]
        expected_ext = "_exr"
    else:
        out_fmt = "video"
        outputs = ["alpha", "fg"]
        expected_ext = ".mp4"

    # 5. Build infer.py command
    cmd = [
        str(py_exe),
        str(ck_root / "infer.py"),
        "--input", source_path,
        "--output_dir", str(out_dir),
        "--output_format", out_fmt,
        "--despill_strength", f"{args.despill:.2f}",
        "--outputs", *outputs,
    ]
    if args.low_vram:
        cmd.append("--low_vram")

    print(f"[CorridorKey Fusion] Running Inference:\n{' '.join(cmd)}")

    try:
        tool.InStatus[comp.CurrentTime] = "GPU AI inference running..."
    except Exception:
        pass

    # 6. Execute process
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(ck_root),
    )

    prog_regex = re.compile(r"(\d+)/(\d+)")
    for line in proc.stdout:
        m = prog_regex.search(line)
        if m:
            cur, total = int(m.group(1)), int(m.group(2))
            if total > 0:
                pct = int((cur / total) * 100)
                try:
                    tool.InStatus[comp.CurrentTime] = f"Rendering... {pct}%"
                except Exception:
                    pass

    ret_code = proc.wait()
    if ret_code != 0:
        print(f"[CorridorKey Fusion] ERROR: Inference failed with code {ret_code}.")
        try:
            tool.InStatus[comp.CurrentTime] = f"Inference Failed ({ret_code})"
        except Exception:
            pass
        return

    # 7. Locate rendered file
    rendered_file = ""
    if out_fmt == "video":
        for f in out_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (".mov", ".mp4"):
                if "cutout" in f.name.lower() or "alpha" in f.name.lower():
                    rendered_file = str(f.resolve())
                    break
    else:
        for sub in out_dir.iterdir():
            if sub.is_dir() and "cutout_exr" in sub.name.lower():
                rendered_file = str((sub / "cutout_%06d.exr").resolve())
                break

    # 8. Create Loader node in Fusion and wire into Flow
    try:
        loader = comp.AddTool("Loader")
        if loader and rendered_file:
            loader.Clip = rendered_file
            loader.SetAttrs({"TOOLS_Name": f"{clip_stem}_Keyed"})

            # Position Loader neatly in Flow graph
            try:
                flow = comp.CurrentFrame.FlowView
                x, y = flow.GetPos(tool)
                flow.SetPos(loader, x + 100, y + 50)
            except Exception:
                pass

        tool.InStatus[comp.CurrentTime] = "✨ Render Completed!"
        print(f"[CorridorKey Fusion] Successfully loaded keyed media into Fusion Flow: {rendered_file}")
    except Exception as e:
        print(f"[CorridorKey Fusion] Note adding Loader to Fusion: {e}")

    # 9. Also import into DaVinci Resolve Media Pool
    try:
        if resolve and rendered_file:
            pm = resolve.GetProjectManager()
            proj = pm.GetCurrentProject()
            if proj:
                mp = proj.GetMediaPool()
                if mp:
                    root_folder = mp.GetRootFolder()
                    target_folder = None
                    for sub in root_folder.GetSubFolderList():
                        if sub.GetName() == "CorridorKey_Matte":
                            target_folder = sub
                            break
                    if not target_folder:
                        target_folder = mp.AddSubFolder(root_folder, "CorridorKey_Matte")
                    if target_folder:
                        mp.SetCurrentFolder(target_folder)
                    mp.ImportMedia([rendered_file])
    except Exception as e:
        print(f"[CorridorKey Fusion] Note importing into Media Pool: {e}")


if __name__ == "__main__":
    main()
