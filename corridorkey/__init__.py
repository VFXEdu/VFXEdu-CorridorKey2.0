import os
import sys

# Prevent PyTorch CUDA memory fragmentation on long video footage
_alloc_val = "max_split_size_mb:512" if sys.platform == "win32" else "expandable_segments:True"
if "PYTORCH_ALLOC_CONF" not in os.environ and "PYTORCH_CUDA_ALLOC_CONF" not in os.environ:
    os.environ["PYTORCH_ALLOC_CONF"] = _alloc_val

from .model import CorridorKeyV3


class CorridorKeyV2(CorridorKeyV3):
    """Public CorridorKey v2 runtime alias for the exported model."""


__all__ = ["CorridorKeyV2"]
