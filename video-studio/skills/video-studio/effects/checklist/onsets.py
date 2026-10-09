#!/usr/bin/env python3
"""checklist / onsets.py: word onsets from the AUDIO, not from Whisper (its word starts run 1 to 4 frames early).

Run from the slot folder (plain python3, no packages):
    python3 onsets.py            table of suggested frames for every word in words.json
    python3 onsets.py -v         also prints the per-frame loudness strip, to check a suggestion by eye

For each word it finds the loudest frame near Whisper's start, walks back to where the sound rises to within 10 dB of
that peak (the stressed vowel), and prints:
    loud   first frame of the stressed vowel
    say    loud - 2  -> use as f_say for the word that STARTS a row's phrase (the row text lands on the consonant)
    tick   loud - 1  -> use as f_tick for the word that FINISHES the phrase (the check peaks 2 frames later, on the vowel)
Treat it as a first guess: a soft word right after a loud one can be off by a frame or two. The strip settles it.
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
words = json.load(open('words.json')) if os.path.exists('words.json') else []
n = len(db)
out = []
for w in words:
    fw = min(n - 1, round(w['start'] * 30))
    hi = min(n - 1, max(fw + 2, min(fw + 8, round(w['end'] * 30) + 2)))
    pk = max(range(fw, hi + 1), key=lambda i: db[i])
    loud = pk
    while loud > 0 and loud > fw - 1 and db[loud - 1] >= db[pk] - 10:     # never walk back into the word before
        loud -= 1
    out.append((w['text'], fw, loud, max(0, loud - 2), max(0, loud - 1), db[pk]))
    w['loud_frame'] = loud
if '-v' in sys.argv:
    for i, d in enumerate(db):
        mark = ' '.join(t for t, fw, loud, *_ in out if loud == i)
        print(f'{i:4d} {i / 30:6.2f}s {d:6.1f} dB ' + '#' * max(0, int((d + 60) / 1.5)) + ('   <- ' + mark if mark else ''))
    print()
print(f'{n} frames of audio. Speech starts at frame {next((i for i, d in enumerate(db) if d > -32), 0)}.')
print(f'{"word":16s} {"whisper":>7s} {"loud":>5s} {"say":>5s} {"tick":>5s}  peak dB')
for t, fw, loud, say, tick, p in out:
    print(f'{t:16s} {fw:7d} {loud:5d} {say:5d} {tick:5d}  {p:6.1f}')
os.makedirs('work', exist_ok=True)
json.dump([{'text': t, 'whisper': fw, 'loud': loud, 'say': say, 'tick': tick} for t, fw, loud, say, tick, _ in out],
          open('work/onsets.json', 'w'), indent=1)
