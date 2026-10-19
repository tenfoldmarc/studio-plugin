#!/usr/bin/env python3
"""Check the slot render (run from the slot folder, after hf render). Plain python, ffmpeg only.

  python check.py      reads renders/<slot folder>.webm (an overlay effect) or .mp4 and prints / writes:
    - size and frame count against clip.json (must be 1080x1920 and exactly the slot's frames)
    - whether the red safe-zone guide was left in index.html
    - work/check/sheet.jpg: 8 frames spread over the slot, to LOOK at (words readable, nothing on the face,
      nothing in the red area of a SAFE=1 snapshot)
    - renders/<slot folder>-phone.mp4 (720 x 1280 preview)
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'


def main():
    name = os.path.basename(HERE)
    try:
        overlay = json.load(open('slot.json', encoding='utf-8')).get('layer') == 'overlay'
    except (OSError, ValueError):
        overlay = False
    out = f'renders/{name}.webm' if overlay else f'renders/{name}.mp4'
    if not os.path.exists(out):
        sys.exit(f'{out} is missing: render first')
    if 'rgba(255,0,0,.28)' in open('index.html', encoding='utf-8').read():
        print('!! index.html still has the red safe-zone guide: run build.py without SAFE=1 and render again')
    nfr = int(json.load(open('clip.json', encoding='utf-8'))['frames'])
    info = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                           'stream=width,height,nb_read_frames', '-of', 'csv=p=0', out], capture_output=True, text=True).stdout.strip()
    ok = info == f'1080,1920,{nfr}'
    print(f'render: {info}  (want 1080,1920,{nfr})  {"OK" if ok else "!! WRONG"}')
    os.makedirs('work/check', exist_ok=True)
    picks = sorted({min(nfr - 1, round(k * (nfr - 1) / 7)) for k in range(8)})
    sel = '+'.join(f'eq(n\\,{f})' for f in picks)
    # an overlay render is transparent: look at it laid over the slot's own footage, as the reel will show it
    src = ['-i', 'assets/aroll.mp4', '-c:v', 'libvpx-vp9', '-i', out] if overlay else ['-i', out]
    pre = '[0:v][1:v]overlay=format=auto,' if overlay else ''
    subprocess.run([FF, '-v', 'error', '-y'] + src + ['-filter_complex', f"{pre}select='{sel}',scale=270:480,tile={len(picks)}x1",
                    '-frames:v', '1', 'work/check/sheet.jpg'], check=False)
    print('sheet: work/check/sheet.jpg  frames ' + ', '.join(str(f) for f in picks) + '  LOOK at it')
    pre = '[0:v][1:v]overlay=format=auto,' if overlay else '[0:v]'
    subprocess.run([FF, '-v', 'error', '-y'] + src + ['-filter_complex', pre + 'scale=720:1280[v]', '-map', '[v]', '-map', '0:a?',
                    '-c:v', 'libx264', '-crf', '27', '-preset', 'veryfast', '-c:a', 'aac', '-b:a', '96k',
                    f'renders/{name}-phone.mp4'], check=False)
    print(f'phone copy: renders/{name}-phone.mp4')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
