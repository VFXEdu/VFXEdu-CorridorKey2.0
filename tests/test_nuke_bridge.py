#!/usr/bin/env python3
"""Unit tests for CorridorKey 2.0 Nuke Bridge."""

import os
from pathlib import Path
import sys
import unittest

# Add nuke folder to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
NUKE_DIR = ROOT / "nuke"
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

    def test_build_command_args_hint_video(self):
        root = corridorkey_nuke.find_corridorkey_root()
        py_exe = corridorkey_nuke.find_python_executable(root)

        dummy_seq_dir = Path(root) / "tmp" / "_test_hint_seq"
        dummy_seq_dir.mkdir(parents=True, exist_ok=True)

        try:
            cmd = corridorkey_nuke.build_command_args(
                ck_root=root,
                python_exe=py_exe,
                input_path="D:/plates/shot_02",
                output_dir="D:/renders",
                hint_video=str(dummy_seq_dir),
                hint_quality=0.85,
            )
            self.assertIn("--hint_video", cmd)
            self.assertIn(str(dummy_seq_dir), cmd)
            self.assertIn("--hint_quality", cmd)
            self.assertIn("0.85", cmd)
        finally:
            if dummy_seq_dir.exists():
                import shutil
                shutil.rmtree(dummy_seq_dir, ignore_errors=True)

    def test_offline_utility_stubs(self):
        # Verify offline executions safely return without throwing exceptions
        self.assertIsNone(corridorkey_nuke.open_output_folder(None))
        self.assertIsNone(corridorkey_nuke.reload_reads(None))
        self.assertFalse(corridorkey_nuke.execute_keyer(None))
        self.assertIsNone(corridorkey_nuke.create_corridorkeyer_node())


if __name__ == "__main__":
    unittest.main()
