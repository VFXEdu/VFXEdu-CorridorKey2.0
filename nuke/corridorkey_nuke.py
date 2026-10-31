#!/usr/bin/env python3
"""CorridorKey 2.0 Nuke Bridge & Gizmo Controller.

Provides native integration between The Foundry Nuke and VFXEdu CorridorKey 2.0.
Works seamlessly with Nuke 12, 13, 14, 15, 16, and 17.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time

try:
    import nuke
except ImportError:
    # Allows offline testing / unit test mocking outside Nuke
    nuke = None


def _has_torch(py_path: Path | None) -> bool:
    """Verify if a python executable has PyTorch installed in site-packages."""
    if not py_path or not py_path.is_file():
        return False
    parent = py_path.parent
    site_dirs = [
        parent / "Lib" / "site-packages" / "torch",
        parent.parent / "Lib" / "site-packages" / "torch",
    ]
    return any(d.is_dir() for d in site_dirs)


def find_corridorkey_root() -> Path | None:
    """Auto-detect the CorridorKey root repository or portable installation."""
    candidates = []

    # 1. Environment variable
    env_root = os.environ.get("CORRIDORKEY_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    # 2. Known portable installations with weights
    candidates.append(Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v0.1.3"))
    candidates.append(Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v1.1.1"))

    # 3. Main Development Repository

    # 4. Relative to this script (e.g. repo_root/nuke/corridorkey_nuke.py -> repo_root)
    this_dir = Path(__file__).resolve().parent
    candidates.append(this_dir.parent)
    candidates.append(this_dir)

    for p in candidates:
        if p and p.is_dir() and (p / "infer.py").is_file():
            # Check if this candidate actually has a working python with torch
            py = find_python_executable(p)
            if py and _has_torch(py):
                return p.resolve()

    # Fallback to any directory having infer.py
    for p in candidates:
        if p and p.is_dir() and (p / "infer.py").is_file():
            return p.resolve()

    return None


def find_python_executable(ck_root: Path | None) -> Path | None:
    """Find a Python executable with PyTorch installed."""
    if ck_root and ck_root.is_dir():
        # Check venv first if on Windows
        venv_py_win = ck_root / "venv" / "Scripts" / "python.exe"
        if _has_torch(venv_py_win):
            return venv_py_win.resolve()

        # Check embedded python (portable release)
        embed_py = ck_root / "python_embed" / "python.exe"
        if _has_torch(embed_py):
            return embed_py.resolve()

        # Check POSIX venv
        venv_py_posix = ck_root / "venv" / "bin" / "python"
        if _has_torch(venv_py_posix):
            return venv_py_posix.resolve()

    # Cross-search known working environments if ck_root's Python is not setup
    fallback_pythons = [
        Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v0.1.3\python_embed\python.exe"),
    ]
    for fpy in fallback_pythons:
        if _has_torch(fpy):
            return fpy.resolve()

    # Last resort fallback
    if ck_root:
        p1 = ck_root / "venv" / "Scripts" / "python.exe"
        if p1.is_file():
            return p1.resolve()
        p2 = ck_root / "python_embed" / "python.exe"
        if p2.is_file():
            return p2.resolve()

    return None


def build_command_args(
    ck_root: Path,
    python_exe: Path,
    input_path: str,
    output_dir: str,
    *,
    output_format: str = "exr",
    exr_dtype: str = "half",
    outputs: list[str] | None = None,
    despill_strength: float = 0.5,
    auto_vram: bool = True,
    low_vram: bool = False,
    hann_chunk: int = 0,
    hann_stride: int = 0,
    hint_first_frame: str | None = None,
    carry_hint: bool = True,
    hint_quality: float = 0.95,
    linear_workflow: bool = True,
) -> list[str]:
    """Construct CLI arguments for CorridorKey infer.py."""
    infer_py = ck_root / "infer.py"
    if not infer_py.is_file():
        raise FileNotFoundError(f"infer.py not found in {ck_root}")

    cmd = [
        str(python_exe),
        str(infer_py),
        "--input", str(input_path),
        "--output_dir", str(output_dir),
        "--output_format", str(output_format),
        "--exr_dtype", str(exr_dtype),
        "--despill_strength", f"{float(despill_strength):.2f}",
    ]

    if outputs:
        cmd.extend(["--outputs"] + list(outputs))
    else:
        cmd.extend(["--outputs", "alpha", "fg", "cutout"])

    if low_vram:
        cmd.append("--low_vram")

    if not auto_vram and hann_chunk > 0:
        cmd.extend(["--hann_chunk", str(int(hann_chunk))])
        if hann_stride > 0:
            cmd.extend(["--hann_stride", str(int(hann_stride))])

    if hint_first_frame and os.path.exists(hint_first_frame):
        cmd.extend(["--hint_first_frame", str(hint_first_frame)])
        cmd.extend(["--hint_quality", f"{float(hint_quality):.2f}"])

    if not carry_hint:
        cmd.append("--no_carry_hint")

    if linear_workflow:
        # Pass --frame_dir_linear for frame directories (not video containers)
        is_video = str(input_path).lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".m4v"))
        if not is_video:
            cmd.append("--frame_dir_linear")
        cmd.append("--cutout_linear")

    return cmd


def execute_keyer(node) -> bool:
    """Main execution function triggered by the Gizmo button in Nuke."""
    if nuke is None:
        print("[CorridorKey] Error: nuke module not available.")
        return False

    # 1. Resolve CorridorKey root & Python executable
    ck_root_val = node.knob("ck_root").value().strip() if node.knob("ck_root") else ""
    ck_root = Path(ck_root_val) if ck_root_val and os.path.isdir(ck_root_val) else find_corridorkey_root()
    if not ck_root or not ck_root.is_dir():
        nuke.message(
            "CorridorKey 2.0 root directory not found!\n\n"
            "Please specify the CorridorKey installation path in the 'System / Paths' tab."
        )
        return False

    py_exe_val = node.knob("python_path").value().strip() if node.knob("python_path") else ""
    python_exe = Path(py_exe_val) if py_exe_val and os.path.isfile(py_exe_val) else find_python_executable(ck_root)
    if not python_exe or not python_exe.is_file() or not _has_torch(python_exe):
        nuke.message(
            f"PyTorch-enabled Python executable not found for CorridorKey!\n\n"
            f"Checked Root: {ck_root}\n"
            f"Please ensure PyTorch is installed in venv or python_embed."
        )
        return False

    # 2. Check input node
    source_node = node.input(0)
    if not source_node:
        nuke.message("Please connect a Source plate to Input 0 (Source) of CorridorKeyer!")
        return False

    # Determine frame range
    range_mode = node.knob("frame_range").value() if node.knob("frame_range") else "Input Node Range"
    if range_mode == "Global Range":
        first_frame = int(nuke.root().firstFrame())
        last_frame = int(nuke.root().lastFrame())
    elif range_mode == "Custom":
        first_frame = int(node.knob("first_frame").value())
        last_frame = int(node.knob("last_frame").value())
    else:  # Input Node Range
        first_frame = int(source_node.firstFrame())
        last_frame = int(source_node.lastFrame())

    # 3. Setup output directory safely
    out_dir_val = ""
    if node.knob("output_dir"):
        try:
            out_dir_val = node.knob("output_dir").evaluate().strip()
        except Exception:
            out_dir_val = node.knob("output_dir").value().strip()

    # If empty, invalid, or unsaved Nuke script
    if (
        not out_dir_val
        or out_dir_val.startswith("[file")
        or out_dir_val.startswith("./")
        or out_dir_val == "corridorkey_output"
    ):
        script_path = nuke.root().name()
        if script_path and script_path != "Root" and os.path.isabs(script_path):
            base_dir = os.path.dirname(script_path)
        else:
            base_dir = str(Path(tempfile.gettempdir()) / "corridorkey_output")
        out_dir_val = os.path.join(base_dir, "corridorkey_output")

    out_dir = Path(out_dir_val).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 4. Resolve input path
    input_path = ""
    is_direct_disk = False

    if source_node.Class() == "Read":
        file_path = source_node.knob("file").value()
        try:
            file_path = nuke.filename(source_node)
        except Exception:
            pass

        if file_path:
            lower = file_path.lower()
            if lower.endswith((".mp4", ".mov", ".mkv", ".avi", ".m4v")):
                if os.path.isfile(file_path):
                    input_path = file_path
                    is_direct_disk = True
            else:
                seq_dir = os.path.dirname(file_path)
                if os.path.isdir(seq_dir):
                    input_path = seq_dir
                    is_direct_disk = True

    # If source is modified or not a direct file, bake to a temp EXR sequence
    temp_plate_dir = None
    if not is_direct_disk:
        temp_plate_dir = out_dir / "_temp_plate_exr"
        temp_plate_dir.mkdir(parents=True, exist_ok=True)
        plate_pattern = str(temp_plate_dir / "plate_%06d.exr").replace("\\", "/")

        print(f"[CorridorKey] Baking source comp to temporary EXR sequence: {plate_pattern}")
        write_tmp = nuke.nodes.Write(inputs=[source_node])
        write_tmp.knob("file").setValue(plate_pattern)
        write_tmp.knob("file_type").setValue("exr")
        write_tmp.knob("datatype").setValue("16 bit half")
        write_tmp.knob("compression").setValue("Zip (1 scanline)")

        try:
            nuke.execute(write_tmp, first_frame, last_frame, 1)
        finally:
            nuke.delete(write_tmp)

        input_path = str(temp_plate_dir)

    # 5. Check FrameHint input (Input 1)
    hint_node = node.input(1)
    hint_file_path = None
    if hint_node:
        temp_hint_dir = out_dir / "_temp_hint"
        temp_hint_dir.mkdir(parents=True, exist_ok=True)
        hint_file_path = str(temp_hint_dir / "frame_hint.png").replace("\\", "/")

        print(f"[CorridorKey] Baking first-frame hint from Input 1 to: {hint_file_path}")
        write_hint = nuke.nodes.Write(inputs=[hint_node])
        write_hint.knob("file").setValue(hint_file_path)
        write_hint.knob("file_type").setValue("png")
        try:
            nuke.execute(write_hint, first_frame, first_frame, 1)
        finally:
            nuke.delete(write_hint)

    # 6. Read parameter knobs
    output_format = node.knob("output_format").value() if node.knob("output_format") else "exr"
    exr_dtype = node.knob("exr_dtype").value() if node.knob("exr_dtype") else "half"
    despill = float(node.knob("despill_strength").value()) if node.knob("despill_strength") else 0.5
    auto_vram = bool(node.knob("auto_vram").value()) if node.knob("auto_vram") else True
    low_vram = bool(node.knob("low_vram").value()) if node.knob("low_vram") else False
    hann_chunk = int(node.knob("hann_chunk").value()) if node.knob("hann_chunk") else 0
    hann_stride = int(node.knob("hann_stride").value()) if node.knob("hann_stride") else 0
    carry_hint = bool(node.knob("carry_hint").value()) if node.knob("carry_hint") else True
    hint_quality = float(node.knob("hint_quality").value()) if node.knob("hint_quality") else 0.95
    linear_wf = bool(node.knob("linear_workflow").value()) if node.knob("linear_workflow") else True

    # 7. Build CLI command
    cmd = build_command_args(
        ck_root=ck_root,
        python_exe=python_exe,
        input_path=input_path,
        output_dir=str(out_dir),
        output_format=output_format,
        exr_dtype=exr_dtype,
        outputs=["alpha", "fg", "cutout"],
        despill_strength=despill,
        auto_vram=auto_vram,
        low_vram=low_vram,
        hann_chunk=hann_chunk,
        hann_stride=hann_stride,
        hint_first_frame=hint_file_path,
        carry_hint=carry_hint,
        hint_quality=hint_quality,
        linear_workflow=linear_wf,
    )

    print(f"[CorridorKey] Executing Command:\n{' '.join(cmd)}")

    # 8. Run inference in background thread with Nuke ProgressTask
    def _run_worker():
        progress_task = None
        if nuke.GUI:
            progress_task = nuke.ProgressTask("CorridorKey 2.0 AI Keying")
            progress_task.setMessage("Initializing GPU AI models...")
            progress_task.setProgress(5)

        proc_env = os.environ.copy()
        _alloc_val = "max_split_size_mb:512" if sys.platform == "win32" else "expandable_segments:True"
        proc_env["PYTORCH_ALLOC_CONF"] = _alloc_val
        proc_env.pop("PYTORCH_CUDA_ALLOC_CONF", None)
        proc_env["PYTHONUTF8"] = "1"
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(ck_root),
            env=proc_env,
        )

        prog_regex = re.compile(r"(\d+)/(\d+)")
        output_logs = []

        for line in proc.stdout:
            output_logs.append(line)
            try:
                nuke.tprint(line.rstrip())
            except Exception:
                pass
            sys.stdout.write(line)
            sys.stdout.flush()

            line_clean = line.strip()
            if progress_task:
                if progress_task.isCancelled():
                    proc.terminate()
                    print("[CorridorKey] User cancelled keying.")
                    break

                progress_task.setMessage(line_clean[:80])
                m = prog_regex.search(line_clean)
                if m:
                    try:
                        cur, total = int(m.group(1)), int(m.group(2))
                        if total > 0:
                            pct = int(min(98, 10 + (cur / total) * 88))
                            progress_task.setProgress(pct)
                    except Exception:
                        pass

        ret_code = proc.wait()
        if progress_task:
            progress_task.setProgress(100)
            del progress_task

        if ret_code == 0:
            print("\n[CorridorKey] Inference completed successfully!")
            nuke.executeInMainThread(
                lambda: _on_success(node, input_path, out_dir, output_format, first_frame, last_frame)
            )
        else:
            tail_error = "".join(output_logs[-25:]) if output_logs else "No process output."
            print(f"\n[CorridorKey] ERROR: Inference failed with exit code {ret_code}.\n{tail_error}")
            nuke.executeInMainThread(
                lambda: nuke.message(
                    f"CorridorKey Inference Failed (Exit code: {ret_code})!\n\n"
                    f"--- Error Details ---\n{tail_error}"
                )
            )

    t = threading.Thread(target=_run_worker, daemon=True)
    t.start()
    return True


def _on_success(node, input_path: str, out_dir: Path, output_format: str, first_frame: int, last_frame: int):
    """Callback when keying finishes: updates Gizmo internals and builds DAG nodes."""
    import_mode = node.knob("import_to_dag").value() if node.knob("import_to_dag") else "Both"

    alpha_path = ""
    fg_path = ""
    cutout_path = ""

    if output_format == "exr":
        for sub in out_dir.iterdir():
            if sub.is_dir():
                sname = sub.name
                if "alpha_exr" in sname:
                    alpha_path = str(sub / "alpha_%06d.exr").replace("\\", "/")
                elif "fg_exr" in sname:
                    fg_path = str(sub / "fg_%06d.exr").replace("\\", "/")
                elif "cutout_exr" in sname:
                    cutout_path = str(sub / "cutout_%06d.exr").replace("\\", "/")
    else:
        for f in out_dir.iterdir():
            if f.is_file():
                fname = f.name
                if "alpha" in fname and fname.endswith(".mp4"):
                    alpha_path = str(f).replace("\\", "/")
                elif "fg" in fname and fname.endswith(".mp4"):
                    fg_path = str(f).replace("\\", "/")
                elif "cutout" in fname and fname.endswith((".mov", ".mp4")):
                    cutout_path = str(f).replace("\\", "/")

    # 1. Update internal Gizmo nodes if present
    try:
        with node:
            r_cutout = nuke.toNode("Read_Cutout")
            if r_cutout and cutout_path:
                r_cutout.knob("file").setValue(cutout_path)
                r_cutout.knob("first").setValue(first_frame)
                r_cutout.knob("last").setValue(last_frame)
                r_cutout.knob("origfirst").setValue(first_frame)
                r_cutout.knob("origlast").setValue(last_frame)

            r_alpha = nuke.toNode("Read_Alpha")
            if r_alpha and alpha_path:
                r_alpha.knob("file").setValue(alpha_path)
                r_alpha.knob("first").setValue(first_frame)
                r_alpha.knob("last").setValue(last_frame)

            r_fg = nuke.toNode("Read_FG")
            if r_fg and fg_path:
                r_fg.knob("file").setValue(fg_path)
                r_fg.knob("first").setValue(first_frame)
                r_fg.knob("last").setValue(last_frame)

            sw = nuke.toNode("Switch_Output")
            if sw:
                sw.knob("which").setValue(1)
    except Exception as e:
        print(f"[CorridorKey] Note: Internal Gizmo wiring update: {e}")

    # 2. Build external DAG nodes if requested
    if import_mode in ("Create Read Nodes in DAG", "Both"):
        _build_dag_node_tree(node, alpha_path, fg_path, cutout_path, first_frame, last_frame)

    if node.knob("status_lbl"):
        node.knob("status_lbl").setValue("<font color='#00ff88'><b>Render Completed!</b></font>")

    if node.knob("open_folder") and node.knob("open_folder").value():
        try:
            if sys.platform == "win32":
                os.startfile(str(out_dir))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(out_dir)])
            else:
                subprocess.Popen(["xdg-open", str(out_dir)])
        except Exception:
            pass

    nuke.message(f"CorridorKey 2.0 Keying Finished!\nOutput saved to:\n{out_dir}")


def _build_dag_node_tree(gizmo_node, alpha_path: str, fg_path: str, cutout_path: str, first: int, last: int):
    """Create clean Read -> Copy(Alpha) -> Premult node tree in Nuke's Node Graph."""
    gx = gizmo_node.xpos()
    gy = gizmo_node.ypos()

    if cutout_path:
        r_cut = nuke.nodes.Read(xpos=gx + 150, ypos=gy)
        r_cut.knob("file").setValue(cutout_path)
        r_cut.knob("first").setValue(first)
        r_cut.knob("last").setValue(last)
        r_cut.knob("origfirst").setValue(first)
        r_cut.knob("origlast").setValue(last)
        r_cut.knob("label").setValue("CorridorKey Cutout (RGBA)")

    if fg_path and alpha_path:
        r_fg = nuke.nodes.Read(xpos=gx, ypos=gy + 100)
        r_fg.knob("file").setValue(fg_path)
        r_fg.knob("first").setValue(first)
        r_fg.knob("last").setValue(last)
        r_fg.knob("origfirst").setValue(first)
        r_fg.knob("origlast").setValue(last)
        r_fg.knob("label").setValue("CorridorKey Clean FG")

        r_alpha = nuke.nodes.Read(xpos=gx + 120, ypos=gy + 100)
        r_alpha.knob("file").setValue(alpha_path)
        r_alpha.knob("first").setValue(first)
        r_alpha.knob("last").setValue(last)
        r_alpha.knob("origfirst").setValue(first)
        r_alpha.knob("origlast").setValue(last)
        r_alpha.knob("label").setValue("CorridorKey Alpha Matte")

        cpy = nuke.nodes.Copy(xpos=gx, ypos=gy + 180, inputs=[r_fg, r_alpha])
        cpy.knob("from0").setValue("rgba.alpha")
        cpy.knob("to0").setValue("rgba.alpha")

        pm = nuke.nodes.Premult(xpos=gx, ypos=gy + 240, inputs=[cpy])
        pm.knob("label").setValue("Keyed & Despilled")


def create_corridorkeyer_node():
    """Create a CorridorKeyer Group node directly in the active Nuke DAG."""
    if nuke is None:
        return None

    group = nuke.nodes.Group()
    group.setName("CorridorKeyer1")
    group.knob("tile_color").setValue(0x1a4a6eff)
    group.knob("note_font").setValue("Verdana Bold")

    tab = nuke.Tab_Knob("CorridorKeyer", "CorridorKeyer 2.0")
    group.addKnob(tab)

    title = nuke.Text_Knob(
        "title_lbl", "",
        "<font size='4' color='#00d2ff'><b>⚡ VFXEdu CorridorKey 2.0</b></font> <font color='#888888'>AI Green Screen Keyer</font>"
    )
    group.addKnob(title)

    btn_render = nuke.PyScript_Knob(
        "btn_render", "  🚀 Render CorridorKey Matte  ",
        "import corridorkey_nuke\ncorridorkey_nuke.execute_keyer(nuke.thisNode())"
    )
    group.addKnob(btn_render)

    status = nuke.Text_Knob("status_lbl", "Status: ", "<font color='#aaaaaa'>Ready to Key</font>")
    group.addKnob(status)

    div1 = nuke.Text_Knob("div1", "", "")
    group.addKnob(div1)

    grp_out = nuke.Tab_Knob("grp_out", "Output Settings", nuke.TABBEGANGROUP)
    group.addKnob(grp_out)

    out_dir = nuke.File_Knob("output_dir", "Output Directory")
    out_dir.setValue("[file dirname [value root.name]]/corridorkey_output")
    group.addKnob(out_dir)

    out_fmt = nuke.Enumeration_Knob("output_format", "Format", ["exr", "video"])
    out_fmt.setValue("exr")
    group.addKnob(out_fmt)

    exr_dt = nuke.Enumeration_Knob("exr_dtype", "EXR Bit Depth", ["half", "float"])
    exr_dt.setValue("half")
    group.addKnob(exr_dt)

    f_range = nuke.Enumeration_Knob("frame_range", "Frame Range", ["Input Node Range", "Global Range", "Custom"])
    group.addKnob(f_range)

    ff = nuke.Int_Knob("first_frame", "First")
    ff.setValue(int(nuke.root().firstFrame()))
    group.addKnob(ff)

    lf = nuke.Int_Knob("last_frame", "Last")
    lf.setValue(int(nuke.root().lastFrame()))
    group.addKnob(lf)

    grp_out_end = nuke.Tab_Knob("grp_out_end", "", nuke.TABENDGROUP)
    group.addKnob(grp_out_end)

    grp_param = nuke.Tab_Knob("grp_param", "AI Keying Parameters", nuke.TABBEGANGROUP)
    group.addKnob(grp_param)

    despill = nuke.Double_Knob("despill_strength", "Despill Strength")
    despill.setRange(0.0, 1.0)
    despill.setValue(0.5)
    group.addKnob(despill)

    auto_v = nuke.Boolean_Knob("auto_vram", "Auto VRAM Profiling")
    auto_v.setValue(True)
    group.addKnob(auto_v)

    low_v = nuke.Boolean_Knob("low_vram", "Force Low VRAM Mode")
    low_v.setValue(False)
    group.addKnob(low_v)

    h_chunk = nuke.Int_Knob("hann_chunk", "Hann Chunk (Frames)")
    h_chunk.setValue(80)
    group.addKnob(h_chunk)

    h_stride = nuke.Int_Knob("hann_stride", "Hann Stride (Frames)")
    h_stride.setValue(40)
    group.addKnob(h_stride)

    carry_h = nuke.Boolean_Knob("carry_hint", "Carry Hint to Long Clip")
    carry_h.setValue(True)
    group.addKnob(carry_h)

    lin_wf = nuke.Boolean_Knob("linear_workflow", "Scene-Linear HDR Workflow")
    lin_wf.setValue(True)
    group.addKnob(lin_wf)

    grp_param_end = nuke.Tab_Knob("grp_param_end", "", nuke.TABENDGROUP)
    group.addKnob(grp_param_end)

    import_dag = nuke.Enumeration_Knob("import_to_dag", "DAG Integration", ["Both", "Update Gizmo Output", "Create Read Nodes in DAG"])
    group.addKnob(import_dag)

    open_f = nuke.Boolean_Knob("open_folder", "Open Output Folder on Finish")
    open_f.setValue(False)
    group.addKnob(open_f)

    tab_sys = nuke.Tab_Knob("tab_sys", "System / Paths")
    group.addKnob(tab_sys)

    detected_root = find_corridorkey_root()
    ck_root_k = nuke.File_Knob("ck_root", "CorridorKey Root")
    if detected_root:
        ck_root_k.setValue(str(detected_root))
    group.addKnob(ck_root_k)

    detected_py = find_python_executable(detected_root)
    py_k = nuke.File_Knob("python_path", "Python Executable")
    if detected_py:
        py_k.setValue(str(detected_py))
    group.addKnob(py_k)

    with group:
        in_source = nuke.nodes.Input(name="Source", xpos=0, ypos=0)
        in_hint = nuke.nodes.Input(name="FrameHint", xpos=200, ypos=0)

        read_cutout = nuke.nodes.Read(name="Read_Cutout", xpos=100, ypos=100)
        read_cutout.knob("file").setValue("")

        read_fg = nuke.nodes.Read(name="Read_FG", xpos=220, ypos=100)
        read_fg.knob("file").setValue("")

        read_alpha = nuke.nodes.Read(name="Read_Alpha", xpos=340, ypos=100)
        read_alpha.knob("file").setValue("")

        sw = nuke.nodes.Switch(name="Switch_Output", inputs=[in_source, read_cutout], xpos=0, ypos=200)
        sw.knob("which").setValue(0)

        out = nuke.nodes.Output(inputs=[sw], xpos=0, ypos=300)

    return group
