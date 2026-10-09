#!/usr/bin/env python3
"""Frame-exact QA of a render: the last frame before and first frame after every cut, in one strip, plus a phone copy.

Usage:  PY check_cuts.py <project_dir> <render.mp4> [--phone]
Writes work/cut_check.jpg (pairs left->right: before|after for each cut). LOOK at it: every 'after' frame must show the
new shot with that section's look and no leftovers (room plates, cutout of the previous shot, stale captions).
Snapshots from `hyperframes snapshot` seek approximately at cuts; only frames pulled from the final render are proof.
--phone also writes <render>-phone.mp4 (720p, crf 26; SendUserFile uploads over ~5MB often fail, drop to crf 28).
<render.mp4> may be written the short way, "renders/<file>.mp4": it is looked up inside the project folder.
The last line is the audio level of the render (peak and average).
"""
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True   # no __pycache__ next to the scripts (a plugin's folder is not ours to write in)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

skillenv.utf8_stdio()
FF = skillenv.tool('ffmpeg')
if len(sys.argv) < 3:
    sys.exit(__doc__)
proj = skillenv.path_arg(sys.argv[1])
render = skillenv.project_file(proj, sys.argv[2])            # "renders/x.mp4" is read inside the project
if not os.path.isfile(render):
    sys.exit(f'render not found: {render}')
with open(os.path.join(proj, 'segments.json'), encoding='utf-8') as fh:
    segs = json.load(fh)
cf = os.path.join(proj, 'work', 'cf')
sheet = os.path.join(proj, 'work', 'cut_check.jpg')
os.makedirs(cf, exist_ok=True)
pngs = []
for s in segs[1:]:
    for n in (s['frame'] - 1, s['frame']):
        p = os.path.join(cf, f'f{n}.png')
        subprocess.run([FF, '-loglevel', 'error', '-y', '-i', render, '-vf', f'select=eq(n\\,{n}),scale=150:-2', '-frames:v', '1', p], check=True)
        pngs.append(p)
if pngs:
    ins = sum((['-i', p] for p in pngs), [])
    subprocess.run([FF, '-loglevel', 'error', '-y', *ins, '-filter_complex', f'hstack={len(pngs)}', sheet], check=True)
    print('cuts at frames', [s['frame'] for s in segs[1:]], '->', sheet)
else:
    print('one continuous take: there are no cuts to check')
if '--phone' in sys.argv:
    out = os.path.splitext(render)[0] + '-phone.mp4'
    subprocess.run([FF, '-loglevel', 'error', '-y', '-i', render, '-vf', 'scale=720:-2', '-c:v', 'libx264', '-crf', '26', '-preset', 'slow',
                    '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', out], check=True)
    print('phone copy', out, f'{os.path.getsize(out) / 1e6:.1f} MB')

# how loud the voice is. The reel keeps the level the clip was recorded at: nothing in the edit raises or lowers it.
r = subprocess.run([FF, '-hide_banner', '-nostats', '-i', render, '-vn', '-af', 'volumedetect', '-f', 'null', '-'], **skillenv.TEXT)
levels = dict(re.findall(r'(mean_volume|max_volume): (-?[\d.]+) dB', r.stderr or ''))
if 'max_volume' in levels:
    peak = float(levels['max_volume'])
    note = ('fine' if peak >= -6 else
            'a quiet recording: say so in the delivery note and offer a louder copy (references/cutting.md, step 5)')
    print(f"audio: peak {peak:.1f} dB, average {float(levels.get('mean_volume', 0)):.1f} dB -> {note}")
else:
    print('audio: NO SOUND found in the render. Check that the clip has a voice track before delivering.')
