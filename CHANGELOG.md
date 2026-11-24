# VFXEdu CorridorKey 2.0 - Changelog

모든 버전의 업데이트 내역과 패치 상세 사항을 기록합니다.
GitHub 릴리즈 시 해당 버전의 내용이 릴리즈 노트 및 GUI 업데이트 창에 자동으로 반영됩니다.
모든 이전 릴리즈 버전은 GitHub 릴리즈 페이지에 영구 보존됩니다.

---

## [v0.2.0] - 2026-11-24

### 🚀 주요 업데이트 및 버그 수정 (Highlights)
- **임의 프레임 키프레임 힌트(`--hint_frame`) & 양방향 Hann 전파 (Bidirectional Propagation) 탑재**
  - 기존에 첫 프레임(0번)에만 적용되던 단일 힌트 마스크를 **대상이 가장 잘 보이는 임의의 프레임**에 지정할 수 있도록 확장했습니다.
  - 힌트가 지정된 프레임을 포함한 앵커(Anchor) Hann 윈도우를 먼저 추론한 뒤, **앞쪽(역방향)과 뒤쪽(정방향)으로 양방향 전파**하여 카메라 이동으로 대상이 중간에 등장하는 샷도 정확하게 추출합니다.
  - **Desktop GUI**: 인스펙터에 `Hint Frame #` 및 `Current` 버튼을 추가하고, `Quick Brush` 에디터로 현재 뷰포트 프레임에 브러시를 칠해 적용하면 해당 프레임 번호가 자동 등록됩니다.
  - **Foundry Nuke**: `Hint Conditioning Mode`에 `Current Frame Keyframe (Bidirectional)` 모드를 추가하여 타임라인 현재 프레임의 RotoPaint/Roto 힌트를 양방향 전파할 수 있습니다.
- **DaVinci Resolve / Fusion 브릿지 크래시 수정 및 v0.2.0 기능 완전 동기화**
  - Fusion 브릿지(`corridorkey_fusion.py`)에서 `ck_root` 선언 전 참조로 발생하던 `UnboundLocalError` 크래시를 수정했습니다.
  - DaVinci Resolve Edit/Color 다이얼로그 및 Fusion Fuse 노드에 `Despill Color (Green/Blue)`, `Despill Method (Average/Max/None)`, `AI Plate Scale (Model Scale)` 컨트롤을 추가하여 GUI/Nuke와 1:1 기능 패리티를 완성했습니다.
  - Resolve/Fusion 서브프로세스에 `encoding="utf-8", errors="replace"`를 적용해 Windows 한글 경로 실행 시 발생하던 `UnicodeDecodeError`를 원천 차단했습니다.
  - Resolve `"Timeline Cut In/Out Only"` 실행 시 `left_offset`을 신규 CLI 옵션 `--start_offset`으로 전달하여 정확한 타임라인 트리밍 구간만 렌더링하며, 완료 시 V2 트랙의 원본 클립 시작 위치에 배치하도록 개선했습니다.
- **CLI `--start_offset` 구간 트리밍 지원 및 코어 I/O 안정성 대폭 강화**
  - `infer.py` / `runtime.py` / `video_io.py`에 0-based 시작 프레임 오프셋 `--start_offset`을 추가해 비디오 및 이미지 시퀀스 모두 임의 구간 고속 렌더링이 가능합니다.
  - `ExrSequenceWriter`를 `cv2.imencode(".exr")` 기반 유니코드 안전 저장 방식으로 전환하여 Windows 한글 경로에서도 EXR 시퀀스가 깨짐 없이 저장됩니다.
  - `ThreadedVideoWriter` / `ExrSequenceWriter`의 워커 예외 종료 시 `release()` 큐 데드락 가능성을 차단했습니다.
  - 이미지 시퀀스 입력에서도 `linear_brightness` / `linear_contrast` / `linear_contrast_pivot` 색보정 파라미터가 정상 적용되도록 수정하고, 자연 숫자 정렬(Natural Sort, 예: `frame_2` → `frame_10`)을 도입했습니다.
- **Desktop GUI 뷰포트 캐시·EXR 자동 감지·메모리 안전성 패치**
  - 렌더 완료 후 `_viewport_frame_cache`를 즉시 무효화하고 최신 출력 폴더 및 `_exr` 시퀀스 폴더를 자동 감지하여 뷰포트에 바로 반영되도록 수정했습니다.
  - 뷰포트에서 `alpha` 파일이 존재할 때 디스필 완료된 `comp`/`cutout` 결과를 원본 그린스크린으로 덮어쓰던 버그를 수정했습니다.
  - 뷰포트 프레임 캐시에 ~512 MB 해상도 기반 동적 메모리 상한을 적용해 4K/8K 스크러빙 시 RAM 과점유를 방지했습니다.
  - `ModelManagerDialog` 언어 리스너 누수 해제, 프로젝트 복원 시 `weights` 경로 복원, 배치 렌더 수동 힌트 적용 일관성 수정, 존재하지 않던 `desktop_check.py` 호출을 `scripts/smoke_test_runtime.py`로 교정했습니다.
- **Foundry Nuke 기즈모·프리뷰 정밀도 및 내부 배선 완전 수정**
  - Nuke `Read` 노드 직결 시 `Preview Current Frame` 또는 `Custom Range`가 전체 클립을 렌더링하던 버그를 `--start_offset` / `--num_frames` 전달로 해결했습니다.
  - `CorridorKeyer.gizmo` 내부에 누락되었던 `Read_Cutout` 노드를 추가하고, 꼬여 있던 `Switch_Output` / `Copy_Refined_Alpha` 스택 연결을 정상화했습니다.
  - 1채널 EXR 알파가 Nuke에서 `rgba.alpha = 0`으로 읽히던 문제를 `Norm_Alpha (alpha = max(r, a))` 및 DAG `Copy(rgba.red -> rgba.alpha)`로 해결하고, `video` 포맷 1-프레임 프리뷰 시 `frame_mode = "start at"`을 자동 설정하도록 개선했습니다.
  - Nuke/Resolve/Fusion 브릿지에서 개발자 로컬 `K:\` 하드코딩 경로를 제거했습니다.
- **업데이터·배치 런처·저장소 정리**
  - 자동 업데이터가 GitHub `CHANGELOG.md`에서 최신 릴리즈 노트를 동적으로 추출하고, Resolve 미설치 환경에서는 불필요한 Resolve 동기화를 건너뛰도록 개선했습니다.
  - `CorridorKey_DRAG_CLIPS_HERE.bat`가 멀티 클립 드래그 앤 드롭(`%*`)을 지원하며, `pytest.ini` 추가 및 루트의 불필요한 `[file dirname [value root.name]]` 폴더를 정리했습니다.

---

## [v0.1.9] - 2026-11-14

### 🚀 주요 업데이트 및 개선 내역 (Highlights)
- **Model Scale (`0.75`, `0.50`, `0.25`) GPU 출력 리사이즈 완벽 구현**
  - 4K/8K 고해상도 플레이트에서 VRAM 절약을 위해 `Model Scale`(`AI Plate Scale`)을 `1.0` 미만으로 설정했을 때 Stage 2 출력 단계에서 발생하던 `RuntimeError`를 해결했습니다. 이제 GPU 텐서 기반 Antialiased Bicubic 리사이즈를 통해 원본 해상도로 정확하고 빠르게 복원됩니다.
- **블루스크린(`Blue Screen`) 및 `Max / Average / None` 디스필(Despill) 엔진 구현 (GUI & Nuke)**
  - 기존 Green + Average 고정 방식에서 확장하여, 블루스크린(`Blue`) 촬영본과 `Max` / `Average` / `None` 디스필 알고리즘을 백엔드 GPU 텐서 연산(`runtime.py`), CLI(`--despill_color`, `--despill_method`), Desktop GUI, 그리고 Nuke 기즈모에 모두 완벽히 연결했습니다.
- **Desktop GUI 이미지 시퀀스(`.exr`, `.png`, `.jpg`, `.tif`, `.dpx` 등) 업로드 및 프리뷰 완벽 지원**
  - `+ Import` 파일 선택창 및 드래그 앤 드롭에서 이미지 시퀀스 프레임 파일을 직접 선택하거나 드롭하면 자동으로 시퀀스 폴더로 묶여서 로드되도록 개선했습니다.
  - 시퀀스 로드 시 좌측 미디어 카드 썸네일/해상도/프레임 수 표시, 하단 16구간 필름스트립 타임라인, 중앙 VFX 뷰포트 실시간 스크러빙(EXR Scene-Linear → sRGB 자동 톤매핑 포함), Quick Brush 브러쉬 에디터 연동, 그리고 `.exr` 시퀀스 로드 시 `Scene-Linear Input` 자동 체크를 지원합니다.
- **Desktop GUI Inspector 메모리/시간축 컨트롤 및 시퀀스 힌트 폴더(`--hint_video`) 연동**
  - `Temporal Awareness` 체크박스/슬라이더와 `GPU Memory Limit` 드롭다운을 `Hann Window` 프리셋 및 실시간 VRAM 진단기에 양방향 동기화했습니다.
  - `Full Video Hint (--hint_video)` 모드에서 동영상뿐만 아니라 연번 마스크 이미지 시퀀스 폴더도 바로 인식 및 선택할 수 있도록 개선했습니다.

---

## [v0.1.8] - 2026-11-03

### 🚀 주요 업데이트 및 개선 내역 (Highlights)
- **Nuke RotoPaint 러프 브러쉬 힌트(Rough Hint) 자연스러운 마스크 추출 패치**
  - **Hint Quality (신뢰도) 기본값 GUI 1:1 동기화 (`0.95` → `0.75`, `carry_hint_quality = 0.85`)**: 기존 Nuke에서 기본값이 `0.95`(완성형 정밀 마스크 기준)로 고정되어 러프하게 칠한 RotoPaint 브러쉬 모양이 외곽선에 그대로 굳어버리던 문제를 해결했습니다. 이제 GUI 버전의 Quick Brush와 동일하게 대략적인 브러쉬 터치만으로도 AI가 피사체의 실제 외곽선과 머리카락 디테일을 자연스럽게 찾아냅니다.
  - **Hint Quality (Trust) 슬라이더 추가**: Nuke 기즈모의 `AI Keying Parameters` 탭에 `Hint Quality (Trust)` 슬라이더(`0.0 ~ 1.0`, 기본값 `0.75`)를 추가하여 러프 힌트(`0.65~0.75`)와 정밀 알파 마스크(`0.90~0.95`) 상황에 맞춰 조절할 수 있습니다.
  - **Roto / RotoPaint 채널(`alpha` / `rgba`) 및 배경(BG) 오염 완벽 차단**: `init.py` 등에서 `RotoPaint.output`이 `alpha`로 설정된 경우 기존의 `rgb` 전용 Write 노드가 페인팅 마스크를 누락하던 문제, 그리고 `Source` 영상을 RotoPaint의 `bg`에 연결하고 칠할 때 컬러 원본 영상이 힌트 이미지에 같이 구워지던 문제를 완벽히 해결했습니다. 이제 배경을 자동으로 블랙(`0`)으로 분리하고 `max(R, G, B, A)` 순수 브러쉬 스트로크만 원본 해상도에 맞춰 정확히 추출합니다.
  - **힌트 해상도 자동 리사이즈 지원**: Roto/RotoPaint 노드의 포맷이 원본 영상 해상도와 다를 경우에도 에러 없이 모델 해상도에 맞춰 자동 보정(Lanczos4)됩니다.
- **Desktop GUI 이미지 시퀀스(`.exr`, `.png`, `.jpg`, `.tif` 등) 업로드 및 뷰포트 프리뷰 완벽 지원 패치**
  - `+ Import` 파일 선택창 및 드래그 앤 드롭에서 이미지 시퀀스 프레임 파일(`*.exr *.png *.jpg *.jpeg *.tif *.tiff *.webp *.dpx`)을 직접 선택하거나 드롭하면 자동으로 시퀀스 폴더로 묶여서 로드되도록 개선했습니다.
  - 시퀀스 로드 시 미디어 카드 썸네일/해상도/프레임 수 표시, 하단 16구간 필름스트립 타임라인, 중앙 VFX 뷰포트 실시간 스크러빙(EXR Scene-Linear → sRGB 자동 톤매핑 포함), 그리고 Quick Brush 브러쉬 에디터 연동까지 완벽하게 작동하도록 수정했습니다.
  - `.exr` 시퀀스 로드 시 `Scene-Linear Input` 옵션이 자동으로 활성화되며, Windows 한글 경로에서도 EXR/이미지 시퀀스가 깨짐 없이 읽히도록 개선했습니다.
- **Nuke EXR 랜더링 시작 프레임 1번 표준화 (VFX Standard)**
  - Nuke에서 EXR 시퀀스 랜더링 시 항상 `000000.exr`(0번 프레임)부터 생성되던 문제를 수정하여, 기본 시작 프레임을 `1`(`000001.exr`)로 표준화하고 Nuke 타임라인의 시작 프레임(`first_frame`, 예: `1`, `1001`)과 1:1로 일치하도록 개선했습니다.

---

## [v0.1.7] - 2026-11-01

### 🚀 주요 업데이트 및 개선 내역 (Highlights)
- **RTX 5090 / 4090 GPU Auto-Detect 최적화 및 속도 2~3배 향상**
  - 고용량 VRAM(24GB/32GB) 환경에서 Auto-Detect 시 청크 크기(80) 과다 할당으로 인한 Swin-Attention $O(T^2)$ 연산 병목 및 OOM 메모리 부족 현상 원천 차단
  - 최대 청크 안전 상한선(Safety Cap 48/24)을 적용하여 연산 속도 2~3배 대폭 향상
  - 안정적이고 빠른 연산을 위해 `Standard Balanced (24 chunk / 12 stride)`를 기본 추천 프로필로 안내
- **Nuke 기즈모 2-포트 단순화 (Source & FrameHint)**
  - 필수 입력 포트인 `Source`와 `FrameHint` 2개로 간소화하여 노드 그래프(DAG) 가독성 극대화 (Garbage/Core 포트 정리)
  - GPU VRAM 하드웨어 프리셋(8GB / 12GB / 16GB / 24GB+)과 Hann Window 프리셋 완벽 공존 탑재
- **Nuke EXR 랜더링 시작 프레임 1번 표준화 (VFX Standard)**
  - Nuke에서 EXR로 랜더링 시 항상 0부터 파일이 생성되던 문제를 수정하여, 1번 프레임(`000001.exr`) 또는 Nuke 타임라인의 시작 프레임에 맞춰 정확히 1:1로 넘버링되도록 패치
- **Windows Nuke 한글 환경 및 수식 오류 수정**
  - Windows Nuke 파이썬에서 한글 경로 및 UTF-8 로그 출력 시 발생하던 `UnicodeDecodeError (0xeb)` 완벽 해결
  - Nuke `Switch_Output` 노드의 따옴표 구문 오류(`unexpected '"'`) 수정
- **GUI 인앱 업데이트 시 Nuke / Resolve 스크립트 자동 동기화**
  - GUI에서 [Update Now]를 누르면 메인 코드 패치뿐만 아니라 Nuke(`~/.nuke`) 및 DaVinci Resolve(Fusion Scripts/Fuses) 연동 스크립트까지 최신 버전으로 원클릭 자동 갱신

---

## [v0.1.6] - 2026-10-31

### 🚀 주요 업데이트
- **Nuke 환경설정 자동 동기화**: `Install_To_Nuke.bat` 및 업데이트 시 `~/.nuke` 경로로 기즈모 및 파이썬 모듈 직접 배포 및 최신화
- **GUI 인앱 업데이트 확장**: GUI [Update Now] 클릭 시 Nuke 및 Resolve 브릿지 연동 스크립트 자동 갱신
- **Nuke Hann Window 프리셋 탑재**: Desktop GUI와 1:1로 일치하는 Hann Window 5단계 프리셋 지원

---

## [v0.1.5] - 2026-10-28

### 🚀 주요 업데이트
- **Alpha Hint 및 마스크 에디터 안정화**: 수동 로토 힌트 및 알파 마스크 로딩/동기화 문제 해결
- **DaVinci Resolve Fusion Fuse 브릿지 개선**: Fusion 페이지에서 인스펙터 연동 및 파이썬 경로 감지 개선
- **Windows PyTorch 메모리 할당 최적화**: `PYTORCH_ALLOC_CONF` 환경 변수를 통한 가상 메모리 단편화 완화

---

## [v0.1.4] - 2026-10-25

### 🚀 초기 릴리즈 및 안정화
- Hann Window 가중치 오버랩 블렌딩(Overlap Hann Blending) 최초 구현 (프레임 경계 깜빡임 제거)
- Nuke 1-Frame 실시간 미리보기 및 Nuke 전용 CorridorKeyer 기즈모 탑재
- DaVinci Resolve Studio / Fusion Studio 퓨즈 연동
