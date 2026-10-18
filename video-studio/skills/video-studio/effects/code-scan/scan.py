"""code-scan engine: one frame in, one frame out. Used by bake.py (and build.py for sizes / fonts / sounds).

The picture is re-drawn as readable code: the room in dim slate glyphs, the speaker as a brighter figure of tokens
(finer cells on the head so the face still reads), a small terminal card types two short lines, then the real
picture comes back.

The transition (the part that has to feel premium) has two layers that never fight each other:
  1. PRINT: a soft, organic front (a smooth order field: the speaker's core first, then outward through the room,
     bright areas a touch earlier) turns the photo into glyphs printed in the photo's OWN colours. The brightness
     stays close to the photo, so no dark patches appear; the front carries a faint light so it reads as drawn.
  2. GRADE: the printed picture eases into the code palette (dark slate room, cream figure) as one smooth, nearly
     global move, with only a gentle lag outward. There is no cell that jumps to near black on its own, which is
     what made the dark blocky cloud in the lab build.
Out is the same thing in reverse with its own frozen order field. Every random choice is seeded; a frame is a pure
function of its number, so worker processes can split the clip.
"""
import os
import re
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
SAFE = dict(top=220, bottom=1470, side=35, right_low=(1155, 100))
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)
CHARS = [chr(c) for c in range(32, 127)]
CIDX = {c: i for i, c in enumerate(CHARS)}
SP = CIDX[' ']


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def smoother(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


def ease_out(p, a=3.0):
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** a


def hexc(c):
    """'#rrggbb' or (r, g, b) 0..255 -> float32 0..1"""
    if isinstance(c, str):
        c = c.lstrip('#')
        c = [int(c[i:i + 2], 16) for i in (0, 2, 4)]
    return np.array(c[:3], np.float32) / 255.0


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
    f = ImageFont.truetype(path, float(px))
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


# ---------------------------------------------------------------------------------------------------- glyph grids
class Grid:
    def __init__(self, cw, ch, spec, boost=1.0):
        self.cw, self.ch = cw, ch
        self.cols, self.rows = W // cw, H // ch
        probe = '({[|gjpqy}$#@Q'
        size, best = 4.0, None
        while size < 90:
            f = load_font(spec, size)
            l, t, r, b = f.getbbox(probe)
            if f.getlength('M') > cw + 0.35 or (b - t) > ch:
                break
            best = (size, f, t, b)
            size += 0.25
        size, f, t, b = best
        adv = f.getlength('M')
        x0, y0 = (cw - adv) / 2.0, (ch - (b - t)) / 2.0 - t
        at = np.zeros((len(CHARS), ch, cw), np.float32)
        for i, c in enumerate(CHARS):
            if c == ' ':
                continue
            im = Image.new('L', (cw, ch), 0)
            ImageDraw.Draw(im).text((x0 + (adv - f.getlength(c)) / 2.0, y0), c, font=f, fill=255)
            at[i] = np.asarray(im, np.float32) / 255.0
        if boost != 1.0:
            at = np.clip(at, 0, 1) ** (1.0 / boost)
        self.atlas = at

    def pool(self, img):
        return img[:self.rows * self.ch, :self.cols * self.cw].reshape(self.rows, self.ch, self.cols, self.cw).mean((1, 3))

    def up(self, cells):
        out = cv2.resize(np.ascontiguousarray(cells, np.float32), (self.cols * self.cw, self.rows * self.ch),
                         interpolation=cv2.INTER_NEAREST)
        return pad_to(out)

    def glyphs(self, idx):
        g = self.atlas[idx].transpose(0, 2, 1, 3).reshape(self.rows * self.ch, self.cols * self.cw)
        return pad_to(g)


def pad_to(a):
    if a.shape[0] == H and a.shape[1] == W:
        return a
    out = np.zeros((H, W) + a.shape[2:], a.dtype)
    out[:a.shape[0], :a.shape[1]] = a
    return out


def make_stream(tokens, accents, n, seed):
    """A dense run of code-like statements built from the tokens. -> (char idx, class, statement id), each n long.
    class 0 = punctuation, 1 = word, 2 = accent word."""
    rng = np.random.RandomState(seed)
    chars, cls, sid = [], [], []
    st = [0]
    lead = accents[0] if accents else tokens[0]

    def emit(s, c):
        s = ''.join(ch if ch in CIDX else '?' for ch in s)
        chars.extend(CIDX[x] for x in s)
        cls.extend([c] * len(s))
        sid.extend([st[0]] * len(s))

    def word(w=None):
        w = w or tokens[rng.randint(len(tokens))]
        emit(w, 2 if (w in accents or rng.rand() < 0.07) else 1)

    while len(chars) < n:
        k = rng.randint(8)
        if k == 0:
            word(); emit('(', 0); word(); emit(');', 0)
        elif k == 1:
            word(); emit(' => ', 0); word(); emit(';', 0)
        elif k == 2:
            emit('{ ', 0); word(); emit(', ', 0); word(); emit(' }', 0)
        elif k == 3:
            word(lead); emit('.', 0); word(); emit('()', 0)
        elif k == 4:
            word(); emit('.', 0); word(); emit(';', 0)
        elif k == 5:
            word(); emit(': ', 0); word(); emit(',', 0)
        elif k == 6:
            emit('=> { ', 0); word(); emit(' }', 0)
        else:
            word(); emit('{ }', 0)
        emit(' ', 0)
        st[0] += 1
    return np.array(chars[:n], np.int64), np.array(cls[:n], np.int64), np.array(sid[:n], np.int64)


# ---------------------------------------------------------------------------------------------------- terminal card
def term_layout(term, spec):
    """card size (1x px) for the two lines at the card's font size. -> dict(pw, ph, fs, pad)"""
    fs = term['font_px']
    f = load_font(spec, fs)
    w1 = f.getlength(term['prompt'] + term['line1'] + 'M')
    w2 = f.getlength('MM' + term['line2'])
    pw = int(max(452, 80 + max(w1, w2)))
    ph = int(round(fs * 3.87))
    return dict(pw=pw, ph=ph, fs=fs, pad=60)


class Terminal:
    def __init__(self, term, spec, ink, acc, bg):
        self.t, self.spec = term, spec
        self.ink = tuple(int(round(v * 255)) for v in ink)
        self.acc = tuple(int(round(v * 255)) for v in acc)
        self.bg = tuple(int(round(v * 255)) for v in bg)
        self.cache = {}

    def sprite(self, n_chars, cursor_on, done_p):
        key = (n_chars, cursor_on, round(done_p, 2))
        if key in self.cache:
            return self.cache[key]
        T = self.t
        S = 3
        lay = term_layout(T, self.spec)
        pw, ph, pad, fs = lay['pw'], lay['ph'], lay['pad'], lay['fs']
        font = load_font(self.spec, fs * S)
        adv = font.getlength('M')
        im = Image.new('RGBA', ((pw + pad * 2) * S, (ph + pad * 2) * S), (0, 0, 0, 0))
        sh = Image.new('L', im.size, 0)
        ImageDraw.Draw(sh).rounded_rectangle([pad * S, (pad + 14) * S, (pad + pw) * S, (pad + ph + 14) * S], 28 * S, fill=150)
        sh = sh.filter(ImageFilter.GaussianBlur(20 * S))
        im.putalpha(sh)
        d = ImageDraw.Draw(im)
        bg = tuple(max(0, min(255, int(c * 1.15) + 2)) for c in self.bg)
        d.rounded_rectangle([pad * S, pad * S, (pad + pw) * S, (pad + ph) * S], 28 * S, fill=bg + (252,),
                            outline=self.ink + (58,), width=2 * S)
        x = (pad + 40) * S
        y1 = (pad + fs * 0.65) * S
        y2 = y1 + fs * 1.35 * S
        d.text((x, y1), T['prompt'], font=font, fill=self.acc + (255,))
        xt = x + font.getlength(T['prompt'])
        typed = T['line1'][:n_chars]
        d.text((xt, y1), typed, font=font, fill=self.ink + (255,))
        asc = font.getbbox('M')
        if done_p <= 0:
            if cursor_on:
                cxp = xt + font.getlength(typed) + 6 * S
                d.rectangle([cxp, y1 + asc[1] - 3 * S, cxp + adv * 0.86, y1 + asc[3] + 4 * S], fill=self.acc + (255,))
        else:
            p = ease_out(done_p, 3.0)
            a = int(255 * min(1.0, done_p * 2.5))
            dy = (1 - p) * 10 * S
            cx0, cyc = x + adv * 0.12, y2 + (asc[1] + asc[3]) / 2 + dy
            u = adv * 0.52
            d.line([(cx0, cyc + u * 0.05), (cx0 + u * 0.62, cyc + u * 0.62), (cx0 + u * 1.75, cyc - u * 0.72)],
                   fill=self.acc + (a,), width=int(fs * 0.12 * S), joint='curve')
            d.text((x + adv * 2, y2 + dy), T['line2'], font=font, fill=self.acc + (a,))
        im = im.resize((pw + pad * 2, ph + pad * 2), Image.LANCZOS)
        arr = np.asarray(im, np.float32) / 255.0
        self.cache[key] = arr
        return arr

    def draw(self, img, t):
        T = self.t
        if t < T['t_in'] or t >= T['t_out'] + T['out_dur']:
            return img
        p = ease_out((t - T['t_in']) / T['in_dur'], 3.0)
        fade = 1.0 - smooth((t - T['t_out']) / T['out_dur']) if t >= T['t_out'] else 1.0
        n = int(np.clip(np.floor((t - T['t_type']) * T['cps']) + 1, 0, len(T['line1']))) if t >= T['t_type'] else 0
        done_p = float(np.clip((t - T['t_done']) / 0.20, 0, 1)) if (t >= T['t_done'] and T['line2']) else 0.0
        typing = T['t_type'] <= t < T['t_type'] + len(T['line1']) / T['cps'] + 0.05
        cursor_on = typing or (int(round(t * FPS)) // 5) % 2 == 0
        sp = self.sprite(n, cursor_on, done_p)
        sc = T['scale'] * (0.965 + 0.035 * p) * (0.985 + 0.015 * fade)
        if abs(sc - 1.0) > 1e-3:
            sp = cv2.resize(sp, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_LINEAR)
        sh, sw = sp.shape[:2]
        x0 = int(round(T['cx'] - sw / 2))
        y0 = int(round(T['cy'] - sh / 2 + (1 - p) * 14))
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + sw), min(H, y0 + sh)
        sp = sp[ya - y0:yb - y0, xa - x0:xb - x0]
        a = sp[..., 3:4] * min(1.0, p * 1.4) * fade
        reg = img[ya:yb, xa:xb]
        img[ya:yb, xa:xb] = reg * (1 - a) + sp[..., :3] * a
        return img


# ---------------------------------------------------------------------------------------------------- the scene
class Scene:
    def __init__(self, pl, here):
        self.pl = pl
        self.here = here
        table = font_table(os.path.join(here, 'assets', 'fonts'))
        code_spec = pick_font(table, pl['code_font'], pl['code_weight'])
        pal = pl['palette']
        self.BG, self.ROOM, self.BODY, self.ACC = (hexc(pal[k]) for k in ('bg', 'room', 'body', 'accent'))
        self.G1 = Grid(12, 20, code_spec)                 # body + room
        self.G2 = Grid(6, 10, code_spec, boost=1.5)       # head (finer, so the face still reads)
        toks, acc = pl['tokens'], pl['accent_words']
        G1, G2 = self.G1, self.G2
        self.S1, self.C1, self.I1 = (a.reshape(G1.rows, G1.cols) for a in make_stream(toks, acc, G1.rows * G1.cols, 11))
        self.S2, self.C2, _ = (a.reshape(G2.rows, G2.cols) for a in make_stream(toks, acc, G2.rows * G2.cols, 23))
        self.S0, self.C0, self.I0 = (a.reshape(G1.rows, G1.cols) for a in make_stream(toks, acc, G1.rows * G1.cols, 37))
        r = np.random.RandomState(5)
        light = np.array([CIDX[c] for c in ".:-'`,;~"], np.int64)
        self.CODECH = np.array([CIDX[c] for c in '{}()=>;.:,_<+*/01'], np.int64)
        shp = self.S0.shape
        self.R0 = dict(light=light[r.randint(len(light), size=shp)], mut=r.rand(*shp) < 0.22,
                       phase=r.randint(0, 64, size=shp), period=r.randint(5, 26, size=shp),
                       salt=r.randint(0, 9973, size=shp))
        ns = int(max(self.I0.max(), self.I1.max())) + 1
        self.ST = dict(phase=r.randint(0, 97, size=ns), period=r.randint(7, 19, size=ns), salt=r.randint(0, 9973, size=ns))
        self.YY = np.arange(H, dtype=np.float32)[:, None]
        self.XX = np.arange(W, dtype=np.float32)[None, :]
        vs = 0.42 if pl.get('grade') else 0.30
        self.VIGN = (1.0 - vs * np.clip(((self.XX - W / 2) / (W * 0.72)) ** 2 + ((self.YY - H / 2) / (H * 0.72)) ** 2, 0, 1)).astype(np.float32)
        self.order = {}
        for k in ('in', 'out'):
            q = np.load(os.path.join(here, f'work/order_{k}.npy'))
            self.order[k] = cv2.resize(q.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
        self.term = None
        if pl.get('term'):
            tspec = pick_font(table, pl['term']['font'], pl['term']['weight'])
            self.term = Terminal(pl['term'], tspec, self.BODY, self.ACC, self.BG)

    # ---- code world
    def room_chars(self, f):
        R0 = self.R0
        epoch = (f + R0['phase']) // R0['period']
        mut = self.CODECH[(R0['salt'] + epoch * 7919) % len(self.CODECH)]
        return np.where(R0['mut'] & (self.C0 == 0) & (self.S0 != SP), mut, self.S0)

    def running(self, f, ids, pct):
        ST = self.ST
        epoch = (f + ST['phase']) // ST['period']
        on = ((ST['salt'] + epoch * 7919) % 100) < pct
        return on[ids]

    def render_code(self, rgb, A, f, head):
        """rgb float32 HxWx3 0..1, A float32 HxW (speaker matte) -> (the frame as code, glyph coverage)."""
        pl, G1, G2 = self.pl, self.G1, self.G2
        BG, ROOM, BODY, ACC = self.BG, self.ROOM, self.BODY, self.ACC
        XX, YY = self.XX, self.YY
        L = rgb @ LUMA
        a1 = G1.pool(A)
        body1 = a1 > 0.45
        if head is not None:
            # the head outline on the fine grid, so its edge follows the face instead of stepping in big cells
            hx, hy, rx, ry = head
            cyc = (np.arange(G2.rows) + 0.5)[:, None] * G2.ch
            cxc = (np.arange(G2.cols) + 0.5)[None, :] * G2.cw
            head2 = (((cxc - hx) / rx) ** 2 + ((cyc - hy) / ry) ** 2 < 1.0) & (G2.pool(A) > 0.30)
            head_px = G2.up(head2) > 0.5
            head1 = G1.pool(head_px.astype(np.float32)) > 0.5
        else:
            head_px = np.zeros((H, W), bool)
            head1 = np.zeros_like(body1)
        body1 &= ~head1
        solid = (body1 | head1).astype(np.uint8)
        rim1 = (solid - cv2.erode(solid, np.ones((3, 3), np.uint8))).astype(bool) & body1
        body_px = (G1.up(body1) > 0.5) & ~head_px
        person_soft = cv2.GaussianBlur(A, (0, 0), 46) if A.any() else A

        out = np.empty((H, W, 3), np.float32)
        out[:] = BG
        # room: dim slate glyphs; density follows the picture, levelled to this room (a dark room still reads)
        lo, hi = pl['room_levels']
        Lr = np.clip((L - lo) / max(hi - lo, 0.05), 0, 1)
        l0 = G1.pool(Lr)
        l0 = np.clip(l0 + 1.5 * (l0 - cv2.GaussianBlur(l0, (0, 0), 5.0)), 0, 1)
        ch0 = self.room_chars(f)
        ch0 = np.where(l0 < 0.10, SP, np.where(l0 < 0.33, self.R0['light'], ch0))
        i0 = (0.09 + 0.58 * l0 ** 1.5) * np.where(self.running(f, self.I0, 5), 1.7, 1.0)
        room_i = G1.up(i0) * (0.72 + 0.28 * np.clip(Lr / np.maximum(G1.up(l0), 0.05), 0, 1.6) / 1.6)
        room_i *= (1.0 - 0.55 * np.clip(person_soft * 1.3, 0, 1)) * self.VIGN
        room_g = G1.glyphs(ch0)
        room_m = np.where(body_px | head_px, 0.0, room_g * room_i)
        out += room_m[..., None] * (ROOM - BG * 0.4)

        # body: cream and accent tokens, brightness follows the picture, levelled to the speaker
        blo, bhi = pl['body_levels']
        l1 = G1.pool(L)
        lb = np.clip((l1 - blo) / max(bhi - blo, 0.05), 0, 1) ** 0.62
        lb = np.clip(lb + 1.1 * (lb - cv2.GaussianBlur(lb, (0, 0), 2.6)), 0, 1)
        i1 = (0.36 + 0.70 * lb) * np.where(self.running(f, self.I1, 7), 1.18, 1.0)
        i1 = np.where(rim1, np.maximum(i1, 0.92), i1) * np.clip(a1 * 1.6, 0, 1)
        col1 = np.where((self.C1 == 2)[..., None], ACC, BODY)
        col1 = col1 * np.where(self.C1 == 0, 0.74, 1.0)[..., None]
        col1 = np.where(rim1[..., None], ACC * 0.55 + BODY * 0.45, col1).astype(np.float32)
        lp = np.clip((L - blo) / max(bhi - blo, 0.05), 0, 1) ** 0.62
        body_i = G1.up(i1) * (0.50 + 0.50 * (0.35 + 0.65 * lp) / (0.35 + 0.65 * G1.up(lb)))
        g1 = G1.glyphs(self.S1)
        body_m = np.where(body_px, g1 * body_i, 0.0)
        body_rgb = body_m[..., None] * pad_to(cv2.resize(col1, (G1.cols * G1.cw, G1.rows * G1.ch), interpolation=cv2.INTER_NEAREST))

        # head: half-size cells, plus a little of the real face underneath
        l2 = G2.pool(L)
        lh = np.clip((l2 - blo) / max(bhi - blo + 0.08, 0.05), 0, 1) ** 0.85
        lph = np.clip((L - blo) / max(bhi - blo + 0.08, 0.05), 0, 1) ** 0.85
        col2 = np.where((self.C2 == 2)[..., None], ACC * 0.5 + BODY * 0.5, BODY).astype(np.float32)
        g2 = G2.glyphs(self.S2)
        head_i = (0.16 + 1.0 * (0.45 * G2.up(lh) + 0.55 * lph)) * np.clip(A * 1.5, 0, 1)
        head_m = np.where(head_px, (0.20 + 0.80 * g2) * head_i, 0.0)
        head_rgb = head_m[..., None] * pad_to(cv2.resize(col2, (G2.cols * G2.cw, G2.rows * G2.ch), interpolation=cv2.INTER_NEAREST))
        cover = np.where(head_px, 0.20 + 0.80 * g2, np.where(body_px, g1, room_g))

        fig = body_rgb + head_rgb
        out = out * (1.0 - np.clip(np.maximum(body_m, head_m), 0, 1))[..., None] + fig
        small = cv2.resize(fig, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        # bloom, eased off when the figure fills the frame (a close shot would otherwise turn the backdrop milky)
        share = float((body_px | head_px).mean())
        bg = 1.0 / (1.0 + 2.5 * share)
        glow = (cv2.GaussianBlur(small, (0, 0), 7) * 0.42 + cv2.GaussianBlur(small, (0, 0), 22) * 0.30) * bg
        out += cv2.resize(glow, (W, H), interpolation=cv2.INTER_LINEAR) * (ACC * 0.55 + BODY * 0.45)
        out += cv2.GaussianBlur(fig, (0, 0), 1.6) * 0.22
        if head is not None and pl['face_blend'] > 0:
            hx, hy, rx, ry = head
            fm = np.clip(1.0 - (((XX - hx) / (rx * 1.02)) ** 2 + ((YY - hy) / (ry * 1.02)) ** 2), 0, 1)
            fm = np.clip(fm * 2.6, 0, 1) * np.clip(A * 1.3, 0, 1) * pl['face_blend']
            out = out * (1.0 - fm[..., None] * 0.6) + rgb * fm[..., None]
        return out, cover

    # ---- timing
    def state(self, t):
        """-> (print front 0..1, grade into the code palette 0..1, phase 'in' / 'hold' / 'out' / None).
        Both run on their own gentle curves over the whole transition (linear time u), so no step of either moves more
        than about an eighth of the way in one frame: the front leads on the way in, the grade leads on the way out."""
        pl = self.pl
        if t < pl['t_in0'] or t >= pl['t_out1']:
            return 0.0, 0.0, None
        if t < pl['t_in1']:
            u = (t - pl['t_in0']) / (pl['t_in1'] - pl['t_in0'])
            return float(smooth(u / 0.85)), float(smooth((u - 0.18) / 0.82)), 'in'
        if t < pl['t_out0']:
            return 1.0, 1.0, 'hold'
        u = (t - pl['t_out0']) / (pl['t_out1'] - pl['t_out0'])
        return 1.0 - float(smooth((u - 0.15) / 0.85)), 1.0 - float(smooth(u / 0.80)), 'out'

    def frame(self, f, rgb8, a8):
        """one frame: uint8 HxWx3 (+ uint8 HxW matte or None) -> uint8 HxWx3. Outside the effect: the input bytes."""
        pl = self.pl
        t = f / FPS
        P, ag, phase = self.state(t)
        if phase is None:
            return rgb8
        rgb = rgb8.astype(np.float32) / 255.0
        A = a8.astype(np.float32) / 255.0 if a8 is not None else np.zeros((H, W), np.float32)
        head = pl['heads'][f]
        code, cover = self.render_code(rgb, A, f, head)
        if self.term is not None:
            code = self.term.draw(code, t)
        if phase == 'hold':
            settle = t - pl['t_in1']
            if settle < 0.40:                     # the code breathes once as it lands, then sits
                k = (1.0 - settle / 0.40) ** 2 * 0.10 * pl['glint']
                code = code * (1.0 + k)
            return self.encode(code)

        s = self.order[phase]
        w1 = pl['front']                          # width of the soft print front (share of the order field)
        a1 = smooth((P * (1.0 + w1) - s) / w1)
        a2 = smooth(ag * 1.25 - 0.25 * s)         # the grade into the code palette: nearly global, a gentle lag outward
        soft = cv2.GaussianBlur(rgb, (0, 0), 3.0)
        # glyphs printed in the photo's own colours, brightness matched to the photo around them (local mean of the
        # glyph ink), so the printed area never reads as a darker cloud
        local = cv2.GaussianBlur(cover, (0, 0), 9.0)
        printed = soft * ((0.40 + cover) / (0.40 + local))[..., None]
        out = rgb + (printed - rgb) * a1[..., None]
        band = (4.0 * a1 * (1.0 - a1) * (1.0 - ag))[..., None]       # light on the front while it travels
        lum = out @ LUMA
        out = out + (out * 0.30 + self.ACC * 0.06) * band * pl['glint'] * (1.0 - 0.7 * np.clip(lum, 0, 1))[..., None]
        out = out + (code - out) * a2[..., None]
        return self.encode(out)

    @staticmethod
    def encode(img):
        img = np.where(img > 0.86, 0.86 + (1 - np.exp(-(img - 0.86) / 0.14)) * 0.14, img)    # soft shoulder
        return (np.clip(img, 0, 1) * 255.0 + 0.5).astype(np.uint8)


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


def _band(rng, n, lo, hi):
    spec = np.fft.rfft(rng.randn(n))
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    spec *= 1.0 / (1 + (lo / np.maximum(fr, 1.0)) ** 4) / (1 + (fr / hi) ** 4)
    x = np.fft.irfft(spec, n)
    return x / (np.abs(x).max() + 1e-9)


def make_sfx(folder, in_len, out_len, n_keys, cps):
    """Four quiet cues, synthesised and seeded (every build writes the same files), far under the voice:
    a soft air swell with a faint high shimmer into the code look, soft key ticks while the card types,
    a two-note glass blip on the second line, a shorter swell as the picture comes back."""
    os.makedirs(folder, exist_ok=True)
    rng = np.random.RandomState(31)
    out = {}
    for key, ln, gain in (('in', in_len + 0.25, 0.060), ('out', out_len + 0.20, 0.045)):
        n = int(ln * SR)
        tt = np.arange(n) / SR
        peak = ln - 0.18
        air = _band(rng, n, 220.0, 1600.0)
        shim = _band(rng, n, 3500.0, 7500.0)
        grain = (rng.rand(n // 240 + 1) < 0.35).repeat(240)[:n] * 1.0
        grain = np.convolve(grain, np.hanning(120) / 60.0, mode='same')
        env = np.where(tt < peak, np.sin(np.clip(tt / peak, 0, 1) * np.pi / 2) ** 2.4, np.exp(-(tt - peak) / 0.07))
        if key == 'out':
            env = np.where(tt < 0.06, tt / 0.06, np.exp(-(tt - 0.06) / (ln * 0.45)))
        env *= np.clip((ln - tt) / 0.05, 0, 1)
        x = (air * 0.8 + shim * grain * 0.35) * env
        _wav(os.path.join(folder, f'code-{key}.wav'), x / (np.abs(x).max() + 1e-9) * gain)
        out[key] = (f'assets_fx/code-{key}.wav', ln)
    ln = max(0.2, n_keys / cps + 0.12)
    n = int(ln * SR)
    x = np.zeros(n)
    for k in range(n_keys):
        i0 = int((k / cps + rng.uniform(-0.006, 0.006)) * SR)
        m = int(0.018 * SR)
        if i0 < 0 or i0 + m >= n:
            continue
        tick = _band(rng, m, 1800.0, 6000.0) * np.exp(-np.arange(m) / (0.0035 * SR))
        x[i0:i0 + m] += tick * rng.uniform(0.7, 1.0)
    _wav(os.path.join(folder, 'code-type.wav'), x / (np.abs(x).max() + 1e-9) * 0.035)
    out['type'] = ('assets_fx/code-type.wav', ln)
    n = int(0.42 * SR)
    tt = np.arange(n) / SR
    x = np.zeros(n)
    for f0, st in ((1046.5, 0.0), (1568.0, 0.07)):
        u = np.clip(tt - st, 0, None)
        x += np.sin(2 * np.pi * f0 * u) * np.exp(-u / 0.09) * (tt >= st) * np.clip(u / 0.004, 0, 1)
    _wav(os.path.join(folder, 'code-done.wav'), x / (np.abs(x).max() + 1e-9) * 0.030)
    out['done'] = ('assets_fx/code-done.wav', 0.42)
    return out
