import os

# Prevent PyTorch CUDA memory fragmentation on long video footage
_alloc_conf = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
if not _alloc_conf:
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
elif "expandable_segments" not in _alloc_conf:
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = f"{_alloc_conf},expandable_segments:True"

from .model import CorridorKeyV3


class CorridorKeyV2(CorridorKeyV3):
    """Public CorridorKey v2 runtime alias for the exported model."""


__all__ = ["CorridorKeyV2"]
