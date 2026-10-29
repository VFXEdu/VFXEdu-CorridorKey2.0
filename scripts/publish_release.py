#!/usr/bin/env python3
"""Automated GitHub Release Publisher & Version Manager for VFXEdu CorridorKey 2.0.

Features:
- Auto-extracts current version tag (e.g. v0.1.1) from gui.py.
- Ensures the portable distribution package (dist/CorridorKeyer2.0_Portable_Setup.zip) is built.
- Creates Git tag and pushes to your GitHub remote.
- Publishes a GitHub Release with release notes and attaches the 95 MB portable ZIP asset.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
RELEASE_ZIP = DIST_DIR / "CorridorKeyer2.0_Portable_Setup.zip"
RELEASE_SHA = DIST_DIR / "CorridorKeyer2.0_Portable_Setup.zip.sha256"


def get_current_app_version() -> str:
    gui_file = ROOT / "gui.py"
    if gui_file.is_file():
        text = gui_file.read_text(encoding="utf-8")
        m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
    return "v0.1.1"


def get_git_remote_url(remote_name: str = "origin") -> str | None:
    try:
        res = subprocess.run(
            ["git", "remote", "get-url", remote_name],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        return res.stdout.strip()
    except Exception:
        return None


def parse_github_repo(remote_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from GitHub URL."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
    if m:
        return m.group(1), m.group(2)
    return None


def ensure_distribution_package():
    if not RELEASE_ZIP.is_file() or RELEASE_ZIP.stat().st_size < 10_000_000:
        print("[*] Portable release ZIP not found. Building distribution package...")
        import create_distribution_zip
        create_distribution_zip.main()
    print(f"[*] Distribution package ready: {RELEASE_ZIP.name} ({RELEASE_ZIP.stat().st_size / (1024*1024):.2f} MB)")


def create_github_release_api(
    token: str,
    owner: str,
    repo: str,
    tag: str,
    name: str,
    body: str,
) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": False,
        "prerelease": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "VFXEdu-Release-Publisher",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        if e.code == 422 and "already_exists" in err_body:
            print(f"[*] Release with tag {tag} already exists. Fetching existing release...")
            get_req = urllib.request.Request(
                f"{url}/tags/{tag}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "VFXEdu-Release-Publisher",
                },
            )
            with urllib.request.urlopen(get_req) as g_resp:
                return json.loads(g_resp.read().decode("utf-8"))
        raise RuntimeError(f"GitHub API error {e.code}: {err_body}")


def upload_release_asset(token: str, upload_url_template: str, file_path: Path):
    upload_url = upload_url_template.split("{")[0]
    filename = file_path.name
    url = f"{upload_url}?name={urllib.parse.quote(filename)}"

    file_size = file_path.stat().st_size
    print(f"[*] Uploading asset: {filename} ({file_size / (1024*1024):.2f} MB)...")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    req = urllib.request.Request(
        url,
        data=file_bytes,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(file_bytes)),
            "User-Agent": "VFXEdu-Release-Publisher",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            print(f"  -> Uploaded successfully: {res_data.get('browser_download_url')}")
            return res_data
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"[!] Upload error {e.code}: {err_body}")
        if e.code == 422:
            print(f"[*] Asset {filename} already exists on this release.")
        else:
            raise


def git_tag_and_push(tag: str, remote: str = "origin"):
    print(f"[*] Creating Git tag: {tag}...")
    subprocess.run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], cwd=ROOT)
    print(f"[*] Pushing tag {tag} to remote {remote}...")
    res = subprocess.run(["git", "push", remote, tag], cwd=ROOT)
    if res.returncode == 0:
        print("[SUCCESS] Git tag pushed successfully!")
    else:
        print("[!] Git tag push failed or permission denied.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", default=None, help="Release tag (defaults to version in gui.py)")
    ap.add_argument("--token", default=None, help="GitHub Personal Access Token")
    ap.add_argument("--repo", default=None, help="GitHub repository in 'owner/repo' format")
    ap.add_argument("--git-push", action="store_true", help="Also push git commit and tag")
    args = ap.parse_args()

    tag = args.tag or get_current_app_version()
    print("=" * 68)
    print(f" VFXEdu CorridorKey 2.0 - GitHub Release Publisher ({tag})")
    print("=" * 68)

    # 1. Ensure portable package is built
    ensure_distribution_package()

    # 2. Identify GitHub Repo
    owner_repo = None
    if args.repo:
        parts = args.repo.split("/")
        if len(parts) == 2:
            owner_repo = (parts[0], parts[1])
    else:
        remote_url = get_git_remote_url("origin")
        if remote_url:
            parsed = parse_github_repo(remote_url)
            if parsed and parsed[0].lower() != "nikopueringer":
                owner_repo = parsed
                print(f"[*] Detected GitHub repository: {owner_repo[0]}/{owner_repo[1]}")

    if not owner_repo:
        print("\n[?] Please enter your GitHub Repository details:")
        inp = input("    GitHub Repo (format: username/repo-name): ").strip()
        parts = inp.split("/")
        if len(parts) == 2 and parts[0] and parts[1]:
            owner_repo = (parts[0], parts[1])
        else:
            print("[ERROR] Invalid repository format. Expected: username/repository")
            return 1

    owner, repo = owner_repo

    # 3. Check / Prompt Token
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("\n[?] GitHub Personal Access Token is required to publish releases.")
        print("    (Create one at https://github.com/settings/tokens with 'repo' scope)")
        token = input("    Enter GitHub Token: ").strip()

    if not token:
        print("[ERROR] GitHub token not provided. Aborting API upload.")
        return 1

    # 4. Optional Git Tag & Push
    if args.git_push:
        git_tag_and_push(tag)

    # 5. Create Release
    release_name = f"VFXEdu CorridorKey 2.0 {tag}"
    release_body = f"""## ⚡ VFXEdu CorridorKey 2.0 ({tag}) Portable Release

### 📦 특징 (Features)
- **완전 무설치 (Zero Prerequisites)**: Python 및 FFmpeg 사전 설치 불필요.
- **하이브리드 포터블 배포본 (~95 MB)**: 가벼운 배포 압축 파일로 다운로드가 빠름.
- **원클릭 자동 설정**: 압축 해제 후 `Setup_GUI.bat` 1회 실행으로 PyTorch(CUDA 12.8) 자동 구성.
- **VFX Workbench UI**: 실시간 GPU 점유율 모니터링, 와이프(Wipe) 비교, 브러시 마스크 편집기 탑재.

### 🚀 설치 및 실행 방법
1. 아래 Assets에서 `CorridorKeyer2.0_Portable_Setup.zip`을 다운로드합니다.
2. 원하는 폴더에 압축을 풉니다.
3. `Setup_GUI.bat`를 더블 클릭하여 초기 환경 설정을 진행합니다.
4. `Launch_GUI.bat`를 더블 클릭하여 앱을 실행합니다.
"""
    print(f"\n[*] Creating GitHub Release '{release_name}' on {owner}/{repo}...")
    release = create_github_release_api(
        token=token,
        owner=owner,
        repo=repo,
        tag=tag,
        name=release_name,
        body=release_body,
    )

    upload_url = release.get("upload_url", "")
    html_url = release.get("html_url", "")
    print(f"[OK] Release created: {html_url}")

    # 6. Upload Assets
    if upload_url:
        upload_release_asset(token, upload_url, RELEASE_ZIP)
        if RELEASE_SHA.is_file():
            upload_release_asset(token, upload_url, RELEASE_SHA)

    print("\n" + "=" * 68)
    print(" [SUCCESS] Release Published to GitHub Successfully!")
    print(f" Public Release URL: {html_url}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
