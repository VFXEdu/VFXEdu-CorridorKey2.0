#!/usr/bin/env python3
"""Unit tests for CorridorKey 2.0 DaVinci Resolve Bridge."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RESOLVE_DIR = ROOT / "resolve"
if str(RESOLVE_DIR) not in sys.path:
    sys.path.insert(0, str(RESOLVE_DIR))

import corridorkey_resolve
import scripts.install_resolve as install_resolve


class TestResolveBridge(unittest.TestCase):
    def test_find_root_and_python(self):
        root = corridorkey_resolve.find_corridorkey_root()
        self.assertIsNotNone(root)
        self.assertTrue((root / "infer.py").is_file())

        py_exe = corridorkey_resolve.find_python_executable(root)
        self.assertIsNotNone(py_exe)
        self.assertTrue(py_exe.is_file())
        self.assertTrue(corridorkey_resolve._has_torch(py_exe))

    def test_resolve_script_dirs(self):
        dirs = install_resolve.get_resolve_script_dirs()
        self.assertIsInstance(dirs, list)
        self.assertGreater(len(dirs), 0)

    def test_stub_content_generation(self):
        root = corridorkey_resolve.find_corridorkey_root()
        stub = install_resolve.create_launcher_script_content(root)
        self.assertIn("corridorkey_resolve", stub)
        self.assertIn(root.as_posix(), stub)


if __name__ == "__main__":
    unittest.main()
