"""CorridorKey 2.0 Internationalization (i18n) Module.

Provides English (default) and Korean localization with runtime language switching
and persistent user preference storage.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List

LANG_EN = "en"
LANG_KO = "ko"
DEFAULT_LANG = LANG_EN

CONFIG_PATH = Path(__file__).resolve().parent / "gui_config.json"

_current_lang = DEFAULT_LANG
_listeners: List[Callable[[str], None]] = []


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    LANG_EN: {
        # App Header
        "app_title": "CORRIDORKEY 2.0",
        "app_sub": "Green Screen Slain · AI Native Video & HDR Keying Suite",
        "window_title": "CorridorKey 2.0 · Professional Desktop Suite",
        "btn_about": "ℹ️  About & License",
        "lbl_language": "🌐 Language:",
        "license_badge": "CC BY-NC-SA 4.0 · Corridor Digital LLC",

        # Workbench Layout
        "wb_title": "CORRIDORKEY WORKBENCH",
        "wb_project": "Project: Default",
        "wb_take": "Take A",
        "wb_mode_single": "Single",
        "wb_mode_wipe": "Wipe",
        "wb_mode_side": "Side by side",
        "wb_chan_composite": "Composite (Checkerboard)",
        "wb_chan_alpha": "Alpha Matte",
        "wb_chan_cutout": "Cutout (Black)",
        "wb_chan_clean": "Clean Plate (SD)",
        "wb_chan_orig": "Original Video",
        "wb_media_bin": "MEDIA",
        "wb_import": "+ Import...",
        "wb_queue": "QUEUE",
        "wb_queue_empty": "No renders yet. Click Render or Add to queue to add the current clip.",
        "wb_inspector": "INSPECTOR",
        "wb_deliver": "DELIVER",
        "wb_awareness": "Awareness?",
        "wb_time_awareness": "Time Awareness",
        "wb_gpu_mem_limit": "GPU Memory Limit",
        "wb_low_gpu_mem": "Low GPU Memory",
        "wb_sec_status": "Status",
        "wb_gpu_memory": "GPU Memory",
        "wb_sec_memory": "Core & Memory",
        "wb_sec_hint": "Alpha Hint",
        "wb_sec_despill": "Despill",
        "wb_sec_clean_plate": "Clean Plate (RGVI Remover)",
        "wb_sec_output": "Output & Advanced",
        "wb_btn_render": "Render",
        "wb_btn_add_queue": "Add to Queue",
        "wb_btn_cancel": "Cancel",
        "wb_fit": "Fit",
        "wb_fit_100": "100%",
        "wb_fit_50": "50%",
        "wb_format_note": "Premultiplied RGBA, Rec.709. Saved in a new folder inside output folder.",

        # Group 1: Inputs & Hints
        "grp_input": "01  Input Queue & Mask Hints",
        "btn_add_videos": "Add Videos",
        "btn_add_folder": "Add Sequence",
        "btn_remove": "Remove",
        "btn_clear_queue": "Clear All",
        "lbl_keying_mode": "Keying Mode",
        "mode_no_hint": "Auto · No Hint (Subject Decided by Model)",
        "mode_first_frame": "First-Frame Mask (--hint_first_frame)",
        "mode_video_hint": "Full Video Hint (--hint_video)",
        "lbl_hint_file": "Hint File",
        "hint_placeholder": "Auto-detect companion hint or browse...",
        "btn_browse": "Browse",
        "btn_brush_editor": "🖌️  Open Brush Mask Editor (Paint Mask)",
        "btn_brush_editor_tip": "Paint foreground mask directly on selected frame and apply as hint",
        "lbl_hint_quality": "Hint Quality",
        "lbl_explicit_quality": "Explicit Quality:",
        "lbl_carry_quality": "Carry Quality:",
        "chk_no_carry": "Disable Hint Carry (--no_carry_hint)",
        "chk_no_carry_tip": "Do not carry forward model predictions; strictly follow the provided hint video",

        # Group 2: Outputs & Format
        "grp_output": "02  Output Settings & Formats",
        "lbl_output_dir": "Output Directory",
        "lbl_format": "Output Format",
        "format_video": "Video (MP4 / ProRes 4444) · Display Preview",
        "format_exr": "OpenEXR Sequences · Unclamped Linear HDR",
        "lbl_exr_dtype": "EXR Precision",
        "exr_half": "half (16-bit Float) — VFX Interchange Standard",
        "exr_float": "float (32-bit Float) — Full Precision HDR",
        "lbl_despill": "Despill Strength",
        "chk_cutout_linear": "Export Cutout as Straight Linear RGB (--cutout_linear)",
        "chk_cutout_linear_tip": "Export straight linear RGB for VFX compositing pipelines instead of sRGB",
        "out_alpha": "Alpha Matte",
        "out_fg": "Foreground (FG)",
        "out_checker": "Checker Comp",
        "out_cutout": "Cutout (Alpha)",
        "out_clean_plate": "Clean Plate (RGVI Remover)",
        "lbl_clean_plate_prompt": "Clean Plate AI Prompt (Optional):",
        "placeholder_clean_plate_prompt": "e.g. empty street, clean wall, natural texture (Leave empty for auto)",

        # Tabs
        "tab_vram": "⚡ VRAM & Performance",
        "tab_enc": "🎬 Range & Encoding",
        "tab_color": "🎨 Linear Color (VFX)",

        # Tab 1: VRAM & Performance
        "lbl_hann": "Hann Window",
        "hann_auto": "Auto-Detect (Optimized per clip from free GPU memory — Recommended)",
        "hann_80_40": "Max Continuity (80 chunk / 40 stride) — 24GB+ High-end GPU",
        "hann_48_24": "High Quality (48 chunk / 24 stride) — 16GB+ GPU Recommended",
        "hann_24_12": "Standard Balanced (24 chunk / 12 stride) — 8~12GB GPU",
        "hann_8_4": "Low VRAM (8 chunk / 4 stride) — 6~8GB GPU",
        "hann_1_1": "Single Frame (1 chunk / 1 stride) — Lowest Peak Memory",
        "hann_custom": "Custom Size",
        "lbl_custom_hann": "Custom Window",
        "chk_low_vram": "Force Staged Low-VRAM Mode (--low_vram)",
        "chk_low_vram_tip": "Precomputes foundation features to disk memmaps; reduces peak VRAM significantly",
        "lbl_model_scale": "Model Scale",
        "lbl_model_scale_tip": "1.0 is native resolution. 0.5 or 0.75 enables ultra-fast previews",
        "lbl_stage2_batch": "Stage 2 Batch",
        "lbl_weights": "Model Weights",
        "weights_placeholder": "Default: weights/corridorkey_v2.safetensors",

        # Tab 2: Range & Video Encoding
        "lbl_num_frames": "Frames to Process",
        "special_all_frames": "All Frames",
        "lbl_start_mode": "Test Segment",
        "start_begin": "From Beginning (begin)",
        "start_middle": "Center Segment (middle)",
        "start_random_middle": "Deterministic Random Segment (random_middle)",
        "lbl_seed": "Random Seed",
        "lbl_fps": "Sequence FPS",
        "chk_linear": "Treat frame sequences as scene-linear RGB (--frame_dir_linear)",
        "lbl_codec": "Video Codec",
        "codec_x264": "libx264 (H.264 CPU Standard · 10-bit Recommended)",
        "codec_h264_nvenc": "h264_nvenc (NVIDIA GPU Accelerated · 8-bit)",
        "codec_hevc_nvenc": "hevc_nvenc (NVIDIA GPU Accelerated HEVC/H.265)",
        "codec_prores": "prores_ks (Apple ProRes Standard)",
        "lbl_crf": "CRF Quality (Lower = Higher Quality):",
        "lbl_crf_row": "CRF Quality",
        "lbl_pix_fmt": "Pixel Format",
        "pix_yuv444p10le": "yuv444p10le (10-bit 4:4:4 Master Quality)",
        "pix_yuv444p": "yuv444p (8-bit 4:4:4 Standard Compatibility)",
        "pix_yuv420p": "yuv420p (8-bit 4:2:0 Web Compatibility)",
        "lbl_preset": "Encoding Speed",

        # Tab 3: Color Tuning
        "lbl_bright": "Linear Brightness",
        "lbl_contrast": "Linear Contrast",
        "lbl_pivot": "Contrast Pivot",
        "note_color": "Experimental linear-light color controls for research. Leave at defaults (1.0/1.0/0.18) for normal production.",

        # Right Previews
        "preview_source": "03  Source Plate Preview",
        "preview_result": "04  Keyed Output Preview",
        "empty_preview": "Select a clip to display frames",
        "btn_brush_preview": "🖌️ Edit Brush Mask",
        "btn_brush_preview_tip": "Open the currently previewed frame in Brush Mask Editor",
        "frame_caption": "{name}  ·  {w} × {h}  ·  Frame {frame}",

        # Bottom Bar
        "status_ready": "Ready · All CorridorKey 2.0 features enabled",
        "btn_check": "System Check",
        "btn_download": "Download Weights",
        "btn_run": "🚀  Start Keying",
        "btn_stop": "Stop",
        "btn_open_folder": "Open Output Folder",
        "status_processing": "Processing {current}/{total} · {name}",
        "status_stopping": "Stopping process tree...",
        "status_stopped": "Stopped · Incomplete output files may remain",
        "status_done": "All jobs completed",
        "status_failed": "Failed (Exit code {code}) · Check log below",

        # Brush Editor Dialog
        "be_title": "Brush Mask Editor — {clip} ({w}×{h})",
        "be_grp_tools": "01  Drawing Tools",
        "be_btn_brush": "🖌️  Foreground Brush (White) [B]",
        "be_btn_eraser": "🧹  Eraser / Background (Black) [E]",
        "be_btn_rect_add": "🔲  Fill Rect (Foreground)",
        "be_btn_rect_sub": "⬛  Erase Rect (Background)",
        "be_grp_props": "02  Brush Parameters",
        "be_lbl_size": "Radius Size:",
        "be_lbl_hardness": "Edge Hardness (Feather):",
        "be_lbl_opacity": "Paint Opacity (Flow):",
        "be_grp_edit": "03  Mask Operations & Refine",
        "be_btn_dilate": "➕  Dilate (+3px)",
        "be_btn_dilate_tip": "Expand mask boundary outwards",
        "be_btn_erode": "➖  Erode (-3px)",
        "be_btn_erode_tip": "Shrink mask boundary inwards",
        "be_btn_blur": "🌫️  Feather Blur (Smooth)",
        "be_btn_blur_tip": "Smooth edges with Gaussian blur",
        "be_btn_invert": "🔄  Invert Mask",
        "be_btn_invert_tip": "Invert foreground and background",
        "be_btn_clear": "🗑️  Clear All",
        "be_btn_fill": "⬜  Fill All",
        "be_btn_undo": "↩️  Undo [Ctrl+Z]",
        "be_btn_redo": "↪️  Redo [Ctrl+Y]",
        "be_grp_view": "04  Display View Mode",
        "be_view_overlay": "🔴  Mask Overlay",
        "be_view_matte": "⬛⬜  Pure Matte (B&W)",
        "be_view_cutout": "🏁  Cutout Checkerboard",
        "be_view_rgb": "🖼️  Source RGB",
        "be_btn_fit": "Fit Window [F]",
        "be_btn_100": "100% Original",
        "be_lbl_stats": "Mask Area: {pct:.1f}%  ·  Resolution: {w} × {h}",
        "be_grp_action": "05  Apply & Export",
        "be_btn_apply": "⭐  Apply as First-Frame Hint",
        "be_btn_apply_tip": "Save companion FrameHint.png and automatically bind as first-frame hint",
        "be_btn_export_mask": "💾  Export Mask PNG",
        "be_btn_export_cutout": "✂️  Extract FG RGBA",
        "be_btn_import": "📂  Import Mask...",
        "be_hud": "Zoom: {zoom}%  ·  [F] Fit Window  ·  Double-Click: Fit  ·  Space/Right-Drag: Pan",
        "be_no_frame": "No frame image to display",
        "be_msg_no_mask": "No mask data available.",
        "be_msg_save_fail": "Failed to save mask file:\n{exc}",
        "be_dlg_save_mask": "Save Mask File",
        "be_msg_save_done": "Mask saved successfully:\n{path}",
        "be_msg_save_err": "Error saving mask file:\n{exc}",
        "be_dlg_save_cutout": "Save Foreground Cutout (RGBA)",
        "be_msg_cutout_done": "Foreground cutout exported successfully:\n{path}",
        "be_msg_cutout_err": "Error extracting foreground cutout:\n{exc}",
        "be_dlg_import_mask": "Select Existing Mask File",
        "be_msg_import_fail": "Failed to read mask file:\n{exc}",
        "msg_error": "Error",
        "msg_save_complete": "Saved",
        "msg_export_complete": "Exported",
        "msg_load_fail": "Load Failed",
        "preview_unavailable": "Preview not available — please check output folder",

        # Tool Rail Tips
        "rail_media_tip": "Media Bin (Clips & Takes)",
        "rail_layers_tip": "Matte & Layer Inspector",
        "rail_wipe_tip": "Wipe & Compare Tools",
        "rail_history_tip": "Queue & Render History",
        "rail_color_tip": "Despill & Color Tuning",
        "rail_models_tip": "AI Models & Weights",
        "rail_export_tip": "Deliver & Export",

        # About & License Dialog
        "about_dialog_title": "CorridorKey 2.0 · About & License",
        "about_tab_summary": "📋 About & Legal Terms",
        "about_tab_license": "📜 License Text (LICENSE)",
        "about_tab_third": "🧩 Third-Party Notices",
        "about_btn_close": "Close",

        # Dialogs & Messages
        "msg_warn_title": "Notice",
        "msg_no_clip_for_brush": "Please add and select a video or image sequence before opening the brush editor.",
        "msg_error_input_required": "Please add at least one video or image sequence to process.",
        "msg_error_hint_single": "When using a mask hint, specify only 1 input clip or process clips individually.",
        "msg_error_output_required": "Please specify an output directory.",
        "msg_config_check": "Configuration Check",
        "msg_running_title": "Job in Progress",
        "msg_running_text": "Please click Stop and wait for processes to terminate before closing.",
        "dlg_select_videos": "Select Video Files",
        "dlg_select_folder": "Select Image Sequence Folder",
        "dlg_select_hint": "Select Mask Hint File",
        "dlg_select_out_dir": "Select Output Folder",
        "dlg_select_file": "Select File",
        "log_hint_companion_first": "✨ Companion first-frame hint detected: {name}",
        "log_hint_companion_video": "✨ Companion mask video hint detected: {name}",
        "log_brush_applied": "🖌️ Brush mask applied: {path}",
        "log_job_start": "\n▶ Job Started [{name}]\nInput: {src}\nOutput: {dst}",
        "log_kill_failed": "Failed to terminate process tree. You may try stopping again.",
        "status_checking_env": "Checking environment...",
        "status_downloading_weights": "Downloading model weights (~5GB, one-time setup)...",
        "status_check_passed": "Environment check passed",
        "status_download_done": "Model download completed",
        "status_mkdir_failed": "Failed to create output directory: {err}",
        "status_proc_start_failed": "Failed to start process: {err}",
        "status_rgvi_running": "Reconstructing clean background with RGVI (AAAI 2025)...",
        "status_rgvi_done": "RGVI clean plate completed",
        "log_rgvi_start": "\n▶ [RGVI] Starting Video Object Removal & Inpainting...\nVideo: {src}\nMask: {mask}\nOutput: {dst}",
        "log_rgvi_done": "✨ [RGVI] Clean plate generated: {path}",

        # Model Manager
        "btn_models": "📦  Model Manager",
        "btn_models_tip": "Manage and download AI model weights",
        "model_mgr_title": "AI Model & Weight Manager",
        "model_mgr_desc": "Inspect installed models, download required foundation weights, and manage optional features.",
        "model_mgr_path_lbl": "Model Directory:",
        "model_mgr_btn_open_folder": "📂 Open Weights Folder",
        "model_mgr_req_header": "Required Core Models (Keying)",
        "model_mgr_opt_header": "Optional Feature Models",
        "model_mgr_btn_dl_required": "⚡ Download All Required Models (~4.8 GB)",
        "model_mgr_btn_dl_rgvi": "✨ Download Clean Plate Model (~47 MB)",
        "model_mgr_btn_refresh": "🔄 Refresh",
        "model_mgr_btn_close": "Close",
        "model_mgr_btn_cancel": "Cancel Download",
        "model_mgr_installed": "Installed",
        "model_mgr_missing": "Missing",
        "model_mgr_downloading": "Downloading...",
        "model_mgr_btn_download": "Download",
        "model_mgr_req_badge": "Required",
        "model_mgr_opt_badge": "Optional",
        "prompt_missing_req_title": "Required AI Models Missing",
        "prompt_missing_req_msg": "One or more required AI foundation models are missing:\n\n{models}\n\nWould you like to open the Model Manager to download them now?",
        "prompt_rgvi_needed_title": "Clean Plate Model Required",
        "prompt_rgvi_needed_msg": "The RGVI Clean Plate AI model (~47 MB) is required to remove objects and generate clean plates.\n\nWould you like to download it now?",
        "status_model_downloading": "Downloading model weights: {model}...",
        "status_model_download_done": "Model weights ready.",
    },

    LANG_KO: {
        # App Header
        "app_title": "CORRIDORKEY 2.0",
        "app_sub": "그린스크린 종결 · AI 네이티브 비디오 & HDR 키잉 스위트",
        "window_title": "CorridorKey 2.0 · 데스크톱 스위트 (한국어)",
        "btn_about": "ℹ️  정보 및 라이선스",
        "lbl_language": "🌐 언어 (Language):",
        "license_badge": "CC BY-NC-SA 4.0 · Corridor Digital LLC",

        # Workbench Layout
        "wb_title": "CORRIDORKEY WORKBENCH",
        "wb_project": "프로젝트: 기본",
        "wb_take": "Take A",
        "wb_mode_single": "단일 뷰",
        "wb_mode_wipe": "와이프 비교",
        "wb_mode_side": "나란히 비교",
        "wb_chan_composite": "체커보드 합성 (Composite)",
        "wb_chan_alpha": "알파 매트 (Alpha)",
        "wb_chan_cutout": "블랙 컷아웃 (Cutout)",
        "wb_chan_clean": "클린 플레이트 (Clean Plate)",
        "wb_chan_orig": "원본 영상 (Original)",
        "wb_media_bin": "미디어 빈 (MEDIA)",
        "wb_import": "+ 가져오기...",
        "wb_queue": "대기열 (QUEUE)",
        "wb_queue_empty": "렌더링 작업이 없습니다. 렌더 또는 큐 추가를 클릭하세요.",
        "wb_inspector": "인스펙터 (INSPECTOR)",
        "wb_deliver": "배송 / 출력 (DELIVER)",
        "wb_awareness": "Awareness?",
        "wb_time_awareness": "시간 연속성 (Time Awareness)",
        "wb_gpu_mem_limit": "GPU 메모리 한도",
        "wb_low_gpu_mem": "저사양 VRAM 모드",
        "wb_sec_status": "Status (상태)",
        "wb_gpu_memory": "GPU Memory",
        "wb_sec_memory": "엔진 및 메모리",
        "wb_sec_hint": "알파 힌트 (Alpha Hint)",
        "wb_sec_despill": "디스필 (Despill)",
        "wb_sec_clean_plate": "클린 플레이트 (RGVI Remover)",
        "wb_sec_output": "출력 및 고급 옵션",
        "wb_btn_render": "렌더링 (Render)",
        "wb_btn_add_queue": "큐에 추가",
        "wb_btn_cancel": "렌더 취소",
        "wb_fit": "맞춤 (Fit)",
        "wb_fit_100": "100%",
        "wb_fit_50": "50%",
        "wb_format_note": "프리멀티플라이 RGBA, Rec.709. 출력 폴더 내 하위 폴더로 저장됩니다.",

        # Group 1: Inputs & Hints
        "grp_input": "01  입력 대기열 및 마스크 힌트 (Input & Hints)",
        "btn_add_videos": "영상 추가",
        "btn_add_folder": "시퀀스 폴더",
        "btn_remove": "선택 삭제",
        "btn_clear_queue": "전체 비우기",
        "lbl_keying_mode": "키잉 모드",
        "mode_no_hint": "자동 · 힌트 없음 (모델이 주체 판단)",
        "mode_first_frame": "첫 프레임 마스크 (--hint_first_frame)",
        "mode_video_hint": "전체 마스크 영상 (--hint_video)",
        "lbl_hint_file": "힌트 파일",
        "hint_placeholder": "동반 힌트 자동 탐지 또는 직접 선택...",
        "btn_browse": "찾기",
        "btn_brush_editor": "🖌️  브러시 마스크 편집기 열기 (Paint Mask)",
        "btn_brush_editor_tip": "현재 선택된 비디오 프레임에 직접 브러시로 마스크를 칠하고 첫 프레임 힌트로 자동 등록합니다.",
        "lbl_hint_quality": "힌트 신뢰도",
        "lbl_explicit_quality": "명시적 힌트 신뢰도:",
        "lbl_carry_quality": "캐리 힌트 신뢰도:",
        "chk_no_carry": "힌트 캐리(전파) 끄기 (--no_carry_hint)",
        "chk_no_carry_tip": "이전 윈도우 예측 마스크 피드백을 끄고 원본 힌트 영상만 엄격하게 적용",

        # Group 2: Outputs & Format
        "grp_output": "02  출력 설정 (Outputs & Format)",
        "lbl_output_dir": "저장 위치",
        "lbl_format": "저장 형식",
        "format_video": "영상 (MP4 / ProRes 4444) · 디스플레이 프리뷰",
        "format_exr": "EXR 시퀀스 (OpenEXR) · 비압축 씬-리니어 HDR",
        "lbl_exr_dtype": "EXR 정밀도",
        "exr_half": "half (16-bit Float) — VFX 표준 포맷",
        "exr_float": "float (32-bit Float) — 극단적 HDR 정밀도",
        "lbl_despill": "색 번짐 제거 (Despill)",
        "chk_cutout_linear": "투명 영상을 씬-리니어 RGB로 내보내기 (--cutout_linear)",
        "chk_cutout_linear_tip": "VFX 합성 파이프라인에서 sRGB 대신 직선형 선형 RGB로 저장",
        "out_alpha": "알파 (Alpha)",
        "out_fg": "전경 (FG)",
        "out_checker": "체크 합성 (Checker)",
        "out_cutout": "투명 영상 (Cutout)",
        "out_clean_plate": "클린 플레이트 (RGVI 배경 복원)",
        "lbl_clean_plate_prompt": "클린 플레이트 AI 프롬프트 (선택):",
        "placeholder_clean_plate_prompt": "예: empty street, clean wall, natural texture (비워두면 자동 완성)",

        # Tabs
        "tab_vram": "⚡ VRAM & 성능",
        "tab_enc": "🎬 구간 & 인코딩",
        "tab_color": "🎨 선형 색상 (Color)",

        # Tab 1: VRAM & Performance
        "lbl_hann": "Hann 윈도우",
        "hann_auto": "자동 감지 (GPU 메모리에 맞춰 자동 선택 — 권장)",
        "hann_80_40": "최대 연속성 (80 chunk / 40 stride) — 24GB+ GPU",
        "hann_48_24": "고품질 권장 (48 chunk / 24 stride) — 16GB+ GPU",
        "hann_24_12": "표준 균형 (24 chunk / 12 stride) — 8~12GB GPU",
        "hann_8_4": "저메모리 (8 chunk / 4 stride) — 6~8GB GPU",
        "hann_1_1": "단일 프레임 (1 chunk / 1 stride) — 최저 메모리",
        "hann_custom": "사용자 직접 지정 (Custom Size)",
        "lbl_custom_hann": "커스텀 윈도우",
        "chk_low_vram": "저메모리 단계별 추론 모드 강제 (--low_vram)",
        "chk_low_vram_tip": "VFM 특성을 디스크 임시 파일에 기록하여 VRAM 사용량을 대폭 낮춤",
        "lbl_model_scale": "모델 추론 스케일",
        "lbl_model_scale_tip": "1.0은 원본 네이티브 해상도입니다. 0.5 등으로 축소하여 초고속 테스트 가능",
        "lbl_stage2_batch": "Stage 2 배치",
        "lbl_weights": "모델 가중치",
        "weights_placeholder": "기본: weights/corridorkey_v2.safetensors",

        # Tab 2: Range & Video Encoding
        "lbl_num_frames": "처리 프레임 수",
        "special_all_frames": "전체 영상 처리",
        "lbl_start_mode": "테스트 구간",
        "start_begin": "처음부터 (begin)",
        "start_middle": "중간 구간 (middle)",
        "start_random_middle": "랜덤 중간 구간 (random_middle)",
        "lbl_seed": "랜덤 시드 (Seed)",
        "lbl_fps": "시퀀스 FPS",
        "chk_linear": "이미지 시퀀스 입력이 선형 RGB (--frame_dir_linear)",
        "lbl_codec": "비디오 코덱",
        "codec_x264": "libx264 (H.264 CPU 표준 · 10-bit 권장)",
        "codec_h264_nvenc": "h264_nvenc (NVIDIA GPU 가속 · 8-bit)",
        "codec_hevc_nvenc": "hevc_nvenc (NVIDIA GPU 가속 HEVC/H.265)",
        "codec_prores": "prores_ks (Apple ProRes 표준)",
        "lbl_crf": "CRF 화질 (낮을수록 고화질):",
        "lbl_crf_row": "CRF 화질",
        "lbl_pix_fmt": "픽셀 포맷",
        "pix_yuv444p10le": "yuv444p10le (10-bit 4:4:4 고품질 마스터)",
        "pix_yuv444p": "yuv444p (8-bit 4:4:4 일반 호환)",
        "pix_yuv420p": "yuv420p (8-bit 4:2:0 웹 표준 호환)",
        "lbl_preset": "인코딩 속도",

        # Tab 3: Color Tuning
        "lbl_bright": "선형 밝기 조정",
        "lbl_contrast": "선형 대비 조정",
        "lbl_pivot": "대비 피벗 포인트",
        "note_color": "실험적 선형-빛 컬러 보정입니다. 일반적인 프로덕션 작업 시에는 기본값(1.0/1.0/0.18)을 권장합니다.",

        # Right Previews
        "preview_source": "03  원본 프리뷰 (Source Plate)",
        "preview_result": "04  결과 프리뷰 (Keyed Outputs)",
        "empty_preview": "영상을 선택하면 프레임을 표시합니다",
        "btn_brush_preview": "🖌️ 브러시 마스크 편집",
        "btn_brush_preview_tip": "현재 미리보기 중인 프레임을 브러시 마스크 에디터로 엽니다.",
        "frame_caption": "{name}  ·  {w} × {h}  ·  프레임 {frame}",

        # Bottom Bar
        "status_ready": "준비됨 · 모든 CorridorKey 2.0 기능이 활성화되었습니다",
        "btn_check": "환경 점검",
        "btn_download": "모델 다운로드",
        "btn_run": "🚀  키잉 처리 시작",
        "btn_stop": "중지",
        "btn_open_folder": "결과 폴더 열기",
        "status_processing": "처리 중 {current}/{total} · {name}",
        "status_stopping": "작업과 인코더를 중지하는 중…",
        "status_stopped": "중지됨 · 불완전한 결과 파일이 남을 수 있습니다",
        "status_done": "모든 작업 완료",
        "status_failed": "실패 (종료 코드 {code}) · 로그를 확인하세요",

        # Brush Editor Dialog
        "be_title": "브러시 마스크 편집기 — {clip} ({w}×{h})",
        "be_grp_tools": "01  그리기 도구",
        "be_btn_brush": "🖌️  전경 브러시 (White) [B]",
        "be_btn_eraser": "🧹  지우개 / 배경 (Black) [E]",
        "be_btn_rect_add": "🔲  영역 채우기 (전경 사각형)",
        "be_btn_rect_sub": "⬛  영역 지우기 (배경 사각형)",
        "be_grp_props": "02  브러시 파라미터",
        "be_lbl_size": "반경 크기:",
        "be_lbl_hardness": "가장자리 경도 (Hardness):",
        "be_lbl_opacity": "칠 불투명도 (Opacity):",
        "be_grp_edit": "03  마스크 조작 및 엣지 다듬기",
        "be_btn_dilate": "➕  팽창 (+3px)",
        "be_btn_dilate_tip": "마스크 영역을 바깥으로 넓힙니다",
        "be_btn_erode": "➖  수축 (-3px)",
        "be_btn_erode_tip": "마스크 영역을 안쪽으로 줄입니다",
        "be_btn_blur": "🌫️  페더 블러 (Smooth)",
        "be_btn_blur_tip": "마스크 경계를 부드럽게 가우시안 블러 처리합니다",
        "be_btn_invert": "🔄  반전 (Invert)",
        "be_btn_invert_tip": "전경과 배경을 뒤집습니다",
        "be_btn_clear": "🗑️  전체 지우기",
        "be_btn_fill": "⬜  전체 채우기",
        "be_btn_undo": "↩️  실행 취소 [Ctrl+Z]",
        "be_btn_redo": "↪️  다시 실행 [Ctrl+Y]",
        "be_grp_view": "04  화면 보기 모드",
        "be_view_overlay": "🔴  마스크 오버레이 (Overlay)",
        "be_view_matte": "⬛⬜  순수 마스크 (Matte B&W)",
        "be_view_cutout": "🏁  체커 컷아웃 (Cutout)",
        "be_view_rgb": "🖼️  원본 영상 (Source RGB)",
        "be_btn_fit": "화면 맞춤 [F]",
        "be_btn_100": "100% 원본",
        "be_lbl_stats": "마스크 면적: {pct:.1f}%  ·  해상도: {w} × {h}",
        "be_grp_action": "05  완료 및 내보내기",
        "be_btn_apply": "⭐  첫 프레임 힌트로 즉시 적용",
        "be_btn_apply_tip": "현재 마스크를 파일로 자동 저장하고 CorridorKey의 첫 프레임 마스크로 등록합니다.",
        "be_btn_export_mask": "💾  마스크 PNG 저장",
        "be_btn_export_cutout": "✂️  전경 RGBA 추출",
        "be_btn_import": "📂  기존 마스크 불러오기…",
        "be_hud": "배율: {zoom}%  ·  [F] 화면 맞춤  ·  더블클릭: 핏팅  ·  Space/우클릭: 이동",
        "be_no_frame": "표시할 프레임 이미지가 없습니다",
        "be_msg_no_mask": "마스크 데이터가 없습니다.",
        "be_msg_save_fail": "마스크 파일 저장 중 오류:\n{exc}",
        "be_dlg_save_mask": "마스크 파일 저장",
        "be_msg_save_done": "마스크가 저장되었습니다:\n{path}",
        "be_msg_save_err": "마스크 저장 오류:\n{exc}",
        "be_dlg_save_cutout": "전경 컷아웃(RGBA) 저장",
        "be_msg_cutout_done": "전경 컷아웃이 저장되었습니다:\n{path}",
        "be_msg_cutout_err": "전경 컷아웃 추출 오류:\n{exc}",
        "be_dlg_import_mask": "기존 마스크 파일 선택",
        "be_msg_import_fail": "마스크 파일을 읽을 수 없습니다:\n{exc}",
        "msg_error": "오류",
        "msg_save_complete": "저장 완료",
        "msg_export_complete": "추출 완료",
        "msg_load_fail": "불러오기 실패",
        "preview_unavailable": "미리보기 불가 — 결과 폴더에서 확인하세요",

        # Tool Rail Tips
        "rail_media_tip": "미디어 보관함 (클립 및 테이크)",
        "rail_layers_tip": "매트 및 레이어 인스펙터",
        "rail_wipe_tip": "와이프 및 비교 도구",
        "rail_history_tip": "대기열 및 렌더링 히스토리",
        "rail_color_tip": "디스필 및 컬러 튜닝",
        "rail_models_tip": "AI 모델 및 가중치 관리",
        "rail_export_tip": "배송 및 최종 내보내기",

        # About & License Dialog
        "about_dialog_title": "CorridorKey 2.0 · 정보 및 라이선스 (About & License)",
        "about_tab_summary": "📋 정보 및 권리 요약",
        "about_tab_license": "📜 라이선스 전문 (LICENSE)",
        "about_tab_third": "🧩 서드파티 고지 (Third-Party)",
        "about_btn_close": "확인 및 닫기",

        # Dialogs & Messages
        "msg_warn_title": "안내",
        "msg_no_clip_for_brush": "마스크를 그릴 영상이나 이미지 시퀀스를 먼저 추가해 주세요.",
        "msg_error_input_required": "처리할 영상 또는 시퀀스를 추가하세요.",
        "msg_error_hint_single": "힌트를 사용할 때는 입력을 1개만 지정하거나 각 항목별로 순차 처리해야 합니다.",
        "msg_error_output_required": "저장 위치를 선택하세요.",
        "msg_config_check": "설정 확인",
        "msg_running_title": "작업 진행 중",
        "msg_running_text": "먼저 중지 버튼을 누르고 프로세스가 종료된 후 창을 닫아 주세요.",
        "dlg_select_videos": "영상 선택",
        "dlg_select_folder": "이미지 시퀀스 폴더 선택",
        "dlg_select_hint": "마스크 힌트 파일 선택",
        "dlg_select_out_dir": "저장 폴더 선택",
        "dlg_select_file": "파일 선택",
        "log_hint_companion_first": "✨ 동반 첫 프레임 힌트 자동 감지: {name}",
        "log_hint_companion_video": "✨ 동반 마스크 영상 힌트 자동 감지: {name}",
        "log_brush_applied": "🖌️ 브러시 마스크 적용 완료: {path}",
        "log_job_start": "\n▶ 작업 시작 [{name}]\n입력: {src}\n출력: {dst}",
        "log_kill_failed": "작업 트리 종료 실패. 다시 중지할 수 있습니다.",
        "status_checking_env": "환경 점검 중…",
        "status_downloading_weights": "모델 다운로드 중 · 약 5GB, 최초 1회 필요",
        "status_check_passed": "환경 점검 통과",
        "status_download_done": "모델 다운로드 완료",
        "status_mkdir_failed": "저장 폴더 생성 실패: {err}",
        "status_proc_start_failed": "프로세스 시작 실패: {err}",
        "status_rgvi_running": "RGVI (AAAI 2025) AI 엔진으로 배경 클린 플레이트 복원 중…",
        "status_rgvi_done": "RGVI 클린 플레이트 생성 완료",
        "log_rgvi_start": "\n▶ [RGVI] 비디오 객체 제거 및 배경 인페인팅 시작...\n영상: {src}\n마스크: {mask}\n출력: {dst}",
        "log_rgvi_done": "✨ [RGVI] 클린 플레이트 생성 완료: {path}",

        # Model Manager
        "btn_models": "📦  AI 모델 매니저",
        "btn_models_tip": "AI 모델 가중치 설치 상태 확인 및 다운로드",
        "model_mgr_title": "AI 모델 및 가중치 관리자",
        "model_mgr_desc": "설치된 모델 가중치 상태를 확인하고, 키잉 필수 모델 및 선택 기능 모델을 다운로드합니다.",
        "model_mgr_path_lbl": "모델 저장 위치:",
        "model_mgr_btn_open_folder": "📂 모델 폴더 열기",
        "model_mgr_req_header": "필수 코어 모델 (키잉용)",
        "model_mgr_opt_header": "선택 기능 모델 (클린 플레이트)",
        "model_mgr_btn_dl_required": "⚡ 필수 모델 일괄 다운로드 (~4.8 GB)",
        "model_mgr_btn_dl_rgvi": "✨ 클린 플레이트 모델 다운로드 (~47 MB)",
        "model_mgr_btn_refresh": "🔄 새로고침",
        "model_mgr_btn_close": "닫기",
        "model_mgr_btn_cancel": "다운로드 취소",
        "model_mgr_installed": "설치 완료",
        "model_mgr_missing": "미설치",
        "model_mgr_downloading": "다운로드 중...",
        "model_mgr_btn_download": "다운로드",
        "model_mgr_req_badge": "필수",
        "model_mgr_opt_badge": "선택",
        "prompt_missing_req_title": "필수 AI 모델 미설치 알림",
        "prompt_missing_req_msg": "키잉 작업에 필요한 AI 모델 가중치가 설치되지 않았습니다:\n\n{models}\n\n지금 AI 모델 매니저를 열어 다운로드하시겠습니까?",
        "prompt_rgvi_needed_title": "클린 플레이트 모델 다운로드 알림",
        "prompt_rgvi_needed_msg": "객체 제거 및 배경 복원(클린 플레이트)을 실행하려면 RGVI 모델(약 47 MB)이 필요합니다.\n\n지금 다운로드하시겠습니까?",
        "status_model_downloading": "AI 모델 가중치 다운로드 중: {model}...",
        "status_model_download_done": "AI 모델 가중치 준비 완료.",
    }
}


def load_preference() -> str:
    """Load language preference from config file; defaults to English."""
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            lang = data.get("language", DEFAULT_LANG)
            if lang in TRANSLATIONS:
                return lang
        except Exception:
            pass
    return DEFAULT_LANG


def save_preference(lang: str):
    """Save language preference to config file."""
    try:
        data = {}
        if CONFIG_PATH.is_file():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["language"] = lang
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def get_language() -> str:
    global _current_lang
    return _current_lang


def set_language(lang: str):
    global _current_lang
    if lang in TRANSLATIONS and lang != _current_lang:
        _current_lang = lang
        save_preference(lang)
        for listener in _listeners:
            try:
                listener(lang)
            except Exception:
                pass


def add_language_listener(fn: Callable[[str], None]):
    if fn not in _listeners:
        _listeners.append(fn)


def tr(key: str, **kwargs) -> str:
    """Translate key to current language with format kwargs fallback."""
    table = TRANSLATIONS.get(_current_lang, TRANSLATIONS[DEFAULT_LANG])
    template = table.get(key) or TRANSLATIONS[DEFAULT_LANG].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template


# Initialize with saved preference or default to English
_current_lang = load_preference()
