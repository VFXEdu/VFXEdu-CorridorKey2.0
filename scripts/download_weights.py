#!/usr/bin/env python3
"""Unified downloader for CorridorKey v2 weights and foundation models.

Models covered:
- corridorkey: CorridorKey v2 core weights (Hugging Face)
- cradio: NVIDIA C-RADIOv4-SO400M (Hugging Face)
- moge: Microsoft MoGe-2 Depth (Hugging Face)
- rvm: Google DeepMind Robust Video Matting (GCS CDN)

Usage:
    python scripts/download_weights.py --model required  # Download 4 core models (~4.8 GB)
    python scripts/download_weights.py --model all       # Download everything (~4.8 GB)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import shutil
import sys
import urllib.request
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

CORRIDORKEY_REPO = "nikopueringer/CorridorKey2.0"
CORRIDORKEY_FILES = ("corridorkey_v2.safetensors", "foundation_stats.safetensors")

CRADIO_REPO = "nvidia/C-RADIOv4-SO400M"
CRADIO_REVISION = "c0457f5dc26ca145f954cd4fc5bb6114e5705ad8"

MOGE_REPO = "Ruicheng/moge-2-vitb-normal"
MOGE_REVISION = "ca5f0e07ff01d3e5a364c1d954ed12ee1814b368"

RVM_FILE = "pretrain_rvm_small16_256_204031069.npz"
RVM_URL = f"https://storage.googleapis.com/representations4d/checkpoints/{RVM_FILE}"
RVM_MD5_B64 = "ZJb6kj8+tasiJbVeplXu7Q=="


def _md5_b64(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode()


def download_corridorkey(root: Path, repo: str = CORRIDORKEY_REPO, revision: str | None = None) -> None:
    from huggingface_hub import hf_hub_download
    print("[START] corridorkey: Downloading CorridorKey 2.0 Core (~2.54 GB)...")
    for name in CORRIDORKEY_FILES:
        target = root / "weights" / name
        if target.is_file() and target.stat().st_size > 100_000:
            print(f"  [corridorkey] {name} already present.")
            continue
        print(f"  [corridorkey] Fetching {name} from {repo}...")
        hf_hub_download(repo, name, revision=revision, local_dir=root / "weights")
    print("[SUCCESS] corridorkey: CorridorKey 2.0 Core is ready.")


def download_cradio(root: Path) -> None:
    from huggingface_hub import snapshot_download
    print(f"[START] cradio: Downloading NVIDIA C-RADIOv4 (~1.65 GB) from {CRADIO_REPO}...")
    target = root / "vfms/cradio/C-RADIOv4-SO400M/model.safetensors"
    if target.is_file() and target.stat().st_size > 1_000_000_000:
        print("  [cradio] model.safetensors already present.")
    else:
        snapshot_download(
            CRADIO_REPO,
            revision=CRADIO_REVISION,
            local_dir=root / "vfms/cradio/C-RADIOv4-SO400M",
            ignore_patterns=["*.pth.tar"],
        )
    print("[SUCCESS] cradio: C-RADIOv4 Foundation Model is ready.")


def download_moge(root: Path) -> None:
    from huggingface_hub import hf_hub_download
    print(f"[START] moge: Downloading Microsoft MoGe-2 Depth (~400 MB) from {MOGE_REPO}...")
    target = root / "vfms/moge/model.pt"
    if target.is_file() and target.stat().st_size > 200_000_000:
        print("  [moge] model.pt already present.")
    else:
        hf_hub_download(MOGE_REPO, "model.pt", revision=MOGE_REVISION, local_dir=root / "vfms/moge")
    print("[SUCCESS] moge: MoGe-2 Depth Foundation Model is ready.")


def download_rvm(root: Path) -> None:
    dst = root / "vfms/rvm" / RVM_FILE
    if dst.is_file() and _md5_b64(dst) == RVM_MD5_B64:
        print(f"  [rvm] {RVM_FILE} already present and verified.")
        print("[SUCCESS] rvm: DeepMind RVM Video Matting Model is ready.")
        return

    print(f"[START] rvm: Downloading Google DeepMind RVM (~258 MB) from {RVM_URL}...")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    with urllib.request.urlopen(RVM_URL) as response, open(tmp, "wb") as f:
        shutil.copyfileobj(response, f, length=1 << 20)
    if _md5_b64(tmp) != RVM_MD5_B64:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"checksum mismatch downloading {RVM_URL}")
    tmp.replace(dst)
    print("[SUCCESS] rvm: DeepMind RVM Video Matting Model is ready.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package_root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument(
        "--model",
        default="required",
        choices=["all", "required", "corridorkey", "cradio", "moge", "rvm"],
        help="Specific model to download (default: required)",
    )
    ap.add_argument("--corridorkey_repo", default=CORRIDORKEY_REPO)
    ap.add_argument("--corridorkey_revision", default=None)
    args = ap.parse_args()

    root = Path(args.package_root).resolve()
    target = args.model

    print(f"Target package root: {root}")
    print(f"Requested model target: {target}")

    if target in {"all", "required", "corridorkey"}:
        download_corridorkey(root, args.corridorkey_repo, args.corridorkey_revision)
    if target in {"all", "required", "cradio"}:
        download_cradio(root)
    if target in {"all", "required", "moge"}:
        download_moge(root)
    if target in {"all", "required", "rvm"}:
        download_rvm(root)

    print(f"[COMPLETE] All requested assets are in place under {root}")


if __name__ == "__main__":
    main()
