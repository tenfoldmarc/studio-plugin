"""word-pile physics: a small deterministic 2D rigid-body solver for rounded slabs (no physics package needed).

Bodies are rounded rectangles. Obstacles: the drawn floor line (a half-plane), two side walls that open outwards
above the pile, and per-frame distance fields of the speaker's head and body (made from the cutout by build.py).
Sequential impulses with friction, restitution and sleeping. Plain Python + numpy, fixed step, no randomness:
the same inputs give the same track every run.
"""
import math

import numpy as np

FLOOR, WALL, HEAD, HIM, SLAB = 1, 2, 4, 8, 16
GRAV = 5200.0                 # px/s^2
ITERS = 10
BETA, SLOP, BIAS_MAX = 0.22, 0.6, 700.0
REST_V = 120.0                # px/s: slower impacts do not bounce
SLEEP_V, SLEEP_W, SLEEP_T = 9.0, 0.07, 0.22
SWITCH_DELAY = 0.07           # s after the first hit on his outline that a slab comes in front of him
MU = {FLOOR: 0.55, WALL: 0.19, HEAD: 0.06, HIM: 0.28, SLAB: 0.5}
EL = {FLOOR: 0.08, WALL: 0.2, HEAD: 0.3, HIM: 0.25, SLAB: 0.24}
ELAST = 0.24


class Field:
    """Signed distance (full-res px, + outside) per frame on a coarse grid (cell = scale px)."""

    def __init__(self, sdf, scale):
        self.sdf, self.s = sdf, float(scale)
        self.h, self.w = sdf.shape[1:]

    def sample(self, f, pts):
        g = self.sdf[min(f, len(self.sdf) - 1)]
        u = np.clip(pts[:, 0] / self.s - 0.5, 0, self.w - 1.001)
        v = np.clip(pts[:, 1] / self.s - 0.5, 0, self.h - 1.001)
        j, i = u.astype(np.int32), v.astype(np.int32)
        fu, fv = u - j, v - i
        g00, g01 = g[i, j].astype(np.float32), g[i, j + 1].astype(np.float32)
        g10, g11 = g[i + 1, j].astype(np.float32), g[i + 1, j + 1].astype(np.float32)
        d = (g00 * (1 - fu) + g01 * fu) * (1 - fv) + (g10 * (1 - fu) + g11 * fu) * fv
        gx = (g01 - g00) * (1 - fv) + (g11 - g10) * fv
        gy = (g10 - g00) * (1 - fu) + (g11 - g01) * fu
        n = np.hypot(gx, gy)
        ok = n > 1e-4
        nx = np.where(ok, gx / np.maximum(n, 1e-4), 0.0)
        ny = np.where(ok, gy / np.maximum(n, 1e-4), -1.0)
        # outside the grid (a slab entering above the frame) nothing is there
        out = (pts[:, 1] < 0) | (pts[:, 0] < 0) | (pts[:, 0] > self.w * self.s)
        d = np.where(out, 1e4, d)
        return d, nx, ny


class Body:
    __slots__ = ('i', 'w', 'h', 'a', 'b', 'r', 'm', 'im', 'ii', 'x', 'y', 'ang', 'vx', 'vy', 'om', 'pts', 'e',
                 'spawned', 'asleep', 'sleep_t', 'hit_t', 'front', 'grip_t', 'floor_t', 'floor_x', 'floor_v',
                 'slab_t', 'head_hit', 'wall_lean', 'cfg', 'touch')

    def __init__(self, i, s):
        self.i, self.cfg = i, s
        self.w, self.h = float(s['w']), float(s['h'])
        self.r = min(14.0, 0.2 * min(self.w, self.h))
        self.a, self.b = self.w / 2 - self.r, self.h / 2 - self.r
        self.m = self.w * self.h * 1e-4 * s.get('weight', 1.0)
        inertia = self.m * (self.w ** 2 + self.h ** 2) / 12.0
        self.im, self.ii = 1.0 / self.m, 1.0 / inertia
        self.e = ELAST / (s.get('weight', 1.0) ** 0.8)       # heavy slabs thud, they do not bounce
        # sample points on the inner box (corners + every ~20 px along the edges)
        nx_, ny_ = max(2, int(math.ceil(2 * self.a / 20)) + 1), max(2, int(math.ceil(2 * self.b / 20)) + 1)
        xs, ys = np.linspace(-self.a, self.a, nx_), np.linspace(-self.b, self.b, ny_)
        p = [(x, -self.b) for x in xs] + [(x, self.b) for x in xs] + [(-self.a, y) for y in ys[1:-1]] + \
            [(self.a, y) for y in ys[1:-1]]
        self.pts = np.array(p, np.float64)
        self.x = self.y = self.ang = self.vx = self.vy = self.om = 0.0
        self.spawned = self.asleep = self.front = self.head_hit = False
        self.sleep_t, self.grip_t, self.wall_lean = 0.0, -9.0, 0.0
        self.hit_t = self.floor_t = self.slab_t = None
        self.floor_x = self.floor_v = 0.0
        self.touch = 0

    def world_pts(self):
        c, s = math.cos(self.ang), math.sin(self.ang)
        P = self.pts
        return np.stack([self.x + P[:, 0] * c - P[:, 1] * s, self.y + P[:, 0] * s + P[:, 1] * c], 1)


class World:
    def __init__(self, cfg, slabs, head=None, him=None):
        """cfg: fps, sub, floor_y, wall_l, wall_r, wall_top, t_sweep, sweep_dir (None = away from the middle)."""
        self.c = cfg
        self.head, self.him = head, him
        self.bodies = [Body(i, s) for i, s in enumerate(slabs)]
        self.dt = 1.0 / (cfg['fps'] * cfg['sub'])
        self.t, self.step_i = 0.0, 0
        self.sweep_dir = cfg.get('sweep_dir')
        self.walls_on = True
        n_steps = int(cfg['n'] * cfg['sub'])
        self.track = np.full((len(slabs), n_steps, 3), np.nan, np.float32)

    # ------------------------------------------------------------------ contacts
    def _reduce(self, bi, d, nx, ny, P, rad, kind, ob, out, off=None):
        """Keep at most two contacts per (body, obstacle): the deepest and the one farthest from it."""
        hit = np.nonzero(d < rad + 0.5)[0]
        if not len(hit):
            return
        k0 = hit[np.argmin(d[hit])]
        sel = [k0]
        if len(hit) > 1:
            dd = np.hypot(P[hit, 0] - P[k0, 0], P[hit, 1] - P[k0, 1])
            k1 = hit[np.argmax(dd)]
            if dd.max() > 4:
                sel.append(k1)
        off = bi.r if off is None else off
        for k in sel:
            n_x, n_y = float(nx[k]), float(ny[k])
            out.append([bi, ob, n_x, n_y, float(P[k, 0]) - n_x * off, float(P[k, 1]) - n_y * off,
                        float(rad - d[k]), kind])

    def _box_vs(self, A, B, P):
        """A's sample points against B's rounded box -> distance to B's inner box and the normal (out of B)."""
        c, s = math.cos(B.ang), math.sin(B.ang)
        dx, dy = P[:, 0] - B.x, P[:, 1] - B.y
        qx, qy = dx * c + dy * s, -dx * s + dy * c
        ex, ey = np.abs(qx) - B.a, np.abs(qy) - B.b
        ox, oy = np.maximum(ex, 0), np.maximum(ey, 0)
        dout = np.hypot(ox, oy)
        inside = (ex <= 0) & (ey <= 0)
        d = np.where(inside, np.maximum(ex, ey), dout)
        lx = np.where(inside, np.where(ex > ey, np.sign(qx), 0.0), np.sign(qx) * ox / np.maximum(dout, 1e-6))
        ly = np.where(inside, np.where(ex > ey, 0.0, np.sign(qy)), np.sign(qy) * oy / np.maximum(dout, 1e-6))
        lx = np.where(lx == 0, np.where(ly == 0, 0.0, lx), lx)
        return d, lx * c - ly * s, lx * s + ly * c

    def contacts(self, f):
        cf = self.c
        out = []
        live = [b for b in self.bodies if b.spawned]
        for A in live:
            if A.asleep:
                continue
            P = A.world_pts()
            # floor line (half-plane)
            d = cf['floor_y'] - P[:, 1]
            self._reduce(A, d, np.zeros_like(d), -np.ones_like(d), P, A.r, FLOOR, None, out)
            if self.walls_on:
                for side in (-1, 1):
                    xw = cf['wall_l'] if side < 0 else cf['wall_r']
                    # vertical beside the pile, opening outwards above wall_top (nothing jams between wall and head)
                    above = np.maximum(0.0, cf['wall_top'] - P[:, 1])
                    xb = xw + side * above * 0.35
                    d = (P[:, 0] - xb) * (-side) / np.sqrt(1 + 0.35 ** 2 * (above > 0))
                    nx = np.where(above > 0, -side / 1.0595, float(-side))
                    ny = np.where(above > 0, -0.35 / 1.0595, 0.0)
                    self._reduce(A, d, nx, ny, P, A.r, WALL, None, out)
            if self.head is not None:
                d, nx, ny = self.head.sample(f, P)
                self._reduce(A, d, nx, ny, P, A.r, HEAD, None, out)
            if self.him is not None and not A.front:
                d, nx, ny = self.him.sample(f, P)
                self._reduce(A, d, nx, ny, P, A.r, HIM, None, out)
        for ia in range(len(live)):
            for ib in range(ia + 1, len(live)):
                A, B = live[ia], live[ib]
                if A.asleep and B.asleep:
                    continue
                lim = math.hypot(A.w, A.h) / 2 + math.hypot(B.w, B.h) / 2 + 2
                if abs(A.x - B.x) > lim or abs(A.y - B.y) > lim:
                    continue
                for X, Y in ((A, B), (B, A)):
                    P = X.world_pts()
                    d, nx, ny = self._box_vs(X, Y, P)
                    rad = X.r + Y.r
                    if X.asleep:      # the awake one is pushed along -n from the sleeper's points
                        self._reduce(Y, d, -nx, -ny, P, rad, SLAB, X, out, off=-X.r)
                    else:
                        self._reduce(X, d, nx, ny, P, rad, SLAB, Y, out)
        return out

    # ------------------------------------------------------------------ solver
    def solve(self, cons):
        dt = self.dt
        rows = []
        for A, B, nx, ny, cx, cy, pen, kind in cons:
            bs = B is not None and not B.asleep
            rax, ray = cx - A.x, cy - A.y
            rbx, rby = (cx - B.x, cy - B.y) if B is not None else (0.0, 0.0)
            imb, iib = (B.im, B.ii) if bs else (0.0, 0.0)
            rna, rnb = rax * ny - ray * nx, rbx * ny - rby * nx
            kn = A.im + imb + A.ii * rna * rna + iib * rnb * rnb
            tx, ty = -ny, nx
            rta, rtb = rax * ty - ray * tx, rbx * ty - rby * tx
            kt = A.im + imb + A.ii * rta * rta + iib * rtb * rtb
            vax, vay = A.vx - A.om * ray, A.vy + A.om * rax
            vbx, vby = (B.vx - B.om * rby, B.vy + B.om * rbx) if bs else (0.0, 0.0)
            vn = (vax - vbx) * nx + (vay - vby) * ny
            if B is not None and B.asleep and vn < -60.0:
                B.asleep, B.sleep_t = False, 0.0       # hit hard enough: wake it (it takes part from the next step)
            e = A.e * (B.e if kind == SLAB else EL[kind])
            bias = max(-e * vn if vn < -REST_V else 0.0, min(BIAS_MAX, BETA / dt * max(0.0, pen - SLOP)))
            mu = MU[kind]
            if kind & (FLOOR | SLAB | HIM) and self.t - A.grip_t < 0.06:
                mu = 0.0                               # leaning on his head or a wall: no grip anywhere else
            rows.append([A, B if bs else None, nx, ny, tx, ty, rax, ray, rbx, rby, 1.0 / kn, 1.0 / kt, bias, mu, 0.0, 0.0])
            if kind & (HEAD | WALL):
                A.grip_t = self.t
        for _ in range(ITERS):
            for r in rows:
                A, B, nx, ny, tx, ty, rax, ray, rbx, rby, mn, mt, bias, mu = r[:14]
                vx, vy = A.vx - A.om * ray, A.vy + A.om * rax
                if B is not None:
                    vx -= B.vx - B.om * rby
                    vy -= B.vy + B.om * rbx
                vn = vx * nx + vy * ny
                p0 = r[14]
                r[14] = max(p0 + (bias - vn) * mn, 0.0)
                dp = r[14] - p0
                px, py = dp * nx, dp * ny
                vt = vx * tx + vy * ty
                q0 = r[15]
                lim = mu * r[14]
                r[15] = min(max(q0 - vt * mt, -lim), lim)
                dq = r[15] - q0
                px += dq * tx
                py += dq * ty
                A.vx += px * A.im
                A.vy += py * A.im
                A.om += (rax * py - ray * px) * A.ii
                if B is not None:
                    B.vx -= px * B.im
                    B.vy -= py * B.im
                    B.om -= (rbx * py - rby * px) * B.ii
        return rows

    # ------------------------------------------------------------------ stepping
    def run(self, f_end, hook=None):
        cf = self.c
        sub, dt = cf['sub'], self.dt
        while self.step_i < f_end * sub:
            f = self.step_i // sub
            t = self.step_i * dt
            self.t = t
            sweeping = cf.get('t_sweep') is not None and t >= cf['t_sweep']
            if sweeping and self.walls_on:
                self.walls_on = False
                if self.sweep_dir is None:
                    xs = [b.x for b in self.bodies if b.spawned]
                    self.sweep_dir = 1 if (np.mean(xs) if xs else 0) > cf['mid_x'] else -1
            for b in self.bodies:
                s = b.cfg
                if not b.spawned and t >= s['t_spawn']:
                    b.spawned = True
                    b.x, b.y, b.ang = s['x'], s['y'], math.radians(s['ang'])
                    b.vx, b.vy, b.om = s.get('vx', 0.0), s.get('vy', 1500.0), s.get('spin', 0.0)
                if not b.spawned:
                    continue
                if not b.front and b.hit_t is not None and t - b.hit_t >= SWITCH_DELAY:
                    b.front = True
                if sweeping:
                    sd = self.sweep_dir
                    up = (cf['wall_r'] - b.x) if sd < 0 else (b.x - cf['wall_l'])
                    ts = t - cf['t_sweep'] - max(0.0, up) / 9000.0
                    if ts >= 0:
                        b.asleep = False
                        ramp = min(1.0, ts / 0.10)
                        b.vx += sd * 15000.0 * ramp * dt
                        b.vy += GRAV * (1 - (1.18 if ts < 0.14 else 0.95)) * dt
                        b.om += (26.0 if b.i % 2 else -22.0) * ramp * dt
                        continue
                if not b.asleep:
                    b.vy += GRAV * dt
            cons = self.contacts(f)
            for b in self.bodies:
                b.touch = 0
            for A, B, nx, ny, cx, cy, pen, kind in cons:
                A.touch |= kind
                if kind & (HEAD | HIM) and A.hit_t is None:
                    A.hit_t = t
                if kind == HEAD:
                    A.head_hit = True
                if kind == FLOOR and A.floor_t is None and not sweeping:
                    A.floor_t, A.floor_x, A.floor_v = t, cx, math.hypot(A.vx, A.vy)
                if kind == SLAB and B is not None:
                    late = A if A.i > B.i else B
                    if late.slab_t is None and not sweeping:
                        late.slab_t = t
                if kind == WALL:
                    lean = abs((math.degrees(A.ang) + 90) % 180 - 90)
                    if lean > 12 and math.hypot(A.vx, A.vy) < 260:
                        A.wall_lean += dt
            self.solve(cons)
            for b in self.bodies:
                if not b.spawned or b.asleep:
                    if b.spawned:
                        self.track[b.i, self.step_i] = (b.x, b.y, b.ang)
                    continue
                b.x += b.vx * dt
                b.y += b.vy * dt
                b.ang += b.om * dt
                if not sweeping and b.touch and math.hypot(b.vx, b.vy) < SLEEP_V and abs(b.om) < SLEEP_W:
                    b.sleep_t += dt
                    if b.sleep_t > SLEEP_T:
                        b.asleep, b.vx, b.vy, b.om = True, 0.0, 0.0, 0.0
                else:
                    b.sleep_t = 0.0
                self.track[b.i, self.step_i] = (b.x, b.y, b.ang)
            self.step_i += 1
            if hook:
                hook(self)
        return self

    def events(self):
        return [dict(hit_t=b.hit_t, head=b.head_hit, floor_t=b.floor_t, floor_x=b.floor_x, floor_v=b.floor_v,
                     slab_t=b.slab_t, wall_lean=b.wall_lean) for b in self.bodies]


def corners(x, y, ang, w, h):
    c, s = math.cos(ang), math.sin(ang)
    return [(x + dx * c - dy * s, y + dx * s + dy * c) for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
