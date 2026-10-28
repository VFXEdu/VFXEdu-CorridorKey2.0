# CorridorKey 2.0 Professional Desktop Suite

`Launch_GUI.bat`를 더블 클릭하여 실행할 수 있는 CorridorKey 2.0 풀스펙 GUI 데스크톱 스위트입니다.

---

## 🌟 주요 기능 및 새로운 기능

### 1. 🖌️ 대화형 브러시 마스크 편집기 (Interactive Brush Mask Editor)
- **원클릭 브러시 마스크 추출**: 원하는 영상의 특정 프레임을 보고 **[🖌️ 브러시 마스크 편집기]**를 열어 직접 전경 영역을 칠할 수 있습니다.
- **도구 모음**:
  - `전경 브러시 (White)` [B]: 마스크를 칠해 대상 객체(인물, 물체) 지정
  - `지우개 / 배경 (Black)` [E]: 잘못 칠한 영역 지우기
  - `영역 채우기 / 지우기`: 사각형 드래그로 넓은 영역을 한 번에 추가 또는 삭제
- **브러시 세부 조절**:
  - **크기 (Size)**: 1px ~ 300px (슬라이더, `[` / `]` 키, Ctrl+휠)
  - **경도 (Hardness / Feather)**: 0%(가우시안 소프트 브러시) ~ 100%(하드 엣지)
  - **불투명도 (Opacity / Flow)**: 5% ~ 100%
- **마스크 다듬기**:
  - `팽창 (+3px)` / `수축 (-3px)`: 버튼 하나로 마스크 영역을 확장하거나 축소
  - `페더 블러 (Gaussian Blur)`: 마스크 가장자리를 자연스럽게 부드럽게 스무딩
  - `반전 (Invert)`: 전경과 배경을 즉시 반전
  - `전체 채우기` / `전체 지우기`
  - `실행 취소 (Undo)` [Ctrl+Z] / `다시 실행 (Redo)` [Ctrl+Y]
- **화면 보기 모드**:
  - **마스크 오버레이 (Overlay)**: 원본 영상 위에 붉은색 반투명 마스크 표시
  - **순수 마스크 (Matte B&W)**: 흑백 알파 마스크 뷰
  - **체커 컷아웃 (Cutout)**: 마스크로 분리된 전경만 투명 체커보드 위에 실시간 표시
  - **원본 영상 (Source RGB)**
- **완료 및 내보내기**:
  - **⭐ [첫 프레임 힌트로 즉시 적용]**: 그린 마스크를 `<clip>FrameHint.png`로 자동 저장하고 CorridorKey의 첫 프레임 마스크로 즉시 등록
  - **💾 [마스크 PNG 저장]**: 알파 마스크를 별도 이미지 파일로 저장
  - **✂️ [전경 RGBA 추출]**: 브러시로 선택한 영역만을 투명 배경 PNG로 바로 추출하여 저장

---

### 2. CorridorKey 2.0 공식 기능 100% 구현
공식 CorridorKey 2.0 레포지토리의 모든 옵션과 기능이 완벽하게 연동됩니다:

1. **Hann Window (시간적 연속성 윈도우)**:
   - `자동 감지 (Auto)`: 남은 GPU VRAM과 해상도에 맞춰 최적 윈도우 자동 선택 (권장)
   - `80/40 (최대 연속성)`: 24GB+ 고성능 GPU용
   - `48/24 (고품질)`: 16GB+ GPU 권장
   - `24/12 (표준 균형)`: 8~12GB GPU
   - `8/4 (저메모리)`: 6~8GB GPU
   - `1/1 (단일 프레임)`: 윈도우 없음, 프레임별 독립 키잉
   - `사용자 직접 지정 (Custom)`: Chunk 및 Stride 자유 설정
2. **동반 힌트 자동 탐지 (Auto-Detect Companion Hints)**:
   - 영상을 드래그하거나 추가하면 같은 폴더에 있는 `<clip>FrameHint.png` 또는 `<clip>_AlphaHint.mp4`를 자동으로 탐지하여 힌트로 즉시 등록
3. **힌트 신뢰도 및 전파 제어**:
   - `--hint_quality`: 명시적 힌트 신뢰도 (0.0 ~ 1.0, 기본 0.95)
   - `--carry_hint_quality`: Hann 윈도우 간 전파되는 힌트 신뢰도 (기본 0.95)
   - `--no_carry_hint`: 이전 윈도우의 예측 마스크 피드백을 끄고 원본 힌트만 엄격 적용
4. **VFX 선형 컴포지팅 (Linear Compositing)**:
   - `--cutout_linear`: 투명 영상(cutout)을 sRGB가 아닌 직선형 씬-리니어(Scene-Linear) RGB로 출력
   - `--frame_dir_linear`: EXR/시퀀스 프레임 입력을 씬-리니어 RGB로 취급
   - `--exr_dtype`: `half` (16-bit Float, VFX 표준) 또는 `float` (32-bit Float)
5. **실험적 선형 색상 조정 (Linear Color Controls)**:
   - `--linear_brightness`: 선형 밝기 조절 (기본 1.0)
   - `--linear_contrast`: 선형 대비 조절 (기본 1.0)
   - `--linear_contrast_pivot`: 대비 피벗 포인트 (기본 0.18)
6. **고급 비디오 인코딩 (FFmpeg)**:
   - 코덱 선택: `libx264` (CPU), `h264_nvenc` (NVIDIA 가속), `hevc_nvenc` (H.265 가속), `prores_ks` (Apple ProRes)
   - CRF 화질 조절 (0~51, 기본 12)
   - 픽셀 포맷: `yuv444p10le` (10-bit 고화질), `yuv444p` (8-bit 호환), `yuv420p`
   - 프리셋: ultrafast, fast, medium, slow, veryslow
7. **테스트 구간 및 모델 스케일링**:
   - 구간 선택: `begin` (처음부터), `middle` (중간), `random_middle` (랜덤 중간 구간)
   - `--seed`: 난수 시드 지정
   - `--model_scale`: 1.0(네이티브 해상도) 외 0.5, 0.75 등으로 초고속 프리뷰 가능
   - `--stage2_batch`: Stage-2 배치 크기 지정

---

### 3. 🌐 다국어 지원 (Bilingual: English Default & 한국어 전환)
- **기본 언어는 영어(English)**로 설정되어 있어 글로벌 사용자 환경에서도 바로 사용 가능합니다.
- 상단 헤더 우측의 언어 선택 드롭다운(`🌐 Language`)을 통해 **English ↔ 한국어**를 프로그램 재시작 없이 실시간으로 즉시 전환할 수 있습니다.
- 사용자가 선택한 언어 설정은 [gui_config.json](file:///k:/________________VFXEdu_Script/CorridorKeyer2.0/gui_config.json)에 자동 저장되어 다음 실행 시에도 유지됩니다.
- 브러시 편집기, 프리뷰 HUD, 라이선스 안내 다이얼로그, 툴팁, 로그 메시지 등 모든 UI 텍스트가 완벽하게 다국어로 지원됩니다.

---

### 4. 🪄 RGVI (AAAI 2025) 비디오 오브젝트 리무버 & 클린 플레이트 (Clean Plate)
- **최신 SOTA 영상 인페인팅 엔진 탑재**:
  - 연세대학교 & Adobe Research 팀의 최신 논문 *"Elevating Flow-Guided Video Inpainting with Reference Generation"* (AAAI 2025) 파이프라인을 완전 통합 탑재했습니다.
  - 마스크로 지정한 인물, 와이어, 장비, 불필요한 물체를 영상에서 감쪽같이 지우고 깨끗한 배경을 복원합니다.
- **원클릭 통합 워크플로우**:
  - `02 출력 설정`에서 **`[✔] 클린 플레이트 (RGVI 배경 복원)`**을 체크하면 CorridorKey 2.0이 객체 마스크를 정밀하게 자동 추적하고, RGVI 엔진이 이어서 고화질 클린 플레이트(`<clip>_clean_plate.mp4`)를 자동 렌더링합니다.
  - 브러시 마스크 편집기에서 **`[✨ 객체 지우기 (RGVI)]`** 버튼을 누르면 마스크 저장과 동시에 클린 플레이트 모드가 즉시 세팅됩니다.
- **VFX 프로덕션급 화질**:
  - AI 생성 그림체로 뭉개지는 기존 디퓨전 방식과 달리, **실제 카메라에 찍힌 다른 시간대의 배경 픽셀을 양방향 옵티컬 플로우(RAFT + FCNet)와 원샷 픽셀 풀링(One-Shot Pulling)**으로 당겨와 1:1 합성하므로 노이즈, 필름 그레인, 디테일이 100% 원본 그대로 살아납니다.
  - 독립 CLI 실행 지원: `python inpaint_rgvi.py --video <input.mp4> --mask <alpha.mp4> --output <clean.mp4>`

---

### 5. 📜 저작권 및 무료 배포 가이드 (About & License)
- 상단 헤더의 **[ℹ️ About & License]** 버튼을 통해 라이선스 전문(CC BY-NC-SA 4.0), 파운데이션 모델 서드파티 고지, 저작권 크레딧을 언제든지 열람할 수 있습니다.
- 상세한 배포 체크리스트 및 가이드는 [DISTRIBUTION_GUIDE.md](file:///k:/________________VFXEdu_Script/CorridorKeyer2.0/DISTRIBUTION_GUIDE.md)를 참고하세요.

---

## 🚀 빠른 시작 가이드 (무설치 포터블 배포 방식)

CorridorKey 2.0은 **무설치 포터블 런타임(Embedded Python 3.12 + FFmpeg 바이너리 동봉)**을 기본 지원하므로, 사용자의 PC에 Python이나 FFmpeg가 없어도 바로 실행할 수 있습니다.

1. **최초 1회 설정**: `Setup_GUI.bat` 더블 클릭 (동봉된 Embedded Python으로 PyTorch 2.9.1+CUDA 12.8 및 필수 패키지 자동 설치).
2. **GUI 실행**: `Launch_GUI.bat` 더블 클릭.
3. **영상 추가**: 작업할 동영상이나 이미지 시퀀스 폴더를 창에 드래그하거나 [영상 추가] 버튼 클릭.
4. **브러시 마스크 지정**:
   - 미리보기 슬라이더에서 원하는 프레임(첫 프레임 등)을 확인한 뒤 **[🖌️ 브러시 마스크 편집기 열기]** 클릭.
   - 브러시로 대상 객체를 칠하고 **[⭐ 첫 프레임 힌트로 즉시 적용]** 클릭.
5. **출력 선택**: 알파(`alpha`), 전경(`fg`), 체크무늬(`checker`), 투명 영상(`cutout`) 체크.
6. **처리 시작**: **[🚀 키잉 처리 시작]** 클릭.
7. **결과 확인**: 완료 후 우측 결과 프리뷰에서 각 채널을 확인하고, **[결과 폴더 열기]**로 최종 마스터 파일 접근.

---

## 🧪 검증 및 테스트 결과

- **OS / GPU**: Windows 11 / NVIDIA GeForce RTX 4090 (24GB VRAM)
- **환경**: Embedded Python 3.12.10 / PyTorch 2.9.1+cu128 / Standalone FFmpeg 2026
- **단위 및 통합 테스트**: `.\venv\Scripts\python.exe test_desktop.py` (12개 통합 테스트 전체 통과)
- **E2E 모델 추론**: 실제 CorridorKey v2 safetensors 및 3개 파운데이션 모델(C-RADIO, MoGe-2, RVM) 연동, 첫 프레임 브러시 마스크 힌트를 적용한 GPU 추론(Alpha, Checker, Cutout ProRes 4444) 정상 완료 검증.
