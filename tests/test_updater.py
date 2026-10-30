"""Unit tests for CorridorKey 2.0 Auto-Updater."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import zipfile

import pytest
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.updater import (
    DEFAULT_REPO,
    EXCLUDE_EXTENSIONS,
    PROTECTED_PATTERNS,
    apply_code_update,
    get_configured_github_repo,
    is_newer_version,
    parse_version_tuple,
)


class TestUpdaterCore:
    """Core logic tests for version parsing and comparison."""

    def test_parse_version_tuple(self):
        assert parse_version_tuple("v0.1.1") == (0, 1, 1)
        assert parse_version_tuple("0.1.2") == (0, 1, 2)
        assert parse_version_tuple("v1.0.0") == (1, 0, 0)
        assert parse_version_tuple("v0.1.10") == (0, 1, 10)
        assert parse_version_tuple("invalid") == (0,)

    def test_is_newer_version(self):
        assert is_newer_version("v0.1.2", "v0.1.1") is True
        assert is_newer_version("v0.1.10", "v0.1.2") is True
        assert is_newer_version("v1.0.0", "v0.9.9") is True
        assert is_newer_version("v0.1.1", "v0.1.1") is False
        assert is_newer_version("v0.1.0", "v0.1.1") is False
        assert is_newer_version("v0.0.9", "v0.1.0") is False

    def test_repo_configured_fallback(self):
        repo = get_configured_github_repo()
        assert repo is not None
        assert "/" in repo
        assert "VFXEdu" in repo

    def test_protected_patterns_defined(self):
        assert "weights" in PROTECTED_PATTERNS
        assert "vfms" in PROTECTED_PATTERNS
        assert "venv" in PROTECTED_PATTERNS
        assert "python_embed" in PROTECTED_PATTERNS
        assert ".git" in PROTECTED_PATTERNS
        assert "gui_config.json" in PROTECTED_PATTERNS

        assert ".safetensors" in EXCLUDE_EXTENSIONS
        assert ".pth" in EXCLUDE_EXTENSIONS
        assert ".pt" in EXCLUDE_EXTENSIONS


class TestUpdateApplication:
    """Test incremental patching and protective filters."""

    def test_apply_code_update_protection(self, tmp_path):
        target_dir = tmp_path / "app"
        target_dir.mkdir()

        # Existing files
        (target_dir / "gui.py").write_text("APP_VERSION = 'v0.1.1'", encoding="utf-8")
        (target_dir / "gui_config.json").write_text('{"language": "ko"}', encoding="utf-8")

        # Create a mock GitHub release zipball
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Simulated updated files inside top-level archive directory
            zf.writestr("VFXEdu-CorridorKey2.0-master/gui.py", "APP_VERSION = 'v0.1.2'")
            zf.writestr("VFXEdu-CorridorKey2.0-master/new_tool.py", "print('hello from new tool')")

            # Protected files that MUST NOT overwrite or create
            zf.writestr("VFXEdu-CorridorKey2.0-master/gui_config.json", '{"language": "en"}')
            zf.writestr("VFXEdu-CorridorKey2.0-master/weights/big_model.safetensors", "FAKE_MODEL_BYTES")
            zf.writestr("VFXEdu-CorridorKey2.0-master/python_embed/new_bin.dll", "FAKE_DLL")

        zip_path = tmp_path / "mock_update.zip"
        zip_path.write_bytes(zip_buf.getvalue())

        progress_log = []

        def on_prog(pct, msg):
            progress_log.append((pct, msg))

        # Apply using file:/// URI as zip_url
        ok, msg = apply_code_update(
            zip_url=zip_path.as_uri(),
            target_dir=target_dir,
            progress_callback=on_prog,
        )

        assert ok is True
        assert len(progress_log) > 0

        # Verify updated files
        assert (target_dir / "gui.py").read_text(encoding="utf-8") == "APP_VERSION = 'v0.1.2'"
        assert (target_dir / "new_tool.py").is_file()

        # Verify protected files were NOT touched
        assert (target_dir / "gui_config.json").read_text(encoding="utf-8") == '{"language": "ko"}'
        assert not (target_dir / "weights" / "big_model.safetensors").exists()
        assert not (target_dir / "python_embed" / "new_bin.dll").exists()


class TestUpdateUIComponents:
    """Test PySide6 UpdateDialog & Workers."""

    def test_update_dialog_instantiation(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtWidgets import QApplication
        import gui

        app = QApplication.instance() or QApplication([])

        mock_info = {
            "update_available": True,
            "latest_version": "v0.1.2",
            "current_version": "v0.1.1",
            "release_name": "CorridorKey 2.0 v0.1.2 Feature Release",
            "release_notes": "Added Resolve Fuse and Nuke Gizmo auto-updates.",
            "release_url": "https://github.com/VFXEdu/VFXEdu-CorridorKey2.0/releases/tag/v0.1.2",
            "zipball_url": "https://github.com/VFXEdu/VFXEdu-CorridorKey2.0/archive/refs/tags/v0.1.2.zip",
            "error": None,
        }

        dlg = gui.UpdateDialog(None, initial_info=mock_info)
        assert dlg.info["update_available"] is True
        assert dlg.btn_apply.isEnabled() is True
        assert "v0.1.2" in dlg.lbl_status_badge.text()
        assert "Resolve Fuse" in dlg.text_notes.toPlainText()

        # Up-to-date state
        mock_up_to_date = {
            "update_available": False,
            "latest_version": "v0.1.1",
            "current_version": "v0.1.1",
            "release_name": "",
            "release_notes": "",
            "release_url": "https://github.com/VFXEdu/VFXEdu-CorridorKey2.0",
            "zipball_url": "",
            "error": None,
        }
        dlg2 = gui.UpdateDialog(None, initial_info=mock_up_to_date)
        assert dlg2.btn_apply.isEnabled() is False
