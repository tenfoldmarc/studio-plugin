#!/usr/bin/env python3
"""Step 0. Word onsets per FRAME, read off the audio of assets/aroll.mp4 (Whisper word starts are 1 to 4 frames off).

Prints one line per half frame: loudness bar (#), consonant-burst bar (+), and the Whisper word that claims that time.
How to read it for the CLIP block:
  - a word's onset = the first line of its run of # after a gap (vowels) or the + spike just before it (t, k, p, s)
  - the STRESSED VOWEL is where the # bar jumps: that frame is t_land for a snap, and t_land - 2 for a creep
  - caption words get the frame of their onset
Usage (from the slot folder):  PY onsets.py [first_frame last_frame]
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
SR = 24000
raw = subprocess.run([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                     capture_output=True).stdout
a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
hi = np.diff(a, prepend=0)                      # crude high-pass: consonant bursts
wpath = os.path.join(HERE, 'words.json')
words = json.load(open(wpath)) if os.path.exists(wpath) else []
hop = SR // 60
rows = [(float(np.sqrt((a[i * hop:(i + 1) * hop] ** 2).mean())), float(np.sqrt((hi[i * hop:(i + 1) * hop] ** 2).mean())))
        for i in range(len(a) // hop)]
mx, mh = max(r[0] for r in rows) or 1, max(r[1] for r in rows) or 1
f0 = float(sys.argv[1]) if len(sys.argv) > 2 else 0
f1 = float(sys.argv[2]) if len(sys.argv) > 2 else 1e9
print('frame   time   loudness                                  bursts               whisper word')
for i, (rms, rh) in enumerate(rows):
    t = i / 60
    if not f0 <= t * 30 <= f1:
        continue
    w = [x['text'] for x in words if x['start'] <= t < x['end']]
    print(f'f{t * 30:6.1f} {t:5.2f}s {"#" * int(40 * rms / mx):40s} {"+" * int(20 * rh / mh):20s} {w[0] if w else ""}')
