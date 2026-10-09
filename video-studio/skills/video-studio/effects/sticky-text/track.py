#!/usr/bin/env python3
"""sticky-text / track.py: measure everything the tag sticks to. numpy + scipy + Pillow only. Run once per slot.

Reads  assets/subject.webm (cutout alpha), assets/aroll.mp4 (picture + audio), words.json
Writes work/track.json:
  frames[f] = hx, hy   head centre (silhouette: cap top + half a head height, cap centre line)
              s        head size relative to frame `ref` (width of the cap band in the cutout)
              rot      head roll in degrees relative to frame `ref` (+ = clockwise on screen), template match
              cx, cy   a point of cloth on their chest (template match seeded under their chin), crot = its roll
              q, cq    match quality 0..1 (head, chest)
  hw, hh, capw        head width / height and cap band width in px at frame `ref`;  top = y of the cap top per frame
  words               words.json plus `onset`: the word start snapped to the audio (use these, not Whisper's)
How: silhouette for position and size (it is the edge the eye checks the tag against), a 96 px template of the head
/ chest matched against the reference frame over a few angles for roll (FFT correlation, no optical flow).
"""
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H, N = 1080, 1920, 96
WIN = np.outer(np.hanning(N), np.hanning(N)).astype(np.float32)


def stream(name, alpha):
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + \
          ['-i', os.path.join(HERE, 'assets', name), '-vf', ('alphaextract,' if alpha else '') + f'scale={W}:{H}',
           '-f', 'rawvideo', '-pix_fmt', 'gray', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(W * H)
        if len(b) < W * H:
            break
        yield np.frombuffer(b, np.uint8).reshape(H, W)


def gsmooth(v, sig):
    return ndimage.gaussian_filter1d(np.asarray(v, float), sig, mode='nearest') if sig > 0 else np.asarray(v, float)


def fill(v, ok):
    """replace the entries where ok is False by linear interpolation from the good ones"""
    v, ok = np.asarray(v, float), np.asarray(ok, bool)
    i = np.arange(len(v))
    return np.interp(i, i[ok], v[ok])


def silhouette(m):
    """walk down the cutout from its top, following the run of pixels that holds their head.
    -> top row, left / right edge per row, head width (widest row before the neck), neck row (or None)"""
    solid = (m.sum(1) >= 8).astype(np.float32)
    ok = np.flatnonzero(np.convolve(solid, np.ones(7, np.float32), 'valid') >= 7)
    if ok.size == 0:
        return None
    top, c, L, R = int(ok[0]), None, [], []
    for y in range(top, H):
        idx = np.flatnonzero(m[y])
        if idx.size == 0:
            break
        cut = np.flatnonzero(np.diff(idx) > 1)
        s, e = np.r_[idx[0], idx[cut + 1]], np.r_[idx[cut], idx[-1]]
        k = int(np.argmax(e - s)) if c is None else int(np.argmin(np.where((s <= c) & (c <= e), 0, np.minimum(abs(s - c), abs(e - c)))))
        L.append(s[k]); R.append(e[k]); c = (s[k] + e[k]) / 2
        if len(L) > 60 and (e[k] - s[k]) > 0.9 * W:
            break
    L, R = np.array(L, float), np.array(R, float)
    ws = ndimage.uniform_filter1d(R - L + 1, 9, mode='nearest')
    cm = np.maximum.accumulate(ws)
    k = np.arange(len(ws))
    cand = np.flatnonzero((k > 0.6 * cm) & (ws < 0.88 * cm))
    hw = neck = None
    if cand.size:
        j = int(cand[0]); hw = float(cm[j])
        seg = ws[j:min(len(ws), int(2.2 * hw))]
        sh = np.flatnonzero(seg > 1.2 * hw)
        end = int(sh[0]) if sh.size else len(seg)
        neck = j + (int(np.argmin(seg[:end])) if end > 0 else 0)
    return top, L, R, hw, neck


def crop(img, cx, cy, side):
    """N x N patch centred on (cx, cy), `side` px wide in the frame (zeros outside the picture)"""
    h = side / 2
    return np.asarray(img.transform((N, N), Image.EXTENT, (cx - h, cy - h, cx + h, cy + h), Image.BILINEAR), np.float32)


def prep(c):
    c = (c - ndimage.gaussian_filter(c, 5)) * WIN
    return c - c.mean()


def match(refc, refn, c, ang):
    """how well patch c, turned back by `ang` degrees, fits the reference -> (score, dx, dy) in patch px"""
    x = prep(ndimage.rotate(c, ang, reshape=False, order=1, mode='nearest') if ang else c)
    cc = np.fft.fftshift(np.fft.irfft2(np.fft.rfft2(x) * refc, s=(N, N))) / (refn * np.linalg.norm(x) + 1e-9)
    r, c0 = N // 3, N // 2
    sub = cc[c0 - r:c0 + r + 1, c0 - r:c0 + r + 1]
    iy, ix = np.unravel_index(int(np.argmax(sub)), sub.shape)
    p, dx, dy = float(sub[iy, ix]), float(ix - r), float(iy - r)
    if 0 < ix < 2 * r and 0 < iy < 2 * r:          # sub-pixel peak
        a, b, c2 = sub[iy, ix - 1], sub[iy, ix], sub[iy, ix + 1]
        dx += float(.5 * (a - c2) / (a - 2 * b + c2 - 1e-9))
        a, c2 = sub[iy - 1, ix], sub[iy + 1, ix]
        dy += float(.5 * (a - c2) / (a - 2 * b + c2 - 1e-9))
    return p, dx, dy


def follow(patches, ref):
    """roll + residual shift of every patch against the patch of frame `ref` (search walks outwards from ref)"""
    r0 = prep(patches[ref])
    refc, refn = np.conj(np.fft.rfft2(r0)), float(np.linalg.norm(r0))
    n = len(patches)
    out = [None] * n
    out[ref] = (0.0, 0.0, 0.0, 1.0)
    for order in (range(ref + 1, n), range(ref - 1, -1, -1)):
        prev = 0.0
        for f in order:
            sc = {a: match(refc, refn, patches[f], a) for a in (prev + d for d in (-3, -2, -1, 0, 1, 2, 3))}
            b = max(sc, key=lambda a: sc[a][0])
            for a in (b - .5, b + .5):
                sc[a] = match(refc, refn, patches[f], a)
            pa, pb, pc = sc[b - .5][0], sc[b][0], sc[b + .5][0]
            ang = b + .25 * (pa - pc) / (pa - 2 * pb + pc - 1e-9) if pb >= max(pa, pc) else max((b - .5, b, b + .5), key=lambda a: sc[a][0])
            p, dx, dy = sc[min(sc, key=lambda a: abs(a - ang))]
            if p < 0.2:                             # lost (hand in front, blur): hold the last good angle
                ang, dx, dy = prev, 0.0, 0.0
            out[f] = (float(ang), dx, dy, p)
            prev = float(ang)
    return out


def onsets():
    wp = os.path.join(HERE, 'words.json')
    if not os.path.exists(wp):
        return []
    words = json.load(open(wp))
    raw = subprocess.run([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-vn', '-ac', '1', '-ar', '16000',
                          '-f', 's16le', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop, win = 160, 512                             # 10 ms hop, 32 ms window
    k = (len(a) - win) // hop
    if k < 8:
        return words
    idx = np.arange(win)[None, :] + hop * np.arange(k)[:, None]
    mag = np.abs(np.fft.rfft(a[idx] * np.hanning(win), axis=1))[:, 1:257]
    band = np.log1p(200 * mag.reshape(k, 32, 8).mean(2))               # 32 bands of 250 Hz: an "s" shows in the top ones
    flux = np.r_[0, 0, np.maximum(band[2:] - band[:-2], 0).sum(1)]     # spectral flux: something new starts here
    for w in words:
        c = w['start'] * 100
        i = np.arange(max(2, int(c) - 14), min(k, int(c) + 22))
        if i.size == 0:
            w['onset'] = w['start']
            continue
        b = int(i[np.argmax(flux[i] * np.exp(-.5 * ((i - c) / 10.0) ** 2))])
        w['onset'] = round((b * hop + win / 2 - hop) / 16000, 3)
    return words


def main():
    sil = [silhouette(m > 127) for m in stream('subject.webm', True)]
    n = len(sil)
    if n == 0 or sum(s is None for s in sil) > 0.2 * n:
        sys.exit('track.py: no usable cutout in assets/subject.webm (is the speaker in frame for the whole slot?)')
    good = np.array([s is not None and s[3] is not None and 0.05 * W < s[3] < 0.8 * W for s in sil])
    if good.sum() < 0.4 * n:
        sys.exit('track.py: could not find a head + neck shape in the cutout on most frames '
                 '(hood up, long hair over the shoulders, or a hand on their head?). This effect needs a clear head outline.')
    hws = np.array([s[3] if g else np.nan for s, g in zip(sil, good)])
    good &= np.abs(hws / np.nanmedian(hws) - 1) < 0.35
    hw_raw = fill(np.nan_to_num(hws), good)
    hh_ratio = float(np.clip(np.median([(s[4] + 1) / s[3] for s, g in zip(sil, good) if g]), 1.15, 1.6))
    # cap band: the rows 15% to 45% of a head width under the cap top. Its centre line and width are read on every
    # frame, also the ones where the collar hides the neck.
    have = np.array([s is not None for s in sil])
    top, bx, bw = np.zeros(n), np.zeros(n), np.zeros(n)
    for f, s in enumerate(sil):
        if s is None:
            continue
        t, L, R = s[0], s[1], s[2]
        a, b = int(.15 * hw_raw[f]), max(int(.45 * hw_raw[f]), int(.15 * hw_raw[f]) + 2)
        a, b = min(a, len(L) - 1), min(b, len(L))
        top[f], bx[f], bw[f] = t, float(np.median((L[a:b] + R[a:b]) / 2)), float(np.median(R[a:b] - L[a:b] + 1))
    top, bx, bw = fill(top, have), fill(bx, have), fill(bw, have)
    bwm = ndimage.median_filter(bw, 5, mode='nearest')
    ref = int(np.argmin(np.abs(bwm - np.median(bwm)) + 1e6 * ~good))        # a typical, well measured frame
    s_rel = bwm / bwm[ref]
    hw, hh = float(hw_raw[ref]), float(hh_ratio * hw_raw[ref])
    hx, hy = bx, top + .5 * hh * s_rel
    chest_y = top + (hh + .8 * hw) * s_rel

    hp, cp = [], []
    for f, y in enumerate(stream('aroll.mp4', False)):
        if f >= n:
            break
        img = Image.fromarray(y)
        hp.append(crop(img, hx[f], hy[f], 1.5 * hw * s_rel[f]))
        cp.append(crop(img, hx[f], chest_y[f], 1.3 * hw * s_rel[f]))
    n = min(n, len(hp))
    ht, ct = follow(hp, ref), follow(cp, ref)
    chest_ok = bool(chest_y[ref] < H - .25 * hw)

    def place(tr, x0, y0, side):
        rot = np.array([t[0] for t in tr])
        px = N / (side * s_rel[:n])
        dx, dy = np.array([t[1] for t in tr]) / px, np.array([t[2] for t in tr]) / px
        cs, sn = np.cos(np.radians(rot)), np.sin(np.radians(rot))
        return rot, x0[:n] + dx * cs - dy * sn, y0[:n] + dx * sn + dy * cs, np.array([t[3] for t in tr])

    hrot, tx, ty, hq = place(ht, hx, hy, 1.5 * hw)
    crot, cx, cy, cq = place(ct, hx, chest_y, 1.3 * hw)
    # head position = silhouette, except where it jumps away from the template (hand at the speaker's head, matte flicker)
    ex, ey = tx - hx[:n], ty - hy[:n]
    mx, my = ndimage.median_filter(ex, 9, mode='nearest'), ndimage.median_filter(ey, 9, mode='nearest')
    bad = (np.hypot(ex - mx, ey - my) > .12 * hw * s_rel[:n]) & (hq > .3)
    px, py = np.where(bad, tx - mx, hx[:n]), np.where(bad, ty - my, hy[:n])
    px, py, cx, cy = gsmooth(px, .8), gsmooth(py, .8), gsmooth(cx, .8), gsmooth(cy, .8)
    hrot, ss = gsmooth(hrot, 1.6), gsmooth(s_rel[:n], 1.6)
    # cloth folds and a low camera fake a roll on the chest: drop the spikes, smooth more, stay within 8 degrees of the head
    crot = np.clip(gsmooth(ndimage.median_filter(crot, 9, mode='nearest'), 3), hrot - 8, hrot + 8)
    speed = np.r_[0, np.hypot(np.diff(px), np.diff(py))]
    move = int(np.argmax(ndimage.uniform_filter1d(speed, 3)))
    words = onsets()
    fr = [{'f': f, 'hx': round(float(px[f]), 2), 'hy': round(float(py[f]), 2), 's': round(float(ss[f]), 4),
           'rot': round(float(hrot[f]), 3), 'top': round(float(py[f] - .5 * hh * ss[f]), 2),
           'cx': round(float(cx[f]), 2), 'cy': round(float(cy[f]), 2), 'crot': round(float(crot[f]), 3),
           'q': round(float(hq[f]), 3), 'cq': round(float(cq[f]), 3)} for f in range(n)]
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    json.dump({'n': n, 'ref': ref, 'hw': round(hw, 1), 'hh': round(hh, 1), 'capw': round(float(bwm[ref]), 1),
               'chest_ok': chest_ok, 'move_frame': move,
               'frames': fr, 'words': words}, open(os.path.join(HERE, 'work/track.json'), 'w'))

    shot = 'close' if hw > .36 * W else ('medium' if hw > .17 * W else 'wide')
    print(f'{n} frames, reference frame {ref}. Head {hw:.0f} px wide, {hh:.0f} px tall = {shot} shot '
          f'(head outline found on {int(good.sum())}/{len(good)} frames, silhouette overruled on {int(bad.sum())})')
    print(f'head centre x {px.min():.0f}..{px.max():.0f}  y {py.min():.0f}..{py.max():.0f}   cap top y {min(r["top"] for r in fr):.0f}..'
          f'{max(r["top"] for r in fr):.0f}   roll {hrot.min():+.1f}..{hrot.max():+.1f} deg   size {ss.min():.2f}..{ss.max():.2f}')
    print(f'head match quality: median {np.median(hq):.2f}, worst {hq.min():.2f}' + ('   !! weak: check the lock sheet' if np.median(hq) < .35 else ''))
    if chest_ok:
        print(f'chest point x {cx.min():.0f}..{cx.max():.0f}  y {cy.min():.0f}..{cy.max():.0f}   match median {np.median(cq):.2f}, worst {cq.min():.2f}'
              + ('   !! weak (plain cloth or hands crossing): prefer cap / head' if np.median(cq) < .35 else ''))
    else:
        print("chest: under the frame edge on this clip, anchor 'chest' is not available")
    print(f'biggest head movement: frame {move} ({speed[move]:.0f} px per frame)')
    if words:
        print('words (start snapped to the audio, frame):  ' + '  '.join(f"{w['text']}@{w['onset']:.2f}/f{round(w['onset'] * 30)}" for w in words))


if __name__ == '__main__':
    main()
