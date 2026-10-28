# CorridorKey 2.0 배포 및 라이선스 가이드 (Distribution Guide)

이 문서는 본 도구(CorridorKey 2.0 Professional Workbench GUI Suite)를 GitHub, 블로그, 커뮤니티, 유튜브, 아카이브 등에 **무료로 배포(재배포)할 때 준수해야 할 라이선스 규정 및 포터블(무설치) 배포 패키지 안내**입니다.

---

## 📌 1. 라이선스 핵심 요약 (CC BY-NC-SA 4.0 + CorridorKey Terms)

CorridorKey 2.0 라이선스(`LICENSE` 파일)에 따라 다음 사항을 반드시 숙지하고 준수해야 합니다:

| 항목 | 허용 여부 | 설명 및 조건 |
|---|:---:|---|
| **무료 배포 (Free Distribution)** | **필수 (의무)** | 2차 수정본/파생 툴(GUI, 기능 추가 등)을 배포할 때는 **반드시 무료(Free of charge)**로만 공개해야 합니다. |
| **결과물 상업적 사용 (Commercial Use of Output)** | **완전 허용 (자유)** | 이 툴을 이용해 제작한 영상, 알파 마스크, 컷아웃 결과물은 **100% 사용자의 소유**이며 상업 프로젝트(광고, 영화, 유튜브, 외주 등)에 무제한 사용 가능합니다. |
| **자발적 후원 / 기부 링크** | **허용** | 무료 다운로드(0원) 옵션이 기본 제공되는 한 후원(Donation) 버튼은 허용됩니다. |
| **소프트웨어 유료 판매** | **절대 금지** | 프로그램이나 모델 가중치를 유료로 판매하거나 패키징하여 돈을 받는 행위는 금지됩니다. |
| **유료 API / 클라우드 서비스** | **절대 금지** | 유료 웹 추론 API나 유료 구독형 SaaS 형태로 제공하는 것은 금지됩니다. |
| **대기업 이용** | **제한** | 연간 총매출 2,000만 달러(약 260억 원) 이상의 대기업은 공식 상용 플러그인 구매가 필요합니다. |

---

## 📦 2. 방안 A: 하이브리드 무설치(Portable) 배포 패키지 안내

본 프로젝트는 **방안 A (하이브리드 포터블 배포 방식)**를 채택하여, 최종 사용자가 **Python이나 FFmpeg를 컴퓨터에 미리 설치할 필요가 전혀 없습니다.**

### 🌟 방안 A의 장점:
1. **완전 무설치 (Zero Prerequisites)**:
   - 사용자의 Windows에 Python이 없어도 됨
   - FFmpeg를 별도로 받거나 윈도우 환경 변수(PATH)를 편집할 필요가 전혀 없음
   - 오직 **NVIDIA 그래픽카드 (VRAM 8GB 이상 권장)**만 있으면 실행 가능
2. **초경량 배포 용량 (~94 MB)**:
   - 기가바이트 단위의 무거운 PyTorch 휠 파일과 AI 모델 가중치를 미리 묶지 않고 분리하여 배포 ZIP 크기가 **94 MB**에 불과함 (빠른 다운로드와 쉬운 배포).
3. **독립된 격리 환경**:
   - 사용자 컴퓨터의 기존 Python 버전이나 레지스트리에 일체 영향을 주지 않는 완전 독립 격리 구조.

---

## ⚡ 3. 원클릭 배포 패키지 빌드 방법 (배포자용)

프로젝트 루트에서 다음 파일 중 하나를 실행하면 `dist/` 폴더에 배포용 ZIP 파일이 자동 생성됩니다:
* **윈도우**: `Build_Release_Package.bat` 더블 클릭
* **터미널**: `python scripts/create_distribution_zip.py`
* **생성 파일**: `dist/CorridorKeyer2.0_Portable_Setup.zip` (~94 MB) + SHA-256 체크섬

### 배포 패키지 내부 구성:
1. `python_embed/` : 윈도우 무설치 내장 Python 3.12 런타임 + Pip
2. `bin/ffmpeg.exe` : 비디오 렌더링용 공식 FFmpeg 정적 바이너리
3. `Setup_GUI.bat` : 사용자 1회 초기화 스크립트 (동봉된 Python으로 PyTorch 2.9.1+cu128 자동 설치)
4. `Launch_GUI.bat` : 사용자 앱 실행 런처
5. `LICENSE` & `THIRD_PARTY_NOTICES.md` : 공식 라이선스 및 서드파티 고지문
6. `gui.py`, `workbench_widgets.py`, `model_manager.py`, `mask_editor.py` 등 전체 소스 코드
7. 빈 가중치 폴더 구조: `weights/.gitkeep`, `vfms/*/.gitkeep`, `outputs/` 등

---

## 🚀 4. 최종 사용자 사용 순서 (유저용 안내문)

배포본을 내려받은 최종 사용자는 다음 단계만 거치면 됩니다:

1. **압축 풀기**: `CorridorKeyer2.0_Portable_Setup.zip` 압축을 원하는 폴더에 풉니다.
2. **최초 1회 설치**: `Setup_GUI.bat` 더블 클릭
   - 동봉된 무설치 Python을 통해 해당 폴더 안에만 PyTorch(CUDA 12.8)와 필수 라이브러리를 자동 설치합니다.
   - 마지막에 AI 모델 가중치(~4.8 GB) 다운로드 여부를 묻습니다 (`Y` 입력 시 자동 다운로드).
3. **앱 실행**: `Launch_GUI.bat` 더블 클릭
   - CorridorKey 2.0 Workbench GUI가 즉시 실행됩니다.

---

## 📢 5. 배포 페이지용 표준 크레딧 템플릿 (복사해서 사용)

웹사이트, 깃허브 README, 유튜브 설명란 등에 배포할 때 아래 문구를 복사하여 그대로 사용하실 수 있습니다:

### [한국어 버전]
```markdown
### 저작권 및 라이선스 안내 (License & Credits)
- 본 도구는 Corridor Digital과 Zachary Harris가 개발한 오픈 소스 모델 **CorridorKey 2.0**을 기반으로 제작된 무료 데스크톱 GUI 스위트입니다.
- **원작자**: Corridor Digital LLC (Niko Pueringer) & Zachary Harris
- **공식 레포지토리**: https://github.com/nikopueringer/CorridorKey2.0
- **공식 상용 플러그인**: https://corridorkey.com
- **라이선스**: CorridorKey Licence (Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International, CC BY-NC-SA 4.0)
- **무료 배포 원칙**: 본 툴 및 수정본은 대중에게 영구히 무료(Free of charge)로 제공됩니다.
- **결과물 권리**: 본 도구로 추출 및 생성된 모든 비디오, 매트, 이미지 결과물은 전적으로 사용자의 소유이며 상업적 프로젝트(광고, 영화, 외주, 유튜브 등)에 자유롭게 사용하실 수 있습니다.
```

### [English Version]
```markdown
### Credits & License Notice
- This tool is an enhanced Desktop GUI Suite built on top of **CorridorKey 2.0**, designed and trained by Zachary Harris in collaboration with Niko Pueringer and Corridor Digital LLC.
- **Original Authors**: Zachary Harris & Niko Pueringer (Corridor Digital LLC)
- **Official Repository**: https://github.com/nikopueringer/CorridorKey2.0
- **Official Commercial Plugin**: https://corridorkey.com
- **License**: CorridorKey Licence (CC BY-NC-SA 4.0 + Additional Terms)
- **Free Accessibility**: In accordance with Section 2(c) of the CorridorKey Licence, this derivative suite is made available to the public completely free of charge.
- **Commercial Use of Outputs**: In accordance with Section 1(b), all images and videos produced with this tool belong entirely to the user and may be used commercially.
```
