"""CorridorKey 2.0 Professional Workbench Desktop Suite.

Full implementation of the official CorridorKey 2.0 WORKBENCH layout:
- Studio NLE / DCC aesthetic: Dark theme, Top Workbench Header, Left Media Bin & Queue
- Center VFX Viewport: Checkerboard transparency, Single view, Wipe interactive split slider, Side-by-side
- Filmstrip Timeline: Real-time thumbnail filmstrip, interactive playhead scrubbing, transport controls
- Inspector Accordion: Core & Memory, Alpha Hint, Despill, Clean Plate (SD Inpainting), Output & Color
- Deliver Panel: Output formats (EXR / ProRes / MP4), hardware VRAM & disk space diagnosis, prominent Render action
- Telemetry Status Bar: Live GPU VRAM and Disk space monitoring
- 100% backward compatibility with all CorridorKey 2.0 CLI arguments, brush mask editor, and test suites
"""
from __future__ import annotations

import codecs
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys

# ---------------------------------------------------------------------------
# Python 3.12 compatibility shim (PEP 632 removed distutils)
# C-RADIOv4-SO400M imports `from distutils.version import LooseVersion`.
# ---------------------------------------------------------------------------
def _ensure_distutils_shim():
    try:
        import setuptools  # Activates _distutils_hack if available
    except ImportError:
        pass

    try:
        import distutils.version
    except ImportError:
        import types
        try:
            from packaging.version import Version as _LooseVersion
        except ImportError:
            class _LooseVersion:
                def __init__(self, vstring=None):
                    self.vstring = str(vstring or "")
                def __lt__(self, other):
                    return str(self.vstring) < str(getattr(other, "vstring", other))
                def __le__(self, other):
                    return str(self.vstring) <= str(getattr(other, "vstring", other))
                def __gt__(self, other):
                    return str(self.vstring) > str(getattr(other, "vstring", other))
                def __ge__(self, other):
                    return str(self.vstring) >= str(getattr(other, "vstring", other))
                def __eq__(self, other):
                    return str(self.vstring) == str(getattr(other, "vstring", other))
                def __repr__(self):
                    return f"LooseVersion ('{self.vstring}')"

        d_mod = sys.modules.get("distutils") or types.ModuleType("distutils")
        dv_mod = types.ModuleType("distutils.version")
        dv_mod.LooseVersion = _LooseVersion
        d_mod.version = dv_mod
        sys.modules.setdefault("distutils", d_mod)
        sys.modules.setdefault("distutils.version", dv_mod)


_ensure_distutils_shim()

import uuid

# Ensure local bin (ffmpeg.exe) is in PATH
_ROOT = Path(__file__).resolve().parent
APP_NAME = "VFXEdu CorridorKey 2.0"
APP_VERSION = "v0.1.3"
_BIN = _ROOT / "bin"
if _BIN.is_dir() and str(_BIN) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(_BIN) + os.pathsep + os.environ.get("PATH", "")

import cv2
import numpy as np
import torch

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QUrl, Signal, QTimer, QThread
from PySide6.QtGui import (
    QDesktopServices, QImage, QPixmap, QFont, QFontDatabase, QIcon, QColor, QPalette,
    QKeySequence, QShortcut
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QComboBox, QDoubleSpinBox,
    QSpinBox, QCheckBox, QPlainTextEdit, QListWidget, QListWidgetItem, QGroupBox,
    QSplitter, QMessageBox, QProgressBar, QSlider, QScrollArea, QTabWidget,
    QGridLayout, QToolButton, QFrame, QDialog, QSizePolicy, QButtonGroup
)

from mask_editor import BrushMaskEditorDialog
from i18n import tr, set_language, get_language, LANG_EN, LANG_KO
from model_manager import (
    ModelManagerDialog,
    are_required_models_installed,
    get_missing_required_models,
)
from workbench_widgets import (
    VFXViewport,
    FilmstripTimeline,
    MediaCardWidget,
    CollapsibleSection,
    ToolRailWidget,
)

ROOT = Path(__file__).resolve().parent
VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.exr', '.tiff', '.tif', '.webp', '.dpx'}


class _NvmlMemory(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


def get_gpu_vram_info() -> tuple[float, float, float, float, str]:
    """Query live GPU VRAM via NVML (matching Task Manager), falling back to PyTorch."""
    # 1. Real-time NVML hardware query (100% matches Windows Task Manager & nvidia-smi)
    try:
        nvml = ctypes.CDLL("nvml.dll")
        if nvml.nvmlInit_v2() == 0:
            handle = ctypes.c_void_p()
            if nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) == 0:
                mem = _NvmlMemory()
                if nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem)) == 0:
                    used_gb = mem.used / (1024**3)
                    free_gb = mem.free / (1024**3)
                    tot_gb = mem.total / (1024**3)
                    pct = (mem.used / mem.total) * 100 if mem.total > 0 else 0.0

                    name_buf = ctypes.create_string_buffer(64)
                    if nvml.nvmlDeviceGetName(handle, name_buf, 64) == 0:
                        gpu_name = name_buf.value.decode("utf-8", errors="ignore")
                    else:
                        gpu_name = "NVIDIA GPU"
                    nvml.nvmlShutdown()
                    return (used_gb, free_gb, tot_gb, pct, gpu_name)
            nvml.nvmlShutdown()
    except Exception:
        pass

    # 2. Fallback to PyTorch CUDA mem_get_info
    try:
        if torch.cuda.is_available():
            free_b, tot_b = torch.cuda.mem_get_info()
            used_b = max(0, tot_b - free_b)
            used_gb = used_b / (1024**3)
            free_gb = free_b / (1024**3)
            tot_gb = tot_b / (1024**3)
            pct = (used_b / tot_b) * 100 if tot_b > 0 else 0.0
            name = torch.cuda.get_device_name(0)
            return (used_gb, free_gb, tot_gb, pct, name)
    except Exception:
        pass
    return (0.0, 0.0, 0.0, 0.0, "CPU (No CUDA)")


def get_system_telemetry() -> str:
    """Query live GPU VRAM and Disk space with accurate, non-misleading labels."""
    used_gb, free_gb, tot_gb, pct, gpu_name = get_gpu_vram_info()
    if tot_gb > 0:
        gpu_str = f"GPU: {gpu_name} · VRAM: {used_gb:.1f} / {tot_gb:.1f} GB ({free_gb:.1f} GB free)"
    else:
        gpu_str = "GPU: Not Detected (CPU Mode)"

    disk_str = "Disk: N/A"
    try:
        disk = shutil.disk_usage(ROOT)
        disk_str = f"Disk: {disk.free/(1024**3):.1f} GB free"
    except Exception:
        pass

    return f"{gpu_str}    {disk_str}"


def find_first_frame_hint(input_path: Path) -> Path | None:
    """Locate companion first-frame hint image next to input (<clip>FrameHint.png)."""
    parent_dir = input_path.parent
    base_name = input_path.stem.lower()
    allowed_exts = {'.png', '.jpg', '.jpeg', '.exr'}

    if not parent_dir.exists():
        return None

    frame_hints = []
    legacy_hints = []
    for item in sorted(parent_dir.iterdir()):
        if item.is_file() and item.suffix.lower() in allowed_exts:
            name_lower = item.stem.lower()
            if not name_lower.startswith(base_name):
                continue
            remainder = name_lower[len(base_name):].lstrip("_- ")
            if remainder.startswith("framehint"):
                frame_hints.append(item)
            elif remainder.startswith("alphahint"):
                legacy_hints.append(item)

    hint_files = frame_hints or legacy_hints
    return hint_files[0] if hint_files else None


def find_alpha_hint_video(input_path: Path) -> Path | None:
    """Locate companion full hint video next to input (<clip>_alphahint.mp4)."""
    parent_dir = input_path.parent
    base_name = input_path.stem.lower()
    allowed_exts = VIDEO_EXTS

    if not parent_dir.exists():
        return None

    for item in parent_dir.iterdir():
        if item.is_file() and item.suffix.lower() in allowed_exts:
            name_lower = item.name.lower()
            prefix_lower = f"{base_name}_alphahint"
            if name_lower.startswith(prefix_lower):
                return item
    return None


def make_arguments(source: Path, destination: Path, options: dict) -> list[str]:
    """Construct complete CLI argument list for infer.py covering all CorridorKey 2.0 features."""
    if not source.exists():
        raise ValueError(f'Input path does not exist: {source}')
    if source.is_dir() and not any(p.suffix.lower() in IMAGE_EXTS for p in source.iterdir() if p.is_file()):
        raise ValueError(f'Folder contains no image frames: {source}')
    outputs = list(options.get('outputs') or [])
    if not outputs:
        raise ValueError('Select at least one output.')

    args = [
        '-u', str(ROOT / 'infer.py'),
        '--input', str(source),
        '--output_dir', str(destination),
        '--outputs', *outputs,
        '--output_format', options.get('format', 'video'),
        '--despill_strength', str(options.get('despill', 0.5)),
        '--frame_dir_fps', str(options.get('fps', 24.0)),
        '--num_frames', str(options.get('frames', -1)),
        '--start_mode', options.get('start', 'begin'),
        '--seed', str(options.get('seed', 0)),
        '--model_scale', str(options.get('model_scale', 1.0)),
        '--temp_dir', str(options.get('temp_dir') or (ROOT / 'tmp' / destination.name)),
    ]

    # Hints & Conditioning
    hint_mode = options.get('hint_mode')
    hint_path = options.get('hint')
    if hint_mode and hint_path:
        args += [hint_mode, str(hint_path)]
        if options.get('quality') is not None:
            args += ['--hint_quality', str(options['quality'])]
        if options.get('carry_hint_quality') is not None:
            args += ['--carry_hint_quality', str(options['carry_hint_quality'])]
        if options.get('no_carry_hint'):
            args += ['--no_carry_hint']

    # Hann Windows & VRAM
    hann_mode = options.get('hann_mode', 'auto')
    if hann_mode == 'custom':
        args += [
            '--hann_chunk', str(options.get('hann_chunk', 48)),
            '--hann_stride', str(options.get('hann_stride', 24)),
        ]
    elif hann_mode != 'auto':
        chunk, stride = map(int, hann_mode.split('_'))
        args += ['--hann_chunk', str(chunk), '--hann_stride', str(stride)]
    elif options.get('low_vram'):
        # Fallback to compact window when user activates low_vram on auto
        args += ['--hann_chunk', '8', '--hann_stride', '4']

    if options.get('low_vram'):
        args += ['--low_vram']

    if options.get('stage2_batch') and options['stage2_batch'] > 1:
        args += ['--stage2_batch', str(options['stage2_batch'])]

    if options.get('weights'):
        args += ['--weights', str(options['weights'])]

    # Color & VFX Linear Pipeline
    if options.get('linear'):
        args += ['--frame_dir_linear']
    if options.get('cutout_linear'):
        args += ['--cutout_linear']
    if options.get('format') == 'exr' and options.get('exr_dtype'):
        args += ['--exr_dtype', options['exr_dtype']]

    if options.get('linear_brightness') is not None and options['linear_brightness'] != 1.0:
        args += ['--linear_brightness', str(options['linear_brightness'])]
    if options.get('linear_contrast') is not None and options['linear_contrast'] != 1.0:
        args += ['--linear_contrast', str(options['linear_contrast'])]
    if options.get('linear_contrast_pivot') is not None and options['linear_contrast_pivot'] != 0.18:
        args += ['--linear_contrast_pivot', str(options['linear_contrast_pivot'])]

    # Video Encoding Options
    if options.get('format') == 'video':
        if options.get('ffmpeg_codec'):
            args += ['--ffmpeg_codec', options['ffmpeg_codec']]
        if options.get('crf') is not None:
            args += ['--crf', str(options['crf'])]
        if options.get('pix_fmt'):
            args += ['--pix_fmt', options['pix_fmt']]
        if options.get('preset'):
            args += ['--preset', options['preset']]
        if options.get('ffmpeg_threads'):
            args += ['--ffmpeg_threads', str(options['ffmpeg_threads'])]
        if options.get('bitrate'):
            args += ['--bitrate', str(options['bitrate'])]

    return args


class AboutLicenseDialog(QDialog):
    """License and attribution dialog adhering to CorridorKey CC BY-NC-SA 4.0 terms."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("about_dialog_title"))
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        tabs = QTabWidget()

        # Tab 1: About & Summary
        tab_about = QWidget()
        v_about = QVBoxLayout(tab_about)
        v_about.setContentsMargins(12, 12, 12, 12)
        v_about.setSpacing(8)

        lbl_title = QLabel(f'{APP_NAME} Professional Workbench ({APP_VERSION})')
        lbl_title.setStyleSheet('font-size:16px;font-weight:bold;color:#e5a93c;')
        v_about.addWidget(lbl_title)

        if get_language() == LANG_KO:
            about_text = (
                "<p style='line-height:140%;'><b>CorridorKey 2.0 WORKBENCH</b>는 Corridor Digital과 Zachary Harris가 공동 설계 및 훈련한 차세대 비디오 그린스크린 제거/AI 매팅 모델을 탑재한 전문 VFX 워크벤치 스위트입니다.</p>"
                "<p style='line-height:140%;'>본 워크벤치는 대형 체커보드 VFX 뷰포트, 실시간 와이프(Wipe) 분할 비교, 비주얼 필름스트립 타임라인, Stable Diffusion 인페인팅 클린 플레이트 엔진을 지원합니다.</p>"
                "<hr style='border:1px solid #30363d;'>"
                "<p style='line-height:150%;'><b>저작권 및 크레딧:</b><br>"
                "• Model Architecture & Training: Zachary Harris & Niko Pueringer (Corridor Digital)<br>"
                "• Official Repository: <a style='color:#58a6ff;' href='https://github.com/nikopueringer/CorridorKey2.0'>github.com/nikopueringer/CorridorKey2.0</a><br>"
                "• Official Plugin & Standalone App: <a style='color:#58a6ff;' href='https://corridorkey.com'>corridorkey.com</a><br>"
                "• Foundation Models: NVIDIA C-RADIOv4, Microsoft MoGe-2, Google DeepMind RVM, RunwayML SD</p>"
                "<hr style='border:1px solid #30363d;'>"
                "<p style='line-height:150%;'><b>배포 및 라이선스 핵심 규정 (CC BY-NC-SA 4.0 + Additional Terms):</b><br>"
                "• <span style='color:#71e0be;'><b>✔ 무료 배포 필수 (Derivatives Must Be Free)</b></span>: 본 도구 및 파생 수정본은 일반 대중에게 반드시 <b>무료(Free of charge)</b>로만 제공되어야 합니다.<br>"
                "• <span style='color:#71e0be;'><b>✔ 결과물의 상업적 사용 100% 보장</b></span>: 본 도구로 추출/생성한 마스크, 투명 영상, 합성 결과물은 100% 사용자의 소유이며 상업적 프로젝트에 자유롭게 사용하실 수 있습니다.<br>"
                "• <span style='color:#f85149;'><b>✖ 유료 재판매 및 유료 서비스 금지</b></span>: 본 도구를 유료로 재판매하거나, 유료 클라우드/API 추론 서비스(SaaS)로 제공하는 행위는 엄격히 금지됩니다.<br>"
                "• <b>대기업 규정</b>: 연간 총매출 2,000만 달러(약 260억 원) 이상의 대기업은 공식 상용 플러그인 시트 라이선스 구매가 필요합니다.</p>"
            )
        else:
            about_text = (
                "<p style='line-height:140%;'><b>CorridorKey 2.0 WORKBENCH</b> is a professional VFX suite powered by the state-of-the-art AI video matting and green screen replacement model, designed and trained by Zachary Harris and Niko Pueringer (Corridor Digital).</p>"
                "<p style='line-height:140%;'>Features an interactive VFX viewport with checkerboard transparency, real-time wipe comparison slider, filmstrip scrubber, and Stable Diffusion inpainting clean plate synthesis.</p>"
                "<hr style='border:1px solid #30363d;'>"
                "<p style='line-height:150%;'><b>Credits & Attribution:</b><br>"
                "• Model Architecture & Training: Zachary Harris & Niko Pueringer (Corridor Digital)<br>"
                "• Official Repository: <a style='color:#58a6ff;' href='https://github.com/nikopueringer/CorridorKey2.0'>github.com/nikopueringer/CorridorKey2.0</a><br>"
                "• Official Plugin: <a style='color:#58a6ff;' href='https://corridorkey.com'>corridorkey.com</a><br>"
                "• Foundation Models: NVIDIA C-RADIOv4, Microsoft MoGe-2, Google DeepMind RVM, RunwayML SD</p>"
                "<hr style='border:1px solid #30363d;'>"
                "<p style='line-height:150%;'><b>Key License Terms (CC BY-NC-SA 4.0 + Additional Terms):</b><br>"
                "• <span style='color:#71e0be;'><b>✔ Derivatives Must Be Freely Accessible</b></span>: Any modified versions or forks of this software must be made available to the public free of charge.<br>"
                "• <span style='color:#71e0be;'><b>✔ Commercial Use of Outputs Allowed</b></span>: Images and videos produced with this tool belong entirely to the user and may be used commercially.<br>"
                "• <span style='color:#f85149;'><b>✖ No Repackaging or Paid Services</b></span>: Selling this software or providing paid inference API services is strictly prohibited.<br>"
                "• <b>Large Organizations</b>: Organizations with gross revenue exceeding US $20,000,000 must purchase official plugin seats.</p>"
            )
        desc = QLabel(about_text)
        desc.setWordWrap(True)
        desc.setOpenExternalLinks(True)
        v_about.addWidget(desc)
        v_about.addStretch()
        tabs.addTab(tab_about, tr("about_tab_summary"))

        # Tab 2: Full LICENSE
        tab_lic = QWidget()
        v_lic = QVBoxLayout(tab_lic)
        text_lic = QPlainTextEdit()
        text_lic.setReadOnly(True)
        lic_file = ROOT / 'LICENSE'
        if lic_file.is_file():
            text_lic.setPlainText(lic_file.read_text(encoding='utf-8', errors='replace'))
        v_lic.addWidget(text_lic)
        tabs.addTab(tab_lic, tr("about_tab_license"))

        # Tab 3: Third Party Notices
        tab_third = QWidget()
        v_third = QVBoxLayout(tab_third)
        text_third = QPlainTextEdit()
        text_third.setReadOnly(True)
        third_file = ROOT / 'THIRD_PARTY_NOTICES.md'
        if third_file.is_file():
            text_third.setPlainText(third_file.read_text(encoding='utf-8', errors='replace'))
        v_third.addWidget(text_third)
        tabs.addTab(tab_third, tr("about_tab_third"))

        layout.addWidget(tabs)

        bottom_bar = QHBoxLayout()
        btn_updater = QPushButton(tr("updater_btn_check"))
        btn_updater.setStyleSheet('background:#1d3144;border:1px solid #2b4f73;color:#a3d5ff;font-weight:bold;padding:6px 14px;border-radius:4px;font-size:11px;')
        btn_updater.clicked.connect(self._open_updater)
        bottom_bar.addWidget(btn_updater)

        bottom_bar.addStretch(1)

        btn_close = QPushButton(tr("about_btn_close"))
        btn_close.setStyleSheet('background:#21262d;padding:6px 16px;border-radius:4px;')
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        layout.addLayout(bottom_bar)

    def _open_updater(self):
        dlg = UpdateDialog(self)
        dlg.exec()

class UpdateCheckWorker(QThread):
    """Asynchronous background worker to query GitHub for latest releases."""
    finished_signal = Signal(dict)

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self):
        try:
            from scripts.updater import check_for_updates
            info = check_for_updates(self.current_version)
        except Exception as e:
            info = {
                "update_available": False,
                "latest_version": self.current_version,
                "current_version": self.current_version,
                "release_name": "",
                "release_notes": "",
                "release_url": "https://github.com/VFXEdu/VFXEdu-CorridorKey2.0",
                "zipball_url": "",
                "error": str(e),
            }
        self.finished_signal.emit(info)


class UpdateApplyWorker(QThread):
    """Asynchronous worker to download and apply incremental code updates."""
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str)

    def __init__(self, zip_url: str | None = None, parent=None):
        super().__init__(parent)
        self.zip_url = zip_url

    def run(self):
        try:
            from scripts.updater import apply_code_update
            def on_progress(pct: int, msg: str):
                self.progress_signal.emit(pct, msg)
            ok, msg = apply_code_update(zip_url=self.zip_url, progress_callback=on_progress)
            self.finished_signal.emit(ok, msg)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class UpdateDialog(QDialog):
    """Interactive Auto-Update and Release Notes Dialog."""

    def __init__(self, parent=None, initial_info: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("updater_title"))
        self.resize(650, 520)
        self.setMinimumSize(540, 420)
        self.setStyleSheet("background-color: #0f1218; color: #e2e8f0;")

        self.info = initial_info or {}
        self.check_worker: UpdateCheckWorker | None = None
        self.apply_worker: UpdateApplyWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header Title
        title_box = QHBoxLayout()
        icon_lbl = QLabel("🚀")
        icon_lbl.setStyleSheet("font-size: 24px;")
        title_box.addWidget(icon_lbl)

        v_titles = QVBoxLayout()
        self.lbl_header = QLabel(f"<b style='font-size:16px; color:#38bdf8;'>{APP_NAME}</b>")
        self.lbl_sub = QLabel(tr("updater_title"))
        self.lbl_sub.setStyleSheet("color: #94a3b8; font-size: 11px;")
        v_titles.addWidget(self.lbl_header)
        v_titles.addWidget(self.lbl_sub)
        title_box.addLayout(v_titles)
        title_box.addStretch(1)
        layout.addLayout(title_box)

        # Version Status Card
        self.status_card = QFrame()
        self.status_card.setStyleSheet("""
            QFrame {
                background: #171b24;
                border: 1px solid #28303f;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        card_layout = QVBoxLayout(self.status_card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(6)

        self.lbl_status_badge = QLabel()
        self.lbl_status_badge.setStyleSheet("font-size: 13px; font-weight: bold;")
        card_layout.addWidget(self.lbl_status_badge)

        self.lbl_version_detail = QLabel()
        self.lbl_version_detail.setStyleSheet("color: #94a3b8; font-size: 11px;")
        card_layout.addWidget(self.lbl_version_detail)

        layout.addWidget(self.status_card)

        # Release Notes / Changelog section
        self.lbl_notes_title = QLabel(tr("updater_changelog"))
        self.lbl_notes_title.setStyleSheet("font-weight: bold; font-size: 11px; color: #cbd5e1;")
        layout.addWidget(self.lbl_notes_title)

        self.text_notes = QPlainTextEdit()
        self.text_notes.setReadOnly(True)
        self.text_notes.setStyleSheet("""
            QPlainTextEdit {
                background: #141720;
                border: 1px solid #232938;
                border-radius: 4px;
                color: #e2e8f0;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 11px;
                line-height: 140%;
                padding: 8px;
            }
        """)
        layout.addWidget(self.text_notes, 1)

        # Safe update notice
        self.lbl_safe = QLabel(tr("updater_safe_notice"))
        self.lbl_safe.setStyleSheet("color: #71e0be; font-size: 10px; font-weight: 600;")
        self.lbl_safe.setWordWrap(True)
        layout.addWidget(self.lbl_safe)

        # Progress Bar & Status Text (Hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #1a1e29;
                border: 1px solid #2f384a;
                border-radius: 4px;
                height: 18px;
                text-align: center;
                color: #ffffff;
                font-size: 10px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
                border-radius: 3px;
            }
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_prog_status = QLabel("")
        self.lbl_prog_status.setStyleSheet("color: #38bdf8; font-size: 11px;")
        self.lbl_prog_status.setVisible(False)
        layout.addWidget(self.lbl_prog_status)

        # Button row
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_github = QPushButton(tr("updater_btn_github"))
        self.btn_github.setStyleSheet("""
            QPushButton {
                background: #1e2430;
                border: 1px solid #333d52;
                border-radius: 4px;
                color: #cbd5e1;
                font-size: 11px;
                font-weight: 600;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #2a3344;
                color: #ffffff;
            }
        """)
        self.btn_github.clicked.connect(self._open_github)
        btn_box.addWidget(self.btn_github)

        btn_box.addStretch(1)

        self.btn_check_again = QPushButton(tr("updater_btn_check"))
        self.btn_check_again.setStyleSheet("""
            QPushButton {
                background: #1e2430;
                border: 1px solid #333d52;
                border-radius: 4px;
                color: #cbd5e1;
                font-size: 11px;
                font-weight: 600;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #2a3344;
                color: #ffffff;
            }
        """)
        self.btn_check_again.clicked.connect(self._start_check)
        btn_box.addWidget(self.btn_check_again)

        self.btn_apply = QPushButton(tr("updater_btn_apply"))
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background: #0284c7;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background: #0369a1;
            }
            QPushButton:disabled {
                background: #1e293b;
                border-color: #334155;
                color: #64748b;
            }
        """)
        self.btn_apply.clicked.connect(self._start_apply)
        btn_box.addWidget(self.btn_apply)

        self.btn_close = QPushButton(tr("updater_btn_close"))
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: #1e2430;
                border: 1px solid #333d52;
                border-radius: 4px;
                color: #cbd5e1;
                font-size: 11px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #2a3344;
                color: #ffffff;
            }
        """)
        self.btn_close.clicked.connect(self.close)
        btn_box.addWidget(self.btn_close)

        layout.addLayout(btn_box)

        if self.info:
            self._display_info(self.info)
        else:
            self._start_check()

    def _start_check(self):
        self.lbl_status_badge.setText(f"⏳ {tr('updater_checking')}")
        self.lbl_status_badge.setStyleSheet("font-size:13px; font-weight:bold; color:#38bdf8;")
        self.lbl_version_detail.setText(tr("updater_current_version", version=APP_VERSION))
        self.btn_apply.setEnabled(False)
        self.btn_check_again.setEnabled(False)
        self.text_notes.setPlainText("")

        self.check_worker = UpdateCheckWorker(APP_VERSION, self)
        self.check_worker.finished_signal.connect(self._on_check_finished)
        self.check_worker.start()

    def _on_check_finished(self, info: dict):
        self.info = info
        self.btn_check_again.setEnabled(True)
        self._display_info(info)

    def _display_info(self, info: dict):
        if info.get("error"):
            self.lbl_status_badge.setText(f"⚠️ {info['error']}")
            self.lbl_status_badge.setStyleSheet("font-size:12px; font-weight:bold; color:#f87171;")
            self.lbl_version_detail.setText(tr("updater_current_version", version=APP_VERSION))
            self.btn_apply.setEnabled(False)
            self.text_notes.setPlainText(f"Check status:\n{info['error']}")
        elif info.get("update_available"):
            latest = info.get("latest_version", "")
            self.lbl_status_badge.setText(f"🎉 {tr('updater_new_available_title')} ({latest})")
            self.lbl_status_badge.setStyleSheet("font-size:13px; font-weight:bold; color:#4ade80;")
            self.lbl_version_detail.setText(f"{tr('updater_current_version', version=APP_VERSION)}  ➜  {tr('updater_latest_version', version=latest)}")
            self.btn_apply.setEnabled(True)
            body = info.get("release_notes") or info.get("release_name") or "New update available."
            self.text_notes.setPlainText(body)
        else:
            self.lbl_status_badge.setText(f"✅ {tr('updater_up_to_date_title')}")
            self.lbl_status_badge.setStyleSheet("font-size:13px; font-weight:bold; color:#38bdf8;")
            self.lbl_version_detail.setText(tr("updater_up_to_date_msg", version=APP_VERSION))
            self.btn_apply.setEnabled(False)
            self.text_notes.setPlainText(info.get("release_notes") or f"Current version {APP_VERSION} is the latest release.")

    def _start_apply(self):
        zip_url = self.info.get("zipball_url")
        self.btn_apply.setEnabled(False)
        self.btn_check_again.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.lbl_prog_status.setVisible(True)
        self.lbl_prog_status.setText(tr("updater_updating"))

        self.apply_worker = UpdateApplyWorker(zip_url, self)
        self.apply_worker.progress_signal.connect(self._on_apply_progress)
        self.apply_worker.finished_signal.connect(self._on_apply_finished)
        self.apply_worker.start()

    def _on_apply_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.lbl_prog_status.setText(msg)

    def _on_apply_finished(self, ok: bool, msg: str):
        self.btn_close.setEnabled(True)
        self.btn_check_again.setEnabled(True)
        if ok:
            self.progress_bar.setValue(100)
            self.lbl_prog_status.setText(msg)
            ret = QMessageBox.question(
                self,
                tr("updater_success_title"),
                tr("updater_success_msg", msg=msg),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ret == QMessageBox.Yes:
                self.accept()
                import sys
                QProcess.startDetached(sys.executable, sys.argv)
                QApplication.quit()
        else:
            QMessageBox.critical(self, tr("updater_fail_title"), tr("updater_fail_msg", err=msg))
            self.btn_apply.setEnabled(True)

    def _open_github(self):
        url = self.info.get("release_url") or "https://github.com/VFXEdu/VFXEdu-CorridorKey2.0"
        QDesktopServices.openUrl(QUrl(url))


class Preview(QGroupBox):
    """Media viewer with interactive frame seeking, EXR proxy decoding, and brush launcher."""
    frame_changed = Signal(int)

    def __init__(self, title_key: str):
        super().__init__(tr(title_key))
        self.title_key = title_key
        self.path: Path | None = None
        self.frames: list[Path] = []
        self.pixmap: QPixmap | None = None
        self.current_rgb_frame: np.ndarray | None = None
        self.current_frame_index = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(6)

        self.image = QLabel(tr("empty_preview"))
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(280, 200)
        self.image.setStyleSheet('background:#11151d;border-radius:8px;color:#8793a6;font-size:12px;')
        layout.addWidget(self.image, 1)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self.show_frame)
        layout.addWidget(self.slider)

        h_info = QHBoxLayout()
        self.caption = QLabel('')
        self.caption.setStyleSheet('color:#9aa9bb;font-size:11px;')
        h_info.addWidget(self.caption, 1)

        self.btn_open_brush = QPushButton(tr("btn_brush_preview"))
        self.btn_open_brush.setStyleSheet('background:#204b40;color:#85e4c6;font-weight:bold;padding:4px 8px;')
        self.btn_open_brush.setToolTip(tr("btn_brush_preview_tip"))
        self.btn_open_brush.setEnabled(False)
        h_info.addWidget(self.btn_open_brush)

        layout.addLayout(h_info)

    def retranslate(self):
        self.setTitle(tr(self.title_key))
        if not self.path:
            self.image.setText(tr("empty_preview"))
        self.btn_open_brush.setText(tr("btn_brush_preview"))
        self.btn_open_brush.setToolTip(tr("btn_brush_preview_tip"))

    def load(self, path: Path | str):
        self.path = Path(path)
        self.frames = []
        count = 0
        if self.path.is_dir():
            self.frames = sorted(p for p in self.path.iterdir() if p.suffix.lower() in IMAGE_EXTS)
            count = len(self.frames)
        elif self.path.is_file():
            cap = cv2.VideoCapture(str(self.path))
            count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()

        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, count - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.slider.setEnabled(count > 1)
        self.btn_open_brush.setEnabled(count > 0)
        self.show_frame(0)

    def show_frame(self, index: int):
        if not self.path:
            return
        self.current_frame_index = index
        try:
            frame = None
            if self.path.is_dir():
                if 0 <= index < len(self.frames):
                    frame = cv2.imdecode(np.fromfile(self.frames[index], dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    if frame is not None:
                        if np.issubdtype(frame.dtype, np.floating):
                            frame = (np.power(np.clip(np.nan_to_num(frame), 0, 1), 1 / 2.2) * 255).astype(np.uint8)
                        elif frame.dtype == np.uint16:
                            frame = (frame / 257).astype(np.uint8)
                        if frame.ndim == 2:
                            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                        elif frame.shape[2] == 4:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            else:
                cap = cv2.VideoCapture(str(self.path))
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = cap.read()
                cap.release()
                if not ok:
                    frame = None

            if frame is None:
                raise ValueError('Failed to read frame.')

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.current_rgb_frame = rgb
            h, w, _ = rgb.shape
            self.pixmap = QPixmap.fromImage(QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy())
            self.render()
            self.caption.setText(tr('frame_caption', name=self.path.name, w=w, h=h, frame=index + 1))
            self.frame_changed.emit(index)
        except Exception:
            self.pixmap = None
            self.current_rgb_frame = None
            self.image.clear()
            self.image.setText(tr('preview_unavailable'))
            self.caption.setText('')

    def render(self):
        if self.pixmap:
            self.image.setPixmap(self.pixmap.scaled(self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render()


class Window(QMainWindow):
    """CorridorKey 2.0 WORKBENCH Desktop Interface."""

    def __init__(self):
        super().__init__()
        os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} · WORKBENCH")
        self.resize(1560, 980)
        self.setMinimumSize(1200, 780)
        self.setAcceptDrops(True)

        self.jobs = []
        self.cancelled = False
        self.mode = ''
        self.destination = None
        self.total = 0
        self.browse_buttons = []
        self.current_opts = {}
        self.current_source = None
        self.current_clip_path: Path | None = None
        self.matched_results: dict[str, Path] = {}
        self._clip_cache: dict[str, dict] = {}
        self.current_project_path: Path | None = None
        self._clip_options: dict[str, dict] = {}

        # High-performance persistent video streams & RAM frame cache (60+ FPS playback)
        self._cap_orig: cv2.VideoCapture | None = None
        self._cap_orig_path: Path | None = None
        self._cap_orig_pos: int = -1

        self._cap_res: cv2.VideoCapture | None = None
        self._cap_res_path: Path | None = None
        self._cap_res_pos: int = -1

        self._cap_alpha: cv2.VideoCapture | None = None
        self._cap_alpha_path: Path | None = None
        self._cap_alpha_pos: int = -1

        self._viewport_frame_cache: dict[int, tuple[QPixmap, QPixmap, QPixmap | None, int, int]] = {}

        # Process management
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.read_log)
        self.proc.finished.connect(self.finished)
        self.proc.errorOccurred.connect(self.process_error)

        self.killer = QProcess(self)
        self.killer.finished.connect(self.kill_finished)

        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

        # Hidden proxies for test suite compatibility
        self.original = Preview('preview_source')
        self.original.btn_open_brush.clicked.connect(self.open_brush_editor)
        self.result = Preview('preview_result')
        self.result_choice = QComboBox()
        self.result_choice.currentIndexChanged.connect(self.preview_result)

        self._build_workbench_ui()

        # Keyboard shortcuts for Project Management
        QShortcut(QKeySequence("Ctrl+N"), self, self.new_project)
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_project_dialog)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_project)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, self.save_project_as)

        # Telemetry Timer (updates VRAM and live GPU metrics every 1.5 seconds)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._update_telemetry)
        self.telemetry_timer.start(1500)
        self._update_telemetry()

        # Check required models on startup
        QTimer.singleShot(700, self._check_models_on_startup)

        # Background update check (non-blocking)
        self._last_update_info = None
        self._update_worker = None
        QTimer.singleShot(1500, self._check_updates_background)

    def _check_models_on_startup(self):
        """Prompt to download required models on initial launch if missing."""
        if not are_required_models_installed(ROOT):
            missing = get_missing_required_models(ROOT)
            ret = QMessageBox.question(
                self,
                tr('prompt_missing_req_title'),
                tr('prompt_missing_req_msg', models='\n'.join(f'• {m}' for m in missing)),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if ret == QMessageBox.Yes:
                self.show_model_manager(initial_target='required')

    def _build_workbench_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Workbench Header
        main_layout.addWidget(self._build_header_bar())

        # 2. Main Workbench Body (ToolRail + Splitter [Media Bin, Viewport, Inspector])
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Far-Left Tool Rail
        self.tool_rail = ToolRailWidget()
        self.tool_rail.tool_selected.connect(self._on_tool_rail_selected)
        body_layout.addWidget(self.tool_rail)

        # 3-Way Splitter
        self.split = QSplitter(Qt.Horizontal)
        self.split.setStyleSheet("""
            QSplitter::handle {
                background: #1c202b;
                width: 2px;
            }
        """)

        # Panel 1: Left Media Bin & Queue
        self.split.addWidget(self._build_media_panel())

        # Panel 2: Center VFX Viewport & Filmstrip Scrubber
        self.split.addWidget(self._build_center_viewport_panel())

        # Panel 3: Right Inspector & Deliver Panel
        self.split.addWidget(self._build_inspector_panel())

        # Proportions: 260px (Media), 820px (Center), 380px (Inspector)
        self.split.setSizes([260, 840, 380])
        body_layout.addWidget(self.split, 1)

        main_layout.addWidget(body_widget, 1)

        # 3. Live Process Monitor & Console Drawer
        self.console_drawer = self._build_console_drawer()
        main_layout.addWidget(self.console_drawer)

        # 4. Bottom Status Bar & Telemetry
        main_layout.addWidget(self._build_status_bar())

        self.retranslate_ui()

    # =========================================================================
    # Header Bar
    # =========================================================================
    def _build_header_bar(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(44)
        header.setStyleSheet("""
            QWidget {
                background-color: #12141a;
                border-bottom: 1px solid #1f232e;
            }
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 0, 14, 0)
        h_layout.setSpacing(10)

        # Logo & Clean App Title: "⚡ CORRIDORKEY 2.0"
        self.lbl_logo = QLabel("⚡")
        self.lbl_logo.setStyleSheet("font-size:16px; color:#e5a93c;")
        h_layout.addWidget(self.lbl_logo)

        self.lbl_title = QLabel()
        self.lbl_title.setText("<span style='color:#38bdf8; font-weight:900;'>VFXEdu</span>&nbsp;&nbsp;<span style='color:#e5a93c; font-weight:800;'>CORRIDORKEY 2.0</span>")
        self.lbl_title.setStyleSheet("font-size:14px; letter-spacing:1.2px;")
        h_layout.addWidget(self.lbl_title)

        # Version Pill Badge: "v0.1.1"
        self.lbl_version = QLabel(APP_VERSION)
        self.lbl_version.setStyleSheet("""
            QLabel {
                color: #8b9bb0;
                font-size: 10px;
                font-weight: 700;
                background: #181c26;
                border: 1px solid #283142;
                border-radius: 3px;
                padding: 2px 6px;
                margin-left: 2px;
            }
        """)
        self.lbl_version.setToolTip(f"{APP_NAME} Workbench Desktop {APP_VERSION}")
        h_layout.addWidget(self.lbl_version)

        # In-App Update Badge Button (hidden until an update is detected)
        self.btn_update_badge = QPushButton()
        self.btn_update_badge.setStyleSheet("""
            QPushButton {
                background: #0284c7;
                color: #ffffff;
                font-size: 10px;
                font-weight: 800;
                border: 1px solid #38bdf8;
                border-radius: 3px;
                padding: 2px 8px;
                margin-left: 4px;
            }
            QPushButton:hover {
                background: #0369a1;
                border-color: #7dd3fc;
            }
        """)
        self.btn_update_badge.setVisible(False)
        self.btn_update_badge.clicked.connect(self._on_update_badge_clicked)
        h_layout.addWidget(self.btn_update_badge)

        # Top-Left Live GPU Status Badge
        self.badge_gpu = QLabel("⚡ GPU: -- / -- GB")
        self.badge_gpu.setStyleSheet("""
            QLabel {
                background: #171b24;
                border: 1px solid #28303f;
                border-radius: 4px;
                color: #a4b7cc;
                font-size: 11px;
                font-weight: bold;
                padding: 3px 9px;
                margin-left: 6px;
            }
        """)
        h_layout.addWidget(self.badge_gpu)

        # Top Project Actions: [📄 New] [📂 Open] [💾 Save]
        proj_btn_style = """
            QPushButton {
                background: #171b24;
                border: 1px solid #28303f;
                border-radius: 4px;
                color: #a4b7cc;
                font-size: 11px;
                font-weight: bold;
                padding: 3px 8px;
            }
            QPushButton:hover {
                background: #232a38;
                border-color: #38bdf8;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #12151c;
            }
        """
        self.btn_proj_new = QPushButton(tr("btn_proj_new"))
        self.btn_proj_new.setStyleSheet(proj_btn_style)
        self.btn_proj_new.setToolTip(tr("btn_proj_new_tip"))
        self.btn_proj_new.clicked.connect(self.new_project)
        h_layout.addWidget(self.btn_proj_new)

        self.btn_proj_open = QPushButton(tr("btn_proj_open"))
        self.btn_proj_open.setStyleSheet(proj_btn_style)
        self.btn_proj_open.setToolTip(tr("btn_proj_open_tip"))
        self.btn_proj_open.clicked.connect(self.open_project_dialog)
        h_layout.addWidget(self.btn_proj_open)

        self.btn_proj_save = QPushButton(tr("btn_proj_save"))
        self.btn_proj_save.setStyleSheet(proj_btn_style)
        self.btn_proj_save.setToolTip(tr("btn_proj_save_tip"))
        self.btn_proj_save.clicked.connect(self.save_project)
        h_layout.addWidget(self.btn_proj_save)

        h_layout.addStretch(1)

        # Center View Mode Buttons: [Single] [Wipe] [Side by side]
        pill_style = """
            QPushButton {
                background: #161922;
                border: 1px solid #282d3b;
                color: #8392a5;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background: #202431;
                color: #e5a93c;
            }
            QPushButton:checked {
                background: #232936;
                border: 1px solid #e5a93c;
                color: #f5b642;
            }
        """
        self.btn_view_single = QPushButton(tr("wb_mode_single"))
        self.btn_view_single.setCheckable(True)
        self.btn_view_single.setStyleSheet(pill_style)

        self.btn_view_wipe = QPushButton(tr("wb_mode_wipe"))
        self.btn_view_wipe.setCheckable(True)
        self.btn_view_wipe.setChecked(True)
        self.btn_view_wipe.setStyleSheet(pill_style)

        self.btn_view_side = QPushButton(tr("wb_mode_side"))
        self.btn_view_side.setCheckable(True)
        self.btn_view_side.setStyleSheet(pill_style)

        self.view_grp = QButtonGroup(self)
        self.view_grp.addButton(self.btn_view_single)
        self.view_grp.addButton(self.btn_view_wipe)
        self.view_grp.addButton(self.btn_view_side)
        self.view_grp.buttonClicked.connect(self._on_view_mode_changed)

        h_layout.addWidget(self.btn_view_single)
        h_layout.addWidget(self.btn_view_wipe)
        h_layout.addWidget(self.btn_view_side)

        # Channel Dropdown
        self.combo_channel = QComboBox()
        self.combo_channel.setStyleSheet("background:#171a22; border:1px solid #272c38; color:#c9d1d9; padding:3px 8px; border-radius:4px; font-size:11px;")
        self.combo_channel.addItem(tr("wb_chan_composite"), "comp")
        self.combo_channel.addItem(tr("wb_chan_alpha"), "alpha")
        self.combo_channel.addItem(tr("wb_chan_orig"), "orig")
        self.combo_channel.currentIndexChanged.connect(self._on_channel_changed)
        h_layout.addWidget(self.combo_channel)

        # Fit Dropdown
        self.combo_zoom = QComboBox()
        self.combo_zoom.setStyleSheet("background:#171a22; border:1px solid #272c38; color:#c9d1d9; padding:3px 8px; border-radius:4px; font-size:11px;")
        self.combo_zoom.addItem(tr("wb_fit"), "fit")
        self.combo_zoom.addItem(tr("wb_fit_100"), "100")
        self.combo_zoom.addItem(tr("wb_fit_50"), "50")
        h_layout.addWidget(self.combo_zoom)

        h_layout.addStretch(1)

        # Active Clip Title
        self.lbl_active_clip = QLabel("")
        self.lbl_active_clip.setStyleSheet("color:#c9d1d9; font-weight:bold; font-size:12px; margin-right:8px;")
        h_layout.addWidget(self.lbl_active_clip)

        # Language Toggle
        self.lbl_lang = QLabel(tr('lbl_language'))
        self.lbl_lang.setStyleSheet('color:#8fa3bf;font-size:11px;')
        h_layout.addWidget(self.lbl_lang)

        self.combo_lang = QComboBox()
        self.combo_lang.setStyleSheet('background:#171a22;border:1px solid #272c38;color:#c9d1d9;padding:2px 8px;border-radius:4px;font-size:11px;')
        self.combo_lang.addItem('EN', LANG_EN)
        self.combo_lang.addItem('KO', LANG_KO)
        cur_lang = get_language()
        idx = self.combo_lang.findData(cur_lang)
        if idx >= 0:
            self.combo_lang.setCurrentIndex(idx)
        self.combo_lang.currentIndexChanged.connect(self._on_language_changed)
        h_layout.addWidget(self.combo_lang)

        # AI Models Button
        self.btn_models = QPushButton(tr('btn_models'))
        self.btn_models.setToolTip(tr('btn_models_tip'))
        self.btn_models.setStyleSheet('background:#1d3144;border:1px solid #2b4f73;color:#a3d5ff;font-weight:bold;padding:3px 10px;border-radius:4px;font-size:11px;')
        self.btn_models.clicked.connect(lambda: self.show_model_manager())
        h_layout.addWidget(self.btn_models)

        # About Button
        self.btn_about = QPushButton(tr('btn_about'))
        self.btn_about.setStyleSheet('background:#171a22;border:1px solid #272c38;color:#8fa3bf;padding:3px 10px;border-radius:4px;font-size:11px;')
        self.btn_about.clicked.connect(self.show_about_dialog)
        h_layout.addWidget(self.btn_about)

        return header

    # =========================================================================
    # Panel 1: Left Media Bin & Queue
    # =========================================================================
    def _build_media_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background-color: #12141a;")
        v_layout = QVBoxLayout(panel)
        v_layout.setContentsMargins(8, 8, 8, 8)
        v_layout.setSpacing(6)

        # Left-Top Status Section (GPU Memory)
        self.sec_left_status = CollapsibleSection(tr("wb_sec_status"), starts_open=True)
        f_left_stat = QFormLayout()
        f_left_stat.setContentsMargins(8, 4, 8, 6)
        f_left_stat.setSpacing(6)
        self.lbl_left_gpu_title = QLabel(tr("wb_gpu_memory"))
        self.lbl_left_gpu_title.setStyleSheet("color:#8e939d; font-size:11px; font-weight:bold;")
        self.lbl_left_gpu_val = QLabel("-- / -- GB")
        self.lbl_left_gpu_val.setStyleSheet("color:#ffffff; font-size:13px; font-weight:800;")
        self.lbl_left_gpu_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f_left_stat.addRow(self.lbl_left_gpu_title, self.lbl_left_gpu_val)
        self.sec_left_status.addLayout(f_left_stat)
        v_layout.addWidget(self.sec_left_status)

        self.grp_queue = QGroupBox(tr("grp_input"))
        self.grp_queue.setStyleSheet("""
            QGroupBox {
                border: 1px solid #1e222b;
                border-radius: 6px;
                margin-top: 6px;
                padding-top: 8px;
                font-weight: bold;
                color: #e5a93c;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
            }
        """)
        g_layout = QVBoxLayout(self.grp_queue)
        g_layout.setContentsMargins(6, 6, 6, 6)
        g_layout.setSpacing(6)

        # Media Header
        h_media_hdr = QHBoxLayout()
        self.lbl_media_bin = QLabel(tr("wb_media_bin"))
        self.lbl_media_bin.setStyleSheet("font-size:12px; font-weight:800; color:#e1e7ee; letter-spacing:1px;")
        h_media_hdr.addWidget(self.lbl_media_bin)
        h_media_hdr.addStretch(1)

        self.btn_add_vid = QPushButton(tr("wb_import"))
        self.btn_add_vid.setStyleSheet("background:#191d26; border:1px solid #2b313e; color:#e5a93c; font-weight:bold; padding:4px 8px; border-radius:4px; font-size:11px;")
        self.btn_add_vid.clicked.connect(self.add_videos)
        h_media_hdr.addWidget(self.btn_add_vid)

        self.btn_clear_q = QPushButton("🗑️")
        self.btn_clear_q.setToolTip(tr("btn_clear_queue"))
        self.btn_clear_q.setStyleSheet("background:#191d26; border:1px solid #2b313e; color:#8fa3bf; padding:4px 6px; border-radius:4px;")
        self.btn_clear_q.clicked.connect(self.clear_queue)
        h_media_hdr.addWidget(self.btn_clear_q)

        g_layout.addLayout(h_media_hdr)

        # List Widget for Media Cards
        self.queue = QListWidget()
        self.queue.setStyleSheet("""
            QListWidget {
                background: #0d0f13;
                border: 1px solid #1d212b;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                margin-bottom: 4px;
                border-radius: 4px;
            }
        """)
        self.queue.currentRowChanged.connect(self.preview_input)
        g_layout.addWidget(self.queue, 1)

        # Secondary Actions
        h_sub = QHBoxLayout()
        self.btn_add_seq = QPushButton(tr("btn_add_folder"))
        self.btn_add_seq.setStyleSheet("background:#151820; border:1px solid #242935; color:#8fa3bf; font-size:10px; padding:3px 6px;")
        self.btn_add_seq.clicked.connect(self.add_folder)
        h_sub.addWidget(self.btn_add_seq)

        self.btn_remove_item = QPushButton(tr("btn_remove"))
        self.btn_remove_item.setStyleSheet("background:#151820; border:1px solid #242935; color:#8fa3bf; font-size:10px; padding:3px 6px;")
        self.btn_remove_item.clicked.connect(self.remove_input)
        h_sub.addWidget(self.btn_remove_item)
        g_layout.addLayout(h_sub)

        v_layout.addWidget(self.grp_queue, 3)

        # Queue / Render History Section
        v_queue = QWidget()
        v_queue_layout = QVBoxLayout(v_queue)
        v_queue_layout.setContentsMargins(4, 4, 4, 4)
        v_queue_layout.setSpacing(4)

        self.lbl_queue_title = QLabel(tr("wb_queue"))
        self.lbl_queue_title.setStyleSheet("font-size:11px; font-weight:bold; color:#7e8b9d; letter-spacing:1px;")
        v_queue_layout.addWidget(self.lbl_queue_title)

        self.queue_info = QLabel(tr("wb_queue_empty"))
        self.queue_info.setStyleSheet("color:#5c6878; font-size:10px; padding:6px; background:#0d0f13; border:1px dashed #1e222c; border-radius:4px;")
        self.queue_info.setWordWrap(True)
        v_queue_layout.addWidget(self.queue_info)

        v_layout.addWidget(v_queue, 1)

        return panel

    # =========================================================================
    # Panel 2: Center VFX Viewport & Filmstrip Scrubber
    # =========================================================================
    def _build_center_viewport_panel(self) -> QWidget:
        center = QWidget()
        center.setStyleSheet("background-color: #0e1014;")
        v_layout = QVBoxLayout(center)
        v_layout.setContentsMargins(6, 6, 6, 6)
        v_layout.setSpacing(4)

        # Large Interactive VFX Viewport
        self.viewport = VFXViewport()
        self.viewport.wipe_position_changed.connect(lambda pos: None)
        v_layout.addWidget(self.viewport, 1)

        # Filmstrip Scrubber & Transport Timeline
        self.filmstrip = FilmstripTimeline()
        self.filmstrip.frame_changed.connect(self._on_filmstrip_frame_changed)
        v_layout.addWidget(self.filmstrip)

        return center

    # =========================================================================
    # Panel 3: Right Inspector & Deliver Panel
    # =========================================================================
    def _build_inspector_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background-color: #12141a; border-left: 1px solid #1f232e;")
        v_layout = QVBoxLayout(panel)
        v_layout.setContentsMargins(8, 8, 8, 8)
        v_layout.setSpacing(6)

        # Inspector Title & Dock Icon (matching official DCC Workbench)
        h_insp_hdr = QHBoxLayout()
        self.lbl_insp = QLabel(tr("wb_inspector"))
        self.lbl_insp.setStyleSheet("font-size:12px; font-weight:800; color:#a0a5ad; letter-spacing:1px; margin-bottom:2px;")
        h_insp_hdr.addWidget(self.lbl_insp)
        h_insp_hdr.addStretch(1)
        self.btn_insp_dock = QLabel("◫")
        self.btn_insp_dock.setStyleSheet("color:#626b7a; font-size:12px; margin-right:4px;")
        h_insp_hdr.addWidget(self.btn_insp_dock)
        v_layout.addLayout(h_insp_hdr)

        # Scrollable Accordions
        self.inspector_scroll = QScrollArea()
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #12141a;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #242935;
                border-radius: 4px;
            }
        """)

        accordions = QWidget()
        accordions.setStyleSheet("background: transparent;")
        acc_layout = QVBoxLayout(accordions)
        acc_layout.setContentsMargins(0, 0, 0, 0)
        acc_layout.setSpacing(4)

        # 0. Status Section (GPU Memory) - Matching reference mockup
        self.sec_insp_status = CollapsibleSection(tr("wb_sec_status"), starts_open=True)
        f_insp_stat = QFormLayout()
        f_insp_stat.setContentsMargins(8, 4, 8, 6)
        f_insp_stat.setSpacing(6)
        self.lbl_insp_gpu_title = QLabel(tr("wb_gpu_memory"))
        self.lbl_insp_gpu_title.setStyleSheet("color:#8e939d; font-size:11px; font-weight:bold;")
        self.lbl_insp_gpu_val = QLabel("-- / -- GB")
        self.lbl_insp_gpu_val.setStyleSheet("color:#ffffff; font-size:13px; font-weight:800;")
        self.lbl_insp_gpu_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f_insp_stat.addRow(self.lbl_insp_gpu_title, self.lbl_insp_gpu_val)
        self.sec_insp_status.addLayout(f_insp_stat)
        acc_layout.addWidget(self.sec_insp_status)

        # 1. Core & Memory Section
        self.sec_memory = CollapsibleSection(tr("wb_sec_memory"), starts_open=True)
        f_mem = QFormLayout()
        f_mem.setSpacing(6)

        self.chk_awareness = QCheckBox(tr("wb_awareness"))
        self.chk_awareness.setChecked(True)
        f_mem.addRow("", self.chk_awareness)

        h_ta = QHBoxLayout()
        self.slider_time_awareness = QSlider(Qt.Horizontal)
        self.slider_time_awareness.setRange(1, 8)
        self.slider_time_awareness.setValue(4)
        self.lbl_time_val = QLabel("4")
        self.lbl_time_val.setStyleSheet("color:#e5a93c; font-weight:bold; min-width:18px;")
        self.slider_time_awareness.valueChanged.connect(lambda v: self.lbl_time_val.setText(str(v)))
        h_ta.addWidget(self.slider_time_awareness)
        h_ta.addWidget(self.lbl_time_val)
        self.lbl_row_time_awareness = QLabel(tr("wb_time_awareness"))
        f_mem.addRow(self.lbl_row_time_awareness, h_ta)

        self.combo_gpu_limit = QComboBox()
        self.combo_gpu_limit.addItems(["Auto", "24 GB (RTX 4090)", "16 GB (RTX 4080)", "12 GB (RTX 3060)", "8 GB"])
        self.combo_gpu_limit.currentIndexChanged.connect(lambda _: self.update_deliver_vram_diagnosis())
        self.lbl_row_gpu_limit = QLabel(tr("wb_gpu_mem_limit"))
        f_mem.addRow(self.lbl_row_gpu_limit, self.combo_gpu_limit)

        self.low_vram = QCheckBox(tr("chk_low_vram"))
        self.low_vram.setToolTip(tr("chk_low_vram_tip"))
        self.low_vram.toggled.connect(lambda _: self.update_deliver_vram_diagnosis())
        f_mem.addRow("", self.low_vram)

        self.hann_mode = QComboBox()
        self.hann_mode.addItem(tr('hann_auto'), 'auto')
        self.hann_mode.addItem(tr('hann_80_40'), '80_40')
        self.hann_mode.addItem(tr('hann_48_24'), '48_24')
        self.hann_mode.addItem(tr('hann_24_12'), '24_12')
        self.hann_mode.addItem(tr('hann_8_4'), '8_4')
        self.hann_mode.addItem(tr('hann_1_1'), '1_1')
        self.hann_mode.addItem(tr('hann_custom'), 'custom')
        self.hann_mode.currentIndexChanged.connect(self._on_hann_mode_changed)
        self.lbl_row_hann = QLabel(tr('lbl_hann'))
        f_mem.addRow(self.lbl_row_hann, self.hann_mode)

        h_custom_hann = QHBoxLayout()
        self.hann_chunk = QSpinBox()
        self.hann_chunk.setRange(1, 128)
        self.hann_chunk.setValue(48)
        self.hann_stride = QSpinBox()
        self.hann_stride.setRange(1, 64)
        self.hann_stride.setValue(24)
        self.hann_chunk.setEnabled(False)
        self.hann_stride.setEnabled(False)
        h_custom_hann.addWidget(QLabel('Chunk:'))
        h_custom_hann.addWidget(self.hann_chunk)
        h_custom_hann.addWidget(QLabel('Stride:'))
        h_custom_hann.addWidget(self.hann_stride)
        self.lbl_row_custom_hann = QLabel(tr('lbl_custom_hann'))
        f_mem.addRow(self.lbl_row_custom_hann, h_custom_hann)

        self.model_scale = QDoubleSpinBox()
        self.model_scale.setRange(0.25, 1.0)
        self.model_scale.setSingleStep(0.05)
        self.model_scale.setValue(1.0)
        self.model_scale.setToolTip(tr('lbl_model_scale_tip'))
        self.lbl_row_model_scale = QLabel(tr('lbl_model_scale'))
        f_mem.addRow(self.lbl_row_model_scale, self.model_scale)

        self.stage2_batch = QSpinBox()
        self.stage2_batch.setRange(1, 16)
        self.stage2_batch.setValue(1)
        self.lbl_row_stage2_batch = QLabel(tr('lbl_stage2_batch'))
        f_mem.addRow(self.lbl_row_stage2_batch, self.stage2_batch)

        self.weights_path = QLineEdit()
        self.weights_path.setPlaceholderText(tr('weights_placeholder'))
        self.lbl_row_weights = QLabel(tr('lbl_weights'))
        f_mem.addRow(self.lbl_row_weights, self.path_row(self.weights_path, is_file=True))

        self.sec_memory.addLayout(f_mem)
        acc_layout.addWidget(self.sec_memory)

        # 2. Alpha Hint Section
        self.sec_hint = CollapsibleSection(tr("wb_sec_hint"), starts_open=True)
        f_hint = QFormLayout()
        f_hint.setSpacing(6)

        self.hint = QLineEdit()
        self.hint.setPlaceholderText(tr('hint_placeholder'))
        self.lbl_row_hint_file = QLabel(tr('lbl_hint_file'))
        f_hint.addRow(self.lbl_row_hint_file, self.path_row(self.hint, is_hint=True))

        h_hint_btns = QHBoxLayout()
        self.btn_brush_main = QPushButton(tr('btn_brush_editor'))
        self.btn_brush_main.setStyleSheet('background:#1a4d38;font-weight:bold;color:#67e8b2;padding:5px 8px;border-radius:4px;')
        self.btn_brush_main.setToolTip(tr('btn_brush_editor_tip'))
        self.btn_brush_main.clicked.connect(self.open_brush_editor)
        h_hint_btns.addWidget(self.btn_brush_main)
        f_hint.addRow("", h_hint_btns)

        self.chk_use_hint = QCheckBox("Use Alpha Hint?")
        self.chk_use_hint.setChecked(True)
        f_hint.addRow("", self.chk_use_hint)

        self.hint_mode = QComboBox()
        self.hint_mode.addItem(tr('mode_no_hint'), '')
        self.hint_mode.addItem(tr('mode_first_frame'), '--hint_first_frame')
        self.hint_mode.addItem(tr('mode_video_hint'), '--hint_video')
        self.hint_mode.currentIndexChanged.connect(self._on_hint_mode_changed)
        self.lbl_row_hint_mode = QLabel(tr('lbl_keying_mode'))
        f_hint.addRow(self.lbl_row_hint_mode, self.hint_mode)

        h_qual = QHBoxLayout()
        self.quality = QDoubleSpinBox()
        self.quality.setRange(0.0, 1.0)
        self.quality.setSingleStep(0.05)
        self.quality.setValue(0.75)
        self.lbl_exp_quality = QLabel(tr('lbl_explicit_quality'))
        h_qual.addWidget(self.lbl_exp_quality)
        h_qual.addWidget(self.quality)

        self.carry_quality = QDoubleSpinBox()
        self.carry_quality.setRange(0.0, 1.0)
        self.carry_quality.setSingleStep(0.05)
        self.carry_quality.setValue(0.85)
        self.lbl_cry_quality = QLabel(tr('lbl_carry_quality'))
        h_qual.addWidget(self.lbl_cry_quality)
        h_qual.addWidget(self.carry_quality)
        self.lbl_row_hint_quality = QLabel(tr('lbl_hint_quality'))
        f_hint.addRow(self.lbl_row_hint_quality, h_qual)

        self.no_carry_hint = QCheckBox(tr('chk_no_carry'))
        self.no_carry_hint.setToolTip(tr('chk_no_carry_tip'))
        f_hint.addRow('', self.no_carry_hint)

        self.sec_hint.addLayout(f_hint)
        acc_layout.addWidget(self.sec_hint)

        # 3. Despill Section
        self.sec_despill = CollapsibleSection(tr("wb_sec_despill"), starts_open=True)
        f_despill = QFormLayout()
        f_despill.setSpacing(6)

        self.combo_despill_color = QComboBox()
        self.combo_despill_color.addItems(["Green", "Blue"])
        f_despill.addRow("Despill Color", self.combo_despill_color)

        self.combo_despill_method = QComboBox()
        self.combo_despill_method.addItems(["Average", "Max", "None"])
        f_despill.addRow("Despill Method", self.combo_despill_method)

        self.despill = QDoubleSpinBox()
        self.despill.setRange(0.0, 1.0)
        self.despill.setSingleStep(0.05)
        self.despill.setValue(0.36)
        self.lbl_row_despill = QLabel(tr('lbl_despill'))
        f_despill.addRow(self.lbl_row_despill, self.despill)

        self.sec_despill.addLayout(f_despill)
        acc_layout.addWidget(self.sec_despill)

        # 4. Output & Layers Section
        self.sec_out = CollapsibleSection(tr("wb_sec_output"), starts_open=True)
        v_out_layers = QVBoxLayout()
        v_out_layers.setSpacing(4)

        self.outputs = {}
        for key, tr_k in [
            ('alpha', 'out_alpha'),
            ('fg', 'out_fg'),
            ('checker', 'out_checker'),
            ('cutout', 'out_cutout'),
        ]:
            chk = QCheckBox(tr(tr_k))
            chk.setChecked(key in {'alpha', 'checker'})
            self.outputs[key] = chk

        row_chk1 = QHBoxLayout()
        row_chk1.addWidget(self.outputs['alpha'])
        row_chk1.addWidget(self.outputs['cutout'])
        v_out_layers.addLayout(row_chk1)

        row_chk2 = QHBoxLayout()
        row_chk2.addWidget(self.outputs['checker'])
        row_chk2.addWidget(self.outputs['fg'])
        v_out_layers.addLayout(row_chk2)

        self.cutout_linear = QCheckBox(tr('chk_cutout_linear'))
        self.cutout_linear.setToolTip(tr('chk_cutout_linear_tip'))
        v_out_layers.addWidget(self.cutout_linear)

        f_enc = QFormLayout()
        self.frames = QSpinBox()
        self.frames.setRange(0, 10000000)
        self.frames.setSpecialValueText(tr('special_all_frames'))
        self.lbl_row_num_frames = QLabel(tr('lbl_num_frames'))
        f_enc.addRow(self.lbl_row_num_frames, self.frames)

        self.start = QComboBox()
        self.start.addItem(tr('start_begin'), 'begin')
        self.start.addItem(tr('start_middle'), 'middle')
        self.start.addItem(tr('start_random_middle'), 'random_middle')
        self.lbl_row_start_mode = QLabel(tr('lbl_start_mode'))
        f_enc.addRow(self.lbl_row_start_mode, self.start)

        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)
        self.seed.setValue(0)
        self.lbl_row_seed = QLabel(tr('lbl_seed'))
        f_enc.addRow(self.lbl_row_seed, self.seed)

        self.fps = QDoubleSpinBox()
        self.fps.setRange(1.0, 240.0)
        self.fps.setDecimals(3)
        self.fps.setValue(24.0)
        self.lbl_row_fps = QLabel(tr('lbl_fps'))
        f_enc.addRow(self.lbl_row_fps, self.fps)

        self.linear = QCheckBox(tr('chk_linear'))
        f_enc.addRow('', self.linear)

        self.codec = QComboBox()
        self.codec.addItem(tr('codec_x264'), 'libx264')
        self.codec.addItem(tr('codec_h264_nvenc'), 'h264_nvenc')
        self.codec.addItem(tr('codec_hevc_nvenc'), 'hevc_nvenc')
        self.codec.addItem(tr('codec_prores'), 'prores_ks')
        self.codec.currentIndexChanged.connect(self._on_codec_changed)
        self.lbl_row_codec = QLabel(tr('lbl_codec'))
        f_enc.addRow(self.lbl_row_codec, self.codec)

        self.crf = QSpinBox()
        self.crf.setRange(0, 51)
        self.crf.setValue(12)
        self.lbl_crf_text = QLabel(tr('lbl_crf'))
        self.lbl_row_crf = QLabel(tr('lbl_crf_row'))
        f_enc.addRow(self.lbl_row_crf, self.crf)

        self.pix_fmt = QComboBox()
        self.pix_fmt.addItem(tr('pix_yuv444p10le'), 'yuv444p10le')
        self.pix_fmt.addItem(tr('pix_yuv444p'), 'yuv444p')
        self.pix_fmt.addItem(tr('pix_yuv420p'), 'yuv420p')
        self.lbl_row_pix_fmt = QLabel(tr('lbl_pix_fmt'))
        f_enc.addRow(self.lbl_row_pix_fmt, self.pix_fmt)

        self.preset = QComboBox()
        for p in ['ultrafast', 'fast', 'medium', 'slow', 'veryslow']:
            self.preset.addItem(p, p)
        self.preset.setCurrentText('medium')
        self.lbl_row_preset = QLabel(tr('lbl_preset'))
        f_enc.addRow(self.lbl_row_preset, self.preset)

        self.linear_bright = QDoubleSpinBox()
        self.linear_bright.setRange(0.1, 10.0)
        self.linear_bright.setValue(1.0)
        self.lbl_row_bright = QLabel(tr('lbl_bright'))
        f_enc.addRow(self.lbl_row_bright, self.linear_bright)

        self.linear_contrast = QDoubleSpinBox()
        self.linear_contrast.setRange(0.1, 10.0)
        self.linear_contrast.setValue(1.0)
        self.lbl_row_contrast = QLabel(tr('lbl_contrast'))
        f_enc.addRow(self.lbl_row_contrast, self.linear_contrast)

        self.linear_pivot = QDoubleSpinBox()
        self.linear_pivot.setRange(0.01, 1.0)
        self.linear_pivot.setValue(0.18)
        self.lbl_row_pivot = QLabel(tr('lbl_pivot'))
        f_enc.addRow(self.lbl_row_pivot, self.linear_pivot)

        v_out_layers.addLayout(f_enc)
        self.sec_out.addLayout(v_out_layers)
        acc_layout.addWidget(self.sec_out)

        acc_layout.addStretch(1)
        self.inspector_scroll.setWidget(accordions)
        v_layout.addWidget(self.inspector_scroll, 1)

        # Bottom DELIVER Dock
        deliver_dock = QFrame()
        deliver_dock.setStyleSheet("""
            QFrame {
                background: #141720;
                border: 1px solid #232835;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        v_deliv = QVBoxLayout(deliver_dock)
        v_deliv.setContentsMargins(8, 8, 8, 8)
        v_deliv.setSpacing(6)

        self.lbl_deliv_title = QLabel(tr("wb_deliver"))
        self.lbl_deliv_title.setStyleSheet("font-size:11px; font-weight:800; color:#e5a93c; letter-spacing:1px;")
        v_deliv.addWidget(self.lbl_deliv_title)

        # Output folder
        self.output = QLineEdit(str(ROOT / 'outputs'))
        self.lbl_row_output_dir = QLabel(tr('lbl_output_dir'))
        v_deliv.addWidget(self.lbl_row_output_dir)
        v_deliv.addWidget(self.path_row(self.output, directory=True))

        # Format
        h_fmt = QHBoxLayout()
        self.format = QComboBox()
        self.format.addItem(tr('format_video'), 'video')
        self.format.addItem(tr('format_exr'), 'exr')
        self.format.currentIndexChanged.connect(self._on_format_changed)
        self.lbl_row_format = QLabel(tr('lbl_format'))
        h_fmt.addWidget(self.lbl_row_format)
        h_fmt.addWidget(self.format, 1)

        self.exr_dtype = QComboBox()
        self.exr_dtype.addItem(tr('exr_half'), 'half')
        self.exr_dtype.addItem(tr('exr_float'), 'float')
        self.exr_dtype.setEnabled(False)
        self.lbl_row_exr_dtype = QLabel(tr('lbl_exr_dtype'))
        h_fmt.addWidget(self.lbl_row_exr_dtype)
        h_fmt.addWidget(self.exr_dtype)
        v_deliv.addLayout(h_fmt)

        self.lbl_format_note = QLabel(tr("wb_format_note"))
        self.lbl_format_note.setStyleSheet("color:#65778c; font-size:10px;")
        self.lbl_format_note.setWordWrap(True)
        v_deliv.addWidget(self.lbl_format_note)

        # Diagnosis string (dynamically updated against real GPU hardware)
        self.lbl_deliver_vram = QLabel("")
        self.lbl_deliver_vram.setStyleSheet("color:#7e8b9d; font-size:10px;")
        v_deliv.addWidget(self.lbl_deliver_vram)
        self.update_deliver_vram_diagnosis()

        # Action Buttons: [Render All] [Render] [📁]
        h_deliv_btns = QHBoxLayout()
        self.btn_batch_render = QPushButton(tr("wb_btn_render_all"))
        self.btn_batch_render.setToolTip(tr("wb_btn_render_all_tip"))
        self.btn_batch_render.setStyleSheet("background:#1a1e27; border:1px solid #2b3240; color:#c9d1d9; padding:8px 12px; border-radius:4px; font-weight:bold; font-size:11px;")
        self.btn_batch_render.clicked.connect(self.run_all)
        self.btn_add_to_queue = self.btn_batch_render  # backward compatibility alias
        h_deliv_btns.addWidget(self.btn_batch_render)

        self.run_button = QPushButton(tr("wb_btn_render"))
        self.run_button.setToolTip(tr("wb_btn_render_tip"))
        self.run_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d4952b, stop:1 #f0b842);
                border: 1px solid #f5b642;
                border-radius: 4px;
                color: #111317;
                font-weight: 800;
                font-size: 13px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e5a93c, stop:1 #ffd066);
            }
            QPushButton:disabled {
                background: #2b303d;
                border-color: #383e4d;
                color: #636b7b;
            }
        """)
        self.run_button.clicked.connect(self.run)
        h_deliv_btns.addWidget(self.run_button, 1)

        self.stop_button = QPushButton("⏹ " + tr('btn_stop'))
        self.stop_button.setToolTip(tr('wb_btn_cancel_tip'))
        self.stop_button.setStyleSheet("""
            QPushButton {
                background: #8b1d1d;
                border: 1px solid #dc2626;
                border-radius: 4px;
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background: #dc2626;
                border-color: #ef4444;
            }
            QPushButton:disabled {
                background: #171a22;
                border: 1px solid #232835;
                color: #434c5b;
            }
        """)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        h_deliv_btns.addWidget(self.stop_button)

        self.folder_btn = QPushButton("📁")
        self.folder_btn.setToolTip(tr('btn_open_folder'))
        self.folder_btn.setStyleSheet("background:#1a1e27; border:1px solid #2b3240; color:#8fa3bf; padding:8px 10px; border-radius:4px;")
        self.folder_btn.clicked.connect(self.open_output)
        h_deliv_btns.addWidget(self.folder_btn)

        v_deliv.addLayout(h_deliv_btns)
        v_layout.addWidget(deliver_dock)

        # Hidden proxies for legacy compatibility
        self.check_button = QPushButton(tr('btn_check'))
        self.check_button.clicked.connect(self.check_environment)
        self.check_button.setVisible(False)
        self.download_button = QPushButton(tr('btn_download'))
        self.download_button.clicked.connect(self.download)
        self.download_button.setVisible(False)

        return panel

    # =========================================================================
    # Live Process Console & Progress Drawer
    # =========================================================================
    def _build_console_drawer(self) -> QWidget:
        drawer = QFrame()
        drawer.setStyleSheet("""
            QFrame {
                background-color: #0b0d12;
                border-top: 1px solid #1a1e27;
                border-bottom: 1px solid #13161f;
            }
        """)
        v_layout = QVBoxLayout(drawer)
        v_layout.setContentsMargins(12, 6, 12, 6)
        v_layout.setSpacing(4)

        # Header of Console Drawer
        h_hdr = QHBoxLayout()
        lbl_console_title = QLabel("▶ LIVE PROCESS & TERMINAL LOG")
        lbl_console_title.setStyleSheet("font-size:10px; font-weight:800; color:#e5a93c; letter-spacing:1px;")
        h_hdr.addWidget(lbl_console_title)

        self.lbl_live_task = QLabel("Ready")
        self.lbl_live_task.setStyleSheet("font-size:11px; font-weight:bold; color:#71e0be; margin-left:14px;")
        h_hdr.addWidget(self.lbl_live_task)

        # Prominent Stop Process button in console drawer (active during execution)
        self.btn_live_stop = QPushButton("⏹ " + tr('wb_btn_cancel'))
        self.btn_live_stop.setToolTip(tr('wb_btn_cancel_tip'))
        self.btn_live_stop.setStyleSheet("""
            QPushButton {
                background: #b91c1c;
                border: 1px solid #ef4444;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 2px 10px;
                border-radius: 3px;
                margin-left: 10px;
            }
            QPushButton:hover {
                background: #dc2626;
            }
        """)
        self.btn_live_stop.clicked.connect(self.stop)
        self.btn_live_stop.setVisible(False)
        h_hdr.addWidget(self.btn_live_stop)

        h_hdr.addStretch(1)

        self.btn_clear_log = QPushButton("Clear")
        self.btn_clear_log.setStyleSheet("background:#161922; border:1px solid #282d3b; color:#8fa3bf; font-size:10px; padding:2px 8px; border-radius:3px;")
        self.btn_clear_log.clicked.connect(lambda: self.log.clear())
        h_hdr.addWidget(self.btn_clear_log)

        self.btn_toggle_drawer = QPushButton("Hide Log ▼")
        self.btn_toggle_drawer.setStyleSheet("background:#161922; border:1px solid #282d3b; color:#8fa3bf; font-size:10px; padding:2px 8px; border-radius:3px;")
        self.btn_toggle_drawer.clicked.connect(self._toggle_console_drawer)
        h_hdr.addWidget(self.btn_toggle_drawer)

        v_layout.addLayout(h_hdr)

        # Log Output Box (Monospace, clear green/cyan terminal)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        self.log.setFixedHeight(120)
        self.log.setStyleSheet("""
            QPlainTextEdit {
                background-color: #06070a;
                border: 1px solid #161922;
                border-radius: 4px;
                color: #58e6b8;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                line-height: 140%;
                padding: 6px 10px;
            }
        """)
        v_layout.addWidget(self.log)

        return drawer

    def _toggle_console_drawer(self):
        is_vis = self.log.isVisible()
        self.log.setVisible(not is_vis)
        self.btn_toggle_drawer.setText("Show Log ▲" if is_vis else "Hide Log ▼")

    # =========================================================================
    # Bottom Status Bar & Telemetry
    # =========================================================================
    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet("background-color: #090b0e; border-top: 1px solid #161922;")
        h_layout = QHBoxLayout(bar)
        h_layout.setContentsMargins(12, 0, 14, 0)
        h_layout.setSpacing(10)

        self.btn_status_log = QPushButton("📋 Log Console")
        self.btn_status_log.setStyleSheet("background:#151820; border:1px solid #242936; color:#8fa3bf; font-size:10px; padding:2px 8px; border-radius:3px;")
        self.btn_status_log.clicked.connect(self._toggle_console_drawer)
        h_layout.addWidget(self.btn_status_log)

        self.status = QLabel(tr("status_ready"))
        self.status.setStyleSheet("color:#a1b2c6; font-size:11px; font-weight:bold;")
        h_layout.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFixedWidth(200)
        self.progress.setStyleSheet("""
            QProgressBar {
                max-height: 12px;
                border: 1px solid #202633;
                background: #0f1218;
                border-radius: 3px;
                color: #ffffff;
                font-size: 9px;
                font-weight: bold;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e8061, stop:1 #49de80);
                border-radius: 2px;
            }
        """)
        h_layout.addWidget(self.progress)

        h_layout.addStretch(1)

        self.lbl_lic_badge = QLabel(tr('license_badge'))
        self.lbl_lic_badge.setStyleSheet('color:#485261;font-size:10px;')
        h_layout.addWidget(self.lbl_lic_badge)

        self.lbl_telemetry = QLabel(get_system_telemetry())
        self.lbl_telemetry.setStyleSheet("color:#7e8b9d; font-size:11px; font-weight:bold;")
        h_layout.addWidget(self.lbl_telemetry)

        return bar

    def _update_telemetry(self):
        """Periodically refresh hardware telemetry string and live GPU metrics."""
        used_gb, free_gb, tot_gb, pct, gpu_name = get_gpu_vram_info()
        has_cuda = (tot_gb > 0)

        if has_cuda:
            gpu_mem_text = f"{used_gb:.1f} / {tot_gb:.1f} GB"
            badge_text = f"⚡ GPU: {used_gb:.1f}/{tot_gb:.1f} GB ({pct:.0f}%)"
            tip = (
                f"Device: {gpu_name}\n"
                f"Used VRAM: {used_gb:.2f} GB ({pct:.1f}%)\n"
                f"Free VRAM: {free_gb:.2f} GB\n"
                f"Total Physical VRAM: {tot_gb:.2f} GB"
            )
        else:
            gpu_mem_text = "N/A"
            badge_text = "⚡ GPU: N/A"
            tip = "CUDA GPU not detected (CPU Mode)"

        if hasattr(self, 'badge_gpu'):
            self.badge_gpu.setText(badge_text)
            self.badge_gpu.setToolTip(tip)
        if hasattr(self, 'lbl_left_gpu_val'):
            self.lbl_left_gpu_val.setText(gpu_mem_text)
            self.lbl_left_gpu_val.setToolTip(tip)
        if hasattr(self, 'lbl_insp_gpu_val'):
            self.lbl_insp_gpu_val.setText(gpu_mem_text)
            self.lbl_insp_gpu_val.setToolTip(tip)
        if hasattr(self, 'lbl_telemetry'):
            self.lbl_telemetry.setText(get_system_telemetry())
            self.lbl_telemetry.setToolTip(tip)

        if hasattr(self, 'lbl_deliver_vram'):
            self.update_deliver_vram_diagnosis()

    def update_deliver_vram_diagnosis(self):
        """Dynamically diagnose active clip VRAM requirement against real GPU hardware."""
        used_gb, free_gb, tot_gb, pct, gpu_name = get_gpu_vram_info()
        has_gpu = (tot_gb > 0)

        if not hasattr(self, 'lbl_deliver_vram'):
            return

        if not self.current_clip_path or self.queue.count() == 0:
            if has_gpu:
                self.lbl_deliver_vram.setText(
                    tr('vram_diag_idle', free=f"{free_gb:.1f}", total=f"{tot_gb:.1f}")
                )
                self.lbl_deliver_vram.setStyleSheet("color:#7e8b9d; font-size:10px;")
            else:
                self.lbl_deliver_vram.setText(tr('vram_diag_cpu'))
                self.lbl_deliver_vram.setStyleSheet("color:#e5a93c; font-size:10px;")
            return

        clip_key = str(self.current_clip_path.resolve())
        meta = self._clip_cache.get(clip_key, {})
        w = meta.get('w', 1920)
        h = meta.get('h', 1080)
        n_frames = meta.get('n_frames', 0)
        is_low_vram = self.low_vram.isChecked() if hasattr(self, 'low_vram') else False

        # Calculate estimated peak VRAM using official CorridorKey formula
        try:
            from corridorkey.runtime import estimate_peak_vram_gb, select_vram_profile
            mp = (w * h) / 1e6
            chunk, stride, auto_low, est_peak = select_vram_profile((h, w), max(1, n_frames), max(1.0, free_gb))
            if is_low_vram:
                est_peak = estimate_peak_vram_gb(mp, min(chunk, max(1, n_frames)), low_vram=True)
            est_vram_str = f"{est_peak:.1f}"
        except Exception:
            est_peak = 14.0 if (w * h >= 3840 * 2160) else (5.8 if (w * h >= 1920 * 1080) else 3.2)
            if is_low_vram:
                est_peak *= 0.55
            est_vram_str = f"{est_peak:.1f}"

        if has_gpu:
            fits = (free_gb >= est_peak)
            if fits:
                msg = tr(
                    'vram_diag_fits',
                    req=est_vram_str,
                    free=f"{free_gb:.1f}",
                    total=f"{tot_gb:.1f}",
                    frames=n_frames,
                    res=f"{w}x{h}"
                )
                self.lbl_deliver_vram.setText(msg)
                self.lbl_deliver_vram.setStyleSheet("color:#4ade80; font-size:10px; font-weight:bold;")
            else:
                msg = tr(
                    'vram_diag_tight',
                    req=est_vram_str,
                    free=f"{free_gb:.1f}",
                    total=f"{tot_gb:.1f}",
                    frames=n_frames,
                    res=f"{w}x{h}"
                )
                self.lbl_deliver_vram.setText(msg)
                self.lbl_deliver_vram.setStyleSheet("color:#f59e0b; font-size:10px; font-weight:bold;")

            self.lbl_deliver_vram.setToolTip(
                f"Device: {gpu_name}\n"
                f"Estimated Peak VRAM: ~{est_vram_str} GB\n"
                f"Free VRAM: {free_gb:.2f} GB\n"
                f"Total Physical VRAM: {tot_gb:.2f} GB\n"
                f"Currently Used VRAM: {used_gb:.2f} GB\n"
                f"Resolution: {w}x{h} ({n_frames} frames)\n"
                f"Low-VRAM: {'ON' if is_low_vram else 'OFF'}"
            )
        else:
            self.lbl_deliver_vram.setText(tr('vram_diag_cpu'))
            self.lbl_deliver_vram.setStyleSheet("color:#e5a93c; font-size:10px;")

    # =========================================================================
    # Media Loading & Syncing with Viewport / Filmstrip
    # =========================================================================
    def preview_input(self, index: int):
        if index < 0 or index >= self.queue.count():
            return
        clip_path = Path(self.queue.item(index).text())
        if hasattr(self, 'current_clip_path') and self.current_clip_path and self.current_clip_path != clip_path:
            self._clip_options[str(self.current_clip_path.resolve())] = self.options()
        self.current_clip_path = clip_path
        self.lbl_active_clip.setText(clip_path.name)

        # Stop playback if currently playing
        if hasattr(self, 'filmstrip') and self.filmstrip.is_playing:
            self.filmstrip.toggle_play()
        self._release_video_caps()

        # Update card selection state
        for i in range(self.queue.count()):
            item = self.queue.item(i)
            card = self.queue.itemWidget(item)
            if isinstance(card, MediaCardWidget):
                card.set_selected(i == index)

        # Update queue status line when idle
        if hasattr(self, 'queue_info') and not getattr(self, 'jobs', None) and self.proc.state() == QProcess.NotRunning:
            self.queue_info.setText(tr('wb_queue_ready_active', name=clip_path.name))

        # Restore per-clip options if saved
        clip_key_res = str(clip_path.resolve())
        if clip_key_res in self._clip_options:
            self.set_options(self._clip_options[clip_key_res])
        else:
            self.auto_detect_companion_hint(clip_path)

        # Synchronize hidden legacy preview
        self.original.load(clip_path)

        # Fast Cached Metadata & Thumbnails for zero-lag clip switching
        clip_key = str(clip_path.resolve())
        if clip_key in self._clip_cache and self._clip_cache[clip_key].get('thumbs'):
            meta = self._clip_cache[clip_key]
            n_frames = meta['n_frames']
            fps = meta['fps']
            w, h = meta['w'], meta['h']
            thumbs = meta['thumbs']
        else:
            cap = cv2.VideoCapture(str(clip_path))
            n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS)) or 24.0
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            thumbs = []
            if n_frames > 0:
                step = max(1, n_frames // 16)
                for idx in range(0, n_frames, step)[:16]:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    ok, f = cap.read()
                    if ok and f is not None:
                        rgb_small = cv2.cvtColor(cv2.resize(f, (80, 45)), cv2.COLOR_BGR2RGB)
                        q_img = QImage(rgb_small.data, 80, 45, rgb_small.strides[0], QImage.Format_RGB888).copy()
                        thumbs.append(QPixmap.fromImage(q_img))
            cap.release()
            self._clip_cache[clip_key] = {
                'n_frames': n_frames,
                'fps': fps,
                'w': w,
                'h': h,
                'thumbs': thumbs,
            }

        # Update filmstrip immediately
        self.filmstrip.load_clip_metadata(n_frames, fps, thumbs)

        # Search for any pre-rendered outputs for this clip in outputs/
        self._detect_matched_results(clip_path)

        # Display first frame in viewport
        self.show_frame_in_viewport(0)

        # Dynamically diagnose VRAM requirement against real GPU hardware
        self.update_deliver_vram_diagnosis()

        # Auto-detect companion hint specifically for this clip
        self.auto_detect_companion_hint(clip_path)

    def _detect_matched_results(self, clip_path: Path):
        """Find existing rendered outputs matching this clip name without heavy disk walking."""
        self.matched_results.clear()
        out_root = Path(self.output.text()).resolve() if self.output.text().strip() else (ROOT / 'outputs')
        if not out_root.exists():
            return
        base = clip_path.stem.lower()
        try:
            for item in out_root.iterdir():
                if base in item.name.lower():
                    if item.is_dir():
                        for f in item.iterdir():
                            if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
                                nl = f.name.lower()
                                if 'checker' in nl or 'comp' in nl:
                                    self.matched_results['comp'] = f
                                elif 'alpha' in nl:
                                    self.matched_results['alpha'] = f
                    elif item.is_file() and item.suffix.lower() in VIDEO_EXTS:
                        nl = item.name.lower()
                        if 'checker' in nl or 'comp' in nl:
                            self.matched_results['comp'] = item
                        elif 'alpha' in nl:
                            self.matched_results['alpha'] = item
        except OSError:
            pass

    def _on_filmstrip_frame_changed(self, frame_idx: int):
        """Called when user scrubs or plays the filmstrip."""
        self.show_frame_in_viewport(frame_idx)
        # Keep legacy slider in sync
        if self.original.slider.maximum() >= frame_idx:
            self.original.slider.blockSignals(True)
            self.original.slider.setValue(frame_idx)
            self.original.slider.blockSignals(False)

    def _release_video_caps(self):
        """Safely close persistent VideoCapture streams and reset RAM cache."""
        if hasattr(self, '_cap_orig') and self._cap_orig is not None:
            self._cap_orig.release()
            self._cap_orig = None
            self._cap_orig_path = None
            self._cap_orig_pos = -1
        if hasattr(self, '_cap_res') and self._cap_res is not None:
            self._cap_res.release()
            self._cap_res = None
            self._cap_res_path = None
            self._cap_res_pos = -1
        if hasattr(self, '_cap_alpha') and self._cap_alpha is not None:
            self._cap_alpha.release()
            self._cap_alpha = None
            self._cap_alpha_path = None
            self._cap_alpha_pos = -1
        if hasattr(self, '_viewport_frame_cache'):
            self._viewport_frame_cache.clear()

    def show_frame_in_viewport(self, frame_idx: int):
        """High-performance zero-lag frame decoding and viewport rendering (60+ FPS)."""
        if not self.current_clip_path or not self.current_clip_path.exists():
            return

        # 0. Check in-memory viewport cache for zero-latency instant playback (300+ FPS)
        if hasattr(self, '_viewport_frame_cache') and frame_idx in self._viewport_frame_cache:
            orig_pix, comp_pix, alpha_pix, w, h = self._viewport_frame_cache[frame_idx]
            self.viewport.set_images(
                orig=orig_pix,
                comp=comp_pix or orig_pix,
                alpha=alpha_pix,
                title=f"{self.current_clip_path.name} [Frame {frame_idx + 1}]"
            )
            self.original.caption.setText(tr('frame_caption', name=self.current_clip_path.name, w=w, h=h, frame=frame_idx + 1))
            return

        clip_path = self.current_clip_path

        # 1. Maintain persistent VideoCapture stream for original video
        if self._cap_orig_path != clip_path or self._cap_orig is None:
            if self._cap_orig is not None:
                self._cap_orig.release()
            self._cap_orig = cv2.VideoCapture(str(clip_path))
            self._cap_orig_path = clip_path
            self._cap_orig_pos = 0

        # High-speed read (sequential read does not require GOP seek!)
        f = None
        ok = False
        if self._cap_orig_pos == frame_idx:
            ok, f = self._cap_orig.read()
            self._cap_orig_pos += 1
        else:
            self._cap_orig.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, f = self._cap_orig.read()
            self._cap_orig_pos = frame_idx + 1 if ok else -1

        if not ok or f is None:
            return

        rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        self.original.current_rgb_frame = rgb
        h, w, _ = rgb.shape
        orig_pix = QPixmap.fromImage(QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy())
        self.original.pixmap = orig_pix

        # 2. Maintain persistent stream for result video (composite or alpha)
        comp_pix = None
        alpha_pix = None
        res_path = self.matched_results.get('comp') or self.matched_results.get('alpha')
        if res_path and res_path.exists():
            if self._cap_res_path != res_path or self._cap_res is None:
                if self._cap_res is not None:
                    self._cap_res.release()
                self._cap_res = cv2.VideoCapture(str(res_path))
                self._cap_res_path = res_path
                self._cap_res_pos = 0

            if self._cap_res_pos == frame_idx:
                ok_res, f_res = self._cap_res.read()
                self._cap_res_pos += 1
            else:
                self._cap_res.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok_res, f_res = self._cap_res.read()
                self._cap_res_pos = frame_idx + 1 if ok_res else -1

            if ok_res and f_res is not None:
                rgb_res = cv2.cvtColor(f_res, cv2.COLOR_BGR2RGB)
                hr, wr, _ = rgb_res.shape
                comp_pix = QPixmap.fromImage(QImage(rgb_res.data, wr, hr, rgb_res.strides[0], QImage.Format_RGB888).copy())

        # 3. Maintain persistent stream for standalone alpha channel
        alpha_path = self.matched_results.get('alpha')
        if alpha_path and alpha_path.exists():
            if self._cap_alpha_path != alpha_path or self._cap_alpha is None:
                if self._cap_alpha is not None:
                    self._cap_alpha.release()
                self._cap_alpha = cv2.VideoCapture(str(alpha_path))
                self._cap_alpha_path = alpha_path
                self._cap_alpha_pos = 0

            if self._cap_alpha_pos == frame_idx:
                ok_a, f_a = self._cap_alpha.read()
                self._cap_alpha_pos += 1
            else:
                self._cap_alpha.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok_a, f_a = self._cap_alpha.read()
                self._cap_alpha_pos = frame_idx + 1 if ok_a else -1

            if ok_a and f_a is not None:
                rgb_a = cv2.cvtColor(f_a, cv2.COLOR_BGR2RGB)
                ha, wa, _ = rgb_a.shape
                alpha_pix = QPixmap.fromImage(QImage(rgb_a.data, wa, ha, rgb_a.strides[0], QImage.Format_RGB888).copy())
                if f is not None:
                    gray_a = cv2.cvtColor(f_a, cv2.COLOR_BGR2GRAY) if f_a.ndim == 3 else f_a
                    if gray_a.shape[:2] != f.shape[:2]:
                        gray_a = cv2.resize(gray_a, (w, h), interpolation=cv2.INTER_LINEAR)
                    rgba = cv2.cvtColor(f, cv2.COLOR_BGR2RGBA)
                    rgba[:, :, 3] = gray_a
                    comp_pix = QPixmap.fromImage(QImage(rgba.data, w, h, rgba.strides[0], QImage.Format_RGBA8888).copy())

        # 4. Cache decoded frame tuple into memory (limit to 300 frames to keep RAM footprint low)
        if hasattr(self, '_viewport_frame_cache'):
            if len(self._viewport_frame_cache) > 300:
                for k in list(self._viewport_frame_cache.keys())[:50]:
                    del self._viewport_frame_cache[k]
            self._viewport_frame_cache[frame_idx] = (orig_pix, comp_pix, alpha_pix, w, h)

        # 5. Bind into VFX Viewport
        self.viewport.set_images(
            orig=orig_pix,
            comp=comp_pix or orig_pix,
            alpha=alpha_pix,
            title=f"{self.current_clip_path.name} [Frame {frame_idx + 1}]"
        )
        self.original.caption.setText(tr('frame_caption', name=self.current_clip_path.name, w=w, h=h, frame=frame_idx + 1))

    def _on_view_mode_changed(self, btn):
        if btn == self.btn_view_single:
            self.viewport.set_view_mode("single")
        elif btn == self.btn_view_wipe:
            self.viewport.set_view_mode("wipe")
        elif btn == self.btn_view_side:
            self.viewport.set_view_mode("side_by_side")

    def _on_channel_changed(self, idx: int):
        mode = self.combo_channel.itemData(idx)
        self.viewport.set_channel_mode(mode)

    def _on_tool_rail_selected(self, key: str):
        """Handle click actions for all 7 vertical DCC workstation tool rail icons."""
        if key == "media":
            # 📁 Focus & ensure Left Media Bin is visible
            sizes = self.split.sizes()
            if sizes[0] <= 10:
                self.split.setSizes([260, max(400, sizes[1] - 130), max(300, sizes[2] - 130)])
            self.queue.setFocus()
            self.status.setText("📁 Media Bin: Clips & Queue active")

        elif key == "layers":
            # 🎭 Ensure Inspector visible, open Alpha Hint & Output Layers
            sizes = self.split.sizes()
            if sizes[2] <= 10:
                self.split.setSizes([sizes[0], max(400, sizes[1] - 150), 380])
            self.sec_hint.set_open(True)
            if hasattr(self, 'inspector_scroll'):
                self.inspector_scroll.ensureWidgetVisible(self.sec_hint)
            self.btn_brush_main.setFocus()
            idx_alpha = self.combo_channel.findData("alpha")
            if idx_alpha >= 0:
                self.combo_channel.setCurrentIndex(idx_alpha)
            self.status.setText("🎭 Matte & Layers: Alpha Hint & Output Layers active")

        elif key == "wipe":
            # ↔️ Activate Wipe Split Comparison in Viewport
            self.btn_view_wipe.setChecked(True)
            self.viewport.set_view_mode("wipe")
            self.viewport.wipe_pos = 0.5
            self.viewport.update()
            idx_comp = self.combo_channel.findData("comp")
            if idx_comp >= 0:
                self.combo_channel.setCurrentIndex(idx_comp)
            self.status.setText("↔️ Wipe Comparison: Drag vertical divider across viewport")

        elif key == "history":
            # ⏱️ Toggle Live Process Log & Terminal Drawer
            if hasattr(self, 'console_drawer'):
                is_vis = self.log.isVisible()
                self._toggle_console_drawer()
                if not is_vis:
                    self.log.setFocus()
            self.status.setText("⏱️ Terminal Log & Process Drawer toggled")

        elif key == "color":
            # 🎨 Ensure Inspector visible, open Despill & Color Tuning
            sizes = self.split.sizes()
            if sizes[2] <= 10:
                self.split.setSizes([sizes[0], max(400, sizes[1] - 150), 380])
            self.sec_despill.set_open(True)
            if hasattr(self, 'inspector_scroll'):
                self.inspector_scroll.ensureWidgetVisible(self.sec_despill)
            self.despill.setFocus()
            self.status.setText("🎨 Despill & Color Tuning active")

        elif key == "models":
            # 📦 Open AI Model Manager
            self.show_model_manager()

        elif key == "export":
            # 🚀 Scroll down to Deliver dock and focus Render button
            sizes = self.split.sizes()
            if sizes[2] <= 10:
                self.split.setSizes([sizes[0], max(400, sizes[1] - 150), 380])
            if hasattr(self, 'inspector_scroll'):
                self.inspector_scroll.ensureWidgetVisible(self.run_button)
            self.run_button.setFocus()
            self.status.setText("🚀 Deliver & Export dock focused")

    def _on_add_to_queue_clicked(self):
        self.run_all()

    # =========================================================================
    # Retranslate UI
    # =========================================================================
    def _refresh_combo(self, combo: QComboBox, items: list[tuple[str, any]]):
        if not hasattr(combo, 'count'):
            return
        curr = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for t, d in items:
            combo.addItem(t, d)
        idx = combo.findData(curr)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def retranslate_ui(self):
        """Update all UI widget texts dynamically to match current language."""
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} · {tr('window_title')}")
        self.lbl_title.setText("<span style='color:#38bdf8; font-weight:900;'>VFXEdu</span>&nbsp;&nbsp;<span style='color:#e5a93c; font-weight:800;'>CORRIDORKEY 2.0</span>")
        if hasattr(self, 'lbl_version'):
            self.lbl_version.setText(APP_VERSION)
        if hasattr(self, 'lbl_sub'):
            self.lbl_sub.setText("")
        self.lbl_lang.setText(tr('lbl_language'))
        self.btn_about.setText(tr('btn_about'))
        if hasattr(self, 'btn_proj_new'):
            self.btn_proj_new.setText(tr('btn_proj_new'))
            self.btn_proj_new.setToolTip(tr('btn_proj_new_tip'))
        if hasattr(self, 'btn_proj_open'):
            self.btn_proj_open.setText(tr('btn_proj_open'))
            self.btn_proj_open.setToolTip(tr('btn_proj_open_tip'))
        if hasattr(self, 'btn_proj_save'):
            self.btn_proj_save.setText(tr('btn_proj_save'))
            self.btn_proj_save.setToolTip(tr('btn_proj_save_tip'))
        self._update_window_title()
        self.btn_models.setText(tr('btn_models'))
        self.btn_models.setToolTip(tr('btn_models_tip'))

        # Tool Rail
        if hasattr(self, 'tool_rail'):
            self.tool_rail.retranslate()

        # Viewport Modes & Channel
        self.btn_view_single.setText(tr('wb_mode_single'))
        self.btn_view_wipe.setText(tr('wb_mode_wipe'))
        self.btn_view_side.setText(tr('wb_mode_side'))
        if hasattr(self, 'combo_channel'):
            self._refresh_combo(self.combo_channel, [
                (tr("wb_chan_composite"), "comp"),
                (tr("wb_chan_alpha"), "alpha"),
                (tr("wb_chan_orig"), "orig"),
            ])
        if hasattr(self, 'combo_zoom'):
            self._refresh_combo(self.combo_zoom, [
                (tr("wb_fit"), "fit"),
                (tr("wb_fit_100"), "100"),
                (tr("wb_fit_50"), "50"),
            ])

        # Media Bin & Queue
        self.grp_queue.setTitle(tr('grp_input'))
        self.lbl_media_bin.setText(tr('wb_media_bin'))
        self.btn_add_vid.setText(tr('wb_import'))
        self.btn_add_seq.setText(tr('btn_add_folder'))
        self.btn_remove_item.setText(tr('btn_remove'))
        if hasattr(self, 'btn_clear_q'):
            self.btn_clear_q.setToolTip(tr('btn_clear_queue'))
        if hasattr(self, 'lbl_queue_title'):
            self.lbl_queue_title.setText(tr('wb_queue'))
        if hasattr(self, 'queue_info') and (not self.current_source or self.proc.state() == QProcess.NotRunning):
            self.queue_info.setText(tr('wb_queue_empty'))

        # Telemetry Status Sections
        if hasattr(self, 'sec_left_status'):
            self.sec_left_status.setTitle(tr('wb_sec_status'))
        if hasattr(self, 'lbl_left_gpu_title'):
            self.lbl_left_gpu_title.setText(tr('wb_gpu_memory'))
        if hasattr(self, 'sec_insp_status'):
            self.sec_insp_status.setTitle(tr('wb_sec_status'))
        if hasattr(self, 'lbl_insp_gpu_title'):
            self.lbl_insp_gpu_title.setText(tr('wb_gpu_memory'))
        if hasattr(self, 'lbl_insp'):
            self.lbl_insp.setText(tr('wb_inspector'))

        # Section 1: Core & Memory
        self.sec_memory.setTitle(tr('wb_sec_memory'))
        self.chk_awareness.setText(tr('wb_awareness'))
        self.lbl_row_time_awareness.setText(tr('wb_time_awareness'))
        self.lbl_row_gpu_limit.setText(tr('wb_gpu_mem_limit'))
        self.low_vram.setText(tr('chk_low_vram'))
        self.low_vram.setToolTip(tr('chk_low_vram_tip'))
        if hasattr(self, 'lbl_row_hann'):
            self.lbl_row_hann.setText(tr('lbl_hann'))
        if hasattr(self, 'hann_mode'):
            self._refresh_combo(self.hann_mode, [
                (tr('hann_auto'), 'auto'),
                (tr('hann_80_40'), '80_40'),
                (tr('hann_48_24'), '48_24'),
                (tr('hann_24_12'), '24_12'),
                (tr('hann_8_4'), '8_4'),
                (tr('hann_1_1'), '1_1'),
                (tr('hann_custom'), 'custom'),
            ])
        if hasattr(self, 'lbl_row_custom_hann'):
            self.lbl_row_custom_hann.setText(tr('lbl_custom_hann'))
        if hasattr(self, 'lbl_row_model_scale'):
            self.lbl_row_model_scale.setText(tr('lbl_model_scale'))
        if hasattr(self, 'model_scale'):
            self.model_scale.setToolTip(tr('lbl_model_scale_tip'))
        if hasattr(self, 'lbl_row_stage2_batch'):
            self.lbl_row_stage2_batch.setText(tr('lbl_stage2_batch'))
        if hasattr(self, 'lbl_row_weights'):
            self.lbl_row_weights.setText(tr('lbl_weights'))
        if hasattr(self, 'weights_path'):
            self.weights_path.setPlaceholderText(tr('weights_placeholder'))

        # Section 2: Alpha Hint
        self.sec_hint.setTitle(tr('wb_sec_hint'))
        self.lbl_row_hint_file.setText(tr('lbl_hint_file'))
        self.hint.setPlaceholderText(tr('hint_placeholder'))
        self.btn_brush_main.setText(tr('btn_brush_editor'))
        self.btn_brush_main.setToolTip(tr('btn_brush_editor_tip'))
        if hasattr(self, 'lbl_row_hint_mode'):
            self.lbl_row_hint_mode.setText(tr('lbl_keying_mode'))
        if hasattr(self, 'hint_mode'):
            self._refresh_combo(self.hint_mode, [
                (tr('mode_no_hint'), ''),
                (tr('mode_first_frame'), '--hint_first_frame'),
                (tr('mode_video_hint'), '--hint_video'),
            ])
        if hasattr(self, 'lbl_exp_quality'):
            self.lbl_exp_quality.setText(tr('lbl_explicit_quality'))
        if hasattr(self, 'lbl_cry_quality'):
            self.lbl_cry_quality.setText(tr('lbl_carry_quality'))
        if hasattr(self, 'lbl_row_hint_quality'):
            self.lbl_row_hint_quality.setText(tr('lbl_hint_quality'))
        if hasattr(self, 'no_carry_hint'):
            self.no_carry_hint.setText(tr('chk_no_carry'))
            self.no_carry_hint.setToolTip(tr('chk_no_carry_tip'))

        # Section 3: Despill
        self.sec_despill.setTitle(tr('wb_sec_despill'))
        self.lbl_row_despill.setText(tr('lbl_despill'))

        # Section 4: Output & Deliver
        self.sec_out.setTitle(tr('wb_sec_output'))
        if hasattr(self, 'outputs'):
            for k, tr_k in [('alpha', 'out_alpha'), ('fg', 'out_fg'), ('checker', 'out_checker'), ('cutout', 'out_cutout')]:
                if k in self.outputs:
                    self.outputs[k].setText(tr(tr_k))
        if hasattr(self, 'cutout_linear'):
            self.cutout_linear.setText(tr('chk_cutout_linear'))
            self.cutout_linear.setToolTip(tr('chk_cutout_linear_tip'))
        if hasattr(self, 'lbl_row_num_frames'):
            self.lbl_row_num_frames.setText(tr('lbl_num_frames'))
        if hasattr(self, 'frames'):
            self.frames.setSpecialValueText(tr('special_all_frames'))
        if hasattr(self, 'lbl_row_start_mode'):
            self.lbl_row_start_mode.setText(tr('lbl_start_mode'))
        if hasattr(self, 'start'):
            self._refresh_combo(self.start, [
                (tr('start_begin'), 'begin'),
                (tr('start_middle'), 'middle'),
                (tr('start_random_middle'), 'random_middle'),
            ])
        if hasattr(self, 'lbl_row_seed'):
            self.lbl_row_seed.setText(tr('lbl_seed'))
        if hasattr(self, 'lbl_row_fps'):
            self.lbl_row_fps.setText(tr('lbl_fps'))
        if hasattr(self, 'linear'):
            self.linear.setText(tr('chk_linear'))
        if hasattr(self, 'lbl_row_codec'):
            self.lbl_row_codec.setText(tr('lbl_codec'))
        if hasattr(self, 'codec'):
            self._refresh_combo(self.codec, [
                (tr('codec_x264'), 'libx264'),
                (tr('codec_h264_nvenc'), 'h264_nvenc'),
                (tr('codec_hevc_nvenc'), 'hevc_nvenc'),
                (tr('codec_prores'), 'prores_ks'),
            ])
        if hasattr(self, 'lbl_crf_text'):
            self.lbl_crf_text.setText(tr('lbl_crf'))
        if hasattr(self, 'lbl_row_crf'):
            self.lbl_row_crf.setText(tr('lbl_crf_row'))
        if hasattr(self, 'lbl_row_pix_fmt'):
            self.lbl_row_pix_fmt.setText(tr('lbl_pix_fmt'))
        if hasattr(self, 'pix_fmt'):
            self._refresh_combo(self.pix_fmt, [
                (tr('pix_yuv444p10le'), 'yuv444p10le'),
                (tr('pix_yuv444p'), 'yuv444p'),
                (tr('pix_yuv420p'), 'yuv420p'),
            ])
        if hasattr(self, 'lbl_row_preset'):
            self.lbl_row_preset.setText(tr('lbl_preset'))
        if hasattr(self, 'lbl_row_bright'):
            self.lbl_row_bright.setText(tr('lbl_bright'))
        if hasattr(self, 'lbl_row_contrast'):
            self.lbl_row_contrast.setText(tr('lbl_contrast'))
        if hasattr(self, 'lbl_row_pivot'):
            self.lbl_row_pivot.setText(tr('lbl_pivot'))

        # Deliver Panel
        if hasattr(self, 'lbl_deliv_title'):
            self.lbl_deliv_title.setText(tr('wb_deliver'))
        self.lbl_row_output_dir.setText(tr('lbl_output_dir'))
        self.lbl_row_format.setText(tr('lbl_format'))
        if hasattr(self, 'format'):
            self._refresh_combo(self.format, [
                (tr('format_video'), 'video'),
                (tr('format_exr'), 'exr'),
            ])
        if hasattr(self, 'lbl_row_exr_dtype'):
            self.lbl_row_exr_dtype.setText(tr('lbl_exr_dtype'))
        if hasattr(self, 'exr_dtype'):
            self._refresh_combo(self.exr_dtype, [
                (tr('exr_half'), 'half'),
                (tr('exr_float'), 'float'),
            ])
        self.lbl_format_note.setText(tr('wb_format_note'))
        if hasattr(self, 'folder_btn'):
            self.folder_btn.setToolTip(tr('btn_open_folder'))

        # Browse buttons
        for btn in self.browse_buttons:
            btn.setText(tr('btn_browse'))

        if hasattr(self, 'btn_batch_render'):
            self.btn_batch_render.setText(tr('wb_btn_render_all'))
            self.btn_batch_render.setToolTip(tr('wb_btn_render_all_tip'))
        elif hasattr(self, 'btn_add_to_queue'):
            self.btn_add_to_queue.setText(tr('wb_btn_add_queue'))
        self.run_button.setText(tr('wb_btn_render'))
        self.run_button.setToolTip(tr('wb_btn_render_tip'))
        self.stop_button.setText("⏹ " + tr('btn_stop'))
        self.stop_button.setToolTip(tr('wb_btn_cancel_tip'))
        if hasattr(self, 'btn_live_stop'):
            self.btn_live_stop.setText("⏹ " + tr('btn_stop'))
            self.btn_live_stop.setToolTip(tr('wb_btn_cancel_tip'))

        if self.proc.state() == QProcess.NotRunning:
            self.status.setText(tr('status_ready'))
        self.lbl_lic_badge.setText(tr('license_badge'))
        if hasattr(self, 'lbl_deliver_vram'):
            self.update_deliver_vram_diagnosis()
        if hasattr(self, 'lbl_telemetry'):
            self.lbl_telemetry.setText(get_system_telemetry())

    def _on_language_changed(self, idx: int):
        lang = self.combo_lang.itemData(idx)
        if lang and lang != get_language():
            set_language(lang)
            self.retranslate_ui()

    # =========================================================================
    # Path & File Choosers
    # =========================================================================
    def path_row(self, field: QLineEdit, directory: bool = False, is_file: bool = False, is_hint: bool = False) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(field)

        btn = QPushButton(tr('btn_browse'))
        btn.setStyleSheet("background:#1a1e27; border:1px solid #2b3240; color:#8fa3bf; padding:3px 8px; border-radius:4px; font-size:11px;")
        self.browse_buttons.append(btn)

        def select():
            if directory:
                val = QFileDialog.getExistingDirectory(self, tr('dlg_select_out_dir'), field.text())
            elif is_hint:
                val, _ = QFileDialog.getOpenFileName(
                    self, tr('dlg_select_hint'), field.text(),
                    'Hints (*.png *.jpg *.jpeg *.exr *.mp4 *.mov *.avi *.webm);;Images (*.png *.exr);;Videos (*.mp4 *.mov)'
                )
            else:
                val, _ = QFileDialog.getOpenFileName(self, tr('dlg_select_file'), field.text(), 'All Files (*.*)')
            if val:
                field.setText(val)
        btn.clicked.connect(select)
        row.addWidget(btn)
        return widget

    def add_paths(self, paths: list[str]):
        existing = {self.queue.item(i).text() for i in range(self.queue.count())}
        added = []
        for path in paths:
            p = Path(path)
            if p.exists() and (p.is_dir() or p.suffix.lower() in VIDEO_EXTS) and str(p) not in existing:
                item = QListWidgetItem(str(p), self.queue)
                card = MediaCardWidget(p)
                # Ensure clicking anywhere on the card immediately selects the row smoothly
                card.clicked.connect(lambda p_path, it=item: self.queue.setCurrentItem(it))
                item.setSizeHint(card.sizeHint())
                self.queue.addItem(item)
                self.queue.setItemWidget(item, card)
                existing.add(str(p))
                added.append(p)

                # Extract metadata & filmstrip thumbnails ahead of time for instantaneous switching
                if p.is_file():
                    cap = cv2.VideoCapture(str(p))
                    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 24.0
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    res_str = "UHD" if w >= 3840 else ("FHD" if w >= 1920 else f"{w}x{h}")
                    ok, f0 = cap.read()
                    thumbs = []
                    f0_pix = None
                    f0_rgb = None
                    if ok and f0 is not None:
                        f0_rgb = cv2.cvtColor(f0, cv2.COLOR_BGR2RGB)
                        rgb_small = cv2.resize(f0_rgb, (96, 60))
                        q0 = QImage(rgb_small.data, 96, 60, rgb_small.strides[0], QImage.Format_RGB888).copy()
                        card.set_thumbnail_and_specs(QPixmap.fromImage(q0), n, res_str, fps)

                        f0_pix = QPixmap.fromImage(QImage(f0_rgb.data, w, h, f0_rgb.strides[0], QImage.Format_RGB888).copy())
                        rgb_thumb0 = cv2.resize(f0_rgb, (80, 45))
                        thumbs.append(QPixmap.fromImage(QImage(rgb_thumb0.data, 80, 45, rgb_thumb0.strides[0], QImage.Format_RGB888).copy()))

                        # Extract remaining 15 thumbnails across duration
                        if n > 1:
                            step = max(1, n // 16)
                            for idx in range(step, n, step)[:15]:
                                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                                ok_t, ft = cap.read()
                                if ok_t and ft is not None:
                                    rgbt = cv2.cvtColor(cv2.resize(ft, (80, 45)), cv2.COLOR_BGR2RGB)
                                    qt = QImage(rgbt.data, 80, 45, rgbt.strides[0], QImage.Format_RGB888).copy()
                                    thumbs.append(QPixmap.fromImage(qt))
                    cap.release()
                    self._clip_cache[str(p.resolve())] = {
                        'n_frames': n,
                        'fps': fps,
                        'w': w,
                        'h': h,
                        'thumbs': thumbs,
                        'f0_pix': f0_pix,
                        'f0_rgb': f0_rgb,
                    }

        if added:
            # Focus, preview, and load companion hint for the newly added clip
            new_idx = self.queue.count() - 1
            if self.queue.currentRow() == new_idx:
                self.preview_input(new_idx)
            else:
                self.queue.setCurrentRow(new_idx)

    def auto_detect_companion_hint(self, clip_path: Path):
        """Automatically find <clip>FrameHint.png or <clip>_AlphaHint.mp4."""
        f_hint = find_first_frame_hint(clip_path)
        if f_hint:
            self.hint_mode.setCurrentIndex(1)
            self.hint.setText(str(f_hint.resolve()))
            self.log.appendPlainText(tr('log_hint_companion_first', name=f_hint.name))
            return

        v_hint = find_alpha_hint_video(clip_path)
        if v_hint:
            self.hint_mode.setCurrentIndex(2)
            self.hint.setText(str(v_hint.resolve()))
            self.log.appendPlainText(tr('log_hint_companion_video', name=v_hint.name))
            return

        # No companion hint for this clip: reset hint cleanly
        self.hint_mode.setCurrentIndex(0)
        self.hint.setText("")

    def add_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr('dlg_select_videos'), '', 'Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)')
        if paths:
            self.add_paths(paths)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, tr('dlg_select_folder'))
        if path:
            self.add_paths([path])

    def remove_input(self):
        row = self.queue.currentRow()
        if row >= 0:
            self.queue.takeItem(row)
            if self.queue.count() > 0:
                new_row = min(row, self.queue.count() - 1)
                self.queue.setCurrentRow(new_row)
            else:
                self.clear_queue()

    def clear_queue(self):
        self._release_video_caps()
        self.queue.clear()
        self.current_clip_path = None
        self.lbl_active_clip.setText("")
        self.viewport.set_images(None, None, None)
        self.filmstrip.load_clip_metadata(0, 24.0, [])
        if hasattr(self, 'queue_info'):
            self.queue_info.setText(tr('wb_queue_empty'))
        if hasattr(self, 'lbl_deliver_vram'):
            self.update_deliver_vram_diagnosis()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])

    def preview_result(self, index: int):
        path = self.result_choice.itemData(index)
        if path:
            self.result.load(path)

    def show_about_dialog(self):
        dlg = AboutLicenseDialog(self)
        dlg.exec()

    def _check_updates_background(self):
        """Asynchronously check for updates without blocking UI."""
        self._update_worker = UpdateCheckWorker(APP_VERSION, self)
        self._update_worker.finished_signal.connect(self._on_background_update_checked)
        self._update_worker.start()

    def _on_background_update_checked(self, info: dict):
        self._last_update_info = info
        if info.get("update_available"):
            latest = info.get("latest_version", "")
            self.btn_update_badge.setText(f"✨ {latest}")
            self.btn_update_badge.setToolTip(
                f"{tr('updater_new_available_title')}: {latest}\n{tr('updater_btn_apply')}"
            )
            self.btn_update_badge.setVisible(True)

    def _on_update_badge_clicked(self):
        dlg = UpdateDialog(self, initial_info=self._last_update_info)
        dlg.exec()


    # =========================================================================
    # Brush Mask Editor Integration
    # =========================================================================
    def open_brush_editor(self):
        """Open interactive Brush Mask Editor on the current preview frame."""
        if self.original.current_rgb_frame is None:
            QMessageBox.warning(self, tr('msg_warn_title'), tr('msg_no_clip_for_brush'))
            return

        current_clip = self.current_clip_path or Path("clip")
        frame_rgb = self.original.current_rgb_frame
        hint_path = self.hint.text().strip() if self.hint.text().strip() else None

        output_dir = Path(self.output.text()).resolve() if self.output.text().strip() else (ROOT / 'outputs')
        output_dir.mkdir(parents=True, exist_ok=True)

        editor = BrushMaskEditorDialog(
            rgb_image=frame_rgb,
            clip_name=current_clip.name,
            initial_mask_path=hint_path,
            output_hint_dir=output_dir,
            parent=self,
        )

        def on_applied(saved_path: str):
            self.hint_mode.setCurrentIndex(1)
            self.hint.setText(saved_path)
            self.log.appendPlainText(tr('log_brush_applied', path=saved_path))

        editor.applied_hint.connect(on_applied)
        editor.exec()

    # =========================================================================
    # Dynamic Handlers & Options Builder
    # =========================================================================
    def _on_hint_mode_changed(self, idx: int):
        flag = self.hint_mode.itemData(idx)
        is_active = bool(flag)
        self.hint.setEnabled(is_active)
        self.quality.setEnabled(is_active)
        self.carry_quality.setEnabled(is_active)
        self.no_carry_hint.setEnabled(is_active)

    def _on_format_changed(self, idx: int):
        fmt = self.format.itemData(idx)
        is_exr = (fmt == 'exr')
        self.exr_dtype.setEnabled(is_exr)
        self.codec.setEnabled(not is_exr)
        self.crf.setEnabled(not is_exr)
        self.preset.setEnabled(not is_exr)
        self.pix_fmt.setEnabled(not is_exr)

    def _on_hann_mode_changed(self, idx: int):
        mode = self.hann_mode.itemData(idx)
        is_custom = (mode == 'custom')
        self.hann_chunk.setEnabled(is_custom)
        self.hann_stride.setEnabled(is_custom)

    def _on_codec_changed(self, idx: int):
        codec = self.codec.itemData(idx)
        if codec == 'h264_nvenc':
            if self.pix_fmt.currentData() == 'yuv444p10le':
                self.pix_fmt.setCurrentIndex(2)
        elif codec == 'libx264':
            self.pix_fmt.setCurrentIndex(0)

    def options(self) -> dict:
        outputs = [k for k, v in self.outputs.items() if v.isChecked()]
        return dict(
            outputs=outputs,
            format=self.format.currentData(),
            exr_dtype=self.exr_dtype.currentData(),
            despill=self.despill.value(),
            cutout_linear=self.cutout_linear.isChecked(),
            hint_mode=self.hint_mode.currentData(),
            hint=self.hint.text().strip(),
            quality=self.quality.value(),
            carry_hint_quality=self.carry_quality.value(),
            no_carry_hint=self.no_carry_hint.isChecked(),
            hann_mode=self.hann_mode.currentData(),
            hann_chunk=self.hann_chunk.value(),
            hann_stride=self.hann_stride.value(),
            low_vram=self.low_vram.isChecked(),
            model_scale=self.model_scale.value(),
            stage2_batch=self.stage2_batch.value(),
            weights=self.weights_path.text().strip(),
            frames=self.frames.value() or -1,
            start=self.start.currentData(),
            seed=self.seed.value(),
            fps=self.fps.value(),
            linear=self.linear.isChecked(),
            ffmpeg_codec=self.codec.currentData(),
            crf=self.crf.value(),
            preset=self.preset.currentData(),
            pix_fmt=self.pix_fmt.currentData(),
            ffmpeg_threads=2,
            linear_brightness=self.linear_bright.value(),
            linear_contrast=self.linear_contrast.value(),
            linear_contrast_pivot=self.linear_pivot.value(),
        )

    def busy(self, value: bool):
        if hasattr(self, 'btn_batch_render'):
            self.btn_batch_render.setEnabled(not value)
        self.btn_add_vid.setEnabled(not value)
        if hasattr(self, 'btn_clear_q'):
            self.btn_clear_q.setEnabled(not value)
        if hasattr(self, 'btn_remove_item'):
            self.btn_remove_item.setEnabled(not value)
        self.run_button.setEnabled(not value)
        self.stop_button.setEnabled(value)
        if hasattr(self, 'btn_live_stop'):
            self.btn_live_stop.setVisible(value)

        if value:
            if hasattr(self, 'console_drawer'):
                self.console_drawer.setVisible(True)
                self.log.setVisible(True)
                self.btn_toggle_drawer.setText("Hide Log ▼")
            if hasattr(self, 'progress'):
                self.progress.setRange(0, 100)
                self.progress.setValue(5)
            if hasattr(self, 'lbl_live_task'):
                self.lbl_live_task.setText("Process launching...")
        else:
            if hasattr(self, 'lbl_live_task'):
                self.lbl_live_task.setText("Ready")
            if hasattr(self, 'progress'):
                self.progress.setRange(0, 1)
                self.progress.setValue(1)

    def launch(self, args: list[str], mode: str):
        self.mode = mode
        self.decoder.reset()
        env = QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONUTF8', '1')
        env.insert('PYTHONIOENCODING', 'utf-8')
        env.insert('OPENCV_IO_ENABLE_OPENEXR', '1')
        env.insert('HF_HOME', str(ROOT / 'tmp' / 'huggingface'))
        self.proc.setProcessEnvironment(env)
        self.proc.setWorkingDirectory(str(ROOT))
        self.busy(True)
        interpreter = Path(sys.executable)
        if interpreter.name.lower() == 'pythonw.exe':
            interpreter = interpreter.with_name('python.exe')
        self.proc.start(str(interpreter), args)

    def set_options(self, opts: dict):
        """Restore all inspector and delivery UI widgets from an options dictionary."""
        if not opts:
            return
        # 1. Outputs
        outputs = set(opts.get("outputs", []))
        if outputs:
            for k, cb in self.outputs.items():
                cb.setChecked(k in outputs)

        # 2. Format & EXR dtype
        fmt = opts.get("format")
        if fmt is not None:
            idx = self.format.findData(fmt)
            if idx >= 0:
                self.format.setCurrentIndex(idx)
        exr_dt = opts.get("exr_dtype")
        if exr_dt is not None:
            idx = self.exr_dtype.findData(exr_dt)
            if idx >= 0:
                self.exr_dtype.setCurrentIndex(idx)

        # 3. Despill & Cutout linear
        if "despill" in opts:
            self.despill.setValue(float(opts["despill"]))
        if "cutout_linear" in opts:
            self.cutout_linear.setChecked(bool(opts["cutout_linear"]))

        # 4. Hints & Conditioning
        hint_m = opts.get("hint_mode")
        if hint_m is not None:
            idx = self.hint_mode.findData(hint_m)
            if idx >= 0:
                self.hint_mode.setCurrentIndex(idx)
        if "hint" in opts:
            self.hint.setText(str(opts["hint"]))
        if "quality" in opts:
            self.quality.setValue(float(opts["quality"]))
        if "carry_hint_quality" in opts:
            self.carry_quality.setValue(float(opts["carry_hint_quality"]))
        if "no_carry_hint" in opts:
            self.no_carry_hint.setChecked(bool(opts["no_carry_hint"]))

        # 5. Hann & VRAM
        hann_m = opts.get("hann_mode")
        if hann_m is not None:
            idx = self.hann_mode.findData(hann_m)
            if idx >= 0:
                self.hann_mode.setCurrentIndex(idx)
        if "hann_chunk" in opts:
            self.hann_chunk.setValue(int(opts["hann_chunk"]))
        if "hann_stride" in opts:
            self.hann_stride.setValue(int(opts["hann_stride"]))
        if "low_vram" in opts:
            self.low_vram.setChecked(bool(opts["low_vram"]))
        if "model_scale" in opts:
            self.model_scale.setValue(float(opts["model_scale"]))
        if "stage2_batch" in opts:
            self.stage2_batch.setValue(int(opts["stage2_batch"]))

        # 6. Frames, Start, Seed, FPS, Linear
        if "frames" in opts:
            self.frames.setValue(int(opts["frames"]))
        start_m = opts.get("start")
        if start_m is not None:
            idx = self.start.findData(start_m)
            if idx >= 0:
                self.start.setCurrentIndex(idx)
        if "seed" in opts:
            self.seed.setValue(int(opts["seed"]))
        if "fps" in opts:
            self.fps.setValue(float(opts["fps"]))
        if "linear" in opts:
            self.linear.setChecked(bool(opts["linear"]))

        # 7. Encoding
        codec = opts.get("ffmpeg_codec")
        if codec is not None:
            idx = self.codec.findData(codec)
            if idx >= 0:
                self.codec.setCurrentIndex(idx)
        if "crf" in opts:
            self.crf.setValue(int(opts["crf"]))
        preset = opts.get("preset")
        if preset is not None:
            idx = self.preset.findData(preset)
            if idx >= 0:
                self.preset.setCurrentIndex(idx)
        pix_fmt = opts.get("pix_fmt")
        if pix_fmt is not None:
            idx = self.pix_fmt.findData(pix_fmt)
            if idx >= 0:
                self.pix_fmt.setCurrentIndex(idx)

        # 8. Color
        if "linear_brightness" in opts:
            self.linear_bright.setValue(float(opts["linear_brightness"]))
        if "linear_contrast" in opts:
            self.linear_contrast.setValue(float(opts["linear_contrast"]))
        if "linear_contrast_pivot" in opts:
            self.linear_pivot.setValue(float(opts["linear_contrast_pivot"]))

    # =========================================================================
    # Project File Management (.ckproj)
    # =========================================================================
    def _update_window_title(self):
        title = f"{APP_NAME} {APP_VERSION} · {tr('window_title')}"
        if getattr(self, "current_project_path", None):
            title = f"{APP_NAME} - [{self.current_project_path.name}]"
        self.setWindowTitle(title)

    def new_project(self):
        """Create a new blank project, prompting if existing queue has items."""
        if self.queue.count() > 0:
            ret = QMessageBox.question(
                self,
                tr("proj_new_confirm_title"),
                tr("proj_new_confirm_msg"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if ret != QMessageBox.Yes:
                return

        self.clear_queue()
        self._clip_options.clear()
        self.current_project_path = None
        self._update_window_title()
        self.log.appendPlainText(tr("log_proj_new_created"))

    def save_project(self) -> bool:
        """Save current project. If not saved before, prompt for file path."""
        if not getattr(self, "current_project_path", None):
            return self.save_project_as()
        return self._write_project_file(self.current_project_path)

    def save_project_as(self) -> bool:
        """Prompt user for a .ckproj file path and save."""
        default_name = "Untitled.ckproj"
        if getattr(self, "current_project_path", None):
            default_name = self.current_project_path.name
        elif self.current_clip_path:
            default_name = f"{self.current_clip_path.stem}.ckproj"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("proj_save_dialog_title"),
            str(ROOT / default_name),
            "CorridorKey Project (*.ckproj);;All Files (*.*)"
        )
        if not file_path:
            return False

        p = Path(file_path)
        if p.suffix.lower() != ".ckproj":
            p = p.with_suffix(".ckproj")

        return self._write_project_file(p)

    def _write_project_file(self, target_path: Path) -> bool:
        try:
            # Sync current active clip options
            if self.current_clip_path:
                self._clip_options[str(self.current_clip_path.resolve())] = self.options()

            clips_data = []
            for i in range(self.queue.count()):
                item = self.queue.item(i)
                clip_p = Path(item.text())
                card = self.queue.itemWidget(item)
                status = card.status if isinstance(card, MediaCardWidget) else "READY"
                clip_key = str(clip_p.resolve())
                clip_opts = self._clip_options.get(clip_key, {})
                clips_data.append({
                    "path": str(clip_p),
                    "status": status,
                    "options": clip_opts
                })

            data = {
                "project_format": "corridorkey_project",
                "format_version": 1,
                "app_version": APP_VERSION,
                "saved_at": datetime.now().isoformat(),
                "output_dir": self.output.text().strip(),
                "current_clip": str(self.current_clip_path) if self.current_clip_path else None,
                "clips": clips_data,
            }

            target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self.current_project_path = target_path
            self._update_window_title()
            self.log.appendPlainText(tr("log_proj_saved", name=target_path.name))
            return True
        except Exception as e:
            QMessageBox.critical(self, tr("proj_error_title"), tr("proj_save_error_msg", err=str(e)))
            return False

    def open_project_dialog(self):
        """Prompt user for a .ckproj file to open."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("proj_open_dialog_title"),
            str(ROOT),
            "CorridorKey Project (*.ckproj);;JSON Files (*.json);;All Files (*.*)"
        )
        if not file_path:
            return
        self.open_project(Path(file_path))

    def open_project(self, project_path: Path) -> bool:
        try:
            if not project_path.is_file():
                raise FileNotFoundError(f"Project file not found: {project_path}")

            data = json.loads(project_path.read_text(encoding="utf-8"))
            if data.get("project_format") != "corridorkey_project" and "clips" not in data:
                raise ValueError(tr("proj_invalid_format"))

            # Clear current state
            self.clear_queue()
            self._clip_options.clear()

            # Restore output dir if present
            if data.get("output_dir"):
                self.output.setText(data["output_dir"])

            clips = data.get("clips", [])
            paths_to_add = []
            saved_options_map = {}
            missing_clips = []

            for c in clips:
                c_path_str = c.get("path")
                if not c_path_str:
                    continue
                cp = Path(c_path_str)
                # Handle relative paths relative to project file
                if not cp.is_absolute():
                    cp = (project_path.parent / cp).resolve()
                if cp.exists():
                    paths_to_add.append(str(cp))
                    if c.get("options"):
                        saved_options_map[str(cp.resolve())] = c["options"]
                else:
                    missing_clips.append(c_path_str)

            if paths_to_add:
                self.add_paths(paths_to_add)
                self._clip_options.update(saved_options_map)

                # Restore card statuses
                for i in range(self.queue.count()):
                    item = self.queue.item(i)
                    card = self.queue.itemWidget(item)
                    if isinstance(card, MediaCardWidget) and i < len(clips):
                        saved_status = clips[i].get("status", "READY")
                        if saved_status == "DONE":
                            card.set_status_done()
                        elif saved_status == "PROCESSING":
                            card.set_status_processing()

            # Select active clip
            cur_clip = data.get("current_clip")
            if cur_clip:
                cur_p = Path(cur_clip)
                for i in range(self.queue.count()):
                    if Path(self.queue.item(i).text()).resolve() == cur_p.resolve():
                        self.queue.setCurrentRow(i)
                        break

            # Restore active clip options
            if self.current_clip_path and str(self.current_clip_path.resolve()) in self._clip_options:
                self.set_options(self._clip_options[str(self.current_clip_path.resolve())])

            self.current_project_path = project_path
            self._update_window_title()
            self.log.appendPlainText(tr("log_proj_loaded", name=project_path.name, count=len(paths_to_add)))

            if missing_clips:
                QMessageBox.warning(
                    self,
                    tr("proj_missing_clips_title"),
                    tr("proj_missing_clips_msg", clips="\n• ".join(missing_clips[:5]))
                )
            return True
        except Exception as e:
            QMessageBox.critical(self, tr("proj_error_title"), tr("proj_open_error_msg", err=str(e)))
            return False

    def _validate_run_prerequisites(self) -> bool:
        if not self.queue.count():
            raise ValueError(tr('msg_error_input_required'))
        if not self.output.text().strip():
            raise ValueError(tr('msg_error_output_required'))

        missing_req = get_missing_required_models(ROOT)
        if missing_req:
            ret = QMessageBox.question(
                self,
                tr('prompt_missing_req_title'),
                tr('prompt_missing_req_msg', models='\n'.join(f'• {m}' for m in missing_req)),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if ret == QMessageBox.Yes:
                self.show_model_manager(initial_target='required')
            return False
        return True

    def run(self):
        """Render the active clip currently previewed and edited in the Viewport."""
        try:
            if not self._validate_run_prerequisites():
                return

            row = self.queue.currentRow()
            if row < 0 and self.queue.count() > 0:
                row = 0
                self.queue.setCurrentRow(0)

            if row < 0 or row >= self.queue.count():
                raise ValueError(tr('msg_error_input_required'))

            source = Path(self.queue.item(row).text())
            opts = self.options()
            dest = Path(self.output.text()).resolve() / (
                source.stem + '_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
            )
            args = make_arguments(source, dest, opts)

            self.jobs = [(source, dest, args, opts)]
            self.total = 1
            self.cancelled = False
            if hasattr(self, 'queue_info'):
                self.queue_info.setText(tr('wb_queue_rendering_active', name=source.name))
            self.next_job()
        except Exception as exc:
            QMessageBox.warning(self, tr('msg_config_check'), str(exc))

    def run_all(self):
        """Batch render all clips in the Media Bin sequentially."""
        try:
            if not self._validate_run_prerequisites():
                return

            base_opts = self.options()
            active_hint = base_opts.get('hint', '')

            # Check if active hint is clip-specific
            if base_opts.get('hint_mode') and self.queue.count() > 1 and active_hint:
                f_comp = find_first_frame_hint(self.current_clip_path) if self.current_clip_path else None
                v_comp = find_alpha_hint_video(self.current_clip_path) if self.current_clip_path else None
                is_companion = (
                    (f_comp and str(f_comp.resolve()) == active_hint) or
                    (v_comp and str(v_comp.resolve()) == active_hint)
                )
                if not is_companion:
                    ret = QMessageBox.question(
                        self,
                        tr('msg_warn_title'),
                        tr('msg_hint_batch_warn'),
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if ret != QMessageBox.Yes:
                        return

            jobs = []
            for i in range(self.queue.count()):
                source = Path(self.queue.item(i).text())
                clip_opts = dict(base_opts)

                # For batch processing, auto-bind companion hint for each clip if not fixed
                f_hint = find_first_frame_hint(source)
                v_hint = find_alpha_hint_video(source)
                if f_hint:
                    clip_opts['hint_mode'] = '--hint_first_frame'
                    clip_opts['hint'] = str(f_hint.resolve())
                elif v_hint:
                    clip_opts['hint_mode'] = '--hint_alpha_video'
                    clip_opts['hint'] = str(v_hint.resolve())
                else:
                    clip_opts['hint_mode'] = ''
                    clip_opts['hint'] = ''

                dest = Path(self.output.text()).resolve() / (
                    source.stem + '_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
                )
                args = make_arguments(source, dest, clip_opts)
                jobs.append((source, dest, args, clip_opts))

            self.jobs = jobs
            self.total = len(jobs)
            self.cancelled = False
            if hasattr(self, 'queue_info') and jobs:
                self.queue_info.setText(tr('wb_queue_rendering_batch', current=1, total=self.total, name=jobs[0][0].name))
            self.next_job()
        except Exception as exc:
            QMessageBox.warning(self, tr('msg_config_check'), str(exc))

    def next_job(self):
        source, self.destination, args, self.current_opts = self.jobs.pop(0)
        self.current_source = source

        # Synchronize UI selection, Viewport, and Filmstrip to this source clip
        for i in range(self.queue.count()):
            item = self.queue.item(i)
            if Path(item.text()).resolve() == source.resolve():
                if self.queue.currentRow() != i:
                    self.queue.blockSignals(True)
                    self.queue.setCurrentRow(i)
                    self.preview_input(i)
                    self.queue.blockSignals(False)
                card = self.queue.itemWidget(item)
                if isinstance(card, MediaCardWidget):
                    card.set_status("PROCESSING")
                break

        try:
            self.destination.mkdir(parents=True, exist_ok=False)
            (self.destination / 'gui_job.json').write_text(
                json.dumps({'input': str(source), 'arguments': args}, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except OSError as exc:
            self.jobs.clear()
            self.busy(False)
            self.status.setText(tr('status_mkdir_failed', err=str(exc)))
            return

        current_idx = self.total - len(self.jobs)
        self.status.setText(tr('status_processing', current=current_idx, total=self.total, name=source.name))
        if hasattr(self, 'queue_info'):
            if self.total > 1:
                self.queue_info.setText(tr('wb_queue_rendering_batch', current=current_idx, total=self.total, name=source.name))
            else:
                self.queue_info.setText(tr('wb_queue_rendering_active', name=source.name))
        self.log.appendPlainText(tr('log_job_start', name=source.name, src=source, dst=self.destination))
        self.launch(args, 'inference')

    def check_environment(self):
        self.cancelled = False
        self.status.setText(tr('status_checking_env'))
        self.launch(['-u', str(ROOT / 'desktop_check.py')], 'check')

    def download(self):
        self.show_model_manager()

    def show_model_manager(self, initial_target: str | None = None):
        dlg = ModelManagerDialog(self, initial_target=initial_target)
        dlg.exec()

    def read_log(self):
        text = self.decoder.decode(bytes(self.proc.readAllStandardOutput()))
        text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text).replace('\r', '\n')
        if text:
            self.log.appendPlainText(text.rstrip())
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

            # Real-time progress detection
            for raw_line in text.split('\n'):
                line = raw_line.strip()
                if not line:
                    continue

                # 1. Hann Window progress: "window 2/5 [24:72]"
                m_hann = re.search(r'window\s+(\d+)/(\d+)', line)
                if m_hann:
                    curr, total = int(m_hann.group(1)), int(m_hann.group(2))
                    pct = int((curr / max(1, total)) * 100)
                    self.progress.setRange(0, 100)
                    self.progress.setValue(pct)
                    status_msg = f"Window {curr}/{total} ({pct}%)"
                    self.status.setText(f"⏳ {status_msg}")
                    if hasattr(self, 'lbl_live_task'):
                        self.lbl_live_task.setText(f"Hann Stage 1: {status_msg}")
                    if hasattr(self, 'queue_info') and self.current_source:
                        self.queue_info.setText(f"▶ {self.current_source.name}: {status_msg}")

            if self.mode == 'inference' and self.destination:
                try:
                    with (self.destination / 'desktop.log').open('a', encoding='utf-8') as stream:
                        stream.write(text)
                except OSError:
                    pass

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.jobs.clear()
            self.busy(False)
            self.status.setText(tr('status_proc_start_failed', err=self.proc.errorString()))

    def finished(self, code, exit_status):
        self.read_log()
        if self.cancelled:
            self.jobs.clear()
            if self.current_source:
                for i in range(self.queue.count()):
                    item = self.queue.item(i)
                    if Path(item.text()).resolve() == self.current_source.resolve():
                        card = self.queue.itemWidget(item)
                        if isinstance(card, MediaCardWidget):
                            card.set_status("READY")
                        break
            self.status.setText(tr('status_stopped'))
            self.busy(False)
            return

        if code != 0 or exit_status != QProcess.NormalExit:
            if self.current_source:
                for i in range(self.queue.count()):
                    item = self.queue.item(i)
                    if Path(item.text()).resolve() == self.current_source.resolve():
                        card = self.queue.itemWidget(item)
                        if isinstance(card, MediaCardWidget):
                            card.set_status("READY")
                        break
            self.jobs.clear()
            self.busy(False)
            self.status.setText(tr('status_failed', code=code))
            return

        # Mark processed clip as DONE
        if self.current_source:
            for i in range(self.queue.count()):
                item = self.queue.item(i)
                if Path(item.text()).resolve() == self.current_source.resolve():
                    card = self.queue.itemWidget(item)
                    if isinstance(card, MediaCardWidget):
                        card.set_status("DONE")
                    break

        if self.destination:
            for path in sorted(self.destination.iterdir()):
                if path.suffix.lower() in VIDEO_EXTS or (path.is_dir() and any(path.glob('*.exr'))):
                    entry = f'{self.destination.name} / {path.name}'
                    if self.result_choice.findText(entry) < 0:
                        self.result_choice.addItem(entry, str(path))
            if self.result_choice.count():
                self.result_choice.setCurrentIndex(self.result_choice.count() - 1)
            # Re-detect results for active source clip
            if self.current_source:
                self._detect_matched_results(self.current_source)
                self.show_frame_in_viewport(self.filmstrip.current_frame)

            if self.jobs:
                self.next_job()
                return

        self.busy(False)
        self.progress.setValue(1)
        self.status.setText({
            'inference': tr('status_done'),
            'download': tr('status_download_done'),
            'check': tr('status_check_passed'),
        }.get(self.mode, tr('status_done')))
        if hasattr(self, 'queue_info') and self.current_source:
            self.queue_info.setText(tr('wb_queue_ready_active', name=self.current_source.name))

    def stop(self):
        self.cancelled = True
        self.jobs.clear()
        if self.current_source:
            for i in range(self.queue.count()):
                item = self.queue.item(i)
                if Path(item.text()).resolve() == self.current_source.resolve():
                    card = self.queue.itemWidget(item)
                    if isinstance(card, MediaCardWidget):
                        card.set_status("READY")
                    break
        self.status.setText(tr('status_stopping'))
        if hasattr(self, 'lbl_live_task'):
            self.lbl_live_task.setText("Stopping...")

        pid = self.proc.processId()
        if pid and pid > 0 and os.name == 'nt':
            try:
                import subprocess
                subprocess.run(
                    ['taskkill', '/PID', str(pid), '/T', '/F'],
                    capture_output=True,
                    timeout=5,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
                )
            except Exception as exc:
                self.log.appendPlainText(f"[WARN] taskkill exception: {exc}")

        if self.proc.state() != QProcess.NotRunning:
            self.proc.kill()
            self.proc.waitForFinished(1000)

        # Immediate clean exit to idle state
        self.busy(False)
        self.status.setText(tr('status_stopped'))
        if hasattr(self, 'lbl_live_task'):
            self.lbl_live_task.setText("Stopped")
        if hasattr(self, 'queue_info') and self.current_source:
            self.queue_info.setText(tr('wb_queue_ready_active', name=self.current_source.name))
        self.log.appendPlainText(tr('status_stopped'))

    def kill_finished(self, code, status):
        self.busy(False)

    def open_output(self):
        path = self.destination or Path(self.output.text())
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event):
        if self.proc.state() != QProcess.NotRunning or self.killer.state() != QProcess.NotRunning:
            QMessageBox.information(self, tr('msg_running_title'), tr('msg_running_text'))
            event.ignore()
        else:
            self._release_video_caps()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    font_file = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'malgun.ttf'
    if font_file.is_file():
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 9))

    # Dark Studio Workstation Palette
    app.setStyleSheet('''
        QWidget {
            background-color: #12141a;
            color: #dbe3ee;
            font-size: 11px;
            font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
        }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
            background-color: #0f1116;
            border: 1px solid #242936;
            border-radius: 4px;
            padding: 4px 6px;
            color: #c9d1d9;
        }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
            border: 1px solid #e5a93c;
        }
        QPushButton {
            background-color: #181c25;
            border: 1px solid #282f3d;
            border-radius: 4px;
            padding: 6px 12px;
            color: #c9d1d9;
        }
        QPushButton:hover {
            background-color: #232936;
            border-color: #e5a93c;
            color: #f5b642;
        }
        QPushButton:disabled {
            color: #556070;
            background-color: #12141a;
            border-color: #1c202a;
        }
        QSlider::groove:horizontal {
            height: 4px;
            background: #232835;
            border-radius: 2px;
        }
        QSlider::sub-page:horizontal {
            background: #e5a93c;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            width: 12px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 6px;
            background: #f5b642;
        }
        QCheckBox {
            spacing: 6px;
            color: #c9d1d9;
        }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            background: #0f1116;
            border: 1px solid #282d3b;
            border-radius: 3px;
        }
        QCheckBox::indicator:checked {
            background: #e5a93c;
            border-color: #f5b642;
        }
    ''')

    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
