#!/usr/bin/env python3
"""type-wall / onsets.py: the frame each word starts on, from the AUDIO (Whisper word starts can run early or late).

Run from the slot folder (plain python3, no packages):
    python3 onsets.py            table: Whisper's frame and the suggested swap frame for every word in words.json
    python3 onsets.py -v         also prints the loudness of every frame, to settle a doubtful word by eye

A wall swap should land on the first sound of the word. For each word this looks from 4 frames before to 2 frames
after Whisper's start for the frame where the voice jumps up the most, and suggests that frame. Treat it as a first
guess: a word that runs straight out of the one before (no dip in the voice) keeps Whisper's frame, and the -v strip
settles it. When in doubt go a frame late, never early: a swap before the speaker says the word looks like a mistake.
"""
import array
import json
import math
import os
import shutil
import subprocess
import sys

FF = shutil.which('ffmpeg') or 'ffmpeg'
os.chdir(os.path.dirname(os.path.abspath(__file__)))
raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'],
                     capture_output=True).stdout
a = array.array('h')
a.frombytes(raw[:len(raw) // 2 * 2])
HOP = 1600
db = []
for i in range(len(a) // HOP):
    seg = a[i * HOP:(i + 1) * HOP]
    db.append(20 * math.log10(math.sqrt(sum(v * v for v in seg) / HOP) / 32768 + 1e-9))
n = len(db)
words = json.load(open('words.json')) if os.path.exists('words.json') else []
out = []
prev = -1
for w in words:
    fw = min(n - 1, int(w['start'] * 30 + .5))
    best, jump = fw, 0.0
    for f in range(max(1, prev + 1, fw - 4), min(n - 1, fw + 2) + 1):      # never at or before the word before
        j = db[f] - db[f - 1]
        if j > jump + .01 and db[f] > -45:
            best, jump = f, j
    if jump < 6:                      # no real rise nearby: the word runs straight out of the one before
        best = max(fw, prev + 1)
    prev = best
    out.append((w['text'], fw, best, jump))
if '-v' in sys.argv:
    for i, d in enumerate(db):
        mark = ' '.join(t for t, _, f, _ in out if f == i)
        print(f'{i:4d} {i / 30:6.2f}s {d:6.1f} dB ' + '#' * max(0, int((d + 60) / 1.5)) + ('   <- ' + mark if mark else ''))
    print()
print(f'{n} frames of audio. Speech starts at frame {next((i for i, d in enumerate(db) if d > -32), 0)}.')
print(f'{"word":16s} {"whisper":>7s} {"swap":>5s}  rise dB')
for t, fw, f, j in out:
    print(f'{t:16s} {fw:7d} {f:5d}  {j:6.1f}' + ('   (no clear rise: kept Whisper)' if j < 6 else ''))
os.makedirs('work', exist_ok=True)
json.dump([{'text': t, 'whisper': fw, 'swap': f} for t, fw, f, _ in out], open('work/onsets.json', 'w'), indent=1)
