"""CorridorKey 2.0 Workbench Custom UI Components.

Provides DaVinci Resolve / Nuke style VFX workstation components:
- VFXViewport: Large canvas with checkerboard alpha composite, wipe split slider, side-by-side
- FilmstripTimeline: Video thumbnail filmstrip with interactive playhead scrubbing & transport
- MediaCardWidget: Visual clip card with video thumbnail, status badge, specs
- CollapsibleSection: Polished dark accordion containers for Inspector
- ToolRailWidget: Far-left vertical tool icon rail
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List

import cv2
import numpy as np

from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QSize, Signal, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QFont, QIcon, QImage, QPainter, QPaintEvent,
    QPen, QPixmap, QPolygon, QLinearGradient
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QToolButton, QScrollArea, QSizePolicy
)


# =============================================================================
# Helper: Checkerboard Pattern Generator
# =============================================================================
def make_checker_pixmap(tile_size: int = 16, c1: str = "#181b22", c2: str = "#222731") -> QPixmap:
    """Create a seamless 2x2 repeating checkerboard pattern pixmap."""
    pix = QPixmap(tile_size * 2, tile_size * 2)
    p = QPainter(pix)
    col1 = QColor(c1)
    col2 = QColor(c2)
    p.fillRect(0, 0, tile_size, tile_size, col1)
    p.fillRect(tile_size, tile_size, tile_size, tile_size, col1)
    p.fillRect(tile_size, 0, tile_size, tile_size, col2)
    p.fillRect(0, tile_size, tile_size, tile_size, col2)
    p.end()
    return pix


# =============================================================================
# 1. Tool Rail (Far-Left Vertical Icon Strip)
# =============================================================================
class ToolRailWidget(QFrame):
    """Vertical DCC workstation tool rail on the far left."""
    tool_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(46)
        self.setStyleSheet("""
            QFrame {
                background-color: #0e1014;
                border-right: 1px solid #1e222b;
            }
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 6px;
                color: #8392a5;
                font-size: 16px;
                margin: 3px 4px;
                padding: 8px 4px;
            }
            QToolButton:hover {
                background: #1c202a;
                color: #e5a93c;
            }
            QToolButton:checked {
                background: #232936;
                color: #e5a93c;
                border-left: 3px solid #e5a93c;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 8, 2, 8)
        layout.setSpacing(4)

        self.buttons = {}
        tools = [
            ("media", "📁", "Media Bin (Clips & Takes)"),
            ("layers", "🎭", "Matte & Layer Inspector"),
            ("wipe", "↔️", "Wipe & Compare Tools"),
            ("history", "⏱️", "Queue & Render History"),
            ("color", "🎨", "Despill & Color Tuning"),
            ("models", "📦", "AI Models & Weights"),
            ("export", "🚀", "Deliver & Export"),
        ]

        for key, icon, tip in tools:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda chk, k=key: self._on_clicked(k))
            layout.addWidget(btn)
            self.buttons[key] = btn

        self.buttons["media"].setChecked(True)
        layout.addStretch()
        self.retranslate()

    def retranslate(self):
        from i18n import tr
        tips = {
            "media": tr("rail_media_tip"),
            "layers": tr("rail_layers_tip"),
            "wipe": tr("rail_wipe_tip"),
            "history": tr("rail_history_tip"),
            "color": tr("rail_color_tip"),
            "models": tr("rail_models_tip"),
            "export": tr("rail_export_tip"),
        }
        for k, tip in tips.items():
            if k in self.buttons:
                self.buttons[k].setToolTip(tip)

    def _on_clicked(self, key: str):
        for k, b in self.buttons.items():
            b.setChecked(k == key)
        self.tool_selected.emit(key)


# =============================================================================
# 2. VFX Viewport (Checkerboard, Single, Wipe Split, Side-by-Side)
# =============================================================================
class VFXViewport(QWidget):
    """High-performance VFX viewer supporting transparent checkerboard, interactive wipe, and side-by-side."""
    wipe_position_changed = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(420, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self.checker_pixmap = make_checker_pixmap(16, "#171a21", "#212631")
        self.orig_pixmap: Optional[QPixmap] = None
        self.comp_pixmap: Optional[QPixmap] = None
        self.alpha_pixmap: Optional[QPixmap] = None

        self.view_mode = "wipe"       # "single", "wipe", "side_by_side"
        self.channel_mode = "comp"    # "comp", "alpha", "cutout", "orig", "clean"
        self.wipe_pos = 0.5           # 0.0 to 1.0 (horizontal ratio)
        self.is_dragging_wipe = False
        self.handle_hover = False
        self.title_text = ""
        self.preview_badge = "PREVIEW"

    def set_images(
        self,
        orig: Optional[QPixmap] = None,
        comp: Optional[QPixmap] = None,
        alpha: Optional[QPixmap] = None,
        title: str = "",
    ):
        """Update active pixmaps displayed in the viewport."""
        self.orig_pixmap = orig
        self.comp_pixmap = comp
        self.alpha_pixmap = alpha
        self.title_text = title
        self.update()

    def set_view_mode(self, mode: str):
        """Switch between 'single', 'wipe', 'side_by_side'."""
        self.view_mode = mode
        self.update()

    def set_channel_mode(self, mode: str):
        """Switch channel display: 'comp', 'alpha', 'cutout', 'orig', 'clean'."""
        self.channel_mode = mode
        self.update()

    # --- Mouse Interaction for Wipe Split Handle ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.view_mode == "wipe":
            split_x = int(self.width() * self.wipe_pos)
            if abs(event.position().x() - split_x) <= 18:
                self.is_dragging_wipe = True
                self.setCursor(Qt.SplitHCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        split_x = int(self.width() * self.wipe_pos)
        is_near = abs(event.position().x() - split_x) <= 18
        if self.view_mode == "wipe":
            if self.is_dragging_wipe:
                new_pos = max(0.02, min(0.98, event.position().x() / max(1, self.width())))
                self.wipe_pos = new_pos
                self.wipe_position_changed.emit(new_pos)
                self.update()
                event.accept()
                return
            elif is_near != self.handle_hover:
                self.handle_hover = is_near
                self.setCursor(Qt.SplitHCursor if is_near else Qt.ArrowCursor)
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_dragging_wipe:
            self.is_dragging_wipe = False
            self.setCursor(Qt.ArrowCursor)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # --- Paint Event ---
    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        vw = self.width()
        vh = self.height()

        # 1. Base dark background
        painter.fillRect(0, 0, vw, vh, QColor("#121419"))

        # Determine active foreground pixmap based on channel mode
        active_result = self.comp_pixmap or self.orig_pixmap
        if self.channel_mode == "alpha" and self.alpha_pixmap:
            active_result = self.alpha_pixmap
        elif self.channel_mode == "orig" and self.orig_pixmap:
            active_result = self.orig_pixmap

        if not self.orig_pixmap and not active_result:
            # Draw placeholder message
            painter.setPen(QPen(QColor("#546173"), 1))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(
                QRect(0, 0, vw, vh),
                Qt.AlignCenter,
                "No clip loaded — drag & drop video files into Media Bin or click [+ Import...]"
            )
            return

        ref_pix = active_result or self.orig_pixmap
        pw = ref_pix.width()
        ph = ref_pix.height()

        # Calculate aspect-ratio fit box inside viewport
        scale = min(vw / pw, vh / ph)
        target_w = int(pw * scale)
        target_h = int(ph * scale)
        target_x = (vw - target_w) // 2
        target_y = (vh - target_h) // 2
        fit_rect = QRect(target_x, target_y, target_w, target_h)

        # 2. Draw Checkerboard background inside the image fit rectangle
        painter.drawTiledPixmap(fit_rect, self.checker_pixmap)

        # 3. Draw content depending on view_mode
        if self.view_mode == "single" or not self.orig_pixmap or not active_result or active_result == self.orig_pixmap:
            # Draw single image
            painter.drawPixmap(fit_rect, active_result)

        elif self.view_mode == "side_by_side":
            half_w = (vw - 8) // 2
            scale_half = min(half_w / pw, vh / ph)
            th_w = int(pw * scale_half)
            th_h = int(ph * scale_half)
            th_y = (vh - th_h) // 2

            r_left = QRect(half_w - th_w, th_y, th_w, th_h)
            r_right = QRect(half_w + 8, th_y, th_w, th_h)

            painter.drawTiledPixmap(r_left, self.checker_pixmap)
            painter.drawTiledPixmap(r_right, self.checker_pixmap)

            painter.drawPixmap(r_left, self.orig_pixmap)
            painter.drawPixmap(r_right, active_result)

            # Labels for Left/Right
            painter.setPen(QColor("#8392a5"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(r_left.adjusted(8, 8, 0, 0), Qt.AlignTop | Qt.AlignLeft, "ORIGINAL")
            painter.drawText(r_right.adjusted(8, 8, 0, 0), Qt.AlignTop | Qt.AlignLeft, "KEYED / MATTE")

        elif self.view_mode == "wipe":
            split_x = int(vw * self.wipe_pos)

            # Left side: Original Image
            painter.save()
            painter.setClipRect(0, 0, split_x, vh)
            painter.drawPixmap(fit_rect, self.orig_pixmap)
            painter.restore()

            # Right side: Composite / Matte Result
            painter.save()
            painter.setClipRect(split_x, 0, vw - split_x, vh)
            painter.drawPixmap(fit_rect, active_result)
            painter.restore()

            # Wipe Split Bar & Handle
            line_color = QColor("#f0b842" if (self.is_dragging_wipe or self.handle_hover) else "#d4952b")
            painter.setPen(QPen(line_color, 2))
            painter.drawLine(split_x, target_y, split_x, target_y + target_h)

            # Central handle circle
            handle_y = target_y + target_h // 2
            painter.setBrush(QBrush(line_color))
            painter.setPen(QPen(QColor("#0e1014"), 2))
            painter.drawEllipse(QPoint(split_x, handle_y), 9, 9)

            # Handle arrows
            painter.setPen(QPen(QColor("#1e232e"), 1.5))
            painter.drawLine(split_x - 5, handle_y, split_x - 2, handle_y - 3)
            painter.drawLine(split_x - 5, handle_y, split_x - 2, handle_y + 3)
            painter.drawLine(split_x + 5, handle_y, split_x + 2, handle_y - 3)
            painter.drawLine(split_x + 5, handle_y, split_x + 2, handle_y + 3)

        # 4. Corner Overlays: Green [PREVIEW] Badge
        badge_rect = QRect(16, vh - 38, 76, 22)
        painter.setBrush(QBrush(QColor(32, 75, 48, 220)))
        painter.setPen(QPen(QColor("#2ecc71"), 1))
        painter.drawRoundedRect(badge_rect, 4, 4)

        painter.setPen(QColor("#2ecc71"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(badge_rect, Qt.AlignCenter, self.preview_badge)

        painter.end()


# =============================================================================
# 3. Filmstrip Scrubber & Transport Timeline
# =============================================================================
class FilmstripTimeline(QWidget):
    """Horizontal video filmstrip with draggable playhead and transport controls."""
    frame_changed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(82)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.total_frames = 0
        self.current_frame = 0
        self.fps = 24.0
        self.thumbnails: List[QPixmap] = []
        self.is_scrubbing = False
        self.is_playing = False

        # Playback timer
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._on_play_tick)

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(4)

        # Transport Bar
        h_trans = QHBoxLayout()
        h_trans.setContentsMargins(4, 0, 4, 0)
        h_trans.setSpacing(6)

        self.lbl_counter = QLabel("0 / 0")
        self.lbl_counter.setStyleSheet("font-weight:bold; font-size:12px; color:#c9d1d9; min-width:85px;")
        h_trans.addWidget(self.lbl_counter)

        h_trans.addStretch(1)

        # Transport Buttons
        btn_style = """
            QPushButton {
                background: #191c24;
                border: 1px solid #2a313d;
                border-radius: 4px;
                color: #c9d1d9;
                font-size: 11px;
                padding: 3px 8px;
            }
            QPushButton:hover {
                background: #232834;
                border-color: #e5a93c;
                color: #e5a93c;
            }
        """

        self.btn_first = QPushButton("|◀")
        self.btn_prev = QPushButton("◀")
        self.btn_play = QPushButton("▶")
        self.btn_next = QPushButton("▶")
        self.btn_last = QPushButton("▶|")

        for b in [self.btn_first, self.btn_prev, self.btn_play, self.btn_next, self.btn_last]:
            b.setStyleSheet(btn_style)
            h_trans.addWidget(b)

        self.btn_first.clicked.connect(lambda: self.seek(0))
        self.btn_prev.clicked.connect(lambda: self.seek(max(0, self.current_frame - 1)))
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next.clicked.connect(lambda: self.seek(min(max(0, self.total_frames - 1), self.current_frame + 1)))
        self.btn_last.clicked.connect(lambda: self.seek(max(0, self.total_frames - 1)))

        h_trans.addStretch(1)

        self.lbl_fps = QLabel("Display: as is  24.00 fps")
        self.lbl_fps.setStyleSheet("color:#7e899b; font-size:11px;")
        h_trans.addWidget(self.lbl_fps)

        main_layout.addLayout(h_trans)

        # Filmstrip Widget
        self.strip_widget = _FilmstripStrip(self)
        self.strip_widget.setFixedHeight(48)
        self.strip_widget.frame_picked.connect(self.seek)
        main_layout.addWidget(self.strip_widget)

    def load_clip_metadata(self, total_frames: int, fps: float, thumbnails: List[QPixmap]):
        """Bind new video metadata and thumbnails."""
        self.total_frames = max(0, total_frames)
        self.fps = fps if fps > 0 else 24.0
        self.current_frame = 0
        self.thumbnails = thumbnails
        self.strip_widget.set_thumbnails(thumbnails, self.total_frames)
        self.seek(0)
        self.lbl_fps.setText(f"Display: as is  {self.fps:.2f} fps")

    def seek(self, frame_idx: int):
        if self.total_frames <= 0:
            self.lbl_counter.setText("0 / 0")
            return
        self.current_frame = max(0, min(self.total_frames - 1, frame_idx))
        self.lbl_counter.setText(f"{self.current_frame + 1} / 1-{self.total_frames}")
        self.strip_widget.set_current_frame(self.current_frame)
        self.frame_changed.emit(self.current_frame)

    def toggle_play(self):
        if self.is_playing:
            self.play_timer.stop()
            self.is_playing = False
            self.btn_play.setText("▶")
        else:
            if self.total_frames > 1:
                interval_ms = int(1000.0 / max(1.0, self.fps))
                self.play_timer.start(interval_ms)
                self.is_playing = True
                self.btn_play.setText("⏸")

    def _on_play_tick(self):
        if self.total_frames <= 1:
            return
        nxt = (self.current_frame + 1) % self.total_frames
        self.seek(nxt)


class _FilmstripStrip(QWidget):
    """Custom drawing canvas for the filmstrip thumbnails and yellow playhead bar."""
    frame_picked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.thumbnails: List[QPixmap] = []
        self.total_frames = 0
        self.current_frame = 0
        self.is_dragging = False

    def set_thumbnails(self, thumbs: List[QPixmap], total_frames: int):
        self.thumbnails = thumbs
        self.total_frames = total_frames
        self.update()

    def set_current_frame(self, frame: int):
        self.current_frame = frame
        self.update()

    def _pick_frame_from_x(self, x: float):
        if self.total_frames <= 0:
            return
        ratio = max(0.0, min(1.0, x / max(1, self.width())))
        frame = int(ratio * (self.total_frames - 1))
        self.frame_picked.emit(frame)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self._pick_frame_from_x(event.position().x())
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            self._pick_frame_from_x(event.position().x())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            event.accept()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        w = self.width()
        h = self.height()

        painter.fillRect(0, 0, w, h, QColor("#101217"))

        # Draw thumbnails
        if self.thumbnails:
            num_t = len(self.thumbnails)
            tile_w = w / max(1, num_t)
            for i, pix in enumerate(self.thumbnails):
                rect = QRectF(i * tile_w, 0, tile_w + 1, h)
                painter.drawPixmap(rect.toRect(), pix)

        # Dark border
        painter.setPen(QPen(QColor("#20242e"), 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        # Draw playhead indicator
        if self.total_frames > 0:
            px = int((self.current_frame / max(1, self.total_frames - 1)) * (w - 2)) + 1
            # Playhead line
            painter.setPen(QPen(QColor("#e5a93c"), 2))
            painter.drawLine(px, 0, px, h)

            # Playhead top marker (small triangle)
            painter.setBrush(QBrush(QColor("#f5b642")))
            painter.setPen(Qt.NoPen)
            poly = QPolygon([
                QPoint(px - 5, 0),
                QPoint(px + 5, 0),
                QPoint(px, 7),
            ])
            painter.drawPolygon(poly)

        painter.end()


# =============================================================================
# 4. Media Bin Visual Clip Card
# =============================================================================
class MediaCardWidget(QFrame):
    """Visual clip item with video thumbnail, status badge, specs and active selection."""
    clicked = Signal(Path)

    def __init__(self, clip_path: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.clip_path = clip_path
        self.is_selected = False
        self.status = "READY"  # READY, PROCESSING, DONE

        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._build_ui()
        self.update_style()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # Thumbnail Label
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setFixedSize(96, 60)
        self.lbl_thumb.setStyleSheet("background:#0a0c10; border-radius:4px;")
        self.lbl_thumb.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_thumb)

        # Details
        v_info = QVBoxLayout()
        v_info.setContentsMargins(0, 2, 0, 2)
        v_info.setSpacing(2)

        # Status badge row
        h_badge = QHBoxLayout()
        self.badge = QLabel("READY")
        self.badge.setStyleSheet("""
            background: #194d2e;
            color: #49de80;
            font-size: 10px;
            font-weight: bold;
            padding: 1px 6px;
            border-radius: 3px;
        """)
        h_badge.addWidget(self.badge)
        h_badge.addStretch(1)
        v_info.addLayout(h_badge)

        # Name
        self.lbl_name = QLabel(self.clip_path.name)
        self.lbl_name.setStyleSheet("color:#e1e7ee; font-weight:bold; font-size:12px;")
        v_info.addWidget(self.lbl_name)

        # Specs
        self.lbl_specs = QLabel("Loading specs...")
        self.lbl_specs.setStyleSheet("color:#768394; font-size:10px;")
        v_info.addWidget(self.lbl_specs)

        layout.addLayout(v_info, 1)

    def set_thumbnail_and_specs(self, thumb: QPixmap, frames: int, resolution: str, fps: float):
        self.lbl_thumb.setPixmap(thumb.scaled(self.lbl_thumb.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.lbl_specs.setText(f"{frames} frames · {resolution} · {fps:.2f} fps")

    def set_status(self, status: str):
        self.status = status
        color_map = {
            "READY": ("#194d2e", "#49de80"),
            "PROCESSING": ("#5c3c0a", "#f5a623"),
            "DONE": ("#133f6b", "#4ea8de"),
        }
        bg, fg = color_map.get(status, ("#1f242d", "#8fa3bf"))
        self.badge.setText(status)
        self.badge.setStyleSheet(f"background:{bg}; color:{fg}; font-size:10px; font-weight:bold; padding:1px 6px; border-radius:3px;")

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.update_style()

    def update_style(self):
        border = "2px solid #e5a93c" if self.is_selected else "1px solid #20242e"
        bg = "#191d26" if self.is_selected else "#13161c"
        self.setStyleSheet(f"""
            MediaCardWidget {{
                background-color: {bg};
                border: {border};
                border-radius: 6px;
            }}
            MediaCardWidget:hover {{
                border-color: #f5b642;
                background-color: #1a1e27;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.clip_path)
        super().mousePressEvent(event)


# =============================================================================
# 5. Collapsible Section (Inspector Accordion)
# =============================================================================
class CollapsibleSection(QWidget):
    """Sleek collapsible accordion section for the Inspector panel."""

    def __init__(self, title: str, parent: Optional[QWidget] = None, starts_open: bool = True):
        super().__init__(parent)
        self.is_open = starts_open
        self.title_text = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(0)

        # Header Toggle Button
        self.btn_toggle = QPushButton()
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(starts_open)
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background: #151820;
                border: none;
                border-top: 1px solid #242934;
                border-bottom: 1px solid #1c202a;
                color: #c9d1d9;
                font-size: 11px;
                font-weight: bold;
                text-align: left;
                padding: 7px 10px;
            }
            QPushButton:hover {
                background: #1c202a;
                color: #e5a93c;
            }
        """)
        self._update_header_text()
        self.btn_toggle.clicked.connect(self._toggle)
        layout.addWidget(self.btn_toggle)

        # Content Container
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 8, 10, 8)
        self.content_layout.setSpacing(6)
        self.content_widget.setVisible(starts_open)
        layout.addWidget(self.content_widget)

    def _update_header_text(self):
        arrow = "▼" if self.is_open else "▶"
        self.btn_toggle.setText(f"{arrow}  {self.title_text}")

    def _toggle(self):
        self.is_open = not self.is_open
        self.content_widget.setVisible(self.is_open)
        self._update_header_text()

    def set_open(self, is_open: bool):
        """Programmatically expand or collapse this section."""
        self.is_open = is_open
        self.content_widget.setVisible(is_open)
        self.btn_toggle.setChecked(is_open)
        self._update_header_text()

    def addWidget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def addLayout(self, sub_layout):
        self.content_layout.addLayout(sub_layout)

    def setContentLayout(self, sub_layout):
        self.content_layout.addLayout(sub_layout)

    def setTitle(self, title: str):
        self.title_text = title
        self._update_header_text()
