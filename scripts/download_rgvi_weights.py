"""Download weights for RGVI (AAAI 2025) video inpainting."""
from pathlib import Path
import re
import sys
import requests
from tqdm import tqdm

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
RGVI_DIR = ROOT / "third_party" / "RGVI"
WEIGHTS_DIR = RGVI_DIR / "weights"
WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "FCNet.pth": "1KNetMWeYVlgrhgguw45uRfoJDmljw5hT",
    "PFCNet.pth": "1wknOIQmOnzPtLpN1Ydfb698tUZVOYuKF",
}

def download_gdrive_file(file_id: str, dest_path: Path):
    if dest_path.is_file() and dest_path.stat().st_size > 1000000:
        print(f"[OK] {dest_path.name} already exists ({dest_path.stat().st_size / 1024 / 1024:.1f} MB). Skipping.")
        return

    print(f"[*] Downloading {dest_path.name} from Google Drive...")
    session = requests.Session()
    url = "https://docs.google.com/uc?export=download"
    r = session.get(url, params={"id": file_id}, stream=True)

    if "attachment" not in r.headers.get("Content-Disposition", ""):
        # File is large, parse download-form
        action_match = re.search(r'action="([^"]+)"', r.text)
        action_url = action_match.group(1) if action_match else "https://drive.usercontent.google.com/download"
        params = {}
        for m in re.finditer(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', r.text):
            params[m.group(1)] = m.group(2)
        r = session.get(action_url, params=params, stream=True)

    total_size = int(r.headers.get("content-length", 0))
    temp_path = dest_path.with_suffix(".tmp")
    with open(temp_path, "wb") as f, tqdm(total=total_size, unit="B", unit_scale=True, desc=dest_path.name) as bar:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
                bar.update(len(chunk))

    temp_path.replace(dest_path)
    print(f"[SUCCESS] Saved {dest_path.name} ({dest_path.stat().st_size / 1024 / 1024:.1f} MB).")


def main():
    print(f"Target weights directory: {WEIGHTS_DIR}")
    for fname, fid in FILES.items():
        dest = WEIGHTS_DIR / fname
        download_gdrive_file(fid, dest)
    print("[SUCCESS] All RGVI model checkpoints are ready.")

if __name__ == "__main__":
    main()
