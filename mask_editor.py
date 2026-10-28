"""CorridorKey 2.0 Interactive Brush Mask Editor.

Allows artists to paint precise foreground/background masks on any video frame
or image, inspect the matte with multiple view modes, and export masks or apply
them directly as CorridorKey first-frame hints.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Optional, List, Tuple

import cv2
import numpy as np
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, Signal
from PySide6.QtGui import (
    QAction, QColor, QCursor, QFont, QGuiApplication, QIcon, QImage, QKeySequence,
    QPainter, QPen, QPixmap, QRadialGradient, QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QComboBox, QDialog, QFileDialog, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QRadioButton, QScrollArea, QSlider, QSpinBox, QSplitter, QToolButton,
    QVBoxLayout, QWidget,
)

from i18n import tr


class MaskHistory:
    """Undo/Redo manager for mask states using compact numpy arrays."""
    def __init__(self, max_states: int = 20):
        self.max_states = max_states
        self.undo_stack: List[np.ndarray] = []
        self.redo_stack: List[np.ndarray] = []

    def push(self, mask: np.ndarray):
        # Store a copy
        self.undo_stack.append(mask.copy())
        if len(self.undo_stack) > self.max_states:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self, current_mask: np.ndarray) -> Optional[np.ndarray]:
        if not self.undo_stack:
            return None
        self.redo_stack.append(current_mask.copy())
        return self.undo_stack.pop()

    def redo(self, current_mask: np.ndarray) -> Optional[np.ndarray]:
        if not self.redo_stack:
            return None
        self.undo_stack.append(current_mask.copy())
        return self.redo_stack.pop()

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0


class MaskCanvas(QWidget):
    """High-performance interactive painting canvas for mask editing."""
    mask_changed = Signal()
    cursor_moved = Signal(int, int)

    MODE_BRUSH = 0    # Paint white (foreground)
    MODE_ERASER = 1   # Paint black (background)
    MODE_RECT_ADD = 2 # Fill rect white
    MODE_RECT_SUB = 3 # Fill rect black

    VIEW_OVERLAY = 0  # Semi-transparent colored overlay over RGB
    VIEW_MATTE = 1    # Pure black & white mask
    VIEW_CUTOUT = 2   # Foreground on transparent checkerboard
    VIEW_RGB = 3      # Raw source image without mask

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.source_rgb: Optional[np.ndarray] = None  # (H, W, 3) uint8 RGB
        self.mask: Optional[np.ndarray] = None        # (H, W) uint8 0..255
        self.width_img = 0
        self.height_img = 0

        # View settings
        self.zoom = 1.0
        self.pan_offset = QPointF(0, 0)
        self.view_mode = self.VIEW_OVERLAY
        self.overlay_color = QColor(255, 50, 50, 160)  # Reddish tint
        self.overlay_opacity = 0.65

        # Tool settings
        self.tool_mode = self.MODE_BRUSH
        self.brush_size = 40
        self.brush_hardness = 0.5  # 0.0 (soft Gaussian-like) to 1.0 (hard edge)
        self.brush_opacity = 1.0

        # Interaction state
        self.is_drawing = False
        self.is_panning = False
        self.pan_start_pos = QPoint()
        self.last_img_pos: Optional[QPointF] = None
        self.current_mouse_pos = QPoint(-1000, -1000)
        self.rect_start_img_pos: Optional[QPoint] = None
        self.rect_current_img_pos: Optional[QPoint] = None

        self.history = MaskHistory()
        self._brush_stamp_cache: dict = {}
        self._checkerboard_pixmap: Optional[QPixmap] = None
        self._user_has_transformed = False

    def set_image(self, rgb_image: np.ndarray, initial_mask: Optional[np.ndarray] = None):
        """Set source RGB image (H, W, 3 uint8) and optional starting mask."""
        self.source_rgb = rgb_image
        self.height_img, self.width_img = rgb_image.shape[:2]

        if initial_mask is not None and initial_mask.shape[:2] == (self.height_img, self.width_img):
            if initial_mask.ndim == 3:
                initial_mask = cv2.cvtColor(initial_mask, cv2.COLOR_BGR2GRAY)
            self.mask = initial_mask.astype(np.uint8)
        else:
            self.mask = np.zeros((self.height_img, self.width_img), dtype=np.uint8)

        self.history = MaskHistory()
        self._user_has_transformed = False
        self.zoom_to_fit()
        self.update()
        self.mask_changed.emit()

    def zoom_to_fit(self):
        """Fit image inside widget viewport with comfortable padding."""
        if self.width_img <= 0 or self.height_img <= 0:
            return
        w_avail = max(40, self.width() - 40)
        h_avail = max(40, self.height() - 40)
        scale_w = w_avail / self.width_img
        scale_h = h_avail / self.height_img
        # Remove arbitrary 1.0 ceiling so image fits neatly in available viewport
        self.zoom = min(scale_w, scale_h)
        self.center_image()
        self._user_has_transformed = False
        self.update()

    def reset_view(self):
        self.zoom_to_fit()

    def zoom_100(self):
        self.zoom = 1.0
        self.center_image()
        self._user_has_transformed = True
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        # Use singleShot to guarantee layout geometry has settled
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.zoom_to_fit)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not getattr(self, '_user_has_transformed', False):
            self.zoom_to_fit()
        else:
            self.center_image()
        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.zoom_to_fit()

    def center_image(self):
        if self.width_img > 0 and self.height_img > 0:
            disp_w = self.width_img * self.zoom
            disp_h = self.height_img * self.zoom
            self.pan_offset = QPointF(
                (self.width() - disp_w) / 2.0,
                (self.height() - disp_h) / 2.0,
            )

    # -------------------------------------------------------------------------
    # Coordinate Transforms
    # -------------------------------------------------------------------------
    def widget_to_image(self, pt: QPoint) -> QPointF:
        x = (pt.x() - self.pan_offset.x()) / self.zoom
        y = (pt.y() - self.pan_offset.y()) / self.zoom
        return QPointF(x, y)

    def image_to_widget(self, pt: QPointF) -> QPointF:
        x = pt.x() * self.zoom + self.pan_offset.x()
        y = pt.y() * self.zoom + self.pan_offset.y()
        return QPointF(x, y)

    # -------------------------------------------------------------------------
    # Mask & Brush Operations
    # -------------------------------------------------------------------------
    def _get_brush_stamp(self, radius: int, hardness: float) -> np.ndarray:
        """Generate a radial brush profile kernel (2R+1, 2R+1) float32 [0..1]."""
        key = (radius, round(hardness, 2))
        if key in self._brush_stamp_cache:
            return self._brush_stamp_cache[key]

        d = radius * 2 + 1
        y, x = np.ogrid[-radius:radius + 1, -radius:radius + 1]
        dist = np.sqrt(x * x + y * y)

        if hardness >= 0.99:
            stamp = (dist <= radius).astype(np.float32)
        else:
            # Linear/cosine falloff based on hardness
            inner_r = radius * hardness
            falloff = np.clip((radius - dist) / max(1e-5, radius - inner_r), 0.0, 1.0)
            # Smooth cosine curve for natural paint feel
            stamp = 0.5 * (1.0 - np.cos(falloff * np.pi))

        if len(self._brush_stamp_cache) > 64:
            self._brush_stamp_cache.clear()
        self._brush_stamp_cache[key] = stamp
        return stamp

    def _apply_stamp_to_mask(self, center: QPointF, is_eraser: bool, opacity: float):
        if self.mask is None:
            return

        cx = int(round(center.x()))
        cy = int(round(center.y()))
        r = max(1, self.brush_size)

        stamp = self._get_brush_stamp(r, self.brush_hardness) * opacity
        sh, sw = stamp.shape

        # Source slice (stamp)
        s_y1 = max(0, r - cy)
        s_y2 = sh - max(0, (cy + r + 1) - self.height_img)
        s_x1 = max(0, r - cx)
        s_x2 = sw - max(0, (cx + r + 1) - self.width_img)

        # Dest slice (mask)
        d_y1 = max(0, cy - r)
        d_y2 = min(self.height_img, cy + r + 1)
        d_x1 = max(0, cx - r)
        d_x2 = min(self.width_img, cx + r + 1)

        if d_y2 <= d_y1 or d_x2 <= d_x1 or s_y2 <= s_y1 or s_x2 <= s_x1:
            return

        stamp_patch = stamp[s_y1:s_y2, s_x1:s_x2]
        dest_patch = self.mask[d_y1:d_y2, d_x1:d_x2].astype(np.float32)

        if not is_eraser:
            # Paint white foreground (target 255)
            # Alpha blend towards 255
            dest_patch = dest_patch + (255.0 - dest_patch) * stamp_patch
        else:
            # Erase to black background (target 0)
            # Alpha blend towards 0
            dest_patch = dest_patch * (1.0 - stamp_patch)

        self.mask[d_y1:d_y2, d_x1:d_x2] = np.clip(dest_patch, 0, 255).astype(np.uint8)

    def paint_stroke(self, pt1: QPointF, pt2: QPointF):
        """Draw interpolated brush stamps between pt1 and pt2 for seamless stroke."""
        dx = pt2.x() - pt1.x()
        dy = pt2.y() - pt1.y()
        dist = np.hypot(dx, dy)
        step = max(1.0, self.brush_size * 0.25)  # 4 stamps per radius for smooth lines
        num_steps = max(1, int(np.ceil(dist / step)))

        is_eraser = (self.tool_mode == self.MODE_ERASER)
        for i in range(1, num_steps + 1):
            t = i / num_steps
            cur_pt = QPointF(pt1.x() + dx * t, pt1.y() + dy * t)
            self._apply_stamp_to_mask(cur_pt, is_eraser, self.brush_opacity)

    def fill_rect_selection(self, p1: QPoint, p2: QPoint, is_eraser: bool):
        if self.mask is None:
            return
        x1 = max(0, min(p1.x(), p2.x()))
        x2 = min(self.width_img, max(p1.x(), p2.x()) + 1)
        y1 = max(0, min(p1.y(), p2.y()))
        y2 = min(self.height_img, max(p1.y(), p2.y()) + 1)
        if x2 > x1 and y2 > y1:
            val = 0 if is_eraser else 255
            self.mask[y1:y2, x1:x2] = val
            self.update()
            self.mask_changed.emit()

    def clear_all(self):
        """Reset mask to entirely black (background)."""
        if self.mask is not None:
            self.history.push(self.mask)
            self.mask.fill(0)
            self.update()
            self.mask_changed.emit()

    def fill_all(self):
        """Fill mask entirely white (foreground)."""
        if self.mask is not None:
            self.history.push(self.mask)
            self.mask.fill(255)
            self.update()
            self.mask_changed.emit()

    def invert_mask(self):
        """Invert foreground and background."""
        if self.mask is not None:
            self.history.push(self.mask)
            self.mask = 255 - self.mask
            self.update()
            self.mask_changed.emit()

    def dilate_mask(self, pixels: int = 5):
        """Expand foreground mask boundaries by N pixels."""
        if self.mask is not None and pixels > 0:
            self.history.push(self.mask)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (pixels * 2 + 1, pixels * 2 + 1))
            self.mask = cv2.dilate(self.mask, kernel)
            self.update()
            self.mask_changed.emit()

    def erode_mask(self, pixels: int = 5):
        """Shrink foreground mask boundaries by N pixels."""
        if self.mask is not None and pixels > 0:
            self.history.push(self.mask)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (pixels * 2 + 1, pixels * 2 + 1))
            self.mask = cv2.erode(self.mask, kernel)
            self.update()
            self.mask_changed.emit()

    def blur_mask(self, ksize: int = 9):
        """Smooth mask edges with Gaussian feathering."""
        if self.mask is not None and ksize > 1:
            if ksize % 2 == 0:
                ksize += 1
            self.history.push(self.mask)
            self.mask = cv2.GaussianBlur(self.mask, (ksize, ksize), 0)
            self.update()
            self.mask_changed.emit()

    def undo(self):
        if self.mask is not None and self.history.can_undo():
            prev = self.history.undo(self.mask)
            if prev is not None:
                self.mask = prev
                self.update()
                self.mask_changed.emit()

    def redo(self):
        if self.mask is not None and self.history.can_redo():
            nxt = self.history.redo(self.mask)
            if nxt is not None:
                self.mask = nxt
                self.update()
                self.mask_changed.emit()

    # -------------------------------------------------------------------------
    # Mouse and Wheel Event Handlers
    # -------------------------------------------------------------------------
    def mousePressEvent(self, event):
        self.current_mouse_pos = event.pos()
        img_pt = self.widget_to_image(event.pos())

        # Middle button or Space+Left: Pan
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and (event.modifiers() & Qt.AltModifier or event.modifiers() & Qt.ShiftModifier and event.modifiers() & Qt.ControlModifier)):
            self.is_panning = True
            self.pan_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.RightButton:
            # Right-click drag can be quick pan
            self.is_panning = True
            self.pan_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton:
            if self.mask is None:
                return

            self.history.push(self.mask)

            if self.tool_mode in (self.MODE_RECT_ADD, self.MODE_RECT_SUB):
                self.rect_start_img_pos = QPoint(int(img_pt.x()), int(img_pt.y()))
                self.rect_current_img_pos = self.rect_start_img_pos
                self.update()
                return

            # Brush or Eraser stroke start
            self.is_drawing = True
            self.last_img_pos = img_pt
            is_eraser = (self.tool_mode == self.MODE_ERASER)
            self._apply_stamp_to_mask(img_pt, is_eraser, self.brush_opacity)
            self.update()
            self.mask_changed.emit()

    def mouseMoveEvent(self, event):
        self.current_mouse_pos = event.pos()
        img_pt = self.widget_to_image(event.pos())
        self.cursor_moved.emit(int(img_pt.x()), int(img_pt.y()))

        if self.is_panning:
            delta = event.pos() - self.pan_start_pos
            self.pan_offset += QPointF(delta.x(), delta.y())
            self.pan_start_pos = event.pos()
            self._user_has_transformed = True
            self.update()
            return

        if self.is_drawing and self.mask is not None and self.last_img_pos is not None:
            self.paint_stroke(self.last_img_pos, img_pt)
            self.last_img_pos = img_pt
            self.update()
            self.mask_changed.emit()
            return

        if self.rect_start_img_pos is not None:
            self.rect_current_img_pos = QPoint(int(img_pt.x()), int(img_pt.y()))
            self.update()
            return

        # Normal hover: redraw brush cursor ring
        self.update()

    def mouseReleaseEvent(self, event):
        if self.is_panning:
            self.is_panning = False
            self.setCursor(Qt.ArrowCursor)

        if self.is_drawing:
            self.is_drawing = False
            self.last_img_pos = None

        if self.rect_start_img_pos is not None and self.rect_current_img_pos is not None:
            is_eraser = (self.tool_mode == self.MODE_RECT_SUB)
            self.fill_rect_selection(self.rect_start_img_pos, self.rect_current_img_pos, is_eraser)
            self.rect_start_img_pos = None
            self.rect_current_img_pos = None
            self.update()

    def wheelEvent(self, event):
        # Ctrl + Wheel or Wheel alone: Zoom or Adjust Brush size
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.ControlModifier:
            # Adjust brush size
            step = 2 if self.brush_size < 30 else (5 if self.brush_size < 100 else 15)
            new_size = max(1, min(500, self.brush_size + (step if delta > 0 else -step)))
            self.brush_size = new_size
            self.update()
            self.mask_changed.emit()
            return

        # Standard Zoom centered around cursor
        old_zoom = self.zoom
        zoom_factor = 1.15 if delta > 0 else (1.0 / 1.15)
        new_zoom = max(0.05, min(20.0, old_zoom * zoom_factor))

        if abs(new_zoom - old_zoom) > 1e-4:
            mouse_widget = QPointF(event.position())
            # Maintain image coordinate at cursor
            img_x = (mouse_widget.x() - self.pan_offset.x()) / old_zoom
            img_y = (mouse_widget.y() - self.pan_offset.y()) / old_zoom

            self.zoom = new_zoom
            self.pan_offset = QPointF(
                mouse_widget.x() - img_x * new_zoom,
                mouse_widget.y() - img_y * new_zoom,
            )
            self._user_has_transformed = True
            self.update()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_F:
            self.zoom_to_fit()
        elif key == Qt.Key_BracketLeft:
            # Decrease brush size
            self.brush_size = max(1, self.brush_size - (3 if self.brush_size <= 20 else 8))
            self.update()
            self.mask_changed.emit()
        elif key == Qt.Key_BracketRight:
            # Increase brush size
            self.brush_size = min(500, self.brush_size + (3 if self.brush_size < 20 else 8))
            self.update()
            self.mask_changed.emit()
        elif key == Qt.Key_B:
            self.tool_mode = self.MODE_BRUSH
            self.update()
            self.mask_changed.emit()
        elif key == Qt.Key_E:
            self.tool_mode = self.MODE_ERASER
            self.update()
            self.mask_changed.emit()
        elif key == Qt.Key_Z and (event.modifiers() & Qt.ControlModifier):
            if event.modifiers() & Qt.ShiftModifier:
                self.redo()
            else:
                self.undo()
        elif key == Qt.Key_Y and (event.modifiers() & Qt.ControlModifier):
            self.redo()
        elif key == Qt.Key_Space:
            self.setCursor(Qt.OpenHandCursor)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not self.is_panning:
            self.setCursor(Qt.ArrowCursor)
        super().keyReleaseEvent(event)

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------
    def _get_checkerboard(self, w: int, h: int) -> QPixmap:
        """Create or scale a checkerboard background for cutout preview."""
        tile_size = 16
        img = QImage(tile_size * 2, tile_size * 2, QImage.Format_RGB32)
        c1 = QColor(36, 40, 48).rgb()
        c2 = QColor(24, 27, 33).rgb()
        for y in range(tile_size * 2):
            for x in range(tile_size * 2):
                bx = x // tile_size
                by = y // tile_size
                img.setPixel(x, y, c1 if (bx + by) % 2 == 0 else c2)
        return QPixmap.fromImage(img)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Clear background canvas
        painter.fillRect(self.rect(), QColor(16, 20, 26))

        if self.source_rgb is None or self.mask is None or self.width_img <= 0:
            painter.setPen(QColor(120, 130, 150))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(self.rect(), Qt.AlignCenter, tr("be_no_frame"))
            return

        # Target display rect
        disp_x = self.pan_offset.x()
        disp_y = self.pan_offset.y()
        disp_w = self.width_img * self.zoom
        disp_h = self.height_img * self.zoom
        target_rect = QRectF(disp_x, disp_y, disp_w, disp_h)

        # Render composite image according to view_mode
        composite_qimg = self._generate_composite_qimage()
        if composite_qimg is not None:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom < 2.0)
            painter.drawImage(target_rect, composite_qimg)

        # Draw frame border
        painter.setPen(QPen(QColor(60, 75, 95), 1))
        painter.drawRect(target_rect)

        # Draw active rectangle selection preview if dragging rect tool
        if self.rect_start_img_pos is not None and self.rect_current_img_pos is not None:
            p1 = self.image_to_widget(QPointF(self.rect_start_img_pos))
            p2 = self.image_to_widget(QPointF(self.rect_current_img_pos))
            rect_w = QRectF(
                min(p1.x(), p2.x()), min(p1.y(), p2.y()),
                abs(p2.x() - p1.x()), abs(p2.y() - p1.y())
            )
            pen_color = QColor(255, 80, 80) if self.tool_mode == self.MODE_RECT_SUB else QColor(80, 255, 120)
            painter.setPen(QPen(pen_color, 2, Qt.DashLine))
            fill_color = QColor(pen_color.red(), pen_color.green(), pen_color.blue(), 40)
            painter.fillRect(rect_w, fill_color)
            painter.drawRect(rect_w)

        # Draw Brush Cursor Ring when hovering inside widget
        if not self.is_panning and self.tool_mode in (self.MODE_BRUSH, self.MODE_ERASER):
            self._draw_brush_cursor(painter)

        # Draw HUD info overlay on top-left of canvas
        hud_text = tr("be_hud", zoom=int(self.zoom * 100))
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 20, 28, 190))
        hud_rect = QRect(12, 12, 380, 24)
        painter.drawRoundedRect(hud_rect, 4, 4)
        painter.setPen(QColor(180, 205, 230))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(hud_rect, Qt.AlignCenter, hud_text)

    def _generate_composite_qimage(self) -> Optional[QImage]:
        """Compose image and mask into a displayable QImage."""
        if self.source_rgb is None or self.mask is None:
            return None

        h, w = self.height_img, self.width_img

        if self.view_mode == self.VIEW_RGB:
            # Source RGB only
            return QImage(self.source_rgb.data, w, h, w * 3, QImage.Format_RGB888)

        elif self.view_mode == self.VIEW_MATTE:
            # Pure black & white mask
            # Repeat mask channel to 3 channels for fast display
            matte_rgb = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2RGB)
            return QImage(matte_rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()

        elif self.view_mode == self.VIEW_OVERLAY:
            # Overlay color on foreground mask
            # Blend: output = src * (1 - mask*alpha) + overlay_color * (mask*alpha)
            alpha_f = (self.mask.astype(np.float32) / 255.0) * self.overlay_opacity
            alpha_3 = np.stack([alpha_f] * 3, axis=-1)

            ov_r = self.overlay_color.red()
            ov_g = self.overlay_color.green()
            ov_b = self.overlay_color.blue()
            color_mat = np.array([ov_r, ov_g, ov_b], dtype=np.float32)

            blended = self.source_rgb.astype(np.float32) * (1.0 - alpha_3) + color_mat * alpha_3
            blended_uint8 = np.clip(blended, 0, 255).astype(np.uint8)
            return QImage(blended_uint8.data, w, h, w * 3, QImage.Format_RGB888).copy()

        elif self.view_mode == self.VIEW_CUTOUT:
            # Cutout foreground on dark/checkerboard background
            # Generate BG checkerboard
            tile = 16
            y_idx, x_idx = np.indices((h, w))
            checker = (((x_idx // tile) + (y_idx // tile)) % 2 == 0)
            bg = np.where(checker[..., None], np.uint8(45), np.uint8(25))

            alpha_f = self.mask.astype(np.float32) / 255.0
            alpha_3 = np.stack([alpha_f] * 3, axis=-1)

            cutout = (self.source_rgb.astype(np.float32) * alpha_3 + bg.astype(np.float32) * (1.0 - alpha_3))
            cutout_uint8 = np.clip(cutout, 0, 255).astype(np.uint8)
            return QImage(cutout_uint8.data, w, h, w * 3, QImage.Format_RGB888).copy()

        return None

    def _draw_brush_cursor(self, painter: QPainter):
        """Draw circular brush size ring at mouse position."""
        cx = self.current_mouse_pos.x()
        cy = self.current_mouse_pos.y()
        radius_screen = self.brush_size * self.zoom

        painter.setRenderHint(QPainter.Antialiasing, True)

        # Outer ring
        ring_color = QColor(255, 70, 70) if self.tool_mode == self.MODE_ERASER else QColor(80, 255, 160)
        painter.setPen(QPen(ring_color, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius_screen, radius_screen)

        # Inner hardness ring if soft brush
        if self.brush_hardness < 0.95 and radius_screen > 6:
            inner_r = radius_screen * self.brush_hardness
            painter.setPen(QPen(QColor(ring_color.red(), ring_color.green(), ring_color.blue(), 120), 1, Qt.DashLine))
            painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # Center dot
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
        painter.drawPoint(QPoint(cx, cy))


class BrushMaskEditorDialog(QDialog):
    """Full-featured Brush Mask Editor Dialog for CorridorKey 2.0.

    Allows painting masks, refining edges, and exporting or directly binding
    as the primary first-frame matte hint.
    """
    applied_hint = Signal(str)  # Emitted when applied directly as hint with saved file path

    def __init__(self, rgb_image: np.ndarray, clip_name: str = "clip",
                 initial_mask_path: Optional[str] = None, output_hint_dir: Optional[Path] = None,
                 parent=None):
        super().__init__(parent)
        self.clip_name = clip_name
        self.output_hint_dir = Path(output_hint_dir) if output_hint_dir else Path("./outputs")
        self.output_hint_dir.mkdir(parents=True, exist_ok=True)
        self.saved_mask_path: Optional[str] = None

        self.setWindowTitle(tr("be_title", clip=clip_name, w=rgb_image.shape[1], h=rgb_image.shape[0]))
        self.resize(1360, 920)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        # Load starting mask if specified
        starting_mask = None
        if initial_mask_path and Path(initial_mask_path).is_file():
            try:
                loaded = cv2.imdecode(np.fromfile(initial_mask_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                if loaded is not None:
                    if loaded.ndim == 3:
                        if loaded.shape[2] == 4:
                            starting_mask = loaded[:, :, 3]  # Alpha
                        else:
                            starting_mask = cv2.cvtColor(loaded, cv2.COLOR_BGR2GRAY)
                    else:
                        starting_mask = loaded
            except Exception:
                starting_mask = None

        # Main Layout
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        # Canvas Widget
        self.canvas = MaskCanvas(self)
        self.canvas.set_image(rgb_image, starting_mask)
        self.canvas.mask_changed.connect(self._update_stats)
        self.canvas.cursor_moved.connect(self._update_coords)
        root_layout.addWidget(self.canvas, 1)

        # Sidebar Controls
        sidebar = self._build_sidebar()
        root_layout.addWidget(sidebar)

        self._apply_theme()
        self._update_stats()

    def showEvent(self, event):
        super().showEvent(event)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self.canvas.zoom_to_fit)

    def _build_sidebar(self) -> QWidget:
        container = QWidget()
        container.setFixedWidth(330)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- 1. 도구 선택 ---
        grp_tool = QGroupBox(tr("be_grp_tools"))
        v_tool = QVBoxLayout(grp_tool)

        self.btn_brush = QPushButton(tr("be_btn_brush"))
        self.btn_brush.setCheckable(True)
        self.btn_brush.setChecked(True)
        self.btn_brush.setStyleSheet("font-weight: bold; background:#24695c;")
        self.btn_brush.clicked.connect(lambda: self._select_tool(MaskCanvas.MODE_BRUSH))

        self.btn_eraser = QPushButton(tr("be_btn_eraser"))
        self.btn_eraser.setCheckable(True)
        self.btn_eraser.clicked.connect(lambda: self._select_tool(MaskCanvas.MODE_ERASER))

        self.btn_rect_add = QPushButton(tr("be_btn_rect_add"))
        self.btn_rect_add.setCheckable(True)
        self.btn_rect_add.clicked.connect(lambda: self._select_tool(MaskCanvas.MODE_RECT_ADD))

        self.btn_rect_sub = QPushButton(tr("be_btn_rect_sub"))
        self.btn_rect_sub.setCheckable(True)
        self.btn_rect_sub.clicked.connect(lambda: self._select_tool(MaskCanvas.MODE_RECT_SUB))

        self.tool_group = QButtonGroup(self)
        self.tool_group.addButton(self.btn_brush)
        self.tool_group.addButton(self.btn_eraser)
        self.tool_group.addButton(self.btn_rect_add)
        self.tool_group.addButton(self.btn_rect_sub)

        v_tool.addWidget(self.btn_brush)
        v_tool.addWidget(self.btn_eraser)
        v_tool.addWidget(self.btn_rect_add)
        v_tool.addWidget(self.btn_rect_sub)
        layout.addWidget(grp_tool)

        # --- 2. 브러시 설정 ---
        grp_props = QGroupBox(tr("be_grp_props"))
        g_props = QGridLayout(grp_props)

        # Size
        g_props.addWidget(QLabel(tr("be_lbl_size")), 0, 0)
        self.lbl_size = QLabel(f"{self.canvas.brush_size} px")
        self.lbl_size.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        g_props.addWidget(self.lbl_size, 0, 1)

        self.slider_size = QSlider(Qt.Horizontal)
        self.slider_size.setRange(1, 300)
        self.slider_size.setValue(self.canvas.brush_size)
        self.slider_size.valueChanged.connect(self._on_size_changed)
        g_props.addWidget(self.slider_size, 1, 0, 1, 2)

        # Hardness / Softness
        g_props.addWidget(QLabel(tr("be_lbl_hardness")), 2, 0)
        self.lbl_hardness = QLabel(f"{int(self.canvas.brush_hardness * 100)} %")
        self.lbl_hardness.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        g_props.addWidget(self.lbl_hardness, 2, 1)

        self.slider_hardness = QSlider(Qt.Horizontal)
        self.slider_hardness.setRange(0, 100)
        self.slider_hardness.setValue(int(self.canvas.brush_hardness * 100))
        self.slider_hardness.valueChanged.connect(self._on_hardness_changed)
        g_props.addWidget(self.slider_hardness, 3, 0, 1, 2)

        # Opacity / Flow
        g_props.addWidget(QLabel(tr("be_lbl_opacity")), 4, 0)
        self.lbl_opacity = QLabel("100 %")
        self.lbl_opacity.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        g_props.addWidget(self.lbl_opacity, 4, 1)

        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(5, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.valueChanged.connect(self._on_opacity_changed)
        g_props.addWidget(self.slider_opacity, 5, 0, 1, 2)

        layout.addWidget(grp_props)

        # --- 3. 마스크 다듬기 및 변형 ---
        grp_edit = QGroupBox(tr("be_grp_edit"))
        g_edit = QGridLayout(grp_edit)

        btn_dilate = QPushButton(tr("be_btn_dilate"))
        btn_dilate.setToolTip(tr("be_btn_dilate_tip"))
        btn_dilate.clicked.connect(lambda: self.canvas.dilate_mask(3))
        g_edit.addWidget(btn_dilate, 0, 0)

        btn_erode = QPushButton(tr("be_btn_erode"))
        btn_erode.setToolTip(tr("be_btn_erode_tip"))
        btn_erode.clicked.connect(lambda: self.canvas.erode_mask(3))
        g_edit.addWidget(btn_erode, 0, 1)

        btn_blur = QPushButton(tr("be_btn_blur"))
        btn_blur.setToolTip(tr("be_btn_blur_tip"))
        btn_blur.clicked.connect(lambda: self.canvas.blur_mask(7))
        g_edit.addWidget(btn_blur, 1, 0)

        btn_invert = QPushButton(tr("be_btn_invert"))
        btn_invert.setToolTip(tr("be_btn_invert_tip"))
        btn_invert.clicked.connect(self.canvas.invert_mask)
        g_edit.addWidget(btn_invert, 1, 1)

        btn_clear = QPushButton(tr("be_btn_clear"))
        btn_clear.clicked.connect(self.canvas.clear_all)
        g_edit.addWidget(btn_clear, 2, 0)

        btn_fill = QPushButton(tr("be_btn_fill"))
        btn_fill.clicked.connect(self.canvas.fill_all)
        g_edit.addWidget(btn_fill, 2, 1)

        btn_undo = QPushButton(tr("be_btn_undo"))
        btn_undo.clicked.connect(self.canvas.undo)
        g_edit.addWidget(btn_undo, 3, 0)

        btn_redo = QPushButton(tr("be_btn_redo"))
        btn_redo.clicked.connect(self.canvas.redo)
        g_edit.addWidget(btn_redo, 3, 1)

        layout.addWidget(grp_edit)

        # --- 4. 보기 모드 (View Modes) ---
        grp_view = QGroupBox(tr("be_grp_view"))
        v_view = QVBoxLayout(grp_view)

        self.combo_view = QComboBox()
        self.combo_view.addItem(tr("be_view_overlay"), MaskCanvas.VIEW_OVERLAY)
        self.combo_view.addItem(tr("be_view_matte"), MaskCanvas.VIEW_MATTE)
        self.combo_view.addItem(tr("be_view_cutout"), MaskCanvas.VIEW_CUTOUT)
        self.combo_view.addItem(tr("be_view_rgb"), MaskCanvas.VIEW_RGB)
        self.combo_view.currentIndexChanged.connect(self._on_view_mode_changed)
        v_view.addWidget(self.combo_view)

        h_zoom = QHBoxLayout()
        btn_fit = QPushButton(tr("be_btn_fit"))
        btn_fit.clicked.connect(self.canvas.zoom_to_fit)
        btn_100 = QPushButton(tr("be_btn_100"))
        btn_100.clicked.connect(self.canvas.zoom_100)
        h_zoom.addWidget(btn_fit)
        h_zoom.addWidget(btn_100)
        v_view.addLayout(h_zoom)

        layout.addWidget(grp_view)

        # --- 5. 상태 및 정보 ---
        self.lbl_stats = QLabel("Mask Area: 0.0%  ·  0 × 0")
        self.lbl_stats.setStyleSheet("color:#8ea3be; font-size:11px;")
        layout.addWidget(self.lbl_stats)

        layout.addStretch()

        # --- 6. 액션 버튼 (적용 및 내보내기) ---
        grp_action = QGroupBox(tr("be_grp_action"))
        v_action = QVBoxLayout(grp_action)

        self.btn_apply_hint = QPushButton(tr("be_btn_apply"))
        self.btn_apply_hint.setStyleSheet(
            "background:#1b8061; color:#ffffff; font-weight:bold; font-size:13px; padding:10px; border-radius:6px;"
        )
        self.btn_apply_hint.setToolTip(tr("be_btn_apply_tip"))
        self.btn_apply_hint.clicked.connect(self.apply_as_first_frame_hint)
        v_action.addWidget(self.btn_apply_hint)

        h_exports = QHBoxLayout()
        btn_export_mask = QPushButton(tr("be_btn_export_mask"))
        btn_export_mask.clicked.connect(self.export_mask_file)
        btn_export_cutout = QPushButton(tr("be_btn_export_cutout"))
        btn_export_cutout.clicked.connect(self.export_cutout_file)
        h_exports.addWidget(btn_export_mask)
        h_exports.addWidget(btn_export_cutout)
        v_action.addLayout(h_exports)

        btn_import_mask = QPushButton(tr("be_btn_import"))
        btn_import_mask.clicked.connect(self.import_mask_file)
        v_action.addWidget(btn_import_mask)

        layout.addWidget(grp_action)

        return container

    # -------------------------------------------------------------------------
    # UI Event Handlers
    # -------------------------------------------------------------------------
    def _select_tool(self, mode: int):
        self.canvas.tool_mode = mode
        # Adjust button styles
        for btn in [self.btn_brush, self.btn_eraser, self.btn_rect_add, self.btn_rect_sub]:
            btn.setChecked(False)
            btn.setStyleSheet("")

        active_btn = {
            MaskCanvas.MODE_BRUSH: self.btn_brush,
            MaskCanvas.MODE_ERASER: self.btn_eraser,
            MaskCanvas.MODE_RECT_ADD: self.btn_rect_add,
            MaskCanvas.MODE_RECT_SUB: self.btn_rect_sub,
        }.get(mode, self.btn_brush)

        active_btn.setChecked(True)
        active_btn.setStyleSheet("font-weight: bold; background:#24695c;")
        self.canvas.update()

    def _on_size_changed(self, val: int):
        self.canvas.brush_size = val
        self.lbl_size.setText(f"{val} px")
        self.canvas.update()

    def _on_hardness_changed(self, val: int):
        self.canvas.brush_hardness = val / 100.0
        self.lbl_hardness.setText(f"{val} %")
        self.canvas.update()

    def _on_opacity_changed(self, val: int):
        self.canvas.brush_opacity = val / 100.0
        self.lbl_opacity.setText(f"{val} %")
        self.canvas.update()

    def _on_view_mode_changed(self, idx: int):
        mode = self.combo_view.itemData(idx)
        self.canvas.view_mode = mode
        self.canvas.update()

    def _update_stats(self):
        if self.canvas.mask is not None:
            w = self.canvas.width_img
            h = self.canvas.height_img
            # % of non-zero mask pixels
            covered = np.count_nonzero(self.canvas.mask > 10)
            total = w * h
            pct = (covered / max(1, total)) * 100.0
            self.lbl_stats.setText(tr("be_lbl_stats", pct=pct, w=w, h=h))
            self.lbl_size.setText(f"{self.canvas.brush_size} px")
            self.slider_size.blockSignals(True)
            self.slider_size.setValue(self.canvas.brush_size)
            self.slider_size.blockSignals(False)

    def _update_coords(self, x: int, y: int):
        pass

    # -------------------------------------------------------------------------
    # Actions: Apply, Export, Import
    # -------------------------------------------------------------------------
    def apply_as_first_frame_hint(self):
        """Save mask to companion FrameHint.png and emit signal to main GUI."""
        if self.canvas.mask is None:
            QMessageBox.warning(self, tr("msg_error"), tr("be_msg_no_mask"))
            return

        # Convention: <clip_name>FrameHint.png
        safe_name = Path(self.clip_name).stem
        target_path = self.output_hint_dir / f"{safe_name}FrameHint.png"

        try:
            # Save 8-bit single channel grayscale PNG
            ok, enc = cv2.imencode(".png", self.canvas.mask)
            if ok:
                target_path.write_bytes(enc.tobytes())
                self.saved_mask_path = str(target_path.resolve())
                self.applied_hint.emit(self.saved_mask_path)
                if QGuiApplication.platformName() != "offscreen":
                    # Non-blocking notification or simple accepted status
                    pass
                self.accept()
            else:
                raise RuntimeError("PNG encoding failed")
        except Exception as exc:
            QMessageBox.critical(self, tr("msg_error"), tr("be_msg_save_fail", exc=str(exc)))

    def export_mask_file(self):
        """Export mask as standalone PNG image."""
        if self.canvas.mask is None:
            return
        default_name = f"{Path(self.clip_name).stem}_mask.png"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("be_dlg_save_mask"),
            str(self.output_hint_dir / default_name),
            "PNG Image (*.png);;TIFF Image (*.tif *.tiff)"
        )
        if path:
            try:
                ok, enc = cv2.imencode(".png", self.canvas.mask)
                if ok:
                    Path(path).write_bytes(enc.tobytes())
                    QMessageBox.information(self, tr("msg_save_complete"), tr("be_msg_save_done", path=path))
            except Exception as exc:
                QMessageBox.critical(self, tr("msg_error"), tr("be_msg_save_err", exc=str(exc)))

    def export_cutout_file(self):
        """Export selected foreground as transparent RGBA PNG."""
        if self.canvas.mask is None or self.canvas.source_rgb is None:
            return
        default_name = f"{Path(self.clip_name).stem}_cutout.png"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("be_dlg_save_cutout"),
            str(self.output_hint_dir / default_name),
            "PNG Transparent Image (*.png)"
        )
        if path:
            try:
                # Build BGRA
                bgr = cv2.cvtColor(self.canvas.source_rgb, cv2.COLOR_RGB2BGR)
                bgra = np.dstack([bgr, self.canvas.mask])
                ok, enc = cv2.imencode(".png", bgra)
                if ok:
                    Path(path).write_bytes(enc.tobytes())
                    QMessageBox.information(self, tr("msg_export_complete"), tr("be_msg_cutout_done", path=path))
            except Exception as exc:
                QMessageBox.critical(self, tr("msg_error"), tr("be_msg_cutout_err", exc=str(exc)))

    def import_mask_file(self):
        """Load external mask image."""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("be_dlg_import_mask"),
            str(self.output_hint_dir),
            "Images (*.png *.jpg *.jpeg *.exr *.tif *.tiff)"
        )
        if path and Path(path).is_file():
            try:
                loaded = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                if loaded is not None:
                    if loaded.ndim == 3:
                        if loaded.shape[2] == 4:
                            loaded = loaded[:, :, 3]
                        else:
                            loaded = cv2.cvtColor(loaded, cv2.COLOR_BGR2GRAY)
                    # Resize if size does not match
                    if loaded.shape[:2] != (self.canvas.height_img, self.canvas.width_img):
                        loaded = cv2.resize(
                            loaded, (self.canvas.width_img, self.canvas.height_img),
                            interpolation=cv2.INTER_NEAREST
                        )
                    self.canvas.history.push(self.canvas.mask)
                    self.canvas.mask = loaded.astype(np.uint8)
                    self.canvas.update()
                    self._update_stats()
            except Exception as exc:
                QMessageBox.warning(self, tr("msg_load_fail"), tr("be_msg_import_fail", exc=str(exc)))

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog { background: #161b22; color: #e6edf3; font-family: 'Segoe UI', 'Malgun Gothic', sans-serif; }
            QGroupBox { border: 1px solid #30363d; border-radius: 6px; margin-top: 10px; padding-top: 10px; font-weight: bold; color: #58a6ff; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
            QPushButton { background: #21262d; border: 1px solid #363b42; border-radius: 5px; padding: 6px 12px; color: #c9d1d9; font-size: 12px; }
            QPushButton:hover { background: #30363d; border-color: #8b949e; }
            QPushButton:pressed { background: #161b22; }
            QComboBox { background: #0d1117; border: 1px solid #30363d; border-radius: 5px; padding: 5px; color: #c9d1d9; }
            QSlider::groove:horizontal { height: 4px; background: #30363d; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #238636; border-radius: 2px; }
            QSlider::handle:horizontal { width: 14px; margin-top: -5px; margin-bottom: -5px; border-radius: 7px; background: #58a6ff; }
        """)
