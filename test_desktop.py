"""Offscreen GUI integration checks; testing all CorridorKey 2.0 desktop features."""
from __future__ import annotations

import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import tempfile
import time
from pathlib import Path
import unittest

import cv2
import numpy as np

from PySide6.QtCore import QPointF, QProcess
from PySide6.QtWidgets import QApplication

import gui
from mask_editor import MaskCanvas, BrushMaskEditorDialog

APP = QApplication.instance() or QApplication([])


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError('Timed out')


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.w = gui.Window()
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name) / '한글 공백 영상.mp4'
        self.source.touch()

    def tearDown(self):
        if self.w.proc.state() != QProcess.NotRunning:
            self.w.proc.kill()
            self.w.proc.waitForFinished(5000)
        self.w.close()
        self.temp.cleanup()

    def test_arguments_preserve_unicode_and_automatic_memory(self):
        options = self.w.options()
        args = gui.make_arguments(self.source, Path(self.temp.name), options)
        self.assertEqual(args[args.index('--input') + 1], str(self.source))
        self.assertNotIn('--hann_chunk', args)

        # low_vram triggers default 8/4 window when hann_mode is auto
        options['low_vram'] = True
        args = gui.make_arguments(self.source, Path(self.temp.name), options)
        self.assertEqual(args[args.index('--hann_chunk') + 1], '8')
        self.assertEqual(args[args.index('--hann_stride') + 1], '4')
        self.assertIn('--low_vram', args)

        options['outputs'] = []
        with self.assertRaises(ValueError):
            gui.make_arguments(self.source, Path(self.temp.name), options)

    def test_all_missing_corridorkey_features_in_arguments(self):
        """Verify that all CorridorKey 2.0 CLI flags are correctly produced."""
        options = self.w.options()
        # Custom Hann Window
        options['hann_mode'] = 'custom'
        options['hann_chunk'] = 64
        options['hann_stride'] = 32

        # Model Scale & Stage 2 batch
        options['model_scale'] = 0.75
        options['stage2_batch'] = 2

        # Hints & Carry
        hint_dummy = Path(self.temp.name) / 'mask_hint.png'
        hint_dummy.touch()
        options['hint_mode'] = '--hint_first_frame'
        options['hint'] = str(hint_dummy)
        options['quality'] = 0.90
        options['carry_hint_quality'] = 0.80
        options['no_carry_hint'] = True

        # VFX Linear Compositing
        options['cutout_linear'] = True
        options['format'] = 'exr'
        options['exr_dtype'] = 'float'

        # Linear Color Tuning
        options['linear_brightness'] = 1.25
        options['linear_contrast'] = 1.15
        options['linear_contrast_pivot'] = 0.20

        # Video/Seq controls
        options['frames'] = 50
        options['start'] = 'random_middle'
        options['seed'] = 42

        dest = Path(self.temp.name) / 'out'
        args = gui.make_arguments(self.source, dest, options)

        # Check Hann
        self.assertEqual(args[args.index('--hann_chunk') + 1], '64')
        self.assertEqual(args[args.index('--hann_stride') + 1], '32')

        # Check Scale & Stage 2
        self.assertEqual(args[args.index('--model_scale') + 1], '0.75')
        self.assertEqual(args[args.index('--stage2_batch') + 1], '2')

        # Check Hints
        self.assertIn('--hint_first_frame', args)
        self.assertEqual(args[args.index('--hint_first_frame') + 1], str(hint_dummy))
        self.assertEqual(args[args.index('--hint_quality') + 1], '0.9')
        self.assertEqual(args[args.index('--carry_hint_quality') + 1], '0.8')
        self.assertIn('--no_carry_hint', args)

        # Check Linear VFX & EXR
        self.assertIn('--cutout_linear', args)
        self.assertEqual(args[args.index('--output_format') + 1], 'exr')
        self.assertEqual(args[args.index('--exr_dtype') + 1], 'float')

        # Check Linear Color
        self.assertEqual(args[args.index('--linear_brightness') + 1], '1.25')
        self.assertEqual(args[args.index('--linear_contrast') + 1], '1.15')
        self.assertEqual(args[args.index('--linear_contrast_pivot') + 1], '0.2')

        # Check Range
        self.assertEqual(args[args.index('--num_frames') + 1], '50')
        self.assertEqual(args[args.index('--start_mode') + 1], 'random_middle')
        self.assertEqual(args[args.index('--seed') + 1], '42')

    def test_companion_hint_auto_detection(self):
        """Verify automatic detection and binding of <clip>FrameHint.png."""
        clip_file = Path(self.temp.name) / 'vfx_shot.mp4'
        clip_file.touch()
        companion_hint = Path(self.temp.name) / 'vfx_shotFrameHint.png'
        companion_hint.touch()

        self.w.add_paths([str(clip_file)])
        self.assertEqual(self.w.queue.count(), 1)
        # Should auto-select first frame hint mode and set path
        self.assertEqual(self.w.hint_mode.currentData(), '--hint_first_frame')
        self.assertEqual(Path(self.w.hint.text()).resolve(), companion_hint.resolve())

    def test_brush_mask_editor_and_canvas_operations(self):
        """Test the interactive Brush Mask Canvas drawing, undo/redo, feathering, and cutout extraction."""
        test_rgb = np.full((100, 150, 3), 120, dtype=np.uint8)
        # Add a fake object
        test_rgb[20:80, 30:120] = (255, 100, 50)

        canvas = MaskCanvas()
        canvas.set_image(test_rgb)
        self.assertEqual(canvas.mask.shape, (100, 150))
        self.assertEqual(np.count_nonzero(canvas.mask), 0)

        # 1. Paint stroke
        canvas.history.push(canvas.mask)
        canvas.brush_size = 20
        canvas.brush_hardness = 0.8
        canvas.paint_stroke(QPointF(30, 30), QPointF(90, 70))
        painted_pixels = np.count_nonzero(canvas.mask > 0)
        self.assertGreater(painted_pixels, 100)

        # 2. Undo
        canvas.undo()
        self.assertEqual(np.count_nonzero(canvas.mask), 0)

        # 3. Redo
        canvas.redo()
        self.assertEqual(np.count_nonzero(canvas.mask > 0), painted_pixels)

        # 4. Dilate & Erode
        canvas.dilate_mask(3)
        self.assertGreater(np.count_nonzero(canvas.mask > 0), painted_pixels)
        canvas.erode_mask(3)

        # 5. Dialog initialization and direct hint apply
        out_hint_dir = Path(self.temp.name) / 'hints'
        editor = BrushMaskEditorDialog(
            rgb_image=test_rgb,
            clip_name='shot01',
            output_hint_dir=out_hint_dir
        )
        editor.canvas.fill_all()
        self.assertEqual(np.count_nonzero(editor.canvas.mask == 255), 100 * 150)

        # Trigger apply_as_first_frame_hint
        editor.apply_as_first_frame_hint()
        saved_hint_file = out_hint_dir / 'shot01FrameHint.png'
        self.assertTrue(saved_hint_file.is_file())

        # Verify saved PNG
        loaded = cv2.imread(str(saved_hint_file), cv2.IMREAD_GRAYSCALE)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.shape, (100, 150))
        self.assertEqual(np.count_nonzero(loaded == 255), 100 * 150)

    def test_process_success_and_failure(self):
        self.w.launch(['-u', '-c', "print('실행 확인')"], 'check')
        wait_until(lambda: self.w.run_button.isEnabled())
        self.assertTrue('passed' in self.w.status.text().lower() or '통과' in self.w.status.text())
        self.assertIn('실행 확인', self.w.log.toPlainText())
        self.w.launch(['-c', 'raise RuntimeError("expected failure")'], 'check')
        wait_until(lambda: self.w.run_button.isEnabled())
        self.assertTrue('failed' in self.w.status.text().lower() or '실패' in self.w.status.text())

    def test_cancel_process_tree(self):
        marker = Path(self.temp.name) / 'child.pid'
        child_code = 'import time; time.sleep(60)'
        code = f'import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c",{child_code!r}]); Path({str(marker)!r}).write_text(str(p.pid)); time.sleep(60)'
        self.w.launch(['-u', '-c', code], 'check')
        wait_until(marker.exists)
        child_pid = int(marker.read_text())
        self.w.stop()
        wait_until(lambda: self.w.run_button.isEnabled())
        self.assertTrue('stopped' in self.w.status.text().lower() or '중지' in self.w.status.text())
        if os.name == 'nt':
            import ctypes
            kernel = ctypes.windll.kernel32
            handle = kernel.OpenProcess(0x1000, False, child_pid)
            if handle:
                result = ctypes.c_ulong()
                kernel.GetExitCodeProcess(handle, ctypes.byref(result))
                kernel.CloseHandle(handle)
                self.assertNotEqual(result.value, 259, 'Child process still active')

    def test_about_license_dialog(self):
        dlg = gui.AboutLicenseDialog(self.w)
        self.assertIsNotNone(dlg)
        self.assertIn('CorridorKey 2.0', dlg.windowTitle())
        self.assertEqual(self.w.lbl_version.text(), 'v0.1.1')
        self.assertIn('v0.1.1', self.w.windowTitle())
        self.assertIn('VFXEdu', self.w.windowTitle())

    def test_language_switch_and_persistence(self):
        """Test switching language between English and Korean, verifying UI labels update dynamically."""
        from i18n import get_language, LANG_EN, LANG_KO, tr, set_language

        # 1. Verify / set baseline is English
        idx_en0 = self.w.combo_lang.findData(LANG_EN)
        if idx_en0 >= 0:
            self.w.combo_lang.setCurrentIndex(idx_en0)
        self.assertEqual(get_language(), LANG_EN)
        self.assertEqual(self.w.btn_about.text(), tr('btn_about'))
        self.assertIn('Input', self.w.grp_queue.title())

        # 2. Switch to Korean
        idx_ko = self.w.combo_lang.findData(LANG_KO)
        self.assertGreaterEqual(idx_ko, 0)
        self.w.combo_lang.setCurrentIndex(idx_ko)

        self.assertEqual(get_language(), LANG_KO)
        self.assertIn('대기열', self.w.grp_queue.title())
        self.assertIn('정보', self.w.btn_about.text())

        # 3. Switch back to English
        idx_en = self.w.combo_lang.findData(LANG_EN)
        self.w.combo_lang.setCurrentIndex(idx_en)

        self.assertEqual(get_language(), LANG_EN)
        self.assertIn('Input', self.w.grp_queue.title())
        self.assertIn('About', self.w.btn_about.text())

    def test_queue_and_preview(self):
        video = Path(self.temp.name) / 'sample.mp4'
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 24, (320, 180))
        for i in range(4):
            writer.write(np.full((180, 320, 3), (0, 160, i * 50), dtype=np.uint8))
        writer.release()
        self.w.add_paths([str(video), str(video)])
        self.assertEqual(self.w.queue.count(), 1)
        self.assertIsNotNone(self.w.original.pixmap)
        self.assertEqual(self.w.original.slider.maximum(), 3)
        self.w.original.slider.setValue(3)
        self.assertTrue('frame 4' in self.w.original.caption.text().lower() or '프레임 4' in self.w.original.caption.text())

    def test_rgvi_clean_plate_integration(self):
        """Test RGVI options handling and clean plate argument generation."""
        self.w.outputs['clean_plate'].setChecked(True)
        self.w.outputs['alpha'].setChecked(False)
        self.w.outputs['checker'].setChecked(False)
        opts = self.w.options()
        self.assertTrue(opts['clean_plate'])
        self.assertIn('alpha', opts['outputs'])

        dest = Path(self.temp.name) / 'rgvi_job'
        args = gui.make_arguments(self.source, dest, opts)
        self.assertIn('alpha', args[args.index('--outputs'):])

        # Test RGVIRemover import and initialization
        import inpaint_rgvi
        self.assertTrue(hasattr(inpaint_rgvi, 'remove_object_rgvi'))
        self.assertTrue(hasattr(inpaint_rgvi, 'RGVIRemover'))

    def test_model_manager_status_and_dialog(self):
        """Test model manager registry, status checks, and visual dialog components."""
        from model_manager import (
            check_model_status,
            are_required_models_installed,
            is_clean_plate_installed,
            ModelManagerDialog,
            MODEL_REGISTRY,
        )

        st = check_model_status()
        self.assertEqual(len(st), len(MODEL_REGISTRY))
        self.assertIn('corridorkey', st)
        self.assertIn('cradio', st)
        self.assertIn('moge', st)
        self.assertIn('rvm', st)
        self.assertIn('rgvi', st)

        self.assertTrue(are_required_models_installed())
        self.assertTrue(is_clean_plate_installed())

        # Test ModelManagerDialog instantiation
        dlg = ModelManagerDialog(self.w)
        self.assertIsNotNone(dlg)
        self.assertEqual(len(dlg.cards), len(MODEL_REGISTRY))
        self.assertTrue(hasattr(self.w, 'btn_models'))
        self.assertIn('Model', self.w.btn_models.text())
        dlg.close()

    def test_portable_distribution_components(self):
        """Verify Option A portable components: embedded python and bin/ffmpeg."""
        from corridorkey.video_io import find_ffmpeg, require_ffmpeg
        ffmpeg_p = find_ffmpeg()
        self.assertIsNotNone(ffmpeg_p)
        self.assertTrue(Path(ffmpeg_p).is_file())
        # require_ffmpeg should not raise
        require_ffmpeg("ffmpeg")

        root = Path(__file__).resolve().parent
        bin_ffmpeg = root / "bin" / "ffmpeg.exe"
        self.assertTrue(bin_ffmpeg.is_file(), "bin/ffmpeg.exe must exist in project")

        embed_python = root / "python_embed" / "python.exe"
        self.assertTrue(embed_python.is_file(), "python_embed/python.exe must exist")

        pth_file = list((root / "python_embed").glob("*._pth"))
        self.assertTrue(len(pth_file) > 0, "python_embed must contain a ._pth file")
        pth_text = pth_file[0].read_text(encoding="utf-8")
        self.assertIn("import site", pth_text)
        self.assertIn("Lib/site-packages", pth_text)


if __name__ == '__main__':
    unittest.main()
