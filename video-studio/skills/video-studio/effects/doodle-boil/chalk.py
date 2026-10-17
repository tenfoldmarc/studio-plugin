"""doodle-boil chalk engine (clip independent). Hand paths, chalk stamping, the board tooth, the boiling outline,
doodle draw-on / rub-out and the finale rays. Used by bake.py; build.py uses schedule() for timing and sound.
Every random draw is seeded from (purpose, doodle, stroke, boil step): the same slot always bakes the same frames.
"""
import math

import cv2
import numpy as np

import doodles

W, H, FPS = 1080, 1920, 30
BOIL_OUTLINE = 2        # the outline is redrawn every 2 frames
BOIL_DOODLE = 3         # doodles are redrawn every 3 frames
SAFE = dict(top=220, bottom=1470, side=35, right=100, right_from=1155)
ORDER = ['cream', 'yellow', 'pink']     # layer order: a pink or yellow fill paints over cream lines


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def keyed(keys, t):
    if not keys:
        return 0.0
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * ease_io((t - t0) / max(t1 - t0, 1e-6))
    return keys[-1][1]


def snoise(rng, n, wl):
    """Circular smooth noise, n samples, wavelength wl samples, unit std."""
    n = max(int(n), 8)
    spec = np.fft.rfft(rng.standard_normal(n))
    fr = np.fft.rfftfreq(n)
    spec *= np.exp(-0.5 * (fr * wl * 1.6) ** 2)
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    s = x.std()
    return x / s if s > 1e-9 else x


def densify(pts, step=2.0, corner=2.5, closed=False):
    """Resample a polyline at uniform arc length and round the corners a little, like a hand does."""
    pts = np.asarray(pts, np.float64)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    L = s[-1]
    if L < 1e-6:
        return pts[:1].copy()
    m = max(int(L / step) + 1, 2)
    q = np.linspace(0, L, m)
    out = np.stack([np.interp(q, s, pts[:, 0]), np.interp(q, s, pts[:, 1])], 1)
    k = int(corner / step * 3) | 1
    if corner > 0 and m > k + 2:
        ker = np.exp(-0.5 * ((np.arange(k) - k // 2) / (corner / step)) ** 2)
        ker /= ker.sum()
        pad = k // 2
        if closed:
            ext = np.concatenate([out[-pad:], out, out[:pad]])
        else:
            ext = np.concatenate([np.repeat(out[:1], pad, 0), out, np.repeat(out[-1:], pad, 0)])
        out = np.stack([np.convolve(ext[:, 0], ker, 'valid'), np.convolve(ext[:, 1], ker, 'valid')], 1)
    return out


def stamp(mask, pts, rad, inten):
    """Chalk stick stamps: one anti-aliased disc per sample, value = pressure."""
    xs = np.round(pts[:, 0] * 8).astype(np.int64)
    ys = np.round(pts[:, 1] * 8).astype(np.int64)
    rs = np.maximum(np.round(rad * 8), 6).astype(np.int64)
    vs = np.clip(inten * 255, 0, 255).astype(np.int64)
    for x, y, r, v in zip(xs.tolist(), ys.tolist(), rs.tolist(), vs.tolist()):
        cv2.circle(mask, (x, y), r, v, -1, cv2.LINE_AA, 3)


def draw_path(mask, pts, width, press, a, b, rng, taper=(16, 26), wob=0.22):
    """Draw the arc-fraction window [a, b] of a hand path with uneven width and pressure."""
    n = len(pts)
    if n < 2 or b <= a:
        return
    seg = np.hypot(*np.diff(pts, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    L = max(s[-1], 1e-6)
    tap = np.minimum(1, (s + 5) / taper[0]) * np.minimum(1, (L - s + 5) / taper[1])
    step = L / (n - 1)
    wn = 1 + wob * snoise(rng, n, 46 / step)[:n]
    pn = 0.84 + 0.16 * snoise(rng, n, 80 / step)[:n]
    rad = width / 2 * (0.5 + 0.5 * tap) * np.clip(wn, 0.55, 1.5)
    inten = press * np.clip(pn, 0.5, 1.12) * (0.62 + 0.38 * tap)
    sel = (s >= a * L - 1e-6) & (s <= b * L + 1e-6)
    if sel.any():
        stamp(mask, pts[sel], rad[sel], inten[sel])


def hand(pts, rng, amp=2.0, wl=60.0, step=2.0):
    """Hand tremor: smooth displacement along the stroke."""
    n = len(pts)
    if n < 4:
        return pts
    d = np.stack([snoise(rng, n, wl / step)[:n], snoise(rng, n, wl / step)[:n]], 1) * amp
    d += np.stack([snoise(rng, n, 14 / step)[:n], snoise(rng, n, 14 / step)[:n]], 1) * amp * 0.22
    return pts + d


# ------------------------------------------------------------------------------------------------- timing + colour
def schedule(d):
    """Strokes of one cue with absolute start times (stroke order) and the cue's colour choices applied.
    colour = main line slot, fill = scribble fill slot, accent = every other stroke. cross adds the X on that time."""
    strokes = doodles.SHAPES[d['shape']](d)
    evs = {'cross': d['cross']} if d.get('cross') is not None else {}
    if evs and not any(s['ev'] == 'cross' for s in strokes):
        strokes += doodles.cross_strokes()
    strokes = [s for s in strokes if (not s['ev'] or s['ev'] in evs) and (not s.get('grp') or s['grp'] in evs)]
    main0 = strokes[0]['color']
    line = d.get('colour')
    for s in strokes:
        if s['kind'] == 'fill':
            if d.get('fill'):
                s['color'] = d['fill']
            elif line and s['color'] == main0:
                s['color'] = line
        elif s['color'] == main0:
            if line:
                s['color'] = line
        elif d.get('accent') and not s['ev'] and not s.get('grp'):
            s['color'] = d['accent']
    t = d['t_in']
    for s in strokes:
        if s['ev']:
            t = max(evs[s['ev']], t)
        t += s['gap']
        s['t0'] = t
        t += s['dur']
    return strokes


# ---------------------------------------------------------------------------------------------- silhouette (per frame)
class Sil:
    """Per-frame silhouette from the cutout alpha (half resolution for speed): largest body only."""

    def __init__(self, alpha):
        a = cv2.resize(alpha, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
        a = cv2.GaussianBlur(a, (0, 0), 1.6)
        b = (a > 140).astype(np.uint8)
        b = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        n, lab, st, _ = cv2.connectedComponentsWithStats(b, 8)
        if n > 1:
            k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            b = (lab == k).astype(np.uint8)
        # mattes go soft in the last few rows / columns: carry him out to the frame edge so the contour runs along the
        # edge (hidden) instead of drawing a line just inside it
        p = 8
        b[-p:] = np.maximum(b[-p:], b[-p - 1])
        b[:p] = np.maximum(b[:p], b[p])
        b[:, :p] = np.maximum(b[:, :p], b[:, p:p + 1])
        b[:, -p:] = np.maximum(b[:, -p:], b[:, -p - 1:-p])
        self.b = b
        self.empty = int(b.sum()) < 400
        self.dist = cv2.distanceTransform(1 - b, cv2.DIST_L2, 5)

    def contour(self, d, step=3.0, smooth=11.0):
        """Closed contour d px outside him: uniform spacing, smoothed, clockwise on screen, starting at the top.
        Returns (points, on_screen): on_screen is False where the contour only runs along the frame edge (a close-up's
        shoulders, a body cut by the bottom of the frame) so that part is never drawn."""
        if self.empty:
            return None, None
        m = (self.dist <= d / 2.0).astype(np.uint8)
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cs:
            return None, None
        c = max(cs, key=cv2.contourArea)[:, 0, :].astype(np.float64) * 2.0 + 0.5
        if len(c) < 40:
            return None, None
        c = np.concatenate([c, c[:1]])
        c = densify(c, step=step, corner=smooth, closed=True)[:-1]
        x, y = c[:, 0], c[:, 1]
        area = 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)
        if area < 0:                      # make it clockwise on screen (y down => positive shoelace)
            c = c[::-1]
        c = np.roll(c, -int(np.argmin(c[:, 1])), axis=0)
        e = 12.0 + smooth * 0.6
        on = (c[:, 0] > e) & (c[:, 0] < W - e) & (c[:, 1] > e) & (c[:, 1] < H - e)
        on = np.logical_and.reduce([np.roll(on, k) for k in range(-3, 4)])     # trim 3 samples off each hidden run
        return c, on

    def ray(self, cx, cy, ang_deg, d):
        """Distance from (cx, cy) to the point d px outside the silhouette, going out at ang_deg from straight up."""
        a = math.radians(ang_deg)
        dx, dy = math.sin(a), -math.cos(a)
        r = np.arange(0, 1300, 3.0)
        px = np.round((cx + r * dx) / 2).astype(int)
        py = np.round((cy + r * dy) / 2).astype(int)
        ok = (px >= 0) & (px < W // 2) & (py >= 0) & (py < H // 2)
        inside = np.zeros(len(r), bool)
        inside[ok] = self.dist[py[ok], px[ok]] <= d / 2.0
        idx = np.nonzero(inside)[0]
        return (r[idx[-1]] if len(idx) else 0.0), dx, dy


# ----------------------------------------------------------------------------------------------------- chalk engine
class Chalk:
    def __init__(self, pal):
        rng = np.random.default_rng(11)
        th, tw = H + 420, W + 420
        fine = cv2.GaussianBlur(rng.standard_normal((th, tw)).astype(np.float32), (0, 0), 0.75)
        coarse = cv2.GaussianBlur(rng.standard_normal((th, tw)).astype(np.float32), (0, 0), 2.4)
        t = 0.62 * fine / fine.std() + 0.38 * coarse / coarse.std()
        t /= t.std()
        self.tex = (0.5 + 0.5 * np.tanh(t * 0.9)).astype(np.float32)     # tooth of the board, about uniform 0..1
        self.pal = pal

    @staticmethod
    def new_masks():
        return {k: np.zeros((H, W), np.uint8) for k in ORDER}

    def composite(self, img, masks, seed):
        """img float32 BGR 0..255. Chalk = stamped mask broken up by the board tooth, plus a little dust."""
        rng = np.random.default_rng([5, seed])
        union = None
        for k in ORDER:
            if masks[k].any():
                union = masks[k] if union is None else np.maximum(union, masks[k])
        if union is None:
            return img
        ys = np.nonzero(union.any(1))[0]
        xs = np.nonzero(union.any(0))[0]
        y0, y1 = max(int(ys[0]) - 40, 0), min(int(ys[-1]) + 41, H)
        x0, x1 = max(int(xs[0]) - 40, 0), min(int(xs[-1]) + 41, W)
        sub = img[y0:y1, x0:x1]
        # soft contact shadow so the chalk separates from pale walls (pressure ** 4: firm lines cast it, fills hardly)
        sh = cv2.GaussianBlur((union[y0:y1, x0:x1].astype(np.float32) / 255) ** 4, (0, 0), 6.0)
        sh = np.roll(sh, (3, 2), (0, 1))
        sub *= (1 - 0.28 * np.clip(sh * 1.5, 0, 1))[..., None]
        oy, ox = int(rng.integers(0, 400)), int(rng.integers(0, 400))
        tex = self.tex[y0 + oy:y1 + oy, x0 + ox:x1 + ox]
        for k in ORDER:
            M = masks[k][y0:y1, x0:x1]
            if not M.any():
                continue
            m = M.astype(np.float32) / 255
            mb = cv2.GaussianBlur(m, (0, 0), 0.9)
            a = np.clip((mb * 1.12 - tex * 0.92 + 0.02) / 0.26, 0, 1)
            a = a * a * (3 - 2 * a)
            dust = cv2.GaussianBlur(m, (0, 0), 3.5) * 0.16
            a = np.clip(a * 0.94 + dust * (1 - a), 0, 1)[..., None]
            col = np.array(self.pal[k][::-1], np.float32)
            sub[:] = sub * (1 - a) + col * a
        return img


# ---------------------------------------------------------------------------------------------------- draw: outline
def draw_outline(mask, C, on, seed, width, press, vis_fn, lateral=1.6):
    """One boiling chalk pass around a closed contour: several strokes, small gaps and overlaps, uneven pressure.
    The draw-on runs over the ON-SCREEN length only, so a close-up's hidden frame-edge run never stalls the pen."""
    n = len(C)
    if n < 20 or not on.any():
        return
    rng = np.random.default_rng(seed)
    step = 3.0
    Lpx = n * step
    u = np.arange(n) / n
    uv = np.cumsum(on) / max(on.sum(), 1)            # progress along the visible part only
    NQ = 2048
    uq = np.arange(NQ) / NQ

    def nz(wl_px, amp):
        return np.interp(u, uq, snoise(rng, NQ, wl_px / Lpx * NQ), period=1.0) * amp

    tan = np.roll(C, -1, 0) - np.roll(C, 1, 0)
    tan /= np.maximum(np.hypot(tan[:, 0], tan[:, 1]), 1e-6)[:, None]
    nrm = np.stack([tan[:, 1], -tan[:, 0]], 1)            # outward for a clockwise screen contour
    disp = nz(90, 2.3) + nz(22, 0.8)
    P = C + nrm * disp[:, None]
    wn = np.clip(1 + nz(60, 0.22), 0.55, 1.5)
    pn = np.clip(0.86 + nz(120, 0.15), 0.5, 1.1)
    vis = vis_fn(uv) & on
    K = int(rng.integers(10, 15))
    wts = rng.uniform(0.55, 1.45, K)
    cuts = (np.cumsum(wts) / wts.sum() + rng.random()) % 1.0
    cuts.sort()
    for k in range(K):
        u0, u1 = cuts[k], cuts[(k + 1) % K] + (1.0 if k == K - 1 else 0.0)
        if rng.random() < 0.5:
            u0 += rng.uniform(9, 26) / Lpx              # small gap before this stroke
        else:
            u0 -= rng.uniform(14, 44) / Lpx             # or it overlaps the previous one, slightly off
        i0, i1 = int(math.floor(u0 * n)), int(math.ceil(u1 * n))
        idx = np.arange(i0, i1) % n
        if len(idx) < 6:
            continue
        s = np.arange(len(idx)) * step
        L = s[-1]
        tap = np.minimum(1, (s + 6) / 30) * np.minimum(1, (L - s + 6) / 40)
        off = rng.uniform(-lateral, lateral)
        pk = rng.uniform(0.84, 1.0)
        pts = P[idx] + nrm[idx] * off
        rad = width / 2 * (0.5 + 0.5 * tap) * wn[idx]
        inten = press * pk * pn[idx] * (0.6 + 0.4 * tap)
        sel = vis[idx]
        if sel.any():
            # 3 px contour spacing is too coarse for a 5 px stick: stamp at the midpoints too
            stamp(mask, pts[sel], rad[sel], inten[sel])
            mid = (pts + np.roll(pts, -1, 0)) / 2
            mid[-1] = pts[-1]
            stamp(mask, mid[sel], rad[sel], inten[sel])


def outline_vis(o, t):
    """Which part of the loop (u in 0..1 along the visible line, 0 = top of the head, clockwise) shows at time t."""
    r = ease_io((t - o['t_in']) / o['draw'])
    e = 0.0
    if o.get('t_out') is not None:
        e = ease_io((t - o['t_out']) / max(o.get('undraw', 0.3), 1e-3))
    if o['style'] == 'single':
        return lambda u, r=r, e=e: (u <= r) & (u >= e)
    return lambda u, r=r, e=e: ((u <= r / 2) | (u >= 1 - r / 2)) & ((u >= e / 2) & (u <= 1 - e / 2) if e > 0 else True)


# ---------------------------------------------------------------------------------------------------- draw: doodles
def xform(pts, size, rot_deg, cx, cy):
    a = math.radians(rot_deg)
    ca, sa = math.cos(a), math.sin(a)
    p = np.asarray(pts, np.float64) * size
    return np.stack([p[:, 0] * ca - p[:, 1] * sa + cx, p[:, 0] * sa + p[:, 1] * ca + cy], 1)


def draw_doodle(masks, di, d, strokes, centre, f, t):
    t_out = d.get('t_out')
    ex = ease_io((t - t_out) / 0.16) if t_out is not None else 0.0
    if t < d['t_in'] or ex >= 0.93:      # stop before the last crumbs so the exit never leaves specks
        return
    boil = f // BOIL_DOODLE
    brng = np.random.default_rng([101, di, boil])
    cx = centre[0] + brng.uniform(-1.3, 1.3)
    cy = centre[1] + brng.uniform(-1.3, 1.3)
    rot = d.get('rot', 0) + brng.uniform(-0.7, 0.7)
    size = d['size'] * (1 + brng.uniform(-0.012, 0.012))
    wscale = clamp(size / 150.0, 0.75, 1.0)           # small doodles get a thinner stick or they turn to mush
    for si, s in enumerate(strokes):
        rv = (t - s['t0']) / s['dur']
        if rv <= 0:
            continue
        b = ease_out(rv) if s['kind'] == 'line' else clamp(rv)
        a = ex
        if b <= a:
            continue
        rng = np.random.default_rng([202, di, si, boil])
        m = masks[s['color']]
        if s['kind'] == 'fill':
            poly = xform(s['poly'], size, rot, cx, cy)
            poly = densify(np.concatenate([poly, poly[:1]]), 3.0, 2.0)
            poly = hand(poly, rng, 1.6, 50, 3.0)
            x0, y0 = poly.min(0) - 6
            x1, y1 = poly.max(0) + 6
            ang = math.radians(s['angle'] + rng.uniform(-4, 4))
            dv = np.array([math.cos(ang), math.sin(ang)])
            pv = np.array([-dv[1], dv[0]])
            cen = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
            R = math.hypot(x1 - x0, y1 - y0) / 2
            sp = s['spacing'] * wscale
            rows = int(2 * R / sp) + 1
            zz = []
            for k in range(rows + 1):
                q = -R + k * sp + rng.uniform(-0.2, 0.2) * sp
                e = R * (1 if k % 2 == 0 else -1) + rng.uniform(-8, 8)
                zz.append(cen + pv * q + dv * e)
            zp = hand(densify(np.array(zz), 3.0, 4.0), rng, 1.5, 40, 3.0)
            bx0, by0 = max(int(x0) - 20, 0), max(int(y0) - 20, 0)
            bx1, by1 = min(int(x1) + 21, W), min(int(y1) + 21, H)
            if bx1 <= bx0 or by1 <= by0:
                continue
            off = np.array([bx0, by0], np.float64)
            tmp = np.zeros((by1 - by0, bx1 - bx0), np.uint8)
            draw_path(tmp, zp - off, s['width'] * wscale, s['press'], a, b, rng, taper=(4, 4), wob=0.28)
            clip = np.zeros_like(tmp)
            cv2.fillPoly(clip, [np.round(poly - off).astype(np.int32)], 255, cv2.LINE_AA)
            sub = m[by0:by1, bx0:bx1]
            np.maximum(sub, cv2.bitwise_and(tmp, clip), out=sub)
            continue
        pts = xform(s['pts'], size, rot, cx, cy)
        pts = densify(pts, 2.0, s.get('corner', 2.5))
        amp = 2.4 if s['kind'] == 'zig' else 1.7
        pts = hand(pts, rng, amp, 55, 2.0)
        draw_path(m, pts, s['width'] * wscale, s['press'], a, b, rng, taper=s.get('taper', (14, 22)))


def draw_rays(masks, di, d, sil, centre, f, t, outer, angles, scale=1.0):
    """The finale burst: short chalk dashes radiating out of his outline, nearest-to-vertical first."""
    if t < d['t_in']:
        return
    t_out = d.get('t_out')
    if t_out is not None and t >= t_out + 0.12:
        return
    boil = f // BOIL_DOODLE
    cx, cy = centre
    order = sorted(range(len(angles)), key=lambda j: abs(angles[j]))
    for k, ang in enumerate(angles):
        t0 = d['t_in'] + order.index(k) * 0.016
        rv = (t - t0) / 0.10
        if rv <= 0:
            continue
        a = ease_io((t - t_out) / 0.12) if t_out is not None else 0.0
        rng = np.random.default_rng([303, di, k, boil])
        rb, dx, dy = sil.ray(cx, cy, ang, outer)
        if rb <= 0:
            continue
        a0 = rb + 30 * scale + rng.uniform(-3, 3)
        ln = ((78 if k % 2 == 0 else 46) + rng.uniform(-6, 6)) * scale
        p0 = np.array([cx + dx * a0, cy + dy * a0])
        p1 = np.array([cx + dx * (a0 + ln), cy + dy * (a0 + ln)])
        if not all(inside_safe(p, 10) for p in (p0, p1)):
            continue
        pts = hand(densify(np.array([p0, p1]), 2.0, 0), rng, 1.3, 40, 2.0)
        draw_path(masks['yellow' if k % 2 == 0 else 'cream'], pts, 11 * max(scale, 0.8), 0.97, a, ease_out(rv), rng,
                  taper=(10, 26))


def inside_safe(p, pad=0):
    x, y = p
    right = W - (SAFE['right'] if y > SAFE['right_from'] else SAFE['side'])
    return SAFE['side'] + pad < x < right - pad and SAFE['top'] + pad < y < SAFE['bottom'] - pad
