"""Patch files for Python 3.12 distutils compatibility."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SHIM_CODE = """
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
"""

def patch_foundations(filepath: Path):
    if not filepath.is_file():
        return
    text = filepath.read_text(encoding="utf-8")
    if "_ensure_distutils_shim" in text:
        print(f"[*] Already patched: {filepath}")
        return
    target = "import torch\nimport torch.nn as nn"
    crlf_target = "import torch\r\nimport torch.nn as nn"
    if crlf_target in text:
        text = text.replace(crlf_target, crlf_target + "\r\n" + SHIM_CODE.replace("\n", "\r\n"), 1)
    elif target in text:
        text = text.replace(target, target + "\n" + SHIM_CODE, 1)
    else:
        print(f"[!] Target not found in {filepath}")
        return
    filepath.write_text(text, encoding="utf-8")
    print(f"[+] Patched {filepath}")

def patch_infer(filepath: Path):
    if not filepath.is_file():
        return
    text = filepath.read_text(encoding="utf-8")
    if "_ensure_distutils_shim" in text:
        print(f"[*] Already patched: {filepath}")
        return
    target = 'os.environ["TRANSFORMERS_OFFLINE"] = "1"'
    crlf_target = 'os.environ["TRANSFORMERS_OFFLINE"] = "1"'
    if target in text:
        text = text.replace(target, target + "\n" + SHIM_CODE, 1)
    filepath.write_text(text, encoding="utf-8")
    print(f"[+] Patched {filepath}")

def patch_gui(filepath: Path):
    if not filepath.is_file():
        return
    text = filepath.read_text(encoding="utf-8")
    if "_ensure_distutils_shim" in text:
        print(f"[*] Already patched: {filepath}")
        return
    target = 'import sys'
    if target in text:
        text = text.replace(target, target + "\n" + SHIM_CODE, 1)
    filepath.write_text(text, encoding="utf-8")
    print(f"[+] Patched {filepath}")

def patch_extra_models(filepath: Path):
    if not filepath.is_file():
        return
    text = filepath.read_text(encoding="utf-8")
    target = "from distutils.version import LooseVersion"
    replacement = """try:
    from distutils.version import LooseVersion
except ImportError:
    try:
        from packaging.version import Version as LooseVersion
    except ImportError:
        class LooseVersion:
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
"""
    if target in text:
        text = text.replace(target, replacement, 1)
        filepath.write_text(text, encoding="utf-8")
        print(f"[+] Patched {filepath}")
    else:
        print(f"[*] Target already replaced in {filepath}")

def main():
    print("[*] Patching dev workspace...")
    patch_foundations(ROOT / "corridorkey" / "foundations.py")
    patch_infer(ROOT / "infer.py")
    patch_gui(ROOT / "gui.py")
    patch_extra_models(ROOT / "vfms" / "cradio" / "C-RADIOv4-SO400M" / "extra_models.py")

    user_portable = Path(r"K:\CorridorKey2.0\CorridorKey2.0_Portable_v0.1.1")
    if user_portable.exists():
        print(f"[*] Patching user extracted portable directory: {user_portable}...")
        patch_foundations(user_portable / "corridorkey" / "foundations.py")
        patch_infer(user_portable / "infer.py")
        patch_gui(user_portable / "gui.py")
        patch_extra_models(user_portable / "vfms" / "cradio" / "C-RADIOv4-SO400M" / "extra_models.py")

        pth_src = ROOT / "python_embed" / "Lib" / "site-packages" / "distutils-precedence.pth"
        pth_dst = user_portable / "python_embed" / "Lib" / "site-packages" / "distutils-precedence.pth"
        if pth_src.exists() and not pth_dst.exists():
            pth_dst.write_bytes(pth_src.read_bytes())
            print(f"[+] Copied distutils-precedence.pth to {pth_dst}")

if __name__ == "__main__":
    main()
