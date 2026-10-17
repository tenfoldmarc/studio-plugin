"""neon-sign compositor: one finished frame from the plain a-roll frame, the cutout alpha and the static maps that
build.py wrote (work/static.npz + work/plan.json). Used by bake.py (process pool). All in linear light.

Timeline per frame (all frame numbers in work/plan.json):
  before `appear`      plain footage
  appear .. +fade      the unlit sign fades onto the wall (coated glass, standoff feet, soft shadow)
  each tube's strike   irregular ignition (FLICKER), then steady; the room dims, the wall and the speaker take the light
  step (optional)      one step brighter, then it settles
  off                  a short flicker out, the room comes back up, the unlit sign fades away
  after `gone`         plain footage again
"""
import json

import cv2
import numpy as np

W, H, FPS = 1080, 1920, 30
GAMMA = 2.2
LUT = (np.arange(256, dtype=np.float32) / 255.0) ** GAMMA
HOT = (255, 250, 228)                       # the white-hot core of a lit tube
OFF_FLICKER = [0.85, 0.20, 0.55, 0.0]       # the levels while it switches off


def lin(rgb):
    return (np.float32(rgb) / 255.0) ** GAMMA


def sstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def soft_add(base, extra):
    """Add light without clipping and without bending its hue (the strongest channel rolls off, the other two keep
    their ratio to it: a per-channel shoulder turns butter yellow into lemon)."""
    room = np.maximum(1.0 - base.max(-1, keepdims=True), 1e-3)
    m = np.maximum(extra.max(-1, keepdims=True), 1e-6)
    return base + extra * (room * (1.0 - np.exp(-m / room)) / m)


def level(pl, g, f):
    """Tube brightness at frame f: strike pattern, a short warm-up overshoot, gas shimmer, the optional step, the
    switch-off."""
    k = f - g['f_strike']
    if k < 0:
        return 0.0
    fl = g['flicker']
    if k < len(fl):
        v = fl[k]
    else:
        v = 1.0 + 0.10 * np.exp(-(k - len(fl)) / 5.0)
        v *= 1.0 + 0.012 * np.sin(f * 2.1 + g['f_strike']) + 0.008 * np.sin(f * 0.83)
        st = pl.get('step')
        if st is not None and f >= st['frame']:
            v *= st['settle'] + (st['peak'] - st['settle']) * np.exp(-(f - st['frame']) / st['tau'])
    off = pl['f_off']
    if off is not None and f >= off:
        j = f - off
        v *= OFF_FLICKER[j] if j < len(OFF_FLICKER) else 0.0
    return float(v)


def striking(g, f):
    k = f - g['f_strike']
    return 0 <= k < len(g['flicker'])


def exposure(pl, f):
    a, b = pl['dim_in']
    e = sstep((f - a) / float(max(b - a, 1)))
    if pl['f_off'] is not None:
        c, d = pl['dim_out']
        e *= 1.0 - sstep((f - c) / float(max(d - c, 1)))
    return 1.0 - (1.0 - pl['room_dim']) * e


def visible(pl, f):
    """How much of the unlit sign is on the wall (0 = plain footage)."""
    a0, a1 = pl['appear']
    v = sstep((f - a0 + 1) / float(max(a1 - a0, 1)))
    if pl['f_off'] is not None:
        g0, g1 = pl['gone']
        v *= 1.0 - sstep((f - g0 + 1) / float(max(g1 - g0, 1)))
    return float(v)


class Scene:
    def __init__(self, plan_path, static_path):
        self.pl = pl = json.load(open(plan_path))
        z = np.load(static_path)
        self.art_a = z['art_a'].astype(np.float32)
        self.art_e = z['art_e'].astype(np.float32)
        self.SG = z['SG'].astype(np.float32)
        self.MS = z['MS'].astype(np.float32)
        self.wallcol = z['wallcol'].astype(np.float32)
        self.cents = np.float64(pl['cents'])
        self.art_to_img = np.float64(pl['art_to_img'])
        self.track = [np.float64(m) for m in pl['track']]
        self.groups = pl['groups']
        self.col = np.stack([lin(g['colour']) for g in self.groups])
        self.thr = np.stack([lin(g['throw']) for g in self.groups])
        self.hot = lin(HOT)
        self.active = pl['active']

    def frame(self, f, plate, alpha):
        """plate: HxWx3 uint8 a-roll frame, alpha: HxW uint8 cutout. Returns HxWx3 uint8."""
        pl = self.pl
        vis = visible(pl, f)
        if vis <= 0.0 or not (self.active[0] <= f <= self.active[1]):
            return plate
        size = (W, H)
        T = self.track[f]
        base = LUT[plate]
        a = alpha.astype(np.float32) / 255.0
        a = np.clip((a - 0.18) / (0.90 - 0.18), 0, 1)                   # choke the matte's loose rim
        G = len(self.groups)
        SG = cv2.warpPerspective(self.SG, T, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        if SG.ndim == 2:
            SG = SG[..., None]
        MS = cv2.warpPerspective(self.MS, T, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        Ma = T @ self.art_to_img
        La = cv2.warpPerspective(self.art_a, Ma, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(1, 0, 0, 0))
        Le = cv2.warpPerspective(self.art_e, Ma, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(0, 0, 0, 0))
        # the matte runs a few px wide of the speaker: light and glass behind must reach the real edge
        mp = pl['matte_pull']
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (mp, mp))
        a_in = cv2.morphologyEx(a, cv2.MORPH_CLOSE, ker)
        a_in = cv2.GaussianBlur(cv2.erode(a_in, ker), (0, 0), 0.8)
        wall_vis = 1 - a_in
        behind = wall_vis
        E = exposure(pl, f)
        lv = np.float32([level(pl, g, f) for g in self.groups])
        on = float(np.clip(lv.max(), 0, 1))

        # --- room light: the plate, dimmed, with the unlit glass, its feet and shadows on the wall
        gain = 1 + (La[..., 0] - 1) * behind * vis
        out = base * (E * gain)[..., None]
        glass = (La[..., 2] * behind * vis)[..., None]                   # coated glass is opaque
        out = out * (1 - glass) + self.wallcol * (E * La[..., 0])[..., None] * glass
        out += (La[..., 1] * behind * vis * (0.30 * E))[..., None]
        if on > 0:
            # --- the sign lights the room (albedo from the plate)
            glow = np.einsum('hwg,gc->hwc', SG, self.thr * lv[:, None]) * pl['spill_gain']
            extra = base * glow * wall_vis[..., None]
            # --- and the speaker: the side that faces it
            cen = cv2.perspectiveTransform(np.float64([[np.average(self.cents, 0, weights=lv + 1e-3)]]), T)[0, 0]
            small = cv2.resize(a, (270, 480), interpolation=cv2.INTER_AREA)
            ab_t = cv2.GaussianBlur(a, (0, 0), 9.0)
            ab_w = cv2.resize(cv2.GaussianBlur(small, (0, 0), 8.0), size, interpolation=cv2.INTER_LINEAR)
            sg = cv2.GaussianBlur(small, (0, 0), 3.0)
            nx = -cv2.resize(cv2.Sobel(sg, cv2.CV_32F, 1, 0, ksize=5), size, interpolation=cv2.INTER_LINEAR)
            ny = -cv2.resize(cv2.Sobel(sg, cv2.CV_32F, 0, 1, ksize=5), size, interpolation=cv2.INTER_LINEAR)
            nn = np.sqrt(nx * nx + ny * ny) + 0.6          # not 1e-5: along the middle of a hand the gradient is noise
            xx = np.arange(W, dtype=np.float32)[None, :]
            yy = np.arange(H, dtype=np.float32)[:, None]
            dx, dy = cen[0] - xx, cen[1] - yy
            dist = np.sqrt(dx * dx + dy * dy) + 1e-3
            facing = np.clip((nx * dx + ny * dy) / (nn * dist), 0, 1) ** 1.5
            front = np.clip(MS[..., 2] * 1.5, 0, 1)                     # a hand across the sign: lit from behind
            facing = np.maximum(facing, 0.6 * front)
            rim = pl['rim']
            fall = 1.0 / (1.0 + (dist / rim['reach']) ** 2)
            solid = np.clip((cv2.erode(a, np.ones((5, 5), np.uint8)) - 0.6) / 0.4, 0, 1)
            w_t = solid * np.clip((1 - ab_t) * 2.0, 0, 1) ** 1.2
            w_w = solid * np.clip((1 - ab_w) * 2.0, 0, 1)
            him = facing * fall * (rim['tight'] * w_t + rim['wide'] * w_w) * float(np.clip(lv, 0, 1.6).mean())
            # skin and cloth take the same light less saturated (yellow on skin turns orange otherwise)
            hcol = np.average(self.thr, 0, weights=lv + 1e-3) * 0.62 + 0.38
            extra += (base * 1.1 + 0.012) * him[..., None] * hcol
            out = soft_add(out, extra)

            # --- the lit glass
            ph = La[..., 3]
            cov = np.zeros((H, W), np.float32)
            rad = np.zeros((H, W, 3), np.float32)
            hdr = np.zeros((H, W, 3), np.float32)
            for gi, g in enumerate(self.groups):
                if lv[gi] <= 0:
                    continue
                e = Le[..., gi]
                lit = np.clip(e / 0.5, 0, 1)
                core = np.clip((e - 0.5) / 0.5, 0, 1)
                L = np.full(e.shape, lv[gi], np.float32)
                if striking(g, f):
                    # partial ignition: the discharge has not filled the tube yet (seeded per frame and tube)
                    r = np.random.default_rng(1000 + f * 7 + gi)
                    k1, k2, p1, p2 = r.uniform(1.5, 4.0), r.uniform(5, 9), r.uniform(0, 6.28), r.uniform(0, 6.28)
                    L *= np.clip(0.75 + 0.55 * np.sin(ph * k1 + p1) + 0.2 * np.sin(ph * k2 + p2), 0.05, 1.5)
                Lc = np.minimum(L, 1.0)
                over = np.clip((L - 1.0) * 0.5, 0, 0.5)[..., None]          # past full: the sheath whitens
                sheath = self.col[gi] * (1 - over) + self.hot * over
                c_g = sheath * (lit * (1 - 0.9 * core) * Lc ** 0.8)[..., None] + self.hot * (core * Lc ** 0.6)[..., None]
                rad += c_g
                cov = np.maximum(cov, lit * (1 - np.exp(-6.0 * L)))
                hdr += (self.thr[gi] * (lit * 2.6 * L)[..., None] + self.hot * (core * 0.7 * L)[..., None])
            cov *= behind
            out = out * (1 - cov)[..., None] + np.minimum(rad, 1.0) * behind[..., None]
            # --- lens bloom of what the camera can see of it
            hdr *= behind[..., None]
            bloom = np.zeros_like(hdr)
            for sig, w in pl['bloom']:
                if sig <= 4:
                    bloom += cv2.GaussianBlur(hdr, (0, 0), sig) * w
                else:
                    d = 4 if sig < 40 else 8
                    s = cv2.resize(hdr, (W // d, H // d), interpolation=cv2.INTER_AREA)
                    s = cv2.GaussianBlur(s, (0, 0), sig / d)
                    bloom += cv2.resize(s, size, interpolation=cv2.INTER_LINEAR) * w
            out = soft_add(out, bloom * (1 - 0.85 * cov)[..., None])
        return (np.clip(out, 0, 1) ** (1 / GAMMA) * 255 + 0.5).astype(np.uint8)


def safe_guide(img):
    img = img.copy()
    for (x0, y0, x1, y1) in ((35, 220, 1045, 1470), (980, 1155, 1080, 1470)):
        cv2.rectangle(img, (x0, y0), (x1, y1), (255, 40, 40), 3)
    return img
