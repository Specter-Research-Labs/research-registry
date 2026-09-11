"""Package native Lenia CLI body renders for the morphospace report.

First render a collection containing the two selected replay campaigns:
  LeniaCLI publish media --input REPLAY_COLLECTION --output MEDIA_ROOT \
    --steps 3600 --frame-budget 300 --fps 30 --render-mode body
Then run this script with --media-root MEDIA_ROOT. The CLI uses the original
256-square simulation, a fixed crop across the recording, and a shared density
scale within each recording. Its presentation frames are 512-square.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--media-root', type=Path, required=True)
args = parser.parse_args()
out = ROOT / 'site/assets/blog/lenia-morphospace-report/motion'
out.mkdir(exist_ok=True)
records = json.loads((args.media_root / 'index.json').read_text())
ids = {'library-0-flow-map-elite-12': '870da94a', 'library-0-flow-map-elite-11': '781d0200'}
receipt = {'source': 'Lenia CLI publish media', 'simulation_steps': 3600,
           'frame_budget': 300, 'fps': 30, 'render_mode': 'body', 'transparent_format': 'lossless animated WebP',
           'simulation_grid': [256, 256], 'presentation_frame': [512, 512],
           'purpose': 'Unperturbed replay of two coherent movers used in the obstacle assay; not the fish-near selection.',
           'specimens': []}
for record in records:
    if record['label'] not in ids:
        continue
    label = ids[record['label']]
    frames = Path(record['framesColorPath'])
    files = sorted(frames.glob('frame_*.png'))
    assert len(files) == 300
    video = out / f'{label}.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30',
                    '-i', str(frames / 'frame_%06d.png'), '-c:v', 'libx264',
                    '-crf', '14', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)], check=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(files[150]),
                    '-frames:v', '1', str(out / f'{label}.png')], check=True)
    animation = out / f'{label}-transparent.webp'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30',
                    '-i', str(frames / 'frame_%06d.png'), '-c:v', 'libwebp_anim',
                    '-lossless', '1', '-compression_level', '6', '-loop', '0',
                    '-pix_fmt', 'bgra', str(animation)], check=True)
    receipt['specimens'].append({'id': label, 'source_label': record['label'],
        'presentation_frames_sha256': hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in files)).hexdigest(),
        'video_sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
        'transparent_sha256': hashlib.sha256(animation.read_bytes()).hexdigest()})
assert len(receipt['specimens']) == 2
(out / 'provenance.json').write_text(json.dumps(receipt, indent=2)+'\n')
