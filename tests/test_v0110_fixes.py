import os
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestV0110Fixes(unittest.TestCase):
    def test_natural_sort_frame_paths(self):
        from corridorkey.video_io import frame_paths
        import gui

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            for idx in (1, 2, 10, 11, 3):
                (d / f"shot_{idx}.png").write_bytes(b"fake")
            res_io = [Path(p).name for p in frame_paths(d)]
            res_gui = [p.name for p in gui._list_sequence_frames(d)]
            expected = ["shot_1.png", "shot_2.png", "shot_3.png", "shot_10.png", "shot_11.png"]
            self.assertEqual(res_io, expected)
            self.assertEqual(res_gui, expected)

    def test_probe_frame_dir_start_offset_and_linear_adjust(self):
        from corridorkey.video_io import probe_frame_dir_meta

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            img = np.zeros((64, 64, 3), dtype=np.uint8)
            for idx in range(1, 6):
                cv2.imwrite(str(d / f"plate_{idx:04d}.png"), img)

            meta = probe_frame_dir_meta(
                str(d),
                num_frames=2,
                shape_quantum=128,
                fps=24.0,
                exr_linear=False,
                model_scale=1.0,
                start_offset=2,
                linear_brightness=1.5,
                linear_contrast=1.2,
                linear_contrast_pivot=0.18,
            )
            self.assertEqual(meta["num_frames"], 2)
            self.assertEqual(meta["start_frame"], 3)
            self.assertEqual([Path(p).name for p in meta["frame_paths"]], ["plate_0003.png", "plate_0004.png"])
            self.assertAlmostEqual(meta["linear_brightness"], 1.5)
            self.assertAlmostEqual(meta["linear_contrast"], 1.2)

    def test_exr_sequence_writer_unicode_path(self):
        from corridorkey.video_io import ExrSequenceWriter

        with tempfile.TemporaryDirectory() as td:
            unicode_dir = Path(td) / "한글_EXR_출력"
            writer = ExrSequenceWriter(
                str(unicode_dir),
                fps=24.0,
                size=(32, 32),
                channels=3,
                dtype="half",
                frame_name="fg",
                start_frame=1001,
            )
            batch = np.zeros((2, 32, 32, 3), dtype=np.float32)
            writer.write_many(batch)
            writer.release()

            self.assertTrue((unicode_dir / "fg_001001.exr").is_file())
            self.assertTrue((unicode_dir / "fg_001002.exr").is_file())

    def test_nuke_build_command_args_offset_and_frames(self):
        from nuke import corridorkey_nuke

        cmd = corridorkey_nuke.build_command_args(
            ck_root=ROOT,
            python_exe=Path(sys.executable),
            input_path="plate.mp4",
            output_dir="out_dir",
            start_frame=1010,
            start_offset=9,
            num_frames=1,
        )
        self.assertIn("--start_frame", cmd)
        self.assertEqual(cmd[cmd.index("--start_frame") + 1], "1010")
        self.assertIn("--start_offset", cmd)
        self.assertEqual(cmd[cmd.index("--start_offset") + 1], "9")
        self.assertIn("--num_frames", cmd)
        self.assertEqual(cmd[cmd.index("--num_frames") + 1], "1")

    def test_fusion_ck_root_defined_before_hint_lookup(self):
        fusion_src = (ROOT / "resolve" / "fusion" / "corridorkey_fusion.py").read_text(encoding="utf-8")
        idx_def = fusion_src.find("ck_root = find_corridorkey_root()")
        idx_use = fusion_src.find('ck_root / "outputs"')
        self.assertGreater(idx_def, 0)
        self.assertGreater(idx_use, 0)
        self.assertLess(idx_def, idx_use)

    def test_gui_detect_matched_exr_results_and_listener_cleanup(self):
        from PySide6.QtWidgets import QApplication
        import gui
        import i18n
        import model_manager

        app = QApplication.instance() or QApplication([])

        # 1. Verify ModelManagerDialog cleans up its language listener on close
        before = len(i18n._listeners)
        dlg = model_manager.ModelManagerDialog()
        self.assertEqual(len(i18n._listeners), before + 1)
        dlg.close()
        self.assertEqual(len(i18n._listeners), before)

        # 2. Verify _detect_matched_results finds EXR sequence folders
        win = gui.Window()
        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td)
            run_dir = out_root / "shot01_20261124_150000_abc123"
            cutout_dir = run_dir / "shot01_cutout_exr"
            alpha_dir = run_dir / "shot01_alpha_exr"
            cutout_dir.mkdir(parents=True)
            alpha_dir.mkdir(parents=True)
            (cutout_dir / "cutout_000001.exr").write_bytes(b"exr")
            (alpha_dir / "alpha_000001.exr").write_bytes(b"exr")

            win.output.setText(str(out_root))
            win.destination = None
            win._detect_matched_results(Path("shot01.mp4"))
            self.assertEqual(win.matched_results.get("comp"), cutout_dir)
            self.assertEqual(win.matched_results.get("alpha"), alpha_dir)
        win.close()


if __name__ == "__main__":
    unittest.main()
