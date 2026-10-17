"""god-rays look: the light per frame, the two lines of type, the sounds, the safe guide. Used by build.py and bake.py.

Everything here is tuned once on the approved demo and carries to other clips. Clip-specific values arrive in the
plan (work/plan.json, written by build.py): times, the light scale, how far the room drops, fonts, colours.
"""
import math
import os
import re
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
HW, HH = W // 2, H // 2

# ---------------------------------------------------------------------------------------------------- LOOK (the demo)
RISE = 0.70                   # seconds for the source to bloom fully (slow start, long settle)
DIM_LEAD = 0.05               # the room starts falling this long before the light opens
FALL = 0.64                   # seconds for the light to fall away
SUBJ_STOPS = 0.26             # the speaker drops a little too, so they sit in the same light as the room
FACE_STOPS = 0.0              # ... except the face, which keeps its natural exposure
BUTTER = (250, 230, 122)
TINT_MIX_RAYS = 0.26          # beams: warm white pulled this far towards butter (more goes olive on a grey wall)
TINT_MIX_CORE = 0.07
SOURCE_OFFSET = (0.05, -0.18)  # source point from the head centre, in head radii (slightly above centre)
SOURCE_SIZE = 1.50            # gaussian radius of the source core, in light-scale units
RAY_SAMPLES = 56
RAY_LENGTH = 0.96
RAY_GAIN = 4.6
RAY_FLOOR = 0.16              # haze between shafts (0 = hard separated shafts, 1 = no shafts)
RAY_REACH = 3.0               # beams lose half their strength this many source radii out
RAY_SUBJECT = 0.16            # how much of the beam haze veils the speaker (flare in front of the lens)
HALO = 0.05
HALO_R = 2.5
CORE_GAIN = 2.2
BLOOM = ((0.30, 0.60), (1.0, 0.34), (3.0, 0.06))   # (sigma in light-scale units, gain)
BLOOM_SUBJECT = 0.12
RIM_GAIN = 2.6
RIM_DIFFUSE = 3.2             # the rim mostly brightens the speaker's own colours ...
RIM_SPEC = 0.30               # ... a little of it is the lamp's colour laid on top (a white line reads as a sticker)
RIM_W = 3.6                   # px at the demo's head size (scaled with the head)
WRAP_GAIN = 0.34
WRAP_W = 13.0
MOTES = 110
MOTE_GAIN = 3.0
SEED = 11
DEMO_R = 105.0               # head radius of the demo clip (px): the rim widths were tuned at this size
TEXT_IN = 0.52                # seconds for a line to pull into focus
TEXT_FADE_OUT = 0.32

LIN = (np.arange(256, dtype=np.float32) / 255.0) ** 2.2


def srgb_lin(c):
    return np.array([(v / 255.0) ** 2.2 for v in c], np.float32)


WHITE_L = np.array([1.0, 0.915, 0.80], np.float32)          # warm white, linear
TINT_RAYS = WHITE_L * (1 - TINT_MIX_RAYS) + srgb_lin(BUTTER) * TINT_MIX_RAYS
TINT_CORE = WHITE_L * (1 - TINT_MIX_CORE) + srgb_lin(BUTTER) * TINT_MIX_CORE
TINT_RAYS /= TINT_RAYS.max()
TINT_CORE /= TINT_CORE.max()
WARM = np.array([1.035, 1.0, 0.93], np.float32)             # GRADE=1: the dimmed room leans warm


# ---------------------------------------------------------------------------------------------------- envelopes
def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ease_open(x):
    x = min(1.0, max(0.0, x))
    return 1.0 - (1.0 - x ** 1.3) ** 3.2


def env_open(p, t):
    return ease_open((t - p['t_light']) / RISE) * (0.84 + 0.16 * (1.0 - smooth((t - p['t_out']) / FALL)))


def env_light(p, t):
    return ease_open((t - p['t_light']) / RISE) * (1.0 - smooth((t - p['t_out']) / FALL))


def env_dim(p, t):
    # on the way out the room comes back a little ahead of the light, or it sits grey with the lamp already gone
    up = ease_open((t - (p['t_light'] - DIM_LEAD)) / (RISE * 0.85))
    down = (1.0 - smooth((t - p['t_out']) / (FALL * 0.92))) ** 1.5
    return up * down


def light_span(p):
    """First and last frame where the light or the dim is on (outside them the frame is the a-roll itself)."""
    a = max(0, int(math.floor((p['t_light'] - DIM_LEAD) * FPS)))
    b = int(math.ceil((p['t_out'] + FALL) * FPS))
    return a, b


# ---------------------------------------------------------------------------------------------------- shafts
def _periodic_noise(rng, knots, n=4096):
    v = rng.random(knots).astype(np.float64)
    spec = np.fft.rfft(v)
    full = np.zeros(n // 2 + 1, complex)
    full[:len(spec)] = spec
    out = np.fft.irfft(full, n) * (n / knots)
    return (out - out.mean()) / (out.std() + 1e-6)


_rng = np.random.default_rng(SEED)
# gobo layers (angular noise, weight, turn speed rad/s): they turn slowly against each other, the shafts breathe
GOBO = [(_periodic_noise(_rng, 7), 1.0, 0.03), (_periodic_noise(_rng, 17), 0.9, -0.045),
        (_periodic_noise(_rng, 41), 0.6, 0.07), (_periodic_noise(_rng, 101), 0.28, -0.10)]
GOBO_LO, GOBO_HI = -0.75, 1.35
_hz = [cv2.resize(cv2.GaussianBlur(_rng.random((40, 24)).astype(np.float32), (0, 0), 1.2), (HW + 240, HH + 240),
                  interpolation=cv2.INTER_CUBIC) for _ in range(2)]
HAZE = [(h - h.min()) / (h.max() - h.min()) for h in _hz]
HAZE_VAR = 0.42
YH, XH = np.mgrid[0:HH, 0:HW].astype(np.float32)
XH = XH * 2 + 0.5
YH = YH * 2 + 0.5
YF, XF = np.mgrid[0:H, 0:W].astype(np.float32)


def haze(t, shift):
    acc = None
    for j, hz in enumerate(HAZE):
        ox = 120 + (shift[0] * 0.25 + (14 if j == 0 else -10) * t)
        oy = 120 + (shift[1] * 0.25 + (-9 if j == 0 else 6) * t)
        m = np.float32([[1, 0, -ox], [0, 1, -oy]])
        part = cv2.warpAffine(hz, m, (HW, HH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        acc = part if acc is None else acc + part
    return 1.0 + HAZE_VAR * (acc - 1.0)


def gobo(theta, t):
    n = 4096
    acc = np.zeros(theta.shape, np.float32)
    tot = 0.0
    for tab, wgt, rot in GOBO:
        idx = ((theta + rot * t) * (n / (2 * math.pi))).astype(np.int32) % n
        acc += wgt * tab[idx].astype(np.float32)
        tot += wgt * wgt
    g = np.clip((acc / math.sqrt(tot) - GOBO_LO) / (GOBO_HI - GOBO_LO), 0, 1)
    return g * g * (3 - 2 * g)


def zoom_blur(img, sx, sy, length, n):
    acc = np.zeros_like(img)
    for i in range(n):
        s = 1.0 - length * (i + 0.5) / n
        m = np.float32([[s, 0, sx * (1 - s)], [0, s, sy * (1 - s)]])
        acc += cv2.warpAffine(img, m, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_REPLICATE)
    return acc / n


class Motes:
    """Sparse dust, only lit inside the beams. Each mote sits between the speaker (moves with the head) and the room
    (moves with the tracked background), plus a slow drift. Seeded: every bake draws the same dust."""

    def __init__(self, off, hoff):
        rng = np.random.default_rng(SEED + 5)
        n = MOTES
        self.depth = rng.uniform(0.0, 0.34, n)
        lo = np.minimum(off.min(0) * 0.34, 0) + np.minimum(hoff.min(0), 0) - 80
        hi = np.maximum(off.max(0) * 0.34, 0) + np.maximum(hoff.max(0), 0) + 80
        self.base = np.stack([rng.uniform(-hi[0], W - lo[0], n), rng.uniform(-hi[1], H - lo[1], n)], 1)
        self.vel = np.stack([rng.uniform(-9, 9, n), rng.uniform(-16, 5, n)], 1)
        self.size = np.where(rng.random(n) < 0.14, rng.uniform(4.5, 9.0, n), rng.uniform(0.8, 1.7, n))
        self.lum = rng.uniform(0.35, 1.0, n)
        self.ph = rng.uniform(0, 6.28, n)
        self.fr = rng.uniform(0.5, 1.4, n)

    def pos(self, offs, t):
        off, hoff = offs
        wob = np.stack([np.sin(self.ph + t * self.fr) * 5, np.cos(self.ph * 1.7 + t * self.fr * 0.8) * 4], 1)
        d = self.depth[:, None]
        return self.base + off[None, :] * d + hoff[None, :] * (1 - d) + self.vel * t + wob

    def draw(self, offs_now, offs_prev, t, field):
        p1 = self.pos(offs_now, t)
        p0 = self.pos((offs_prev[0], offs_now[1]), t - 1.0 / FPS)   # the head's own move is left out: no dashes
        cv8 = np.zeros((H, W), np.uint8)
        big = np.zeros((H, W), np.uint8)
        for i in range(len(p1)):
            x, y = p1[i]
            if not (4 <= x < W - 4 and 4 <= y < H - 4):
                continue
            lit = float(field[int(y), int(x)])
            if lit < 0.02:
                continue
            v = (p1[i] - p0[i]) * 0.5
            ln = float(np.hypot(*v))
            sz = self.size[i]
            tw = 0.75 + 0.25 * math.sin(self.ph[i] * 3 + t * 2.2 * self.fr[i])
            b = min(1.0, lit * 1.6) * self.lum[i] * tw
            a = (int((x - v[0] / 2) * 16), int((y - v[1] / 2) * 16))
            c = (int((x + v[0] / 2) * 16), int((y + v[1] / 2) * 16))
            if sz > 4:
                cv2.line(big, a, c, int(255 * b * 0.17 * (2 * sz / (2 * sz + ln))), max(1, int(round(sz * 2))),
                         cv2.LINE_AA, 4)
            else:
                cv2.line(cv8, a, c, int(255 * b * (2 * sz / (2 * sz + ln))), max(1, int(round(sz * 1.6))),
                         cv2.LINE_AA, 4)
        out = cv2.GaussianBlur(cv8.astype(np.float32), (0, 0), 0.9) + cv2.GaussianBlur(big.astype(np.float32), (0, 0), 1.3)
        return out / 255.0


def god_rays(p, frame, alpha, src, rh, k_light, k_dim, k_open, t, head_c, motes, moff, rng):
    """One frame. frame uint8 RGB, alpha uint8 matte, src (x, y) source point, rh head radius (px). With both
    envelopes at 0 the output is the input frame."""
    rl = float(np.clip(rh, p['light_min'], p['light_max']))     # light scale: the demo look at any head size
    sw = float(np.clip(rh / DEMO_R, 0.6, 1.8))                   # rim widths follow the head
    lin = LIN[frame]
    a = alpha.astype(np.float32) / 255.0
    sx, sy = src
    kl = k_light * p['strength']
    rs = rl * SOURCE_SIZE * (0.62 + 0.38 * k_open) * (1.0 + 0.05 * math.sin(t * 1.3))

    ah = cv2.resize(a, (HW, HH), interpolation=cv2.INTER_AREA)
    occ = 1.0 - cv2.GaussianBlur(ah, (0, 0), 1.0)
    dx = XH - sx
    dy = YH - sy
    r = cv2.magnitude(dx, dy)
    theta = np.arctan2(dy, dx)
    core = np.exp(-(r / rs) ** 2)
    halo = HALO / (1.0 + (r / (HALO_R * rs)) ** 2)
    vis = (core + halo) * occ

    g = gobo(theta, t)
    near = np.clip((r - 0.7 * rh) / (1.3 * rl), 0, 1)
    gmix = 1.0 - near * (1.0 - (RAY_FLOOR + (1 - RAY_FLOOR) * g))
    rays = zoom_blur(vis, sx / 2, sy / 2, RAY_LENGTH, RAY_SAMPLES)
    rays = zoom_blur(rays, sx / 2, sy / 2, RAY_LENGTH / RAY_SAMPLES * 1.6, 10)
    rays = cv2.GaussianBlur(rays, (0, 0), 0.8) * gmix * RAY_GAIN * p['ray_k'] / (1.0 + (r / (RAY_REACH * rs)) ** 2)
    rays *= 1.0 - near * (1.0 - haze(t, moff[0][1]))

    bloom = vis * core * CORE_GAIN * p['core_k']
    q = cv2.resize(vis, (HW // 2, HH // 2), interpolation=cv2.INTER_AREA)
    for sig, gain in BLOOM:
        b = cv2.GaussianBlur(q, (0, 0), max(0.5, sig * rl / 4.0))
        bloom += cv2.resize(b, (HW, HH), interpolation=cv2.INTER_LINEAR) * gain * p['core_k']

    rays_f = cv2.resize(rays, (W, H), interpolation=cv2.INTER_LINEAR)
    bloom_f = cv2.resize(bloom, (W, H), interpolation=cv2.INTER_LINEAR)

    # rim: inner edge band x the light just outside it, on edges that face the source
    outside = (rays_f + bloom_f) * (1.0 - a)
    lout = cv2.GaussianBlur(outside, (0, 0), 9.0 * sw) / (cv2.GaussianBlur(1.0 - a, (0, 0), 9.0 * sw) + 0.05)
    asoft = cv2.GaussianBlur(a, (0, 0), 4.0 * sw)
    gx = cv2.Sobel(asoft, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(asoft, cv2.CV_32F, 0, 1, ksize=3)
    gn = cv2.magnitude(gx, gy) + 1e-5
    fdx = sx - XF
    fdy = sy - YF
    fr_ = cv2.magnitude(fdx, fdy) + 1e-3
    facing = np.clip((-(gx * fdx + gy * fdy) / (gn * fr_)) * 1.15 + 0.30, 0, 1)
    hd = cv2.magnitude(XF - head_c[0], YF - head_c[1])
    at_head = 1.0 - np.clip((hd - 1.25 * rh) / (1.1 * rh), 0, 1)
    facing = np.maximum(facing, at_head)
    rim = a * (1.0 - cv2.GaussianBlur(a, (0, 0), RIM_W * sw)) * RIM_GAIN
    wrap = a * (1.0 - cv2.GaussianBlur(a, (0, 0), WRAP_W * sw)) * WRAP_GAIN
    edge = (rim + wrap) * lout * facing

    # exposure: room down (never more than a stop), the speaker a little, the face not at all (tight matte)
    at = np.clip((a - 0.30) / 0.62, 0, 1)
    g_bg = 2.0 ** (-p['dim_stops'] * k_dim)
    g_s = 2.0 ** (-SUBJ_STOPS * k_dim)
    g_f = 2.0 ** (-FACE_STOPS * k_dim)
    face = np.exp(-(hd / (1.2 * rh)) ** 2)
    g_subj = g_s + (g_f - g_s) * face
    gain = g_bg + (g_subj - g_bg) * at

    lr = rays_f * (1.0 - a * (1.0 - RAY_SUBJECT))
    lb = bloom_f * (1.0 - a * (1.0 - BLOOM_SUBJECT))
    if motes is not None:
        lr = lr + motes.draw(moff[0], moff[1], t, rays_f) * (1.0 - a * 0.9) * MOTE_GAIN

    light = (lr[..., None] * TINT_RAYS + (lb + edge * RIM_SPEC)[..., None] * TINT_CORE) * kl
    base = lin * (gain * (1.0 + edge * RIM_DIFFUSE * kl))[..., None]
    if p.get('grade'):
        base = base * (1.0 + (WARM - 1.0) * (k_dim * (1.0 - at))[..., None])
    out = 1.0 - (1.0 - base) * np.exp(-light)                 # screen with a soft shoulder: never clips
    out = np.clip(out, 0, 1) ** (1 / 2.2) * 255.0
    out += rng.random(out.shape, dtype=np.float32) - 0.5      # sub-LSB dither against banding in the glow
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------------------------------- fonts + words
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
    f = ImageFont.truetype(path, px)
    try:
        vals = []
        for ax in f.get_variation_axes():
            name = ax['name'].decode() if isinstance(ax['name'], bytes) else str(ax['name'])
            v = weight if name.lower().startswith('weight') else ax['default']
            vals.append(max(ax['minimum'], min(ax['maximum'], v)))
        f.set_variation_by_axes(vals)
    except Exception:
        pass                                    # a static face: the weight is whatever the file is
    return f


def line_mask(text, spec, size, track_em=0.0):
    """Set one line centred on x = W/2, middle at y = 0 of a tall canvas. Returns (mask HxW-band float, width)."""
    font = load_font(spec, size)
    img = Image.new('L', (W, 4 * size), 0)
    d = ImageDraw.Draw(img)
    if track_em:
        ws = [d.textlength(ch, font=font) for ch in text]
        total = sum(ws) + track_em * size * (len(text) - 1)
        x = (W - total) / 2
        for ch, wch in zip(text, ws):
            d.text((x, 2 * size), ch, font=font, fill=255, anchor='lm')
            x += wch + track_em * size
    else:
        total = d.textlength(text, font=font)
        d.text((W / 2, 2 * size), text, font=font, fill=255, anchor='mm')
    return np.asarray(img, np.float32) / 255.0, total


def make_text_layers(p):
    """plan['text'] -> [(mask crop, box, t_in, colour)]. Each line is drawn at its centre y."""
    layers = []
    for ln in p.get('text', []):
        m, _ = line_mask(ln['text'], ln['font'], ln['size'], ln['track'])
        ys, xs = np.where(m > 0.01)
        if not len(ys):
            continue
        y_off = int(round(ln['cy'] - 2 * ln['size']))
        pad = 70
        x0, x1 = max(0, xs.min() - pad), min(W, xs.max() + pad)
        y0, y1 = max(0, ys.min() - pad), min(m.shape[0], ys.max() + pad)
        crop = m[y0:y1, x0:x1].copy()
        box = (x0, y0 + y_off, x1, y1 + y_off)
        layers.append((crop, box, ln['t_in'], np.array(ln['colour'], np.float32), ln.get('shadow', 0.5)))
    return layers


def draw_text(out, layers, t, t_text_out):
    for m, box, t_in, col, shadow in layers:
        x = (t - t_in) / TEXT_IN
        if x <= 0:
            continue
        k_in = 1.0 - (1.0 - min(1.0, x)) ** 3
        k_out = 1.0 - smooth((t - t_text_out) / TEXT_FADE_OUT)
        op = k_in * k_out
        if op <= 0.003:
            continue
        blur = 0.6 + 7.0 * (1.0 - k_in) ** 2 + 3.0 * (1.0 - k_out)        # pulls into focus, drifts out of it
        rise = 9.0 * (1.0 - k_in) - 5.0 * (t - t_in) / 1.2                 # settles, then floats up slowly
        mm = cv2.GaussianBlur(m, (0, 0), blur)
        mm = cv2.warpAffine(mm, np.float32([[1, 0, 0], [0, 1, rise]]), (mm.shape[1], mm.shape[0]), flags=cv2.INTER_LINEAR)
        sh = cv2.GaussianBlur(mm, (0, 0), 11.0)
        sh = cv2.warpAffine(sh, np.float32([[1, 0, 0], [0, 1, 5]]), (sh.shape[1], sh.shape[0]))
        glow = cv2.GaussianBlur(mm, (0, 0), 16.0)
        x0, y0, x1, y1 = box
        cy0, cy1 = max(0, y0), min(H, y1)
        if cy1 <= cy0:
            continue
        sl = slice(cy0 - y0, cy1 - y0)
        reg = out[cy0:cy1, x0:x1].astype(np.float32)
        reg *= (1.0 - np.clip(sh[sl] * 1.5, 0, 1) * shadow * op * op)[..., None]
        if col.mean() > 128:
            reg += (glow[sl] * 0.22 * op)[..., None] * col
        aa = (mm[sl] * op)[..., None]
        reg = reg * (1 - aa) + col * aa
        out[cy0:cy1, x0:x1] = np.clip(reg + 0.5, 0, 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------------------------------------------- the frame
class Scene:
    def __init__(self, p, track_path):
        self.p = p
        z = np.load(track_path)
        self.f0 = int(z['f0'])
        self.head, self.off, self.hoff = z['head'], z['off'], z['hoff']
        self.motes = Motes(self.off, self.hoff)
        self.layers = make_text_layers(p)

    def frame(self, f, rgb, alpha):
        p = self.p
        t = f / FPS
        kl, kd = env_light(p, t), env_dim(p, t)
        out = rgb.copy()
        if kl > 1e-4 or kd > 1e-4:
            n = len(self.head)
            i = min(n - 1, max(0, f - self.f0))
            j = max(0, i - 1)
            cx, cy, rh = (float(v) for v in self.head[i])
            src = (cx + SOURCE_OFFSET[0] * rh + p['source_shift'][0], cy + SOURCE_OFFSET[1] * rh + p['source_shift'][1])
            rng = np.random.default_rng(SEED * 1000 + f)
            out = god_rays(p, rgb, alpha, src, rh, kl, kd, env_open(p, t), t, (cx, cy), self.motes,
                           ((self.off[i], self.hoff[i]), (self.off[j], self.hoff[j])), rng)
        if self.layers:
            out = draw_text(out, self.layers, t, p['t_text_out'])
        return out


def safe_guide(img):
    g = img.copy()
    cv2.rectangle(g, (35, 220), (W - 35, 1470), (255, 60, 60), 2)
    cv2.rectangle(g, (W - 100, 1155), (W - 35, 1470), (255, 60, 60), 2)
    return g


# ---------------------------------------------------------------------------------------------------- sounds
SR = 48000


def _wav(path, x):
    x = np.clip(x, -0.9, 0.9)
    st = np.stack([x, x], axis=1)
    with wave.open(path, 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((st * 32767).astype('<i2').tobytes())


def make_sfx(folder, p):
    """Three quiet cues synthesised from fixed seeds (the same files every build), each starting at its cue time:
    an air swell under the bloom, one low soft thump on the word, a faint hum while the source is on.
    Returns {key: (path, start_s, length_s)}."""
    os.makedirs(folder, exist_ok=True)
    tl, to = p['t_light'], p['t_out']
    out = {}
    # air: soft band of noise around 220 Hz, up with the bloom, gone with the light
    t0 = tl - 0.07
    n = int((to + FALL + 0.5 - t0) * SR)
    rng = np.random.RandomState(3)
    sp = np.fft.rfft(rng.randn(n))
    fq = np.fft.rfftfreq(n, 1 / SR)
    shape = (fq / 220.0) / (1 + (fq / 220.0) ** 2) * 2.0 / (1 + (fq / 900.0) ** 4)
    x = np.fft.irfft(sp * shape, n)
    x /= np.abs(x).max()
    tt = np.arange(n) / SR
    up = np.clip(tt / 0.55, 0, 1)
    up = up * up * (3 - 2 * up)
    dn = np.clip((tt - (to - 0.25 - t0)) / (FALL + 0.45), 0, 1)
    dn = 1 - dn * dn * (3 - 2 * dn)
    peak = np.exp(-((tt - 0.38) / 0.30) ** 2) * 0.8 + 0.45
    _wav(os.path.join(folder, 'god-air.wav'), x * up * dn * peak * 0.050)
    out['air'] = ('assets_fx/god-air.wav', t0, n / SR)
    # thump: one low soft hit on the word
    n = int(1.0 * SR)
    tt = np.arange(n) / SR
    env = (1 - np.exp(-tt / 0.012)) * np.exp(-tt / 0.26)
    ph = 2 * np.pi * (46 * tt + (72 - 46) * 0.10 * (1 - np.exp(-tt / 0.10)))
    body = np.sin(ph) + 0.30 * np.sin(2 * ph) * np.exp(-tt / 0.12)
    x = body * env * np.clip((1.0 - tt) / 0.1, 0, 1)
    _wav(os.path.join(folder, 'god-thump.wav'), x * 0.115)
    out['thump'] = ('assets_fx/god-thump.wav', p['t_word'] - 0.01, 1.0)
    # hum: faint, only while the source is on
    t0 = tl + 0.09
    n = int(max(0.3, to + FALL - t0) * SR)
    tt = np.arange(n) / SR
    up = np.clip(tt / 0.5, 0, 1)
    dn = 1 - np.clip((tt - (to - t0)) / FALL, 0, 1)
    x = np.sin(2 * np.pi * 120 * tt) + 0.5 * np.sin(2 * np.pi * 240 * tt + 0.7) + 0.22 * np.sin(2 * np.pi * 360 * tt + 1.9)
    _wav(os.path.join(folder, 'god-hum.wav'), x * up * dn * 0.012)
    out['hum'] = ('assets_fx/god-hum.wav', t0, n / SR)
    return out
