"""CorridorKey 2.0 AI Model & Weight Manager.

Provides metadata, file validation, on-demand automatic detection,
and a visual PySide6 manager dialog for downloading foundation AI models.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QProcess, QTimer, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QFrame,
    QWidget,
    QMessageBox,
    QApplication,
)

from i18n import tr, add_language_listener

ROOT = Path(__file__).resolve().parent

# Registry of all foundation models in CorridorKey 2.0
MODEL_REGISTRY: Dict[str, dict] = {
    "corridorkey": {
        "id": "corridorkey",
        "name": "CorridorKey 2.0 Core",
        "category": "required",
        "size_str": "~2.54 GB",
        "source": "Hugging Face · nikopueringer/CorridorKey2.0",
        "license": "CC BY-NC-SA 4.0",
        "desc": "Core spatio-temporal video keying & matting weights (v2).",
        "files": ["weights/corridorkey_v2.safetensors", "weights/foundation_stats.safetensors"],
        "check_file": "weights/corridorkey_v2.safetensors",
        "min_size": 1_000_000_000,
    },
    "cradio": {
        "id": "cradio",
        "name": "C-RADIO v4 (NVIDIA)",
        "category": "required",
        "size_str": "~1.65 GB",
        "source": "Hugging Face · nvidia/C-RADIOv4-SO400M",
        "license": "NVIDIA Open Model License",
        "desc": "High-resolution multi-scale visual foundation model.",
        "files": ["vfms/cradio/C-RADIOv4-SO400M/model.safetensors"],
        "check_file": "vfms/cradio/C-RADIOv4-SO400M/model.safetensors",
        "min_size": 1_000_000_000,
    },
    "moge": {
        "id": "moge",
        "name": "MoGe-2 ViT-B Depth (Microsoft)",
        "category": "required",
        "size_str": "~400 MB",
        "source": "Hugging Face · Ruicheng/moge-2-vitb-normal",
        "license": "MIT License",
        "desc": "Monocular 3D depth and surface normal foundation model.",
        "files": ["vfms/moge/model.pt"],
        "check_file": "vfms/moge/model.pt",
        "min_size": 200_000_000,
    },
    "rvm": {
        "id": "rvm",
        "name": "Robust Video Matting (DeepMind)",
        "category": "required",
        "size_str": "~258 MB",
        "source": "Google Cloud Storage CDN",
        "license": "CC BY 4.0",
        "desc": "Continuous recurrent video matting prepass backbone.",
        "files": ["vfms/rvm/pretrain_rvm_small16_256_204031069.npz"],
        "check_file": "vfms/rvm/pretrain_rvm_small16_256_204031069.npz",
        "min_size": 100_000_000,
    },
}


def check_model_status(package_root: Optional[Path] = None) -> Dict[str, dict]:
    """Check installation status of all registered models."""
    root = (package_root or ROOT).resolve()
    status = {}

    for mid, info in MODEL_REGISTRY.items():
        all_present = True
        total_bytes = 0
        missing = []

        for rel in info["files"]:
            p = root / rel
            if p.is_file() and p.stat().st_size > 1000:
                total_bytes += p.stat().st_size
            else:
                all_present = False
                missing.append(rel)

        chk_p = root / info["check_file"]
        is_installed = all_present and chk_p.is_file() and chk_p.stat().st_size >= info["min_size"]

        status[mid] = {
            **info,
            "installed": is_installed,
            "total_bytes": total_bytes,
            "size_formatted": _format_bytes(total_bytes) if is_installed else info["size_str"],
            "missing_files": missing,
        }

    return status


def are_required_models_installed(package_root: Optional[Path] = None) -> bool:
    """Return True if all 4 required keying models are installed."""
    status = check_model_status(package_root)
    return all(s["installed"] for s in status.values() if s["category"] == "required")


def get_missing_required_models(package_root: Optional[Path] = None) -> List[str]:
    """Return a list of user-friendly names of missing required models."""
    status = check_model_status(package_root)
    return [s["name"] for s in status.values() if s["category"] == "required" and not s["installed"]]


def _format_bytes(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 ** 3):.2f} GB"
    return f"{num_bytes / (1024 ** 2):.1f} MB"


class ModelCardWidget(QFrame):
    """UI card representing a single AI model with real-time status and download action."""

    download_requested = Signal(str)  # model_id

    def __init__(self, model_info: dict, parent=None):
        super().__init__(parent)
        self.model_id = model_info["id"]
        self.category = model_info["category"]
        self._build_ui(model_info)

    def _build_ui(self, info: dict):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            ModelCardWidget {
                background: #19202a;
                border: 1px solid #283344;
                border-radius: 8px;
                padding: 10px;
            }
            ModelCardWidget:hover {
                border-color: #3b4d66;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        # Left: Status Indicator Icon
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(28, 28)
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_icon)

        # Middle: Information
        v_info = QVBoxLayout()
        v_info.setSpacing(4)

        h_title = QHBoxLayout()
        self.lbl_name = QLabel(info["name"])
        self.lbl_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        h_title.addWidget(self.lbl_name)

        badge_txt = tr("model_mgr_req_badge") if self.category == "required" else tr("model_mgr_opt_badge")
        badge_bg = "#1b4d3e" if self.category == "required" else "#2c3b4d"
        badge_fg = "#71e0be" if self.category == "required" else "#8fa3bf"
        self.lbl_badge = QLabel(badge_txt)
        self.lbl_badge.setStyleSheet(f"background: {badge_bg}; color: {badge_fg}; font-size: 10px; font-weight: bold; padding: 2px 6px; border-radius: 3px;")
        h_title.addWidget(self.lbl_badge)
        h_title.addStretch()
        v_info.addLayout(h_title)

        self.lbl_desc = QLabel(info["desc"])
        self.lbl_desc.setStyleSheet("color: #8fa3bf; font-size: 11px;")
        v_info.addWidget(self.lbl_desc)

        h_meta = QHBoxLayout()
        self.lbl_source = QLabel(f"Source: {info['source']} · License: {info['license']}")
        self.lbl_source.setStyleSheet("color: #5d6f85; font-size: 10px;")
        h_meta.addWidget(self.lbl_source)
        h_meta.addStretch()

        self.lbl_size = QLabel(info["size_str"])
        self.lbl_size.setStyleSheet("color: #bde3ff; font-size: 11px; font-weight: bold;")
        h_meta.addWidget(self.lbl_size)
        v_info.addLayout(h_meta)

        layout.addLayout(v_info, 1)

        # Right: Status Badge & Action Button
        v_action = QVBoxLayout()
        v_action.setAlignment(Qt.AlignCenter)
        v_action.setSpacing(6)

        self.lbl_status = QLabel()
        self.lbl_status.setAlignment(Qt.AlignCenter)
        v_action.addWidget(self.lbl_status)

        self.btn_download = QPushButton(tr("model_mgr_btn_download"))
        self.btn_download.setFixedWidth(100)
        self.btn_download.setStyleSheet("""
            QPushButton {
                background: #1e3852;
                border: 1px solid #355778;
                color: #bde3ff;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #284c6e;
                border-color: #4a77a3;
            }
        """)
        self.btn_download.clicked.connect(lambda: self.download_requested.emit(self.model_id))
        v_action.addWidget(self.btn_download)

        layout.addLayout(v_action)

        self.update_status(info)

    def update_status(self, info: dict):
        installed = info.get("installed", False)
        if installed:
            self.lbl_icon.setText("🟢")
            self.lbl_status.setText(f"<span style='color:#71e0be;font-weight:bold;'>✔ {tr('model_mgr_installed')}</span>")
            self.lbl_size.setText(info.get("size_formatted", info["size_str"]))
            self.btn_download.setText(tr("model_mgr_refresh"))
            self.btn_download.setStyleSheet("""
                QPushButton {
                    background: #1a2530;
                    border: 1px solid #2d3e50;
                    color: #798f9f;
                    padding: 5px 10px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #223242;
                    color: #b0c4d6;
                }
            """)
        else:
            self.lbl_icon.setText("🔴")
            self.lbl_status.setText(f"<span style='color:#e06c75;font-weight:bold;'>✘ {tr('model_mgr_missing')}</span>")
            self.lbl_size.setText(info["size_str"])
            self.btn_download.setText(tr("model_mgr_btn_download"))
            self.btn_download.setStyleSheet("""
                QPushButton {
                    background: #1e8061;
                    border: 1px solid #2db88c;
                    color: #ffffff;
                    font-weight: bold;
                    padding: 6px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #269e77;
                }
            """)


class ModelManagerDialog(QDialog):
    """Visual AI Model and Foundation Weights Manager Dialog."""

    def __init__(self, parent=None, initial_target: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("model_mgr_title"))
        self.setMinimumSize(780, 620)
        self.resize(820, 680)
        self.setStyleSheet("""
            QDialog {
                background: #11151c;
                color: #c9d1d9;
            }
            QLabel {
                color: #c9d1d9;
            }
        """)

        self.proc: Optional[QProcess] = None
        self.current_download_target: Optional[str] = None
        self.cards: Dict[str, ModelCardWidget] = {}

        self._build_ui()
        self.refresh_all()

        add_language_listener(self._retranslate_ui)

        if initial_target:
            QTimer.singleShot(400, lambda: self.start_download(initial_target))

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Header Title
        h_head = QHBoxLayout()
        v_title = QVBoxLayout()
        self.lbl_dlg_title = QLabel(tr("model_mgr_title"))
        self.lbl_dlg_title.setStyleSheet("font-size: 20px; font-weight: 800; color: #71e0be;")
        v_title.addWidget(self.lbl_dlg_title)

        self.lbl_dlg_desc = QLabel(tr("model_mgr_desc"))
        self.lbl_dlg_desc.setStyleSheet("color: #8fa3bf; font-size: 12px;")
        v_title.addWidget(self.lbl_dlg_desc)
        h_head.addLayout(v_title, 1)

        self.btn_open_folder = QPushButton(tr("model_mgr_btn_open_folder"))
        self.btn_open_folder.setStyleSheet("""
            QPushButton {
                background: #1e2733;
                border: 1px solid #364354;
                color: #bde3ff;
                padding: 6px 14px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #293647;
            }
        """)
        self.btn_open_folder.clicked.connect(self._open_weights_folder)
        h_head.addWidget(self.btn_open_folder)
        main_layout.addLayout(h_head)

        # Summary Bar
        self.pnl_summary = QFrame()
        self.pnl_summary.setStyleSheet("background: #161c24; border-radius: 6px; padding: 6px 12px;")
        h_sum = QHBoxLayout(self.pnl_summary)
        h_sum.setContentsMargins(10, 6, 10, 6)

        self.lbl_summary_req = QLabel()
        self.lbl_summary_req.setStyleSheet("font-size: 12px; font-weight: bold;")
        h_sum.addWidget(self.lbl_summary_req)
        h_sum.addSpacing(20)

        self.lbl_summary_opt = QLabel()
        self.lbl_summary_opt.setStyleSheet("font-size: 12px; color: #8fa3bf;")
        h_sum.addWidget(self.lbl_summary_opt)
        h_sum.addStretch()

        self.lbl_root_path = QLabel(f"{tr('model_mgr_path_lbl')} {ROOT.name}/")
        self.lbl_root_path.setStyleSheet("font-size: 11px; color: #5d6f85;")
        h_sum.addWidget(self.lbl_root_path)
        main_layout.addWidget(self.pnl_summary)

        # Scrollable Cards Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #222b38; border-radius: 6px; background: #13171f; }")

        cards_container = QWidget()
        self.cards_layout = QVBoxLayout(cards_container)
        self.cards_layout.setContentsMargins(10, 10, 10, 10)
        self.cards_layout.setSpacing(10)

        # 1. Required Models Header
        self.lbl_req_hdr = QLabel(f"━━━  {tr('model_mgr_req_header')}  ━━━")
        self.lbl_req_hdr.setStyleSheet("color: #71e0be; font-weight: bold; font-size: 12px; margin-top: 4px;")
        self.cards_layout.addWidget(self.lbl_req_hdr)

        for mid, info in MODEL_REGISTRY.items():
            if info["category"] == "required":
                card = ModelCardWidget(info, self)
                card.download_requested.connect(self.start_download)
                self.cards[mid] = card
                self.cards_layout.addWidget(card)

        # 2. Optional Models Header (if any)
        has_optional = any(info["category"] == "optional" for info in MODEL_REGISTRY.values())
        if has_optional:
            self.lbl_opt_hdr = QLabel(f"━━━  {tr('model_mgr_opt_header')}  ━━━")
            self.lbl_opt_hdr.setStyleSheet("color: #8fa3bf; font-weight: bold; font-size: 12px; margin-top: 8px;")
            self.cards_layout.addWidget(self.lbl_opt_hdr)

            for mid, info in MODEL_REGISTRY.items():
                if info["category"] == "optional":
                    card = ModelCardWidget(info, self)
                    card.download_requested.connect(self.start_download)
                    self.cards[mid] = card
                    self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()
        scroll.setWidget(cards_container)
        main_layout.addWidget(scroll, 1)

        # Download Progress & Status Area
        v_prog = QVBoxLayout()
        v_prog.setSpacing(4)

        h_prog_lbl = QHBoxLayout()
        self.lbl_prog_status = QLabel(tr("status_ready"))
        self.lbl_prog_status.setStyleSheet("color: #99b0c9; font-weight: bold; font-size: 12px;")
        h_prog_lbl.addWidget(self.lbl_prog_status, 1)

        self.btn_cancel = QPushButton(tr("model_mgr_btn_cancel"))
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setStyleSheet("background: #802228; color: #ffffff; padding: 3px 10px; border-radius: 3px; font-size: 11px;")
        self.btn_cancel.clicked.connect(self.cancel_download)
        h_prog_lbl.addWidget(self.btn_cancel)
        v_prog.addLayout(h_prog_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setStyleSheet("""
            QProgressBar {
                background: #18202b;
                border: 1px solid #2c394a;
                border-radius: 4px;
                height: 10px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e8061, stop:1 #4ce0b3);
                border-radius: 3px;
            }
        """)
        v_prog.addWidget(self.prog_bar)
        main_layout.addLayout(v_prog)

        # Bottom Action Bar
        h_actions = QHBoxLayout()
        h_actions.setSpacing(8)

        self.btn_dl_required = QPushButton(tr("model_mgr_btn_dl_required"))
        self.btn_dl_required.setStyleSheet("""
            QPushButton {
                background: #1e8061;
                border: 1px solid #2db88c;
                color: #ffffff;
                font-weight: bold;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #269e77;
            }
        """)
        self.btn_dl_required.clicked.connect(lambda: self.start_download("required"))
        h_actions.addWidget(self.btn_dl_required)

        h_actions.addStretch()

        self.btn_refresh = QPushButton(tr("model_mgr_btn_refresh"))
        self.btn_refresh.setStyleSheet("background: #1e2733; border: 1px solid #364354; color: #9bb0c7; padding: 7px 14px; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.refresh_all)
        h_actions.addWidget(self.btn_refresh)

        self.btn_close = QPushButton(tr("model_mgr_btn_close"))
        self.btn_close.setStyleSheet("background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 7px 18px; border-radius: 4px;")
        self.btn_close.clicked.connect(self.close)
        h_actions.addWidget(self.btn_close)

        main_layout.addLayout(h_actions)

    def refresh_all(self):
        """Re-scan filesystem and refresh model cards and summaries."""
        status = check_model_status(ROOT)
        req_installed = 0
        req_total = 0
        opt_installed = 0
        opt_total = 0

        for mid, info in status.items():
            if info["category"] == "required":
                req_total += 1
                if info["installed"]:
                    req_installed += 1
            else:
                opt_total += 1
                if info["installed"]:
                    opt_installed += 1

            if mid in self.cards:
                self.cards[mid].update_status(info)

        if req_installed == req_total:
            self.lbl_summary_req.setText(f"<span style='color:#71e0be;'>✔ {tr('model_mgr_req_header')}: {req_installed}/{req_total} {tr('model_mgr_installed')}</span>")
        else:
            self.lbl_summary_req.setText(f"<span style='color:#e06c75;'>✘ {tr('model_mgr_req_header')}: {req_total - req_installed} {tr('model_mgr_missing')} ({req_installed}/{req_total})</span>")

        if opt_total > 0:
            self.lbl_summary_opt.setVisible(True)
            self.lbl_summary_opt.setText(f"{tr('model_mgr_opt_header')}: {opt_installed}/{opt_total} {tr('model_mgr_installed')}")
        else:
            self.lbl_summary_opt.setVisible(False)

    def start_download(self, target: str):
        """Launch download process in background."""
        if self.proc and self.proc.state() != QProcess.NotRunning:
            return

        self.current_download_target = target
        self.btn_cancel.setVisible(True)
        self.btn_dl_required.setEnabled(False)
        self.prog_bar.setRange(0, 0)  # Pulse mode

        disp_target = MODEL_REGISTRY.get(target, {}).get("name", target)
        self.lbl_prog_status.setText(tr("status_model_downloading", model=disp_target))

        self.proc = QProcess(self)
        self.proc.readyReadStandardOutput.connect(self._on_proc_stdout)
        self.proc.readyReadStandardError.connect(self._on_proc_stderr)
        self.proc.finished.connect(self._on_proc_finished)

        args = [
            "-u",
            str(ROOT / "scripts" / "download_weights.py"),
            "--package_root", str(ROOT),
            "--model", target,
        ]
        self.proc.start(sys.executable, args)

    def cancel_download(self):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.proc.kill()
            self.lbl_prog_status.setText("Download cancelled.")
            self.prog_bar.setRange(0, 100)
            self.prog_bar.setValue(0)
            self.btn_cancel.setVisible(False)
            self.btn_dl_required.setEnabled(True)
            self.refresh_all()

    def _on_proc_stdout(self):
        if not self.proc:
            return
        line = bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        for sub in line.splitlines():
            sub = sub.strip()
            if not sub:
                continue
            if sub.startswith("[START]"):
                self.lbl_prog_status.setText(sub)
            elif sub.startswith("[SUCCESS]"):
                self.lbl_prog_status.setText(sub)
                self.refresh_all()
            elif sub.startswith("[COMPLETE]"):
                self.lbl_prog_status.setText(sub)
                self.refresh_all()
            else:
                self.lbl_prog_status.setText(sub[:120])

    def _on_proc_stderr(self):
        if not self.proc:
            return
        err = bytes(self.proc.readAllStandardError()).decode("utf-8", errors="replace").strip()
        if err:
            # Hugging Face and urllib progress bars land in stderr
            self.lbl_prog_status.setText(err.splitlines()[-1][:120])

    def _on_proc_finished(self, exit_code, exit_status):
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(100 if exit_code == 0 else 0)
        self.btn_cancel.setVisible(False)
        self.btn_dl_required.setEnabled(True)

        if exit_code == 0:
            self.lbl_prog_status.setText(f"<span style='color:#71e0be;'>✔ {tr('status_model_download_done')}</span>")
        else:
            self.lbl_prog_status.setText(f"<span style='color:#e06c75;'>✘ Download encountered an error (exit code {exit_code}). Check network or retry.</span>")

        self.refresh_all()

    def _open_weights_folder(self):
        """Open the weights directory in Windows Explorer or file manager."""
        w_dir = ROOT / "weights"
        w_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(w_dir))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(w_dir)])
        else:
            subprocess.run(["xdg-open", str(w_dir)])

    def _retranslate_ui(self, lang: str):
        self.setWindowTitle(tr("model_mgr_title"))
        self.lbl_dlg_title.setText(tr("model_mgr_title"))
        self.lbl_dlg_desc.setText(tr("model_mgr_desc"))
        self.btn_open_folder.setText(tr("model_mgr_btn_open_folder"))
        self.lbl_root_path.setText(f"{tr('model_mgr_path_lbl')} {ROOT.name}/")
        self.lbl_req_hdr.setText(f"━━━  {tr('model_mgr_req_header')}  ━━━")
        if hasattr(self, 'lbl_opt_hdr'):
            self.lbl_opt_hdr.setText(f"━━━  {tr('model_mgr_opt_header')}  ━━━")
        self.btn_dl_required.setText(tr("model_mgr_btn_dl_required"))
        self.btn_refresh.setText(tr("model_mgr_btn_refresh"))
        self.btn_close.setText(tr("model_mgr_btn_close"))
        self.btn_cancel.setText(tr("model_mgr_btn_cancel"))
        self.refresh_all()
