# VFXEdu CorridorKey 2.0 - Changelog

모든 버전의 업데이트 내역과 패치 상세 사항을 기록합니다.
GitHub 릴리즈 시 해당 버전의 내용이 릴리즈 노트 및 GUI 업데이트 창에 자동으로 반영됩니다.
모든 이전 릴리즈 버전은 GitHub 릴리즈 페이지에 영구 보존됩니다.

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
