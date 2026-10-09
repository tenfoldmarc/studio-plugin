#!/usr/bin/env python3
"""odometer / measure: everything build.py reads off the clip instead of hard-coding it.

  - their cutout alpha per frame (assets/subject.webm -> work/alpha_135.npy, 8 px cells) : where the panels can sit
  - the audio envelope (120 samples per second)                                          : when words really start / end
  - words.json look-ups ("hundred percent" -> end of "percent", snapped to the dip in the audio)

Run it on its own to SEE the numbers before you fill the CLIP block (slot folder, the skill's Python (PY)):
    PY measure.py
It prints every Whisper word with its measured start / end, and where the speaker is in the frame.
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
CELL = 8                      # px per matte cell
GW, GH = 1080 // CELL, 1920 // CELL
HOP = 1 / 120                 # envelope step (s)


def clip():
    """{'frames': N, 'cut_frames': [...]} from clip.json (written by fx_new.py), else counted from the a-roll"""
    p = os.path.join(HERE, 'clip.json')
    if os.path.exists(p):
        c = json.load(open(p))
        if c.get('frames'):
            return c
    n = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                        '-of', 'csv=p=0', os.path.join(HERE, 'assets/aroll.mp4')], capture_output=True, text=True).stdout.strip()
    return {'frames': int(n), 'cut_frames': []}


def alpha():
    """bool [frames, 240, 135]: True where their cutout covers the cell. Cached in work/."""
    n = clip()['frames']
    src = os.path.join(HERE, 'assets/subject.webm')
    if not os.path.exists(src):
        sys.exit('odometer needs the cutout (assets/subject.webm): the panels sit BEHIND the speaker. Make the slot without --no-cutout.')
    cache = os.path.join(HERE, 'work', f'alpha_{GW}.npy')
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(src):
        a = np.load(cache)
        if a.shape == (n, GH, GW):
            return a > 60
    # -c:v libvpx-vp9 BEFORE -i, or ffmpeg's native decoder drops the alpha plane
    raw = subprocess.run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', src, '-vf', f'alphaextract,scale={GW}:{GH}:flags=area',
                          '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, GH, GW)
    if len(a) != n:
        sys.exit(f'cutout has {len(a)} frames, the a-roll has {n}: it would drift. Re-make the slot.')
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    np.save(cache, a)
    return a > 60


_ENV = []


def envelope():
    """dB (RMS over 1/60 s) every 1/120 s of the a-roll's audio"""
    if _ENV:
        return _ENV[0]
    pcm = subprocess.run([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-vn', '-ac', '1', '-ar', '48000',
                          '-f', 's16le', '-'], capture_output=True).stdout
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    hop, win = 400, 800
    out = []
    for i in range(0, max(1, len(x) - win), hop):
        out.append(20 * np.log10(max(float(np.sqrt((x[i:i + win] ** 2).mean())), 1e-5)))
    _ENV.append(np.array(out))
    return _ENV[0]


def voice_db():
    """how loud their speech is in this slot (90th percentile of the envelope, dB): the ticks are set under it"""
    return float(np.percentile(envelope(), 90))


def _idx(env, t):
    return int(min(len(env) - 1, max(0, round((t - 1 / 120) / HOP))))      # window centre = i*HOP + 1/120


def _t(i):
    return i * HOP + 1 / 120


def _dips(env, a, b):
    """local minima of the envelope between indices a..b (inclusive)"""
    return [i for i in range(max(1, a), min(len(env) - 1, b + 1)) if env[i] <= env[i - 1] and env[i] < env[i + 1]]


def snap_end(env, t):
    """A word's real end: the dip in the envelope NEAREST to Whisper's end (from 0.05 s before it to 0.12 s after).
    Nearest, not deepest: the deepest dip around "ten" is the stop gap inside the word, 0.09 s too early.
    No clear dip (the speaker runs straight into the next word) -> Whisper's time."""
    cands = [i for i in _dips(env, _idx(env, t - .05), _idx(env, t + .12))
             if env[_idx(env, _t(i) - .3):i + 1].max() - env[i] >= 8]
    if not cands:
        return t
    return round(_t(min(cands, key=lambda i: abs(_t(i) - t))), 3)


def _rise(env, k):
    """from a quiet point k: walk to the end of the silence, then the first clear rise. None if nothing rises."""
    while k < len(env) - 2 and env[k + 1] <= env[k] + 1.5 and env[k + 1] < -34:
        k += 1
    peak = env[k:min(len(env), k + 31)].max()
    if peak - env[k] < 8:
        return None
    thr = env[k] + .4 * (peak - env[k])
    for i in range(k, min(len(env), k + 31)):
        if env[i] >= thr:
            return round(_t(i) - HOP / 2, 3)
    return None


def snap_start(env, t, floor=0.0):
    """A word's real start: the nearest dip to Whisper's start (never before `floor`, the measured end of the word
    before it), then the first rise out of it. Whisper drops the start anywhere in the pause before a word (0.36 s
    early on "running" in the demo) and splits fast words in the wrong place. Nothing clear -> Whisper's time."""
    lo = max(t - .10, floor - .03)
    best = None
    for i in sorted(_dips(env, _idx(env, lo), _idx(env, max(lo, t) + .12)), key=lambda i: abs(_t(i) - t)):
        r = _rise(env, i)
        if r is not None:
            best = r
            break
    if best is None and env[_idx(env, max(t, floor))] < -34:      # Whisper's start sits in a silence: walk out of it
        best = _rise(env, _idx(env, max(t, floor)))
    return max(best if best is not None else t, floor - .03, 0.0)


def timeline(ws, env):
    """measured (start, end) for every word in words.json, in order (each start is bounded by the word before)"""
    out, prev_end = [], 0.0
    for w in ws:
        e = snap_end(env, w['end'])
        s = snap_start(env, w['start'], floor=prev_end)
        if s >= e - .03:
            s = max(min(w['start'], e - .05), 0.0)
        out.append((round(s, 3), round(e, 3)))
        prev_end = e
    return out


def words():
    p = os.path.join(HERE, 'words.json')
    return json.load(open(p)) if os.path.exists(p) else []


def norm(w):
    return ''.join(ch for ch in w.lower() if ch.isalnum())


def find_say(ws, phrase, after=0.0):
    """indices (first, last) of the spoken phrase in words.json, first match starting at or after `after` seconds"""
    want = [norm(x) for x in phrase.split()]
    have = [norm(w['text']) for w in ws]
    for i in range(len(have) - len(want) + 1):
        if have[i:i + len(want)] == want and ws[i]['start'] >= after - 1e-6:
            return i, i + len(want) - 1
    return None


def subject(m):
    """where the speaker is: anchor = top of their silhouette (their head in almost every framing), silhouette box, per frame + median"""
    tops, axs = [], []
    for f in range(len(m)):
        ys = np.where(m[f].any(axis=1))[0]
        if not len(ys):
            continue
        y0, y1 = ys[0], ys[-1]
        band = m[f][y0:y0 + max(2, int((y1 - y0) * .06))]
        xs = np.where(band.any(axis=0))[0]
        tops.append(y0 * CELL)
        axs.append((xs[0] + xs[-1] + 1) / 2 * CELL)
    u = m.any(axis=0)
    ys, xs = np.where(u.any(axis=1))[0], np.where(u.any(axis=0))[0]
    if not len(tops):
        return None
    return {'ax': float(np.median(axs)), 'ay': float(np.median(tops)), 'top_min': float(min(tops)), 'top_max': float(max(tops)),
            'box': [int(xs[0] * CELL), int(ys[0] * CELL), int((xs[-1] + 1) * CELL), int((ys[-1] + 1) * CELL)]}


if __name__ == '__main__':
    c = clip()
    env = envelope()
    print(f"clip: {c['frames']} frames ({c['frames'] / 30:.2f}s), cut frames {c.get('cut_frames', [])}")
    print('\nword           whisper start-end    measured start   measured end   (put the END of the spoken number in `lock`,')
    print('                                                                 or just name the words in `say`)')
    ws = words()
    for w, (s, e) in zip(ws, timeline(ws, env)):
        print(f"{w['text']:14s} {w['start']:6.2f} - {w['end']:5.2f}        {s:6.2f}          {e:6.2f}")
    if os.path.exists(os.path.join(HERE, 'assets/subject.webm')):
        s = subject(alpha())
        print(f"\nhim: top of their head around x {s['ax']:.0f}, y {s['ay']:.0f} (moves between y {s['top_min']:.0f} and "
              f"{s['top_max']:.0f}); silhouette box over the whole clip x {s['box'][0]}-{s['box'][2]}, y {s['box'][1]}-{s['box'][3]}")
    if '--env' in sys.argv:
        for i, d in enumerate(env):
            print(f'{_t(i):6.3f}  {d:6.1f}  ' + '#' * int(max(0, d + 60) / 2))
