"""word-pile look: slab sprites (the slot's fonts), the drawn floor line, one composed frame, the synthesised sounds.
Used by build.py (sizes, sounds) and bake.py (frames). Everything it needs comes in the plan dict (work/plan.json)."""
import math
import os
import re
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
SS = 2                                   # sprite supersampling
SAFE = dict(top=220, bottom=1470, left=35, right=1045, right_low=980, right_low_y=1155)


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


def pick_font(table, family, weight=900, italic=False):
    faces = [f for f in table if f[0].lower() == family.lower()]
    if not faces:
        have = sorted({f[0] for f in table})
        raise SystemExit(f'font "{family}" is not in assets/fonts/fonts.css. Families there: {", ".join(have)}')
    same = [f for f in faces if f[1] == ('italic' if italic else 'normal')] or faces
    best = min(same, key=lambda f: abs(f[2] - weight))
    return [best[3], weight]


def load_font(spec, px):
    path, weight = spec
    f = ImageFont.truetype(path, int(px))
    try:                                 # a variable font opens at its default weight unless the axis is set
        vals = []
        for a in f.get_variation_axes():
            name = a['name'].decode() if isinstance(a['name'], bytes) else str(a['name'])
            v = weight if name.lower().startswith('weight') else a['default']
            vals.append(max(a['minimum'], min(a['maximum'], v)))
        f.set_variation_by_axes(vals)
    except Exception:
        pass
    return f


def cased(s, case):
    if case == 'upper':
        return s.upper()
    if case == 'lower':
        return s.lower()
    if case == 'title':
        return '\n'.join(' '.join(w[:1].upper() + w[1:].lower() for w in ln.split(' ')) for ln in s.split('\n'))
    return s


def _run(font, s, track):
    """x advance of each glyph with kerning kept, plus tracking (em fraction)."""
    xs, x = [], 0.0
    em = font.size
    for i, c in enumerate(s):
        xs.append(x)
        x += (font.getlength(s[i:i + 2]) - font.getlength(s[i + 1:i + 2]) if i + 1 < len(s) else font.getlength(c)) + track * em
    return xs, x - (track * em if s else 0)


# ---------------------------------------------------------------------------------------------------- sprites
def shade(c, k):
    return tuple(int(max(0, min(255, v * k))) for v in c)


def slab_style(pl, heavy):
    lk = pl['look']
    if heavy:
        top = tuple(lk['accent'])
        return dict(top=shade(top, 1.01), bot=shade(top, 0.93), side=shade(top, 0.62), text=tuple(lk['accent_ink']), hi=0.45, rim=0.0)
    top = tuple(lk['slab'])
    return dict(top=shade(top, 1.25), bot=shade(top, 0.70), side=shade(top, 0.2), text=tuple(lk['ink']), hi=0.16, rim=lk['rim'])


def make_sprite(pl, text, heavy, size_only=False):
    lk = pl['look']
    st = slab_style(pl, heavy)
    spec = lk['font']
    px = pl['type_px'] * (lk['heavy_scale'] if heavy else 1.0)
    pad_x, pad_y, radius = px * 0.52, px * 0.47, px * 0.38
    lines = cased(text, lk['case']).split('\n')
    k = SS * 2
    f1 = load_font(spec, px * k)
    fonts = [f1]
    if len(lines) > 1:                   # second line scaled to the first line's width (the demo's stacked slab)
        w1 = _run(f1, lines[0], lk['track'])[1]
        for ln in lines[1:]:
            wl = _run(f1, ln, lk['track'])[1]
            fonts.append(load_font(spec, max(8, round(px * k * min(1.35, w1 / max(1.0, wl))))))
    gap = px * 0.25
    caps = [f.getbbox('H') for f in fonts]
    caph = [c[3] - c[1] for c in caps]
    widths = [_run(f, ln, lk['track'])[1] for f, ln in zip(fonts, lines)]
    w = int(math.ceil(max(widths) / k + 2 * pad_x))
    h = int(math.ceil(sum(caph) / k + gap * (len(lines) - 1) + 2 * pad_y))
    if size_only:
        return dict(w=w, h=h)
    Wk, Hk = w * k, h * k
    grad = np.linspace(0, 1, Hk, dtype=np.float32)[:, None, None]
    face = np.repeat(np.array(st['top'], np.float32) * (1 - grad) + np.array(st['bot'], np.float32) * grad, Wk, axis=1)
    img = Image.fromarray(face.astype(np.uint8), 'RGB').convert('RGBA')
    hi = Image.new('L', (Wk, Hk), 0)
    ImageDraw.Draw(hi).rounded_rectangle((k * 2, k * 2, Wk - k * 2, Hk - k * 2), radius=(radius - 2) * k, outline=255, width=int(k * 1.5))
    fade = np.clip(1 - np.linspace(0, 1, Hk, dtype=np.float32) * 2.2, 0, 1)[:, None]
    hi = Image.fromarray((np.asarray(hi, np.float32) * fade * st['hi']).astype(np.uint8), 'L')
    img.paste(Image.new('RGBA', (Wk, Hk), (255, 255, 255, 255)), (0, 0), hi)
    if st['rim']:                        # faint full outline: a dark slab still separates from dark clothes
        rm = Image.new('L', (Wk, Hk), 0)
        ImageDraw.Draw(rm).rounded_rectangle((k, k, Wk - k, Hk - k), radius=(radius - 1) * k, outline=int(255 * st['rim']), width=int(k * 1.5))
        img.paste(Image.new('RGBA', (Wk, Hk), tuple(lk['line']) + (255,)), (0, 0), rm)
    d = ImageDraw.Draw(img)
    y = pad_y * k
    for f, ln, cb, ch_, wd in zip(fonts, lines, caps, caph, widths):
        xs, _ = _run(f, ln, lk['track'])
        x0 = (Wk - wd) / 2
        for c, xo in zip(ln, xs):
            d.text((x0 + xo, y - cb[1]), c, font=f, fill=st['text'] + (255,))
        y += ch_ + gap * k
    mask = Image.new('L', (Wk, Hk), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, Wk - 1, Hk - 1), radius=radius * k, fill=255)
    img.putalpha(mask)
    img = img.resize((w * SS, h * SS), Image.LANCZOS)
    rgba = np.asarray(img, np.float32) / 255.0
    rgba[:, :, :3] *= rgba[:, :, 3:4]    # premultiplied
    return dict(w=w, h=h, rgba=rgba, side=np.array(st['side'], np.float32) / 255.0)


# ---------------------------------------------------------------------------------------------------- composing
def slab_layer(s, poses, thick):
    w, h = s['w'], s['h']
    diag = math.hypot(w, h) / 2 + thick + 4
    xs, ys = [p[0] for p in poses], [p[1] for p in poses]
    x0, y0 = int(math.floor(min(xs) - diag)), int(math.floor(min(ys) - diag))
    x1, y1 = int(math.ceil(max(xs) + diag)), int(math.ceil(max(ys) + diag))
    if x1 < -200 or x0 > W + 200 or y1 < -200 or y0 > H + 200:
        return None
    rw, rh = x1 - x0, y1 - y0
    acc = np.zeros((rh, rw, 4), np.float32)
    ker = np.ones((thick + 1, 1), np.uint8)
    for (x, y, a) in poses:
        c, sn = math.cos(a) / SS, math.sin(a) / SS
        cx, cy = w * SS / 2, h * SS / 2
        M = np.array([[c, -sn, x - x0 - (c * cx - sn * cy)], [sn, c, y - y0 - (sn * cx + c * cy)]], np.float32)
        face = cv2.warpAffine(s['rgba'], M, (rw, rh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        fa = face[:, :, 3]
        sa = cv2.dilate(fa, ker, anchor=(0, thick))          # extrude straight down: we look up at the slab's underside
        lay = np.empty_like(face)
        lay[:, :, :3] = face[:, :, :3] + s['side'][None, None, :] * (sa * (1 - fa))[:, :, None]
        lay[:, :, 3] = fa + sa * (1 - fa)
        acc += lay
    acc /= len(poses)
    return x0, y0, acc


def comp_slab(canvas, s, poses, speed, thick):
    r = slab_layer(s, poses, thick)
    if r is None:
        return
    x0, y0, lay = r
    pad = 110
    rh, rw = lay.shape[:2]
    big = np.zeros((rh + 2 * pad, rw + 2 * pad), np.float32)
    big[pad:pad + rh, pad:pad + rw] = lay[:, :, 3]
    settle = float(np.clip(1.0 - speed / 2600.0, 0.35, 1.0))

    def sh(dx, dy, sig, op):
        return cv2.GaussianBlur(cv2.warpAffine(big, np.float32([[1, 0, dx], [0, 1, dy]]), (big.shape[1], big.shape[0])), (0, 0), sig) * op

    shadow = 1 - (1 - sh(5, 15, 9, 0.46 * settle)) * (1 - sh(10, 34, 30, 0.26 * settle))
    X0, Y0 = x0 - pad, y0 - pad
    cx0, cy0, cx1, cy1 = max(0, X0), max(0, Y0), min(W, X0 + big.shape[1]), min(H, Y0 + big.shape[0])
    if cx1 <= cx0 or cy1 <= cy0:
        return
    sub = canvas[cy0:cy1, cx0:cx1]
    shc = shadow[cy0 - Y0:cy1 - Y0, cx0 - X0:cx1 - X0, None]
    full = np.zeros((big.shape[0], big.shape[1], 4), np.float32)
    full[pad:pad + rh, pad:pad + rw] = lay
    lc = full[cy0 - Y0:cy1 - Y0, cx0 - X0:cx1 - X0]
    sub[:] = sub * (1 - shc) + np.array([8, 9, 14], np.float32) / 255.0 * shc
    sub[:] = sub * (1 - lc[:, :, 3:4]) + lc[:, :, :3]


def line_dip(pl, x, t):
    """Sag of the floor line (px, down) at x: each landing presses it down and it rings out in ~0.3 s."""
    L = pl['line']
    d = 0.0
    for ev, w, hv in zip(pl['events'], pl['sizes'], pl['heavy']):
        tf = ev['floor_t']
        if tf is None:
            continue
        tau = t - tf
        if 0 <= tau < 0.45:
            amp = L['dip_px'] * (1.0 if hv else 0.4)
            d = d + amp * math.exp(-tau / 0.085) * math.cos(2 * math.pi * 6.5 * tau) * np.exp(-0.5 * ((x - ev['floor_x']) / (0.55 * w['w'])) ** 2)
    return d


def draw_floor_line(pl, canvas, t):
    """The graphic floor: draws itself, dips under landings, leaves after the gust. Returns True if drawn."""
    L = pl['line']
    p = (t - L['t_draw']) / L['draw_s']
    if p <= 0:
        return False
    e = 1 - (1 - min(1.0, p)) ** 4
    if L['draw_dir'] > 0:
        xa, xb = L['x0'], L['x0'] + (L['x1'] - L['x0']) * e
    else:
        xa, xb = L['x1'] - (L['x1'] - L['x0']) * e, L['x1']
    fade_a = fade_b = 0.0
    if p < 1:
        if L['draw_dir'] > 0:
            fade_b = 70.0 * (1 - e) + 6
        else:
            fade_a = 70.0 * (1 - e) + 6
    u = (t - L['t_undraw']) / L['undraw_s']
    if u > 0:
        u = min(1.0, u)
        g = u * u * (3 - 2 * u)
        if L['undraw_dir'] < 0:          # the pile left to the left: the line is pulled out after it
            xb = L['x1'] - (L['x1'] - L['x0']) * g
            fade_b = 50.0 * math.sin(math.pi * u) + 4
        else:
            xa = L['x0'] + (L['x1'] - L['x0']) * g
            fade_a = 50.0 * math.sin(math.pi * u) + 4
    if xb - xa < 2:
        return False
    y0, y1 = int(L['y'] - 24), int(L['y'] + 36)
    xcol = np.arange(W, dtype=np.float32)
    yc = np.full(W, L['y'] - y0, np.float32) + line_dip(pl, np.clip(xcol, xa, xb), t)
    dx = np.where(xcol < xa, xa - xcol, np.where(xcol > xb, xcol - xb, 0.0))
    rows = np.arange(y1 - y0, dtype=np.float32)[:, None]
    m = np.clip(L['px'] / 2 + 0.5 - np.hypot(rows - yc[None, :], dx[None, :]), 0, 1).astype(np.float32)
    xx = xcol[None, :]
    if fade_b:
        m *= np.clip((xb - xx) / fade_b, 0, 1)
    if fade_a:
        m *= np.clip((xx - xa) / fade_a, 0, 1)
    sh = cv2.GaussianBlur(cv2.warpAffine(m, np.float32([[1, 0, 0], [0, 1, 5]]), (W, m.shape[0])), (0, 0), 4.5) * 0.5
    sub = canvas[y0:y1]
    sub[:] = sub * (1 - sh[:, :, None]) + np.array([8, 9, 14], np.float32) / 255.0 * sh[:, :, None]
    sub[:] = sub * (1 - m[:, :, None]) + np.array(pl['look']['line'], np.float32) / 255.0 * m[:, :, None]
    return True


class Scene:
    def __init__(self, pl, track):
        self.pl, self.track = pl, track
        self.spr = [make_sprite(pl, s['text'], s['heavy']) for s in pl['slabs']]
        self.sub = pl['sub']

    def frame(self, f, plate):
        """One finished frame (uint8 RGB) from the plain plate."""
        pl, track, spr, SUB = self.pl, self.track, self.spr, self.sub
        base, last = f * SUB, track.shape[1] - 1
        span = 0.5 * SUB                 # 180 degree shutter
        canvas, drew = None, False
        for i in range(len(spr)):
            p0 = track[i, min(base, last)]
            if np.isnan(p0[0]):
                continue
            p1 = track[i, min(base + int(round(span)), last)]
            if np.isnan(p1[0]):
                p1 = p0
            travel = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) + abs(p1[2] - p0[2]) * math.hypot(spr[i]['w'], spr[i]['h']) / 2
            spd = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * FPS / 0.5
            n = int(np.clip(math.ceil(travel / 2.5), 1, 24))
            ps = []
            for k in range(n):
                u = (k + 0.5) / n * span if n > 1 else 0.0
                a_, fr_ = int(u), u - int(u)
                qa, qb = track[i, min(base + a_, last)], track[i, min(base + a_ + 1, last)]
                if np.isnan(qa[0]):
                    continue
                if np.isnan(qb[0]):
                    qb = qa
                q = qa + (qb - qa) * fr_
                q = q + np.float32([0, line_dip(pl, float(q[0]), f / FPS), 0])   # slabs ride the line's sag
                ps.append(tuple(q))
            if not ps:
                continue
            if canvas is None:
                canvas = plate.astype(np.float32) / 255.0
            comp_slab(canvas, spr[i], ps, spd, pl['thick'])
            drew = True
        if canvas is None:
            canvas = plate.astype(np.float32) / 255.0
        drew = draw_floor_line(pl, canvas, f / FPS) or drew       # the line goes on last: slabs stand ON it
        return np.clip(canvas * 255.0 + 0.5, 0, 255).astype(np.uint8) if drew else plate


def safe_guide(img):
    img = img.copy()
    s, c = SAFE, (255, 40, 40)
    cv2.rectangle(img, (s['left'], s['top']), (s['right'], s['bottom']), c, 2)
    cv2.rectangle(img, (s['right_low'], s['right_low_y']), (W, s['bottom']), c, 2)
    return img


# ---------------------------------------------------------------------------------------------------- sounds
SR = 48000


def _wav(path, x):
    x = np.clip(x, -1, 1)
    st = np.stack([x, x], axis=1)
    with wave.open(path, 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((st * 32767).astype('<i2').tobytes())


def floor_thud(path, f0, dur, gain, seed):
    """Short, low, dull: a damped low body plus a low-passed noise thump. Harmonics and thump sit at 150 to 400 Hz
    so a phone speaker, which drops the fundamental, still plays a thud. Seeded: every build writes the same file."""
    t = np.arange(int(SR * dur)) / SR
    freq = f0 * (1 + 0.6 * np.exp(-t / 0.022))
    ph = 2 * np.pi * np.cumsum(freq) / SR
    body = (np.sin(ph) + 0.8 * np.sin(2 * ph) * np.exp(-t / 0.06) + 0.5 * np.sin(3 * ph) * np.exp(-t / 0.045)
            + 0.3 * np.sin(4 * ph) * np.exp(-t / 0.03)) * np.exp(-t / (dur * 0.2))
    n = np.random.RandomState(seed).standard_normal(len(t) + 800)
    for _ in range(2):
        n = np.convolve(n, np.ones(56) / 56, mode='same')
    n = (n - np.convolve(n, np.ones(400) / 400, mode='same'))[400:400 + len(t)]
    thump = n / (np.abs(n).max() + 1e-9) * np.exp(-t / 0.04)
    x = body / np.abs(body).max() * 0.6 + thump * 0.8
    x = x / (np.abs(x).max() + 1e-9) * gain
    x[:96] *= np.linspace(0, 1, 96)
    x[-480:] *= np.linspace(1, 0, 480)
    _wav(path, x)


def gust(path, dur=0.75, gain=0.5, seed=21):
    """Air rushing past: band-passed noise with a rising then falling centre, seeded."""
    n = int(SR * dur)
    x = np.random.RandomState(seed).standard_normal(n)
    spec = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    spec *= (fr / 700.0) / (1 + (fr / 700.0) ** 2) * 2 / (1 + (fr / 3500.0) ** 4)
    x = np.fft.irfft(spec, n)
    t = np.arange(n) / SR
    env = np.sin(np.clip(t / 0.22, 0, 1) * np.pi / 2) ** 2 * np.exp(-np.maximum(0, t - 0.22) / 0.18)
    x = x / (np.abs(x).max() + 1e-9) * env
    _wav(path, x / (np.abs(x).max() + 1e-9) * gain)
