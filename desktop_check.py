"""Read-only diagnostics for the desktop application."""
import os
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
from pathlib import Path
import shutil
import sys

def main():
    import torch
    import cv2
    from corridorkey.runtime import RuntimePaths
    from corridorkey.video_io import find_ffmpeg
    print('Python:', sys.version)
    print('PyTorch:', torch.__version__, 'CUDA:', torch.version.cuda)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU를 사용할 수 없습니다.')
    print('GPU:', torch.cuda.get_device_name(0))
    free, total = torch.cuda.mem_get_info()
    print(f'VRAM: {free / 2**30:.1f} GiB free / {total / 2**30:.1f} GiB total')
    ffmpeg = shutil.which('ffmpeg') or find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError('FFmpeg가 PATH 또는 bin/ 폴더에 없습니다.')
    print('FFmpeg:', ffmpeg)
    RuntimePaths.from_package(Path(__file__).resolve().parent).validate()
    print('환경 및 모델 경로 확인 완료.')

if __name__ == '__main__':
    main()
