"""paper-cut engine: torn paper sheets, crayon and pen marks, ransom-note letters, tape, the live hand-cut cutout and
the tear-away. Everything is driven by work/plan.json (written by build.py), seeded, so every frame is a pure function
of its frame number and the source frames: bake.py splits the frames over worker processes.

Colours are RGB here. No file paths of this machine: fonts come from the slot's assets/fonts (paths in the plan).
"""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
SAFE = dict(top=220, bottom=1470, side=35, right_low=(1155, 100))   # right_low: (from y, inset px)


def hexrgb(h):
    h = h.lstrip('#')
    return np.array([int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)], np.float32)


BASE = dict(kraft='C29B6C', cream='FFF8EF', yellow='FAE67A', graph='F7F6F1', black='14161C', white='FCFAF4',
            crimson='C8222F', cobalt='2B49C2', cobalt_soft='6F8BE6', ink='1B1E2A', news='E4E1D6', core='F8F4EA',
            tape='E9DBB0', shadow='20160F', gridline='7FA6D8', kraftcore='E6CFA8')
COL = {k: hexrgb(v) for k, v in BASE.items()}
# ransom scraps: (paper, ink). 'black' is the INK colour, 'crimson' ACCENT, 'cobalt' ACCENT2, 'yellow' HIGHLIGHT
BASE_SCRAPS = [('white', 'black'), ('black', 'white'), ('yellow', 'black'), ('crimson', 'white'), ('news', 'black'),
          ('cobalt', 'white'), ('black', 'yellow'), ('white', 'crimson'), ('kraft', 'black')]
SCRAPS = list(BASE_SCRAPS)


def set_colours(c):
    """c: {'black': [r,g,b], 'crimson': ..., 'cobalt': ..., 'yellow': ...} from the plan (the CLIP colours)."""
    for k, v in (c or {}).items():
        COL[k] = np.array(v, np.float32)
    COL['ink'] = COL['black'] * 0.9 + np.array([27, 30, 42], np.float32) * 0.1
    COL['cobalt_soft'] = COL['cobalt'] + 0.30 * (255 - COL['cobalt'])
    lum = lambda k: float(COL[k] @ np.float32([0.2126, 0.7152, 0.0722]))
    SCRAPS[:] = [(bg, "black" if (fg == "white" and lum(bg) > 150) else fg) for bg, fg in BASE_SCRAPS
                 if not (bg == "white" and lum(fg) > 170)]       # light brand colours get dark ink


def smooth_noise(h, w, scale, rng):
    sh, sw = max(2, int(h / scale) + 3), max(2, int(w / scale) + 3)
    n = rng.standard_normal((sh, sw)).astype(np.float32)
    return cv2.resize(n, (w, h), interpolation=cv2.INTER_CUBIC)


def aff(scale=1.0, rot=0.0, cx=0.0, cy=0.0, tx=0.0, ty=0.0):
    """p -> R*s*(p - c) + c + t (rot in degrees, positive = clockwise on screen)."""
    a = math.radians(rot)
    c, s = math.cos(a) * scale, math.sin(a) * scale
    return np.array([[c, -s, cx - c * cx + s * cy + tx], [s, c, cy - s * cx - c * cy + ty]], np.float32)


def chain(M2, M1):
    """apply M1 first, then M2."""
    A = np.vstack([M2, [0, 0, 1]]) @ np.vstack([M1, [0, 0, 1]])
    return A[:2].astype(np.float32)


def blit(canvas, spr, M, opacity=1.0, blur=None):
    """spr: float32 premultiplied (rgb 0..255 * a, a 0..1), or alpha only (= a shadow). M maps sprite px -> canvas."""
    h, w = spr.shape[:2]
    c = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], np.float32) @ M.T
    pad = 2 + (max(blur) if blur else 0)
    x0, y0 = int(max(0, math.floor(c[:, 0].min()) - pad)), int(max(0, math.floor(c[:, 1].min()) - pad))
    x1, y1 = int(min(W, math.ceil(c[:, 0].max()) + pad)), int(min(H, math.ceil(c[:, 1].max()) + pad))
    if x1 <= x0 or y1 <= y0:
        return
    M2 = M.copy()
    M2[:, 2] -= (x0, y0)
    roi = cv2.warpAffine(spr, M2, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                         borderValue=0)
    if blur and (blur[0] > 1 or blur[1] > 1):
        roi = cv2.blur(roi, (max(1, blur[0]), max(1, blur[1])))
    if roi.ndim == 2:
        a = (roi * opacity)[..., None]
        canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - a) + COL['shadow'] * a
    else:
        a = roi[..., 3:4] * opacity
        canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - a) + roi[..., :3] * opacity


def shadow_of(alpha, sigma, pad):
    a = cv2.copyMakeBorder(alpha, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    return cv2.GaussianBlur(a, (0, 0), sigma)


# ---------------------------------------------------------------------------------------------------- paper sheets
def paper_tex(h, w, kind, rng):
    base = COL[kind]
    t = (1 + 0.022 * smooth_noise(h, w, 190, rng) + 0.009 * smooth_noise(h, w, 42, rng)
         + 0.006 * smooth_noise(h, w, 7, rng) + 0.012 * cv2.GaussianBlur(
             rng.standard_normal((h, w)).astype(np.float32), (0, 0), 0.7))
    if kind == 'kraft':
        yy = np.arange(h, dtype=np.float32)[:, None]
        t += 0.006 * np.sin(yy / 2.3 + 2.0 * smooth_noise(h, w, 120, rng))          # faint laid lines
        t += 0.022 * smooth_noise(h, w, 11, rng) + 0.02 * smooth_noise(h, w, 3, rng)
    img = base[None, None, :] * t[..., None]
    fl = np.zeros((h, w), np.float32)                                                # fibres
    n = int(h * w / (520 if kind == 'kraft' else 800))
    xs, ys = rng.uniform(0, w, n), rng.uniform(0, h, n)
    an, ln = rng.uniform(0, math.pi, n), rng.uniform(6, 34, n)
    val = rng.choice([-1.0, 1.0], n, p=[0.55, 0.45]) * rng.uniform(0.3, 1.0, n)
    for i in range(n):
        p1 = (int(xs[i] * 8), int(ys[i] * 8))
        p2 = (int((xs[i] + math.cos(an[i]) * ln[i]) * 8), int((ys[i] + math.sin(an[i]) * ln[i]) * 8))
        cv2.line(fl, p1, p2, float(val[i]), 1, cv2.LINE_AA, 3)
    img += cv2.GaussianBlur(fl, (0, 0), 0.6)[..., None] * (15.0 if kind == 'kraft' else 9.0)
    if kind == 'kraft':                                                              # darker flecks
        fk = (rng.random((h, w)) > 0.9993).astype(np.float32)
        fk = cv2.GaussianBlur(cv2.dilate(fk, np.ones((2, 3), np.uint8)), (0, 0), 0.8)
        img -= fk[..., None] * 55
    if kind == 'graph':
        g = np.zeros((h, w), np.float32)
        for x in range(0, w, 38):
            cv2.line(g, (x, 0), (x, h), 1.0 if (x // 38) % 5 == 0 else 0.5, 2 if (x // 38) % 5 == 0 else 1)
        for y in range(0, h, 38):
            cv2.line(g, (0, y), (w, y), 1.0 if (y // 38) % 5 == 0 else 0.5, 2 if (y // 38) % 5 == 0 else 1)
        g = cv2.GaussianBlur(g, (0, 0), 0.6)[..., None]
        img = img * (1 - 0.7 * g) + COL['gridline'] * 0.7 * g
    X, Y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    for _ in range(2):                                                               # two fold creases
        a = rng.uniform(0, math.pi)
        px, py = rng.uniform(0.25, 0.75) * w, rng.uniform(0.25, 0.75) * h
        d = (X - px) * math.cos(a) + (Y - py) * math.sin(a)
        img *= (1 + 0.045 * np.exp(-((d - 2.5) ** 2) / 9) - 0.055 * np.exp(-((d + 2.5) ** 2) / 9)
                + 0.012 * np.tanh(d / 160))[..., None]
    return np.clip(img, 0, 255)


def torn_alpha(inside, rng, rough=1.0):
    """inside: uint8 0/1 mask -> (alpha, printed); printed < alpha leaves the white fibre fringe of a tear."""
    h, w = inside.shape
    sdf = cv2.distanceTransform(inside, cv2.DIST_L2, 5) - cv2.distanceTransform(1 - inside, cv2.DIST_L2, 5)
    n = rough * (11 * smooth_noise(h, w, 64, rng) + 5 * smooth_noise(h, w, 15, rng)
                 + 2.4 * smooth_noise(h, w, 4.5, rng) + 0.9 * smooth_noise(h, w, 1.6, rng))
    alpha = np.clip(sdf + n + 0.5, 0, 1)
    wf = np.clip(8 + 6 * smooth_noise(h, w, 34, rng) + 3.5 * smooth_noise(h, w, 5, rng), 1.0, 22)
    wf *= np.clip(0.75 + 0.7 * smooth_noise(h, w, 230, rng), 0.12, 1.5)
    printed = np.clip(sdf + n - wf + 0.5, 0, 1)
    return alpha.astype(np.float32), printed.astype(np.float32)


def make_sheet(layer, idx, rng):
    poly = np.array(layer['poly'], np.float32)
    m = 70
    x0, y0 = np.floor(poly.min(0)) - m
    x1, y1 = np.ceil(poly.max(0)) + m
    w, h = int(x1 - x0), int(y1 - y0)
    inside = np.zeros((h, w), np.uint8)
    cv2.fillPoly(inside, [np.round(poly - (x0, y0)).astype(np.int32)], 1)
    alpha, printed = torn_alpha(inside, rng)
    tex = paper_tex(h, w, layer['kind'], rng)
    core = COL['core'] if layer['kind'] != 'kraft' else COL['kraftcore']
    corec = core[None, None, :] * (1 + 0.05 * smooth_noise(h, w, 2.2, rng))[..., None]
    col = tex * printed[..., None] + corec * (1 - printed[..., None])
    spr = np.dstack([col * alpha[..., None], alpha]).astype(np.float32)
    pad = 60
    return dict(spr=spr, sh=shadow_of(alpha, 17, pad), sh2=shadow_of(alpha, 4, pad), pad=pad, x0=float(x0),
                y0=float(y0), cx=w / 2, cy=h / 2, layer=layer, idx=idx)


def sheet_pose(sheet, f, tick, seed):
    L = sheet['layer']
    k = f - L['f']
    if k < 0:
        return None
    seq = [0.48, 0.10, -0.016, 0.0]
    u = seq[k] if k < len(seq) else 0.0
    up = 1.0 if k == 0 else (seq[k - 1] if k - 1 < len(seq) else 0.0)
    r = np.random.default_rng(seed * 131 + sheet['idx'] * 17 + tick // 2)
    jx, jy, jr = (r.uniform(-1.3, 1.3), r.uniform(-1.3, 1.3), r.uniform(-0.10, 0.10)) if k >= len(seq) else (0, 0, 0)
    M = aff(1 + 0.05 * abs(u), L['rot'] * u * 2 + jr, sheet['cx'], sheet['cy'],
            sheet['x0'] + L['frm'][0] * u + jx, sheet['y0'] + L['frm'][1] * u + jy)
    return M, (L['frm'][0] * (u - up), L['frm'][1] * (u - up)), abs(u)


def draw_sheets(canvas, sheets, f, tick, seed):
    for s in sheets:
        p = sheet_pose(s, f, tick, seed)
        if p is None:
            continue
        M, v, lift = p
        bl = (int(min(110, abs(v[0]) * 0.28)), int(min(110, abs(v[1]) * 0.28)))
        pad = s['pad']
        so = 1 + 3.5 * lift
        blit(canvas, s['sh'], chain(M, aff(tx=-pad + 12 * so, ty=-pad + 18 * so)), 0.40, bl)
        blit(canvas, s['sh2'], chain(M, aff(tx=-pad + 3, ty=-pad + 4)), 0.22, bl)
        blit(canvas, s['spr'], M, 1.0, bl)


# ---------------------------------------------------------------------------------------------------- pen + crayon
def resample(pts, step=6.0):
    pts = np.asarray(pts, np.float32)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    d = np.concatenate([[0], np.cumsum(seg)])
    n = max(2, int(d[-1] / step))
    t = np.linspace(0, d[-1], n)
    return np.stack([np.interp(t, d, pts[:, 0]), np.interp(t, d, pts[:, 1])], 1).astype(np.float32)


def mark_strokes(path, rng):
    """a path spec -> list of dense polylines. rng is FIXED per mark (the hand), the boil is per tick."""
    k = path[0]
    if k == 'zigzag':
        _, x0, y0, x1, y1, width, n = path
        a, b = np.array([x0, y0], np.float32), np.array([x1, y1], np.float32)
        ax = (b - a) / max(1e-3, np.linalg.norm(b - a))
        pr = np.array([-ax[1], ax[0]])
        pts = []
        for i in range(int(n) * 2 + 1):
            t = i / (n * 2)
            side = (1 if i % 2 else -1) * width * rng.uniform(0.72, 1.05)
            pts.append(a + (b - a) * (t + rng.uniform(-0.012, 0.012)) + pr * side + ax * side * 0.35)
        s = resample(pts, 7)
        return [cv2.blur(s.reshape(-1, 1, 2), (1, 5)).reshape(-1, 2)]
    if k == 'cross':
        _, cx, cy, r = path
        return [resample([(cx - r, cy - r * 0.9), (cx + r, cy + r)], 4),
                resample([(cx + r * 0.95, cy - r), (cx - r, cy + r * 0.85)], 4)]
    if k == 'loops':
        _, x0, y0, x1, y1, r, n = path
        t = np.linspace(0, n * 2 * math.pi, int(n * 36))
        u = t / t[-1]
        x = x0 + (x1 - x0) * u + r * 0.9 * np.sin(t)
        y = y0 + (y1 - y0) * u - r * np.cos(t) * (1 + 0.25 * np.sin(u * 9))
        return [np.stack([x, y], 1).astype(np.float32)]
    if k == 'stitch':
        _, x0, y0, x1, y1, n = path
        out = []
        for i in range(int(n)):
            u = (i + 0.5) / n
            cx, cy = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u + rng.uniform(-5, 5)
            sl = rng.uniform(-0.25, 0.25)
            out.append(resample([(cx - 9 + sl * 30, cy - 21), (cx + 9 - sl * 30, cy + 21)], 4))
        return out
    if k == 'star':
        _, cx, cy, r = path
        out = []
        for i in range(3):
            a = math.pi * i / 3 + 0.3
            out.append(resample([(cx - r * math.cos(a), cy - r * math.sin(a)),
                                 (cx + r * math.cos(a), cy + r * math.sin(a))], 4))
        return out
    if k == 'ellipse':
        _, cx, cy, rx, ry, rot = path
        t = np.linspace(-2.2, -2.2 + 2 * math.pi * 1.13, 150)
        grow = 1 + 0.035 * (t - t[0]) / (2 * math.pi)
        x, y = rx * np.cos(t) * grow, ry * np.sin(t) * grow
        a = math.radians(rot)
        return [np.stack([cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)],
                         1).astype(np.float32)]
    if k == 'underline':
        _, x0, y0, x1, y1 = path
        t = np.linspace(0, 1, 60)
        s1 = np.stack([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t + 5 * np.sin(t * math.pi)], 1)
        t2 = np.linspace(1, 0.12, 50)
        s2 = np.stack([x0 + (x1 - x0) * t2, y0 + 15 + (y1 - y0) * t2 - 3 * np.sin(t2 * math.pi)], 1)
        return [s1.astype(np.float32), s2.astype(np.float32)]
    raise ValueError(k)


def boil(stroke, rng, amp):
    n = len(stroke)
    m = max(3, n // 7 + 2)
    d = np.stack([np.interp(np.linspace(0, m - 1, n), np.arange(m), rng.standard_normal(m)) for _ in range(2)], 1)
    return stroke + d.astype(np.float32) * amp + rng.uniform(-1.0, 1.0, 2).astype(np.float32)


def draw_marks(canvas, marks, f, tick, grain, over, seed):
    for i, mk in enumerate(marks):
        if bool(mk.get('over')) != over or f < mk['f']:
            continue
        frac = min(1.0, (f - mk['f'] + 1) / mk['dur'])
        rng = np.random.default_rng(seed * 977 + i * 31 + tick)
        strokes = [boil(s, rng, mk['amp']) for s in mk['strokes']]
        total = sum(len(s) for s in strokes)
        left = int(total * frac)
        allp = np.concatenate(strokes)
        pad = mk['w'] + 4
        bx0, by0 = int(max(0, allp[:, 0].min() - pad)), int(max(0, allp[:, 1].min() - pad))
        bx1, by1 = int(min(W, allp[:, 0].max() + pad)), int(min(H, allp[:, 1].max() + pad))
        if bx1 <= bx0 or by1 <= by0:
            continue
        mask = np.zeros((by1 - by0, bx1 - bx0), np.uint8)
        for s in strokes:
            if left < 2:
                break
            p = s[:left] - (bx0, by0)
            left -= len(s)
            cv2.polylines(mask, [np.round(p * 8).astype(np.int32)], False, 255, mk['w'], cv2.LINE_AA, 3)
        if not mask.any():
            continue
        a = mask.astype(np.float32) / 255
        if mk['kind'] == 'crayon':
            ox, oy = int(rng.integers(0, 400)), int(rng.integers(0, 400))
            g = np.roll(grain, (oy, ox), (0, 1))[by0:by1, bx0:bx1]
            a = cv2.GaussianBlur(a, (0, 0), 1.0) * (0.16 + 0.84 * np.clip((g + 0.30) * 1.7, 0, 1))
            a *= mk.get('op', 0.9)
        else:
            a *= 0.93
        a = a[..., None]
        canvas[by0:by1, bx0:bx1] = canvas[by0:by1, bx0:bx1] * (1 - a) + COL[mk['col']] * a


# ---------------------------------------------------------------------------------------------------- ransom letters
_FONT_CACHE = {}


def load_font(spec, px):
    """spec = [path, weight]; variable fonts follow the weight, static faces stay what they are."""
    key = (spec[0], int(spec[1]), int(px))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    f = ImageFont.truetype(spec[0], int(px))
    try:
        vals = []
        for a in f.get_variation_axes():
            name = a['name'].decode() if isinstance(a['name'], bytes) else str(a['name'])
            v = spec[1] if name.lower().startswith('weight') else a['default']
            vals.append(max(a['minimum'], min(a['maximum'], v)))
        f.set_variation_by_axes(vals)
    except Exception:
        pass
    _FONT_CACHE[key] = f
    return f


def make_scrap(ch, h, font_spec, bg, fg, rng):
    S = 2
    f = load_font(font_spec, 200)
    l, t, r, b = f.getbbox(ch)
    if r - l < 2 or b - t < 2:                      # a glyph the face lacks: fall back to a capital-height box
        l, t, r, b = f.getbbox('H')
    fs = max(10, int(200 * (0.62 * h * S) / max(1, b - t)))
    f = load_font(font_spec, fs)
    l, t, r, b = f.getbbox(ch)
    gw, gh = r - l, b - t
    hh = h * S
    ww = int(max(gw + hh * rng.uniform(0.30, 0.46), hh * 0.60))
    m = int(hh * 0.12)
    im = Image.new('L', (ww + 2 * m, hh + 2 * m), 0)
    j = lambda: rng.uniform(-0.045, 0.045) * hh
    quad = [(m + j(), m + j()), (m + ww + j(), m + j()), (m + ww + j(), m + hh + j()), (m + j(), m + hh + j())]
    ImageDraw.Draw(im).polygon(quad, fill=255)
    gl = Image.new('L', im.size, 0)
    ImageDraw.Draw(gl).text((m + (ww - gw) / 2 - l + rng.uniform(-0.02, 0.02) * hh, m + (hh - gh) / 2 - t), ch,
                            font=f, fill=255)
    A = cv2.resize(np.asarray(im, np.float32) / 255, None, fx=1 / S, fy=1 / S, interpolation=cv2.INTER_AREA)
    G = cv2.resize(np.asarray(gl, np.float32) / 255, None, fx=1 / S, fy=1 / S, interpolation=cv2.INTER_AREA)
    sh, sw = A.shape
    tex = (1 + 0.035 * smooth_noise(sh, sw, 30, rng) + 0.022 * smooth_noise(sh, sw, 3, rng))[..., None]
    base = COL[bg][None, None, :] * tex
    if bg == 'news':                                      # faint print lines, like a magazine clipping
        ln = np.zeros((sh, sw), np.float32)
        for y in range(6, sh, 9):
            ln[y:y + 2, :] = 0.16 * (rng.random(sw) > 0.2)
        base = base * (1 - cv2.GaussianBlur(ln, (0, 0), 0.8)[..., None])
    if bg in ('yellow', 'crimson', 'cobalt') and rng.random() < 0.6:   # halftone dots, print feel
        X, Y = np.meshgrid(np.arange(sw, dtype=np.float32), np.arange(sh, dtype=np.float32))
        dots = (np.sin(X * 0.9 + Y * 0.5) * np.sin(Y * 0.9 - X * 0.5) > 0.55).astype(np.float32)
        base = base * (1 - 0.07 * cv2.GaussianBlur(dots, (0, 0), 0.7)[..., None])
    ink = COL[fg][None, None, :] * (1 + 0.03 * smooth_noise(sh, sw, 3, rng))[..., None]
    col = base * (1 - G[..., None]) + ink * G[..., None]
    edge = np.clip(cv2.GaussianBlur(A, (0, 0), 1.6), 0, 1)
    col = col * (0.93 + 0.07 * edge[..., None])
    spr = np.dstack([np.clip(col, 0, 255) * A[..., None], A]).astype(np.float32)
    return dict(spr=spr, sh=shadow_of(A, 8, 30), sh2=shadow_of(A, 2.5, 30), w=ww / S, h=float(h), sw=sw, sh_h=sh)


def build_letters(rows, fonts, seed):
    """rows: [{cy, h, x0, x1, align, items: [[char, frame] | None (a space)]}] -> placed letter sprites.
    fonts: [[path, weight], ...] cycled in a seeded order (one face = every letter in the buyer's font)."""
    rng = np.random.default_rng(seed)
    letters = []
    fi = list(rng.permutation(len(fonts)))
    last_bg, n = None, 0
    for row in rows:
        items = row['items']
        scale = 1.0
        for attempt in range(3):
            made, st = [], np.random.default_rng(seed * 53 + len(letters) + 7)
            lb, nn = last_bg, n
            for it in items:
                if it is None:
                    made.append(None)
                    continue
                fidx = int(fi[nn % len(fi)])
                pairs = [p for p in SCRAPS if p[0] != lb]
                bg, fg = pairs[int(st.integers(0, len(pairs)))]
                hh = int(row['h'] * scale * st.uniform(0.90, 1.06))
                sc = make_scrap(it[0], hh, fonts[fidx], bg, fg, st)
                sc.update(ch=it[0], f=int(it[1]), rot=float(st.uniform(-7.5, 7.5)), dy=float(st.uniform(-9, 9)) * scale)
                made.append(sc)
                lb, nn = bg, nn + 1
            gap = -5 * scale
            space = row['h'] * 0.30 * scale
            total = sum((m['w'] + gap) if m else space for m in made) - gap
            avail = row['x1'] - row['x0']
            if total <= avail or attempt == 2:
                break
            scale *= avail / total * 0.985
        last_bg, n = lb, nn
        x = row['x0'] if row['align'] == 'left' else (row['x1'] - total if row['align'] == 'right'
                                                       else (row['x0'] + row['x1'] - total) / 2)
        for m in made:
            if m is None:
                x += space
                continue
            m.update(cx=x + m['w'] / 2, cy=row['cy'] + m['dy'], idx=len(letters), row=rows.index(row), scale=scale)
            x += m['w'] + gap
            letters.append(m)
    return letters


def letter_box(L, grow=1.0):
    """axis-aligned box of a resting letter (its tilt included) -> x0, y0, x1, y1."""
    a = math.radians(abs(L['rot']) + 0.8)
    w, h = L['w'] * grow, L['h'] * grow
    bw, bh = w * math.cos(a) + h * math.sin(a), w * math.sin(a) + h * math.cos(a)
    return L['cx'] - bw / 2 - 2, L['cy'] - bh / 2 - 2, L['cx'] + bw / 2 + 2, L['cy'] + bh / 2 + 2


def draw_letters(canvas, letters, f, tick, seed):
    seq = [(1.48, 0.8, 9.0), (1.14, 1.0, 3.0), (0.94, 1.0, -1.0), (1.02, 1.0, 0.4)]   # scale, opacity, extra tilt
    for L in sorted(letters, key=lambda q: q['f']):
        k = f - (L['f'] - 2)
        if k < 0:
            continue
        r = np.random.default_rng(seed * 211 + L['idx'] * 13 + tick)
        if k < len(seq):
            s, op, xr = seq[k]
            jx = jy = jr = 0.0
        else:
            s, op, xr = 1.0, 1.0, 0.0
            jx, jy, jr = r.uniform(-1.4, 1.4), r.uniform(-1.4, 1.4), r.uniform(-0.8, 0.8)
        sw, sh = L['sw'], L['sh_h']
        M = aff(s, L['rot'] + xr * (1 if L['idx'] % 2 else -1) + jr, sw / 2, sh / 2,
                L['cx'] - sw / 2 + jx, L['cy'] - sh / 2 + jy - 26 * max(0, s - 1))
        lift = max(0.0, s - 1)
        blit(canvas, L['sh'], chain(M, aff(tx=-30 + 7 + 60 * lift, ty=-30 + 10 + 90 * lift)), 0.36 * op)
        blit(canvas, L['sh2'], chain(M, aff(tx=-30 + 2, ty=-30 + 3)), 0.25 * op * (1 if lift < 0.1 else 0))
        blit(canvas, L['spr'], M, op)


# ---------------------------------------------------------------------------------------------------- tape
def make_tape(tp, rng):
    w, h, m = int(tp['w']), int(tp['h']), 14
    S = 2
    im = Image.new('L', ((w + 2 * m) * S, (h + 2 * m) * S), 0)
    teeth = 7
    left = [(m * S + (0 if i % 2 else 7 * S), m * S + h * S * i / (teeth * 2)) for i in range(teeth * 2 + 1)]
    right = [((m + w) * S - (0 if i % 2 else 7 * S), m * S + h * S * i / (teeth * 2)) for i in range(teeth * 2 + 1)]
    ImageDraw.Draw(im).polygon(left + right[::-1], fill=255)
    A = cv2.resize(np.asarray(im, np.float32) / 255, None, fx=1 / S, fy=1 / S, interpolation=cv2.INTER_AREA)
    sh, sw = A.shape
    streak = cv2.resize(rng.standard_normal((sh // 2, 6)).astype(np.float32), (sw, sh), interpolation=cv2.INTER_CUBIC)
    yy = np.linspace(-1, 1, sh, dtype=np.float32)[:, None]
    tone = 1 + 0.035 * streak - 0.06 * yy ** 4 + 0.03 * np.exp(-((yy + 0.35) ** 2) / 0.02)
    col = COL['tape'][None, None, :] * tone[..., None]
    a = A * 0.88
    return dict(spr=np.dstack([col * a[..., None], a]).astype(np.float32), sh=shadow_of(A, 5, 20), sw=sw, sh_h=sh)


def draw_tape(canvas, tape, tp, f, tick, seed):
    k = f - tp['f']
    if k < 0:
        return
    seq = [(1.45, 0.6, -9), (1.10, 1.0, -3), (0.97, 1.0, 1)]
    s, op, xr = seq[k] if k < len(seq) else (1.0, 1.0, 0)
    r = np.random.default_rng(seed * 71 + tick)
    j = r.uniform(-0.8, 0.8, 3) if k >= len(seq) else (0, 0, 0)
    M = aff(s, tp['rot'] + xr + j[2] * 0.5, tape['sw'] / 2, tape['sh_h'] / 2,
            tp['cx'] - tape['sw'] / 2 + j[0], tp['cy'] - tape['sh_h'] / 2 + j[1] - 30 * max(0, s - 1))
    blit(canvas, tape['sh'], chain(M, aff(tx=-20 + 3 + 50 * max(0, s - 1), ty=-20 + 5 + 70 * max(0, s - 1))),
         0.30 * op)
    blit(canvas, tape['spr'], M, op)


# ---------------------------------------------------------------------------------------------------- the cutout
def clean_matte(a, rgb, mt, plate=None):
    """a: uint8 alpha of the source frame, rgb: the same frame. Drops bits of room the matte grabbed."""
    a = a.copy()
    if plate is not None and mt.get('plate'):
        x0, y0, x1, y1 = mt['plate']['roi']
        px = cv2.blur(rgb[y0:y1, x0:x1], (3, 3)).astype(np.int16)
        same = ((np.abs(px - plate[0]).max(2) < mt['plate']['thr']) & plate[1]).astype(np.uint8)
        same = cv2.morphologyEx(same, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        same = cv2.dilate(cv2.morphologyEx(same, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)), np.ones((5, 5), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(same, 8)
        for i in range(1, n):                               # real patches of room only, not the gaps between fingers
            if st[i, cv2.CC_STAT_AREA] < mt['plate']['min_area']:
                same[lab == i] = 0
        a[y0:y1, x0:x1][same > 0] = 0
    if mt.get('open_roi'):
        x0, y0, x1, y1, k = mt['open_roi']
        a[y0:y1, x0:x1] = cv2.morphologyEx(a[y0:y1, x0:x1], cv2.MORPH_OPEN, np.ones((int(k), 1), np.uint8))
    for p in mt.get('kill_polys') or []:
        cv2.fillPoly(a, [np.array(p, np.int32)], 0)
    n, lab, st, _ = cv2.connectedComponentsWithStats((a > 110).astype(np.uint8), 8)
    if n > 2:                                               # keep the speaker (largest piece) and what touches it
        keep = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        big = cv2.dilate((lab == keep).astype(np.uint8), np.ones((9, 9), np.uint8))
        a = a * big
    return a


def hand_cut(alpha, r, eps, jit, rng):
    """white border = dilated silhouette, simplified into scissor facets, vertices nudged. alpha float 0..1.
    Edge-replicate padding: where the speaker leaves the frame there is no border (the cut stays off screen)."""
    pad = r + 12
    m = cv2.copyMakeBorder((alpha > 0.5).astype(np.uint8), pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    d = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    cs, _ = cv2.findContours(d, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = np.zeros(d.shape, np.uint8)
    for c in cs:
        if cv2.contourArea(c) < 4000:
            continue
        p = cv2.approxPolyDP(c, eps, True)[:, 0, :].astype(np.float32)
        p += rng.uniform(-jit, jit, p.shape).astype(np.float32)
        cv2.fillPoly(out, [np.round(p * 16).astype(np.int32)], 255, cv2.LINE_AA, 4)
    return out[pad:-pad, pad:-pad].astype(np.float32) / 255


def cut_pose(cut, f, f_in):
    """(scale, dx, dy, border px, u) of the cutout at frame f. Pops out of the room over 4 frames."""
    k = f - (f_in + 1)
    seq = [0.36, 1.13, 1.035, 0.985]
    u = 0.0 if k < 0 else (seq[k] if k < len(seq) else 1.0)
    return (1 + (cut['scale'] - 1) * u, cut['dx'] * u, cut['dy'] * u, cut['border'] * min(1.0, max(0.0, u) * 1.2), u)


def cut_matrix(cut, s, dx, dy):
    """scale s about the anchor (ax, bottom of frame), then shift."""
    ax = cut['ax']
    return np.array([[s, 0, ax - s * ax + dx], [0, s, H - s * H + dy]], np.float32)


def draw_cutout(canvas, rgbf, alpha_u8, f, tick, bordertex, cut, f_in, seed):
    s, dx, dy, bpx, u = cut_pose(cut, f, f_in)
    r = np.random.default_rng(seed * 409 + tick)
    if u >= 1.0 and cut['jitter']:
        dx += r.uniform(-1.2, 1.2)
        dy += r.uniform(-1.2, 1.2)
    M = cut_matrix(cut, s, dx, dy)
    a = cv2.warpAffine(alpha_u8, M, (W, H), flags=cv2.INTER_LINEAR).astype(np.float32) / 255
    img = cv2.warpAffine(rgbf, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    if bpx >= 2:
        rr = int(round(bpx + (r.uniform(-3, 3) if u >= 1.0 else 0)))
        b = hand_cut(a, rr, float(r.uniform(5.0, 8.5)), 2.6, r)
        sh = cv2.warpAffine(cv2.GaussianBlur(b, (0, 0), 18), np.float32([[1, 0, 11], [0, 1, 17]]), (W, H))
        sh2 = cv2.warpAffine(cv2.GaussianBlur(b, (0, 0), 4), np.float32([[1, 0, 3], [0, 1, 4]]), (W, H))
        k = np.clip(sh * 0.44 + sh2 * 0.22, 0, 0.6)[..., None] * min(1.0, u)
        canvas[:] = canvas * (1 - k) + COL['shadow'] * k
        bb = b[..., None]
        canvas[:] = canvas * (1 - bb) + bordertex * bb
    at = np.clip((a - 0.46) / 0.30, 0, 1)                   # tighten the soft matte edge: no room colour on the white
    at = cv2.GaussianBlur(cv2.erode(at, np.ones((3, 3), np.uint8)), (0, 0), 0.9)[..., None]
    canvas[:] = canvas * (1 - at) + img * at


# ---------------------------------------------------------------------------------------------------- tear away
def make_pieces(C, tear, rng):
    ys = np.arange(H, dtype=np.float32)

    def n1(scale):
        m = int(H / scale) + 3
        return np.interp(ys, np.linspace(0, H, m), rng.standard_normal(m)).astype(np.float32)
    xl = tear['x_top'] + (tear['x_bot'] - tear['x_top']) * ys / H + 42 * n1(170) + 14 * n1(34) + 4 * n1(7)
    X = np.arange(W, dtype=np.float32)[None, :]
    d = xl[:, None] - X
    n = 2.6 * smooth_noise(H, W, 4.5, rng) + 1.0 * smooth_noise(H, W, 1.6, rng)
    aA = np.clip(d + n + 0.5, 0, 1)
    wf = np.clip(11 + 7 * smooth_noise(H, W, 30, rng) + 4 * smooth_noise(H, W, 5, rng), 2, 26)
    pA = np.clip(d + n - wf + 0.5, 0, 1)[..., None]
    core = COL['core'][None, None, :] * (1 + 0.05 * smooth_noise(H, W, 2.2, rng))[..., None]
    colA = C * pA + core * (1 - pA)
    aB = np.clip(-d - n - 2 + 0.5, 0, 1)
    A = np.dstack([colA * aA[..., None], aA]).astype(np.float32)
    B = np.dstack([C * aB[..., None], aB]).astype(np.float32)
    return dict(A=A, B=B, shA=shadow_of(aA, 16, 50), shB=shadow_of(aB, 16, 50))


def tear_p(f, f_out):
    return min(1.0, ((f - f_out + 1) / 6.0) ** 2.2)


def draw_tear(canvas, pieces, f, f_out):
    p, pp = tear_p(f, f_out), (tear_p(f - 1, f_out) if f > f_out else 0.0)
    v = int(min(120, (p - pp) * 1300 * 0.30))
    for key, sk, tx, ty, rot, cx, cy in (('B', 'shB', 1300, -170, 12.0, 900, 600),
                                         ('A', 'shA', -1300, 130, -14.0, 200, 1400)):
        M = aff(1 + 0.04 * p, rot * p, cx, cy, tx * p, ty * p)
        blit(canvas, pieces[sk], chain(M, aff(tx=-50 + 14 + 40 * p, ty=-50 + 20 + 50 * p)), 0.42, (v, 1 + v // 5))
        blit(canvas, pieces[key], M, 1.0, (v, 1 + v // 5))


# ---------------------------------------------------------------------------------------------------- the scene
def held_frame(f, f_in, step_fps):
    """the source frame the 12 fps cutout shows at frame f (the first frame of f's tick)."""
    if f < f_in:
        return f
    tick = int((f - f_in) * step_fps / FPS)
    return f_in + int(math.ceil(tick * FPS / step_fps - 1e-9))


class Scene:
    def __init__(self, pl, plate=None):
        self.pl = pl
        set_colours(pl['colours'])
        seed = self.seed = pl['seed']
        self.f_in, self.f_out, self.step = pl['f_in'], pl['f_out'], pl['step_fps']
        self.sheets = [make_sheet(L, i, np.random.default_rng(seed * 11 + i)) for i, L in enumerate(pl['layers'])]
        self.letters = build_letters(pl['rows'], pl['fonts'], seed) if pl['rows'] else []
        self.marks = [dict(mk) for mk in pl['marks']]
        for i, mk in enumerate(self.marks):
            mk['strokes'] = mark_strokes(mk['path'], np.random.default_rng(seed * 5 + i))
        self.tape = make_tape(pl['tape'], np.random.default_rng(seed + 3)) if pl.get('tape') else None
        rng = np.random.default_rng(seed + 1)
        g = cv2.GaussianBlur(rng.standard_normal((H, W)).astype(np.float32), (0, 0), 0.85)
        g = g / g.std() + 0.55 * smooth_noise(H, W, 5.0, rng)     # wax tooth of the crayon + a little clumping
        self.grain = g / g.std()
        self.bordertex = COL['white'][None, None, :] * (1 + 0.018 * smooth_noise(H, W, 40, rng)
                                                        + 0.012 * smooth_noise(H, W, 2.5, rng))[..., None]
        self.land = max(L['f'] for L in pl['layers']) + 4
        self.plate = plate
        self.bg = (None, None)
        self.pieces = None

    def tick(self, f):
        return int((f - self.f_in) * self.step / FPS) if f >= self.f_in else -1

    def compose(self, f, room, held_rgb, held_alpha):
        tick = self.tick(f)
        if f >= self.land:
            key = tick // 2
            if self.bg[0] != key:
                c = room.astype(np.float32)
                draw_sheets(c, self.sheets, f, tick, self.seed)
                self.bg = (key, c)
            canvas = self.bg[1].copy()
        else:
            canvas = room.astype(np.float32)
            draw_sheets(canvas, self.sheets, f, tick, self.seed)
        draw_marks(canvas, self.marks, f, tick, self.grain, False, self.seed)
        draw_cutout(canvas, held_rgb.astype(np.float32), held_alpha, f, tick, self.bordertex, self.pl['cut'],
                    self.f_in, self.seed)
        draw_letters(canvas, self.letters, f, tick, self.seed)
        draw_marks(canvas, self.marks, f, tick, self.grain, True, self.seed)
        if self.tape is not None:
            draw_tape(canvas, self.tape, self.pl['tape'], f, tick, self.seed)
        return canvas

    def frame(self, f, src):
        """src.room(i) -> rgb uint8 of source frame i; src.get(i) -> (rgb, cleaned alpha). Returns uint8 rgb."""
        room = src.room(f)
        if f < self.f_in:
            return room
        if f < self.f_out:
            hr, ha = src.get(held_frame(f, self.f_in, self.step))
            return np.clip(self.compose(f, room, hr, ha) + 0.5, 0, 255).astype(np.uint8)
        if tear_p(f, self.f_out) >= 1.0:
            return room
        if self.pieces is None:
            g = self.f_out - 1
            hr, ha = src.get(held_frame(g, self.f_in, self.step))
            c = self.compose(g, src.room(g), hr, ha)
            self.pieces = make_pieces(c, self.pl['tear'], np.random.default_rng(self.seed + 99))
        canvas = room.astype(np.float32)
        draw_tear(canvas, self.pieces, f, self.f_out)
        return np.clip(canvas + 0.5, 0, 255).astype(np.uint8)


def safe_guide(img):
    img = img.copy()
    s = SAFE
    c = (255, 40, 40)
    cv2.line(img, (0, s['top']), (W, s['top']), c, 2)
    cv2.line(img, (0, s['bottom']), (W, s['bottom']), c, 2)
    cv2.line(img, (s['side'], 0), (s['side'], H), c, 2)
    cv2.line(img, (W - s['side'], 0), (W - s['side'], H), c, 2)
    cv2.line(img, (W - s['right_low'][1], s['right_low'][0]), (W - s['right_low'][1], s['bottom']), c, 2)
    cv2.line(img, (W - s['right_low'][1], s['right_low'][0]), (W, s['right_low'][0]), c, 2)
    return img
