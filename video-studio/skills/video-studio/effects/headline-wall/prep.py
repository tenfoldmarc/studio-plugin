#!/usr/bin/env python3
"""Headline wall, step 1: measure the clip and lay the cards out. Run from the slot folder with the skill's Python:

  PY prep.py            track + matte (both cached) + layout
  PY prep.py layout     layout only (after editing headlines / WALL)
  PY prep.py --force    redo track and matte too

Reads the CLIP block from build.py, assets/aroll.mp4, assets/subject.webm, clip.json. Writes:
  work/track.json    room homography per frame (reference frame px -> frame n px), "static": true for a still camera
  assets/fg.webm     the cutout with half-transparent motion blur pushed solid (cards must not shine through the speaker)
  work/layout.json   every card: kind, layer, centre, tilt, size, broken lines, landing order   (build.py reads it)
  work/layout.jpg    LOOK AT THIS: last frame with the planned cards, the wall rectangle, their outline, the safe zone

numpy + scipy + PIL only (no OpenCV): the track is a dense, masked Gauss-Newton homography fit against the reference
frame, coarse to fine, so there is no drift from chaining.
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import build as B      # noqa: E402  (the CLIP block lives there)
import cards as C      # noqa: E402

FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H = 1080, 1920
Q = 4                                   # layout masks are 1/4 size
QW, QH = W // Q, H // Q
CLIPJ = json.load(open('clip.json'))
N = int(CLIPJ['frames'])
if CLIPJ.get('cut_frames'):
    sys.exit('headline-wall needs ONE continuous shot: this slot has internal cuts ' + str(CLIPJ['cut_frames']))
REF = B.REF if B.REF is not None else max(0, N - 4)
FORCE = '--force' in sys.argv
ONLY_LAYOUT = 'layout' in sys.argv
os.makedirs('work', exist_ok=True)


# ---------------------------------------------------------------------------------------------------------- decode
def decode(path, w, h, alpha=False):
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + \
          ['-i', path, '-vf', ('alphaextract,' if alpha else '') + f'scale={w}:{h}:flags=area,format=gray',
           '-fps_mode', 'passthrough', '-f', 'rawvideo', '-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, h, w)
    if len(a) != N:
        sys.exit(f'{path}: decoded {len(a)} frames, clip.json says {N}')
    return a


# ----------------------------------------------------------------------------------------------------------- track
_grid = {}


def grid(h, w):
    if (h, w) not in _grid:
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
        s = w / 2
        Nm = np.array([[1 / s, 0, (.5 - w / 2) / s], [0, 1 / s, (.5 - h / 2) / s], [0, 0, 1]])
        _grid[(h, w)] = (xs, ys, Nm, np.linalg.inv(Nm), (xs + .5 - w / 2) / s, (ys + .5 - h / 2) / s, s)
    return _grid[(h, w)]


def warp(img, Hp, order=1):
    """out(x) = img(Hp x), Hp in pixel coords of this image size"""
    h, w = img.shape
    xs, ys = grid(h, w)[:2]
    d = Hp[2, 0] * xs + Hp[2, 1] * ys + Hp[2, 2]
    u = (Hp[0, 0] * xs + Hp[0, 1] * ys + Hp[0, 2]) / d
    v = (Hp[1, 0] * xs + Hp[1, 1] * ys + Hp[1, 2]) / d
    return ndimage.map_coordinates(img, [v, u], order=order, mode='constant', cval=0.0)


def align(R, MR, T, MT, Hn, iters, dof):
    """Gauss-Newton (forward compositional) fit of T(Hn x) ~ gain * R(x) + bias on MR & warped MT.
    dof 6 = affine (coarse levels: a full homography wanders on a plain wall there), 8 = homography (finest level).
    The gain / bias pair soaks up the exposure shift when the speaker moves; without it the fit drifts. Hn in normalised coords."""
    h, w = R.shape
    _, _, Nm, Ni, xn, yn, s = grid(h, w)
    g, b = 0.0, 0.0
    for _ in range(iters):
        Hp = Ni @ Hn @ Nm
        Tw = warp(T, Hp)
        valid = MR & (warp(MT, Hp) > .98)
        if valid.sum() < 400:
            break
        gy, gx = np.gradient(Tw)
        r = (R - (1 + g) * Tw - b)[valid]
        X, Y, GX, GY = xn[valid], yn[valid], gx[valid] * s, gy[valid] * s
        cols = [GX * X, GX * Y, GX, GY * X, GY * Y, GY]
        if dof == 8:
            cols += [-GX * X * X - GY * X * Y, -GX * X * Y - GY * Y * Y]
        J = np.stack(cols + [Tw[valid], np.ones_like(X)], 1)
        sig = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-3
        wgt = np.minimum(1.0, 1.345 * sig / np.maximum(np.abs(r), 1e-6))     # Huber: the speaker's shadow, reflections
        Jw = J * wgt[:, None]
        A = Jw.T @ J
        dp = np.linalg.solve(A + np.eye(dof + 2) * 1e-7 * np.trace(A), Jw.T @ r)
        g, b = g + dp[dof], b + dp[dof + 1]
        p = np.zeros(8)
        p[:dof] = dp[:dof]
        Hn = Hn @ np.array([[1 + p[0], p[1], p[2]], [p[3], 1 + p[4], p[5]], [p[6], p[7], 1]])
        Hn = Hn / Hn[2, 2]
        if np.abs(p).max() < 8e-5:          # ~0.04px
            break
    return Hn


def pool(a, f=np.mean):
    h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
    return f(a[:h, :w].reshape(h // 2, 2, w // 2, 2), axis=(1, 3))


def track(gray2, alpha2):
    """gray2 / alpha2: uint8 stacks at half size. -> list of 3x3 (full-res px, ref -> frame n), static flag"""
    hh, hw = gray2.shape[1:]
    ymax = B.TRACK_YMAX if B.TRACK_YMAX is not None else 1100

    def levels(n):
        g = ndimage.gaussian_filter(gray2[n].astype(np.float64), .8)
        m = ndimage.binary_erosion(alpha2[n] < 10, iterations=12, border_value=1)
        if n == REF:
            m[int(ymax / 2):] = False          # floor / furniture sit nearer than the wall: keep them out of the fit
        g4, m4 = pool(g), pool(m, np.min).astype(bool)
        g8, m8 = pool(g4), pool(m4, np.min).astype(bool)
        return [(g8, m8, 8, 6), (g4, m4, 5, 6), (g, m, 5, 8)]       # (image, mask, iterations, dof) coarse -> fine
    ref = levels(REF)
    Hn = {REF: np.eye(3)}
    for rng in (range(REF - 1, -1, -1), range(REF + 1, N)):
        prev = np.eye(3)
        for n in rng:
            cur = levels(n)
            h = prev
            for (R, MR, it, dof), (T, MT, _, _) in zip(ref, cur):
                h = align(R, MR.astype(bool), T, MT.astype(np.float64), h, it, dof)
            Hn[n] = prev = h
            if n % 10 == 0:
                print(f'  track frame {n}', flush=True)
    s = W / 2
    Nm = np.array([[1 / s, 0, (.5 - W / 2) / s], [0, 1 / s, (.5 - H / 2) / s], [0, 0, 1]])
    Ni = np.linalg.inv(Nm)
    out = []
    for n in range(N):
        m = Ni @ Hn[n] @ Nm                 # pixel index -> pixel index; next line: CSS px (pixel centre = index + .5)
        m = np.array([[1, 0, .5], [0, 1, .5], [0, 0, 1]]) @ m @ np.array([[1, 0, -.5], [0, 1, -.5], [0, 0, 1]])
        out.append(m / m[2, 2])
    probes = np.array([[x, y, 1.0] for x in (120, 400, 680, 960) for y in (200, 450, 700, 950)]).T
    worst = 0.0
    for m in out:
        p = m @ probes
        worst = max(worst, float(np.abs(p[:2] / p[2] - probes[:2]).max()))
    return out, worst


# ----------------------------------------------------------------------------------------------------------- matte
def fix_alpha(a):
    t = np.clip((a - .04) / .30, 0, 1)
    s = t * t * (3 - 2 * t)                               # partial (motion-blurred) alpha goes solid, edges stay soft
    lab, cnt = ndimage.label(s > .1)
    if cnt > 1:
        areas = np.bincount(lab.ravel())
        kill = [i for i in range(1, cnt + 1) if areas[i] < 6000]
        if kill:
            s[np.isin(lab, kill)] = 0
    s = ndimage.minimum_filter(s, size=3)                 # 1px choke: no light wall fringe over the cards
    return ndimage.gaussian_filter(s, 1.1)


def bake_matte(Hs=None):
    size = W * H
    # FOREGROUND polygons (furniture in front of the wall, reference-frame px): added to the cutout so cards go
    # BEHIND them. Drawn once in the reference frame, carried into every frame by the room track.
    furn = None
    if getattr(B, 'FOREGROUND', None):
        im = Image.new('L', (W, H), 0)
        for poly in B.FOREGROUND:
            ImageDraw.Draw(im).polygon([tuple(p) for p in poly], fill=255)
        furn = ndimage.gaussian_filter(np.asarray(im).astype(np.float64) / 255, 1.6)
    dp = subprocess.Popen([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-vf', f'scale={W}:{H}', '-fps_mode', 'passthrough',
                           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    da = subprocess.Popen([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', 'assets/subject.webm', '-vf',
                           f'alphaextract,scale={W}:{H},format=gray', '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'],
                          stdout=subprocess.PIPE)
    enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', '30',
                            '-i', '-', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '18', '-g', '30',
                            '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '3', '-metadata:s:v:0', 'alpha_mode=1',
                            'assets/fg.webm'], stdin=subprocess.PIPE)
    n = 0
    while True:
        rgb, al = dp.stdout.read(size * 3), da.stdout.read(size)
        if len(rgb) < size * 3 or len(al) < size:
            break
        a = fix_alpha(np.frombuffer(al, np.uint8).reshape(H, W).astype(np.float32) / 255)
        if furn is not None:
            fm = furn if Hs is None else warp(furn, np.linalg.inv(Hs[n]))      # frame n px -> reference px
            a = np.maximum(a, fm.astype(np.float32))
        enc.stdin.write(np.dstack([np.frombuffer(rgb, np.uint8).reshape(H, W, 3),
                                   (a * 255).round().astype(np.uint8)]).tobytes())
        n += 1
    enc.stdin.close()
    enc.wait(); dp.wait(); da.wait()
    if n != N:
        sys.exit(f'matte: wrote {n} frames, expected {N}')
    print(f'matte: assets/fg.webm ({n} frames)')


# ------------------------------------------------------------------------------------------------------------ text
_fonts = {}


def em_width(fkey, s):
    if fkey not in _fonts:
        _fonts[fkey] = ImageFont.truetype(os.path.join('assets', 'fonts', C.FONTS[fkey][0]), 200)
    return _fonts[fkey].getlength(s) / 200


def fit(kind, text, wmax=None):
    """break a headline into balanced lines for this card kind -> (lines, card width, card height)"""
    sp = C.SPEC[kind]
    wmax = wmax or sp['w']
    k = C.base(kind)
    size = sp['size']

    def wpx(s):
        p = C.plain(s)
        return (em_width(sp['font'], p) + sp['ls'] * len(p)) * size * 1.03 + (.2 * size if '[' in s else 0)
    # words; a [marked phrase] never breaks
    words, cur, depth = [], '', 0
    for ch in text.strip():
        if ch == '[':
            depth += 1
        if ch == ']':
            depth -= 1
        if ch == ' ' and depth == 0:
            if cur:
                words.append(cur)
            cur = ''
        else:
            cur += ch
    if cur:
        words.append(cur)
    if k == 'search':
        return [' '.join(words)], round(wpx(' '.join(words)) + C.SEARCH_CHROME), C.SEARCH_H
    avail = (wmax - 40) if k == 'chat' else C.text_w(kind, wmax)
    n = len(words)
    lw = {}

    def linew(i, j):
        if (i, j) not in lw:
            lw[(i, j)] = wpx(' '.join(words[i:j]))
        return lw[(i, j)]
    # fewest lines (greedy), then the most even split with that many lines
    count, i = 0, 0
    while i < n:
        j = i + 1
        while j < n and linew(i, j + 1) <= avail:
            j += 1
        i = j
        count += 1
    best = {(0, 0): (0.0, [])}
    for L in range(1, count + 1):
        for j in range(1, n + 1):
            cand = None
            for i in range(L - 1, j):
                if (i, L - 1) not in best:
                    continue
                wl = linew(i, j)
                if wl > avail and j - i > 1:
                    continue
                cost = best[(i, L - 1)][0] + wl * wl
                if cand is None or cost < cand[0]:
                    cand = (cost, best[(i, L - 1)][1] + [(i, j)])
            if cand:
                best[(j, L)] = cand
    spans = best[(n, count)][1]
    lines = [' '.join(words[i:j]) for i, j in spans]
    maxw = max(linew(i, j) for i, j in spans)
    if k == 'chat':
        w = maxw + 40
    else:
        w = min(max(wmax, maxw + 2 * sp['padx']), max(sp['min_w'], maxw + 2 * sp['padx']))
    return lines, round(w), round(C.card_h(kind, len(lines), w))


# ---------------------------------------------------------------------------------------------------------- layout
def ease(t):                                      # sine.inOut, same curve the page uses for the push-in
    return -(math.cos(math.pi * min(max(t, 0), 1)) - 1) / 2


def layout(Hs, alpha_q):
    rng = random.Random(B.SEED)
    warn = []
    f_hold = max(0, min(N - 1, B.F_ACCENT - 2))
    Sq = np.diag([1 / Q, 1 / Q, 1.0])
    Sqi = np.diag([Q, Q, 1.0])

    def to_ref(a, n):                             # frame-n mask -> reference frame (quarter size)
        return warp(a.astype(np.float64), Sq @ Hs[n] @ Sqi)
    sil_ref = [to_ref(alpha_q[n] > 76, n) > .5 for n in range(N)]      # the speaker's silhouette, every frame, in ref coords
    _occ = {}

    n_end = N if B.F_OUT is None else min(N, B.F_OUT + 9)      # cards are gone after the whip-out

    def occ_from(n0):                             # everywhere the speaker goes from frame n0 until the cards leave, + 12px
        n0 = max(0, min(n_end - 1, n0))
        if n0 not in _occ:
            _occ[n0] = ndimage.binary_dilation(np.any(sil_ref[n0:n_end], axis=0), iterations=3)
        return _occ[n0]
    f_hold = min(f_hold, n_end - 1)
    sil = np.mean(sil_ref[f_hold:n_end], axis=0) > .5  # where the speaker is for most of the hold
    occ = occ_from(f_hold)
    occ_pile = np.mean(sil_ref[max(0, B.F_START):min(N, B.F_PEAK + 8)], axis=0)
    # the frame the camera has settled by (within 12px of its final pose): cards are held to the full safe zone from there
    pr = np.array([[x, y, 1.0] for x in (150, 540, 930) for y in (300, 700)]).T
    fin = Hs[N - 1] @ pr
    dev = []
    for m in Hs:
        p = m @ pr
        dev.append(float(np.abs(p[:2] / p[2] - fin[:2] / fin[2]).max()))
    settle = next((n for n in range(N) if max(dev[n:]) < 12), N - 1)
    f_safe = max(f_hold, settle)
    if f_safe > N - 15:
        warn.append(f'the camera is still moving at frame {settle}: cards are only checked against the safe zone for the last 15 frames')
        f_safe = max(0, N - 15)

    # --- head box from the silhouette
    rows = sil.sum(axis=1)
    ys = np.where(rows >= 3)[0]
    if not len(ys):
        sys.exit('layout: the cutout is empty during the hold, check assets/subject.webm')
    y_top = int(ys[0])
    wh = int(rows[y_top:y_top + 30].max())
    wh = int(rows[y_top:y_top + max(8, wh)].max())                  # widest row within one head-width of the top
    sh = next((y for y in range(y_top + int(.8 * wh), QH) if rows[y] > 1.5 * wh), min(QH - 1, y_top + int(1.35 * wh)))
    head_rows = sil[y_top:y_top + max(4, int(.8 * (sh - y_top)))]       # stop above the shoulders
    xs = np.where(head_rows.sum(axis=0) >= 2)[0]
    head = dict(x0=int(xs[0]) * Q, x1=int(xs[-1] + 1) * Q, top=y_top * Q, shoulder=sh * Q)
    head['cx'] = (head['x0'] + head['x1']) / 2
    head_h = head['shoulder'] - head['top']
    face = tuple(B.FACE) if B.FACE else (round(head['cx']), round(head['top'] + .7 * head_h))
    wall = tuple(B.WALL) if B.WALL else (0, 0, W, int(min(1470, head['shoulder'] + 1.3 * head_h)))

    # --- where may a card sit so that it stays inside the safe zone on every frame it is on screen?
    gy, gx = np.mgrid[0:QH, 0:QW]
    P = np.stack([(gx + .5) * Q, (gy + .5) * Q, np.ones_like(gx, dtype=float)]).reshape(3, -1)
    dur = N / 30
    ox, oy = face[0], face[1] - 60
    ok_top, ok_safe = {}, {}
    for L, par in B.PARALLAX.items():
        top = np.ones(QW * QH, bool)
        safe = np.ones(QW * QH, bool)
        for n in list(range(max(0, B.F_START), N, 3)) + [N - 1]:
            e = ease(n / 30 / dur)
            pp = 1 + (par - 1) * e
            q = P.copy()
            q[0] = ox + pp * (P[0] - ox)
            q[1] = oy + pp * (P[1] - oy)
            r = Hs[n] @ q
            s = (1 + (B.PUSH - 1) * e) * (B.BUMP if abs(n - B.F_ACCENT) < 3 else 1)
            sx = face[0] + s * (r[0] / r[2] - face[0])
            sy = face[1] + s * (r[1] / r[2] - face[1])
            top &= (sy >= 224) & (sy <= 1466)
            for kx0, ky0, kx1, ky1 in B.KEEP_OUT:      # e.g. the main reel's label pill: nothing under it, ever
                top &= ~((sx > kx0 - 8) & (sx < kx1 + 8) & (sy > ky0 - 8) & (sy < ky1 + 8))
            if n >= f_safe:
                safe &= (sx >= 39) & (sx <= 1041) & (sy >= 224) & (sy <= 1466) & ~((sx > 976) & (sy > 1151))
        ok_top[L], ok_safe[L] = top.reshape(QH, QW), safe.reshape(QH, QW)
    wallm = np.zeros((QH, QW), bool)
    wallm[int(wall[1] / Q):int(math.ceil(wall[3] / Q)), int(wall[0] / Q):int(math.ceil(wall[2] / Q))] = True

    def bbox(c):
        s = C.LAYER_SCALE[c['layer']] * c.get('shrink', 1)
        a = math.radians(c['rot'])
        return ((c['w'] * abs(math.cos(a)) + c['h'] * abs(math.sin(a))) * s / 2,
                (c['w'] * abs(math.sin(a)) + c['h'] * abs(math.cos(a))) * s / 2)

    def frac(mask, c, cval=0.0):
        """fraction of the card's box that lies on mask, for every possible centre"""
        hw, hh = bbox(c)
        return ndimage.uniform_filter(mask.astype(np.float64), size=(max(1, round(2 * hh / Q)), max(1, round(2 * hw / Q))),
                                      mode='constant', cval=cval)

    def stamp(mask, c):
        hw, hh = bbox(c)
        x0, x1 = int((c['x'] - hw) / Q), int(math.ceil((c['x'] + hw) / Q))
        y0, y1 = int((c['y'] - hh) / Q), int(math.ceil((c['y'] + hh) / Q))
        mask[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True

    def pick(valid, cost, pad=0):
        if not valid.any():
            return None
        cost = np.where(valid, cost, np.inf)
        iy, ix = np.unravel_index(np.argmin(cost), cost.shape)
        return (ix - pad + .5) * Q, (iy + .5) * Q

    cx_map, cy_map = (gx + .5) * Q, (gy + .5) * Q
    cards = []
    sources = dict(outlet=list(B.OUTLETS), person=list(B.PEOPLE), chat=list(B.CHAT_REPLIES))
    counters = dict(outlet=0, person=0, chat=0)

    def src_for(kind):
        k = C.base(kind)
        if k in ('dark',):
            return B.DARK_LABEL
        if k == 'search':
            return ''
        key = 'chat' if k == 'chat' else ('person' if k in ('post', 'quote', 'video') else 'outlet')
        v = sources[key][counters[key] % len(sources[key])]
        counters[key] += 1
        return v

    # --- near layer: hero cards (one per spoken word) alternate sides of the speaker's head, the search pill tops the other side
    near_ok = ok_safe['near'] & ok_top['near'] & wallm
    free = near_ok & ~occ
    taken = np.zeros((QH, QW), bool)
    cols = np.where(near_ok.any(axis=0))[0]
    if not len(cols):
        sys.exit('layout: no wall inside the safe zone. Check WALL in the CLIP block and work/layout.jpg')
    ax0, ax1 = cols[0] * Q, (cols[-1] + 1) * Q
    side_cx = {'L': (ax0 + head['x0']) / 2, 'R': (head['x1'] + ax1) / 2}
    y_min = np.where(near_ok.any(axis=1))[0][0] * Q
    next_top = {'L': None, 'R': None}
    first = B.HERO_FIRST_SIDE
    other = 'R' if first == 'L' else 'L'
    hero_kinds = ['news_h', 'post', 'dark_h', 'video_h']
    plan = []
    for i, (text, frame) in enumerate(B.HEROES):
        plan.append(dict(text=text, frame=frame, side=first if i % 2 == 0 else other, kind=hero_kinds[i % 4], hero=True))
    if B.SEARCH:                                   # the pill is decoration: it takes what room the heroes leave, or is dropped
        plan.append(dict(text=B.SEARCH, frame=None, side=other if B.HEROES else first, kind='search', hero=False))
    for k, p in enumerate(plan):
        placed = None
        # a hero only has to clear where the speaker is from the moment it lands; the pill clears the whole hold
        free = near_ok & ~(occ_from(p['frame'] - B.LEAD) if p['hero'] else occ)
        flip = 'R' if p['side'] == 'L' else 'L'
        tries = ((.04, [p['side']]), (.04, [flip]), (.22, [p['side'], flip])) if p['hero'] else ((.04, [p['side']]), (.04, [flip]))
        for tol, sides in tries:
            for side in sides:
                for shrink in ((1, .92, .85, .78, .7) if p['hero'] else (1, .92, .85)):
                    lines, cw, ch = fit(p['kind'], p['text'])
                    c = dict(kind=p['kind'], layer='near', lines=lines, w=cw, h=ch, shrink=shrink, hero=p['hero'],
                             frame=p['frame'], rot=rng.uniform(2.5, 5) * (-1 if (k + (side == 'R')) % 2 == 0 else 1))
                    if p['kind'] == 'search':
                        c['rot'] = rng.uniform(1.5, 3) * (-1 if side == 'R' else 1)
                    hw, hh = bbox(c)
                    valid = (frac(near_ok, c) > .999) & (frac(free, c) >= 1 - tol) & (frac(taken, c) <= .10)
                    valid &= (cx_map < head['cx']) if side == 'L' else (cx_map > head['cx'])
                    if next_top[side] is not None:
                        tgt = next_top[side]
                    else:
                        # first card on this side: level with the speaker's head, but higher if the heroes stacked on this
                        # side would not fit above the bottom of the clear wall otherwise
                        mine = [q for q in plan if q['hero'] and q['side'] == side]
                        need = sum(2 * bbox(dict(layer='near', rot=4, w=fit(q['kind'], q['text'])[1],
                                                 h=fit(q['kind'], q['text'])[2]))[1] + 6 for q in mine)
                        sm = free & ((cx_map < head['cx']) if side == 'L' else (cx_map > head['cx']))
                        rows_ok = np.where(sm.sum(axis=1) * Q > 200)[0]
                        y_bot = (rows_ok[-1] + 1) * Q if len(rows_ok) else wall[3]
                        tgt = max(y_min, min(head['top'] - .8 * hh, y_bot - need))
                    xy = pick(valid, np.abs((cy_map - hh) - tgt) + .6 * np.abs(cx_map - side_cx[side]))
                    if xy:
                        c['x'], c['y'] = round(xy[0]), round(xy[1])
                        next_top[side] = c['y'] + hh + 6
                        placed = c
                        break
                if placed:
                    break
            if placed:
                break
        if not placed:
            warn.append(f'no room on the wall for "{C.plain(p["text"])}": dropped (shorten it, widen WALL, or use fewer HEROES)'
                        if p['hero'] else 'search pill left out: the heroes took the clear wall')
            continue
        if placed['shrink'] < 1:
            warn.append(f'"{C.plain(p["text"])}" shrunk to {placed["shrink"]:.2f} to fit beside the speaker')
        placed['src'] = src_for(placed['kind'])
        stamp(taken, placed)
        cards.append(placed)

    # --- pile: mid cards (readable, inside the safe zone) then far cards (small, soft; may run off the sides only)
    pool_txt = [h for h in B.HEADLINES if h not in [t for t, _ in B.HEROES]] or list(B.HEADLINES)
    ti = [0]
    maxlen = {'search': 26, 'quote': 30, 'dark': 30, 'chat': 30, 'video': 34, 'clip': 38, 'news': 40, 'mail': 44, 'post': 70}

    def next_card(layer, cycle, j):
        text = pool_txt[ti[0] % len(pool_txt)]
        ti[0] += 1
        ln = len(C.plain(text))
        kind = next((cycle[(j + d) % len(cycle)] for d in range(len(cycle)) if ln <= maxlen[cycle[(j + d) % len(cycle)]]), 'post')
        if kind == 'search':
            text = text.lower()
        lines, cw, ch = fit(kind, text)
        return dict(kind=kind, layer=layer, lines=lines, w=cw, h=ch, hero=False, frame=None, src=src_for(kind),
                    rot=rng.uniform(2, 7) * (1 if j % 2 else -1))

    def scatter(layer, count, cycle, region, min_vis, pad=0):
        chosen = []
        regp = np.pad(region, ((0, 0), (pad, pad)), mode='edge')
        occp = np.pad(occ, ((0, 0), (pad, pad)))
        cxp = (np.arange(-pad, QW + pad) + .5) * Q
        cxp = np.broadcast_to(cxp, regp.shape)
        cyp = np.broadcast_to(((np.arange(QH) + .5) * Q)[:, None], regp.shape)
        for j in range(count):
            c = next_card(layer, cycle, j)
            valid = (frac(regp, c) > .999) & (frac(~occp, c, cval=1.0) >= min_vis)
            if pad:                                # at least 55% of the card stays in frame
                inframe = np.pad(np.ones((QH, QW)), ((0, 0), (pad, pad)))
                valid &= frac(inframe, c) >= .55
            if not valid.any():
                continue
            if chosen:
                d = np.min([np.hypot(cxp - x, (cyp - y) * 1.25) for x, y in chosen], axis=0)
            else:                                  # first one: as far from the speaker's head as the wall allows
                d = np.hypot(cxp - head['cx'], cyp - head['top'])
            d = d + rng.uniform(0, 30) * np.sin(cxp * .013 + j) * np.cos(cyp * .017 + j)      # break the grid feel
            xy = pick(valid, -d, pad)
            c['x'], c['y'] = round(xy[0]), round(xy[1])
            chosen.append((c['x'], c['y']))
            cards.append(c)
        return len(chosen)

    mid_region = ok_safe['mid'] & ok_top['mid'] & wallm
    n_mid = B.N_MID if B.N_MID is not None else int(min(10, max(5, round((mid_region & ~occ).sum() * Q * Q / 85000))))
    n_mid = scatter('mid', n_mid, ['quote', 'clip', 'mail', 'post', 'chat', 'news'], mid_region, .72)
    far_region = ok_top['far'] & wallm
    far_area = (far_region & ~occ).sum() * Q * Q
    n_far = B.N_FAR if B.N_FAR is not None else int(min(16, max(6, round(far_area / 40000))))
    pad = 30 if (B.FAR_BLEED_SIDES and wall[0] <= 0 and wall[2] >= W) else 0
    n_far = scatter('far', n_far, ['news', 'dark', 'post', 'clip', 'search', 'quote', 'video', 'mail', 'chat'],
                    far_region, .4, pad=pad)

    # --- landing order of the pile: what the speaker is not standing in front of comes first, one mid card opens
    def early_vis(c):
        hw, hh = bbox(c)
        x0, x1 = max(0, int((c['x'] - hw) / Q)), min(QW, int(math.ceil((c['x'] + hw) / Q)))
        y0, y1 = max(0, int((c['y'] - hh) / Q)), min(QH, int(math.ceil((c['y'] + hh) / Q)))
        return 1 - float(occ_pile[y0:y1, x0:x1].mean()) if x1 > x0 and y1 > y0 else 1.0
    pile = [c for c in cards if not c['hero']]
    for c in pile:
        c['vis'] = round(early_vis(c), 2)
    pile.sort(key=lambda c: (-round(c['vis'] * 4), rng.random()))
    opener = next((c for c in pile if c['layer'] == 'mid' and c['vis'] > .8), None)
    if opener:
        pile.remove(opener)
        pile.insert(0, opener)
    for k, c in enumerate(pile):
        c['order'] = k
    for k, c in enumerate(cards):
        c['id'] = f'c{k}'
        c['rot'] = round(c['rot'], 1)
    out = dict(ref=REF, frames=N, face=face, head=head, wall=wall, cards=cards, warnings=warn,
               counts=dict(near=len([c for c in cards if c['layer'] == 'near']), mid=n_mid, far=n_far))
    json.dump(out, open('work/layout.json', 'w'), indent=1)
    return out, occ, (ok_safe, ok_top)


def preview(lay, Hs, occ):
    """last frame + where every card ends up on screen at the end of the push-in"""
    subprocess.run([FF, '-v', 'error', '-y', '-i', 'assets/aroll.mp4', '-vf', f'select=eq(n\\,{N - 1})', '-frames:v', '1',
                    'work/_last.png'], check=True)
    im = Image.open('work/_last.png').convert('RGB')
    d = ImageDraw.Draw(im, 'RGBA')
    for box in [(0, 0, W, 220), (0, 1470, W, H), (0, 220, 35, 1470), (W - 35, 220, W, 1155), (W - 100, 1155, W, 1470)]:
        d.rectangle(box, fill=(255, 0, 0, 70))
    fx, fy = lay['face']
    Hl = Hs[N - 1]

    def scr(x, y, layer):
        par = B.PARALLAX[layer]
        qx, qy = fx + par * (x - fx), (fy - 60) + par * (y - (fy - 60))
        r = Hl @ np.array([qx, qy, 1.0])
        return fx + B.PUSH * (r[0] / r[2] - fx), fy + B.PUSH * (r[1] / r[2] - fy)
    x0, y0, x1, y1 = lay['wall']
    d.line([scr(x0, y0, 'far'), scr(x1, y0, 'far'), scr(x1, y1, 'far'), scr(x0, y1, 'far'), scr(x0, y0, 'far')],
           fill=(0, 255, 255, 255), width=4)
    edge = ndimage.binary_dilation(occ) & ~occ
    ey, ex = np.where(edge)
    for x, y in zip(ex, ey):
        px, py = scr((x + .5) * Q, (y + .5) * Q, 'far')
        d.rectangle((px - 2, py - 2, px + 2, py + 2), fill=(255, 0, 255, 255))
    col = {'far': (120, 160, 255, 255), 'mid': (255, 200, 60, 255), 'near': (60, 255, 120, 255)}
    try:
        font = ImageFont.truetype(os.path.join('assets', 'fonts', 'Inter-600-normal.woff2'), 20)
    except OSError:
        font = None
    for c in sorted(lay['cards'], key=lambda c: ['far', 'mid', 'near'].index(c['layer'])):
        s = C.LAYER_SCALE[c['layer']] * c.get('shrink', 1)
        a = math.radians(c['rot'])
        pts = []
        for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1)):
            ux, uy = dx * c['w'] * s / 2, dy * c['h'] * s / 2
            pts.append(scr(c['x'] + ux * math.cos(a) - uy * math.sin(a), c['y'] + ux * math.sin(a) + uy * math.cos(a), c['layer']))
        d.line(pts, fill=col[c['layer']], width=4 if c['layer'] == 'near' else 2)
        tag = ('HERO ' if c['hero'] else f"{c.get('order', '')} ") + C.plain(c['lines'][0])[:16]
        d.text(scr(c['x'] - c['w'] * s / 2 + 6, c['y'] - 10, c['layer']), tag, fill=col[c['layer']], font=font)
    d.ellipse((fx - 9, fy - 9, fx + 9, fy + 9), outline=(255, 255, 255, 255), width=3)
    im.crop((0, 0, W, 1500)).save('work/layout.jpg', quality=88)


# ------------------------------------------------------------------------------------------------------------ main
def trackcheck(Hs, gray2):
    """work/trackcheck.jpg: the reference frame warped into 3 moving frames and blended 50/50 with them.
    Wall details (frames, lamps, mouldings) must look SHARP, the speaker is allowed to ghost."""
    shift = [float(np.abs((m @ np.array([540, 500, 1.0]))[:2] / (m @ np.array([540, 500, 1.0]))[2] - [540, 500]).max()) for m in Hs]
    worst = int(np.argmax(shift))
    picks = sorted({0, worst, (worst + REF) // 2})
    S2, S2i = np.diag([.5, .5, 1.0]), np.diag([2.0, 2.0, 1.0])
    tiles = []
    for n in picks:
        back = warp(gray2[REF].astype(np.float64), np.linalg.inv(S2 @ Hs[n] @ S2i))      # ref seen from frame n
        tiles.append(Image.fromarray((.5 * back + .5 * gray2[n]).clip(0, 255).astype(np.uint8)))
    sheet = Image.new('L', (540 * len(tiles), 960))
    for i, t in enumerate(tiles):
        sheet.paste(t, (540 * i, 0))
    sheet.save('work/trackcheck.jpg', quality=88)
    print(f'track check: work/trackcheck.jpg (frames {picks}: the wall must be sharp in all of them)')


def main():
    if not os.path.exists('assets/subject.webm'):
        sys.exit('assets/subject.webm is missing: make the slot with fx_new.py WITHOUT --no-cutout')
    if FORCE or not os.path.exists('work/track.json'):
        if ONLY_LAYOUT and not FORCE:
            sys.exit('work/track.json is missing: run prep.py without "layout" first')
        print('tracking the room (dense homography against the reference frame) ...', flush=True)
        gray2 = decode('assets/aroll.mp4', W // 2, H // 2)
        Hs, worst = track(gray2, decode('assets/subject.webm', W // 2, H // 2, alpha=True))
        static = worst < 1.2
        json.dump({'ref': REF, 'static': bool(static), 'max_shift_px': round(worst, 2),
                   'hom': [[float(v) for v in m.ravel()] for m in Hs]}, open('work/track.json', 'w'))
        print(f'track: wall moves up to {worst:.1f}px over the clip -> ' +
              ('camera is still, cards are simply pinned' if static else 'cards will ride the homography'))
        if not static:
            trackcheck(Hs, gray2)
    TR = json.load(open('work/track.json'))
    if TR['ref'] != REF or len(TR['hom']) != N:
        sys.exit('work/track.json was made for another reference frame / clip: run prep.py --force')
    Hs = [np.eye(3) if TR['static'] else np.array(h).reshape(3, 3) for h in TR['hom']]
    if B.FIX_MATTE and not ONLY_LAYOUT and (FORCE or 'matte' in sys.argv or not os.path.exists('assets/fg.webm')):
        print('baking assets/fg.webm ...', flush=True)
        bake_matte(None if TR['static'] else Hs)
    if 'matte' in sys.argv:          # `prep.py matte`: re-bake the cutout only (after editing FOREGROUND)
        return
    lay, occ, _ = layout(Hs, decode('assets/subject.webm', QW, QH, alpha=True))
    preview(lay, Hs, occ)
    print(f"layout: {lay['counts']}  face {lay['face']}  head {lay['head']}  wall {lay['wall']}")
    for c in lay['cards']:
        print(f"  {c['id']:4s} {c['layer']:4s} {c['kind']:8s} ({c['x']:5d},{c['y']:5d}) {c['w']}x{c['h']} rot {c['rot']:5.1f} "
              f"{'HERO f' + str(c['frame']) if c['hero'] else 'pile ' + str(c['order']):10s} {' / '.join(c['lines'])}")
    for wmsg in lay['warnings']:
        print('WARNING:', wmsg)
    print('wrote work/layout.json and work/layout.jpg (look at it: cards on bare wall only? WALL right? nothing on their face?)')


if __name__ == '__main__':
    main()
