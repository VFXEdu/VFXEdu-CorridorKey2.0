# ⚡ VFXEdu CorridorKey 2.0 (v0.1.1)
### Professional VFX Workbench Desktop Suite & Zero-Install Portable Keyer

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-e5a93c.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11%20%28x64%29-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%20%28Embedded%20Portable%29-green.svg)](LICENSE)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.9.1%2BCUDA12.8-red.svg)](https://pytorch.org/)

[**English**](#english-guide) · [**한국어 안내**](#한국어-안내)

---

## ℹ️ Notice of Derivative Work & Credits (저작권 및 원작자 고지)

> [!NOTE]
> **VFXEdu CorridorKey 2.0** is an independent open-source VFX desktop enhancement based on the revolutionary green-screen & AI video matting architecture created by **Zachary Harris** and **Niko Pueringer** ([Corridor Digital](https://corridordigital.com)).
>
> * **Original Upstream Repository**: [nikopueringer/CorridorKey2.0](https://github.com/nikopueringer/CorridorKey2.0)
> * **Official Commercial Plugins & Standalone App**: [corridorkey.com](https://corridorkey.com)
> * **License**: Shared under [CC BY-NC-SA 4.0](LICENSE) (Derivatives must be freely accessible; user outputs are 100% free for commercial and non-commercial work).

---

<a name="english-guide"></a>
## 🌟 What is VFXEdu CorridorKey 2.0?

While the official CorridorKey 2.0 repository provides a command-line interface, **VFXEdu CorridorKey 2.0** transforms it into a **complete, standalone visual VFX studio app** designed for professional post-production artists and editors:

1. **📦 Zero-Install Portable Runtime (Option A)**:
   - Ships with an isolated **Windows Python 3.12 Embeddable environment** and static **FFmpeg binary**.
   - No need to pre-install Python, Git, or FFmpeg system-wide.
2. **🖥️ Interactive VFX Workbench UI**:
   - **Full-Frame Checkerboard Viewport**: Real-time RGBA cutout inspection.
   - **Interactive Wipe & Compare Slider**: Instant split comparison between original plate and keyed matte.
   - **Filmstrip Scrubber & Transport Controls**: Playback and frame scrubbing with thumbnail strip.
   - **⚡ Live GPU Telemetry**: Real-time GPU VRAM and memory load monitor badge.
3. **🖌️ Interactive Brush Mask Editor**:
   - Paint foreground/background hint masks directly on any video frame.
   - Features Gaussian blur feathering, mask expand/contract (dilate/erode), invert, and one-click **"Apply as First-Frame Hint"**.
4. **🌐 Bilingual Support**:
   - Fully localized in **English (Default)** and **Korean (한국어)** with instant runtime toggle without restart.
5. **📦 AI Model Manager**:
   - Visual dashboard to inspect and download foundation model checkpoints (CorridorKey v2, C-RADIOv4, MoGe-2, RVM) in one click.
6. **🎬 Foundry Nuke Native Gizmo Integration**:
   - Ships with `CorridorKeyer.gizmo`, Python bridge, and `menu.py` inside `nuke/`.
   - Run AI keying directly inside Nuke with 16-bit float linear OpenEXR sequences and automatic DAG node tree generation (`Read` + `Copy` + `Premult`).
7. **🎞️ DaVinci Resolve Edit & Color Integration**:
   - 1-click timeline keying directly from the Edit or Color page (`Workspace -> Scripts -> CorridorKeyer`).
   - Renders native Apple ProRes 4444 (RGBA) and automatically imports to Media Pool and overlays on Track V2.

---

## 🚀 Quick Start (Zero-Install Portable Setup)

### 1. Extract Package
Extract the portable distribution archive (`CorridorKeyer2.0_Portable_Setup.zip`, ~95 MB) to any local directory (e.g. `D:\CorridorKeyer2.0`).

### 2. Run Setup Once
Double-click **`Setup_GUI.bat`**.  
The script automatically bootstraps PyTorch with CUDA 12.8 and required packages into the isolated embedded Python environment.

### 3. Launch App
Double-click **`Launch_GUI.bat`** to open the VFX Workbench suite!

---

<a name="한국어-안내"></a>
## 🇰🇷 한국어 안내 (Korean Guide)

### 🌟 VFXEdu CorridorKey 2.0이란?
Corridor Digital의 혁신적인 AI 그린스크린 제거 엔진 CorridorKey 2.0을 누구나 클릭 몇 번으로 쉽게 사용할 수 있도록 제작된 **VFX 워크벤치 풀스펙 데스크톱 애플리케이션**입니다.

### ✨ 주요 추가 기능
* **완전 무설치 포터블 배포 (~95MB)**: 컴퓨터에 파이썬이나 FFmpeg가 없어도 압축만 풀고 `Setup_GUI.bat` 한 번만 실행하면 즉시 구동됩니다.
* **VFX 워크벤치 GUI**: 대형 체커보드 뷰포트, 실시간 와이프(Wipe) 분할 비교 슬라이더, 비주얼 필름스트립 스크러버 탑재.
* **실시간 GPU 점유율 모니터링**: 상단 배지 및 인스펙터에서 실시간 GPU VRAM 사용량을 1.5초 주기로 확인.
* **대화형 브러시 마스크 편집기**: 영상의 특정 프레임을 보고 대상 인물/물체를 직접 브러시로 칠해 첫 프레임 마스크(`FrameHint.png`)로 등록.
* **🎬 Foundry Nuke 전용 기즈모(Gizmo) 노드 기본 탑재**: 누크 노드 그래프에서 `CorridorKeyer` 노드로 직접 키잉을 수행하고 씬 리니어 16비트 EXR 시퀀스 및 컴포지팅 노드 트리 자동 생성 (`nuke/` 폴더 참조).
* **🎞️ DaVinci Resolve 에디트 & 컬러 페이지 원클릭 연동**: 타임라인에서 클립 선택 후 `Workspace -> Scripts -> CorridorKeyer` 클릭 한 번으로 키잉 실행. ProRes 4444 알파 영상 렌더링 후 V2 트랙 및 미디어 풀 자동 배치 (`resolve/` 폴더 참조).
* **다국어 실시간 전환**: 영어(기본)와 한국어를 프로그램 재시작 없이 즉시 전환.

### 🚀 사용 방법
1. 제공된 `CorridorKeyer2.0_Portable_Setup.zip` 압축 파일을 다운로드합니다.
2. 원하는 로컬 폴더에 압축을 풉니다.
3. `Setup_GUI.bat`를 실행하여 1회 자동 설정을 진행합니다.
4. `Launch_GUI.bat`를 더블 클릭하여 실행합니다.

---

## 📜 License & Acknowledgments

* **Original CorridorKey 2.0**: Designed and trained by Zachary Harris and Niko Pueringer ([Corridor Digital](https://corridordigital.com)).
* **Foundation Models**:
  * NVIDIA C-RADIOv4-SO400M
  * Microsoft MoGe-2 Depth
  * Google DeepMind Robust Video Matting (RVM)
* **License**: Released under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)** with CorridorKey 2.0 Additional Terms.
  * Modified derivatives must be distributed **free of charge**.
  * Outputs generated by users are **100% free for commercial and non-commercial work**.
  * See [LICENSE](LICENSE) for full legal text.
