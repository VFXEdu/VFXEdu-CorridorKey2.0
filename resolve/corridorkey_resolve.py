#!/usr/bin/env python3
"""CorridorKey 2.0 DaVinci Resolve Bridge & Edit/Color Page Controller.

Provides native integration between Blackmagic Design DaVinci Resolve and VFXEdu CorridorKey 2.0.
Works seamlessly with DaVinci Resolve Studio & Free versions (Resolve 17, 18, 19, 20).
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

# ---------------------------------------------------------------------------
# 1. Resolve API Initialization
# ---------------------------------------------------------------------------
resolve = None
fusion = None


def init_resolve():
    """Connect to DaVinci Resolve Python Scripting API."""
    global resolve, fusion

    api_paths = [
        r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        "/opt/resolve/Developer/Scripting/Modules",
    ]
    for p in api_paths:
        if os.path.exists(p) and p not in sys.path:
            sys.path.append(p)

    try:
        import DaVinciResolveScript as dvr_script
        resolve = dvr_script.scriptapp("Resolve")
        if resolve:
            fusion = resolve.Fusion()
            return resolve
    except Exception:
        pass

    try:
        if "resolve" in globals():
            resolve = globals()["resolve"]
            fusion = resolve.Fusion()
            return resolve
    except Exception:
        pass

    try:
        import bmd
        resolve = bmd.scriptapp("Resolve")
        fusion = bmd.scriptapp("Fusion")
        return resolve
    except Exception:
        pass

    return None


init_resolve()


# ---------------------------------------------------------------------------
# 2. PySide GUI Initialization
# ---------------------------------------------------------------------------
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Qt, Signal, Slot
except ImportError:
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
        from PySide2.QtCore import Qt, Signal, Slot
    except ImportError:
        QtWidgets = None
        QtCore = None
        QtGui = None


# ---------------------------------------------------------------------------
# 3. Path & Environment Resolution
# ---------------------------------------------------------------------------
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

    env_root = os.environ.get("CORRIDORKEY_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    candidates.append(Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v0.1.3"))
    candidates.append(Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v1.1.1"))

    this_dir = Path(__file__).resolve().parent
    candidates.append(this_dir.parent)
    candidates.append(this_dir)

    for p in candidates:
        if p and p.is_dir() and (p / "infer.py").is_file():
            py = find_python_executable(p)
            if py and _has_torch(py):
                return p.resolve()

    for p in candidates:
        if p and p.is_dir() and (p / "infer.py").is_file():
            return p.resolve()

    return None


def find_python_executable(ck_root: Path | None) -> Path | None:
    """Find a Python executable with PyTorch installed."""
    if ck_root and ck_root.is_dir():
        venv_py_win = ck_root / "venv" / "Scripts" / "python.exe"
        if _has_torch(venv_py_win):
            return venv_py_win.resolve()

        embed_py = ck_root / "python_embed" / "python.exe"
        if _has_torch(embed_py):
            return embed_py.resolve()

        venv_py_posix = ck_root / "venv" / "bin" / "python"
        if _has_torch(venv_py_posix):
            return venv_py_posix.resolve()

    fallback_pythons = [
        Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v0.1.3\python_embed\python.exe"),
    ]
    for fpy in fallback_pythons:
        if _has_torch(fpy):
            return fpy.resolve()

    if ck_root:
        p1 = ck_root / "venv" / "Scripts" / "python.exe"
        if p1.is_file():
            return p1.resolve()
        p2 = ck_root / "python_embed" / "python.exe"
        if p2.is_file():
            return p2.resolve()

    return None


# ---------------------------------------------------------------------------
# 4. Resolve Context Helper
# ---------------------------------------------------------------------------
def get_current_timeline_clip_info() -> dict | None:
    """Get the active timeline clip at the playhead in Edit or Color page."""
    global resolve
    if not resolve:
        init_resolve()
    if not resolve:
        return None

    try:
        pm = resolve.GetProjectManager()
        proj = pm.GetCurrentProject()
        if not proj:
            return None
        timeline = proj.GetCurrentTimeline()
        if not timeline:
            return None

        # Get current clip at playhead
        item = timeline.GetCurrentVideoItem()
        if not item:
            # Fallback: try getting first item on track 1
            items = timeline.GetItemListInTrack("video", 1)
            if items:
                item = items[0]

        if not item:
            return None

        name = item.GetName()
        start = item.GetStart()
        end = item.GetEnd()
        duration = item.GetDuration()
        left_offset = item.GetLeftOffset()  # In-point frame in source clip
        right_offset = item.GetRightOffset()

        media_item = item.GetMediaPoolItem()
        file_path = ""
        fps = 24.0
        if media_item:
            file_path = media_item.GetClipProperty("File Path") or ""
            fps_str = media_item.GetClipProperty("FPS") or "24"
            try:
                fps = float(fps_str)
            except Exception:
                fps = 24.0

        return {
            "item": item,
            "name": name,
            "file_path": file_path,
            "start": start,
            "end": end,
            "duration": duration,
            "left_offset": left_offset,
            "right_offset": right_offset,
            "fps": fps,
            "timeline": timeline,
            "project": proj,
        }
    except Exception as e:
        print(f"[CorridorKey Resolve] Error getting clip info: {e}")
        return None


# ---------------------------------------------------------------------------
# 5. Worker Thread for Running Inference
# ---------------------------------------------------------------------------
class InferenceWorker(QtCore.QThread):
    progress_updated = Signal(int, str)
    finished = Signal(int, str, str)  # ret_code, out_dir, rendered_file

    def __init__(self, cmd: list[str], ck_root: Path, out_dir: Path, expected_name: str, fmt: str):
        super().__init__()
        self.cmd = cmd
        self.ck_root = ck_root
        self.out_dir = out_dir
        self.expected_name = expected_name
        self.fmt = fmt
        self.is_aborted = False
        self.proc = None

    def run(self):
        try:
            proc_env = os.environ.copy()
            proc_env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
            proc_env["PYTHONUTF8"] = "1"
            self.proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(self.ck_root),
                env=proc_env,
            )

            prog_regex = re.compile(r"(\d+)/(\d+)")
            logs = []

            for line in self.proc.stdout:
                if self.is_aborted:
                    self.proc.terminate()
                    break

                logs.append(line)
                line_clean = line.strip()

                m = prog_regex.search(line_clean)
                if m:
                    try:
                        cur, total = int(m.group(1)), int(m.group(2))
                        if total > 0:
                            pct = int(min(98, 10 + (cur / total) * 88))
                            self.progress_updated.emit(pct, line_clean[:70])
                    except Exception:
                        pass
                else:
                    self.progress_updated.emit(-1, line_clean[:70])

            ret_code = self.proc.wait() if not self.is_aborted else -1

            rendered_path = ""
            if ret_code == 0:
                # Find rendered cutout or alpha
                if self.fmt == "video":
                    for f in self.out_dir.iterdir():
                        if f.is_file() and f.suffix.lower() in (".mov", ".mp4"):
                            if "cutout" in f.name.lower() or "alpha" in f.name.lower():
                                rendered_path = str(f.resolve())
                                break
                else:
                    for sub in self.out_dir.iterdir():
                        if sub.is_dir() and "cutout_exr" in sub.name.lower():
                            rendered_path = str(sub.resolve())
                            break

            tail = "".join(logs[-25:]) if logs else ""
            self.finished.emit(ret_code, str(self.out_dir), rendered_path or tail)

        except Exception as exc:
            self.finished.emit(1, str(self.out_dir), str(exc))

    def abort(self):
        self.is_aborted = True
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 6. Resolve Edit / Color UI Dialog
# ---------------------------------------------------------------------------
class CorridorKeyResolveDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VFXEdu CorridorKey 2.0 - DaVinci Resolve")
        self.resize(580, 520)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.clip_info = get_current_timeline_clip_info()
        self.ck_root = find_corridorkey_root()
        self.py_exe = find_python_executable(self.ck_root)

        self._setup_ui()
        self._apply_theme()
        self._refresh_clip_display()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Title Banner
        hdr_layout = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("⚡ VFXEdu CorridorKey 2.0")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00d2ff;")
        hdr_layout.addWidget(title)

        badge = QtWidgets.QLabel("Edit & Color Bridge")
        badge.setStyleSheet(
            "background-color: #238636; color: #ffffff; padding: 3px 8px; "
            "border-radius: 4px; font-weight: bold; font-size: 11px;"
        )
        hdr_layout.addWidget(badge)
        hdr_layout.addStretch()
        layout.addLayout(hdr_layout)

        # 1. Selected Clip Group
        grp_clip = QtWidgets.QGroupBox("Target Timeline Clip")
        v_clip = QtWidgets.QVBoxLayout(grp_clip)
        v_clip.setSpacing(6)

        self.lbl_clip_name = QtWidgets.QLabel("Clip: <No Clip Selected>")
        self.lbl_clip_name.setStyleSheet("font-weight: bold; font-size: 13px; color: #f0f6fc;")
        v_clip.addWidget(self.lbl_clip_name)

        self.lbl_clip_path = QtWidgets.QLabel("File: -")
        self.lbl_clip_path.setStyleSheet("color: #8b949e; font-size: 11px;")
        self.lbl_clip_path.setWordWrap(True)
        v_clip.addWidget(self.lbl_clip_path)

        self.lbl_clip_range = QtWidgets.QLabel("Range: -")
        self.lbl_clip_range.setStyleSheet("color: #58a6ff; font-size: 11px;")
        v_clip.addWidget(self.lbl_clip_range)

        btn_refresh = QtWidgets.QPushButton("🔄 Refresh Playhead Clip")
        btn_refresh.setFixedHeight(26)
        btn_refresh.clicked.connect(self._on_refresh_clicked)
        v_clip.addWidget(btn_refresh)
        layout.addWidget(grp_clip)

        # 2. Keying Parameters Group
        grp_opt = QtWidgets.QGroupBox("Keying Parameters")
        grid = QtWidgets.QGridLayout(grp_opt)
        grid.setSpacing(10)

        # Output Format
        grid.addWidget(QtWidgets.QLabel("Format:"), 0, 0)
        self.cmb_fmt = QtWidgets.QComboBox()
        self.cmb_fmt.addItems([
            "ProRes 4444 MOV with Alpha (Recommended for Resolve)",
            "OpenEXR Sequence (16-bit Half)",
            "Alpha Matte MP4 + Clean FG MP4",
        ])
        grid.addWidget(self.cmb_fmt, 0, 1)

        # Despill Strength Slider
        grid.addWidget(QtWidgets.QLabel("Despill Strength:"), 1, 0)
        despill_layout = QtWidgets.QHBoxLayout()
        self.slider_despill = QtWidgets.QSlider(Qt.Horizontal)
        self.slider_despill.setRange(0, 100)
        self.slider_despill.setValue(50)
        self.lbl_despill_val = QtWidgets.QLabel("0.50")
        self.lbl_despill_val.setFixedWidth(36)
        self.slider_despill.valueChanged.connect(
            lambda v: self.lbl_despill_val.setText(f"{v / 100:.2f}")
        )
        despill_layout.addWidget(self.slider_despill)
        despill_layout.addWidget(self.lbl_despill_val)
        grid.addLayout(despill_layout, 1, 1)

        # Frame Range Mode
        grid.addWidget(QtWidgets.QLabel("Processing Range:"), 2, 0)
        self.cmb_range = QtWidgets.QComboBox()
        self.cmb_range.addItems([
            "Timeline Cut In/Out Only (Fast)",
            "Entire Source Video File",
        ])
        grid.addWidget(self.cmb_range, 2, 1)

        # Low VRAM Checkbox
        self.chk_low_vram = QtWidgets.QCheckBox("Force Low VRAM Mode (For <=8GB GPUs)")
        grid.addWidget(self.chk_low_vram, 3, 1)

        layout.addWidget(grp_opt)

        # 3. Resolve Timeline Integration Options
        grp_res = QtWidgets.QGroupBox("DaVinci Resolve Actions on Finish")
        v_res = QtWidgets.QVBoxLayout(grp_res)
        self.chk_import_pool = QtWidgets.QCheckBox("Import into Media Pool ('CorridorKey_Matte' Bin)")
        self.chk_import_pool.setChecked(True)
        v_res.addWidget(self.chk_import_pool)

        self.chk_place_v2 = QtWidgets.QCheckBox("Automatically place on Video Track V2 above clip")
        self.chk_place_v2.setChecked(True)
        v_res.addWidget(self.chk_place_v2)
        layout.addWidget(grp_res)

        # 4. Progress and Status
        self.prog_bar = QtWidgets.QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setFixedHeight(16)
        self.prog_bar.setTextVisible(False)
        layout.addWidget(self.prog_bar)

        self.lbl_status = QtWidgets.QLabel("Ready to key clip.")
        self.lbl_status.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        # 5. Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_render = QtWidgets.QPushButton("  🚀 Key Selected Clip  ")
        self.btn_render.setFixedHeight(40)
        self.btn_render.setStyleSheet(
            "background-color: #238636; color: #ffffff; font-weight: bold; font-size: 14px; border-radius: 6px;"
        )
        self.btn_render.clicked.connect(self._on_render_clicked)
        btn_layout.addWidget(self.btn_render)

        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0e1117;
                color: #c9d1d9;
                font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
            }
            QGroupBox {
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #58a6ff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QComboBox, QPushButton {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 4px 8px;
                color: #c9d1d9;
            }
            QPushButton:hover {
                background-color: #30363d;
            }
            QCheckBox {
                color: #c9d1d9;
            }
            QProgressBar {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #00d2ff;
                border-radius: 3px;
            }
        """)

    def _refresh_clip_display(self):
        self.clip_info = get_current_timeline_clip_info()
        if self.clip_info and self.clip_info["file_path"]:
            self.lbl_clip_name.setText(f"Clip: {self.clip_info['name']}")
            self.lbl_clip_path.setText(f"File: {self.clip_info['file_path']}")
            dur_sec = self.clip_info['duration'] / max(1.0, self.clip_info['fps'])
            self.lbl_clip_range.setText(
                f"Timeline In: {self.clip_info['start']} | Duration: {self.clip_info['duration']} frames "
                f"({dur_sec:.2f}s @ {self.clip_info['fps']:.2f} fps)"
            )
            self.btn_render.setEnabled(True)
        else:
            self.lbl_clip_name.setText("Clip: <No Video Clip at Playhead>")
            self.lbl_clip_path.setText("Please open the Edit or Color page and position the playhead over a video clip.")
            self.lbl_clip_range.setText("Range: -")
            self.btn_render.setEnabled(False)

    def _on_refresh_clicked(self):
        self._refresh_clip_display()
        self.lbl_status.setText("Clip information refreshed from DaVinci Resolve.")

    def _on_render_clicked(self):
        if not self.clip_info or not self.clip_info["file_path"]:
            QtWidgets.QMessageBox.warning(self, "No Clip", "Please select a valid clip in DaVinci Resolve.")
            return

        if not self.ck_root or not self.py_exe:
            QtWidgets.QMessageBox.critical(
                self, "CorridorKey Not Found",
                "CorridorKey 2.0 engine or PyTorch python environment was not found.\n"
                "Please ensure CorridorKey 2.0 portable or venv is installed."
            )
            return

        input_file = self.clip_info["file_path"]
        if not os.path.exists(input_file):
            QtWidgets.QMessageBox.critical(self, "File Missing", f"Source file does not exist on disk:\n{input_file}")
            return

        # Prepare Output Directory
        proj_name = self.clip_info["project"].GetName() if self.clip_info["project"] else "ResolveProject"
        clip_stem = Path(input_file).stem
        out_base = Path(input_file).parent / "CorridorKey_Renders"
        try:
            out_base.mkdir(parents=True, exist_ok=True)
        except Exception:
            out_base = Path(tempfile.gettempdir()) / "CorridorKey_Renders"
            out_base.mkdir(parents=True, exist_ok=True)

        out_dir = out_base / f"{clip_stem}_keyed"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Determine Format
        fmt_idx = self.cmb_fmt.currentIndex()
        if fmt_idx == 0:
            out_fmt = "video"
            outputs = ["cutout"]
        elif fmt_idx == 1:
            out_fmt = "exr"
            outputs = ["cutout", "alpha", "fg"]
        else:
            out_fmt = "video"
            outputs = ["alpha", "fg"]

        # Build CLI
        infer_py = self.ck_root / "infer.py"
        cmd = [
            str(self.py_exe),
            str(infer_py),
            "--input", input_file,
            "--output_dir", str(out_dir),
            "--output_format", out_fmt,
            "--despill_strength", f"{self.slider_despill.value() / 100:.2f}",
            "--outputs", *outputs,
        ]

        if self.chk_low_vram.isChecked():
            cmd.append("--low_vram")

        # Range Option: Cut In/Out
        if self.cmb_range.currentIndex() == 0:
            # Cut only: offset and num_frames
            left_offset = self.clip_info.get("left_offset", 0)
            duration = self.clip_info.get("duration", -1)
            # CorridorKey supports num_frames
            if duration > 0:
                cmd.extend(["--num_frames", str(duration)])

        # Start Worker
        self.btn_render.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.prog_bar.setValue(5)
        self.lbl_status.setText("Initializing AI Models on GPU...")

        self.worker = InferenceWorker(cmd, self.ck_root, out_dir, clip_stem, out_fmt)
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_cancel_clicked(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.abort()
            self.lbl_status.setText("Keying cancelled by user.")
            self.btn_render.setEnabled(True)
            self.btn_cancel.setEnabled(False)

    def _on_progress(self, pct: int, msg: str):
        if pct >= 0:
            self.prog_bar.setValue(pct)
        if msg:
            self.lbl_status.setText(msg)

    def _on_finished(self, ret_code: int, out_dir: str, result_path: str):
        self.btn_render.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        if ret_code != 0:
            self.prog_bar.setValue(0)
            self.lbl_status.setText("Keying failed.")
            QtWidgets.QMessageBox.critical(
                self, "Inference Failed",
                f"CorridorKey inference returned error (Exit code: {ret_code}):\n\n{result_path}"
            )
            return

        self.prog_bar.setValue(100)
        self.lbl_status.setText("✨ Keying finished successfully!")

        # Import to Media Pool and/or Timeline
        if result_path and os.path.exists(result_path):
            self._import_to_resolve(result_path)

        QtWidgets.QMessageBox.information(
            self, "Complete",
            f"CorridorKey 2.0 keying completed!\n\nRendered Output:\n{result_path}"
        )

    def _import_to_resolve(self, media_path: str):
        """Import the rendered media into DaVinci Resolve Media Pool and timeline."""
        global resolve
        if not resolve:
            return

        try:
            pm = resolve.GetProjectManager()
            proj = pm.GetCurrentProject()
            if not proj:
                return

            mp = proj.GetMediaPool()
            if not mp:
                return

            # 1. Create or select dedicated CorridorKey folder in Media Pool
            if self.chk_import_pool.isChecked():
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

                imported = mp.ImportMedia([media_path])
                print(f"[CorridorKey Resolve] Imported {len(imported)} clip(s) to Media Pool.")

                # 2. Place on Track V2 directly above the source clip
                if self.chk_place_v2.isChecked() and imported:
                    timeline = proj.GetCurrentTimeline()
                    if timeline:
                        track_count = timeline.GetTrackCount("video")
                        if track_count < 2:
                            timeline.AddTrack("video")

                        # Append or insert media
                        mp.AppendToTimeline(imported[0])
                        print("[CorridorKey Resolve] Appended keyed clip to timeline.")
        except Exception as e:
            print(f"[CorridorKey Resolve] Note during Resolve import: {e}")


# ---------------------------------------------------------------------------
# 7. Main Entry Point
# ---------------------------------------------------------------------------
def main():
    if QtWidgets is None:
        print("[CorridorKey Resolve] PySide is required to display the GUI dialog.")
        return

    app = QtWidgets.QApplication.instance()
    created_app = False
    if not app:
        app = QtWidgets.QApplication(sys.argv)
        created_app = True

    dlg = CorridorKeyResolveDialog()
    dlg.show()

    if created_app:
        app.exec()


if __name__ == "__main__":
    main()
