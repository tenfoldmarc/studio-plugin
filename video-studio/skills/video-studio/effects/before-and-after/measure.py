#!/usr/bin/env python3
"""before-after / measure: everything build.py reads off the clip instead of hard-coding it.

  - the audio envelope (120 samples per second)            : when the words really start (Whisper is 0.1 to 0.3 s off)
  - the cutout alpha per frame (assets/subject.webm)        : where the head is, so the line never rests on the face
    (no cutout in the slot = no head numbers; build.py then needs REST as a number, or does one straight sweep)

Run it on its own to SEE the numbers before you fill the CLIP block (slot folder):
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
CELL = 8                      # px per matte cell
GW, GH = 1080 // CELL, 1920 // CELL
HOP = 1 / 120                 # envelope step (s)


def count_frames(path):
    n = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                        '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.strip()
    return int(n or 0)


def clip():
    """{'frames': N, ...} from clip.json (written when the slot is made), else counted from the a-roll"""
    p = os.path.join(HERE, 'clip.json')
    if os.path.exists(p):
        c = json.load(open(p))
        if c.get('frames'):
            return c
    return {'frames': count_frames(os.path.join(HERE, 'assets/aroll.mp4')), 'cut_frames': []}


def has_cutout():
    return os.path.exists(os.path.join(HERE, 'assets/subject.webm'))


def alpha():
    """bool [frames, 240, 135]: True where the cutout covers the cell. Cached in work/. None without a cutout."""
    if not has_cutout():
        return None
    n = clip()['frames']
    src = os.path.join(HERE, 'assets/subject.webm')
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


def heads(m):
    """per frame (x0, top, x1, chin) in px: the head at the top of the silhouette. Walks down from the first covered
    row until it has gone as far down as the head is wide (or the shoulders arrive). chin = top + 1.35 x width.
    Frames with no subject copy their neighbour. Smoothed over 5 frames."""
    out = []
    for f in range(len(m)):
        rows = np.where(m[f].any(axis=1))[0]
        if not len(rows):
            out.append(None)
            continue
        y0 = rows[0]
        ext = []
        for r in range(y0, min(GH, y0 + 120)):
            xs = np.where(m[f][r])[0]
            if not len(xs):
                break
            ext.append((xs[0], xs[-1] + 1))
        w = [b - a for a, b in ext]
        big, k = w[0], 0
        for k in range(1, len(w)):
            if w[k] > 1.45 * big and k >= .5 * big:
                break                                  # shoulders
            big = max(big, w[k])
            if k >= big:
                break
        x0, x1 = min(a for a, _ in ext[:k + 1]), max(b for _, b in ext[:k + 1])
        out.append([x0 * CELL, y0 * CELL, x1 * CELL, y0 * CELL + 1.35 * (x1 - x0) * CELL])
    known = [i for i, h in enumerate(out) if h is not None]
    if not known:
        return None
    for i in range(len(out)):
        if out[i] is None:
            out[i] = out[min(known, key=lambda j: abs(j - i))]
    a = np.array(out, float)
    sm = np.array([np.median(a[max(0, i - 2):i + 3], axis=0) for i in range(len(a))])
    return sm


def head_box(hs, f0, f1):
    """union of the head boxes over frames f0..f1 -> (x0, top, x1, chin)"""
    seg = hs[max(0, f0):max(f0 + 1, min(len(hs), f1 + 1))]
    return float(seg[:, 0].min()), float(seg[:, 1].min()), float(seg[:, 2].max()), float(seg[:, 3].max())


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


def _idx(env, t):
    return int(min(len(env) - 1, max(0, round((t - 1 / 120) / HOP))))      # window centre = i*HOP + 1/120


def _t(i):
    return i * HOP + 1 / 120


def _dips(env, a, b):
    return [i for i in range(max(1, a), min(len(env) - 1, b + 1)) if env[i] <= env[i - 1] and env[i] < env[i + 1]]


def snap_end(env, t):
    """a word's real end: the dip in the envelope NEAREST to Whisper's end. No clear dip -> Whisper's time."""
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
    """a word's real start: the nearest dip to Whisper's start (never before `floor`, the measured end of the word
    before it), then the first rise out of it. Nothing clear -> Whisper's time."""
    lo = max(t - .10, floor - .03)
    best = None
    for i in sorted(_dips(env, _idx(env, lo), _idx(env, max(lo, t) + .12)), key=lambda i: abs(_t(i) - t)):
        r = _rise(env, i)
        if r is not None:
            best = r
            break
    if best is not None and best - t > .15 and env[_idx(env, t)] > -30:
        best = None            # the speaker is already talking at Whisper's start: that rise is the NEXT word, keep Whisper's time
    if best is None and env[_idx(env, max(t, floor))] < -34:      # Whisper's start sits in a silence: walk out of it
        best = _rise(env, _idx(env, max(t, floor)))
    return max(best if best is not None else t, floor - .03, 0.0)


def timeline(ws, env):
    """measured (start, end) for every word in words.json, in order (each start is bounded by the word before)"""
    out, floor = [], 0.0
    for w in ws:
        e = snap_end(env, w['end'])
        # bounded by the START of the word before (+0.06), not its end: Whisper's word ends run into the next word
        s = snap_start(env, w['start'], floor=floor)
        if s >= e - .03:
            s = max(min(w['start'], e - .05), 0.0)
        out.append((round(s, 3), round(e, 3)))
        floor = s + .09
    return out


def words():
    p = os.path.join(HERE, 'words.json')
    return json.load(open(p)) if os.path.exists(p) else []


def norm(w):
    return ''.join(ch for ch in w.lower() if ch.isalnum())


def find_say(ws, phrase, nth=1):
    """index of the first word of the spoken phrase in words.json (the nth time the speaker says it), or None"""
    want = [norm(x) for x in phrase.split()]
    have = [norm(w['text']) for w in ws]
    seen = 0
    for i in range(len(have) - len(want) + 1):
        if have[i:i + len(want)] == want:
            seen += 1
            if seen == nth:
                return i
    return None


if __name__ == '__main__':
    c = clip()
    env = envelope()
    print(f"clip: {c['frames']} frames ({c['frames'] / 30:.2f}s)")
    print('\nword           whisper start    measured start   (COMMIT / PEEK take the word itself; build.py uses the measured start)')
    ws = words()
    for w, (s, e) in zip(ws, timeline(ws, env)):
        print(f"{w['text']:14s} {w['start']:6.2f}           {s:6.2f}")
    m = alpha()
    if m is None:
        print('\nno cutout in this slot: no head numbers. Set REST to an x beside the head (look at a frame), or REST = None.')
    else:
        hs = heads(m)
        x0, top, x1, chin = head_box(hs, 0, len(hs) - 1)
        print(f'\nhead over the whole slot: x {x0:.0f}-{x1:.0f}, top {top:.0f}, chin about {chin:.0f}')
        for f in range(0, len(hs), 15):
            h = hs[f]
            print(f'  f{f:3d} {f / 30:5.2f}s  x {h[0]:.0f}-{h[2]:.0f}  top {h[1]:.0f}  chin {h[3]:.0f}')
    if '--env' in sys.argv:
        for i, d in enumerate(env):
            print(f'{_t(i):6.3f}  {d:6.1f}  ' + '#' * int(max(0, d + 60) / 2))
