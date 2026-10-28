import sys
from pathlib import Path

NVML_CODE = '''import ctypes


class _NvmlMemory(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


def get_gpu_vram_info() -> tuple[float, float, float, float, str]:
    """Query live GPU VRAM via NVML (matching Task Manager), falling back to PyTorch."""
    # 1. Real-time NVML hardware query (100% matches Windows Task Manager & nvidia-smi)
    try:
        nvml = ctypes.CDLL("nvml.dll")
        if nvml.nvmlInit_v2() == 0:
            handle = ctypes.c_void_p()
            if nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) == 0:
                mem = _NvmlMemory()
                if nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem)) == 0:
                    used_gb = mem.used / (1024**3)
                    free_gb = mem.free / (1024**3)
                    tot_gb = mem.total / (1024**3)
                    pct = (mem.used / mem.total) * 100 if mem.total > 0 else 0.0

                    name_buf = ctypes.create_string_buffer(64)
                    if nvml.nvmlDeviceGetName(handle, name_buf, 64) == 0:
                        gpu_name = name_buf.value.decode("utf-8", errors="ignore")
                    else:
                        gpu_name = "NVIDIA GPU"
                    nvml.nvmlShutdown()
                    return (used_gb, free_gb, tot_gb, pct, gpu_name)
            nvml.nvmlShutdown()
    except Exception:
        pass

    # 2. Fallback to PyTorch CUDA mem_get_info
    try:
        if torch.cuda.is_available():
            free_b, tot_b = torch.cuda.mem_get_info()
            used_b = max(0, tot_b - free_b)
            used_gb = used_b / (1024**3)
            free_gb = free_b / (1024**3)
            tot_gb = tot_b / (1024**3)
            pct = (used_b / tot_b) * 100 if tot_b > 0 else 0.0
            name = torch.cuda.get_device_name(0)
            return (used_gb, free_gb, tot_gb, pct, name)
    except Exception:
        pass
    return (0.0, 0.0, 0.0, 0.0, "CPU (No CUDA)")'''

def patch_file(p: Path):
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8")
    
    old_target = """def get_gpu_vram_info() -> tuple[float, float, float, float, str]:
    \"\"\"Query live GPU VRAM. Returns (used_gb, free_gb, tot_gb, pct, gpu_name).\"\"\"
    try:
        if torch.cuda.is_available():
            free_b, tot_b = torch.cuda.mem_get_info()
            used_b = max(0, tot_b - free_b)
            used_gb = used_b / (1024**3)
            free_gb = free_b / (1024**3)
            tot_gb = tot_b / (1024**3)
            pct = (used_b / tot_b) * 100 if tot_b > 0 else 0.0
            name = torch.cuda.get_device_name(0)
            return (used_gb, free_gb, tot_gb, pct, name)
    except Exception:
        pass
    return (0.0, 0.0, 0.0, 0.0, "CPU (No CUDA)")"""

    # Normalize newlines for search
    text_lf = text.replace("\r\n", "\n")
    if old_target in text_lf:
        text_lf = text_lf.replace(old_target, NVML_CODE, 1)
        # Restore CRLF
        text_crlf = text_lf.replace("\n", "\r\n")
        p.write_text(text_crlf, encoding="utf-8")
        print(f"[+] Patched NVML into {p}")
    else:
        print(f"[*] Target not found or already patched in {p}")

def main():
    root = Path(__file__).resolve().parent.parent
    patch_file(root / "gui.py")
    
    user_p = Path(r"K:\CorridorKey2.0\CorridorKeyer2.0_Portable_v1.1.1\gui.py")
    patch_file(user_p)
    user_old = Path(r"K:\CorridorKey2.0\CorridorKey2.0_Portable_v0.1.1\gui.py")
    patch_file(user_old)

if __name__ == "__main__":
    main()
