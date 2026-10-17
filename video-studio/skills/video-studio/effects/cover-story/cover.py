"""cover-story engine: type setting, the page (masthead, labels, cover line, border) and one composited frame.

Shared by build.py (layout + checks) and bake.py (the frame loop). Everything here is driven by work/plan.json, which
build.py writes from the CLIP block and from what it measured on the clip. No clip-specific values live in this file.
"""
import math
import os
import re
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
SS = 4                         # type supersampling
SHUTTER = 0.5                  # motion blur for moving type, in frames
TYPE_OPACITY = 0.965           # a little of the picture comes through the ink
SOFTEN = 0.6                   # px: type is never sharper than the footage
RULE_W, BORDER_W = 2, 2
SAFE = dict(top=220, bottom=1470, side=35, right_low=(1155, 100))

cv2.setNumThreads(1)           # bake.py runs one process per core; threads inside each would fight


# ---------------------------------------------------------------------------------------------------- easing
def clamp01(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def p3out(u):
    return 1 - (1 - clamp01(u)) ** 3


def p4out(u):
    return 1 - (1 - clamp01(u)) ** 4


def p3inout(u):
    u = clamp01(u)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def smoothstep(a, b, x):
    u = np.clip((x - a) / (b - a), 0, 1)
    return u * u * (3 - 2 * u)


def out_at(pl, t):
    """0 while the cover is up, 1 once it has left (the slot hands back plain footage)."""
    if pl['t_out'] is None:
        return 0.0
    return p3inout((t - pl['t_out']) / pl['out_dur'])


def zoom_at(pl, t):
    t0 = pl['t_in'] - 0.12
    z = 1.0 + pl['push'] * p3inout((t - t0) / pl['push_dur'])
    td = t - (t0 + 0.45 * pl['push_dur'])          # the drift fades in under the push so the speed never steps
    if td > 0:
        tau = 0.5
        z += pl['drift'] * (td - tau * (1 - math.exp(-td / tau)))
    return 1.0 + (z - 1.0) * (1 - out_at(pl, t))


def zoom_max(pl):
    return max(zoom_at(pl, f / FPS) for f in range(pl['n']))


def dim_at(pl, t):
    return p3inout((t - (pl['t_in'] - 0.12)) / 1.0) * (1 - out_at(pl, t))


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
    """-> (path, weight) of the closest face of that family. Italic falls back to upright and the other way round."""
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
        axes = f.get_variation_axes()
        vals = []
        for a in axes:
            name = a['name'].decode() if isinstance(a['name'], bytes) else str(a['name'])
            v = weight if name.lower().startswith('weight') else a['default']
            vals.append(max(a['minimum'], min(a['maximum'], v)))
        f.set_variation_by_axes(vals)
    except Exception:
        pass                                    # a static face: the weight is whatever the file is
    return f


def cap_ratio(spec):
    f = load_font(spec, 400)
    return -f.getbbox('H', anchor='ls')[1] / 400.0


def ascent(spec, px):
    return -load_font(spec, px).getbbox('dh', anchor='ls')[1]


# ---------------------------------------------------------------------------------------------------- type setting
def set_line(text, spec, size, track=0.0, groups=None):
    """Set one line. Returns (sprites, w, h, base): float alpha arrays (one per group of character indexes) on one
    ink-tight canvas w x h, base = baseline row inside it. x=0 is the left INK edge, so blocks align optically.
    Kerning from the font's pair table where Pillow exposes it; tracking between pairs, never after the last glyph."""
    f = load_font(spec, size * SS)
    n = len(text)
    xs, pen = [], 0.0
    for i, ch in enumerate(text):
        xs.append(pen)
        adv = f.getlength(ch)
        if i + 1 < n:
            nx = text[i + 1]
            adv += f.getlength(ch + nx) - f.getlength(ch) - f.getlength(nx)
            adv += track * size * SS
        pen += adv
    pad = size * SS
    cw, chh = int(pen + 2 * pad), int(size * SS * 2.4)
    base = int(size * SS * 1.5)
    groups = groups or [set(range(n))]
    ims = []
    for g in groups:
        im = Image.new('L', (cw, chh), 0)
        d = ImageDraw.Draw(im)
        for i in sorted(g):
            if text[i] != ' ':
                d.text((pad + xs[i], base), text[i], font=f, fill=255, anchor='ls')
        ims.append(np.asarray(im, np.float32) / 255.0)
    union = np.max(ims, axis=0)
    cols = np.where(union.max(axis=0) > 0.02)[0]
    rows = np.where(union.max(axis=1) > 0.02)[0]
    x0, x1 = cols[0], cols[-1] + 1
    y0 = rows[0] - ((rows[0] - base) % SS)              # keep the baseline on a whole output row
    y1 = rows[-1] + 1
    x1 += (-(x1 - x0)) % SS
    y1 += (-(y1 - y0)) % SS
    out = []
    for a in ims:
        c = a[y0:y1, x0:x1]
        hh, ww = c.shape
        out.append(c.reshape(hh // SS, SS, ww // SS, SS).mean(axis=(1, 3)))
    return out, (x1 - x0) // SS, (y1 - y0) // SS, (base - y0) // SS


def parse_accent(line):
    """'are *cooked*' -> ('are cooked', {4..9})"""
    out, acc, on = '', set(), False
    for ch in line:
        if ch == '*':
            on = not on
            continue
        if on:
            acc.add(len(out))
        out += ch
    return out, acc


def line_width(text, spec, size, track=0.0):
    return set_line(parse_accent(text)[0], spec, size, track)[1]


def masthead_fit(text, spec, cap, measure):
    """Size by cap height, then justify to the measure (tracking up to 0.30 em). -> (size, track, w)."""
    size = cap / cap_ratio(spec)
    _, w0, _, _ = set_line(text, spec, int(round(size)))
    if w0 > measure:
        size *= measure / w0
        track = 0.0
    else:
        track = min((measure - w0) / max(1, len(text) - 1) / size, 0.30)
    size = int(round(size))
    w = w0
    for _ in range(3):                                   # settle the tracking on the real ink width
        _, w, _, _ = set_line(text, spec, size, track)
        if w <= measure and track >= 0.30:
            break
        track += (measure - w) / max(1, len(text) - 1) / size
        track = min(max(track, -0.03), 0.30)
    _, w, _, _ = set_line(text, spec, size, track)
    return size, track, w


# ---------------------------------------------------------------------------------------------------- the page
class Cover:
    """The page from work/plan.json: elements are sprites with a rest position, a start time and a masked rise. The
    masthead and the label blocks sit BEHIND the speaker (matte), the kicker, cover line and border are printed on top."""

    def __init__(self, pl):
        self.pl = pl
        self.el = []
        self.boxes = []          # (name, x, y, w, h) of every readable block at rest
        F = pl['fonts']
        m = pl['masthead']
        if m:
            size, track = m['size'], m['track']
            groups = [{i} for i, ch in enumerate(m['text']) if ch != ' ']
            sprites, w, h, base = set_line(m['text'], F['mast'], size, track, groups)
            x = m['left'] + (m['measure'] - w) // 2
            y = m['base'] - base
            self.mast_box = (x, y, w, h)
            self.letter_x = []
            for k, a in enumerate(sprites):
                cols = np.where(a.max(axis=0) > 0.1)[0]
                self.letter_x.append((m['text'][sorted(groups[k])[0]], x + int(cols[0]), x + int(cols[-1])))
                self.el.append(dict(a=a, x=x, y=y, ink='back', layer='back', kind='rise', t0=pl['t_in'] - 0.04 + 0.055 * k,
                                    dur=0.95, ease=p3out, tag='mast'))
            self.boxes.append(('masthead', x, y, w, h))
        for lb in pl['labels']:
            self._label(lb)
        if pl['main']:
            self._main(pl['main'])
        self._border()

    def _label(self, lb):
        L = self.pl['label_style']
        x_edge, y_rule, align, layer, t = lb['x_edge'], lb['y_rule'], lb['align'], lb['layer'], lb['t']
        a = np.ones((RULE_W, L['rule_len']), np.float32)
        x = x_edge if align == 'left' else x_edge - L['rule_len']
        self.el.append(dict(a=a, x=x, y=y_rule, ink=layer, layer=layer, kind='wipe', t0=t, dur=0.6, ease=p3out,
                            from_right=(align == 'right'), tag='rule'))
        for k, line in enumerate(lb['text'].split('\n')):
            (a,), w, h, base = set_line(line, self.pl['fonts']['label'], L['size'], L['track'])
            x = x_edge if align == 'left' else x_edge - w
            y = y_rule + L['rule_gap'] + k * L['lead'] - base
            self.el.append(dict(a=a, x=x, y=y, ink=layer, layer=layer, kind='rise', t0=t + 0.12 + 0.09 * k, dur=0.7,
                                ease=p3out, tag='label'))
            self.boxes.append((line, x, y, w, h))

    def _main(self, mn):
        for k, raw in enumerate(mn['lines']):
            line, acc = parse_accent(raw)
            base_set = set(range(len(line))) - acc
            groups = [g for g in (base_set, acc) if g]
            inks = ['front', 'accent'][:len(groups)] if base_set else ['accent']
            sprites, w, h, base = set_line(line, self.pl['fonts']['line'], mn['size'], 0.0, groups)
            x = mn['x']
            y = mn['first_base'] + k * mn['lead'] - base
            for a, ink in zip(sprites, inks):
                self.el.append(dict(a=a, x=x, y=y, ink=ink, layer='front', kind='rise', t0=mn['t'] + 0.14 * k, dur=0.7,
                                    ease=p4out, tag='main'))
            self.boxes.append((line, x, y, w, h))

    def _border(self):
        b = self.pl['border']
        im = Image.new('L', (W * 2, H * 2), 0)
        d = ImageDraw.Draw(im)
        d.rectangle([b * 2, b * 2, (W - b) * 2 - 1, (H - b) * 2 - 1], outline=255, width=BORDER_W * 2)
        self.border_a = np.asarray(im.resize((W, H), Image.BOX), np.float32) / 255.0
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        half_w, side = W / 2 - b, H - 2 * b
        dx = np.abs(xx - W / 2 + 0.5)
        dist = np.where(yy < b + 6, dx, np.where(yy > H - b - 6, half_w + side + (half_w - dx), half_w + (yy - b)))
        self.border_d = dist.astype(np.float32)
        self.border_len = 2 * half_w + side
        self.border_t0, self.border_dur = self.pl['t_in'] - 0.12, 1.25

    def safe_problems(self):
        s, bad = SAFE, []
        for name, x, y, w, h in self.boxes:
            ok = y >= s['top'] and y + h <= s['bottom'] and x >= s['side'] and x + w <= W - s['side']
            if y + h > s['right_low'][0]:
                ok = ok and x + w <= W - s['right_low'][1]
            if not ok:
                bad.append(f'{name!r} at x {x}..{x + w}, y {y}..{y + h}')
        return bad

    # ---- per-frame alpha maps
    def _draw(self, maps, e, t):
        u = (t - e['t0']) / e['dur']
        if u <= 0:
            return
        a = e['a']
        h, w = a.shape
        if e['kind'] == 'wipe':
            p = e['ease'](u)
            xs = np.arange(w, dtype=np.float32) + 0.5
            if e['from_right']:
                xs = w - xs
            a = a * np.clip(p * (w + 6) - xs, 0, 6)[None, :] / 6.0
        elif u < 1:
            rise = h + 2.0
            acc = np.zeros_like(a)
            ns = 6
            for k in range(ns):                       # shutter-averaged: real motion blur on the rise
                tk = t + ((k + 0.5) / ns - 0.5) * SHUTTER / FPS
                dy = rise * (1 - e['ease']((tk - e['t0']) / e['dur']))
                if dy >= rise:
                    continue
                m = np.float32([[1, 0, 0], [0, 1, dy]])
                acc += cv2.warpAffine(a, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                      borderValue=0)
            a = acc / ns
        tgt = maps[e['ink']][e['y']:e['y'] + h, e['x']:e['x'] + w]
        np.maximum(tgt, a, out=tgt)

    def maps(self, t):
        maps = {k: np.zeros((H, W), np.float32) for k in ('back', 'front', 'accent')}
        for e in self.el:
            self._draw(maps, e, t)
        p = p3inout((t - self.border_t0) / self.border_dur)
        maps['border'] = (self.border_a * np.clip((p * (self.border_len + 60) - self.border_d) / 60.0, 0, 1)
                          if p > 0 else None)
        return maps

    def mast_map(self):
        m = np.zeros((H, W), np.float32)
        for e in self.el:
            if e['tag'] == 'mast':
                h, w = e['a'].shape
                tgt = m[e['y']:e['y'] + h, e['x']:e['x'] + w]
                np.maximum(tgt, e['a'], out=tgt)
        return m


# ---------------------------------------------------------------------------------------------------- the picture
def make_dim(pl):
    """Light falls off from the speaker towards the frame edge, and a little more behind the masthead. No matte in
    it, so nothing can ghost around the outline; the face sits in the untouched centre."""
    cx, cy = pl['dim_centre']
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - cx) / 640.0) ** 2 + ((yy - cy) / 1000.0) ** 2)
    v = smoothstep(0.32, 1.22, d)
    top = 1 - smoothstep(170, pl['dim_top_to'], yy)
    side = smoothstep(150, 520, np.abs(xx - pl['zoom_centre'][0]))     # the top falloff stays off the face
    return np.clip(pl['dim_edge'] * v + pl['dim_top'] * top * (0.35 + 0.65 * side), 0, 0.30).astype(np.float32)


def shift_down(a, dy):
    out = np.zeros_like(a)
    out[dy:] = a[:-dy]
    return out


def src_matrix(pl, z, src_w, src_h):
    """Inverse map: output pixel -> source pixel, for a source that aroll.mp4 was made from by scale-to-cover +
    centre crop (aroll_hi.mp4 at native size, or aroll.mp4 itself)."""
    cx, cy = pl['zoom_centre']
    s = max(src_w / W, src_h / H)
    ox, oy = (src_w - W * s) / 2, (src_h - H * s) / 2
    return np.float32([[s / z, 0, ox + s * cx - s * cx / z + 0.5 * s / z - 0.5],
                       [0, s / z, oy + s * cy - s * cy / z + 0.5 * s / z - 0.5]])


def plate_at(pl, src, z):
    if pl['pre_blur'] > 0:
        src = cv2.GaussianBlur(src, (0, 0), pl['pre_blur'])
    m = src_matrix(pl, z, src.shape[1], src.shape[0])
    return cv2.warpAffine(src, m, (W, H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE).astype(np.float32)


class Scene:
    def __init__(self, pl):
        self.pl = pl
        self.cover = Cover(pl)
        self.dim = make_dim(pl)
        self.mast = self.cover.mast_map()
        self.ink = {k: np.array(pl['ink'][k], np.float32) for k in ('back', 'front', 'accent', 'border')}
        self.stats = []

    def active(self, i):
        a, b = self.pl['active']
        return a <= i <= b

    def frame(self, i, plain, src, alpha):
        """plain = the aroll.mp4 frame, src = the frame to resample (aroll_hi or aroll), alpha = cutout plane."""
        pl = self.pl
        if not self.active(i):
            return plain
        t = i / FPS
        z = zoom_at(pl, t)
        plate = plate_at(pl, src, z)
        m_a = src_matrix(pl, z, W, H)
        matte = cv2.warpAffine(alpha, m_a, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_REPLICATE).astype(np.float32) / 255.0
        lo, hi = pl['matte_levels']                     # firm up soft cutout edges (dark hair on a dark wall)
        matte = cv2.GaussianBlur(np.clip((matte - lo) / (hi - lo), 0, 1), (0, 0), 0.8)
        k = dim_at(pl, t)
        if k > 0:
            plate *= (1 - k * self.dim)[..., None]
        if pl['grade'] and k > 0:                       # GRADE=1: a slightly richer print while the cover is up
            g = 0.035 * k
            plate = (plate - 128) * (1 + g) + 128
        fade = 1 - out_at(pl, t)
        if t > pl['t_in'] - 0.2 and fade > 0:
            mp = self.cover.maps(t)
            inv = 1 - matte
            op = TYPE_OPACITY * fade
            # back layer: masthead and label blocks, on the wall behind the speaker
            ab = cv2.GaussianBlur(mp['back'], (0, 0), SOFTEN)
            st, sg, dy = pl['shadow_back']
            if st > 0:
                sh = shift_down(cv2.GaussianBlur(mp['back'], (0, 0), sg), int(dy))
                plate *= (1 - st * fade * sh * inv)[..., None]
            a = (ab * inv * op)[..., None]
            plate = plate * (1 - a) + self.ink['back'] * a
            # front layer: kicker and cover line, printed over the speaker
            af = cv2.GaussianBlur(mp['front'], (0, 0), SOFTEN)
            ac = cv2.GaussianBlur(mp['accent'], (0, 0), SOFTEN)
            st, sg, dy = pl['shadow_front']
            if st > 0:
                sh = shift_down(cv2.GaussianBlur(np.maximum(mp['front'], mp['accent']), (0, 0), sg), int(dy))
                plate *= (1 - st * fade * sh)[..., None]
            a = (af * op)[..., None]
            plate = plate * (1 - a) + self.ink['front'] * a
            a = (ac * op)[..., None]
            plate = plate * (1 - a) + self.ink['accent'] * a
            if mp['border'] is not None:
                a = (cv2.GaussianBlur(mp['border'], (0, 0), 0.5) * 0.88 * fade)[..., None]
                plate = plate * (1 - a) + self.ink['border'] * a
            hid = (self.mast > 0.5) & (matte > 0.5)
            if hid.any() and fade > 0.99:
                top = np.where(hid.any(axis=1))[0][0]
                c0, c1 = pl['masthead']['cap_top'], pl['masthead']['base']
                self.stats.append((i, (c1 - top) / float(c1 - c0), float((self.mast * matte).sum() / self.mast.sum())))
        return np.clip(plate + 0.5, 0, 255).astype(np.uint8)


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


def make_sfx(folder):
    """Two cues, synthesised (seeded, so every build makes the same files) and kept far under the voice: an air
    swell under the masthead, a low thump on the landing."""
    os.makedirs(folder, exist_ok=True)
    rng = np.random.RandomState(7)
    n = int(1.9 * SR)
    spec = np.fft.rfft(rng.randn(n))
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    shape = (fr / 260.0) / (1 + (fr / 260.0) ** 2) * 2            # gentle band around 260 Hz
    shape *= 1 / (1 + (fr / 1400.0) ** 4)                         # nothing bright
    x = np.fft.irfft(spec * shape, n)
    x /= np.abs(x).max()
    tt = np.arange(n) / SR
    env = np.where(tt < 0.85, np.sin(np.clip(tt / 0.85, 0, 1) * np.pi / 2) ** 2.4, np.exp(-(tt - 0.85) / 0.33))
    env *= np.clip((1.9 - tt) / 0.25, 0, 1)
    _wav(os.path.join(folder, 'cover-swell.wav'), x * env * 0.075)
    n = int(0.7 * SR)
    tt = np.arange(n) / SR
    f0 = 46 + 34 * np.exp(-tt / 0.045)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    x = np.sin(ph) * np.exp(-tt / 0.13) + 0.32 * np.sin(2 * ph) * np.exp(-tt / 0.07)
    x *= np.clip(tt / 0.006, 0, 1) * np.clip((0.7 - tt) / 0.1, 0, 1)
    _wav(os.path.join(folder, 'cover-thump.wav'), x / np.abs(x).max() * 0.085)
    return {'swell': ('assets_fx/cover-swell.wav', 1.9), 'thump': ('assets_fx/cover-thump.wav', 0.7)}
