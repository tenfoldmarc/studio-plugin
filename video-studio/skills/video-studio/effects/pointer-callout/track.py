#!/usr/bin/env python3
"""pointer-callout / track.py: measure every point a line can be tied to and the room around the speaker.
numpy + scipy + Pillow only. Run once per slot.

Reads  assets/subject.webm (cutout alpha), assets/aroll.mp4 (picture + audio), words.json
Writes work/track.json
  anchors    {name: [[x, y] per frame]}: head, head_left, head_right, chest, shoulder_left, shoulder_right, hand_left, hand_right
             (left / right as seen on screen). A name is missing when that point is not usable on this clip.
  box        [[x0, y0, x1, y1] per frame]: the head, top of the cap to the chin. Cards and lines keep out of it.
  hw, hh     head width / height in px;   shot: close / medium / wide
  hand_seen  share of the frames each hand was found (the rest of the time the point rests on the shoulder)
  words      words.json plus `onset`: the word start snapped to the audio (use these, not Whisper's)
       work/occ.png  135 x 240, how often each spot is covered by the speaker (white = always)
How: head from the cutout outline. Chest and shoulders: a point seeded from the head, locked to the cloth with a
96 px template match against one reference frame (FFT correlation). Hands: skin-coloured areas of the cutout away
from the face, colour sampled from the speaker's own face.
"""
import json
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
Q = 4                                              # hands and occupancy are measured at 1/4 size
SAFE = (35, 220, 1045, 1470, 1155, 980)            # left, top, right, bottom, y where the right side tightens, its x
WIN = np.outer(np.hanning(N), np.hanning(N)).astype(np.float32)


def stream(name, alpha=False, size=(W, H), fmt='gray'):
    w, h = size
    ch = 3 if fmt == 'rgb24' else 1
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + \
          ['-i', os.path.join(HERE, 'assets', name), '-vf', ('alphaextract,' if alpha else '') + f'scale={w}:{h}',
           '-f', 'rawvideo', '-pix_fmt', fmt, '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(w * h * ch)
        if len(b) < w * h * ch:
            break
        a = np.frombuffer(b, np.uint8)
        yield a.reshape(h, w, 3) if ch == 3 else a.reshape(h, w)


def gsmooth(v, sig):
    return ndimage.gaussian_filter1d(np.asarray(v, float), sig, mode='nearest') if sig > 0 else np.asarray(v, float)


def fill(v, ok):
    """replace the entries where ok is False by linear interpolation from the good ones"""
    v, ok = np.asarray(v, float), np.asarray(ok, bool)
    i = np.arange(len(v))
    return np.interp(i, i[ok], v[ok]) if ok.any() else v


def silhouette(m):
    """walk down the cutout from its top, following the run of pixels that holds the head.
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
    h = side / 2
    return np.asarray(img.transform((N, N), Image.EXTENT, (cx - h, cy - h, cx + h, cy + h), Image.BILINEAR), np.float32)


def prep(c):
    c = (c - ndimage.gaussian_filter(c, 5)) * WIN
    return c - c.mean()


def follow(patches, ref):
    """shift of every patch against the patch of frame `ref` -> dx, dy (patch px), score. Lost frames are bridged."""
    r0 = prep(patches[ref])
    refc, refn = np.conj(np.fft.rfft2(r0)), float(np.linalg.norm(r0))
    r, c0, out = N // 3, N // 2, []
    for c in patches:
        x = prep(c)
        cc = np.fft.fftshift(np.fft.irfft2(np.fft.rfft2(x) * refc, s=(N, N))) / (refn * np.linalg.norm(x) + 1e-9)
        sub = cc[c0 - r:c0 + r + 1, c0 - r:c0 + r + 1]
        iy, ix = np.unravel_index(int(np.argmax(sub)), sub.shape)
        out.append((float(ix - r), float(iy - r), float(sub[iy, ix])))
    out = np.array(out)
    ok = out[:, 2] >= 0.2
    return fill(out[:, 0], ok) * ok.any(), fill(out[:, 1], ok) * ok.any(), out[:, 2]


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
    band = np.log1p(200 * mag.reshape(k, 32, 8).mean(2))
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


def in_safe(x, y, m=24):
    return (x >= SAFE[0] + m) & (x <= np.where(y >= SAFE[4] - m, SAFE[5], SAFE[2]) - m) & (y >= SAFE[1] + m) & (y <= SAFE[3] - m)


def hands(small, hx, top, hw, hh, s, chest):
    """skin-coloured areas of the cutout away from the face -> per side: x, y, found (arrays), or None"""
    n = len(small)
    rgb = [f.astype(np.float32) for _, f in zip(range(n), stream('aroll.mp4', size=(W // Q, H // Q), fmt='rgb24'))]
    n = min(n, len(rgb))

    def ycc(f):
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
        return .299 * r + .587 * g + .114 * b, 128 - .169 * r - .331 * g + .5 * b, 128 + .5 * r - .419 * g - .081 * b

    cbs, crs = [], []
    for f in range(0, n, max(1, n // 12)):          # the speaker's own skin colour, from cheeks and nose
        y0, y1 = int((top[f] + .5 * hh * s[f]) / Q), int((top[f] + .82 * hh * s[f]) / Q) + 1
        x0, x1 = int((hx[f] - .22 * hw * s[f]) / Q), int((hx[f] + .22 * hw * s[f]) / Q) + 1
        _, cb, cr = ycc(rgb[f][max(0, y0):y1, max(0, x0):x1])
        ok = small[f][max(0, y0):y1, max(0, x0):x1]
        cbs.append(cb[ok]); crs.append(cr[ok])
    cbs, crs = np.concatenate(cbs), np.concatenate(crs)
    if cbs.size < 40:
        return {}
    cb0, cr0 = float(np.median(cbs)), float(np.median(crs))
    tb = float(np.clip(3 * 1.4826 * np.median(np.abs(cbs - cb0)), 6, 13))
    tr = float(np.clip(3 * 1.4826 * np.median(np.abs(crs - cr0)), 6, 13))
    res = {k: np.full((n, 3), np.nan) for k in ('hand_left', 'hand_right')}
    pos, lost = {k: None for k in res}, {k: 99 for k in res}
    yy, xx = np.mgrid[0:H // Q, 0:W // Q]
    for f in range(n):
        lum, cb, cr = ycc(rgb[f])
        skin = small[f] & (np.abs(cb - cb0) < tb) & (np.abs(cr - cr0) < tr) & (lum > 45)
        hwf = hw * s[f]                              # keep the face, ears and neck out
        skin &= ~((np.abs(xx * Q - hx[f]) < .75 * hwf) & (yy * Q > top[f] - .1 * hwf) & (yy * Q < top[f] + hh * s[f] + .55 * hwf))
        lab, k = ndimage.label(ndimage.binary_opening(skin))
        amin = max(6.0, (.2 * hwf / Q) ** 2)
        blobs = []
        for i in range(1, k + 1):
            ys, xs = np.nonzero(lab == i)
            if xs.size >= amin:
                blobs.append((xs * Q + Q / 2, ys * Q + Q / 2))
        blobs = sorted(blobs, key=lambda b: -b[0].size)[:4]
        cen = [(float(b[0].mean()), float(b[1].mean())) for b in blobs]
        gate = {sd: (1.0 + .3 * lost[sd]) * hwf for sd in res}
        dist = lambda sd, j: float(np.hypot(cen[j][0] - pos[sd][0], cen[j][1] - pos[sd][1]))
        claim = {}
        for sd in res:                               # each hand keeps the area nearest to where it was last frame
            if blobs and pos[sd] is not None and lost[sd] <= 10:
                j = min(range(len(blobs)), key=lambda q: dist(sd, q))
                if dist(sd, j) <= gate[sd]:
                    claim[sd] = j
        if len(claim) == 2 and claim['hand_left'] == claim['hand_right']:      # both want the same area: is there another?
            alt = [(dist(sd, q), sd, q) for sd in res for q in range(len(blobs)) if q != claim[sd] and dist(sd, q) <= gate[sd]]
            if alt:
                _, sd, q = min(alt)
                claim[sd] = q
        for sd in res:                               # a hand never seen, or gone for a while: the largest unclaimed area on its side
            if sd not in claim and (pos[sd] is None or lost[sd] > 10):
                spare = [q for q in range(len(blobs)) if q not in claim.values() and ((cen[q][0] < hx[f]) == (sd == 'hand_left'))]
                if spare:
                    claim[sd] = spare[0]
        shared = len(claim) == 2 and claim['hand_left'] == claim['hand_right']
        for sd in res:
            if sd not in claim:
                lost[sd] += 1
                continue
            xs, ys = blobs[claim[sd]]
            if shared:                               # hands together: each takes its own end of the area
                sel = xs <= np.quantile(xs, .45) if sd == 'hand_left' else xs >= np.quantile(xs, .55)
            else:                                    # the far end of the area = the hand, not the forearm
                d = np.hypot(xs - chest[f][0], ys - chest[f][1])
                sel = d >= np.quantile(d, .6)
            res[sd][f] = (xs[sel].mean(), ys[sel].mean(), xs.size)
            pos[sd], lost[sd] = cen[claim[sd]], 0
    return res


def main():
    sil, small = [], []
    for m in stream('subject.webm', alpha=True):
        b = m > 127
        sil.append(silhouette(b))
        small.append(b[::Q, ::Q].copy())
    n = len(sil)
    if n == 0 or sum(s is None for s in sil) > 0.2 * n:
        sys.exit('track.py: no usable cutout in assets/subject.webm (is the speaker in frame for the whole slot?)')
    good = np.array([s is not None and s[3] is not None and 0.05 * W < s[3] < 0.8 * W for s in sil])
    if good.sum() < 0.4 * n:
        sys.exit('track.py: could not find a head + neck shape in the cutout on most frames '
                 '(hood up, long hair over the shoulders, or a hand on the head?). This effect needs a clear head outline.')
    hws = np.array([s[3] if g else np.nan for s, g in zip(sil, good)])
    good &= np.abs(hws / np.nanmedian(hws) - 1) < 0.35
    hw_raw = fill(np.nan_to_num(hws), good)
    hh_ratio = float(np.clip(np.median([(s[4] + 1) / s[3] for s, g in zip(sil, good) if g]), 1.15, 1.6))
    have = np.array([s is not None for s in sil])
    top, bx, bw, shl, shr = np.zeros(n), np.zeros(n), np.zeros(n), np.full(n, np.nan), np.full(n, np.nan)
    for f, s in enumerate(sil):
        if s is None:
            continue
        t, L, R = s[0], s[1], s[2]
        a, b = int(.15 * hw_raw[f]), max(int(.45 * hw_raw[f]), int(.15 * hw_raw[f]) + 2)
        a, b = min(a, len(L) - 1), min(b, len(L))
        top[f], bx[f], bw[f] = t, float(np.median((L[a:b] + R[a:b]) / 2)), float(np.median(R[a:b] - L[a:b] + 1))
        k = int((hh_ratio + .32) * hw_raw[f])        # the row a third of a head width under the chin: shoulder line
        if good[f] and k < len(L):
            shl[f], shr[f] = (bx[f] - L[k]) / hw_raw[f], (R[k] - bx[f]) / hw_raw[f]
    top, bx, bw = fill(top, have), fill(bx, have), fill(bw, have)
    bwm = ndimage.median_filter(bw, 5, mode='nearest')
    ref = int(np.argmin(np.abs(bwm - np.median(bwm)) + 1e6 * ~good))        # a typical, well measured frame
    s = gsmooth(bwm / bwm[ref], 1.6)
    hw, hh = float(hw_raw[ref]), float(hh_ratio * hw_raw[ref])
    hx, top = gsmooth(bx, .8), gsmooth(top, .8)

    seeds = {'chest': np.c_[hx, top + (hh + .6 * hw) * s]}
    for name, half, sign in (('shoulder_left', shl, -1), ('shoulder_right', shr, 1)):
        if np.isfinite(half).sum() >= 3:
            off = float(np.clip(np.nanmedian(half), .75, 1.7)) - .28
            seeds[name] = np.c_[hx + sign * off * hw * s, top + (hh + .42 * hw) * s]
    seeds = {k: v for k, v in seeds.items() if v[ref][1] < H - .25 * hw and .1 * hw < v[ref][0] < W - .1 * hw}

    patches = {k: [] for k in seeds}
    for f, y in enumerate(stream('aroll.mp4')):
        if f >= n:
            break
        img = Image.fromarray(y)
        for k, v in seeds.items():
            patches[k].append(crop(img, v[f][0], v[f][1], 1.1 * hw * s[f]))
    # on the cap / hairline, above the brows: centre, and a quarter of a head width to each side
    anchors, quality = {'head': np.c_[hx, top + .16 * hh * s], 'head_left': np.c_[hx - .27 * hw * s, top + .2 * hh * s],
                        'head_right': np.c_[hx + .27 * hw * s, top + .2 * hh * s]}, {}
    for k, v in seeds.items():
        m = len(patches[k])
        dx, dy, q = follow(patches[k], min(ref, m - 1))
        px = 1.1 * hw * s[:m] / N
        x = gsmooth(ndimage.median_filter(v[:m, 0] + dx * px, 5, mode='nearest'), 1.0)
        y = gsmooth(ndimage.median_filter(v[:m, 1] + dy * px, 5, mode='nearest'), 1.0)
        anchors[k], quality[k] = np.c_[x, y], float(np.median(q))
    n = min([n] + [len(v) for v in anchors.values()])

    chest = anchors.get('chest', np.c_[hx, top + (hh + .6 * hw) * s])
    seen = {}
    for side, r in hands(small[:n], hx, top, hw, hh, s, chest).items():
        m = len(r)
        ok = np.isfinite(r[:, 0])
        ok[ok] &= in_safe(r[ok, 0], r[ok, 1])
        seen[side] = round(float(ok.mean()), 2)
        if ok.sum() < max(3, .1 * m):
            continue
        x = gsmooth(ndimage.median_filter(fill(r[:, 0], ok), 5, mode='nearest'), 1.0)
        y = gsmooth(ndimage.median_filter(fill(r[:, 1], ok), 5, mode='nearest'), 1.0)
        wgt = gsmooth(ndimage.binary_closing(np.r_[np.zeros(7, bool), ok, np.zeros(7, bool)], np.ones(7))[7:-7].astype(float), 2.0)
        rest = anchors.get('shoulder_' + side[5:], chest)[:m]
        if not in_safe(rest[:, 0], rest[:, 1]).all():
            rest = anchors['head'][:m]
        anchors[side] = np.c_[wgt * x + (1 - wgt) * rest[:, 0], wgt * y + (1 - wgt) * rest[:, 1]]
        n = min(n, m)

    box = np.c_[hx - .56 * hw * s, top, hx + .56 * hw * s, top + hh * s][:n]
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    occ = np.mean(np.array(small[:n], np.float32), 0)[::2, ::2]
    Image.fromarray((occ * 255).astype(np.uint8)).save(os.path.join(HERE, 'work/occ.png'))
    words = onsets()
    shot = 'close' if hw > .36 * W else ('medium' if hw > .17 * W else 'wide')
    json.dump({'n': n, 'ref': ref, 'hw': round(hw, 1), 'hh': round(hh, 1), 'shot': shot,
               'anchors': {k: np.round(v[:n], 1).tolist() for k, v in anchors.items()},
               'box': np.round(box, 1).tolist(), 'quality': {k: round(v, 3) for k, v in quality.items()},
               'hand_seen': seen, 'words': words}, open(os.path.join(HERE, 'work/track.json'), 'w'))

    print(f'{n} frames, reference frame {ref}. Head {hw:.0f} px wide, {hh:.0f} px tall = {shot} shot '
          f'(head outline found on {int(good.sum())}/{len(good)} frames)')
    print(f'head box over the slot: x {box[:, 0].min():.0f}..{box[:, 2].max():.0f}  y {box[:, 1].min():.0f}..{box[:, 3].max():.0f}')
    print('anchors you can tie a line to (travel = how far the point moves over the slot; more travel = the line visibly follows):')
    for k, v in anchors.items():
        v = v[:n]
        note = ''
        if k in quality:
            note = f'   cloth match {quality[k]:.2f}' + ('  !! weak (plain cloth or hands crossing)' if quality[k] < .35 else '')
        if k in seen:
            note = f'   hand found on {seen[k] * 100:.0f}% of the frames' + ('  !! mostly resting on the shoulder' if seen[k] < .5 else '')
        ok = bool(in_safe(v[:, 0], v[:, 1]).all())
        print(f"  {k:15s} x {v[:, 0].min():5.0f}..{v[:, 0].max():5.0f}  y {v[:, 1].min():5.0f}..{v[:, 1].max():5.0f}  "
              f"travel {np.hypot(np.ptp(v[:, 0]), np.ptp(v[:, 1])):4.0f} px  {'in the safe zone' if ok else '!! leaves the safe zone'}{note}")
    miss = [k for k in ('chest', 'shoulder_left', 'shoulder_right', 'hand_left', 'hand_right') if k not in anchors]
    if miss:
        print('not available on this clip: ' + ', '.join(miss))
    if words:
        print('words (start snapped to the audio, frame):  ' + '  '.join(f"{w['text']}@{w['onset']:.2f}/f{round(w['onset'] * 30)}" for w in words))


if __name__ == '__main__':
    main()
