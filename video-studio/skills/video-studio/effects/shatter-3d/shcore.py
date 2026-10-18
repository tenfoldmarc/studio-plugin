"""Shatter 3D core: the fracture (tiles at different depths, a drifting camera, a jolt on the hit) and the two ways out
('glass': the held picture cracks and breaks into falling glass shards; 'heal': the tiles snap back together).

Pure functions of the plan written by build.py (work/plan.json): every random choice is seeded, so two bakes of the
same plan match frame for frame on any machine. Used by build.py (geometry checks) and bake.py (drawing).
"""
import math

import cv2
import numpy as np

W, H, FPS = 1080, 1920, 30
SS = 2                      # supersample factor for the fractured frames
CAM_D = 2400.0              # camera distance = focal length (px): the z=0 plane maps 1:1
STEP = FPS / 12.0           # 12 fps stepping while fractured
LEAD = 1 / 12.0             # each step shows the pose one step ahead, so the break and the hit land on their frame


def bgr(rgb):
    return tuple(int(v) for v in rgb[::-1])


def expo_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


def back_out(x, s=1.9):
    x = min(max(x, 0.0), 1.0) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


def rot(rx, ry, rz):
    rx, ry, rz = (math.radians(a) for a in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Rx @ Ry


def step_starts(a, b):
    """12 fps step boundaries from frame a up to (not including) b; a last step shorter than 2 frames is merged."""
    out, j = [], 0
    while True:
        f = a + int(math.floor(STEP * j + 0.5))
        if f >= b:
            break
        out.append(f)
        j += 1
    if len(out) > 1 and b - out[-1] < 2:
        out.pop()
    return out


def scale_pose(P, k):
    return dict(A=P['A'] * k, D=0.0, E=P['E'] * k, yaw=P['yaw'] * k, pitch=P['pitch'] * k, roll=P['roll'] * k,
                push=1 + (P['push'] - 1) * k, sx=P['sx'] * k, sy=P['sy'] * k)


class Shatter:
    """Frames in, frames out. plan(n) says what frame n is; render(hi_frame, pose) draws a fractured frame."""

    def __init__(self, pl):
        self.fb, self.fh, self.fe = pl['f_break'], pl['f_hit'], pl['f_heal']
        self.eyes = pl.get('eyes')
        self.ending = pl['ending']
        self.accent = np.float32(bgr(pl['accent']))
        self.ground_col = bgr(pl['ground'])
        if self.ending == 'glass':
            g = pl['glass']
            self.fc = g['f_crack']                           # cracks start
            self.fr = self.fc + g['crack_frames']            # the pane lets go
            self.fg = g['f_gone']                            # clean again
            self.crack_frames = g['crack_frames']
            assert self.fh < self.fc < self.fr < self.fg
            self.fe = self.fc                                # the stepped hold freezes when the cracks start
        rng = np.random.RandomState(pl['seed'])
        tiles = [s for s in pl['shards'] if s.get('kind', 'tile') == 'tile']
        cover = np.zeros((H, W), np.uint8)
        for s in tiles:
            x0, y0, x1, y1 = s['rect']
            cover[y0:y1, x0:x1] += 1
        assert cover.min() == 1 and cover.max() == 1, 'tile shards must cover the frame exactly once'
        free = [s for s in tiles if 'z' not in s]
        depths = list(np.linspace(60, 600, len(free)))
        rng.shuffle(depths)
        self.shards = []
        for s in pl['shards']:
            s = dict(s)
            x0, y0, x1, y1 = s['rect']
            s['kind'] = s.get('kind', 'tile')
            if 'z' not in s:
                s['z'] = float(depths.pop())
            thin = min(x1 - x0, y1 - y0) < 260
            if 'tilt' not in s:
                k = 1.6 if thin else 1.0
                s['tilt'] = (rng.uniform(-3, 3) * k, rng.uniform(-6, 6) * k, rng.uniform(-1.0, 1.0) * k)
            s['jit'] = (rng.uniform(-22, 22), rng.uniform(-22, 22)) if s['kind'] == 'tile' and not s.get('hero') else (0, 0)
            s['grow'] = s.get('grow', 1.0)
            self.shards.append(s)
        self.zfar = max(s['z'] for s in self.shards)
        self.steps1 = step_starts(self.fb, self.fh)
        self.steps2 = step_starts(self.fh, self.fe)
        self.u_hit = (self.fh - self.fb) / FPS
        self.shake_rng = pl['seed'] * 131 + 7
        self._ground = None

    # ---- timing ------------------------------------------------------------------------------------------------
    def plan(self, n):
        """-> (mode, source frame, pose, extra) for output frame n.
        mode: clean | frac | plate (scaled whole frame, 'heal' only) | glass (shards over the live frame)."""
        if n < self.fb:
            return 'clean', n, None, {}
        if n < self.fh:
            b = max(f for f in self.steps1 if f <= n)
            return 'frac', b, self.pose((b - self.fb) / FPS + LEAD, None, b), {}
        if n < self.fe:
            b = max(f for f in self.steps2 if f <= n)
            return 'frac', b, self.pose(None, (b - self.fh) / FPS + LEAD, b), {}
        last = self.steps2[-1]
        held = self.pose(None, (last - self.fh) / FPS + LEAD, last)
        if self.ending == 'glass':
            if n >= self.fg:
                return 'clean', n, None, {}
            if n < self.fr:                       # held picture, cracks racing across it
                return 'frac', last, held, {'crack': (n - self.fc + 1) / self.crack_frames}
            return 'glass', n, held, {'pane_src': last, 't': (n - self.fr) / FPS}
        k = n - self.fe
        if k >= 3:
            return 'clean', n, None, {}
        if k == 0:
            return 'frac', n, scale_pose(held, 0.34), {}
        return 'plate', n, {'scale': (1.020, 1.006)[k - 1]}, {}

    def pose(self, u, v, step_id):
        """Smooth camera + fracture curves, sampled once per 12 fps step. u = s since break, v = s since hit."""
        uh = self.u_hit
        if v is None:
            e = expo_out(u / 0.45)
            A = 0.50 * e + 0.10 * u / uh
            E = 0.030 * e + 0.010 * u / uh
            yaw = -2.5 * e - 5.0 * u / uh
            pitch = 1.2 * e + 1.8 * u / uh
            roll = 0.5 * e + 0.6 * u / uh
            push = 1 + 0.015 * e + 0.075 * u / uh
            Dp = 0.80 * expo_out(u / 0.16) + 0.06 * u / uh
            amp, ramp = 2.5, 0.10
        else:
            k, q = back_out(v / 0.34), expo_out(v / 0.26)
            A = 0.60 + 0.40 * k + 0.07 * v
            E = 0.040 + 0.085 * k + 0.012 * v
            yaw = -7.5 + 12.5 * q + 4.5 * v
            pitch = 3.0 - 6.0 * q - 1.2 * v
            roll = 1.1 - 2.9 * q - 0.5 * v
            push = 1.09 - 0.135 * expo_out(v / 0.20) + 0.085 * v
            Dp = 0.86 + 0.14 * k + 0.03 * v
            d = math.exp(-max(v - LEAD, 0) / 0.16)
            amp, ramp = 2.5 + 15 * d, 0.10 + 0.7 * d
        r = np.random.RandomState(self.shake_rng + step_id * 17)
        return dict(A=A, D=Dp, E=E, yaw=yaw, pitch=pitch, roll=roll + r.uniform(-1, 1) * ramp, push=push,
                    sx=r.uniform(-1, 1) * amp, sy=r.uniform(-1, 1) * amp)

    def frac_poses(self):
        """every distinct pose the fracture shows (for the geometry checks in build.py)."""
        out, seen = [], set()
        for n in range(self.fb, self.fe + 1):
            mode, src, P, extra = self.plan(n)
            if mode == 'frac' and (src, round(P['A'], 5)) not in seen:
                seen.add((src, round(P['A'], 5)))
                out.append((n, P))
        return out

    # ---- geometry ----------------------------------------------------------------------------------------------
    def quad(self, s, P, rect=None):
        """Projected corners (4x2, 1080-space) of a shard, or of a sub-rect lying on it, plus its camera depth."""
        x0, y0, x1, y1 = s['rect']
        hx, hy, A = (x0 + x1) / 2 - W / 2, (y0 + y1) / 2 - H / 2, P['A']
        if s['kind'] == 'dupe':
            A = P['D']                     # close-ups fly out faster than the tiles separate
            tx, ty = s['to'][0] - W / 2, s['to'][1] - H / 2
            c = np.array([hx + (tx - hx) * A, hy + (ty - hy) * A, s['z'] * A])
        else:
            c = np.array([hx * (1 + P['E']) + s['jit'][0] * A, hy * (1 + P['E']) + s['jit'][1] * A, s['z'] * A])
        g = 1 + (s['grow'] - 1) * A
        rx0, ry0, rx1, ry1 = rect or s['rect']
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        loc = np.array([[rx0 - cx, ry0 - cy, 0], [rx1 - cx, ry0 - cy, 0], [rx1 - cx, ry1 - cy, 0],
                        [rx0 - cx, ry1 - cy, 0]], float) * g
        Rs = rot(s['tilt'][0] * A, s['tilt'][1] * A, s['tilt'][2] * A)
        pts = loc @ Rs.T + c
        Rc = rot(P['pitch'], P['yaw'], P['roll'])
        q = pts @ Rc.T
        cz = (c @ Rc.T)[2]
        q[:, 0] += P['sx']
        q[:, 1] += P['sy']
        d = q[:, 2] + CAM_D / P['push']
        return np.stack([W / 2 + CAM_D * q[:, 0] / d, H / 2 + CAM_D * q[:, 1] / d], 1), cz

    def layout(self, P):
        """draw order (far first) of (depth, index, shard, quad) for a pose."""
        items = []
        for i, s in enumerate(self.shards):
            if s['kind'] == 'dupe' and P['D'] < 0.02:
                continue                          # close-ups are glued to the picture: nothing to draw
            q, cz = self.quad(s, P)
            items.append((cz, i, s, q))
        items.sort(key=lambda t: -t[0])
        return items

    def owner(self, items):
        own = np.zeros((H // 4, W // 4), np.uint8)
        for cz, i, s, q in items:
            cv2.fillConvexPoly(own, np.round(q / 4).astype(np.int32), i + 1)
        return own

    def eye_vis(self, P, items=None, own=None):
        """share of the eyes box that is seen, on the face tile or on a close-up that shows the eyes whole."""
        if not self.eyes:
            return 1.0
        items = items if items is not None else self.layout(P)
        own = own if own is not None else self.owner(items)
        hero_i = next(i for i, s in enumerate(self.shards) if s.get('hero'))
        eq, _ = self.quad(self.shards[hero_i], P, rect=self.eyes)
        em = np.zeros_like(own)
        cv2.fillConvexPoly(em, np.round(eq / 4).astype(np.int32), 1)
        inside = (eq[:, 0].min() >= 0 and eq[:, 0].max() <= W and eq[:, 1].min() >= 0 and eq[:, 1].max() <= H)
        vis = float((own[em > 0] == hero_i + 1).mean()) if em.any() and inside else 0.0
        for cz, i, s, q in items:
            if s.get('eyes') and q.min() >= 0 and q[:, 0].max() <= W and q[:, 1].max() <= H:
                dm = np.zeros_like(own)
                cv2.fillConvexPoly(dm, np.round(q / 4).astype(np.int32), 1)
                vis = max(vis, float((own[dm > 0] == i + 1).mean()))
        return vis

    def ground(self):
        if self._ground is None:
            yy, xx = np.mgrid[0:H * SS, 0:W * SS].astype(np.float32)
            r = np.sqrt(((xx - W * SS / 2) / (W * SS * 0.75)) ** 2 + ((yy - H * SS * 0.42) / (H * SS * 0.62)) ** 2)
            lift = np.clip(1 - r, 0, 1) ** 1.6
            g = np.empty((H * SS, W * SS, 3), np.float32)
            for c in range(3):
                g[..., c] = self.ground_col[c] + lift * (17, 15, 14)[c]
            self._ground = g
        return self._ground

    # ---- drawing -----------------------------------------------------------------------------------------------
    def render(self, hi, P):
        """One fractured frame from a source frame (BGR uint8, any 9:16 size) and a pose -> 1080x1920 BGR."""
        hs = hi.shape[1] / W
        canvas = self.ground().copy()
        A = P['A']
        items = self.layout(P)
        k_shadow = 0.55 * min(1.0, A * 1.7)
        for cz, i, s, q in items:
            x0, y0, x1, y1 = s['rect']
            tex = hi[int(y0 * hs):int(y1 * hs), int(x0 * hs):int(x1 * hs)].astype(np.float32)
            gain = 1 - 0.14 * float(np.clip(s['z'] * A / 600, -0.25, 1))   # far shards a touch darker
            tex *= gain
            b = max(2, int(round(2.2 * hs)))      # thin light edge so each shard reads as a slab
            e = 0.26 * min(1.0, A * 2.5)
            col, e = ((self.accent, min(1.0, A * 4)) if s.get('accent') else ((255, 255, 255), e))
            for sl in (np.s_[:b, :], np.s_[-b:, :], np.s_[b:-b, :b], np.s_[b:-b, -b:]):
                tex[sl] = tex[sl] * (1 - e) + np.float32(col) * e
            th, tw = tex.shape[:2]
            rgba = np.dstack([np.clip(tex, 0, 255).astype(np.uint8), np.full((th, tw), 255, np.uint8)])
            qs = q * SS
            bx0, by0 = np.floor(qs.min(0)).astype(int) - 2
            bx1, by1 = np.ceil(qs.max(0)).astype(int) + 2
            bx0, by0, bx1, by1 = max(bx0, 0), max(by0, 0), min(bx1, W * SS), min(by1, H * SS)
            if bx1 <= bx0 or by1 <= by0:
                continue
            src = np.array([[0, 0], [tw, 0], [tw, th], [0, th]], np.float32)
            M = cv2.getPerspectiveTransform(src, (qs - (bx0, by0)).astype(np.float32))
            wp = cv2.warpPerspective(rgba, M, (bx1 - bx0, by1 - by0), flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
            a = wp[..., 3].astype(np.float32) / 255
            hgt = max(0.0, self.zfar * A - cz)    # soft shadow on everything already drawn
            if k_shadow > 0.01:
                m = np.zeros((H * SS, W * SS), np.float32)
                m[by0:by1, bx0:bx1] = a
                sm = cv2.resize(m, (W * SS // 8, H * SS // 8), interpolation=cv2.INTER_AREA)
                off = np.float32([[1, 0, (10 + 0.035 * hgt) * SS / 8], [0, 1, (16 + 0.060 * hgt) * SS / 8]])
                sm = cv2.warpAffine(sm, off, (sm.shape[1], sm.shape[0]))
                sg = (9 + 0.030 * hgt) * SS / 8
                sm = cv2.GaussianBlur(sm, (0, 0), sg)
                ys, xs = np.where(sm > 0.004)
                if len(ys):
                    sy0, sy1, sx0, sx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                    up = cv2.resize(sm[sy0:sy1, sx0:sx1], ((sx1 - sx0) * 8, (sy1 - sy0) * 8),
                                    interpolation=cv2.INTER_LINEAR)
                    canvas[sy0 * 8:sy1 * 8, sx0 * 8:sx1 * 8] *= (1 - k_shadow * up)[..., None]
            roi = canvas[by0:by1, bx0:bx1]
            roi *= (1 - a)[..., None]
            roi += wp[..., :3]
        out = cv2.resize(canvas, (W, H), interpolation=cv2.INTER_AREA)
        return np.clip(out, 0, 255).astype(np.uint8)


def plate(hi, scale):
    """The whole frame, scaled about its centre (overshoot frames of the 'heal' snap back)."""
    hs = hi.shape[1] / W
    w, h = int(round(W * scale / 2)) * 2, int(round(H * scale / 2)) * 2
    big = cv2.resize(hi, (w, h), interpolation=cv2.INTER_AREA if hs > scale else cv2.INTER_CUBIC)
    x, y = (w - W) // 2, (h - H) // 2
    return big[y:y + H, x:x + W]


def pt16(p):
    """Sub-pixel point for cv2 drawing calls with shift=4."""
    return int(round(float(p[0]) * 16)), int(round(float(p[1]) * 16))


class Glass:
    """The 'glass' way out. The held fractured picture is one pane: cracks race out from an impact point, then the
    pane breaks into irregular triangles that fly away from the impact and toward the camera, tumble in 3D and fall
    with gravity. Each shard carries its piece of the picture, a bright bevelled edge and a glint when it catches
    the light. Behind them is the clean live frame. Full frame rate with real motion blur."""
    NS = 18                   # motion blur: sub-frame samples per output frame (6 gives ghost copies)
    SHUTTER = 0.55            # part of a frame the shutter is open
    GRAVITY = 6500.0          # px / s^2
    EDGE = np.float32((255, 251, 240))                       # BGR, slightly cool white for cracks and bevels
    SKY = np.float32((236, 240, 234))                        # what tilted glass reflects
    LIGHT = np.array([-0.45, -0.62, 0.64]) / np.linalg.norm([-0.45, -0.62, 0.64])

    def __init__(self, impact, seed, t_limit, verbose=False):
        rng = np.random.RandomState(seed)
        self.impact = np.array(impact, float)
        self.t_limit = t_limit
        ix, iy = impact
        self.rmax = max(math.hypot(ix - x, iy - y) for x in (0, W) for y in (0, H))
        # crack pattern: jittered rings around the impact (tight near it, wide far away) + points on the frame edge
        pts = [(ix, iy)]
        r, k = 34.0, 5
        while r < self.rmax * 1.05:
            a0 = rng.uniform(0, 2 * math.pi)
            for j in range(k):
                a = a0 + (j + rng.uniform(-0.32, 0.32)) * 2 * math.pi / k
                rr = r * rng.uniform(0.85, 1.15)
                x, y = ix + rr * math.cos(a), iy + rr * math.sin(a)
                if 14 < x < W - 14 and 14 < y < H - 14:
                    pts.append((x, y))
            r, k = r * 1.42 + 22, min(k + 2, 17)
        for x in (0, W):
            pts += [(x, 0), (x, H)]
            pts += [(x, y + rng.uniform(-60, 60)) for y in np.arange(230, H - 150, 235)]
        for y in (0, H):
            pts += [(x + rng.uniform(-60, 60), y) for x in np.arange(215, W - 150, 215)]
        sub = cv2.Subdiv2D((-20, -20, W + 40, H + 40))
        for p in pts:
            sub.insert((float(p[0]), float(p[1])))
        tl = sub.getTriangleList().reshape(-1, 3, 2).astype(np.float64)
        ok = ((tl[..., 0] > -0.5) & (tl[..., 0] < W + 0.5) & (tl[..., 1] > -0.5) & (tl[..., 1] < H + 0.5)).all(1)
        tl = tl[ok]
        e1, e2 = tl[:, 1] - tl[:, 0], tl[:, 2] - tl[:, 0]
        area = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
        tl, area = tl[area > 2], area[area > 2]
        assert abs(area.sum() - W * H) < 0.005 * W * H, 'crack pattern does not cover the frame'
        self.verts, self.n = tl, len(tl)
        self.c0 = tl.mean(1)
        d = self.c0 - self.impact
        self.r = np.hypot(d[:, 0], d[:, 1])
        rn = self.r / self.rmax
        dirs = d / np.maximum(self.r, 1e-3)[:, None]
        # how each shard flies: away from the impact, toward the camera, then gravity takes over
        self.vel = dirs * ((1500 - 500 * rn) * rng.uniform(0.7, 1.35, self.n))[:, None] + rng.normal(0, 120, (self.n, 2))
        self.vz = -(2700 - 700 * rn) * rng.uniform(0.45, 1.0, self.n)
        self.delay = 0.07 * rn * rng.uniform(0.75, 1.2, self.n)          # the break spreads out from the impact
        ph = rng.uniform(0, 2 * math.pi, self.n)
        ax = np.stack([np.cos(ph), np.sin(ph), rng.uniform(-0.3, 0.3, self.n)], 1)
        ax /= np.linalg.norm(ax, axis=1)[:, None]
        small = 1 + 0.6 * (1 - np.clip(area / 60000, 0, 1))             # small pieces spin faster
        self.w = ax * (rng.uniform(5, 13, self.n) * small)[:, None]      # tumble, rad / s
        ph = rng.uniform(0, 2 * math.pi, self.n)
        self.tilt0 = np.stack([np.cos(ph), np.sin(ph), np.zeros(self.n)], 1) * rng.uniform(0.02, 0.07, self.n)[:, None]
        self.gain = rng.uniform(0.93, 1.07, self.n)                      # each facet catches the light differently
        # every shard must be off screen, for good, before the clean frame: speed up the ones that are not
        grid = np.arange(0, t_limit + 1e-6, 1 / 120)
        self.boosted, self.t_exit = 0, np.zeros(self.n)
        for i in range(self.n):
            for it in range(60):
                last = 0.0
                for t in grid:
                    pl = self.place(i, max(0.0, t - self.delay[i]))
                    if pl is not None and self.on_screen(pl[0]):
                        last = t
                if last <= t_limit - 0.10:
                    break
                self.vel[i] *= 1.12
                if self.vz[i] * (t_limit - self.delay[i]) > -1750:      # never through the lens
                    self.vz[i] *= 1.10
                self.boosted += it == 0
            self.t_exit[i] = last
        edges = {}
        for i in range(self.n):
            for a, b in ((0, 1), (1, 2), (2, 0)):
                p, q = self.verts[i][a], self.verts[i][b]
                on_border = any(abs(p[c] - v) < 0.5 and abs(q[c] - v) < 0.5 for c, v in ((0, 0), (0, W), (1, 0), (1, H)))
                if not on_border:
                    edges[tuple(sorted((tuple(np.round(p, 2)), tuple(np.round(q, 2)))))] = (p, q)
        # crack lines: slightly jagged, the ones running away from the impact bright, the ones linking them faint
        self.cracks_paths = []
        for p, q in sorted(edges.values(), key=lambda pq: (tuple(pq[0]), tuple(pq[1]))):
            e, mid = q - p, (p + q) / 2 - self.impact
            ln = np.hypot(*e)
            radial = abs(float(e @ mid)) / max(ln * np.hypot(*mid), 1e-3)
            if radial < 0.55 and rng.uniform() < 0.35 and np.hypot(*mid) > 160:
                continue
            m = max(1, int(round(ln / 34)))
            path = np.array([p + e * j / m for j in range(m + 1)])
            if m > 1:
                path[1:-1] += (np.array([-e[1], e[0]]) / ln)[None] * rng.normal(0, 2.4, (m - 1, 1))
            val = int(255 * (0.22 + 0.78 * radial ** 1.4) * rng.uniform(0.7, 1.0))
            self.cracks_paths.append((path, val))
        self._dist = None
        if verbose:
            print(f'  glass: {self.n} shards, {self.boosted} sped up to clear in time, last one leaves at '
                  f'{self.t_exit.max():.3f}s of {t_limit:.3f}s', flush=True)

    @property
    def dist(self):
        if self._dist is None:
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            self._dist = np.hypot(xx - self.impact[0], yy - self.impact[1])
        return self._dist

    @staticmethod
    def on_screen(pv):
        return pv[:, 0].max() > -2 and pv[:, 0].min() < W + 2 and pv[:, 1].max() > -2 and pv[:, 1].min() < H + 2

    def place(self, i, ti):
        """Projected corners (3x2), depth and surface normal of shard i, ti seconds after it let go."""
        c = self.c0[i] + self.vel[i] * ti
        c[1] += 0.5 * self.GRAVITY * ti * ti
        z = self.vz[i] * ti
        R = cv2.Rodrigues(self.tilt0[i] + self.w[i] * ti)[0]
        loc = np.zeros((3, 3))
        loc[:, :2] = self.verts[i] - self.c0[i]
        P = loc @ R.T
        d = CAM_D + P[:, 2] + z
        if d.min() < 350:
            return None
        s = (CAM_D / d)[:, None]
        ctr = np.array([W / 2, H / 2])
        return ctr + (P[:, :2] + c - ctr) * s, z, R[:, 2]

    def cracks(self, img, prog, bloom=True):
        """The held picture with cracks that have raced `prog` (0..1] of the way out from the impact point."""
        R = self.rmax * 1.03 * (1 - (1 - prog) ** 1.7)
        out = img.astype(np.float32)
        gm = np.ones((H, W), np.float32)
        for i in np.where(self.r < R)[0]:
            cv2.fillConvexPoly(gm, np.round(self.verts[i]).astype(np.int32), float(self.gain[i]))
        out *= gm[..., None]
        L = np.zeros((H, W), np.uint8)
        for path, val in self.cracks_paths:
            for a, b in zip(path[:-1], path[1:]):
                if np.hypot(*((a + b) / 2 - self.impact)) < R:
                    cv2.line(L, pt16(a), pt16(b), val, 1, cv2.LINE_AA, 4)
        Lf = L.astype(np.float32) / 255
        out *= (1 - 0.40 * np.roll(Lf, (1, 1), (0, 1)))[..., None]        # thin dark side: the crack has depth
        k = np.clip(0.92 * Lf + 0.20 * cv2.GaussianBlur(Lf, (0, 0), 2.2), 0, 1)[..., None]
        out = out * (1 - k) + self.EDGE * k
        if bloom:                                                       # the hit itself
            out += (255 - out) * (np.exp(-(self.dist / (45 + 90 * prog)) ** 2) * 0.7 * (1 - prog) ** 0.7
                                  + np.exp(-(self.dist / 9) ** 2) * 0.55)[..., None]
        return np.clip(out, 0, 255).astype(np.uint8)

    def render(self, pane, bg, t):
        """One frame of falling glass, t seconds after the pane let go: shards of `pane` over the live frame `bg`."""
        if getattr(self, '_pane', None) is not pane:                    # pieces still in place keep the cracked look
            self._pane, self._pane_f = pane, pane.astype(np.float32)
            self._cracked_f = self.cracks(pane, 1.0, bloom=False).astype(np.float32)
        bg_f = bg.astype(np.float32)
        acc = np.zeros((H, W, 3), np.float32)
        for k in range(self.NS):
            acc += self.sample(self._pane_f, bg_f, t + (k + 0.5) / self.NS * self.SHUTTER / FPS)
        return np.clip(acc / self.NS, 0, 255).astype(np.uint8)

    def sample(self, pane_f, bg_f, ts):
        st = []
        for i in range(self.n):
            ti = max(0.0, ts - self.delay[i])
            pl = self.place(i, ti)
            if pl is not None and self.on_screen(pl[0]):
                st.append((pl[1], i, pl[0], pl[2], ti))
        canvas = bg_f.copy()
        sm = np.zeros((H // 4, W // 4), np.uint8)                        # soft shadow of the glass on the live frame
        for z, i, pv, nrm, ti in st:
            if ti > 0:
                off = np.array([9.0, 14.0]) * (1 + min(2.0, -z / 450))
                cv2.fillConvexPoly(sm, np.round((pv + off) / 4 * 16).astype(np.int32), 255, cv2.LINE_AA, 4)
        if sm.any():
            sh = cv2.resize(cv2.GaussianBlur(sm, (0, 0), 5.5), (W, H), interpolation=cv2.INTER_LINEAR)
            canvas *= (1 - 0.36 * sh.astype(np.float32) / 255)[..., None]
        st.sort(key=lambda s: (-s[0], s[1]))                             # far first
        for z, i, pv, nrm, ti in st:
            x0, y0 = np.floor(pv.min(0)).astype(int) - 2
            x1, y1 = np.ceil(pv.max(0)).astype(int) + 3
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
            if x1 - x0 < 1 or y1 - y0 < 1:
                continue
            sv = self.verts[i]
            sx0, sy0 = np.maximum(np.floor(sv.min(0)).astype(int) - 2, 0)
            sx1, sy1 = np.minimum(np.ceil(sv.max(0)).astype(int) + 3, (W, H))
            M = cv2.getAffineTransform((sv - (sx0, sy0)).astype(np.float32), (pv - (x0, y0)).astype(np.float32))
            wp = cv2.warpAffine((pane_f if ti > 0 else self._cracked_f)[sy0:sy1, sx0:sx1], M, (int(x1 - x0), int(y1 - y0)),
                                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            loc = pv - (x0, y0)
            mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
            cv2.fillConvexPoly(mask, np.round(loc * 16).astype(np.int32), 255, cv2.LINE_AA, 4)
            g = float(abs(nrm @ self.LIGHT)) ** 16 if ti > 0 else 0.0     # glint when the facet faces the light
            tilt = 1 - abs(float(nrm[2]))
            refl = (0.06 + 0.42 * tilt ** 1.2) if ti > 0 else 0.0         # tilted glass mirrors the bright room
            shade = self.gain[i] * (0.60 + 0.40 * abs(nrm[2])) if ti > 0 else 1.0
            col = wp * (shade * (1 - refl)) + self.SKY * refl + 255 * 0.85 * g
            el = np.zeros_like(mask)                                    # bevel: bright on the edges that face the light
            ctr = loc.mean(0)
            for a, b in ((0, 1), (1, 2), (2, 0)):
                e = loc[b] - loc[a]
                nn = np.array([e[1], -e[0]]) / max(np.hypot(*e), 1e-3)
                if nn @ ((loc[a] + loc[b]) / 2 - ctr) < 0:
                    nn = -nn
                wgt = 0.30 + 0.70 * max(0.0, float(nn @ (-0.6, -0.8)))
                cv2.line(el, pt16(loc[a]), pt16(loc[b]), int(255 * wgt), 2, cv2.LINE_AA, 4)
            if ti > 0:                                                  # second, fainter line: the glass has thickness
                inner = ctr + (loc - ctr) * max(0.0, 1 - 9.0 / max(np.abs(loc - ctr).max(), 9.0))
                cv2.polylines(el, [np.round(inner * 16).astype(np.int32)], True, 70, 1, cv2.LINE_AA, 4)
            e = (el.astype(np.float32) / 255 * (0.85 + 0.15 * min(1.0, 4 * g)) * min(1.0, ti / 0.03))[..., None]
            col = col * (1 - e) + self.EDGE * e
            a = (mask.astype(np.float32) / 255 * ((0.93 - 0.30 * tilt) if ti > 0 else 1.0))[..., None]
            roi = canvas[y0:y1, x0:x1]
            roi *= 1 - a
            roi += col * a
        return canvas


def make(pl, verbose=False):
    """(Shatter, Glass or None) from a plan dict."""
    fx = Shatter(pl)
    glass = None
    if pl['ending'] == 'glass':
        glass = Glass(pl['glass']['impact'], pl['glass']['seed'], (fx.fg - fx.fr) / FPS, verbose)
    return fx, glass
