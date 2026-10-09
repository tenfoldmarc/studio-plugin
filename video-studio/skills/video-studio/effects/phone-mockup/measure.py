#!/usr/bin/env python3
"""phone-mockup / measure: what build.py reads off the clip instead of having it typed in.

  - the speaker's cutout alpha per frame (assets/subject.webm, 8 px cells) : which side has room, how big the phone can be
  - the audio envelope (120 samples per second)                             : where a word's stressed syllable lands
  - words.json look-ups ('approve', or 'send#2' for the second time it is said)

Run it on its own to SEE the numbers before filling the CLIP block (slot folder, the skill's Python (PY)):
    PY measure.py
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
CELL = 8
GW, GH = 1080 // CELL, 1920 // CELL
HOP = 1 / 120


def clip():
    """{'frames': N, ...} from clip.json (fx_new.py writes it), else counted from the a-roll"""
    p = os.path.join(HERE, 'clip.json')
    if os.path.exists(p):
        c = json.load(open(p))
        if c.get('frames'):
            return c
    n = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                        '-of', 'csv=p=0', os.path.join(HERE, 'assets/aroll.mp4')], capture_output=True, text=True).stdout.strip()
    return {'frames': int(n), 'cut_frames': []}


def has_cutout():
    return os.path.exists(os.path.join(HERE, 'assets/subject.webm'))


def alpha():
    """float [frames, 240, 135] in 0..1: how much of each 8 px cell the speaker covers. Cached in work/."""
    n = clip()['frames']
    src = os.path.join(HERE, 'assets/subject.webm')
    cache = os.path.join(HERE, 'work', f'alpha_{GW}.npy')
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(src):
        a = np.load(cache)
        if a.shape == (n, GH, GW):
            return a.astype(np.float32) / 255
    # -c:v libvpx-vp9 BEFORE -i, or ffmpeg's own decoder drops the alpha plane
    raw = subprocess.run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', src, '-vf', f'alphaextract,scale={GW}:{GH}:flags=area',
                          '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, GH, GW)
    if len(a) != n:
        sys.exit(f'cutout has {len(a)} frames, the a-roll has {n}: it would drift. Re-make the slot.')
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    np.save(cache, a)
    return a.astype(np.float32) / 255


def head(a):
    """(x, y) of the top of the speaker's silhouette, median over the frames (their head in almost every framing)"""
    xs, ys = [], []
    for f in range(len(a)):
        m = a[f] > .5
        rows = np.where(m.any(axis=1))[0]
        if not len(rows):
            continue
        y0, y1 = rows[0], rows[-1]
        cols = np.where(m[y0:y0 + max(2, int((y1 - y0) * .06))].any(axis=0))[0]
        ys.append(y0 * CELL)
        xs.append((cols[0] + cols[-1] + 1) / 2 * CELL)
    return (float(np.median(xs)), float(np.median(ys))) if ys else (540.0, 500.0)


_ENV = []


def envelope():
    """dB (RMS over 1/60 s) every 1/120 s of the a-roll's audio"""
    if not _ENV:
        pcm = subprocess.run([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-vn', '-ac', '1', '-ar', '48000',
                              '-f', 's16le', '-'], capture_output=True).stdout
        x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        _ENV.append(np.array([20 * np.log10(max(float(np.sqrt((x[i:i + 800] ** 2).mean())), 1e-5))
                              for i in range(0, max(1, len(x) - 800), 400)]))
    return _ENV[0]


def _idx(env, t):
    return int(min(len(env) - 1, max(0, round((t - 1 / 120) / HOP))))


def _t(i):
    return i * HOP + 1 / 120


def stress(env, s, e):
    """Where a tap on this word should land: the start of its LOUDEST syllable, not the start of the word
    (a tap on the weak first syllable of "approve" reads a fifth of a second early). s, e = Whisper's start / end."""
    c = onsets(env, s, e)
    if not c:
        return round(s, 3)
    top = max(p for _, p in c)
    return next(t for t, p in c if p >= top - 3)   # the first syllable that is about as loud as the loudest


def onsets(env, s, e):
    """[(time, peak dB)] of every syllable that starts inside the word: a rise of 8 dB or more within 40 ms.
    Starts before Whisper's own start are left out: they belong to the word before (the "to a-" ahead of "-PROVE")."""
    out, i, i1 = [], _idx(env, max(0, s - .03)), _idx(env, e - .04)
    while i <= i1:
        if env[i] > -32 and env[i] - env[max(0, i - 5):i + 1].min() >= 8:
            out.append((round(max(0.0, _t(i) - HOP / 2), 3), float(env[i:i + 12].max())))
            i += 10
        else:
            i += 1
    return out


def words():
    p = os.path.join(HERE, 'words.json')
    return json.load(open(p)) if os.path.exists(p) else []


def norm(w):
    return ''.join(ch for ch in str(w).lower() if ch.isalnum())


def find(ws, word):
    """index of a spoken word in words.json. 'send' = first time, 'send#2' = second time. None if the speaker never says it."""
    name, _, nth = str(word).partition('#')
    hits = [i for i, w in enumerate(ws) if norm(w['text']) == norm(name)]
    k = int(nth) - 1 if nth.isdigit() else 0
    return hits[k] if k < len(hits) else None


def when(x, fallback=None):
    """CLIP 'when' -> seconds. A word (its stressed syllable), a frame number (int), or None -> fallback."""
    if x is None:
        return fallback
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return round(x / 30, 4)
    ws = words()
    i = find(ws, x)
    if i is None:
        sys.exit(f'"{x}" is not in words.json. Spoken words: ' + ' '.join(w['text'] for w in ws) +
                 '\n(use one of these, word#2 for a repeat, or a frame number)')
    return stress(envelope(), ws[i]['start'], ws[i]['end'])


if __name__ == '__main__':
    c = clip()
    env = envelope()
    print(f"clip: {c['frames']} frames ({c['frames'] / 30:.2f}s)")
    print('\nword            whisper start-end    tap lands   frame   other syllable starts in the word (frames)')
    for w in words():
        t = stress(env, w['start'], w['end'])
        alt = ' '.join(str(round(o * 30)) for o, _ in onsets(env, w['start'], w['end']) if abs(o - t) > .02)
        print(f"{w['text']:15s} {w['start']:6.2f} - {w['end']:5.2f}       {t:6.2f}     {round(t * 30):4d}    {alt}")
    print('(a tap that looks early or late: give TAPS the frame number instead of the word)')
    if has_cutout():
        a = alpha()
        hx, hy = head(a)
        u = a.mean(axis=0) > .25
        cols = np.where(u.any(axis=0))[0]
        l, r = cols[0] * CELL, (cols[-1] + 1) * CELL
        print(f'\nspeaker: top of the head around x {hx:.0f}, y {hy:.0f}; body spans x {l} to {r} '
              f'(room at their widest point: {max(0, l - 35)} px on the left, {max(0, 1045 - r)} px on the right; build.py does the real search)')
    else:
        print('\nno cutout (assets/subject.webm): build.py needs LAYER="front" and SIDE / PHONE_W / PHONE_TOP typed in')
    if '--env' in sys.argv:
        for i, d in enumerate(env):
            print(f'{_t(i):6.3f}  {d:6.1f}  ' + '#' * int(max(0, d + 60) / 2))
