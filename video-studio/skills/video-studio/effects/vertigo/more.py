#!/usr/bin/env python3
"""Step 1b (optional, strongly recommended on a still speaker). Pull extra frames of the SAME take from around the
slot, so the clean plate sees more of the room behind the speaker (every lean, nod and gesture uncovers a bit more).

Reads clip.json (`src`, `in`, `duration`, written by fx_new.py), cuts up to SECONDS before and after the slot at
5 frames per second, framed exactly like the a-roll -> work/more.mp4. Then matte it with the slot's own cutout tool:
    $PYM _shared/rvm_cut.py . --src work/more.mp4 --out work/more.webm
prep.py uses both files when they exist (MORE=0 prep.py ignores them). Frames from a different shot are rejected
by prep.py's alignment check, so a source with cuts in it is safe, just less useful.
Usage (from the slot folder):  PY more.py [SECONDS, default 10]
"""
import json
import os
import subprocess
import sys

from vcore import FF, FP, here

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
clip = json.load(open(here('clip.json')))
src = clip.get('src', '')
if not src or not os.path.exists(src):
    sys.exit(f'more.py: the source in clip.json is not on this computer ({src or "none"}): skip this step')
dur_src = float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', src],
                               capture_output=True, text=True).stdout.strip() or 0)
t_in, dur = float(clip['in']), float(clip['duration'])
spans = [(max(0.0, t_in - secs), t_in - 0.2), (t_in + dur + 0.2, min(dur_src, t_in + dur + secs))]
spans = [(a, b) for a, b in spans if b - a > 0.4]
if not spans:
    sys.exit('more.py: no footage around the slot in the source')
fit = 'fps=5,scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1'
parts = []
for k, (a, b) in enumerate(spans):
    p = here('work', f'more_{k}.mp4')
    subprocess.run([FF, '-v', 'error', '-y', '-ss', f'{a:.3f}', '-i', src, '-t', f'{b - a:.3f}', '-vf', fit, '-an',
                    '-c:v', 'libx264', '-crf', '14', '-preset', 'medium', '-pix_fmt', 'yuv420p', p], check=True)
    parts.append(p)
lst = here('work', 'more_list.txt')
with open(lst, 'w') as f:
    f.write(''.join(f"file '{os.path.basename(p)}'\n" for p in parts))
subprocess.run([FF, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', here('work', 'more.mp4')],
               check=True)
print(f'wrote work/more.mp4 ({sum(b - a for a, b in spans):.1f}s of the same take at 5 fps). Next:\n'
      '  $PYM _shared/rvm_cut.py . --src work/more.mp4 --out work/more.webm')
