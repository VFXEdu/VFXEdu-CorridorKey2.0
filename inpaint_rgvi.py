"""RGVI (AAAI 2025) Video Object Removal & Inpainting Pipeline.

Official Architecture: "Elevating Flow-Guided Video Inpainting with Reference Generation"
Authors: Suhwan Cho, Seoung Wug Oh, Sangyoun Lee, Joon-Young Lee (AAAI 2025, Adobe Research & Yonsei Univ)

Features:
- Native PyTorch & torchvision DCNv2 execution on CUDA (RTX 4090 optimized)
- Bidirectional RAFT optical flow + Flow Completion (FCNet)
- Sub-pixel accurate One-Shot Pixel Pulling from visible frames
- Edge & context completion via Pixel Flow Completion Network (PFCNet)
- Temporal sliding window for arbitrary-length video clips
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from PIL import Image
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision as tv

ROOT = Path(__file__).resolve().parent
RGVI_ROOT = ROOT / "third_party" / "RGVI"
if str(RGVI_ROOT) not in sys.path:
    sys.path.insert(0, str(RGVI_ROOT))

from fcnet import FCNet
from pfcnet import PFCNet


def backward_warp(x: torch.Tensor, flow: torch.Tensor) -> torch.Tensor:
    """Warp tensor x with optical flow field using bicubic sampling on GPU."""
    B, _, H, W = x.size()
    orig_device = x.device
    x = x.cuda()
    flow = flow.cuda()
    grid_h = torch.arange(0, H, device="cuda").view(1, H, 1).repeat(B, 1, W)
    grid_w = torch.arange(0, W, device="cuda").view(1, 1, W).repeat(B, H, 1)
    grid = torch.stack([grid_w, grid_h], 3).type_as(x)
    grid_flow = grid + flow.permute(0, 2, 3, 1)
    grid_flow_w = 2 * grid_flow[:, :, :, 0] / max(1, W - 1) - 1
    grid_flow_h = 2 * grid_flow[:, :, :, 1] / max(1, H - 1) - 1
    norm_grid_flow = torch.stack([grid_flow_w, grid_flow_h], dim=3)
    out = F.grid_sample(x, norm_grid_flow, mode="bicubic", padding_mode="border", align_corners=True)
    return out.to(orig_device)


class RGVIRemover:
    """RGVI (AAAI 2025) Video Inpainting & Clean-Plate Generator."""

    def __init__(
        self,
        fcnet_weights: Path | str = None,
        pfcnet_weights: Path | str = None,
        device: str = "cuda",
        use_sd: bool = True,
    ):
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        weights_dir = RGVI_ROOT / "weights"

        fcnet_p = Path(fcnet_weights) if fcnet_weights else (weights_dir / "FCNet.pth")
        pfcnet_p = Path(pfcnet_weights) if pfcnet_weights else (weights_dir / "PFCNet.pth")

        if not fcnet_p.is_file() or not pfcnet_p.is_file():
            # Trigger automatic weight download
            import subprocess
            downloader = ROOT / "scripts" / "download_rgvi_weights.py"
            if downloader.is_file():
                print("[RGVI] Downloading required FCNet & PFCNet weights...")
                subprocess.run([sys.executable, str(downloader)], check=True)

        print("[RGVI] Loading RAFT Optical Flow model...")
        of = tv.models.optical_flow
        self.raft = of.raft_large(weights=of.Raft_Large_Weights.DEFAULT).to(self.device).eval()

        print(f"[RGVI] Loading FCNet from {fcnet_p.name}...")
        self.fcnet = FCNet(str(fcnet_p)).to(self.device).eval()

        print(f"[RGVI] Loading PFCNet from {pfcnet_p.name}...")
        self.pfcnet = PFCNet(str(pfcnet_p)).to(self.device).eval()

        self.sdi = None
        if use_sd:
            try:
                print("[RGVI] Initializing Stable Diffusion Inpainting pipeline (RGVI Official AI Generator)...")
                from diffusers import StableDiffusionInpaintPipeline, DPMSolverMultistepScheduler
                self.sdi = StableDiffusionInpaintPipeline.from_pretrained(
                    "runwayml/stable-diffusion-inpainting",
                    torch_dtype=torch.float16,
                    safety_checker=None,
                )
                self.sdi.scheduler = DPMSolverMultistepScheduler.from_config(self.sdi.scheduler.config)
                self.sdi.to(self.device)
                print("[RGVI] Stable Diffusion Inpainting pipeline loaded successfully onto GPU.")
            except Exception as e:
                print(f"[RGVI Warning] Stable Diffusion inpainting unavailable ({e}). Using lightweight texture fallback.")
                self.sdi = None

        print("[RGVI] All models loaded successfully onto GPU.")

    @torch.inference_mode()
    def inpaint_chunk(self, imgs: torch.Tensor, masks: torch.Tensor, prompt: str | None = None) -> torch.Tensor:
        """Process a temporal chunk of video frames and masks.
        
        Args:
            imgs: (L, 3, H, W) normalized to [0, 1]
            masks: (L, 1, H, W) binary (1 = area to inpaint/remove, 0 = keep background)
        Returns:
            inpainted_imgs: (L, 3, H, W)
        """
        L, C, H, W = imgs.size()
        if L < 2:
            return imgs

        # Ensure dimensions are divisible by 16 for FCNet and PFCNet (4 downsamplings = 2^4 = 16)
        orig_in_h, orig_in_w = H, W
        pad_h = (16 - H % 16) % 16
        pad_w = (16 - W % 16) % 16
        if pad_h > 0 or pad_w > 0:
            imgs = F.pad(imgs, (0, pad_w, 0, pad_h), mode="replicate")
            masks = F.pad(masks, (0, pad_w, 0, pad_h), mode="replicate")
            _, _, H, W = imgs.size()

        masks = (masks > 0.5).float()
        cnts = 1.0 - masks
        org_imgs = imgs.clone()

        # Step 1: Forward & Backward Optical Flow via RAFT
        flow_h = min(480, (H // 8) * 8)
        flow_w = min(864, (W // 8) * 8)
        flow_scale_y = flow_h / H
        flow_scale_x = flow_w / W

        fw_flows = {}
        bw_flows = {}
        for i in range(1, L):
            prev_img = F.interpolate(imgs[i - 1:i], size=(flow_h, flow_w), mode="bicubic", antialias=True).to(self.device)
            curr_img = F.interpolate(imgs[i:i + 1], size=(flow_h, flow_w), mode="bicubic", antialias=True).to(self.device)
            fw_flow = self.raft(2.0 * prev_img - 1.0, 2.0 * curr_img - 1.0)[-1].cpu()
            bw_flow = self.raft(2.0 * curr_img - 1.0, 2.0 * prev_img - 1.0)[-1].cpu()
            fw_flows[i - 1] = fw_flow
            bw_flows[i] = bw_flow

        # Mask inputs
        imgs = imgs * cnts

        # Step 2: Flow Completion via FCNet
        fc_h = max(32, (flow_h // 2 // 8) * 8)
        fc_w = max(32, (flow_w // 2 // 8) * 8)

        fcnet_masks = F.interpolate(masks, size=(fc_h, fc_w), mode="bicubic", antialias=True)
        fcnet_masks = F.avg_pool2d(fcnet_masks, 9, 1, 4)
        fcnet_masks = (fcnet_masks != 0).float().unsqueeze(0)

        fcnet_fw_flows = torch.zeros(1, L - 1, 2, fc_h, fc_w)
        fcnet_bw_flows = torch.zeros(1, L - 1, 2, fc_h, fc_w)
        for i in range(L - 1):
            fcnet_fw_flows[:, i] = F.interpolate(fw_flows[i], size=(fc_h, fc_w), mode="bicubic", antialias=True) * (fc_h / flow_h)
            fcnet_bw_flows[:, i] = F.interpolate(bw_flows[i + 1], size=(fc_h, fc_w), mode="bicubic", antialias=True) * (fc_h / flow_h)

        fcnet_fw_flows = (1.0 - fcnet_masks[:, :-1]) * fcnet_fw_flows
        fcnet_bw_flows = (1.0 - fcnet_masks[:, 1:]) * fcnet_bw_flows
        fcnet_flows = [fcnet_fw_flows.to(self.device), fcnet_bw_flows.to(self.device)]

        fcnet_inp_flows = self.fcnet.forward_bidirect_flow(fcnet_flows, fcnet_masks.to(self.device))
        fcnet_inp_flows = self.fcnet.combine_flow(fcnet_flows, fcnet_inp_flows, fcnet_masks.to(self.device))

        inp_fw_flows = {}
        inp_bw_flows = {}
        for i in range(L - 1):
            inp_fw_flows[i] = fcnet_inp_flows[0][:, i].cpu()
            inp_bw_flows[i + 1] = fcnet_inp_flows[1][:, i].cpu()

        # Step 3: One-Shot Pixel Pulling across Frames
        scale_flow_y = H / fc_h
        scale_flow_x = W / fc_w

        fw_imgs = imgs.clone()
        bw_imgs = imgs.clone()
        fw_cnts = cnts.clone()
        bw_cnts = cnts.clone()
        warp_masks = torch.zeros(L, 1, H, W)

        for i in range(L):
            # Pulling from forward direction
            for j in range(i + 1, L):
                if j == i + 1:
                    acc_flow = inp_fw_flows[i]
                else:
                    acc_flow = backward_warp(inp_fw_flows[j - 1], acc_flow) + acc_flow
                acc_flow_s = F.interpolate(acc_flow, size=(H, W), mode="bicubic", antialias=True)
                acc_flow_s[:, 0] *= scale_flow_x
                acc_flow_s[:, 1] *= scale_flow_y

                warp_img = backward_warp(imgs[j:j + 1], acc_flow_s)[0]
                warp_cnt = backward_warp(cnts[j:j + 1], acc_flow_s)[0]
                fw_imgs[i] = fw_imgs[i] + (1.0 - fw_cnts[i]) * warp_img
                fw_cnts[i] = fw_cnts[i] + (1.0 - fw_cnts[i]) * warp_cnt
                warp_masks[i] = warp_masks[i] + (1.0 - warp_cnt)

            # Pulling from backward direction
            for j in range(i - 1, -1, -1):
                if j == i - 1:
                    acc_flow = inp_bw_flows[i]
                else:
                    acc_flow = backward_warp(inp_bw_flows[j + 1], acc_flow) + acc_flow
                acc_flow_s = F.interpolate(acc_flow, size=(H, W), mode="bicubic", antialias=True)
                acc_flow_s[:, 0] *= scale_flow_x
                acc_flow_s[:, 1] *= scale_flow_y

                warp_img = backward_warp(imgs[j:j + 1], acc_flow_s)[0]
                warp_cnt = backward_warp(cnts[j:j + 1], acc_flow_s)[0]
                bw_imgs[i] = bw_imgs[i] + (1.0 - bw_cnts[i]) * warp_img
                bw_cnts[i] = bw_cnts[i] + (1.0 - bw_cnts[i]) * warp_cnt
                warp_masks[i] = warp_masks[i] + (1.0 - warp_cnt)

        # Invalidate incomplete pixels
        fw_imgs[fw_cnts.repeat(1, 3, 1, 1) != 1.0] = 0.0
        fw_cnts[fw_cnts != 1.0] = 0.0
        bw_imgs[bw_cnts.repeat(1, 3, 1, 1) != 1.0] = 0.0
        bw_cnts[bw_cnts != 1.0] = 0.0

        # Fuse bidirectional pulling
        imgs = (fw_imgs + bw_imgs) / (fw_cnts + bw_cnts).clamp(min=1e-7)
        masks = 1.0 - (fw_cnts + bw_cnts).clamp(0.0, 1.0)
        cnts = 1.0 - masks

        # Verification of conflicting edges
        diff = torch.sum(torch.abs(fw_imgs - bw_imgs), dim=1, keepdim=True)
        unsure = (diff > 1.0).float() * (fw_cnts + bw_cnts - 1.0).clamp(min=0.0, max=1.0)
        imgs = imgs * (1.0 - unsure)
        masks = 1.0 - cnts * (1.0 - unsure)

        # Step 4: Missing Area Check & Texture Filling
        # If any unseen holes remain (never visible in any frame), inpaint reference and pull
        con_num = torch.zeros(L)
        for i in range(L):
            con_num[i] = torch.sum(masks[i]) + torch.sum(masks[i] * warp_masks[i])

        k = int(torch.argmax(con_num, dim=0))
        if 1.0 in masks[k]:
            if self.sdi is not None:
                print(f"    [RGVI AI] Synthesizing photorealistic reference on keyframe {k} via Stable Diffusion...")
                y_idx, x_idx = torch.where(masks[k, 0] > 0.5)
                if len(y_idx) > 0:
                    pad_box = 64
                    y0 = max(0, int(y_idx.min()) - pad_box)
                    y1 = min(H, int(y_idx.max()) + pad_box)
                    x0 = max(0, int(x_idx.min()) - pad_box)
                    x1 = min(W, int(x_idx.max()) + pad_box)

                    crop_img_t = imgs[k, :, y0:y1, x0:x1].cpu()
                    crop_mask_t = masks[k, :, y0:y1, x0:x1].cpu()

                    pil_img = tv.transforms.ToPILImage()(crop_img_t)
                    pil_mask = tv.transforms.ToPILImage()(crop_mask_t)

                    pil_img_sd = pil_img.resize((512, 512), Image.Resampling.BICUBIC)
                    pil_mask_sd = pil_mask.resize((512, 512), Image.Resampling.NEAREST)

                    sd_prompt = prompt or "empty clean background, seamless, ultra-high resolution, photorealistic texture"
                    sd_neg = "person, people, human, face, body, limbs, clothes, shoes, ghost, blur, watermark"

                    generator = torch.Generator("cuda").manual_seed(42 + k)
                    sd_out = self.sdi(
                        prompt=sd_prompt,
                        negative_prompt=sd_neg,
                        image=pil_img_sd,
                        mask_image=pil_mask_sd,
                        num_inference_steps=22,
                        guidance_scale=7.5,
                        generator=generator,
                    ).images[0]

                    sd_out_res = sd_out.resize(pil_img.size, Image.Resampling.BICUBIC)
                    out_tensor = tv.transforms.ToTensor()(sd_out_res)

                    # Blend back into keyframe k
                    imgs[k, :, y0:y1, x0:x1] = imgs[k, :, y0:y1, x0:x1] + crop_mask_t * out_tensor
                    cnts[k] = 1.0
            else:
                # Fast fallback when SD model is not installed
                k_img_np = (imgs[k].permute(1, 2, 0).cpu().numpy() * 255.0).astype(np.uint8)
                k_mask_np = (masks[k, 0].cpu().numpy() * 255.0).astype(np.uint8)
                inp_k = cv2.inpaint(k_img_np, k_mask_np, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
                k_tensor = torch.from_numpy(inp_k.astype(np.float32) / 255.0).permute(2, 0, 1)
                imgs[k] = imgs[k] + masks[k] * k_tensor
                cnts[k] = 1.0

            # Pull reference to other frames
            for i in range(k - 1, -1, -1):
                acc_flow = inp_fw_flows[i] if i == k - 1 else backward_warp(acc_flow, inp_fw_flows[i]) + inp_fw_flows[i]
                acc_flow_s = F.interpolate(acc_flow, size=(H, W), mode="bicubic", antialias=True)
                acc_flow_s[:, 0] *= scale_flow_x
                acc_flow_s[:, 1] *= scale_flow_y
                warp_img = backward_warp(imgs[k:k + 1], acc_flow_s)[0]
                warp_cnt = backward_warp(cnts[k:k + 1], acc_flow_s)[0]
                imgs[i] = imgs[i] + (1.0 - cnts[i]) * warp_img
                cnts[i] = cnts[i] + (1.0 - cnts[i]) * warp_cnt

            for i in range(k + 1, L):
                acc_flow = inp_bw_flows[i] if i == k + 1 else backward_warp(acc_flow, inp_bw_flows[i]) + inp_bw_flows[i]
                acc_flow_s = F.interpolate(acc_flow, size=(H, W), mode="bicubic", antialias=True)
                acc_flow_s[:, 0] *= scale_flow_x
                acc_flow_s[:, 1] *= scale_flow_y
                warp_img = backward_warp(imgs[k:k + 1], acc_flow_s)[0]
                warp_cnt = backward_warp(cnts[k:k + 1], acc_flow_s)[0]
                imgs[i] = imgs[i] + (1.0 - cnts[i]) * warp_img
                cnts[i] = cnts[i] + (1.0 - cnts[i]) * warp_cnt

            imgs[cnts.repeat(1, 3, 1, 1) != 1.0] = 0.0
            cnts[cnts != 1.0] = 0.0
            masks = 1.0 - cnts

        # Step 5: Final PFCNet Edge & Missing Completion
        for i in range(L):
            if 1.0 in masks[i]:
                # Downsample/upsample through PFCNet
                pfc_in = imgs[i:i + 1].to(self.device)
                pfc_mask = masks[i:i + 1].to(self.device)
                pfc_out = self.pfcnet(pfc_in, pfc_mask).cpu()
                imgs[i:i + 1] = imgs[i:i + 1] + masks[i:i + 1] * pfc_out

        # Restore original cropped size if padded
        if pad_h > 0 or pad_w > 0:
            imgs = imgs[:, :, :orig_in_h, :orig_in_w]

        return torch.clamp(imgs, 0.0, 1.0)


def load_video_frames(video_path: Path, max_frames: int = -1) -> tuple[list[np.ndarray], float]:
    """Read video frames into a list of RGB numpy uint8 arrays."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(rgb)
        if 0 < max_frames <= len(frames):
            break
    cap.release()
    return frames, fps


def load_mask_frames(mask_path: Path, count: int, target_size: tuple[int, int]) -> list[np.ndarray]:
    """Read binary mask frames (matching video length)."""
    target_w, target_h = target_size
    masks = []

    if mask_path.is_file() and mask_path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.exr'}:
        # Single image mask: repeat for all frames
        img = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Cannot read mask image: {mask_path}")
        if img.shape[1] != target_w or img.shape[0] != target_h:
            img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
        bin_mask = (img > 127).astype(np.uint8) * 255
        return [bin_mask] * count

    # Video mask
    cap = cv2.VideoCapture(str(mask_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open mask video: {mask_path}")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if gray.shape[1] != target_w or gray.shape[0] != target_h:
            gray = cv2.resize(gray, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
        bin_mask = (gray > 127).astype(np.uint8) * 255
        masks.append(bin_mask)
        if len(masks) >= count:
            break
    cap.release()

    # If mask video is shorter than frames, pad with last mask
    while len(masks) < count:
        masks.append(masks[-1] if masks else np.zeros((target_h, target_w), dtype=np.uint8))

    return masks


def remove_object_rgvi(
    video_path: Path | str,
    mask_path: Path | str,
    output_path: Path | str,
    chunk_size: int = 40,
    stride: int = 20,
    scale: float = 1.0,
    prompt: str | None = None,
    use_sd: bool = True,
    max_frames: int = -1,
    callback=None,
) -> Path:
    """Run RGVI (AAAI 2025) Video Object Removal on video + mask."""
    video_path = Path(video_path).resolve()
    mask_path = Path(mask_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[RGVI Remover] Loading video: {video_path}")
    raw_frames, fps = load_video_frames(video_path, max_frames=max_frames)
    total_frames = len(raw_frames)
    if total_frames == 0:
        raise ValueError(f"No frames found in video: {video_path}")

    orig_h, orig_w, _ = raw_frames[0].shape
    if scale != 1.0:
        target_w = int(round(orig_w * scale / 16) * 16)
        target_h = int(round(orig_h * scale / 16) * 16)
        raw_frames = [cv2.resize(f, (target_w, target_h), interpolation=cv2.INTER_AREA) for f in raw_frames]
    else:
        target_w = orig_w
        target_h = orig_h

    print(f"[RGVI Remover] Total Frames: {total_frames}, Resolution: {target_w}x{target_h}, FPS: {fps:.2f}")
    mask_frames = load_mask_frames(mask_path, count=total_frames, target_size=(target_w, target_h))

    # Convert to PyTorch tensors (T, C, H, W) in [0, 1]
    t_imgs = torch.from_numpy(np.stack(raw_frames).transpose(0, 3, 1, 2)).float() / 255.0
    t_masks = torch.from_numpy(np.stack(mask_frames)[:, None, :, :]).float() / 255.0

    remover = RGVIRemover(use_sd=use_sd)

    # Process in temporal sliding windows with Hann/linear blending
    output_frames = torch.zeros_like(t_imgs)
    weight_accum = torch.zeros(total_frames, 1, 1, 1)

    starts = list(range(0, total_frames, stride))
    t0 = time.time()

    for idx, start_f in enumerate(starts):
        end_f = min(start_f + chunk_size, total_frames)
        cur_len = end_f - start_f
        if cur_len <= 0:
            continue

        chunk_imgs = t_imgs[start_f:end_f]
        chunk_masks = t_masks[start_f:end_f]

        print(f"[RGVI Window {idx+1}/{len(starts)}] Processing frames {start_f}..{end_f-1} ({cur_len} frames)...")
        if callback:
            callback(idx + 1, len(starts), f"RGVI Inpainting Window {idx+1}/{len(starts)}")

        inpainted_chunk = remover.inpaint_chunk(chunk_imgs, chunk_masks, prompt=prompt)

        # Triangular / Hann window blending weight
        if cur_len > 1:
            w = torch.hann_window(cur_len).view(cur_len, 1, 1, 1) + 0.1
        else:
            w = torch.ones(cur_len, 1, 1, 1)

        output_frames[start_f:end_f] += inpainted_chunk * w
        weight_accum[start_f:end_f] += w

        if end_f >= total_frames:
            break

    # Normalize blended frames
    output_frames = output_frames / weight_accum.clamp(min=1e-7)
    output_frames = torch.clamp(output_frames, 0.0, 1.0)

    # Convert back to uint8 numpy
    out_np = (output_frames.permute(0, 2, 3, 1).cpu().numpy() * 255.0).astype(np.uint8)

    # If original size differed, resize back to exact original resolution
    if (target_w, target_h) != (orig_w, orig_h):
        final_frames = [cv2.resize(f, (orig_w, orig_h), interpolation=cv2.INTER_LANCZOS4) for f in out_np]
    else:
        final_frames = list(out_np)

    # Write video
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (orig_w, orig_h))
    for f in final_frames:
        bgr = cv2.cvtColor(f, cv2.COLOR_RGB2BGR)
        writer.write(bgr)
    writer.release()

    elapsed = time.time() - t0
    print(f"[RGVI Remover] Done! Clean plate saved to: {output_path} ({elapsed:.1f}s, {total_frames / elapsed:.1f} fps)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="RGVI (AAAI 2025) Video Object Removal & Inpainting")
    parser.add_argument("--video", "-v", required=True, help="Input video file or frame directory")
    parser.add_argument("--mask", "-m", required=True, help="Input mask video or image file")
    parser.add_argument("--output", "-o", required=True, help="Output clean plate video path")
    parser.add_argument("--chunk_size", type=int, default=40, help="Sliding temporal window size (default: 40)")
    parser.add_argument("--stride", type=int, default=20, help="Window stride (default: 20)")
    parser.add_argument("--scale", type=float, default=1.0, help="Downsampling scale factor (default: 1.0)")
    parser.add_argument("--prompt", type=str, default=None, help="Background texture prompt for Stable Diffusion")
    parser.add_argument("--no_sd", action="store_true", help="Disable Stable Diffusion reference generation")
    parser.add_argument("--max_frames", type=int, default=-1, help="Max frames to process (-1 for all)")
    args = parser.parse_args()

    remove_object_rgvi(
        video_path=args.video,
        mask_path=args.mask,
        output_path=args.output,
        chunk_size=args.chunk_size,
        stride=args.stride,
        scale=args.scale,
        prompt=args.prompt,
        use_sd=not args.no_sd,
        max_frames=args.max_frames,
    )


if __name__ == "__main__":
    main()
