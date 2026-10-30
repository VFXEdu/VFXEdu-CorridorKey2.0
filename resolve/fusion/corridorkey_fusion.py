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
    if sys.platform == "win32":
        if "RESOLVE_SCRIPT_API" not in os.environ:
            os.environ["RESOLVE_SCRIPT_API"] = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
        if "RESOLVE_SCRIPT_LIB" not in os.environ:
            os.environ["RESOLVE_SCRIPT_LIB"] = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
        if "PYTHONPATH" not in os.environ:
            os.environ["PYTHONPATH"] = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"

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


def update_status(tool, text: str):
    """Safely update the StatusLbl in Fusion Inspector."""
    if not tool:
        return
    try:
        inp = tool.FindInput("StatusLbl")
        if inp:
            inp.SetAttrs({"LINKS_Name": f"Status: {text}"})
    except Exception:
        pass


def _has_torch(py_path: Path | None) -> bool:
    """Verify whether a given Python environment actually has PyTorch installed."""
    if not py_path or not py_path.is_file():
        return False
    parent = py_path.parent
    site_dirs = [
        parent / "Lib" / "site-packages" / "torch" / "__init__.py",
        parent.parent / "Lib" / "site-packages" / "torch" / "__init__.py",
    ]
    return any(d.is_file() for d in site_dirs)


def find_corridorkey_root() -> Path:
    env_root = os.environ.get("CORRIDORKEY_ROOT")
    if env_root and Path(env_root).is_dir():
        return Path(env_root).resolve()

    candidates = [
        Path(__file__).resolve().parent.parent.parent,
        Path(r"K:\Pateron\CorridorKeyer2.0_Portable"),
        Path(r"K:\________________VFXEdu_Script\CorridorKeyer2.0"),
        Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v0.1.3"),
    ]
    for p in candidates:
        if p and p.is_dir() and (p / "infer.py").is_file():
            return p.resolve()
    return Path(".").resolve()


def find_python_executable(ck_root: Path) -> Path:
    # 1. First priority: look for Python environments that actually have PyTorch installed
    verified_candidates = [
        ck_root / "venv" / "Scripts" / "python.exe",
        ck_root / "python_embed" / "python.exe",
        Path(r"K:\Pateron\CorridorKeyer2.0_Portable\python_embed\python.exe"),
        Path(r"K:\________________VFXEdu_Script\CorridorKeyer2.0\venv\Scripts\python.exe"),
    ]
    for p in verified_candidates:
        if _has_torch(p):
            return p.resolve()

    # 2. Secondary fallback: any existing python executable
    for p in verified_candidates:
        if p.is_file():
            return p.resolve()

    return Path(sys.executable).resolve()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--node", required=True, help="CorridorKeyer node name in Fusion comp")
    ap.add_argument("--despill", type=float, default=0.5, help="Despill strength")
    ap.add_argument("--fmt", type=int, default=0, help="0: ProRes 4444, 1: EXR, 2: MP4")
    ap.add_argument("--low-vram", type=int, default=0, help="Force low vram")
    ap.add_argument("--auto-vram", type=int, default=1, help="Auto vram")

    args = ap.parse_args()

    print("=" * 65)
    print("  VFXEdu CorridorKey 2.0 - DaVinci Resolve AI Bridge")
    print(f"  Target Node : {args.node}")
    print(f"  Despill     : {args.despill:.2f}")
    print(f"  Format      : {args.fmt}")
    print(f"  Low VRAM    : {bool(args.low_vram)}")
    print("=" * 65)

    resolve, fusion = get_resolve_fusion()
    if not fusion:
        print("\n[ERROR] Could not connect to DaVinci Resolve Fusion scripting API.")
        print("Please ensure DaVinci Resolve is running.")
        time.sleep(3)
        return

    comp = fusion.GetCurrentComp()
    if not comp:
        print("\n[ERROR] No active Fusion composition open in Resolve.")
        time.sleep(3)
        return

    # Find CorridorKeyer tool
    tool = comp.FindTool(args.node)
    if not tool:
        for t in comp.GetToolList().values():
            if t.Name == args.node or "CorridorKeyer" in t.ID or "CorridorKeyer" in t.Name:
                tool = t
                break

    if not tool:
        print(f"\n[ERROR] Tool '{args.node}' not found in current composition.")
        time.sleep(3)
        return

    # 1. Update Inspector Status
    update_status(tool, "Analyzing source media...")

    # 2. Resolve source file path
    source_path = ""
    # 2.1 Try resolving from connected node (Loader or MediaIn)
    try:
        in_conn = tool.Input.GetConnectedOutput()
        if in_conn:
            src_tool = in_conn.GetTool()
            if src_tool:
                # If Loader node: has non-None Clip input
                clip_inp = getattr(src_tool, "Clip", None)
                if clip_inp is not None:
                    try:
                        p = str(clip_inp[comp.CurrentTime] or "")
                        if p and os.path.exists(p):
                            source_path = p
                    except Exception:
                        pass

                # If MediaIn node: has non-None MediaID input
                if not source_path:
                    media_inp = getattr(src_tool, "MediaID", None)
                    if media_inp is not None:
                        try:
                            p = str(media_inp[comp.CurrentTime] or "")
                            if p and os.path.exists(p):
                                source_path = p
                        except Exception:
                            pass
    except Exception as conn_err:
        print(f"[*] Note inspecting connected node: {conn_err}")

    # 2.2 If not resolved from node, query active timeline clip from DaVinci Resolve Project
    if (not source_path or not os.path.exists(source_path)) and resolve:
        try:
            pm = resolve.GetProjectManager()
            proj = pm.GetCurrentProject() if pm else None
            if proj:
                timeline = proj.GetCurrentTimeline()
                if timeline:
                    item = timeline.GetCurrentVideoItem()
                    if item:
                        mp_item = item.GetMediaPoolItem()
                        if mp_item:
                            fp = mp_item.GetClipProperty("File Path") or ""
                            if fp and os.path.exists(fp):
                                source_path = fp
        except Exception as tl_err:
            print(f"[*] Note querying timeline: {tl_err}")

    # 2.3 Fallback: query active MediaPool folder clips
    if (not source_path or not os.path.exists(source_path)) and resolve:
        try:
            pm = resolve.GetProjectManager()
            proj = pm.GetCurrentProject() if pm else None
            if proj:
                mp = proj.GetMediaPool()
                cur_folder = mp.GetCurrentFolder() if mp else None
                if cur_folder:
                    for clip in cur_folder.GetClipList():
                        fp = clip.GetClipProperty("File Path") or ""
                        if fp and os.path.exists(fp):
                            source_path = fp
                            break
        except Exception as mp_err:
            print(f"[*] Note querying media pool: {mp_err}")

    if not source_path or not os.path.exists(source_path):
        print(f"\n[ERROR] Source media not found!")
        print("💡 Solution: Connect MediaIn1 (or a Loader node) to CorridorKeyer's orange Input!")
        update_status(tool, "⚠️ Connect MediaIn to Input!")
        time.sleep(4)
        return

    print(f"[*] Source Media: {source_path}")

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

    print(f"[*] Starting AI Inference Engine...")
    print(f"    Command: {' '.join(cmd)}\n")
    update_status(tool, "🚀 GPU AI Running...")

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
        print(line, end="")
        m = prog_regex.search(line)
        if m:
            cur, total = int(m.group(1)), int(m.group(2))
            if total > 0:
                pct = int((cur / total) * 100)
                update_status(tool, f"Rendering... {pct}%")

    ret_code = proc.wait()
    if ret_code != 0:
        print(f"\n[ERROR] Inference failed with exit code {ret_code}.")
        update_status(tool, f"Inference Failed ({ret_code})")
        time.sleep(4)
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

        update_status(tool, "✨ Render Complete!")
        print(f"\n[SUCCESS] Successfully keyed and added Loader into Fusion: {rendered_file}")
    except Exception as e:
        print(f"[Note] Adding Loader to Fusion: {e}")

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
        print(f"[Note] Importing into Media Pool: {e}")

    print("\n" + "=" * 65)
    print(" [DONE] CorridorKey 2.0 AI Processing Completed!")
    print("=" * 65)
    time.sleep(2)


if __name__ == "__main__":
    main()
