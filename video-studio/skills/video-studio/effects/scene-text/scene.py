#!/usr/bin/env python3
"""scene-text machinery: a small word printed across the speaker's real wall like wallpaper (behind him and behind the
things on the wall), then 1 to 3 big painted words land on it. Reads the CLIP block at the top of build.py.

Run from the slot folder with the effect's python (numpy, Pillow, opencv-python-headless; see effect.md):
  python scene.py measure          camera track, wall map, his head, the wall's perspective, the variant it picks
                                   -> work/cache/, work/measure.json, work/measure.jpg (LOOK at it)
  python scene.py still 40 80 120  those frames -> work/stills/ + work/stills/sheet.jpg  (SAFE=1 draws the guide)
  python scene.py bake             every frame -> assets/fx.mp4 (all cores; WORKERS=n to limit)
Everything is seeded: the same slot and CLIP block give the same frames on any machine.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H, FPS = 1080, 1920, 30
HW, HH = W // 2, H // 2               # analysis size
MG = 240                              # margin of the wall-plane canvas around the frame, px
CACHE = os.path.join(HERE, 'work', 'cache')
SAFE_BOX = (35, 220, 1045, 1470)      # Reels safe zone; plus the right column x > 980 from y 1155
cv2.setNumThreads(1)


def P(*a):
    return os.path.join(HERE, *a)


def clip_block():
    src = open(P('build.py'), encoding='utf-8').read()
    a, b = src.index('# ==== CLIP (edit this) ===='), src.index('# ==== END CLIP ====')
    ns = {}
    exec(compile(src[a:b], 'build.py CLIP block', 'exec'), ns)
    return ns


def n_frames():
    return json.load(open(P('clip.json')))['frames']


# ------------------------------------------------------------------------------------------------------------ frame IO
def reader(path, w, h, alpha=False):
    """Frames as numpy arrays. accurate_rnd: swscale's fast YUV->RGB path is about 2 levels dark."""
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + ['-i', path]
    vf = (['alphaextract'] if alpha else []) + ([f'scale={w}:{h}'] if (w, h) != (W, H) else [])
    if vf:
        cmd += ['-vf', ','.join(vf)]
    pix, ch = ('gray', 1) if alpha else ('rgb24', 3)
    cmd += ['-sws_flags', 'accurate_rnd+full_chroma_int+bicubic', '-f', 'rawvideo', '-pix_fmt', pix, '-']
    n = w * h * ch
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=n)   # frame counts are checked
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            a = np.frombuffer(buf, np.uint8)
            yield a.reshape(h, w) if ch == 1 else a.reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.wait()


def writer(path):
    vf = ('scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,'
          'setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709')
    return subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r',
                             str(FPS), '-i', '-', '-an', '-vf', vf, '-c:v', 'libx264', '-preset', 'medium', '-crf', '12',
                             '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
                             '-color_range', 'tv', '-movflags', '+faststart', path], stdin=subprocess.PIPE)


# --------------------------------------------------------------------------------------------------------------- utils
def sstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def m3(m):
    return np.vstack([m, [0, 0, 1]]).astype(np.float64)


def lum(img):
    return img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722


def hexrgb(h):
    h = h.lstrip('#')
    return np.float32([int(h[i:i + 2], 16) for i in (0, 2, 4)])


def noise(shape, cell, seed):
    rng = np.random.default_rng(seed)
    small = rng.random((shape[0] // cell + 2, shape[1] // cell + 2)).astype(np.float32)
    return cv2.resize(small, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)


def ell(k):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def cased(text, case):
    return text.upper() if case == 'upper' else text.lower() if case == 'lower' else text


# --------------------------------------------------------------------------------------------------------------- fonts
def font_faces():
    css_path = P('assets', 'fonts', 'fonts.css')
    if not os.path.exists(css_path):
        sys.exit('assets/fonts/fonts.css is missing: the slot was not made with fx_new.py')
    faces = []
    for blk in re.findall(r'@font-face\s*{(.*?)}', open(css_path, encoding='utf-8').read(), re.S):
        fam = re.search(r"font-family:\s*['\"]?([^;'\"]+)", blk)
        src = re.search(r"url\(\s*['\"]?([^'\")]+)", blk)
        if not (fam and src):
            continue
        wt = re.search(r'font-weight:\s*(\d+)(?:\s+(\d+))?', blk)
        st = re.search(r'font-style:\s*(\w+)', blk)
        lo = int(wt.group(1)) if wt else 400
        faces.append(dict(family=fam.group(1).strip(), lo=lo, hi=int(wt.group(2)) if wt and wt.group(2) else lo,
                          style=st.group(1) if st else 'normal', path=P('assets', 'fonts', src.group(1))))
    return faces


def load_font(family, weight, size, style='normal'):
    faces = [f for f in font_faces() if f['family'].lower() == family.lower() and os.path.exists(f['path'])]
    if not faces:
        have = sorted({f['family'] for f in font_faces()})
        sys.exit(f'font "{family}" is not in assets/fonts/fonts.css. Pick one of: {", ".join(have)}')
    same = [f for f in faces if f['style'] == style] or faces
    best = min(same, key=lambda f: 0 if f['lo'] <= weight <= f['hi'] else min(abs(f['lo'] - weight), abs(f['hi'] - weight)))
    font = ImageFont.truetype(best['path'], size)
    try:                                       # variable files open at their default weight: set the one asked for
        axes = font.get_variation_axes()
        vals = []
        for ax in axes:
            name = ax.get('name', b'')
            name = name.decode('latin-1') if isinstance(name, bytes) else str(name)
            vals.append(min(max(weight, ax['minimum']), ax['maximum']) if name.lower().startswith('weight')
                        else ax.get('default', ax['minimum']))
        font.set_variation_by_axes(vals)
    except Exception:
        pass
    return font


def word_mask(text, font, tracking=0.0, bolden=0.0):
    """Tight 8-bit mask of one word, tracking in em, bolden = extra stroke as a fraction of the letter size."""
    size = font.size
    xs, x = [], 0.0
    for ch in text:
        xs.append(x)
        x += font.getlength(ch) + tracking * size
    im = Image.new('L', (int(x + size), int(size * 1.8)), 0)
    d = ImageDraw.Draw(im)
    if tracking == 0:
        sw = int(round(bolden * size))
        d.text((size * 0.3, size * 0.3), text, font=font, fill=255, stroke_width=sw, stroke_fill=255)
    else:
        for ch, cx in zip(text, xs):
            d.text((cx + size * 0.3, size * 0.3), ch, font=font, fill=255)
    a = np.asarray(im)
    ys, xx = np.where(a > 8)
    if not len(ys):
        sys.exit(f'"{text}" draws nothing in this font')
    return a[ys.min():ys.max() + 1, xx.min():xx.max() + 1]


# ------------------------------------------------------------------------------------------------------------ measure
def track(grays, alphas):
    """Camera motion of the room, frame to frame (similarity transform fitted to the background only).
    Returns per frame a 3x3 that maps reference-frame px (analysis size) to that frame's px."""
    n = len(grays)
    acc = [np.eye(3)]
    weak = 0
    for f in range(1, n):
        bg = (cv2.dilate((alphas[f - 1] > 10).astype(np.uint8), ell(31)) == 0).astype(np.uint8) * 255
        bg[:8], bg[-8:], bg[:, :8], bg[:, -8:] = 0, 0, 0, 0
        pts = cv2.goodFeaturesToTrack(grays[f - 1], 500, 0.01, 7, mask=bg)
        T = np.eye(3)
        if pts is not None and len(pts) >= 12:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(grays[f - 1], grays[f], pts, None, winSize=(21, 21), maxLevel=3)
            ok = st[:, 0] == 1
            if ok.sum() >= 10:
                m, inl = cv2.estimateAffinePartial2D(pts[ok], nxt[ok], method=cv2.RANSAC, ransacReprojThreshold=1.2)
                if m is not None and inl is not None and inl.sum() >= 8:
                    T = m3(m)
                else:
                    weak += 1
            else:
                weak += 1
        else:
            weak += 1
        acc.append(T @ acc[-1])
    r = n // 2
    inv_r = np.linalg.inv(acc[r])
    return [a @ inv_r for a in acc], r, weak


def full_res(Mh):
    """analysis-size 3x3 -> full-size 3x3 (pixel centres kept)."""
    S = np.array([[2, 0, 0.5], [0, 2, 0.5], [0, 0, 1]], np.float64)
    return S @ Mh @ np.linalg.inv(S)


def keystone(plate_h, person_h):
    """Vanishing point of the room's vertical lines (door frames, wall corners, shelves, windows), full-size px.
    None when there are too few lines or they are parallel enough that the wall reads flat."""
    g = cv2.GaussianBlur(cv2.cvtColor(plate_h, cv2.COLOR_RGB2GRAY), (0, 0), 1.2)
    e = cv2.Canny(g, 30, 90)
    e[cv2.dilate(person_h, ell(25)) > 0] = 0
    segs = cv2.HoughLinesP(e, 1, np.pi / 360, 45, minLineLength=70, maxLineGap=5)
    if segs is None:
        return None, []
    L = []
    for x1, y1, x2, y2 in segs.reshape(-1, 4).astype(np.float64):
        dx, dy = (x2 - x1) * 2.0, (y2 - y1) * 2.0
        ln = np.hypot(dx, dy)
        if ln > 0 and np.degrees(np.arctan2(abs(dx), abs(dy))) < 12:          # within 12 degrees of upright
            L.append((x1 * 2.0 + .5, y1 * 2.0 + .5, x2 * 2.0 + .5, y2 * 2.0 + .5, ln))
    if len(L) < 4:
        return None, L
    L = np.array(L)
    xs = (L[:, 0] + L[:, 2]) / 2
    if sum(L[:, 4]) < 900 or xs.max() - xs.min() < 0.3 * W:
        return None, L
    keep = np.ones(len(L), bool)
    vp = None
    for _ in range(3):
        A = []
        for x1, y1, x2, y2, ln in L[keep]:
            l = np.cross([x1 - 540, y1 - 960, 1.0], [x2 - 540, y2 - 960, 1.0])
            l /= np.hypot(l[0], l[1])
            A.append(l * np.sqrt(ln))
        A = np.array(A)
        _, _, vt = np.linalg.svd(A)
        v = vt[-1]
        if abs(v[2]) < 1e-9:
            return None, L[keep]
        vp = v[:2] / v[2]
        # angular error of every line to the VP
        err = []
        for x1, y1, x2, y2, ln in L:
            mx, my = (x1 + x2) / 2 - 540, (y1 + y2) / 2 - 960
            a1 = np.arctan2(x2 - x1, y2 - y1)
            a2 = np.arctan2(vp[0] - mx, vp[1] - my)
            d = abs((a1 - a2 + np.pi / 2) % np.pi - np.pi / 2)
            err.append(np.degrees(d))
        keep = np.array(err) < 1.2
        if keep.sum() < 4:
            return None, L
    if abs(vp[1]) > 40000:                     # verticals all but parallel: the wall is flat on
        return None, L[keep]
    if abs(vp[1]) < 2600:                      # never steeper than this, whatever the lines say
        vp = vp * (2600 / abs(vp[1]))
    return (float(vp[0]), float(vp[1])), L[keep]


def plane_h(vp):
    """3x3: wall-plane canvas px -> reference frame px (full size). Flat on when vp is None."""
    T_in = np.array([[1, 0, -MG - 540], [0, 1, -MG - 960], [0, 0, 1]], np.float64)
    T_out = np.array([[1, 0, 540], [0, 1, 960], [0, 0, 1]], np.float64)
    Hc = np.eye(3)
    if vp is not None:
        vx, vy = vp
        Hc = np.array([[1, vx / vy, 0], [0, 1, 0], [0, 1 / vy, 1]], np.float64)
    return T_out @ Hc @ T_in


def wall_map(plate_h, holes_h):
    """Where the plain wall is (0..1, analysis size): smooth, and the colour the wall has at that spot. Things hanging
    on it, shelves, windows, lamps, furniture and the floor come out as 'not wall', so the print goes behind them."""
    lab = cv2.cvtColor(plate_h, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100 / 255.0
    lab[..., 1:] -= 128
    L = cv2.GaussianBlur(lab[..., 0], (0, 0), 1.5)
    g = np.hypot(cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3))
    tex = cv2.GaussianBlur(g, (0, 0), 4.0)
    usable = ~holes_h
    t_tex = max(4.0, 2.2 * float(np.percentile(tex[usable], 25)))
    cand = (tex < t_tex) & usable
    yy, xx = np.mgrid[0:HH, 0:HW].astype(np.float32)
    xn, yn = xx / HW - .5, yy / HH - .5
    basis = np.stack([np.ones_like(xn), xn, yn, xn * xn, xn * yn, yn * yn], -1)
    idx = np.flatnonzero(cand.ravel()[::1])
    if len(idx) < 500:
        return np.zeros((HH, HW), np.float32), dict(t_tex=t_tex, tol=0, L=0)
    idx = idx[::max(1, len(idx) // 40000)]
    B = basis.reshape(-1, 6)[idx]
    Y = lab.reshape(-1, 3)[idx]
    keep = np.ones(len(idx), bool)
    for _ in range(4):
        coef, *_ = np.linalg.lstsq(B[keep], Y[keep], rcond=None)
        r = np.sqrt(((B @ coef - Y) ** 2).sum(1))
        med = float(np.median(r[keep]))
        keep = r < max(3.5, 2.5 * med)
    model = (basis.reshape(-1, 6) @ coef).reshape(HH, HW, 3)
    dE = np.sqrt(((lab - model) ** 2).sum(-1))
    tol = max(8.0, 3.5 * med)
    wall = sstep((tol - dE) / (tol * 0.5)) * sstep((t_tex * 2.0 - tex) / t_tex)
    b = (wall > 0.5).astype(np.uint8)
    b = cv2.morphologyEx(b, cv2.MORPH_OPEN, ell(5))
    nl, lab_cc, stats, _ = cv2.connectedComponentsWithStats(b, 8)
    small = np.zeros(nl, bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] < 0.003 * HW * HH
    small[1:] |= stats[1:, cv2.CC_STAT_TOP] > 0.62 * HH        # a plain patch that starts low is floor or a rug, not wall
    b[small[lab_cc]] = 0
    b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, ell(7))
    wall_L = float(np.median(lab[..., 0][b > 0])) if b.any() else 0.0
    return cv2.GaussianBlur(b.astype(np.float32), (0, 0), 0.8), dict(t_tex=round(t_tex, 2), tol=round(tol, 2), L=round(wall_L, 1))


def head_of(alpha_h):
    """Head of the cutout in one frame (analysis size): top y, centre x, width. None if he is out of frame."""
    rows = np.flatnonzero((alpha_h > 128).sum(1) >= 6)
    if not len(rows):
        return None
    top = rows[0]
    band = alpha_h[top + 20:top + 70] > 128
    ws, cs = [], []
    for r in band:
        xs = np.flatnonzero(r)
        if len(xs):
            ws.append(xs[-1] - xs[0] + 1)
            cs.append((xs[-1] + xs[0]) / 2)
    if not ws:
        return None
    return top, float(np.median(cs)), float(np.median(ws))


def measure():
    C = clip_block()
    N = n_frames()
    os.makedirs(CACHE, exist_ok=True)
    t0 = time.time()
    rgbs, grays, alphas = [], [], []
    for rgb, a in zip(reader(P('assets', 'aroll.mp4'), HW, HH), reader(P('assets', 'subject.webm'), HW, HH, alpha=True)):
        rgbs.append(rgb.copy())
        grays.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
        alphas.append(a.copy())
    if len(rgbs) != N:
        sys.exit(f'read {len(rgbs)} frames of a-roll + cutout, clip.json says {N}: remake the slot (cutout missing or short)')
    mats, ref, weak = track(grays, alphas)
    corners = np.array([[0, 0, 1], [HW, 0, 1], [0, HH, 1], [HW, HH, 1], [HW / 2, HH / 2, 1]], np.float64).T
    drift = max(float(np.abs((m @ corners)[:2] / (m @ corners)[2] - corners[:2]).max()) for m in mats) * 2
    still = drift < 4.0               # a tripod still measures 1 to 3 px of track noise over a few seconds
    lost = sum(1 for a in alphas if (a > 128).sum() < 400)
    if drift > 300 or weak > N * 0.25:
        sys.exit(f'DECLINE: the camera moves too much in this slot ({drift:.0f} px, {weak} frames it could not follow): the print '
                 'cannot stay stuck to the wall. Use a steadier stretch (tripod, or a phone held fairly still).')
    if lost > N * 0.2:
        sys.exit('DECLINE: you are out of the shot (or the cutout lost you) for a fifth of this slot. Pick a stretch where you stay in frame.')
    if still:
        mats = [np.eye(3) for _ in mats]
    # clean plate of the room in the reference frame: the room wherever he is not, averaged over the slot
    acc = np.zeros((HH, HW, 3), np.float32)
    cnt = np.zeros((HH, HW), np.float32)
    pers = np.zeros((HH, HW), np.uint8)
    pers_q = np.zeros((N, HH // 2, HW // 2), np.uint8)        # where he is, frame by frame (reference frame, quarter size)
    heads = []
    for f in range(N):
        inv = np.linalg.inv(mats[f])[:2]
        free = (cv2.dilate((alphas[f] > 6).astype(np.uint8), ell(15)) == 0).astype(np.float32)
        if not still:
            img = cv2.warpAffine(rgbs[f], inv, (HW, HH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            free = cv2.warpAffine(free, inv, (HW, HH), flags=cv2.INTER_NEAREST, borderValue=0)
            al = cv2.warpAffine(alphas[f], inv, (HW, HH), flags=cv2.INTER_LINEAR)
        else:
            img, al = rgbs[f], alphas[f]
        acc += img.astype(np.float32) * free[..., None]
        cnt += free
        pers = np.maximum(pers, al)
        pers_q[f] = cv2.resize(al, (HW // 2, HH // 2), interpolation=cv2.INTER_AREA)
        h = head_of(al)
        if h:
            heads.append(h)
    seen = cnt >= 3
    plate = np.zeros((HH, HW, 3), np.uint8)
    plate[seen] = (acc[seen] / cnt[seen][:, None]).clip(0, 255).astype(np.uint8)
    q = cv2.resize(plate, (HW // 2, HH // 2), interpolation=cv2.INTER_AREA)
    qh = cv2.resize((~seen).astype(np.uint8) * 255, (HW // 2, HH // 2), interpolation=cv2.INTER_NEAREST)
    fill = cv2.resize(cv2.inpaint(q, qh, 5, cv2.INPAINT_TELEA), (HW, HH), interpolation=cv2.INTER_CUBIC)
    plate[~seen] = fill[~seen]
    wall, wstat = wall_map(plate, ~seen)
    person = (pers > 30).astype(np.uint8) * 255

    # his head (full-size px, reference frame): highest point he reaches, median centre and width
    if not heads:
        sys.exit('no person found in assets/subject.webm: this effect needs the speaker cut out (remake the slot without --no-cutout)')
    hs = np.array(heads)
    head = dict(top=float(hs[:, 0].min() * 2), top_med=float(np.median(hs[:, 0]) * 2), cx=float(np.median(hs[:, 1]) * 2),
                w=float(np.median(hs[:, 2]) * 2))
    row = (person[int(1400 / 2)] > 0)
    span = (np.flatnonzero(row)[-1] - np.flatnonzero(row)[0]) * 2 / W if row.any() else 0
    framing = 'close' if head['w'] > 330 or span > 0.85 else 'wide' if head['w'] < 130 else 'medium'
    side = 'centre' if 380 <= head['cx'] <= 700 else ('left' if head['cx'] < 380 else 'right')

    vp, lines = keystone(plate, person) if C.get('KEYSTONE', 'auto') == 'auto' else (C.get('KEYSTONE'), [])
    wall_full = cv2.resize(wall, (W, H), interpolation=cv2.INTER_LINEAR)
    person_full = cv2.resize(person, (W, H), interpolation=cv2.INTER_NEAREST)
    open_wall = wall_full * (person_full == 0)
    open_wall[1470:] = 0
    frac = float(open_wall.mean())
    mode = C.get('PRINT_MODE', 'auto')
    if mode == 'auto':
        mode = 'lift' if wstat['L'] < 32 else 'multiply'
    cv2.imwrite(os.path.join(CACHE, 'plate.png'), cv2.resize(plate, (W, H), interpolation=cv2.INTER_CUBIC)[..., ::-1])
    cv2.imwrite(os.path.join(CACHE, 'wall.png'), (wall_full * 255).round().astype(np.uint8))
    cv2.imwrite(os.path.join(CACHE, 'person.png'), person_full)
    np.save(os.path.join(CACHE, 'track.npy'), np.array([full_res(m) for m in mats]))
    np.save(os.path.join(CACHE, 'person_q.npy'), pers_q)
    ms = dict(frames=N, ref=ref, still=still, drift_px=round(drift, 1), weak_track_frames=weak, framing=framing,
              side=side, head={k: round(v, 1) for k, v in head.items()}, shoulder_span=round(span, 2),
              wall_fraction=round(frac, 3), wall=wstat, print_mode=mode,
              keystone=None if vp is None else [round(vp[0], 1), round(vp[1], 1)], vertical_lines=len(lines))
    json.dump(ms, open(P('work', 'measure.json'), 'w'), indent=1)

    print(f'camera: {"still" if still else "handheld"} (drift {drift:.1f} px over the slot' +
          (f', {weak} frames with a weak track' if weak else '') + ')' +
          ('' if still else ': the print is pinned to the wall by the track'))
    print(f'framing: {framing} (head {head["w"]:.0f} px wide, top at y {head["top"]:.0f}, centre x {head["cx"]:.0f}, {side})')
    print(f'wall: {frac * 100:.0f}% of the frame is open plain wall (brightness {wstat["L"]:.0f}/100) -> print mode "{mode}"' +
          (' (dark wall: the print is lifted in, not multiplied)' if mode == 'lift' else ''))
    print('perspective: ' + (f'keystone from {len(lines)} vertical lines, they meet at ({vp[0]:.0f}, {vp[1]:.0f})'
                             if vp is not None else f'flat on ({len(lines)} vertical lines, not enough lean to tilt the wall)'))
    if frac < 0.06:
        sys.exit(f'DECLINE: this needs some plain wall behind you; this clip has almost none ({frac * 100:.0f}% of the frame). '
                 'Use another effect here.')
    lay = layout(C, ms, verbose=True)
    preview(plate, wall_full, person_full, lines, lay, head)
    print(f'measure: {time.time() - t0:.0f} s. LOOK at work/measure.jpg (green = wall the print can use, blue = where he goes, '
          'yellow = the big-word block)')


def preview(plate, wall, person, lines, lay, head):
    img = cv2.resize(plate, (W, H), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    img = img * (1 - 0.45 * wall[..., None]) + np.float32([60, 200, 90]) * 0.45 * wall[..., None]
    pm = (person > 0)[..., None]
    img = np.where(pm, img * 0.5 + np.float32([60, 110, 255]) * 0.5, img).clip(0, 255).astype(np.uint8)
    img = np.ascontiguousarray(img)
    for x1, y1, x2, y2, _ in lines:
        cv2.line(img, (int(x1), int(y1)), (int(x2), int(y2)), (255, 40, 40), 3)
    cv2.rectangle(img, SAFE_BOX[:2], SAFE_BOX[2:], (255, 0, 255), 2)
    cv2.rectangle(img, (980, 1155), (1080, 1470), (255, 0, 255), 2)
    if lay and lay.get('quad') is not None:
        cv2.polylines(img, [np.int32(lay['quad'])], True, (255, 230, 0), 5)
    cv2.line(img, (int(head['cx'] - head['w'] / 2), int(head['top'])), (int(head['cx'] + head['w'] / 2), int(head['top'])), (0, 255, 255), 3)
    cv2.imwrite(P('work', 'measure.jpg'), cv2.resize(img, (540, 960), interpolation=cv2.INTER_AREA)[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 88])


# ------------------------------------------------------------------------------------------------------- hero layout
def hero_words(C):
    return [(int(f), cased(w, C.get('CASE', 'upper'))) for f, w in C.get('HERO', [])]


def hero_shapes(C):
    """Each big word drawn once, large: masks the block is built from."""
    font = load_font(C['FONT'], C['WEIGHT'], 400)
    return [word_mask(w, font, 0.0, C.get('BOLDEN', 0.0)) for _, w in hero_words(C)]


def block_size(masks, mode, bw):
    """(width, height, [(x, y, w, h) per word]) of the word block at block width bw (px)."""
    if mode == 'stack':
        gap = 0.0625 * bw
        y, boxes = 0.0, []
        h0 = bw * masks[0].shape[0] / masks[0].shape[1]
        for m in masks:
            h = min(bw * m.shape[0] / m.shape[1], 1.4 * h0)      # a short word (OUT) is not blown up past 1.4x the first
            boxes.append((0.0, y, h * m.shape[1] / m.shape[0], h))
            y += h + gap
        return bw, y - gap, boxes
    cap = max(m.shape[0] for m in masks)
    ws = [m.shape[1] * 1.0 for m in masks]
    sp = 0.28 * cap
    total = sum(ws) + sp * (len(ws) - 1)
    k = bw / total
    x, boxes = 0.0, []
    for m, w in zip(masks, ws):
        boxes.append((x, (cap - m.shape[0]) * k, w * k, m.shape[0] * k))
        x += (w + sp) * k
    return bw, cap * k, boxes


def letter_kernel(letter):
    """Size of the thinnest thing on the wall that may hide part of a big word: half a letter (35 to 81 px)."""
    return (int(min(max(0.5 * letter, 35), 81)) // 8) * 8 + 1


def safe_mask():
    m = np.zeros((H, W), np.uint8)
    x0, y0, x1, y1 = SAFE_BOX
    m[y0 + 14:y1 - 14, x0 + 14:x1 - 14] = 1
    m[1155 - 14:, 980 - 14:] = 0
    return m


def layout(C, ms, verbose=False):
    """Where the big words go, in wall-plane px: the biggest block that sits on open wall, inside the safe zone, clear of
    everywhere he goes, as close to his head as it can. None when there are no big words or no room."""
    if not C.get('HERO'):
        return None
    masks = hero_shapes(C)
    Hp = plane_h(ms['keystone'])
    Hi = np.linalg.inv(Hp)
    size = (W + 2 * MG, H + 2 * MG)
    wall = cv2.imread(os.path.join(CACHE, 'wall.png'), 0).astype(np.float32) / 255
    # where he goes while the big words are up (not before: a gesture during the print does not matter)
    pq = np.load(os.path.join(CACHE, 'person_q.npy'))
    f0 = max(0, min(f for f, _ in C['HERO']) - 3)
    f1 = len(pq) if C.get('HOLD_TO_END') else min(len(pq), (C.get('OUT_FRAME') or (C.get('CLEAR_FRAME') or max(f for f, _ in C['HERO']) + 32) + 14) + 1)
    person = cv2.resize((pq[f0:f1].max(0) > 30).astype(np.uint8) * 255, (W, H), interpolation=cv2.INTER_LINEAR)
    margin = int(round(max(12, (0.09 if ms['framing'] == 'close' else 0.04) * ms['head']['w'])))
    person = cv2.dilate(person, ell(2 * margin + 1))
    notwall_p = cv2.warpPerspective((wall < 0.5).astype(np.uint8), Hi, size, flags=cv2.INTER_NEAREST)
    free_p = cv2.warpPerspective(((person == 0).astype(np.uint8) * safe_mask()), Hi, size, flags=cv2.INTER_NEAREST)
    pp = cv2.warpPerspective((person > 0).astype(np.uint8) | (1 - safe_mask()), Hi, size, flags=cv2.INTER_NEAREST, borderValue=1)
    I_p = cv2.integral(pp.astype(np.float32))
    cache = {}

    def I_ok_for(letter):
        # the block must sit clear of solid things (a shelf post, a bracket, a frame, the plant) that would hide part of
        # a letter. Things thinner than half a letter are painted over (same rule as the paint itself, see hero_ok)
        k = letter_kernel(letter)
        if k not in cache:
            things = cv2.morphologyEx(notwall_p, cv2.MORPH_OPEN, ell(k))
            cache[k] = cv2.integral(((1 - things) * free_p).astype(np.float32))
        return cache[k]
    hx, hy = MG + ms['head']['cx'], MG + ms['head']['top_med'] + 0.6 * ms['head']['w']
    hb = C.get('HERO_BOX')
    tuck = 0.0 if ms['framing'] == 'close' else 0.02
    modes = [C.get('HERO_LAYOUT', 'auto')] if C.get('HERO_LAYOUT', 'auto') != 'auto' else ['stack', 'line']
    if len(masks) == 1:
        modes = ['line']
    best = None
    for mode in modes:
        if hb:
            x, y, bw = hb
            bw_, bh, boxes = block_size(masks, mode, bw)
            cand = (x + MG, y + MG, bw, bh, boxes)
        else:
            cand = None
            # never louder than the demo: the block is at most about 2.5 head widths (stack) or 4.6 (line) wide
            top = min((0.40 if mode == 'stack' else 0.84) * W, (2.5 if mode == 'stack' else 4.6) * ms['head']['w'])
            low = min((0.19 if mode == 'stack' else 0.30) * W, 0.6 * top)
            bw = top
            while bw >= low and cand is None:
                _, bh, boxes = block_size(masks, mode, bw)
                bwi, bhi = int(bw), int(bh)
                if bhi < size[1] and bwi < size[0]:
                    I_ok = I_ok_for(min(b[3] for b in boxes))
                    A = I_ok[bhi:, bwi:] - I_ok[:-bhi, bwi:] - I_ok[bhi:, :-bwi] + I_ok[:-bhi, :-bwi]
                    B = I_p[bhi:, bwi:] - I_p[:-bhi, bwi:] - I_p[bhi:, :-bwi] + I_p[:-bhi, :-bwi]
                    good = (A >= 0.995 * bwi * bhi) & (B <= tuck * bwi * bhi)     # may tuck a corner behind him (not on a close-up)
                    if good.any():
                        ys, xs = np.nonzero(good)
                        d = np.hypot(xs + bwi / 2 - hx, (ys + bhi / 2 - hy) * 1.3)
                        i = int(np.argmin(d))
                        s = 0.92                               # breathing room: shrink about the block centre
                        cx, cy = xs[i] + bwi / 2, ys[i] + bhi / 2
                        _, bh2, boxes2 = block_size(masks, mode, bw * s)
                        cand = (cx - bw * s / 2, cy - bh2 / 2, bw * s, bh2, boxes2)
                bw *= 0.95
        if cand:
            letter = min(b[3] for b in cand[4])
            if verbose:
                print(f'big words "{mode}": block {cand[2]:.0f} x {cand[3]:.0f} px, smallest letter height {letter:.0f} px')
            if best is None or letter > best[0] * 1.08:
                best = (letter, mode, cand)
    if best is None:
        if verbose:
            print('big words: NO open wall big enough near him -> print only. Caption the big words in the main reel '
                  '(or set HERO_BOX by hand).')
        return None
    letter, mode, (x, y, bw, bh, boxes) = best
    quad = cv2.perspectiveTransform(np.float32([[[x, y], [x + bw, y], [x + bw, y + bh], [x, y + bh]]]), Hp)[0]
    if verbose:
        print(f'big words: "{mode}" layout at x {quad[:, 0].min():.0f} to {quad[:, 0].max():.0f}, y {quad[:, 1].min():.0f} to '
              f'{quad[:, 1].max():.0f} (letters {letter:.0f} px tall)')
    return dict(mode=mode, x=x, y=y, bw=bw, bh=bh, boxes=boxes, quad=quad, letter=letter)


# --------------------------------------------------------------------------------------------------------- the scene
def paint_maps(mask, x, y, w, h, shape, seed, shade_px, halo_px):
    """One painted word on the plane canvas: fill (brush edge, streaky cover), block shade, keep-clear halo."""
    m = cv2.resize(mask, (max(1, int(round(w * 2))), max(1, int(round(h * 2)))), interpolation=cv2.INTER_AREA)
    pad = int(halo_px * 2.5 + shade_px + 20)
    x0, y0 = int(np.floor(x)) - pad, int(np.floor(y)) - pad
    cw, ch = int(w) + 2 * pad + 2, int(h) + 2 * pad + 2
    big = np.zeros((ch * 2, cw * 2), np.float32)
    ox, oy = int(round((x - x0) * 2)), int(round((y - y0) * 2))
    big[oy:oy + m.shape[0], ox:ox + m.shape[1]] = m[:big.shape[0] - oy, :big.shape[1] - ox] / 255.0
    c = cv2.resize(big, (cw, ch), interpolation=cv2.INTER_AREA)
    n1, n2 = noise(c.shape, 5, seed) - .5, noise(c.shape, 17, seed + 7) - .5
    fill = sstep((cv2.GaussianBlur(c, (0, 0), 0.8) + n1 * 0.12 + n2 * 0.07 - 0.36) / 0.30)
    streak = cv2.resize(noise((c.shape[0] // 3 + 2, c.shape[1] // 30 + 2), 2, seed + 3), (c.shape[1], c.shape[0]),
                        interpolation=cv2.INTER_CUBIC)
    cover = 0.93 + 0.05 * noise(c.shape, 23, seed + 5) - 0.05 * sstep((streak - 0.62) / 0.3)
    d = max(2, int(round(shade_px)))
    solid = (cv2.GaussianBlur(c, (0, 0), 0.6) > 0.5).astype(np.float32)
    ext = cv2.dilate(solid, np.eye(d + 1, dtype=np.uint8), anchor=(d, d))
    ext = cv2.GaussianBlur(ext, (0, 0), 0.7)
    shade = np.clip(ext - fill, 0, 1)
    hk = int(halo_px) * 2 + 1
    halo = cv2.GaussianBlur(cv2.dilate(np.maximum(solid, ext), ell(hk)), (0, 0), halo_px * 0.45)
    sl = (slice(max(y0, 0), min(y0 + ch, shape[0])), slice(max(x0, 0), min(x0 + cw, shape[1])))
    csl = (slice(sl[0].start - y0, sl[0].stop - y0), slice(sl[1].start - x0, sl[1].stop - x0))
    fy, fx = np.where(fill[csl] > 0.3)
    return dict(sl=sl, fill=np.ascontiguousarray((fill * cover)[csl]), shade=np.ascontiguousarray(shade[csl]),
                halo=np.ascontiguousarray(halo[csl]),
                center=((fx.min() + fx.max()) / 2.0, (fy.min() + fy.max()) / 2.0))


class Scene:
    def __init__(self):
        C = self.C = clip_block()
        ms = self.ms = json.load(open(P('work', 'measure.json')))
        self.N = ms['frames']
        self.track = np.load(os.path.join(CACHE, 'track.npy'))
        self.Hp = plane_h(ms['keystone'])
        Hi = np.linalg.inv(self.Hp)
        self.size = (W + 2 * MG, H + 2 * MG)
        shape = (self.size[1], self.size[0])
        wall = cv2.imread(os.path.join(CACHE, 'wall.png'), 0).astype(np.float32) / 255
        plate = cv2.imread(os.path.join(CACHE, 'plate.png'))[..., ::-1]
        wall_p = cv2.warpPerspective(wall, Hi, self.size, flags=cv2.INTER_LINEAR)
        # things on the wall stay in front of the big words too, but small specks (a switch, a nail) do not cut letters
        case = C.get('CASE', 'upper')
        # ---- timing
        self.t_print = max(C['PRINT_FRAME'], 2) / FPS
        hw = hero_words(C)
        self.lay = layout(C, ms) if hw else None
        # only solid things (a frame, a lamp, a shelf) stay in front of the big words. Anything thinner than about half a
        # letter (trim, a cord, the room's corner line) is opened away so it never cuts a letter in two
        k = letter_kernel(self.lay['letter']) if self.lay else 35
        things = cv2.morphologyEx((wall_p < 0.5).astype(np.uint8), cv2.MORPH_OPEN, ell(k))
        hero_ok = cv2.GaussianBlur(1 - things.astype(np.float32), (0, 0), 1.0)
        last_hero = max([f for f, _ in hw], default=C['PRINT_FRAME'])
        clear = C.get('CLEAR_FRAME') if C.get('CLEAR_FRAME') is not None else last_hero + 32
        out = C.get('OUT_FRAME') if C.get('OUT_FRAME') is not None else clear + 14
        if not C.get('HOLD_TO_END'):
            out = min(out, self.N - 12)
            clear = min(clear, out - 6)
        self.t_clear, self.t_out = clear / FPS, out / FPS
        self.hold = bool(C.get('HOLD_TO_END'))
        # ---- the print
        head_w = ms['head']['w']
        size = int(C.get('PRINT_SIZE') or min(max(0.21 * head_w, 30), 52))
        font = load_font(C.get('PRINT_FONT', 'Inter Tight'), C.get('PRINT_WEIGHT', 900), size * 2)
        m = word_mask(cased(C['PRINT_TEXT'], case), font, 0.05)
        m = cv2.resize(m, (max(1, m.shape[1] // 2), max(1, m.shape[0] // 2)), interpolation=cv2.INTER_AREA)
        c = np.zeros(shape, np.float32)
        tmap = np.full(shape, 99.0, np.float32)
        rng = np.random.default_rng(11)
        gap, pitch = 1.15 * size, 1.5 * size
        step = m.shape[1] + gap
        ox, oy = MG + ms['head']['cx'], MG + ms['head']['top_med'] + 0.5 * head_w
        far = np.hypot(*shape) * 0.55
        y, row = pitch * 0.35, 0
        while y + m.shape[0] < shape[0]:
            x = -step * (0.5 if row % 2 else 0.0) - (step * 0.13 * row) % step
            while x < shape[1]:
                xi, yi = int(round(x)), int(round(y))
                if xi >= 0 and xi + m.shape[1] < shape[1]:
                    c[yi:yi + m.shape[0], xi:xi + m.shape[1]] = np.maximum(c[yi:yi + m.shape[0], xi:xi + m.shape[1]], m / 255.0)
                    dist = np.hypot(xi + m.shape[1] / 2 - ox, yi + m.shape[0] / 2 - oy)
                    g = int(gap * 0.45)
                    tmap[max(yi - g, 0):yi + m.shape[0] + g, max(xi - g, 0):xi + m.shape[1] + g] = \
                        self.t_print + 0.42 * min(dist / far, 1.0) + rng.random() * 0.07
                x += step
            y += pitch
            row += 1
        ink = 0.86 + 0.14 * noise(shape, 13, 5)
        self.wp = cv2.GaussianBlur(c * ink, (0, 0), 0.5) * wall_p
        self.wp_t = tmap
        self.mode = ms['print_mode']
        self.strength = 0.72 if ms['framing'] == 'close' else 0.86     # bigger letters on a selfie: a lighter hand
        self.tone = hexrgb(C.get('PRINT_INK', '#6F8263')) / 255
        # ---- the big words
        self.words = []
        if self.lay:
            lay = self.lay
            masks = hero_shapes(C)
            shade_px, halo_px = 0.023 * lay['bw'] if lay['mode'] == 'stack' else 0.06 * lay['letter'], \
                0.057 * lay['bw'] if lay['mode'] == 'stack' else 0.15 * lay['letter']
            for i, ((f, w), mk, (bx, by, bw, bh)) in enumerate(zip(hw, masks, lay['boxes'])):
                pm = paint_maps(mk, lay['x'] + bx, lay['y'] + by, bw, bh, shape, 3 + i, shade_px, halo_px)
                pm['fill'] *= hero_ok[pm['sl']]
                pm['t_in'] = (f - 1.2) / FPS
                self.words.append(pm)
            # light the paint like the wall around it
            q = lay['quad']
            x0, x1 = int(max(q[:, 0].min(), 0)), int(min(q[:, 0].max(), W))
            y0, y1 = int(max(q[:, 1].min(), 0)), int(min(q[:, 1].max(), H))
            wl = cv2.resize(wall, (W, H))[y0:y1, x0:x1] > 0.5
            pl = lum(plate[y0:y1, x0:x1].astype(np.float32))
            self.l_ref = float(np.median(pl[wl])) if wl.any() else float(np.median(pl))
            self.bump_c = (float(q[:, 0].mean()), float(q[:, 1].mean()))
        self.t_first = min([w['t_in'] for w in self.words], default=99.0)
        self.accent, self.ink = hexrgb(C.get('ACCENT', '#FAE67A')), hexrgb(C.get('INK', '#14161C')) / 255
        self.shape = shape

    def marks(self):
        hw = hero_words(self.C)
        f_print = int(self.t_print * FPS)
        out = [f_print + 8] + [f + 2 for f, _ in hw] + [int(self.t_clear * FPS) - 4, int(self.t_out * FPS) + 3, self.N - 1]
        return sorted({min(max(f, 0), self.N - 1) for f in out})

    def word_state(self, w, t):
        u = (t - w['t_in']) / 0.11
        if u <= 0:
            return None
        cx, cy = w['center']
        size = (w['fill'].shape[1], w['fill'].shape[0])
        op, s, blur = 1.0, 1.0, 0.0
        if u < 1:                                   # lands: big, soft, faint -> exact size, sharp, solid
            e = 1 - (1 - u) ** 3
            s, op, blur = 1 + 0.30 * (1 - e), min(1.0, 0.30 + 1.1 * u), 9.0 * 0.30 * (1 - e)
        if not self.hold and t > self.t_out - 0.3:  # lifts off: fades, grows a touch, softens
            v = sstep((t - (self.t_out - 0.3)) / 0.3)
            op *= 1 - v
            s *= 1 + 0.04 * v
            blur += 3.0 * v
        clear = sstep((t - w['t_in']) / 0.2) * (1.0 if self.hold else 1 - sstep((t - (self.t_out - 0.3)) / 0.3))
        if op <= 0.002:
            return None
        if s == 1.0 and blur == 0.0:
            return w['fill'], w['shade'], op, clear
        M = np.float32([[s, 0, cx * (1 - s)], [0, s, cy * (1 - s)]])
        res = []
        for k in ('fill', 'shade'):
            m = cv2.warpAffine(w[k], M, size, flags=cv2.INTER_LINEAR)
            res.append(cv2.GaussianBlur(m, (0, 0), 0.4 + blur) if blur > 0.05 else m)
        return res[0], res[1], op, clear

    def frame(self, f, plate, alpha, guide=False):
        t = f / FPS
        out = plate.astype(np.float32)
        if t <= self.t_print and not self.words:
            return plate
        Hf = self.track[f] @ self.Hp
        # print alpha on the plane
        a = None
        if t > self.t_print:
            a = self.wp * sstep((t - self.wp_t) / 0.10)
            if t > self.t_clear:
                a *= 1 - sstep((t - (self.t_clear + self.wp_t - self.t_print)) / 0.10)
            k = self.strength * (1 - 0.5 * sstep((t - self.t_first) / 0.45))
            a = a * k
        fill_p = shade_p = None
        for w in self.words:
            st = self.word_state(w, t)
            if st is None:
                continue
            fl, sh, op, clear = st
            sl = w['sl']
            if a is not None:
                a[sl] *= 1 - w['halo'] * clear
            if fill_p is None:
                fill_p = np.zeros(self.shape, np.float32)
                shade_p = np.zeros(self.shape, np.float32)
            fill_p[sl] = np.maximum(fill_p[sl], fl * op)
            shade_p[sl] = np.maximum(shade_p[sl], sh * op)
        if a is None and fill_p is None:
            return plate
        gate = 1 - np.clip((alpha.astype(np.float32) - 46) / (232 - 46), 0, 1)
        if a is not None and a.max() > 0.002:
            ao = cv2.warpPerspective(a, Hf, (W, H), flags=cv2.INTER_LINEAR) * gate
            if self.mode == 'lift':
                out += (ao * 0.6)[..., None] * (self.tone * 255 - out)
            else:
                out *= 1 - ao[..., None] * (1 - self.tone)
        if fill_p is not None:
            so = cv2.warpPerspective(shade_p, Hf, (W, H), flags=cv2.INTER_LINEAR) * gate
            fo = cv2.warpPerspective(fill_p, Hf, (W, H), flags=cv2.INTER_LINEAR) * gate
            # the paint takes the wall's light, not the colour of a dark bracket or cord under a letter: brightest
            # nearby wall (max filter at quarter size), then softened
            q = cv2.resize(lum(plate.astype(np.float32)), (W // 4, H // 4), interpolation=cv2.INTER_AREA)
            q = cv2.GaussianBlur(cv2.dilate(q, ell(7)), (0, 0), 3.0)
            base_l = cv2.resize(q, (W, H), interpolation=cv2.INTER_LINEAR)
            Lr = np.clip(base_l / max(self.l_ref, 1), 0.45, 1.10)[..., None]
            out *= 1 - (so * 0.90)[..., None] * (1 - self.ink)
            out = out * (1 - fo[..., None]) + self.accent * Lr * fo[..., None]
        bump = 0.0
        for fh, _ in hero_words(self.C):
            tau = t - (fh + 1) / FPS
            if tau >= 0:
                bump += self.C.get('BUMP', 0.012) * min(tau / 0.034, 1.0) * np.exp(-max(tau - 0.034, 0) / 0.16) * \
                        (1.0 if fh == hero_words(self.C)[0][0] else 1.4)
        if bump > 0.0004 and self.words:
            cx, cy = self.bump_c
            s = 1 + bump
            out = cv2.warpAffine(out, np.float32([[s, 0, cx * (1 - s)], [0, s, cy * (1 - s)]]), (W, H),
                                 flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        out = out.clip(0, 255).astype(np.uint8)
        if guide:
            cv2.rectangle(out, SAFE_BOX[:2], SAFE_BOX[2:], (255, 0, 255), 2)
            cv2.rectangle(out, (980, 1155), (1080, 1470), (255, 0, 255), 2)
        return out


# ------------------------------------------------------------------------------------------------- bake (all cores)
_S = None


def _init():
    global _S
    cv2.setNumThreads(1)
    _S = Scene()


def _work(job):
    f, plate, alpha = job
    return f, _S.frame(f, plate, alpha).tobytes()


def jobs():
    for f, (plate, alpha) in enumerate(zip(reader(P('assets', 'aroll.mp4'), W, H), reader(P('assets', 'subject.webm'), W, H, alpha=True))):
        yield f, plate, alpha


def bake():
    import multiprocessing as mp
    t0 = time.time()
    sc = Scene()                      # fail early (fonts, measure) before the pool starts
    N = sc.N
    print(f'print "{sc.C["PRINT_TEXT"]}" from frame {int(sc.t_print * FPS)}, clears {int(sc.t_clear * FPS)}; big words ' +
          (', '.join(f'{w}@{f}' for f, w in hero_words(sc.C)) if sc.words else 'none') +
          (f', gone by {int(sc.t_out * FPS)}' if not sc.hold else ', held to the last frame'))
    json.dump({'marks': sc.marks()}, open(P('work', 'marks.json'), 'w'))
    del sc
    nw = int(os.environ.get('WORKERS', '0')) or max(1, min(mp.cpu_count() - 1, 6))
    w = writer(P('assets', 'fx.mp4'))
    n = 0
    with mp.Pool(nw, initializer=_init) as pool:
        for f, buf in pool.imap(_work, jobs(), chunksize=2):
            w.stdin.write(buf)
            n += 1
            if f % 30 == 0:
                print('frame', f, flush=True)
    w.stdin.close()
    w.wait()
    if n != N:
        sys.exit(f'!! baked {n} frames, clip.json says {N}')
    dt = time.time() - t0
    json.dump({'seconds_per_slot_second': round(dt / (N / FPS), 1)}, open(P('work', 'bake_time.json'), 'w'))
    print(f'wrote assets/fx.mp4: {n} frames in {dt:.0f} s ({dt / (N / FPS):.1f} s per slot second, {nw} workers)')


def stills(frames):
    os.makedirs(P('work', 'stills'), exist_ok=True)
    sc = Scene()
    guide = os.environ.get('SAFE', '0') == '1'
    want = sorted(set(frames)) or sc.marks()
    tiles = []
    for f, plate, alpha in jobs():
        if f in want:
            out = sc.frame(f, plate, alpha, guide)
            cv2.imwrite(P('work', 'stills', f'f{f:03d}.jpg'), out[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 92])
            t = cv2.resize(out, (270, 480), interpolation=cv2.INTER_AREA)
            cv2.putText(t, f'f{f}', (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            tiles.append(t)
        if f >= want[-1]:
            break
    for i in range(0, len(tiles), 6):
        cv2.imwrite(P('work', 'stills', f'sheet{i // 6 + 1}.jpg'), np.hstack(tiles[i:i + 6])[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 88])
    print('stills:', want, '-> work/stills/ (sheet*.jpg = 6 per sheet)')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'measure':
        measure()
    elif cmd == 'bake':
        bake()
    elif cmd == 'still':
        stills([int(a) for a in sys.argv[2:]])
    else:
        print(__doc__)
