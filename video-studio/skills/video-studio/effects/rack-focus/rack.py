"""rack-focus engine: light, lens, bokeh, the title sprite and one composited frame.

Shared by build.py (measure + layout) and bake.py (the frame loop). Everything here is driven by work/plan.json,
which build.py writes from the CLIP block and from what it measured on the clip. No clip-specific values live here.

One focus value e(t) in 0..1 drives the frame: the title's blur falls as the picture's blur rises, and the picture
breathes with it. All blur is an aperture-shaped kernel in linear light. e = 0 gives back the source frame.
"""
import math
import os
import re
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
SAFE = dict(top=220, bottom=1470, side=35, right_low=(1155, 100))
BLADES = 9                     # aperture blades: discs are very slightly nine-sided, like a real lens wide open
BLADE_ROT = 0.31               # radians, the lens's fixed blade angle
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

cv2.setNumThreads(1)           # bake.py runs one process per core; threads inside each would fight


# ---------------------------------------------------------------------------------------------------- easing
def smoother(u):
    u = min(max(float(u), 0.0), 1.0)
    return u * u * u * (u * (6 * u - 15) + 10)


def clamp01(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else float(u)


# ---------------------------------------------------------------------------------------------------- light
def _s2l(v):
    v = np.asarray(v, np.float64) / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


SRGB2LIN = _s2l(np.arange(256)).astype(np.float32)


class Light:
    """sRGB bytes <-> linear light with clipped highlights pushed back up, so a bulb or a window blooms when it is
    defocused. Driven by luminance (a bright wall is not a light), and exactly invertible, so radius 0 is the source.
    hdr_t: luminance where the lift starts (linear). hdr_g: how far the very brightest pixel is lifted (x(1 + g))."""

    def __init__(self, hdr_t, hdr_g):
        self.t, self.g = float(hdr_t), float(hdr_g)
        ms = np.linspace(0.0, 1.0, 16384)
        self.ms = ms
        self.hs = ms * (1 + self.g * np.clip((ms - self.t) / (1 - self.t), 0, 1) ** 2)

    def to(self, img8):
        lin = SRGB2LIN[img8]
        m = lin @ LUMA
        s = np.clip((m - self.t) / (1 - self.t), 0, 1)
        return lin * (1 + self.g * s * s)[..., None]

    def back(self, hdr, dither=True, seed=7):
        hdr = np.maximum(hdr, 0)
        m = hdr @ LUMA
        lm = np.interp(m, self.hs, self.ms).astype(np.float32)
        out = np.clip(hdr * (lm / np.maximum(m, 1e-6))[..., None], 0, 1)
        srgb = np.where(out <= 0.0031308, out * 12.92, 1.055 * np.power(out, 1 / 2.4) - 0.055) * 255.0
        if dither:   # half a code value of seeded noise so soft gradients do not band in 8 bit
            rng = np.random.default_rng(seed)
            srgb = srgb + (rng.random(srgb.shape[:2], dtype=np.float32)[..., None] - 0.5) * 0.9
        return np.clip(srgb + 0.5, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------------------------------- lens
def aperture_edge(dx, dy, r):
    """Distance of the aperture's edge from its centre along each (dx, dy): a circle pulled 28 percent of the way
    toward a nine-sided polygon (rounded blades)."""
    th = np.arctan2(dy, dx) - BLADE_ROT
    seg = 2 * np.pi / BLADES
    poly = np.cos(np.pi / BLADES) / np.cos(np.mod(th, seg) - seg / 2)
    return r * (0.72 + 0.28 * poly) / (0.72 + 0.28 * (1 + np.cos(np.pi / BLADES)) / 2)


def disc_kernel(r, rim=0.20):
    """Aperture-shaped blur kernel, anti-aliased edge, slightly brighter rim. Continuous in r; identity below 0.5."""
    if r <= 0.5:
        return None
    n = int(np.ceil(r * 1.05 + 1))
    y, x = np.mgrid[-n:n + 1, -n:n + 1].astype(np.float32)
    d = np.hypot(x, y)
    re_ = aperture_edge(x, y, r) if r > 3 else r
    k = np.clip(re_ + 0.5 - d, 0, 1)
    if r > 2:
        e = np.clip((d - 0.70 * r) / (0.30 * r), 0, 1)
        k = k * (1 + rim * min(1.0, (r - 2) / 6.0) * e * e)
    return (k / k.sum()).astype(np.float32)


def _blur_full(img, r, chroma, rim):
    out = np.empty_like(img)
    radii = [r * chroma[0], r * chroma[1], r * chroma[2]] + ([r * chroma[1]] if img.shape[2] == 4 else [])
    kern = {}
    for c, rc in enumerate(radii):
        if rc not in kern:
            kern[rc] = disc_kernel(rc, rim)
        k = kern[rc]
        out[..., c] = img[..., c] if k is None else cv2.filter2D(img[..., c], -1, k, borderType=cv2.BORDER_REFLECT_101)
    return out


def lens_blur(img, r, chroma=(1.0, 1.0, 1.0), rim=0.20):
    """Aperture blur of a float image (R G B or R G B A). chroma scales the radius per colour channel (longitudinal
    colour fringing); alpha uses the green radius. Above radius 9 it runs at half size (area-averaged light, so no
    energy is lost) and comes back up: the result is smooth there anyway and it is four times faster."""
    if r <= 0.5:
        return img
    if r <= 9 or min(img.shape[:2]) < 64:
        return _blur_full(img, r, chroma, rim)
    h, w = img.shape[:2]
    small = cv2.resize(img, ((w + 1) // 2, (h + 1) // 2), interpolation=cv2.INTER_AREA)
    if small.ndim == 2:
        small = small[..., None]
    b = _blur_full(small, r / 2, chroma, rim)
    up = cv2.resize(b, (w, h), interpolation=cv2.INTER_LINEAR)
    return up if up.ndim == 3 else up[..., None]


def fill_plate(light, hole):
    """Clean plate of the room: push-pull fill of everything under the person. Smooth, so it is stable in time."""
    w = (1.0 - hole).astype(np.float32)
    c = light * w[..., None]
    cs, ws = [c], [w]
    while min(cs[-1].shape[:2]) > 3:
        cs.append(cv2.pyrDown(cs[-1]))
        ws.append(cv2.pyrDown(ws[-1]))
    f = cs[-1] / np.maximum(ws[-1], 1e-4)[..., None]
    for lv in range(len(cs) - 2, -1, -1):
        hh, ww = cs[lv].shape[:2]
        up = cv2.pyrUp(f, dstsize=(ww, hh))
        f = cs[lv] + (1.0 - np.clip(ws[lv], 0, 1))[..., None] * up
    return f


# ---------------------------------------------------------------------------------------------------- bokeh
def bokeh_texture(seed=11, size=257):
    """The lens's own imprint inside every out-of-focus disc, the same for all of them (that is what makes them read
    as one real lens and not as drawn circles): a slightly brighter rim, faint onion rings from the aspheric element,
    a low, uneven glow and three soft dust specks. Values around 1.0, seeded, built once."""
    rng = np.random.RandomState(seed)
    c = (size - 1) / 2
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    u = np.hypot(x - c, y - c) / c
    tex = 0.74 + 0.46 * np.clip(u, 0, 1) ** 5                                   # a lit rim, a clearer middle
    tex += 0.022 * np.sin(2 * np.pi * u * 5.3 + 0.7) * np.clip(1 - u, 0, 1) ** 0.5  # onion rings, fading at the rim
    noise = cv2.GaussianBlur(rng.randn(size, size).astype(np.float32), (0, 0), size / 18)
    tex += 0.05 * noise / (np.abs(noise).max() + 1e-6)
    for _ in range(3):                                                            # dust on a lens element
        px, py = rng.uniform(0.2, 0.8, 2) * size
        rr = rng.uniform(0.018, 0.03) * size
        tex -= 0.10 * np.exp(-((x - px) ** 2 + (y - py) ** 2) / (2 * rr * rr))
    return tex.astype(np.float32)


TEX = bokeh_texture()


def add_bokeh(tile, px, py, r, rgb, chroma, frame_xy, cat=0.55):
    """One out-of-focus point of light, added (linear light) into tile at (px, py).
    Aperture-shaped, carries the lens texture, soft at the very edge, a colour fringe from chroma, and a cat's eye:
    away from the middle of the frame the disc is clipped on its outer side by the lens barrel (frame_xy = where the
    point sits in the 1080x1920 frame)."""
    n = int(np.ceil(r * max(chroma) * 1.06 + 3))
    ix, iy = int(round(px)), int(round(py))
    y0, y1, x0, x1 = max(iy - n, 0), min(iy + n + 1, tile.shape[0]), max(ix - n, 0), min(ix + n + 1, tile.shape[1])
    if y1 <= y0 or x1 <= x0 or r < 0.8:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = xx - px, yy - py
    d = np.hypot(dx, dy)
    soft = max(1.0, 0.07 * r)
    # cat's eye: intersect with a larger circle shifted toward the frame centre
    vx, vy = (frame_xy[0] - W / 2) / (W / 2), (frame_xy[1] - H / 2) / (H / 2)
    off = cat * min(1.0, math.hypot(vx * 0.9, vy * 0.6)) ** 1.6
    ln = math.hypot(vx, vy) + 1e-6
    ccx, ccy = -vx / ln * off * r, -vy / ln * off * r
    d2 = np.hypot(dx - ccx, dy - ccy)
    t = 1.0
    if r > 6:   # the texture belongs to the disc, not to the tile: resample it on the disc's own box
        sx = (xx - px) / (r * 1.06) * (TEX.shape[1] - 1) / 2 + (TEX.shape[1] - 1) / 2
        sy = (yy - py) / (r * 1.06) * (TEX.shape[0] - 1) / 2 + (TEX.shape[0] - 1) / 2
        t = cv2.remap(TEX, sx.astype(np.float32), sy.astype(np.float32), cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_REPLICATE)
    for c in range(3):
        rc = r * chroma[c]
        edge = aperture_edge(dx, dy, rc) if rc > 4 else rc
        p = np.clip((edge - d) / soft + 0.5, 0, 1)
        p = p * p * (3 - 2 * p)
        p2 = np.clip((rc * 1.35 - d2) / soft + 0.5, 0, 1)
        tile[y0:y1, x0:x1, c] += rgb[c] * p * p2 * t


# ---------------------------------------------------------------------------------------------------- fonts
def font_table(fonts_dir):
    """Every @font-face in the slot's assets/fonts/fonts.css -> [(family, style, weight, path)]."""
    css_path = os.path.join(fonts_dir, 'fonts.css')
    out = []
    if not os.path.exists(css_path):
        return out
    css = open(css_path, encoding='utf-8').read()
    for block in re.findall(r'@font-face\s*\{([^}]*)\}', css):
        fam = re.search(r"font-family:\s*['\"]?([^;'\"]+)", block)
        sty = re.search(r'font-style:\s*(\w+)', block)
        wt = re.search(r'font-weight:\s*(\d+)', block)
        src = re.search(r"url\(['\"]?([^'\")]+)", block)
        if fam and src and os.path.exists(os.path.join(fonts_dir, src.group(1))):
            out.append((fam.group(1).strip(), sty.group(1) if sty else 'normal', int(wt.group(1)) if wt else 400,
                        os.path.join(fonts_dir, src.group(1))))
    return out


def pick_font(table, family, weight=400, italic=False):
    """-> [path, weight] of the closest face of that family. Italic falls back to upright and the other way round."""
    faces = [f for f in table if f[0].lower() == family.lower()]
    if not faces:
        have = sorted({f[0] for f in table})
        raise SystemExit(f'font "{family}" is not in assets/fonts/fonts.css. Families there: {", ".join(have)}')
    want = 'italic' if italic else 'normal'
    same = [f for f in faces if f[1] == want] or faces
    best = min(same, key=lambda f: abs(f[2] - weight))
    return [best[3], weight]


def load_font(spec, px):
    path, weight = spec
    f = ImageFont.truetype(path, int(round(px)))
    try:
        vals = []
        for a in f.get_variation_axes():
            name = a['name'].decode() if isinstance(a['name'], bytes) else str(a['name'])
            v = weight if name.lower().startswith('weight') else a['default']
            vals.append(max(a['minimum'], min(a['maximum'], v)))
        f.set_variation_by_axes(vals)
    except Exception:
        pass                                    # a static face: the weight is whatever the file is
    return f


def cased(s, case):
    if case == 'upper':
        return s.upper()
    if case == 'lower':
        return s.lower()
    if case == 'title':
        return ' '.join(w[:1].upper() + w[1:] for w in s.split(' '))
    return s


# ---------------------------------------------------------------------------------------------------- title
def title_metrics(t, ss=1):
    """Size of the two-line block at 1x for the plan t (build.py uses it to fit and place the block)."""
    fb = load_font(t['big_font'], t['big_px'] * ss)
    fm = load_font(t['small_font'], t['small_px'] * ss)
    big, small = t['big'], t['small']
    bb = fb.getbbox(big) if big else (0, 0, 0, 0)
    track = t['track_em'] * t['small_px'] * ss
    adv = [fm.getlength(ch) for ch in small]
    small_w = (sum(adv) + track * (len(adv) - 1)) if small else 0
    mb = fm.getbbox('H')
    cap_h = (mb[3] - mb[1]) if small else 0
    big_w, big_h = bb[2] - bb[0], bb[3] - bb[1]
    pad = 24 * ss
    inset = int(0.035 * big_w) if t.get('italic') else 0
    gap = t['line_gap'] * ss if (small and big) else 0
    bw = int(max(big_w, small_w + inset)) + 2 * pad
    bh = int(cap_h + gap + big_h) + 2 * pad
    return dict(fb=fb, fm=fm, bb=bb, track=track, adv=adv, small_w=small_w, mb=mb, cap_h=cap_h, big_w=big_w,
                big_h=big_h, pad=pad, inset=inset, gap=gap, bw=bw, bh=bh)


def make_title(t):
    """The two lines of type as a premultiplied linear-light sprite at 2x, plus the glint points that bloom into the
    bokeh discs. Glints sit on the thickest parts of the strokes, spread out evenly (seeded)."""
    ss = 2
    m = title_metrics(t, ss)
    bw, bh, pad = m['bw'], m['bh'], m['pad']
    mask_s = Image.new('L', (bw, bh), 0)
    mask_b = Image.new('L', (bw, bh), 0)
    if t['small']:
        d = ImageDraw.Draw(mask_s)
        x = pad + m['inset'] if t['align'] == 'left' else (bw - m['small_w']) / 2
        for ch, a in zip(t['small'], m['adv']):
            d.text((x, pad - m['mb'][1]), ch, font=m['fm'], fill=255)
            x += a + m['track']
    if t['big']:
        d = ImageDraw.Draw(mask_b)
        x = pad - m['bb'][0] if t['align'] == 'left' else (bw - m['big_w']) / 2 - m['bb'][0]
        d.text((x, pad + m['cap_h'] + m['gap'] - m['bb'][1]), t['big'], font=m['fb'], fill=255)
    a_s = np.asarray(mask_s, np.float32) / 255.0
    a_b = np.asarray(mask_b, np.float32) / 255.0
    soft = t.get('soften', 1.15)
    a_s, a_b = cv2.GaussianBlur(a_s, (0, 0), soft), cv2.GaussianBlur(a_b, (0, 0), soft)
    gx = np.linspace(0, 1, bw, dtype=np.float32)[None, :]
    gy = np.linspace(0, 1, bh, dtype=np.float32)[:, None]
    shade = 0.92 + 0.08 * gx - 0.04 * gy                     # a soft key light from one side, never flat
    ink = _s2l(t['ink']).astype(np.float32) * 0.92
    acc = _s2l(t['accent']).astype(np.float32) * 0.92
    rgb = (a_s * shade)[..., None] * ink + (a_b * shade)[..., None] * acc
    a = np.clip(a_s + a_b, 0, 1)
    sprite = np.dstack([rgb, a]).astype(np.float32)

    # glints: farthest-point sampling over the stroke cores (distance transform), seeded
    core = cv2.distanceTransform((np.maximum(np.asarray(mask_s), np.asarray(mask_b)) > 128).astype(np.uint8),
                                 cv2.DIST_L2, 5)
    ys, xs = np.nonzero(core >= max(1.0, 0.45 * core.max()))
    if not len(xs):
        ys, xs = np.nonzero(core > 0)
    rng = np.random.RandomState(t.get('seed', 5))
    pts = []
    if len(xs):
        j = int(rng.randint(len(xs)))
        pts.append(j)
        dmin = (xs - xs[j]) ** 2 + (ys - ys[j]) ** 2
        spread = (bw * bh / max(1, t['glints'])) * 0.35          # not an even grid: some clump, some stand alone
        for _ in range(t['glints'] - 1):
            ok = np.nonzero(dmin > spread)[0]
            j = int(ok[rng.randint(len(ok))]) if len(ok) and rng.rand() < 0.6 else int(np.argmax(dmin))
            pts.append(j)
            dmin = np.minimum(dmin, (xs - xs[j]) ** 2 + (ys - ys[j]) ** 2)
    base = np.array(t['bokeh'], np.float32)
    warm = np.array([255, 238, 205], np.float32)
    glints = []
    for k, j in enumerate(pts):
        wgt = 1.0 if k == 0 else float(0.12 + 0.83 * rng.uniform(0, 1) ** 1.6)   # a few bright, most faint
        mix = float(rng.uniform(0.0, 0.55))
        col = _s2l(base * (1 - mix) + warm * mix).astype(np.float32)
        col = col / max(float(col @ LUMA), 1e-4) * 0.9                   # same light level, different tint
        rf = float(rng.uniform(0.90, 1.06))                              # one plane: nearly one size
        ph = float(rng.uniform(0, 2 * np.pi))
        glints.append(((float(xs[j]) / ss, float(ys[j]) / ss), wgt, col, rf, ph))
    return sprite, ss, glints


# ---------------------------------------------------------------------------------------------------- the effect
class Scene:
    """Scene(plan).frame(i, src8, alpha8) -> rgb8. src8 is the a-roll frame, alpha8 the cutout alpha (or None)."""

    def __init__(self, pl):
        self.pl = pl
        self.light = Light(pl['hdr_t'], pl['hdr_g'])
        tl = pl['title']
        self.show_type = pl['captions']
        self.sprite, self.ss, self.glints = make_title(tl)
        if not self.show_type:
            self.sprite = np.zeros_like(self.sprite)
        self.t_in, self.t_back = pl['t_to_title'], pl['t_back']
        self.rack_in, self.rack_out = pl['rack_in'], pl['rack_out']
        self.t_land = self.t_in + self.rack_in
        self.r_rest = pl['rest_radius']

    def focus(self, t):
        return smoother((t - self.t_in) / self.rack_in) * (1 - smoother((t - self.t_back) / self.rack_out))

    def title_state(self, t):
        """-> (e, cx, cy, scale, radius, opacity) of the title at time t."""
        pl = self.pl
        e = self.focus(t)
        cx0, cy0 = pl['centre']
        fade_in = smoother((t - pl['t_show']) / pl['fade_in'])
        rise = (1 - clamp01((t - pl['t_show']) / max(0.2, self.t_land - pl['t_show']))) ** 3
        x_exit = clamp01((t - self.t_back - 0.10) / pl['exit_dur']) ** 2.0
        ex, ey = pl['exit_vec']
        cx = cx0 - 14 * rise + ex * x_exit
        cy = cy0 + 0.25 * self.r_rest * rise - 4.0 * (t - self.t_land) + ey * x_exit
        scale = 1.0 + 0.014 * (t - self.t_land)                      # slow drift toward the lens
        radius = self.r_rest * (1 - e) * (1 + 0.6 * x_exit)
        opacity = fade_in * (1 - smoother(x_exit * 1.15))
        return e, cx, cy, scale, radius, opacity

    def glint_value(self, r):
        """Linear brightness of a unit disc: a steady glow while it shrinks, dissolving into the type before radius
        14 (glints that keep their energy as the type sharpens turn into fairy lights). Past the rest radius the
        light spreads over a bigger disc and dims."""
        lv = self.pl['glint_level']
        if r >= self.r_rest:
            return lv * (self.r_rest / max(r, 1.0)) ** 1.4
        lo = 0.19 * self.r_rest
        return lv * (self.r_rest / max(r, 1.0)) ** 0.3 * smoother((r - lo) / (0.46 * self.r_rest))

    def body_gain(self, r):
        """The letters' own haze is thinned when far out of focus, so the rest state reads as discs, not a veil."""
        return 1.0 - 0.62 * smoother((r - 0.35 * self.r_rest) / (0.54 * self.r_rest))

    def draw_title(self, scene, t):
        e, cx, cy, scale, radius, op = self.title_state(t)
        if op < 1e-3:
            return None
        sh, sw = self.sprite.shape[:2]
        k = scale / self.ss
        tw, th = sw * k, sh * k
        pad = int(np.ceil(radius * 2.1)) + 8
        x0, y0 = cx - tw / 2, cy - th / 2
        ox, oy = int(np.floor(x0)) - pad, int(np.floor(y0)) - pad
        rw, rh = int(np.ceil(tw)) + 2 * pad + 2, int(np.ceil(th)) + 2 * pad + 2
        if ox >= W or oy >= H or ox + rw <= 0 or oy + rh <= 0:
            return None
        m = np.array([[k, 0, x0 - ox + (k - 1) / 2], [0, k, y0 - oy + (k - 1) / 2]], np.float32)
        tile = cv2.warpAffine(self.sprite, m, (rw, rh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                              borderValue=0)
        tile *= self.body_gain(radius) * op
        front = (1.006, 0.994, 1.006)                 # in front of the focal plane: a faint magenta rim
        tile = lens_blur(tile, radius, chroma=front, rim=0.12)
        if radius > 8:
            tile = cv2.GaussianBlur(tile, (0, 0), 0.022 * radius)       # a real lens never draws a razor edge
        val = self.glint_value(radius) * op
        if val > 1e-4:
            discs = np.zeros(tile.shape[:2] + (3,), np.float32)
            for (gx, gy), wgt, col, rf, ph in self.glints:
                shimmer = 1 + 0.06 * math.sin(2 * math.pi * 0.55 * t + ph)   # light catching the letters
                lx, ly = x0 - ox + gx * scale, y0 - oy + gy * scale
                add_bokeh(discs, lx, ly, radius * rf, val * wgt * shimmer * col, front, (ox + lx, oy + ly))
            small = cv2.resize(discs, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
            glow = cv2.resize(cv2.GaussianBlur(small, (0, 0), max(0.6, 0.42 * radius / 4)), (rw, rh),
                              interpolation=cv2.INTER_LINEAR)
            tile[..., :3] += 0.86 * discs + 0.22 * glow          # a little veiling glow, as a lens flares near light
        ax0, ay0, ax1, ay1 = max(ox, 0), max(oy, 0), min(ox + rw, W), min(oy + rh, H)
        t_ = tile[ay0 - oy:ay1 - oy, ax0 - ox:ax1 - ox]
        reg = scene[ay0:ay1, ax0:ax1]
        scene[ay0:ay1, ax0:ax1] = t_[..., :3] + (1 - np.clip(t_[..., 3:4], 0, 1)) * reg
        return (ax0, ay0, ax1, ay1)

    def backing(self, scene, e):
        """A soft local shade behind the title over a bright room (it comes and goes with the focus)."""
        b = self.pl['backing']
        if b <= 0 or e <= 1e-3:
            return
        cx, cy = self.pl['centre']
        bw, bh = self.pl['block']
        if not hasattr(self, '_shade'):
            yy, xx = np.mgrid[0:H // 4, 0:W // 4].astype(np.float32)
            u = np.hypot((xx * 4 - cx) / (0.62 * bw + 60), (yy * 4 - cy) / (0.62 * bh + 60))
            sh = np.exp(-u ** 2 * 1.6)
            self._shade = cv2.resize(sh, (W, H), interpolation=cv2.INTER_LINEAR)
        scene *= (1 - b * e * self._shade)[..., None]

    def frame(self, i, src8, alpha8):
        t = i / FPS
        e = self.focus(t)
        pl = self.pl
        light = self.light.to(src8)
        if e < 1e-4:
            # focus is on the speaker: the picture is the source, byte for byte, outside the title's own tile
            box = self.draw_title(light, t)
            out = src8.copy()
            if box:
                x0, y0, x1, y1 = box
                out[y0:y1, x0:x1] = self.light.back(light[y0:y1, x0:x1], dither=False)
            return out
        # two layers blurred apart: the room on a clean plate, the speaker premultiplied on top (no halo)
        if alpha8 is not None and alpha8.max() > 8:
            a = alpha8.astype(np.float32) / 255.0
            a = np.maximum(a, cv2.morphologyEx(a, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)))
            hole = cv2.dilate((a > 0.01).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
            plate = fill_plate(light, hole.astype(np.float32))
            subj = np.dstack([light - (1 - a)[..., None] * plate, a])
            behind = (0.985, 1.015, 0.985)                           # behind the focal plane: a faint green rim
            room_b = lens_blur(plate, pl['max_radius'] * e, behind)
            subj_b = lens_blur(subj, pl['max_radius'] * pl['subject_ratio'] * e, behind)
            scene = subj_b[..., :3] + (1 - np.clip(subj_b[..., 3:4], 0, 1)) * room_b
        else:
            scene = lens_blur(light, pl['max_radius'] * e, (0.985, 1.015, 0.985))
        s = 1 + pl['breathing'] * e                                  # focus breathing about the optical centre
        m = np.array([[s, 0, (1 - s) * (W - 1) / 2], [0, s, (1 - s) * (H - 1) / 2]], np.float32)
        scene = cv2.warpAffine(scene, m, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
        scene = np.ascontiguousarray(scene)
        if pl['grade']:                                              # GRADE=1: a touch richer while the title is up
            g = 0.06 * e
            scene = scene * np.array([1 + g * 0.5, 1 + g * 0.2, 1 - g * 0.3], np.float32)
        self.backing(scene, e)
        self.draw_title(scene, t)
        return self.light.back(scene, seed=i)


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


# ---------------------------------------------------------------------------------------------------- sound
SR = 48000


def _wav(path, x):
    x = np.clip(x, -1, 1)
    st = np.stack([x, x], axis=1)
    with wave.open(path, 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((st * 32767).astype('<i2').tobytes())


def _air(rng, n, centre, top):
    spec = np.fft.rfft(rng.randn(n))
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    shape = (fr / centre) / (1 + (fr / centre) ** 2) * 2
    shape *= 1 / (1 + (fr / top) ** 4)
    x = np.fft.irfft(spec * shape, n)
    return x / np.abs(x).max()


def make_sfx(folder):
    """Three cues, synthesised (seeded: every build writes the same files), all far under the voice: a low air swell
    into the pull, a soft low thump as the type lands, a quieter swell on the way back."""
    os.makedirs(folder, exist_ok=True)
    rng = np.random.RandomState(23)
    out = {}
    for key, ln, peak, gain in (('pull', 0.80, 0.55, 0.070), ('back', 0.66, 0.50, 0.046)):
        n = int(ln * SR)
        tt = np.arange(n) / SR
        x = _air(rng, n, 300.0, 520.0)
        env = np.where(tt < peak, np.sin(np.clip(tt / peak, 0, 1) * np.pi / 2) ** 2.2,
                       np.exp(-(tt - peak) / 0.09))
        env *= np.clip((ln - tt) / 0.06, 0, 1)
        _wav(os.path.join(folder, f'rack-{key}.wav'), x * env * gain)
        out[key] = (f'assets_fx/rack-{key}.wav', ln)
    n = int(0.75 * SR)
    tt = np.arange(n) / SR
    f0 = 52 + 30 * np.exp(-tt / 0.05)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    x = np.sin(ph) * np.exp(-tt / 0.16) + 0.25 * np.sin(2 * ph) * np.exp(-tt / 0.07)
    x *= np.clip(tt / 0.008, 0, 1) * np.clip((0.75 - tt) / 0.12, 0, 1)
    _wav(os.path.join(folder, 'rack-land.wav'), x / np.abs(x).max() * 0.06)
    out['land'] = ('assets_fx/rack-land.wav', 0.75)
    return out
