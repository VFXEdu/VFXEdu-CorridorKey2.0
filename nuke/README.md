# ⚡ VFXEdu CorridorKey 2.0 - Nuke Integration Guide

The Foundry **Nuke(누크)**와 **CorridorKey 2.0**을 연결하는 전용 기즈모(Gizmo) 노드 및 파이프라인 연동 도구입니다.

---

## 🌟 주요 특징 (Key Features)

1. **누크 노드 그래프 원클릭 키잉**:
   - 누크 안에서 `CorridorKeyer` 노드를 생성하고 원본 플레이트와 (선택) 첫 프레임 마스크(`FrameHint`)를 연결한 후 버튼 클릭 한 번으로 AI 키잉을 실행합니다.
2. **누크 환경과 완전 격리 (No Conflict)**:
   - 누크 내장 파이썬과 별도로 CorridorKey의 격리된 **무설치 포터블 Python(PyTorch + CUDA 12.8)**을 서브프로세스로 호출하므로 라이브러리 충돌이 전혀 없습니다.
3. **VFX 스튜디오 표준 씬 리니어(Scene-Linear) EXR 워크플로우**:
   - 16-bit Half 또는 32-bit Float OpenEXR 시퀀스로 직접 렌더링되어 감마 왜곡이나 클리핑 없는 네이티브 컬러를 유지합니다.
4. **결과물 자동 DAG 연결**:
   - 렌더가 완료되면 누크 노드 그래프에 `Read (Alpha)` + `Read (Clean FG)` + `Copy` + `Premult` 노드 트리가 자동으로 배치되어 즉시 컴포지팅에 사용할 수 있습니다.
5. **누크 메뉴바 및 노드 툴바 탑재**:
   - `VFXEdu` 메뉴 및 `Keyer` 툴바 카테고리에 기본 등록됩니다.

---

## 📥 설치 방법 (Installation)

### 방법 1. 가장 간단한 개인 PC 설치 (`~/.nuke` 사용)

1. 누크 사용자 설정 폴더(`C:\Users\<사용자명>\.nuke`)를 엽니다.
2. `CorridorKeyer2.0/nuke` 폴더 안에 있는 파일들을 복사합니다:
   - `CorridorKeyer.gizmo`
   - `corridorkey_nuke.py`
   - `init.py` (이미 있다면 파일 끝에 내용 추가)
   - `menu.py` (이미 있다면 파일 끝에 내용 추가)
3. 누크를 실행하면 상단 메뉴에 **`VFXEdu`** 메뉴가 나타납니다.

---

### 방법 2. 스튜디오 공용 파이프라인 설치 (`NUKE_PATH` 환경변수)

스튜디오 네트워크 드라이브나 로컬 폴더를 누크 경로에 등록할 경우:

* Windows 시스템 환경변수(또는 런처 스크립트)에 추가:
  ```batch
  set NUKE_PATH=K:\________________VFXEdu_Script\CorridorKeyer2.0\nuke;%NUKE_PATH%
  ```
* 또는 사용자의 `~/.nuke/init.py`에 다음 한 줄 추가:
  ```python
  nuke.pluginAddPath("K:/________________VFXEdu_Script/CorridorKeyer2.0/nuke")
  ```

---

## 🚀 사용 방법 (Quick Start)

### 1. 노드 생성
누크 노드 그래프(DAG)에서:
* **방법 A**: 빈 공간에서 `Tab` 키를 누르고 **`CorridorKeyer`** 검색 후 생성
* **방법 B**: 상단 메뉴 `VFXEdu` → `CorridorKeyer (Gizmo)` 클릭

### 2. 노드 입력 연결
* **`Source` (Input 0)**: 키잉할 원본 그린/블루스크린 플레이트 (`Read` 노드 또는 보정 노드)
* **`FrameHint` (Input 1 - 선택 사항)**: 첫 프레임의 인물 마스크 (예: `Roto` 노드나 러프한 가비지 매트)
  * 연결하지 않으면 AI가 스스로 피사체를 판별하는 No-Hint 모드로 동작합니다.

### 3. 파라미터 확인 및 렌더링
노드 프로퍼티 패널에서:
* **Output Directory**: 출력 저장 폴더 (기본: 누크 스크립트 위치 하위 `corridorkey_output`)
* **Format**: `exr` (기본값, Half 16-bit) 또는 `video`
* **Despill Strength**: 그린/블루 반사광 제거 강도 (기본: 0.5)
* **Auto VRAM Profiling**: 활성화 시 현재 GPU VRAM에 맞춰 최적 윈도우 크기 자동 지정
* **[ 🚀 Render CorridorKey Matte ]** 버튼 클릭!

### 4. 결과 확인
* 백그라운드에서 AI 인퍼런스가 실행되며 누크 프로그레스 바에 진행률이 표시됩니다.
* 작업이 끝나면 알림 대화상자가 뜨고, 노드 그래프에 바로 연결해서 쓸 수 있는 `Read` + `Premult` 노드 트리가 자동 생성됩니다.

---

## 🛠️ 독립형 워크벤치 바로 열기
누크 작업 중 대형 뷰포트나 브러시 마스크 편집기가 필요하면:
* 누크 메뉴: **`VFXEdu` → `Open VFXEdu CorridorKeyer Workbench GUI...`**를 클릭하면 즉시 독립형 GUI 창이 실행됩니다.
