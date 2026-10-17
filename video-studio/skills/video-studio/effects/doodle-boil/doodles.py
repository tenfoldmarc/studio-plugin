"""Doodle library for doodle-boil. Every doodle is a list of chalk strokes in STROKE ORDER, in unit coords
(x right, y down, roughly -0.5..0.5). chalk.py draws them with the chalk, draw-on and boil.

Colours are palette SLOTS, not colours: 'cream' (main line), 'yellow' (second colour), 'pink' (third colour).
The CLIP block of build.py picks the palette and can override each slot with the buyer's own colours.
A cue's colour= replaces the main line slot, fill= the scribble fill, accent= every other stroke.
Strokes with ev='cross' only draw when the cue has cross=<word> (clapper scribble, chip X); any other doodle gets the
generic X from build.py.

New doodle = one function returning strokes in stroke order (S(pts, slot, width), FILL(poly, slot)), added to SHAPES
and to NAMES (the table in effect.md). Timing follows stroke length and order.
"""
import math

import numpy as np

# Colourways. The three slots keep their classic names; 'blush' puts lilac in the yellow slot.
PALETTES = {
    'classic': {'cream': (255, 248, 239), 'yellow': (250, 230, 122), 'pink': (246, 160, 186)},
    'blush': {'cream': (255, 244, 238), 'yellow': (203, 182, 246), 'pink': (250, 172, 200)},
}


def S(pts, color, width=10, press=0.95, dur=None, gap=0.0, kind='line', ev=None, **kw):
    p = None if pts is None else np.asarray(pts, np.float64)
    if dur is None:                       # time follows the length of the stroke
        ln = float(np.hypot(*np.diff(p, axis=0).T).sum()) if p is not None and len(p) > 1 else 1.0
        dur = min(0.26, max(0.03, 0.15 * ln))
    d = dict(pts=p, color=color, width=width, press=press, dur=dur, gap=gap, kind=kind, ev=ev)
    d.update(kw)
    return d


def FILL(poly, color, angle=-40, spacing=15, press=0.78, width=15, dur=0.16, gap=-0.04):
    return S(None, color, width=width, press=press, dur=dur, gap=gap, kind='fill', poly=np.asarray(poly, np.float64),
             angle=angle, spacing=spacing)


def arc(cx, cy, rx, ry, a0, a1, n=None):
    """Ellipse arc, degrees, increasing angle = clockwise on screen (0 = right, 90 = down)."""
    n = n or max(6, int(abs(a1 - a0) / 7))
    a = np.radians(np.linspace(a0, a1, n))
    return np.stack([cx + rx * np.cos(a), cy + ry * np.sin(a)], 1)


def spline(pts, closed=False, n=10):
    """Catmull-Rom through the points: soft organic curves."""
    P = np.asarray(pts, np.float64)
    P = np.concatenate([P[-1:], P, P[:2]]) if closed else np.concatenate([P[:1], P, P[-1:]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2])
    return np.array(out)


def over(pts, k=4):
    """Close a loop the way a hand does: run a little past the start."""
    pts = np.asarray(pts, np.float64)
    return np.concatenate([pts, pts[1:k + 1]])


def mirror(pts):
    return np.asarray(pts, np.float64) * np.array([-1.0, 1.0])


def blob(cx, cy, r, turns=2.3):
    """A chalk dot: a tight spiral from the middle out."""
    t = np.linspace(0.4, 2 * math.pi * turns, int(14 * turns))
    rr = r * (0.25 + 0.75 * t / t[-1])
    return np.stack([cx + rr * np.cos(t), cy + rr * np.sin(t)], 1)


# ---------------------------------------------------------------------------------------------------------- shapes
def heart_pts(extra=0.22):
    t = np.linspace(0, 2 * math.pi + extra, 90)
    x = 16 * np.sin(t) ** 3
    y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
    return np.stack([x / 34, (y - 2.5) / 34], 1)


def star_pts(r_in=0.21, ov=0.6):
    p = []
    for k in range(10):
        r = 0.5 if k % 2 == 0 else r_in
        a = -math.pi / 2 + k * math.pi / 5
        p.append((r * math.cos(a), r * math.sin(a)))
    p.append(p[0])
    p.append((p[0][0] + (p[1][0] - p[0][0]) * ov, p[0][1] + (p[1][1] - p[0][1]) * ov))
    return np.array(p)


def shape_heart(d):
    hp = heart_pts()
    return [
        S(hp, 'cream', width=11, press=0.97, dur=0.24, corner=1.5),
        S([(0.46, -0.50), (0.62, -0.74)], 'yellow', width=10, dur=0.04, gap=-0.04, taper=(8, 14)),
        S([(0.62, -0.26), (0.90, -0.36)], 'yellow', width=10, dur=0.04, taper=(8, 14)),
        S([(0.62, 0.0), (0.86, 0.10)], 'yellow', width=10, dur=0.04, taper=(8, 14)),
        S(None, 'pink', width=16, press=0.74, dur=0.24, gap=-0.10, kind='fill', poly=heart_pts(0)[:-1], angle=-38,
          spacing=16),
    ]


def shape_clapper(d):
    th = math.radians(24)
    u = np.array([math.cos(th), -math.sin(th)])
    nv = np.array([-math.sin(th), -math.cos(th)])
    A = np.array([-0.5, -0.17])
    Lr, Tk = 1.0, 0.15
    arm = [A, A + Lr * u, A + Lr * u + Tk * nv, A + Tk * nv, A, A + 0.12 * u]
    out = [
        S([(-0.5, -0.12), (0.5, -0.12), (0.5, 0.5), (-0.5, 0.5), (-0.5, -0.12), (-0.36, -0.125)], 'cream', width=11,
          dur=0.22),
        S([(-0.5, 0.045), (0.5, 0.04)], 'cream', width=10, dur=0.05),
        S(arm, 'cream', width=11, dur=0.17),
    ]
    for k in range(4):
        f = 0.16 + k * 0.22
        out.append(S([A + f * Lr * u + 0.01 * nv, A + (f + 0.10) * Lr * u + (Tk - 0.01) * nv], 'yellow', width=12,
                     dur=0.028))
    for k in range(4):
        x = -0.36 + k * 0.23
        out.append(S([(x, 0.03), (x + 0.10, -0.11)], 'yellow', width=12, dur=0.028))
    out.append(S([(-0.34, 0.20), (0.22, 0.19)], 'cream', width=8, press=0.8, dur=0.04))
    out.append(S([(-0.34, 0.34), (0.02, 0.335)], 'cream', width=8, press=0.8, dur=0.04))
    zz = []                                   # scribbled out (cue cross=<word>)
    rows = 8
    for k in range(rows + 1):
        x = -0.54 + k * (1.02 / rows)
        zz.append((x + (0.07 if k % 2 else 0.0), 0.50 if k % 2 else -0.70))
    out.append(S(zz, 'pink', width=14, press=1.0, dur=0.44, kind='zig', ev='cross', corner=5, zig=rows))
    return out


def shape_chip(d):
    o, i = 0.30, 0.125
    out = [
        S([(-o, -o), (o, -o), (o, o), (-o, o), (-o, -o), (-o + 0.16, -o - 0.005)], 'cream', width=11, dur=0.16,
          corner=7),
        S([(-i, -i), (i, -i), (i, i), (-i, i), (-i, -i - 0.01)], 'yellow', width=10, dur=0.07, corner=3),
    ]
    for side in range(4):
        for k in (-1, 0, 1):
            c = k * 0.17
            a, b = o + 0.035, o + 0.17
            p = {0: [(c, -a), (c, -b)], 1: [(a, c), (b, c)], 2: [(-c, a), (-c, b)], 3: [(-a, -c), (-b, -c)]}[side]
            out.append(S(p, 'cream', width=10, dur=0.016))
    out += cross_strokes()
    return out


def cross_strokes():
    """The pink X that lands on a cue's cross=<word> (chip has it built in; build.py adds it to any other doodle)."""
    return [S([(-0.50, -0.46), (-0.1, -0.06), (0.50, 0.50)], 'pink', width=17, press=1.0, dur=0.10, ev='cross', corner=6),
            S([(0.50, -0.50), (0.06, -0.02), (-0.48, 0.46)], 'pink', width=17, press=1.0, dur=0.10, gap=0.05, corner=6,
              grp='cross')]


def shape_crown(d):
    body = [(-0.45, 0.30), (-0.56, -0.24), (-0.25, 0.03), (0.0, -0.42), (0.25, 0.03), (0.56, -0.24), (0.45, 0.30),
            (-0.47, 0.305), (-0.50, 0.12)]
    out = [
        S(body, 'yellow', width=12, dur=0.20, corner=1.5),
        S(None, 'yellow', width=14, press=0.66, dur=0.16, gap=-0.05, kind='fill', poly=np.array(body[:7]), angle=-52,
          spacing=17),
        S([(-0.44, 0.16), (0.44, 0.155)], 'cream', width=9, dur=0.04),
    ]
    for (cx, cy) in [(-0.56, -0.33), (0.0, -0.52), (0.56, -0.33)]:
        t = np.linspace(0, 2 * math.pi * 1.2, 16)
        out.append(S(np.stack([cx + 0.042 * np.cos(t), cy + 0.042 * np.sin(t)], 1), 'pink', width=11, dur=0.03,
                     corner=1.0, taper=(4, 4)))
    return out


def shape_star(d):
    out = [S(star_pts(), 'cream', width=11, dur=0.17, corner=1.2)]
    if d.get('fill'):
        out.append(S(None, d['fill'], width=14, press=0.7, dur=0.15, gap=-0.04, kind='fill', poly=star_pts()[:10],
                     angle=-40, spacing=16))
    return out


def shape_pentagram(d):
    p = []
    for k in (0, 2, 4, 1, 3, 0):
        a = -math.pi / 2 + k * 2 * math.pi / 5
        p.append((0.5 * math.cos(a), 0.5 * math.sin(a)))
    p.append((p[0][0] + (p[1][0] - p[0][0]) * 0.25, p[0][1] + (p[1][1] - p[0][1]) * 0.25))
    return [S(p, 'cream', width=9, dur=0.16, corner=1.0)]


def shape_spiral(d):
    t = np.linspace(0.6, 2 * math.pi * 2.4, 70)
    r = 0.5 * t / t[-1]
    return [S(np.stack([r * np.cos(t), r * np.sin(t)], 1), 'pink', width=10, dur=0.16, corner=1.0)]


def shape_clock(d):
    return [S(arc(0, 0, 0.47, 0.46, -95, 275), 'cream', width=11, dur=0.24, corner=2),
            S([(0.0, 0.02), (0.0, -0.30)], 'yellow', width=12, dur=0.05, taper=(6, 10)),
            S([(-0.01, 0.0), (0.22, 0.12)], 'yellow', width=12, dur=0.045, taper=(6, 10)),
            S(blob(0.0, 0.0, 0.035, 1.5), 'pink', width=10, dur=0.03, corner=1, taper=(4, 4))] + \
        [S([(0.40 * math.cos(a), 0.40 * math.sin(a)), (0.33 * math.cos(a), 0.33 * math.sin(a))], 'cream', width=9,
           dur=0.02, taper=(4, 6)) for a in (-math.pi / 2, 0, math.pi / 2, math.pi)]


def shape_dollar(d):
    s = spline([(0.27, -0.25), (0.05, -0.36), (-0.22, -0.30), (-0.24, -0.08), (0.0, 0.0), (0.24, 0.10), (0.22, 0.32),
                (-0.05, 0.38), (-0.29, 0.25)])
    return [S(s, 'yellow', width=13, dur=0.22, corner=2),
            S([(0.01, -0.52), (-0.01, 0.52)], 'yellow', width=12, dur=0.07, gap=0.02, taper=(8, 12))]


def shape_bulb(d):
    glass = np.concatenate([[(-0.15, 0.20)], arc(0.0, -0.17, 0.33, 0.33, 150, 390), [(0.15, 0.20)]])
    out = [S(glass, 'cream', width=11, dur=0.24, corner=2),
           S([(-0.15, 0.25), (0.15, 0.25)], 'cream', width=9, dur=0.035),
           S([(-0.13, 0.33), (0.13, 0.33)], 'cream', width=9, dur=0.035),
           S([(-0.07, 0.41), (0.07, 0.41)], 'cream', width=9, dur=0.03),
           S([(-0.07, 0.17), (-0.04, -0.12), (0.0, -0.02), (0.04, -0.12), (0.07, 0.17)], 'pink', width=8, dur=0.07)]
    for a in (-150, -112, -68, -30):
        r = math.radians(a)
        out.append(S([(0.43 * math.cos(r), -0.17 + 0.43 * math.sin(r)), (0.56 * math.cos(r), -0.17 + 0.56 * math.sin(r))],
                     'yellow', width=10, dur=0.03, taper=(6, 10)))
    return out


def shape_sparkle(d):
    def spark(cx, cy, r, k=0.30):
        p = []
        for i in range(8):
            rr = (r * (1.12 if i % 4 == 0 else 0.92)) if i % 2 == 0 else r * k
            a = -math.pi / 2 + i * math.pi / 4
            p.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        return np.array(p + [p[0]])
    big = spark(-0.08, 0.06, 0.40)
    return [S(over(big, 1), 'yellow', width=10, corner=1.2), FILL(big[:-1], 'yellow', angle=-35, spacing=15),
            S(over(spark(0.34, -0.31, 0.17), 1), 'cream', width=9, corner=1.0),
            S(over(spark(0.30, 0.37, 0.11), 1), 'cream', width=8, corner=1.0)]


def shape_arrow(d):
    return [S(spline([(-0.50, 0.10), (-0.12, -0.03), (0.44, -0.02)]), 'cream', width=12, corner=2),
            S([(0.19, -0.26), (0.49, -0.02), (0.21, 0.23)], 'cream', width=12, corner=1.5, gap=0.02)]


def shape_arrow_curved(d):
    p0, p1, p2 = np.array([-0.46, -0.36]), np.array([-0.40, 0.46]), np.array([0.40, 0.14])
    t = np.linspace(0, 1, 30)[:, None]
    shaft = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2
    tg = (p2 - p1) / np.hypot(*(p2 - p1))
    tip = p2 + tg * 0.06

    def wing(deg):
        a = math.radians(deg)
        v = np.array([-tg[0] * math.cos(a) + tg[1] * math.sin(a), -tg[0] * math.sin(a) - tg[1] * math.cos(a)])
        return tip + v * 0.27
    return [S(shaft, 'cream', width=12, corner=2), S([wing(34), tip, wing(-38)], 'cream', width=12, corner=1.5, gap=0.02)]


def shape_underline(d):
    x = np.linspace(-0.5, 0.5, 70)
    u = x + 0.5
    y = 0.06 * np.sin(2 * math.pi * 3.5 * u) * (1 - 0.45 * u) - 0.02
    return [S(np.stack([x, y], 1), 'pink', width=12, dur=0.22, corner=2),
            S(spline([(0.44, 0.13), (0.0, 0.15), (-0.40, 0.17)]), 'pink', width=11, dur=0.10, gap=0.02)]


def shape_circle(d):
    t = np.linspace(0, 1.86, 110)
    a = np.radians(-150 + 360 * t)
    rx, ry = 0.50 * (1 - 0.055 * t), 0.37 * (1 - 0.10 * t)
    return [S(np.stack([0.02 * t + rx * np.cos(a), 0.015 * t + ry * np.sin(a)], 1), 'yellow', width=11, dur=0.34,
              corner=2)]


def shape_check(d):
    return [S([(-0.44, 0.0), (-0.17, 0.36), (0.47, -0.42)], 'cream', width=15, dur=0.14, corner=2.0)]


def shape_cross(d):
    return [S([(-0.40, -0.42), (-0.02, 0.0), (0.42, 0.42)], 'pink', width=15, dur=0.09, corner=5),
            S([(0.42, -0.44), (0.02, -0.02), (-0.42, 0.40)], 'pink', width=15, dur=0.09, gap=0.04, corner=5)]


def shape_exclaim(d):
    bar = [(-0.11, -0.50), (0.13, -0.48), (0.03, 0.17), (-0.03, 0.17)]
    return [S(over(np.array(bar + [bar[0]]), 1), 'yellow', width=10, corner=2.5), FILL(bar, 'yellow', angle=-30, spacing=13,
                                                                                     press=0.85),
            S(blob(0.0, 0.41, 0.085), 'yellow', width=11, dur=0.07, corner=1, taper=(4, 4))]


def shape_question(d):
    hook = np.concatenate([arc(0.0, -0.23, 0.25, 0.25, 178, 402), [(0.06, 0.02), (0.0, 0.10), (0.0, 0.20)]])
    return [S(hook, 'cream', width=14, dur=0.20, corner=5),
            S(blob(0.0, 0.42, 0.075), 'cream', width=11, dur=0.07, gap=0.03, corner=1, taper=(4, 4))]


def shape_flower(d):
    th = np.linspace(0, 2 * math.pi * 1.04, 120)
    r = 0.15 + 0.17 * np.abs(np.sin(2.5 * th)) ** 0.6
    cy = -0.18
    petals = np.stack([r * np.sin(th), cy - r * np.cos(th)], 1)
    return [S(petals, 'pink', width=11, dur=0.30, corner=1.6),
            S(blob(0.0, cy, 0.095, 2.6), 'yellow', width=12, dur=0.09, corner=1, taper=(4, 4)),
            S(spline([(0.0, 0.17), (0.05, 0.32), (-0.02, 0.52)]), 'cream', width=11, dur=0.08, taper=(6, 10)),
            S(spline([(0.03, 0.40), (0.14, 0.22), (0.34, 0.18), (0.24, 0.36), (0.04, 0.42)]), 'cream', width=9, dur=0.09)]


def shape_sun(d):
    out = [S(arc(0, 0, 0.21, 0.21, -100, 300), 'yellow', width=11, dur=0.16, corner=2),
           FILL(arc(0, 0, 0.21, 0.21, 0, 360, 28)[:-1], 'yellow', angle=-35, spacing=14)]
    for k in range(8):
        a = -math.pi / 2 + k * math.pi / 4
        r1 = 0.50 if k % 2 == 0 else 0.44
        out.append(S([(0.31 * math.cos(a), 0.31 * math.sin(a)), (r1 * math.cos(a), r1 * math.sin(a))], 'yellow', width=11,
                     dur=0.035, taper=(8, 14)))
    return out


def shape_cloud(d):
    p = np.concatenate([[(0.30, 0.24), (-0.30, 0.24)], arc(-0.31, 0.07, 0.17, 0.17, 95, 262),
                        arc(-0.11, -0.12, 0.21, 0.21, 188, 318), arc(0.17, -0.04, 0.18, 0.17, 236, 352),
                        arc(0.33, 0.10, 0.14, 0.14, 286, 448), [(0.20, 0.245)]])
    return [S(p, 'cream', width=11, dur=0.34, corner=2.2)]


def shape_bolt(d):
    p = [(-0.02, -0.50), (0.25, -0.50), (0.07, -0.09), (0.29, -0.09), (-0.17, 0.50), (-0.03, 0.05), (-0.25, 0.05)]
    return [S(over(np.array(p + [p[0]]), 1), 'cream', width=11, dur=0.24, corner=1.3),
            FILL(p, 'yellow', angle=-30, spacing=15, press=0.8)]


def shape_bubble(d):
    body = np.concatenate([arc(0.0, -0.08, 0.48, 0.34, 124, 460), [(-0.34, 0.47), (-0.262, 0.205)],
                           arc(0.0, -0.08, 0.48, 0.34, 130, 150, 4)])
    out = [S(body, 'cream', width=11, dur=0.32, corner=2)]
    for x in (-0.20, 0.0, 0.20):
        out.append(S(blob(x, -0.08, 0.05, 1.8), 'pink', width=10, dur=0.04, gap=0.02, corner=1, taper=(4, 4)))
    return out


def shape_smiley(d):
    return [S(arc(0, 0, 0.46, 0.45, -110, 300), 'yellow', width=11, dur=0.26, corner=2),
            S([(-0.15, -0.18), (-0.15, -0.05)], 'yellow', width=13, dur=0.035, taper=(6, 8)),
            S([(0.15, -0.18), (0.15, -0.05)], 'yellow', width=13, dur=0.035, taper=(6, 8)),
            S(arc(0, 0.0, 0.25, 0.24, 18, 162), 'yellow', width=11, dur=0.09, gap=0.02),
            S([(-0.36, 0.09), (-0.25, 0.05), (-0.35, 0.15), (-0.24, 0.11)], 'pink', width=10, press=0.8, dur=0.05, corner=2),
            S([(0.25, 0.05), (0.36, 0.09), (0.26, 0.13), (0.37, 0.15)], 'pink', width=10, press=0.8, dur=0.05, corner=2)]


def shape_coffee(d):
    def steam(x0):
        y = np.linspace(-0.20, -0.50, 22)
        return np.stack([x0 + 0.045 * np.sin((y + 0.2) * 23), y], 1)
    return [S(arc(-0.05, -0.07, 0.32, 0.07, -175, 200), 'cream', width=10, dur=0.14, corner=2),
            S(spline([(-0.37, -0.06), (-0.31, 0.24), (-0.19, 0.40), (0.09, 0.40), (0.21, 0.24), (0.27, -0.06)]), 'cream',
              width=11, dur=0.18, corner=2),
            S(spline([(0.26, 0.0), (0.44, 0.0), (0.47, 0.18), (0.21, 0.27)]), 'cream', width=10, dur=0.09),
            S([(-0.44, 0.47), (0.36, 0.475)], 'cream', width=9, dur=0.05),
            S(steam(-0.15), 'pink', width=9, dur=0.08, gap=0.02), S(steam(0.05), 'pink', width=9, dur=0.08)]


def shape_tag(d):
    body = [(-0.14, -0.27), (0.48, -0.27), (0.48, 0.27), (-0.14, 0.27), (-0.46, 0.0), (-0.14, -0.27), (0.04, -0.272)]
    return [S(body, 'cream', width=11, dur=0.26, corner=3.5),
            S(arc(-0.19, 0.0, 0.065, 0.065, 0, 420), 'cream', width=8, dur=0.05, corner=1, taper=(4, 4)),
            S(spline([(-0.25, 0.0), (-0.44, -0.16), (-0.50, -0.38), (-0.36, -0.46), (-0.29, -0.31), (-0.46, -0.24)]),
              'yellow', width=8, dur=0.12),
            S([(-0.02, -0.07), (0.34, -0.08)], 'yellow', width=9, dur=0.04), S([(-0.02, 0.08), (0.22, 0.07)], 'yellow',
                                                                                width=9, dur=0.035)]


def shape_butterfly(d):
    up = spline([(0.08, -0.05), (0.15, -0.36), (0.40, -0.48), (0.53, -0.30), (0.42, -0.05), (0.09, 0.03)], closed=True)
    lo = spline([(0.09, 0.09), (0.30, 0.07), (0.40, 0.24), (0.29, 0.43), (0.14, 0.34), (0.08, 0.16)], closed=True)
    ant = spline([(0.015, -0.24), (0.06, -0.40), (0.17, -0.50), (0.23, -0.44)])
    return [S(over(mirror(up)), 'cream', width=10, dur=0.15, corner=2), S(over(up), 'cream', width=10, dur=0.15, corner=2),
            S(over(mirror(lo)), 'cream', width=10, dur=0.11, corner=2), S(over(lo), 'cream', width=10, dur=0.11, corner=2),
            S([(0.0, -0.22), (0.005, 0.0), (0.0, 0.30)], 'cream', width=15, dur=0.06, taper=(8, 18)),
            S(mirror(ant), 'cream', width=8, dur=0.045), S(ant, 'cream', width=8, dur=0.045),
            FILL(mirror(up)[:-1], 'pink', angle=-40, spacing=15, dur=0.11),
            FILL(up[:-1], 'pink', angle=40, spacing=15, dur=0.11, gap=-0.02),
            S(blob(-0.24, 0.24, 0.055, 1.8), 'yellow', width=10, dur=0.04, corner=1, taper=(4, 4)),
            S(blob(0.24, 0.24, 0.055, 1.8), 'yellow', width=10, dur=0.04, corner=1, taper=(4, 4))]


def shape_bow(d):
    loop = spline([(-0.07, -0.15), (-0.30, -0.42), (-0.50, -0.38), (-0.49, 0.07), (-0.29, 0.11), (-0.07, -0.05)], closed=True)
    tail = np.array([(-0.06, -0.01), (-0.33, 0.50), (-0.19, 0.41), (-0.09, 0.51), (-0.01, 0.02)])
    knot = spline([(-0.08, -0.175), (0.08, -0.185), (0.09, -0.02), (-0.08, -0.01)], closed=True)
    return [S(over(loop), 'cream', width=10, dur=0.17, corner=2), S(over(mirror(loop)), 'cream', width=10, dur=0.17, corner=2),
            S(over(knot, 3), 'cream', width=10, dur=0.06, corner=1.5),
            S(tail, 'cream', width=9, dur=0.12, corner=1.5), S(mirror(tail), 'cream', width=9, dur=0.12, corner=1.5),
            S([(-0.13, -0.11), (-0.31, -0.16)], 'cream', width=8, dur=0.03), S([(0.13, -0.11), (0.31, -0.16)], 'cream',
                                                                               width=8, dur=0.03),
            FILL(loop[:-1], 'pink', angle=-35, spacing=15, dur=0.12), FILL(mirror(loop)[:-1], 'pink', angle=35, spacing=15,
                                                                           dur=0.12, gap=-0.03)]


def shape_dot(d):
    return [S(blob(0, 0, 0.5, 3.2), 'cream', width=12, dur=0.10, corner=1, taper=(4, 4))]


SHAPES = dict(sparkle=shape_sparkle, arrow=shape_arrow, arrow_curved=shape_arrow_curved, underline=shape_underline,
              circle=shape_circle, check=shape_check, cross=shape_cross, exclaim=shape_exclaim, question=shape_question,
              flower=shape_flower, sun=shape_sun, cloud=shape_cloud, bolt=shape_bolt, bubble=shape_bubble,
              smiley=shape_smiley, coffee=shape_coffee, tag=shape_tag, butterfly=shape_butterfly, bow=shape_bow,
              dot=shape_dot, heart=shape_heart, clapper=shape_clapper, chip=shape_chip, crown=shape_crown,
              star=shape_star, pentagram=shape_pentagram, spiral=shape_spiral, clock=shape_clock, dollar=shape_dollar,
              bulb=shape_bulb)

# What each doodle reads as, for picking one per word (the table in effect.md is built from this).
NAMES = {
    'heart': 'love, people you care about, favourite', 'star': 'best, standout, rating', 'sparkle': 'new, magic, shiny',
    'crown': 'winning, results, the best (finale)', 'arrow': 'this, next, points at something', 'arrow_curved': 'look here, turn',
    'underline': 'stress a word', 'circle': 'this one, highlight', 'check': 'yes, done, works', 'cross': 'no, wrong, stop',
    'exclaim': 'warning, wow, important', 'question': 'why, how, confused', 'flower': 'grow, soft, pretty',
    'sun': 'day, bright, morning', 'cloud': 'think, dream, online', 'bolt': 'fast, power, energy',
    'bubble': 'talk, say, comment', 'smiley': 'happy, easy, fun', 'coffee': 'morning, work, break', 'tag': 'price, cost, sale',
    'butterfly': 'change, light, pretty', 'bow': 'gift, cute, wrapped up', 'clapper': 'video, film, editing',
    'chip': 'tech, AI, computer', 'clock': 'time, hours, wait', 'dollar': 'money, paid, revenue', 'bulb': 'idea, learn, smart',
    'pentagram': 'small star (finale sprinkle)', 'spiral': 'dizzy, loop (finale sprinkle)', 'dot': 'tiny accent',
}

# The sheet: 24 doodles, 4 columns x 6 rows. (name, options). Options are the same keys doodle() takes.
LIBRARY = [
    ('heart', dict(size=128, rot=8)), ('star', dict(size=150, fill='yellow', rot=-8)), ('sparkle', dict(size=150)),
    ('crown', dict(size=140, rot=-4)),
    ('arrow', dict(size=170, rot=-6)), ('arrow_curved', dict(size=160, colour='yellow')), ('underline', dict(size=180)),
    ('circle', dict(size=170, rot=-6)),
    ('check', dict(size=140, colour='yellow')), ('cross', dict(size=130)), ('exclaim', dict(size=150, rot=6)),
    ('question', dict(size=150, rot=4)),
    ('flower', dict(size=160)), ('sun', dict(size=160)), ('cloud', dict(size=170)), ('bolt', dict(size=160, rot=4)),
    ('bubble', dict(size=160)), ('smiley', dict(size=150, rot=-5)), ('coffee', dict(size=160)), ('tag', dict(size=160, rot=-16)),
    ('butterfly', dict(size=165, rot=6)), ('bow', dict(size=170)), ('clapper', dict(size=140, rot=-4, dy=14)),
    ('chip', dict(size=165)),
]
