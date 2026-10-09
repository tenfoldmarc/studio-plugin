#!/usr/bin/env python3
"""Word onsets for the CLIP block: Whisper's word start (words.json) next to the frame where the voice actually
starts for that word (first frame within +-5 of Whisper's guess whose level jumps out of a dip). Run from the slot:

  python onsets.py          (any python with numpy)

Use the "onset" column: F_IN = onset of the first key word minus 1, each key word's frame = its onset, F_OUT = onset
of the first word said with the lights back up. Whisper mishears names and brand words: trust the order of the
words, not the spelling, and type the key words the way the speaker says them.
"""
import json
import os
import shutil
import subprocess

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'],
                     capture_output=True).stdout
a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
hop = 1600
db = np.array([20 * np.log10(np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(len(a) // hop)])
floor = np.percentile(db, 10)
loud = np.percentile(db, 90)
thr = floor + .45 * (loud - floor)
words = json.load(open('words.json')) if os.path.exists('words.json') else []
at = {}
print('word            whisper  onset')
for w in words:
    f = round(w['start'] * 30)
    best = None
    for n in range(max(1, f - 5), min(len(db), f + 6)):
        if db[n] >= thr and (db[n - 1] < thr or db[n] - db[n - 1] > 6):      # a rise out of a dip
            if best is None or abs(n - f) < abs(best - f):
                best = n
    on = best if best is not None else f
    at.setdefault(on, []).append(w['text'])
    print(f"{w['text'][:14]:14s}  f{f:4d}    f{on:4d}" + ('' if best is not None else '   (no clear rise: Whisper frame kept)'))
print('\nframe  dB   level')
for i, v in enumerate(db):
    print(f'{i:4d} {v:6.1f} ' + '#' * max(0, int((v + 60) / 1.5)) + ('   <- ' + ' '.join(at[i]) if i in at else ''))
