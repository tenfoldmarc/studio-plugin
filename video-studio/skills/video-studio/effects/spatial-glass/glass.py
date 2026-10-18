"""spatial-glass engine: frosted glass panes floating in the room at three depths. Used by bake.py (the frames).

Every pane shows the LIVE room behind it (a real blur of the picture under it, in linear light so lamps bloom), has a
refracting rim, a specular top edge and throws a soft shadow on whatever is behind it. A slow virtual camera (push +
small sideways orbit) moves the panes against the room with real parallax, and the panes ride the room track, so a
handheld shot keeps them on the wall. The pane flagged 'behind' passes behind the speaker (cutout + clean plate).
Everything here is deterministic. All positions come from work/plan.json (written by build.py).
"""
import math
import os
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
CX0, CY0 = W / 2, H / 2
SS = 3                                  # supersampling of the drawn UI
SAFE = dict(top=220, bottom=1470, side=35, right_low=(1155, 100))
INK_DARK, CREAM = (20, 22, 28), (255, 248, 239)
VEIL = (250, 244, 235)                  # the room light a frosted pane scatters back (warm white)
VEIL_LIN = (np.float32(VEIL) / 255) ** 2.2
LUMA = np.float32([0.2126, 0.7152, 0.0722])
MATERIALS = {
    'light': dict(text=0.90, label=0.66, track=0.11, idle=0.075),
    'smoke': dict(text=0.96, label=0.80, track=0.20, idle=0.14, fixed=(0.36, 0.085)),
}
# generic tile colours for the grid pane (no pictures of anyone): sage, dusty blue, sand, slate, mauve, + ACCENT
TILE_COLS = [(160, 182, 160), (146, 166, 196), (222, 212, 192), (104, 114, 132), (184, 164, 186)]
ARRIVE, ARRIVE_BLUR = 0.58, 13.0
RIM_W, RIM_BEND = 5.0, 12.0
LAMP_REACH, LAMP_SPILL, LAMP_COL = 210.0, 0.10, (1.0, 0.90, 0.72)
HDR = 6.0


# ---------------------------------------------------------------------------------------------------- small maths
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_out(u, p=3.0):
    u = min(max(u, 0.0), 1.0)
    return 1.0 - (1.0 - u) ** p


def ease_io(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * u * (u * (u * 6 - 15) + 10)


def corners():
    return np.float32([[0, 0], [W, 0], [W, H], [0, H]])


def apply_h(hm, pts):
    pts = np.asarray(pts, np.float64)
    return cv2.perspectiveTransform(pts.reshape(1, -1, 2), np.asarray(hm, np.float64))[0]


# ---------------------------------------------------------------------------------------------------- fonts
def font_table(fonts_dir):
    """Every @font-face in the slot's assets/fonts/fonts.css -> [(family, style, weight, path)]."""
    import re
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
    f = ImageFont.truetype(path, max(4, int(round(px))))
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


# ---------------------------------------------------------------------------------------------------- UI drawing
def premult(im):
    a = np.asarray(im).astype(np.float32) / 255
    a[..., :3] *= a[..., 3:4]
    return a


def rgba(col, a):
    return tuple(int(c) for c in col) + (int(round(255 * min(max(a, 0.0), 1.0))),)


def mixc(a, b, s):
    return tuple(int(round(x + (y - x) * s)) for x, y in zip(a, b))


def tint(mask, col, a):
    lay = Image.new('RGBA', mask.size, tuple(int(c) for c in col) + (0,))
    lay.putalpha(mask.point(lambda v: int(v * min(max(a, 0.0), 1.0))))
    return lay


def tracked(d, xy, text, f, fill, tracking):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + tracking * SS
    return x


def fit_font(spec, px, text, max_w):
    """Font of size px, shrunk until text fits max_w (all in SS pixels)."""
    f = load_font(spec, px)
    while text and f.getlength(text) > max_w and px > 10 * SS:
        px *= 0.92
        f = load_font(spec, px)
    return f


class Content:
    """Draws the inside of each pane at SS x, in the pane's own (canonical) pixels. Returns premultiplied RGBA."""
    TW, TH, TGAP, TPAD, TTOP, TR = 102, 136, 13, 30, 66, 11

    def __init__(self, pl):
        self.pl = pl
        st = pl['style']
        self.st = st
        self.ui = MATERIALS[st['material']]
        self.fg = tuple(st['ink'])
        self.accent = tuple(st['accent'])
        self.check_ink = tuple(st['check_ink'])
        self.caps = st['captions']
        self.f_label = load_font(st['font_label'], 15.5 * SS)
        self.font_ui = st['font_ui']
        self.font_serif = st['font_serif']
        self.cache = {}
        self.tiles = self._tiles()

    # -- grid: six generic tiles (soft two-tone gradients with one quiet mark each), no pictures
    def _tiles(self):
        tw, th = self.TW * SS, self.TH * SS
        cols = TILE_COLS + [self.accent]
        order = [0, 1, 5, 2, 3, 4]
        out = []
        yy, xx = np.mgrid[0:th, 0:tw].astype(np.float32)
        for k in range(6):
            c = np.float32(cols[order[k]])
            hi_c, lo_c = c + (255 - c) * 0.28, c * 0.78
            g = np.clip((xx / tw * 0.35 + yy / th * 0.65), 0, 1)[..., None]
            img = hi_c * (1 - g) + lo_c * g
            # one quiet mark per tile: a soft round light, placed differently per tile (seeded by k)
            rng = np.random.RandomState(11 + k)
            mx, my = tw * rng.uniform(0.28, 0.72), th * rng.uniform(0.25, 0.55)
            rr = tw * rng.uniform(0.16, 0.24)
            blob = np.exp(-((xx - mx) ** 2 + (yy - my) ** 2) / (2 * rr * rr))[..., None]
            img = img + (255 - img) * blob * 0.30
            im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert('RGBA')
            d = ImageDraw.Draw(im)                       # two caption-like pills near the bottom
            y0 = th - 30 * SS
            d.rounded_rectangle((12 * SS, y0, tw - 26 * SS, y0 + 5 * SS), 2.5 * SS, fill=(255, 255, 255, 120))
            d.rounded_rectangle((12 * SS, y0 + 10 * SS, tw - 50 * SS, y0 + 15 * SS), 2.5 * SS, fill=(255, 255, 255, 80))
            rim = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
            ImageDraw.Draw(rim).rounded_rectangle((0, 0, tw - 1, th - 1), self.TR * SS, outline=(255, 255, 255, 70),
                                                  width=SS)
            im.alpha_composite(rim)
            m = Image.new('L', (tw, th), 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, tw - 1, th - 1), self.TR * SS, fill=255)
            im.putalpha(m)
            pad = 14 * SS
            sh = Image.new('L', (tw + 2 * pad, th + 2 * pad), 0)
            ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 3 * SS, pad + tw - 1, pad + th - 1 + 3 * SS), self.TR * SS,
                                                 fill=255)
            sh = sh.filter(ImageFilter.GaussianBlur(4.5 * SS))
            out.append((im, sh, pad))
        return out

    def grid(self, pane, t):
        w, h = pane['w'], pane['h']
        c = pane['content']
        states = tuple(round(min(max((t - (c['t0'] + k * 0.075)) / 0.55, 0.0), 1.0), 3) for k in range(6))
        key = ('grid', states)
        if key in self.cache:
            return self.cache[key]
        im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if self.caps and c.get('label'):
            tracked(d, (self.TPAD * SS, 25 * SS), c['label'].upper(), self.f_label, rgba(self.fg, self.ui['label']), 3.6)
        for j in range(3):                                  # a quiet "more" affordance
            cx = (w - self.TPAD - 3 - j * 9) * SS
            d.ellipse((cx - 2 * SS, 31 * SS, cx + 2 * SS, 35 * SS), fill=rgba(self.fg, self.ui['label'] * 0.5))
        for k, (card, sh, pad) in enumerate(self.tiles):
            u = states[k]
            if u <= 0:
                continue
            e = ease_out(u, 3.0)
            a = float(smoothstep(0.0, 0.55, u))
            sc = 0.90 + 0.10 * e
            dy = -18.0 * (1.0 - e)
            col, row = k % 3, k // 3
            cx = (self.TPAD + col * (self.TW + self.TGAP) + self.TW / 2) * SS
            cy = (self.TTOP + row * (self.TH + self.TGAP) + self.TH / 2 + dy) * SS
            cw, chh = max(2, int(round(card.width * sc))), max(2, int(round(card.height * sc)))
            sw, shh = int(round(sh.width * sc)), int(round(sh.height * sc))
            shs = sh.resize((sw, shh), Image.BILINEAR).point(lambda v: int(v * 0.30 * a))
            dark = Image.new('RGBA', (sw, shh), rgba(INK_DARK, 1.0))
            dark.putalpha(shs)
            im.alpha_composite(dark, (int(round(cx - sw / 2)), int(round(cy - shh / 2))))
            c2 = card.resize((cw, chh), Image.LANCZOS) if sc < 0.999 else card.copy()
            if a < 0.999:
                c2.putalpha(c2.getchannel('A').point(lambda v: int(v * a)))
            im.alpha_composite(c2, (int(round(cx - cw / 2)), int(round(cy - chh / 2))))
        self.cache[key] = premult(im)
        return self.cache[key]

    # -- bar: types the step text(s); a later text clears the earlier one first; send pulse after the last
    def bar(self, pane, t):
        w, h = pane['w'], pane['h']
        c = pane['content']
        step = c['type_step']
        cur, n, clear = '', 0, 1.0
        for k, (tt, txt) in enumerate(c['texts']):
            if t >= tt - 0.12:
                cur = txt
                n = int(np.clip(math.floor((t - tt) / step + 1e-6) + 1, 0, len(txt))) if t >= tt else 0
                nxt = c['texts'][k + 1][0] if k + 1 < len(c['texts']) else None
                clear = 1.0 - float(smoothstep(nxt - 0.30, nxt - 0.14, t)) if nxt is not None else 1.0
        t_type0 = c['texts'][0][0]
        t_end = c['texts'][-1][0] + step * len(c['texts'][-1][1])
        typing = t_type0 - 0.05 <= t <= t_end + 0.12
        ca = 1.0 if typing else 0.5 + 0.5 * math.cos(2 * math.pi * (t - t_end) / 1.1)
        ca *= 1.0 - 0.75 * float(smoothstep(c['t_send'], c['t_send'] + 0.4, t))
        s = ease_out((t - c['t_send']) / 0.45, 3.0) if t >= c['t_send'] else 0.0
        press = math.sin(math.pi * min(max((t - c['t_send']) / 0.42, 0.0), 1.0)) ** 2 if t >= c['t_send'] else 0.0
        key = ('bar', cur, n, round(clear, 2), round(ca, 2), round(s, 3), round(press, 3))
        if key in self.cache:
            return self.cache[key]
        im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        txt = cur[:n]
        x0 = 40 * SS
        room = (w - 40 - 100) * SS
        f = fit_font(self.font_ui, 39 * SS, c['longest'], room)
        asc, desc = f.getmetrics()
        ty = h * SS / 2 - (asc + desc) / 2 - 1 * SS
        if self.caps:
            if txt:
                lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
                ImageDraw.Draw(lay).text((x0, ty), txt, font=f, fill=rgba(self.fg, self.ui['text'] * clear))
                im.alpha_composite(lay)
            xc = x0 + f.getlength(txt) + 4 * SS
        else:                                               # CAPTIONS=0: the words become a quiet line that grows
            full = max(1.0, f.getlength(cur))
            ln = full * (n / max(1, len(cur)))
            if ln > 0:
                d.rounded_rectangle((x0, h * SS / 2 - 6 * SS, x0 + ln, h * SS / 2 + 6 * SS), 6 * SS,
                                    fill=rgba(self.fg, 0.30 * clear))
            xc = x0 + ln + 6 * SS
        d.rounded_rectangle((xc, h * SS / 2 - 21 * SS, xc + 2.6 * SS, h * SS / 2 + 21 * SS), 1.3 * SS,
                            fill=rgba(self.fg, 0.90 * ca))
        bx, by, br = (w - 46) * SS, h * SS / 2, 29 * SS * (1.0 - 0.07 * press)
        d.ellipse((bx - br, by - br, bx + br, by + br), fill=rgba(self.fg, self.ui['idle'] * (1 - s)))
        if s > 0:
            lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
            ImageDraw.Draw(lay).ellipse((bx - br, by - br, bx + br, by + br), fill=rgba(self.accent, s))
            im.alpha_composite(lay)
        ia = 0.42 + 0.52 * s
        k = br / (29 * SS)
        aw = 3.3 * SS
        m = Image.new('L', im.size, 0)
        dm = ImageDraw.Draw(m)
        pts = [(bx, by + 11.5 * SS * k), (bx, by - 11.5 * SS * k)]
        head = [(bx - 9.5 * SS * k, by - 2 * SS * k), (bx, by - 11.5 * SS * k), (bx + 9.5 * SS * k, by - 2 * SS * k)]
        dm.line(pts, fill=255, width=int(round(aw)))
        dm.line(head, fill=255, width=int(round(aw)), joint='curve')
        for (px, py) in pts + head:
            dm.ellipse((px - aw / 2, py - aw / 2, px + aw / 2, py + aw / 2), fill=255)
        im.alpha_composite(tint(m, mixc(self.fg, self.check_ink, s), ia))
        self.cache[key] = premult(im)
        return self.cache[key]

    # -- ring: runs while the step is said, resolves to a check
    def ring(self, pane, t):
        w, h = pane['w'], pane['h']
        c = pane['content']
        p0, p1, tc = c['t_prog0'], c['t_prog1'], c['t_check']
        p = ease_io((t - p0) / (p1 - p0)) if t > p0 else 0.0
        p = 0.02 + 0.98 * p if t > p0 else 0.0
        done = ease_out((t - tc) / 0.50, 3.0) if t >= tc else 0.0
        chk = ease_io((t - tc - 0.10) / 0.34) if t >= tc + 0.10 else 0.0
        swap = bool(c.get('done_label'))
        lab_out = float(smoothstep(tc - 0.04, tc + 0.14, t)) if swap else 0.0
        lab_in = ease_out((t - tc - 0.12) / 0.40, 3.0) if (swap and t > tc + 0.12) else 0.0
        key = ('ring', round(p, 4), round(done, 3), round(chk, 3), round(lab_out, 3), round(lab_in, 3))
        if key in self.cache:
            return self.cache[key]
        im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        cx, cy, R, st = w / 2 * SS, 158 * SS, 60 * SS, 7 * SS
        ring_a = 1.0 - done
        d.ellipse((cx - R, cy - R, cx + R, cy + R), outline=rgba(self.fg, self.ui['track'] * ring_a), width=int(st))
        if p > 0 and ring_a > 0:
            a0, a1 = -90.0, -90.0 + 360.0 * p
            m = Image.new('L', im.size, 0)
            dm = ImageDraw.Draw(m)
            dm.arc((cx - R, cy - R, cx + R, cy + R), a0, a1, fill=255, width=int(st))
            for ang in (a0, a1):
                rr = R - st / 2
                px, py = cx + rr * math.cos(math.radians(ang)), cy + rr * math.sin(math.radians(ang))
                dm.ellipse((px - st / 2, py - st / 2, px + st / 2, py + st / 2), fill=255)
            im.alpha_composite(tint(m, self.st['arc'], 0.96 * ring_a))
        if done > 0:
            lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
            rd = R * (0.86 + 0.14 * done)
            ImageDraw.Draw(lay).ellipse((cx - rd, cy - rd, cx + rd, cy + rd),
                                        fill=rgba(self.accent, float(smoothstep(0, 0.7, done))))
            im.alpha_composite(lay)
            d = ImageDraw.Draw(im)
        if chk > 0:
            pts = [(cx + x * SS, cy + y * SS) for x, y in [(-25, 2), (-8, 19), (26, -18)]]
            l1, l2 = math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2])
            run = chk * (l1 + l2)
            path = [pts[0]]
            if run <= l1:
                f = run / l1
                path.append((pts[0][0] + (pts[1][0] - pts[0][0]) * f, pts[0][1] + (pts[1][1] - pts[0][1]) * f))
            else:
                f = (run - l1) / l2
                path += [pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * f, pts[1][1] + (pts[2][1] - pts[1][1]) * f)]
            cw = 7.5 * SS
            d.line(path, fill=rgba(self.check_ink, 1.0), width=int(round(cw)), joint='curve')
            for (px, py) in path:
                d.ellipse((px - cw / 2, py - cw / 2, px + cw / 2, py + cw / 2), fill=rgba(self.check_ink, 1.0))
        if self.caps:
            labs = [(c.get('label', ''), 1.0 - lab_out, -5.0 * lab_out)]
            if swap:
                labs.append((c['done_label'], float(smoothstep(0.0, 0.7, lab_in)), 7.0 * (1.0 - lab_in)))
            longest = max([x[0] for x in labs], key=len)
            f = fit_font(self.font_serif, 44 * SS, longest, (w - 44) * SS)
            for txt, a, dy in labs:
                if not txt or a <= 0.004:
                    continue
                lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
                tw = f.getlength(txt)
                ImageDraw.Draw(lay).text((cx - tw / 2, (246 + dy) * SS), txt, font=f,
                                         fill=rgba(self.fg, self.ui['text'] * a))
                im.alpha_composite(lay)
        self.cache[key] = premult(im)
        return self.cache[key]


# ---------------------------------------------------------------------------------------------------- glass
def disc_kernel(r):
    k = int(math.ceil(r)) * 2 + 1
    c = k // 2
    yy, xx = np.mgrid[0:k, 0:k]
    ker = np.clip(r + 0.5 - np.hypot(xx - c, yy - c), 0.0, 1.0).astype(np.float32)
    return ker / ker.sum()


def local_grid(hm, x0, y0, x1, y1):
    hi = np.linalg.inv(hm)
    gx, gy = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))
    den = hi[2, 0] * gx + hi[2, 1] * gy + hi[2, 2]
    return ((hi[0, 0] * gx + hi[0, 1] * gy + hi[0, 2]) / den).astype(np.float32), \
           ((hi[1, 0] * gx + hi[1, 1] * gy + hi[1, 2]) / den).astype(np.float32)


def rr_sdf(lx, ly, w, h, r):
    qx, qy = np.abs(lx - w / 2) - (w / 2 - r), np.abs(ly - h / 2) - (h / 2 - r)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def quad_scale(q, w, h):
    return 0.5 * (float(np.linalg.norm(q[1] - q[0])) / w + float(np.linalg.norm(q[3] - q[0])) / h)


def crop_reflect(img, x0, y0, x1, y1):
    hh, ww = img.shape[:2]
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, ww), min(y1, hh)
    if cx1 <= cx0 or cy1 <= cy0:
        return np.zeros((y1 - y0, x1 - x0) + img.shape[2:], img.dtype)
    c = img[cy0:cy1, cx0:cx1]
    if (cx0, cy0, cx1, cy1) != (x0, y0, x1, y1):
        c = cv2.copyMakeBorder(c, cy0 - y0, y1 - cy1, cx0 - x0, x1 - cx1, cv2.BORDER_REFLECT_101)
    return c


def glass_layer(img, pane, quad, content, t, margin, ui, lamp=None):
    """The pane as a layer over img (float32 RGB 0..255): box, premultiplied linear colour, coverage."""
    w, h, r = pane['w'], pane['h'], pane['r']
    hm = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), quad.astype(np.float32))
    s = quad_scale(quad, w, h)
    x0, y0 = int(math.floor(quad[:, 0].min())) - margin, int(math.floor(quad[:, 1].min())) - margin
    x1, y1 = int(math.ceil(quad[:, 0].max())) + margin + 1, int(math.ceil(quad[:, 1].max())) + margin + 1
    lx, ly = local_grid(hm, x0, y0, x1, y1)
    d = rr_sdf(lx, ly, w, h, r) * s
    gy_, gx_ = np.gradient(d)
    nn = np.maximum(np.hypot(gx_, gy_), 1e-4)
    nx, ny = gx_ / nn, gy_ / nn
    # 1. frost: real blur of what is behind the pane, in linear light so lamps and windows bloom
    sig = pane['frost'] * s
    pad = int(math.ceil(sig * 2.4 * 2.6)) + 2
    back = crop_reflect(img, x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    lin = np.power(np.clip(back, 0, 255) / 255.0, 2.2).astype(np.float32)
    lin *= (1.0 + HDR * smoothstep(0.78, 0.97, lin @ LUMA))[..., None]
    f1 = cv2.GaussianBlur(lin, (0, 0), sig)
    f2 = cv2.GaussianBlur(lin, (0, 0), sig * 2.4)
    frost = (0.70 * f1 + 0.30 * f2)[pad:-pad, pad:-pad]
    lum = frost @ LUMA
    frost = lum[..., None] + (frost - lum[..., None]) * 0.84
    if 'fixed' in ui:
        glass = frost * ui['fixed'][0] + VEIL_LIN * ui['fixed'][1]
    else:
        glass = frost * pane['trans'] + VEIL_LIN * (1.0 - pane['trans'])
    g = np.power(np.minimum(glass, 1.0), 1 / 2.2)
    # 2. soft inner gradient + one slow travelling highlight
    v = np.clip(ly / h, 0, 1)
    g += (1.0 - g) * (0.05 * (1.0 - v) ** 1.6)[..., None]
    sweep = (lx + 0.55 * ly) / (w + 0.55 * h)
    c = -0.25 + (t - pane['t_in']) / 5.2 * 1.5
    g += (1.0 - g) * (0.06 * np.exp(-((sweep - c) / 0.20) ** 2))[..., None]
    # 3. rim: a polished bevel that bends the room a few pixels and splits its colour
    rw = RIM_W * max(s, 0.8)
    k = np.clip((rw + d) / rw, 0.0, 1.0) * (d <= 0.5)
    sharp = cv2.GaussianBlur(np.clip(back, 0, 255) / 255.0, (0, 0), 1.3)
    gxm, gym = np.meshgrid(np.arange(x1 - x0, dtype=np.float32) + pad, np.arange(y1 - y0, dtype=np.float32) + pad)
    disp = RIM_BEND * s * k ** 1.5
    rim = np.empty_like(g)
    for ch, cc in enumerate((0.78, 1.0, 1.26)):
        rim[..., ch] = cv2.remap(sharp[..., ch].astype(np.float32), gxm - nx * disp * cc, gym - ny * disp * cc,
                                 cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    rim = rim * 0.97 + 0.03
    m = (k ** 1.2 * 0.90)[..., None]
    g = g * (1.0 - m) + rim * m
    # 4. edge light: specular on the top edge, a faint line all round, more of it near a lamp in shot
    line = np.exp(-((d + 0.9) / 0.75) ** 2)
    top, bot = np.clip(-ny, 0, 1), np.clip(ny, 0, 1)
    near = 0.0
    if lamp is not None:
        gxo, gyo = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))
        near = 1.0 / (1.0 + ((gxo - lamp[0]) ** 2 + (gyo - lamp[1]) ** 2) / (LAMP_REACH * s) ** 2)
        g += (np.float32(LAMP_COL) - g) * (LAMP_SPILL * near ** 2 * np.clip(-d / 3.0, 0, 1))[..., None]
    spec = np.clip(line * (0.16 + 0.62 * top ** 1.5 + 0.10 * bot ** 2) * (0.85 + 1.2 * near), 0, 1)[..., None]
    g = g + (np.float32([1.0, 0.985, 0.955]) - g) * spec
    g += (1.0 - g) * (np.exp(np.minimum(d, 0) / 5.0) * (d <= 0) * top * 0.09)[..., None]
    g *= 1.0 - (line * bot ** 1.6 * 0.05)[..., None]
    # 5. the UI on the glass
    if content is not None:
        blur = 0.42 * SS / max(s, 0.5)
        spr = cv2.GaussianBlur(content, (0, 0), blur)
        hc = np.float64([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]]) @ hm.astype(np.float64) @ \
            np.float64([[1 / SS, 0, 0.5 / SS - 0.5], [0, 1 / SS, 0.5 / SS - 0.5], [0, 0, 1]])
        uiw = cv2.warpPerspective(spr, hc, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=0)
        g = g * (1.0 - uiw[..., 3:4]) + uiw[..., :3]
    cov = np.clip(0.5 - d, 0.0, 1.0).astype(np.float32)
    lin_p = np.power(np.clip(g, 0, 1), 2.2).astype(np.float32) * cov[..., None]
    return (x0, y0, x1, y1), lin_p, cov


def glass_over(img, pane, quad, content, t, alpha, blur_r, ui, lamp=None):
    margin = int(math.ceil(blur_r)) + 3
    (x0, y0, x1, y1), lin_p, cov = glass_layer(img, pane, quad, content, t, margin, ui, lamp)
    if blur_r > 0.25:
        ker = disc_kernel(blur_r)
        lin_p = cv2.filter2D(lin_p, -1, ker, borderType=cv2.BORDER_CONSTANT)
        cov = cv2.filter2D(cov, -1, ker, borderType=cv2.BORDER_CONSTANT)
    soft = pane.get('soft', 0.0)
    if soft > 0:
        lin_p = cv2.GaussianBlur(lin_p, (0, 0), soft)
        cov = cv2.GaussianBlur(cov, (0, 0), soft)
    cov = np.clip(cov, 0.0, 1.0)                            # filter2D goes through an FFT: tiny negatives
    col = np.power(np.maximum(lin_p, 0.0) / np.maximum(cov, 1e-4)[..., None], 1 / 2.2) * 255.0
    a = (cov * alpha)[..., None]
    hh, ww = img.shape[:2]
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, ww), min(y1, hh)
    if cx1 <= cx0 or cy1 <= cy0:
        return
    sl = (slice(cy0 - y0, cy1 - y0), slice(cx0 - x0, cx1 - x0))
    img[cy0:cy1, cx0:cx1] = img[cy0:cy1, cx0:cx1] * (1.0 - a[sl]) + col[sl] * a[sl]


def shadow_on(img, pane, quad, sigma, strength):
    w, h, r = pane['w'], pane['h'], pane['r']
    hm = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), quad.astype(np.float32))
    s = quad_scale(quad, w, h)
    pad = int(math.ceil(sigma * 3)) + 2
    hh, ww = img.shape[:2]
    x0, y0 = max(int(math.floor(quad[:, 0].min())) - pad, 0), max(int(math.floor(quad[:, 1].min())) - pad, 0)
    x1, y1 = min(int(math.ceil(quad[:, 0].max())) + pad, ww), min(int(math.ceil(quad[:, 1].max())) + pad, hh)
    if x1 <= x0 or y1 <= y0:
        return
    lx, ly = local_grid(hm, x0, y0, x1, y1)
    m = np.clip(0.5 - rr_sdf(lx, ly, w, h, r) * s, 0.0, 1.0).astype(np.float32)
    wide = cv2.GaussianBlur(m, (0, 0), sigma, borderType=cv2.BORDER_CONSTANT)
    tight = cv2.GaussianBlur(m, (0, 0), sigma * 0.36, borderType=cv2.BORDER_CONSTANT)
    sh = strength * (0.72 * wide + 0.28 * tight)
    img[y0:y1, x0:x1] *= (1.0 - sh[..., None] * np.float32([1.0, 0.985, 0.96]))


# ---------------------------------------------------------------------------------------------------- camera
class Camera:
    """camera(drift): a dolly-in plus a sideways slide that yaws to keep the wall centred (a small orbit).
    The footage is the plane z = wall; anything nearer moves more. env(t) brings it back to the untouched picture
    at both edges of the slot."""

    def __init__(self, pl):
        c = pl['cam']
        self.f, self.wall, self.push, self.truck = c['f'], c['wall'], c['push'], c['truck']
        self.t0, self.t1, self.ease = c['t0'], c['t1'], c['ease']
        self.base, self.shift = c['base'], tuple(c['shift'])
        self.env_t = pl['env']                                     # [in0, in1, out0, out1] (out None = holds)

    def env(self, t):
        a0, a1, b0, b1 = self.env_t
        e = float(smoothstep(a0, a1, t))
        if b0 is not None:
            e *= 1.0 - float(smoothstep(b0, b1, t))
        return e

    def pose(self, t):
        u = min(max((t - self.t0) / max(self.t1 - self.t0, 1e-3), 0.0), 1.0)
        p = 1.0 - (1.0 - u) ** self.ease
        d = self.wall * (1.0 - 1.0 / (1.0 + self.push)) * p
        tx = self.truck * p
        th = math.atan2(-tx, self.wall - d)
        return tx, d, th

    def world(self, u, v, z):
        return np.stack([(np.asarray(u, np.float64) - CX0) * z / self.f,
                         (np.asarray(v, np.float64) - CY0) * z / self.f,
                         np.full(np.shape(u), z, np.float64)], -1)

    def project(self, X, t, base=None, shift=None):
        tx, d, th = self.pose(t)
        x, y, z = X[..., 0] - tx, X[..., 1], X[..., 2] - d
        c, s = math.cos(th), math.sin(th)
        xc, zc = c * x - s * z, s * x + c * z
        fo = self.f * (self.base if base is None else base)
        sh = self.shift if shift is None else shift
        return np.stack([CX0 + fo * xc / zc + sh[0], CY0 + fo * y / zc + sh[1]], -1)

    def full_h(self, t):
        """REF picture (wall plane) -> output at full camera move."""
        c = corners()
        return cv2.getPerspectiveTransform(c, self.project(self.world(c[:, 0], c[:, 1], self.wall), t).astype(np.float32))

    def env_h(self, t):
        """The camera actually used for the footage: full move scaled by env(t), identity at the slot edges."""
        e = self.env(t)
        c = corners()
        if e <= 0:
            return np.eye(3), e
        full = apply_h(self.full_h(t), c)
        return cv2.getPerspectiveTransform(c, (c + (full - c) * e).astype(np.float32)).astype(np.float64), e


# ---------------------------------------------------------------------------------------------------- scene
class Scene:
    def __init__(self, pl, here):
        self.pl = pl
        self.cam = Camera(pl)
        self.track = np.load(os.path.join(here, 'work/track.npy'))
        self.n = pl['n']
        self.ui = MATERIALS[pl['style']['material']]
        self.content = Content(pl)
        self.panes = pl['panes']
        self.light = np.float64(pl['light'])
        self.cp = None
        pp = os.path.join(here, 'work/plate.npz')
        if any(p['behind'] for p in self.panes) and os.path.exists(pp):
            pz = np.load(pp)
            self.cp, self.cp_known, self.cp_roi = pz['plate'], pz['known'], pz['roi']

    # -- pane timing + geometry
    def state(self, pane, t):
        u = (t - pane['t_in']) / ARRIVE
        if u <= 0:
            return None
        e = ease_out(u, 3.0)
        sc, al, bl = 0.92 + 0.08 * e, float(smoothstep(0.0, 0.62, u)), ARRIVE_BLUR * (1.0 - ease_out(u, 2.2))
        if pane.get('t_out') is not None and t > pane['t_out']:
            v = (t - pane['t_out']) / self.pl['out_dur']
            if v >= 1:
                return None
            eo = ease_io(v)
            sc *= 1.0 - 0.06 * eo
            al *= 1.0 - eo
            bl += 10.0 * eo
        return dict(scale=sc, alpha=al, blur=bl + pane['defocus'])

    def quads(self, pane, st, t, i):
        """Output corners of the pane and of its shadow (footage camera + room track)."""
        w, h, k = pane['w'], pane['h'], pane['k']
        amp, per, ph = pane['float']
        fy = amp * math.sin(2 * math.pi * (t / per + ph))
        fx = amp * 0.35 * math.sin(2 * math.pi * (t / (per * 1.37) + ph + 0.3))
        lc = np.float64([[0, 0], [w, 0], [w, h], [0, h]])
        u = pane['cx'] + fx + st['scale'] * k * (lc[:, 0] - w / 2)
        v = pane['cy'] + fy + st['scale'] * k * (lc[:, 1] - h / 2)
        X = self.cam.world(u, v, pane['z'])
        L = self.light
        kk = (pane['recv'] - L[2]) / (pane['z'] - L[2])
        Xs = L + (X - L) * kk
        q, qs = self.cam.project(X, t), self.cam.project(Xs, t)
        # stabilised output -> REF picture -> frame i (room track) -> footage camera
        corr = self.ve @ self.track[i] @ np.linalg.inv(self.cam.full_h(t))
        return apply_h(corr, q), apply_h(corr, qs)

    def bbox(self, pane, i):
        t = i / FPS
        st = self.state(pane, t)
        if st is None:
            return None
        self.ve, _ = self.cam.env_h(t)
        q, _ = self.quads(pane, st, t, i)
        return q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()

    def clean_plate(self, i):
        m = self.ve @ self.track[i] @ np.float64([[1, 0, self.cp_roi[0]], [0, 1, self.cp_roi[1]], [0, 0, 1]])
        cp = cv2.warpPerspective(self.cp, m, (W, H), flags=cv2.INTER_LINEAR).astype(np.float32)
        kn = cv2.warpPerspective(self.cp_known, m, (W, H), flags=cv2.INTER_LINEAR).astype(np.float32) / 255
        kn = cv2.erode((kn > 0.995).astype(np.float32), np.ones((5, 5), np.uint8))
        return cp, smoothstep(0.0, 1.0, cv2.GaussianBlur(kn, (0, 0), 1.5)).astype(np.float32)

    def frame(self, i, rgb, alpha):
        t = i / FPS
        self.ve, e = self.cam.env_h(t)
        live = [(p, self.state(p, t)) for p in self.panes]
        live = [(p, s) for p, s in live if s is not None]
        if e <= 0 and not live:
            return rgb                                       # the untouched picture at both edges of the slot
        if e > 0:
            plate = cv2.warpPerspective(rgb, self.ve, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
            a = cv2.warpPerspective(alpha, self.ve, (W, H), flags=cv2.INTER_LINEAR).astype(np.float32) / 255
        else:
            plate, a = rgb, alpha.astype(np.float32) / 255
        out = plate.astype(np.float32)
        lamp = None
        if self.pl.get('lamp'):
            lamp = apply_h(self.ve @ self.track[i], [self.pl['lamp']])[0]
        a_fix = None
        base = self.cam.base
        for pane, st in live:
            quad, squad = self.quads(pane, st, t, i)
            gap = pane['recv'] - pane['z']
            ssig = (11.0 + 15.0 * gap) * base * pane['k']
            sstr = pane['shadow'] * st['alpha']
            content = getattr(self.content, pane['role'])(pane, t)
            behind_glass = pane['behind']
            behind_shadow = pane['behind'] or pane.get('shadow_behind', False)
            if behind_glass or behind_shadow:
                if a_fix is None:
                    if self.cp is not None:
                        cp, kn = self.clean_plate(i)
                    else:
                        cp, kn = out, np.zeros((H, W), np.float32)
                    a_fix = matte(a, out, cp, kn)
                qs = [squad] + ([quad] if behind_glass else [])
                allq = np.concatenate(qs)
                pad = int(max(ssig * 3, pane['frost'] * 2.4 * 2.6 * 1.2 + 8)) + int(st['blur']) + 12
                x0, y0 = max(int(allq[:, 0].min()) - pad, 0), max(int(allq[:, 1].min()) - pad, 0)
                x1, y1 = min(int(allq[:, 0].max()) + pad, W), min(int(allq[:, 1].max()) + pad, H)
                if x1 <= x0 or y1 <= y0:
                    continue
                pc, ac = out[y0:y1, x0:x1], a_fix[y0:y1, x0:x1]
                room = room_fill(pc, ac, cp[y0:y1, x0:x1], kn[y0:y1, x0:x1])
                new = room.copy()
                off = np.float64([x0, y0])
                shadow_on(new, pane, squad - off, ssig, sstr)
                if behind_glass:
                    glass_over(new, pane, quad - off, content, t, st['alpha'], st['blur'], self.ui,
                               None if lamp is None else lamp - off)
                out[y0:y1, x0:x1] = pc + (1.0 - ac[..., None]) * (new - room)
            else:
                shadow_on(out, pane, squad, ssig, sstr)
            if not behind_glass:
                glass_over(out, pane, quad, content, t, st['alpha'], st['blur'], self.ui, lamp)
        if self.pl.get('grade') and e > 0:                  # GRADE=1: a touch of contrast while the panes are up
            out = 128.0 + (out - 128.0) * (1.0 + 0.05 * e)
        return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def matte(a, pic, cp, kn):
    """The speaker's matte for occlusion. Where the clean room is known the picture decides (same as the empty room =
    not the speaker); holes closed, soft outer fringe trimmed, islands not attached to the speaker dropped."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (23, 23))
    closed = cv2.erode(cv2.morphologyEx(a, cv2.MORPH_CLOSE, k), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    a = np.maximum(a, closed)
    if kn.any():
        diff = np.abs(cv2.GaussianBlur(pic, (0, 0), 2.2) - cv2.GaussianBlur(cp, (0, 0), 2.2)).max(axis=2)
        solid = smoothstep(0.80, 0.97, a)
        a1 = a * (solid + (1.0 - solid) * smoothstep(9.0, 22.0, diff))
        a2 = np.maximum(a1, smoothstep(0.20, 0.55, a) * smoothstep(22.0, 48.0, diff))
        a = a * (1.0 - kn) + a2 * kn
    a = cv2.morphologyEx(a.astype(np.float32), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    nlab, lab, stats, _ = cv2.connectedComponentsWithStats((a > 0.12).astype(np.uint8), connectivity=8)
    if nlab > 2:
        keep = np.zeros(nlab, np.float32)
        big = stats[1:, cv2.CC_STAT_AREA]
        keep[1 + np.where(big >= 0.15 * big.max())[0]] = 1.0    # the speaker (and a big detached hand / arm)
        a = a * cv2.GaussianBlur(cv2.dilate(keep[lab], np.ones((5, 5), np.uint8)), (0, 0), 1.2)
    return smoothstep(0.10, 0.90, a).astype(np.float32)


def room_fill(pc, ac, cp, kn):
    """The room without the speaker: clean plate where known, else what is just outside them (normalised blur)."""
    hard = cv2.dilate((ac > 0.02).astype(np.float32), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    wgt = np.clip(1.0 - cv2.GaussianBlur(hard, (0, 0), 2.0), 0, 1)
    fill, have = None, None
    for sig in (7.0, 22.0, 70.0, 200.0):
        num = cv2.GaussianBlur(pc * wgt[..., None], (0, 0), sig)
        den = cv2.GaussianBlur(wgt, (0, 0), sig)
        est = num / np.maximum(den, 1e-4)[..., None]
        conf = smoothstep(0.02, 0.12, den)[..., None]
        if fill is None:
            fill, have = est * conf, conf
        else:
            fill = fill + est * conf * (1 - have)
            have = have + conf * (1 - have)
    fill = fill / np.maximum(have, 1e-4)
    kb = smoothstep(0.5, 1.0, cv2.GaussianBlur(kn, (0, 0), 3.0)[..., None])
    fill = fill * (1.0 - kb) + cp * kb
    m = smoothstep(0.0, 0.10, ac)[..., None]
    return pc * (1 - m) + fill * m


def safe_guide(img):
    img = img.copy()
    s, c = SAFE, (255, 40, 40)
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
    """Synthesised, seeded (every build makes the same files), far under the voice: a soft push of air under each
    pane as it settles (crest 0.32 s in), a low soft thump on the check."""
    os.makedirs(folder, exist_ok=True)
    rng = np.random.RandomState(37)
    n = int(1.3 * SR)
    spec = np.fft.rfft(rng.randn(n))
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    shape = (fr / 300.0) / (1 + (fr / 300.0) ** 2) * 2 / (1 + (fr / 520.0) ** 4)
    x = np.fft.irfft(spec * shape, n)
    x /= np.abs(x).max()
    tt = np.arange(n) / SR
    env = np.where(tt < 0.42, np.sin(np.clip(tt / 0.42, 0, 1) * np.pi / 2) ** 2, np.exp(-(tt - 0.42) / 0.26))
    env *= np.clip((1.3 - tt) / 0.2, 0, 1)
    _wav(os.path.join(folder, 'glass-air.wav'), x * env * 0.024)    # peaks about -32 dBFS
    n = int(0.46 * SR)
    tt = np.arange(n) / SR
    f0 = 52 + 30 * np.exp(-tt / 0.04)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    x = np.sin(ph) * np.exp(-tt / 0.11) + 0.25 * np.sin(2 * ph) * np.exp(-tt / 0.06)
    x *= np.clip(tt / 0.006, 0, 1) * np.clip((0.46 - tt) / 0.1, 0, 1)
    _wav(os.path.join(folder, 'glass-thump.wav'), x / np.abs(x).max() * 0.034)   # about -29 dBFS, mostly below 100 Hz
    return {'air': ('assets_fx/glass-air.wav', 1.3, 0.32), 'thump': ('assets_fx/glass-thump.wav', 0.46, 0.0)}
