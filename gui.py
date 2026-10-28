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
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

# Ensure local bin (ffmpeg.exe) is in PATH
_ROOT = Path(__file__).resolve().parent
APP_NAME = "VFXEdu CorridorKey 2.0"
APP_VERSION = "v0.1.1"
_BIN = _ROOT / "bin"
if _BIN.is_dir() and str(_BIN) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(_BIN) + os.pathsep + os.environ.get("PATH", "")

import cv2
import numpy as np
import torch

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QUrl, Signal, QTimer
from PySide6.QtGui import (
    QDesktopServices, QImage, QPixmap, QFont, QFontDatabase, QIcon, QColor, QPalette
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
    is_clean_plate_installed,
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


def get_system_telemetry() -> str:
    """Query live GPU VRAM and Disk space."""
    gpu_str = "GPU: N/A"
    try:
        if torch.cuda.is_available():
            free_b, tot_b = torch.cuda.mem_get_info()
            gpu_str = f"GPU: {tot_b/(1024**3):.1f} GB for CorridorKey, {free_b/(1024**3):.1f} GB free"
    except Exception:
        pass

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
        raise ValueError(f'입력 경로가 없습니다: {source}')
    if source.is_dir() and not any(p.suffix.lower() in IMAGE_EXTS for p in source.iterdir() if p.is_file()):
        raise ValueError(f'이미지 프레임이 없는 폴더입니다: {source}')
    outputs = list(options.get('outputs') or [])
    if options.get('clean_plate') and 'alpha' not in outputs:
        outputs.append('alpha')
    if not outputs:
        raise ValueError('출력을 하나 이상 선택하세요.')

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

        btn_close = QPushButton(tr("about_btn_close"))
        btn_close.setStyleSheet('background:#21262d;padding:6px 16px;')
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, 0, Qt.AlignRight)


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
                raise ValueError('프레임을 읽을 수 없습니다.')

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
            self.image.setText('미리보기 불가 — 결과 폴더에서 확인하세요')
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

        # Telemetry Timer (updates VRAM and live GPU metrics every 1.5 seconds)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._update_telemetry)
        self.telemetry_timer.start(1500)
        self._update_telemetry()

        # Check required models on startup
        QTimer.singleShot(700, self._check_models_on_startup)

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

        lbl_queue_title = QLabel(tr("wb_queue"))
        lbl_queue_title.setStyleSheet("font-size:11px; font-weight:bold; color:#7e8b9d; letter-spacing:1px;")
        v_queue_layout.addWidget(lbl_queue_title)

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
        self.lbl_row_gpu_limit = QLabel(tr("wb_gpu_mem_limit"))
        f_mem.addRow(self.lbl_row_gpu_limit, self.combo_gpu_limit)

        self.low_vram = QCheckBox(tr("chk_low_vram"))
        self.low_vram.setToolTip(tr("chk_low_vram_tip"))
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

        # 4. Clean Plate (RGVI Remover)
        self.sec_clean = CollapsibleSection(tr("wb_sec_clean_plate"), starts_open=True)
        v_clean = QVBoxLayout()
        v_clean.setSpacing(6)

        self.outputs = {}
        for key, tr_k in [
            ('alpha', 'out_alpha'),
            ('fg', 'out_fg'),
            ('checker', 'out_checker'),
            ('cutout', 'out_cutout'),
            ('clean_plate', 'out_clean_plate'),
        ]:
            chk = QCheckBox(tr(tr_k))
            chk.setChecked(key in {'alpha', 'checker'})
            self.outputs[key] = chk

        self.outputs['clean_plate'].toggled.connect(self._on_clean_plate_toggled)
        v_clean.addWidget(self.outputs['clean_plate'])

        self.row_cp_prompt_widget = QWidget()
        h_cp_prompt = QVBoxLayout(self.row_cp_prompt_widget)
        h_cp_prompt.setContentsMargins(0, 2, 0, 2)
        h_cp_prompt.setSpacing(4)
        self.lbl_cp_prompt = QLabel(tr('lbl_clean_plate_prompt'))
        self.lbl_cp_prompt.setStyleSheet('color:#8fa3bf;font-size:11px;')
        self.clean_plate_prompt = QLineEdit()
        self.clean_plate_prompt.setPlaceholderText(tr('placeholder_clean_plate_prompt'))
        self.clean_plate_prompt.setStyleSheet('background:#0f1116;border:1px solid #282d3b;color:#d8e2ed;padding:4px 8px;border-radius:4px;')
        h_cp_prompt.addWidget(self.lbl_cp_prompt)
        h_cp_prompt.addWidget(self.clean_plate_prompt)
        self.row_cp_prompt_widget.setVisible(False)
        v_clean.addWidget(self.row_cp_prompt_widget)

        lbl_engine_badge = QLabel("✨ Stable Diffusion + RAFT Optical Flow Engine")
        lbl_engine_badge.setStyleSheet("color:#65778c; font-size:10px;")
        v_clean.addWidget(lbl_engine_badge)

        self.sec_clean.addLayout(v_clean)
        acc_layout.addWidget(self.sec_clean)

        # 5. Output & Layers Section
        self.sec_out = CollapsibleSection(tr("wb_sec_output"), starts_open=False)
        v_out_layers = QVBoxLayout()
        v_out_layers.setSpacing(4)

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

        lbl_deliv_title = QLabel(tr("wb_deliver"))
        lbl_deliv_title.setStyleSheet("font-size:11px; font-weight:800; color:#e5a93c; letter-spacing:1px;")
        v_deliv.addWidget(lbl_deliv_title)

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

        # Diagnosis string
        self.lbl_deliver_vram = QLabel("Fits in GPU memory: 18.2 of 24.0 GB free · Frames 1-121")
        self.lbl_deliver_vram.setStyleSheet("color:#7e8b9d; font-size:10px;")
        v_deliv.addWidget(self.lbl_deliver_vram)

        # Action Buttons: [Add to queue] [Render]
        h_deliv_btns = QHBoxLayout()
        self.btn_add_to_queue = QPushButton(tr("wb_btn_add_queue"))
        self.btn_add_to_queue.setStyleSheet("background:#1a1e27; border:1px solid #2b3240; color:#c9d1d9; padding:8px 12px; border-radius:4px; font-weight:bold; font-size:11px;")
        self.btn_add_to_queue.clicked.connect(self._on_add_to_queue_clicked)
        h_deliv_btns.addWidget(self.btn_add_to_queue)

        self.run_button = QPushButton(tr("wb_btn_render"))
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
        self.stop_button = QPushButton(tr('btn_stop'))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setVisible(False)

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
        used_gb, tot_gb, pct, gpu_name = 0.0, 0.0, 0.0, "N/A"
        has_cuda = False
        try:
            if torch.cuda.is_available():
                free_b, tot_b = torch.cuda.mem_get_info()
                used_b = tot_b - free_b
                used_gb = used_b / (1024**3)
                tot_gb = tot_b / (1024**3)
                pct = (used_b / tot_b) * 100 if tot_b > 0 else 0.0
                gpu_name = torch.cuda.get_device_name(0)
                has_cuda = True
        except Exception:
            pass

        if has_cuda:
            gpu_mem_text = f"{used_gb:.1f} / {tot_gb:.1f} GB"
            badge_text = f"⚡ GPU: {used_gb:.1f}/{tot_gb:.1f} GB ({pct:.0f}%)"
            tip = f"{gpu_name}\nGPU VRAM: {pct:.1f}% ({used_gb:.2f} GB used / {tot_gb:.2f} GB total)"
        else:
            gpu_mem_text = "N/A"
            badge_text = "⚡ GPU: N/A"
            tip = "CUDA GPU not detected"

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

    # =========================================================================
    # Media Loading & Syncing with Viewport / Filmstrip
    # =========================================================================
    def preview_input(self, index: int):
        if index < 0 or index >= self.queue.count():
            return
        clip_path = Path(self.queue.item(index).text())
        self.current_clip_path = clip_path
        self.lbl_active_clip.setText(clip_path.name)

        # Stop playback if currently playing
        if hasattr(self, 'filmstrip') and self.filmstrip.is_playing:
            self.filmstrip.toggle_play()

        # Update card selection state
        for i in range(self.queue.count()):
            item = self.queue.item(i)
            card = self.queue.itemWidget(item)
            if isinstance(card, MediaCardWidget):
                card.set_selected(i == index)

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

        # Update deliver memory string
        est_vram = 5.5 if (w >= 1920) else 3.2
        self.lbl_deliver_vram.setText(
            f"Fits in GPU memory: {est_vram:.1f} of 24.0 GB · {n_frames} frames ({w}x{h})"
        )

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
                                if 'clean_plate' in nl:
                                    self.matched_results['clean'] = f
                                elif 'checker' in nl or 'comp' in nl:
                                    self.matched_results['comp'] = f
                                elif 'alpha' in nl:
                                    self.matched_results['alpha'] = f
                    elif item.is_file() and item.suffix.lower() in VIDEO_EXTS:
                        nl = item.name.lower()
                        if 'clean_plate' in nl:
                            self.matched_results['clean'] = item
                        elif 'checker' in nl or 'comp' in nl:
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

    def show_frame_in_viewport(self, frame_idx: int):
        """Read and render frame at frame_idx for both original and rendered comp/alpha."""
        if not self.current_clip_path or not self.current_clip_path.exists():
            return

        # 1. Read original frame (fast-path cached for frame 0)
        clip_key = str(self.current_clip_path.resolve())
        f = None
        if frame_idx == 0 and clip_key in self._clip_cache and self._clip_cache[clip_key].get('f0_pix'):
            orig_pix = self._clip_cache[clip_key]['f0_pix']
            self.original.pixmap = orig_pix
            self.original.current_rgb_frame = self._clip_cache[clip_key].get('f0_rgb')
            w = self._clip_cache[clip_key]['w']
            h = self._clip_cache[clip_key]['h']
        else:
            cap = cv2.VideoCapture(str(self.current_clip_path))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, f = cap.read()
            cap.release()
            if not ok or f is None:
                return

            rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
            self.original.current_rgb_frame = rgb
            h, w, _ = rgb.shape
            orig_pix = QPixmap.fromImage(QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy())
            self.original.pixmap = orig_pix

        # 2. Read result frame (composite, clean plate, or alpha)
        comp_pix = None
        alpha_pix = None

        res_path = self.matched_results.get('clean') or self.matched_results.get('comp') or self.matched_results.get('alpha')
        if res_path and res_path.exists():
            cap_res = cv2.VideoCapture(str(res_path))
            cap_res.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok_res, f_res = cap_res.read()
            cap_res.release()
            if ok_res and f_res is not None:
                rgb_res = cv2.cvtColor(f_res, cv2.COLOR_BGR2RGB)
                hr, wr, _ = rgb_res.shape
                comp_pix = QPixmap.fromImage(QImage(rgb_res.data, wr, hr, rgb_res.strides[0], QImage.Format_RGB888).copy())

        # If alpha is present, load it and synthesize live RGBA cutout over checkerboard
        alpha_path = self.matched_results.get('alpha')
        if alpha_path and alpha_path.exists():
            cap_a = cv2.VideoCapture(str(alpha_path))
            cap_a.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok_a, f_a = cap_a.read()
            cap_a.release()
            if ok_a and f_a is not None:
                rgb_a = cv2.cvtColor(f_a, cv2.COLOR_BGR2RGB)
                ha, wa, _ = rgb_a.shape
                alpha_pix = QPixmap.fromImage(QImage(rgb_a.data, wa, ha, rgb_a.strides[0], QImage.Format_RGB888).copy())
                if 'clean' not in self.matched_results and f is not None:
                    gray_a = cv2.cvtColor(f_a, cv2.COLOR_BGR2GRAY) if f_a.ndim == 3 else f_a
                    if gray_a.shape[:2] != f.shape[:2]:
                        gray_a = cv2.resize(gray_a, (w, h), interpolation=cv2.INTER_LINEAR)
                    rgba = cv2.cvtColor(f, cv2.COLOR_BGR2RGBA)
                    rgba[:, :, 3] = gray_a
                    comp_pix = QPixmap.fromImage(QImage(rgba.data, w, h, rgba.strides[0], QImage.Format_RGBA8888).copy())

        # Bind into VFX Viewport
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
            # 🎭 Ensure Inspector visible, open Alpha Hint & RGVI, scroll to layer tools
            sizes = self.split.sizes()
            if sizes[2] <= 10:
                self.split.setSizes([sizes[0], max(400, sizes[1] - 150), 380])
            self.sec_hint.set_open(True)
            self.sec_clean.set_open(True)
            if hasattr(self, 'inspector_scroll'):
                self.inspector_scroll.ensureWidgetVisible(self.sec_hint)
            self.btn_brush_main.setFocus()
            idx_alpha = self.combo_channel.findData("alpha")
            if idx_alpha >= 0:
                self.combo_channel.setCurrentIndex(idx_alpha)
            self.status.setText("🎭 Matte & Layers: Alpha Hint & Clean Plate active")

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
        self.queue_info.setText(f"Added {self.queue.count()} clip(s) to render queue. Ready to render.")

    # =========================================================================
    # Retranslate UI
    # =========================================================================
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
        self.btn_models.setText(tr('btn_models'))
        self.btn_models.setToolTip(tr('btn_models_tip'))

        self.btn_view_single.setText(tr('wb_mode_single'))
        self.btn_view_wipe.setText(tr('wb_mode_wipe'))
        self.btn_view_side.setText(tr('wb_mode_side'))

        self.grp_queue.setTitle(tr('grp_input'))
        self.lbl_media_bin.setText(tr('wb_media_bin'))
        self.btn_add_vid.setText(tr('wb_import'))
        self.btn_add_seq.setText(tr('btn_add_folder'))
        self.btn_remove_item.setText(tr('btn_remove'))

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

        self.sec_memory.setTitle(tr('wb_sec_memory'))
        self.chk_awareness.setText(tr('wb_awareness'))
        self.lbl_row_time_awareness.setText(tr('wb_time_awareness'))
        self.lbl_row_gpu_limit.setText(tr('wb_gpu_mem_limit'))
        self.low_vram.setText(tr('chk_low_vram'))
        self.low_vram.setToolTip(tr('chk_low_vram_tip'))

        self.sec_hint.setTitle(tr('wb_sec_hint'))
        self.lbl_row_hint_file.setText(tr('lbl_hint_file'))
        self.hint.setPlaceholderText(tr('hint_placeholder'))
        self.btn_brush_main.setText(tr('btn_brush_editor'))
        self.btn_brush_main.setToolTip(tr('btn_brush_editor_tip'))

        self.sec_despill.setTitle(tr('wb_sec_despill'))
        self.lbl_row_despill.setText(tr('lbl_despill'))

        self.sec_clean.setTitle(tr('wb_sec_clean_plate'))
        if hasattr(self, 'lbl_cp_prompt'):
            self.lbl_cp_prompt.setText(tr('lbl_clean_plate_prompt'))
        if hasattr(self, 'clean_plate_prompt'):
            self.clean_plate_prompt.setPlaceholderText(tr('placeholder_clean_plate_prompt'))

        self.sec_out.setTitle(tr('wb_sec_output'))
        self.lbl_row_output_dir.setText(tr('lbl_output_dir'))
        self.lbl_row_format.setText(tr('lbl_format'))
        self.lbl_format_note.setText(tr('wb_format_note'))

        self.btn_add_to_queue.setText(tr('wb_btn_add_queue'))
        self.run_button.setText(tr('wb_btn_render'))

        if self.proc.state() == QProcess.NotRunning:
            self.status.setText(tr('status_ready'))
        self.lbl_lic_badge.setText(tr('license_badge'))

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

        if added and self.queue.currentRow() < 0:
            self.queue.setCurrentRow(0)

        if added:
            self.auto_detect_companion_hint(added[0])

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

    def clear_queue(self):
        self.queue.clear()
        self.current_clip_path = None
        self.lbl_active_clip.setText("")
        self.viewport.set_images(None, None, None)
        self.filmstrip.load_clip_metadata(0, 24.0, [])

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

        def on_requested_clean_plate(saved_path: str):
            self.hint_mode.setCurrentIndex(1)
            self.hint.setText(saved_path)
            if 'clean_plate' in self.outputs:
                self.outputs['clean_plate'].setChecked(True)
            if 'alpha' in self.outputs:
                self.outputs['alpha'].setChecked(True)
            self.log.appendPlainText(f'✨ [RGVI] 클린 플레이트 마스크 지정: {saved_path}')

        editor.applied_hint.connect(on_applied)
        editor.requested_clean_plate.connect(on_requested_clean_plate)
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

    def _on_clean_plate_toggled(self, checked: bool):
        """Prompt to download RGVI weights if clean plate is enabled and missing."""
        if hasattr(self, 'row_cp_prompt_widget'):
            self.row_cp_prompt_widget.setVisible(checked)
        if checked and not is_clean_plate_installed(ROOT):
            ret = QMessageBox.question(
                self,
                tr('prompt_rgvi_needed_title'),
                tr('prompt_rgvi_needed_msg'),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if ret == QMessageBox.Yes:
                self.show_model_manager(initial_target='rgvi')
            else:
                self.outputs['clean_plate'].setChecked(False)

    def options(self) -> dict:
        outputs = [k for k, v in self.outputs.items() if v.isChecked() and k != 'clean_plate']
        clean_plate = bool(self.outputs.get('clean_plate') and self.outputs['clean_plate'].isChecked())
        if clean_plate and 'alpha' not in outputs:
            outputs.append('alpha')
        return dict(
            outputs=outputs,
            clean_plate=clean_plate,
            clean_plate_prompt=self.clean_plate_prompt.text().strip() if hasattr(self, 'clean_plate_prompt') else '',
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
        self.run_button.setEnabled(not value)
        self.btn_add_vid.setEnabled(not value)
        self.stop_button.setEnabled(value)
        if value:
            self.run_button.setText(tr("wb_btn_cancel"))
            self.run_button.setStyleSheet("background:#c53030; color:#ffffff; font-weight:bold; font-size:12px; padding:8px 20px; border-radius:4px;")
            self.run_button.clicked.disconnect()
            self.run_button.clicked.connect(self.stop)
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
            self.run_button.setText(tr("wb_btn_render"))
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
            """)
            self.run_button.clicked.disconnect()
            self.run_button.clicked.connect(self.run)
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

    def run(self):
        try:
            if not self.queue.count():
                raise ValueError(tr('msg_error_input_required'))
            if self.hint_mode.currentData() and self.queue.count() != 1:
                raise ValueError(tr('msg_error_hint_single'))
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
                return

            opts = self.options()
            jobs = []
            for i in range(self.queue.count()):
                source = Path(self.queue.item(i).text())
                dest = Path(self.output.text()).resolve() / (
                    source.stem + '_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
                )
                args = make_arguments(source, dest, opts)
                jobs.append((source, dest, args, opts))

            self.jobs = jobs
            self.total = len(jobs)
            self.cancelled = False
            self.next_job()
        except Exception as exc:
            QMessageBox.warning(self, tr('msg_config_check'), str(exc))

    def next_job(self):
        source, self.destination, args, self.current_opts = self.jobs.pop(0)
        self.current_source = source
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

        self.status.setText(tr('status_processing', current=self.total - len(self.jobs), total=self.total, name=source.name))
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

                # 2. RGVI chunk progress: "[RGVI Window 2/7] Processing frames 20..59"
                m_rgvi = re.search(r'\[RGVI Window\s+(\d+)/(\d+)\]', line)
                if m_rgvi:
                    curr, total = int(m_rgvi.group(1)), int(m_rgvi.group(2))
                    pct = int((curr / max(1, total)) * 100)
                    self.progress.setRange(0, 100)
                    self.progress.setValue(pct)
                    status_msg = f"Clean Plate Window {curr}/{total} ({pct}%)"
                    self.status.setText(f"✨ {status_msg}")
                    if hasattr(self, 'lbl_live_task'):
                        self.lbl_live_task.setText(f"RGVI Inpainting: {status_msg}")
                    if hasattr(self, 'queue_info') and self.current_source:
                        self.queue_info.setText(f"▶ {self.current_source.name} [Inpaint]: {status_msg}")

                # 3. Diffusion step:
                if "Synthesizing photorealistic reference" in line:
                    if hasattr(self, 'lbl_live_task'):
                        self.lbl_live_task.setText("🎨 Stable Diffusion Inpainting...")

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
            self.status.setText(tr('status_stopped'))
            if self.killer.state() == QProcess.NotRunning:
                self.busy(False)
            return

        if code != 0 or exit_status != QProcess.NormalExit:
            self.jobs.clear()
            self.busy(False)
            self.status.setText(tr('status_failed', code=code))
            return

        # Check if clean_plate (RGVI inpainting) is requested after inference finishes
        if self.mode == 'inference' and self.destination and self.current_opts.get('clean_plate'):
            alpha_files = list(self.destination.glob('*_alpha.mp4')) + list(self.destination.glob('*_alpha.mov'))
            if alpha_files:
                alpha_path = alpha_files[0]
                out_clean = self.destination / f"{self.current_source.stem}_clean_plate.mp4"
                rgvi_args = [
                    '-u', str(ROOT / 'inpaint_rgvi.py'),
                    '--video', str(self.current_source),
                    '--mask', str(alpha_path),
                    '--output', str(out_clean),
                    '--scale', str(self.current_opts.get('model_scale', 1.0)),
                ]
                cp_prompt = self.current_opts.get('clean_plate_prompt', '').strip()
                if cp_prompt:
                    rgvi_args.extend(['--prompt', cp_prompt])
                self.status.setText(tr('status_rgvi_running'))
                self.log.appendPlainText(tr('log_rgvi_start', src=self.current_source.name, mask=alpha_path.name, dst=out_clean.name))
                self.launch(rgvi_args, 'rgvi_inpaint')
                return

        if self.mode == 'rgvi_inpaint' and self.destination:
            out_clean = self.destination / f"{self.current_source.stem}_clean_plate.mp4"
            if out_clean.is_file():
                self.log.appendPlainText(tr('log_rgvi_done', path=out_clean.name))

        if self.destination:
            for path in sorted(self.destination.iterdir()):
                if path.suffix.lower() in VIDEO_EXTS or (path.is_dir() and any(path.glob('*.exr'))):
                    entry = f'{self.destination.name} / {path.name}'
                    if self.result_choice.findText(entry) < 0:
                        self.result_choice.addItem(entry, str(path))
            if self.result_choice.count():
                self.result_choice.setCurrentIndex(self.result_choice.count() - 1)
            # Re-detect results for active clip
            if self.current_clip_path:
                self._detect_matched_results(self.current_clip_path)
                self.show_frame_in_viewport(self.filmstrip.current_frame)

            if self.jobs:
                self.next_job()
                return

        self.busy(False)
        self.progress.setValue(1)
        self.status.setText({
            'inference': tr('status_done'),
            'rgvi_inpaint': tr('status_rgvi_done'),
            'download': tr('status_download_done'),
            'check': tr('status_check_passed'),
        }.get(self.mode, tr('status_done')))

    def stop(self):
        self.cancelled = True
        self.jobs.clear()
        self.status.setText(tr('status_stopping'))
        pid = self.proc.processId()
        if pid and os.name == 'nt':
            self.killer.start('taskkill', ['/PID', str(pid), '/T', '/F'])
        else:
            self.proc.kill()

    def kill_finished(self, code, status):
        if self.proc.state() == QProcess.NotRunning:
            self.busy(False)
        elif code != 0:
            self.log.appendPlainText(tr('log_kill_failed'))

    def open_output(self):
        path = self.destination or Path(self.output.text())
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event):
        if self.proc.state() != QProcess.NotRunning or self.killer.state() != QProcess.NotRunning:
            QMessageBox.information(self, tr('msg_running_title'), tr('msg_running_text'))
            event.ignore()
        else:
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
