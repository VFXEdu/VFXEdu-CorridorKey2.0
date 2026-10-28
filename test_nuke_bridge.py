#!/usr/bin/env python3
"""Unit tests for CorridorKey 2.0 Nuke Bridge."""

import os
from pathlib import Path
import sys
import unittest

# Add nuke folder to sys.path
NUKE_DIR = Path(__file__).resolve().parent / "nuke"
if str(NUKE_DIR) not in sys.path:
    sys.path.insert(0, str(NUKE_DIR))

import corridorkey_nuke


class TestNukeBridge(unittest.TestCase):
    def test_find_root_and_python(self):
        root = corridorkey_nuke.find_corridorkey_root()
        self.assertIsNotNone(root)
        self.assertTrue((root / "infer.py").is_file())

        py_exe = corridorkey_nuke.find_python_executable(root)
        self.assertIsNotNone(py_exe)
        self.assertTrue(py_exe.is_file())

    def test_build_command_args_default(self):
        root = corridorkey_nuke.find_corridorkey_root()
        py_exe = corridorkey_nuke.find_python_executable(root)

        cmd = corridorkey_nuke.build_command_args(
            ck_root=root,
            python_exe=py_exe,
            input_path="D:/plates/shot_01",
            output_dir="D:/renders",
            output_format="exr",
            exr_dtype="half",
            despill_strength=0.75,
            auto_vram=True,
            low_vram=False,
            linear_workflow=True,
        )

        self.assertEqual(cmd[0], str(py_exe))
        self.assertEqual(cmd[1], str(root / "infer.py"))
        self.assertIn("--input", cmd)
        self.assertIn("D:/plates/shot_01", cmd)
        self.assertIn("--output_dir", cmd)
        self.assertIn("D:/renders", cmd)
        self.assertIn("--output_format", cmd)
        self.assertIn("exr", cmd)
        self.assertIn("--exr_dtype", cmd)
        self.assertIn("half", cmd)
        self.assertIn("--despill_strength", cmd)
        self.assertIn("0.75", cmd)
        self.assertIn("--frame_dir_linear", cmd)
        self.assertIn("--cutout_linear", cmd)
        self.assertNotIn("--low_vram", cmd)

    def test_build_command_args_advanced(self):
        root = corridorkey_nuke.find_corridorkey_root()
        py_exe = corridorkey_nuke.find_python_executable(root)

        # Create dummy hint file
        dummy_hint = Path(root) / "tmp" / "_test_hint.png"
        dummy_hint.parent.mkdir(parents=True, exist_ok=True)
        dummy_hint.touch()

        try:
            cmd = corridorkey_nuke.build_command_args(
                ck_root=root,
                python_exe=py_exe,
                input_path="D:/video.mp4",
                output_dir="D:/renders",
                output_format="video",
                despill_strength=0.3,
                auto_vram=False,
                low_vram=True,
                hann_chunk=24,
                hann_stride=12,
                hint_first_frame=str(dummy_hint),
                carry_hint=False,
                hint_quality=0.90,
                linear_workflow=False,
            )

            self.assertIn("--low_vram", cmd)
            self.assertIn("--hann_chunk", cmd)
            self.assertIn("24", cmd)
            self.assertIn("--hann_stride", cmd)
            self.assertIn("12", cmd)
            self.assertIn("--hint_first_frame", cmd)
            self.assertIn(str(dummy_hint), cmd)
            self.assertIn("--no_carry_hint", cmd)
            self.assertIn("0.90", cmd)
            self.assertNotIn("--frame_dir_linear", cmd)
        finally:
            if dummy_hint.exists():
                dummy_hint.unlink()


if __name__ == "__main__":
    unittest.main()
