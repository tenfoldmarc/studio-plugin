"""neon.py: reusable machinery for a glass-tube neon sign that sits on a wall plane and lights the room.

    lettering(text, font, size, origin, ...)  -> smooth single-stroke centre lines of a script face ("chains")
    stroke(points)                            -> a hand-set stroke (underline, arrow) as a chain
    Tube(chains, ...)                         -> the glass in plane space: unlit shading, shadow, emission profile,
                                                 electrode ends, standoffs
    spill(points, occluders, ...)             -> the light a tube throws on the wall, with soft shadows behind
                                                 whatever stands proud of the wall

All geometry is in "plane units" (one plane unit = one pixel of the slot's first frame, 1080x1920). Only numpy +
OpenCV + PIL. Fonts come from the slot's assets/fonts/fonts.css (never a system font).
"""
import os
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TRACE_RS = 4          # the face is traced at this many pixels per plane unit


def sstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------------------------------------------------------------
# fonts: the slot's fonts.css
# ---------------------------------------------------------------------------------------------------------------------
def font_table(fonts_dir):
    """Every @font-face in assets/fonts/fonts.css -> [(family, style, weight, path)]."""
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
    """-> [path, weight] of the closest face of that family (italic falls back to upright and back)."""
    faces = [f for f in table if f[0].lower() == family.lower()]
    if not faces:
        have = sorted({f[0] for f in table})
        raise SystemExit(f'font "{family}" is not in assets/fonts/fonts.css. Families there: {", ".join(have)}')
    want = 'italic' if italic else 'normal'
    same = [f for f in faces if f[1] == want] or faces
    best = min(same, key=lambda f: abs(f[2] - weight))
    return [best[3], weight]


def load_font(spec, px):
    """spec = [path, weight]. Variable faces follow the weight; a static file stays what it is."""
    path, weight = spec
    f = ImageFont.truetype(path, px)
    try:
        vals = []
        for a in f.get_variation_axes():
            name = a['name'].decode() if isinstance(a['name'], bytes) else str(a['name'])
            v = weight if name.lower().startswith('weight') else a['default']
            vals.append(max(a['minimum'], min(a['maximum'], v)))
        f.set_variation_by_axes(vals)
    except Exception:
        pass
    return f


def thin(img):
    """Zhang-Suen thinning of a boolean image, then strip staircase corners so a plain line pixel has exactly two
    8-neighbours."""
    im = np.pad(img.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p2, p3, p4 = im[:-2, 1:-1], im[:-2, 2:], im[1:-1, 2:]
            p5, p6, p7 = im[2:, 2:], im[2:, 1:-1], im[2:, :-2]
            p8, p9 = im[1:-1, :-2], im[:-2, :-2]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            b = sum(n.astype(np.int16) for n in nb)
            a = sum(((nb[i] == 0) & (nb[(i + 1) % 8] == 1)).astype(np.int16) for i in range(8))
            if step == 0:
                c = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                c = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            kill = (im[1:-1, 1:-1] == 1) & (b >= 2) & (b <= 6) & (a == 1) & c
            if kill.any():
                im[1:-1, 1:-1][kill] = 0
                changed = True
        if not changed:
            break
    # staircase corners: a pixel whose only neighbours are two 4-neighbours at right angles is redundant
    for rot in range(4):
        v = np.rot90(im, rot)
        c = v[1:-1, 1:-1]
        n, e, s, w = v[:-2, 1:-1], v[1:-1, 2:], v[2:, 1:-1], v[1:-1, :-2]
        ne, nw, se = v[:-2, 2:], v[:-2, :-2], v[2:, 2:]
        kill = (c == 1) & (w == 1) & (s == 1) & (n == 0) & (e == 0) & (ne == 0) & (nw == 0) & (se == 0)
        c[kill] = 0
    return im[1:-1, 1:-1].astype(bool)


_N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _smooth(poly, sigma, step=2.0):
    """Resample a polyline at `step` px and low-pass it along its length; the two ends stay where they are."""
    p = np.float64(poly)
    if len(p) < 3:
        return p
    seg = np.hypot(*np.diff(p, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < step * 2:
        return p
    n = max(int(round(s[-1] / step)), 2)
    t = np.linspace(0, s[-1], n + 1)
    q = np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], 1)
    k = int(min(np.ceil(sigma / step * 3), len(q) - 1))
    if k < 1:
        return q
    x = np.arange(-k, k + 1)
    g = np.exp(-0.5 * (x * step / sigma) ** 2)
    g /= g.sum()
    head = 2 * q[0] - q[k:0:-1]                 # point reflection: no shrinking at the ends
    tail = 2 * q[-1] - q[-2:-k - 2:-1]
    ext = np.vstack([head, q, tail])
    return np.stack([np.convolve(ext[:, 0], g, mode='valid'), np.convolve(ext[:, 1], g, mode='valid')], 1)


def trace(sk, spur, merge, smooth):
    """Skeleton image -> list of smooth chains. A chain is dict(pts=Nx2 float (x, y) px, ends=[bool, bool]) where
    ends[i] is True when that extremity is a free tube end (False: it joins another chain)."""
    pix = set(map(tuple, np.argwhere(sk)))

    def adj(p):
        return [(p[0] + dy, p[1] + dx) for dy, dx in _N8 if (p[0] + dy, p[1] + dx) in pix]

    deg = {p: len(adj(p)) for p in pix}
    node_pix = {p for p in pix if deg[p] != 2}
    # cluster touching node pixels
    node_of, nodes = {}, []
    for p in node_pix:
        if p in node_of:
            continue
        stack, members = [p], []
        node_of[p] = len(nodes)
        while stack:
            c = stack.pop()
            members.append(c)
            for q in adj(c):
                if q in node_pix and q not in node_of:
                    node_of[q] = len(nodes)
                    stack.append(q)
        nodes.append(dict(pos=np.mean(np.float64(members), 0)[::-1], free=all(deg[m] <= 1 for m in members)))
    edges, visited = [], set()
    for p in node_pix:
        for q in adj(p):
            if q in node_pix or q in visited:
                continue
            path, prev, cur = [p, q], p, q
            while cur not in node_pix:
                visited.add(cur)
                nx = [n for n in adj(cur) if n != prev and n not in path[-3:]]
                if not nx:
                    break
                nx.sort(key=lambda n: (n not in node_pix, abs(n[0] - cur[0]) + abs(n[1] - cur[1])))
                prev, cur = cur, nx[0]
                path.append(cur)
            if cur in node_pix:
                edges.append(dict(a=node_of[p], b=node_of[cur], pts=np.float64(path)[:, ::-1]))
    # isolated pixels and tiny blobs (dots): a chain of one point
    dots = [n['pos'] for i, n in enumerate(nodes) if not any(e['a'] == i or e['b'] == i for e in edges)]

    def length(e):
        return float(np.hypot(*np.diff(e['pts'], axis=0).T).sum())

    # spurs: short branches that end free
    for _ in range(3):
        inc = {}
        for e in edges:
            inc[e['a']] = inc.get(e['a'], 0) + 1
            inc[e['b']] = inc.get(e['b'], 0) + 1
        keep = []
        for e in edges:
            fa, fb = nodes[e['a']]['free'] and inc[e['a']] == 1, nodes[e['b']]['free'] and inc[e['b']] == 1
            if (fa != fb) and length(e) < spur and inc[e['b'] if fa else e['a']] >= 3:
                continue
            keep.append(e)
        if len(keep) == len(edges):
            break
        edges = keep
    # junction pairs joined by a very short edge (the Z a medial axis draws where two strokes meet): merge them
    parent = list(range(len(nodes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    keep = []
    for e in edges:
        if length(e) < merge and not nodes[e['a']]['free'] and not nodes[e['b']]['free'] and e['a'] != e['b']:
            parent[find(e['a'])] = find(e['b'])
        else:
            keep.append(e)
    edges = keep
    groups = {}
    for i in range(len(nodes)):
        groups.setdefault(find(i), []).append(i)
    pos = {r: np.mean([nodes[i]['pos'] for i in m], 0) for r, m in groups.items()}
    for e in edges:
        e['a'], e['b'] = find(e['a']), find(e['b'])
        e['pts'] = np.vstack([pos[e['a']], e['pts'][1:-1], pos[e['b']]])
    # at every node pair up the two edge ends that run straightest through it; chains follow the pairs
    ends_at = {}
    for i, e in enumerate(edges):
        ends_at.setdefault(e['a'], []).append((i, 0))
        ends_at.setdefault(e['b'], []).append((i, 1))

    def direction(i, side, reach=28):
        p = edges[i]['pts'] if side == 0 else edges[i]['pts'][::-1]
        v = p[min(reach, len(p) - 1)] - p[0]
        return v / (np.linalg.norm(v) + 1e-9)
    partner = {}
    for n, lst in ends_at.items():
        cand = []
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                if lst[x][0] == lst[y][0]:
                    continue
                cand.append((float(direction(*lst[x]) @ direction(*lst[y])), lst[x], lst[y]))
        cand.sort(key=lambda c: c[0])
        for dot, u, v in cand:
            if u in partner or v in partner:
                continue
            if dot < -0.45 or len(lst) == 2:
                partner[u], partner[v] = v, u
        left = [u for u in lst if u not in partner]
        if len(lst) >= 4 and len(left) == 2 and left[0][0] != left[1][0]:     # a crossing: the other stroke
            partner[left[0]], partner[left[1]] = left[1], left[0]
    chains, used = [], set()

    def follow(i, side):
        """Walk from edge i entering at `side`, return points and the far (edge, side)."""
        pts = []
        while True:
            used.add(i)
            p = edges[i]['pts'] if side == 0 else edges[i]['pts'][::-1]
            pts.append(p if not pts else p[1:])
            far = (i, 1 - side)
            if far not in partner or partner[far][0] in used:
                return np.vstack(pts), far
            i, side = partner[far]
    starts = [(i, s) for i in range(len(edges)) for s in (0, 1) if (i, s) not in partner]
    for (i, s) in starts + [(i, 0) for i in range(len(edges))]:
        if i in used:
            continue
        pts, far = follow(i, s)
        na = edges[i]['a'] if s == 0 else edges[i]['b']
        nb_ = edges[far[0]]['b'] if far[1] == 1 else edges[far[0]]['a']
        free_a = len(ends_at[na]) == 1
        free_b = len(ends_at[nb_]) == 1
        chains.append(dict(pts=_smooth(pts, smooth), ends=[free_a, free_b]))
    # re-attach branch ends to the smoothed through-stroke they grew from
    for ci, c in enumerate(chains):
        for side in (0, 1):
            if c['ends'][side]:
                continue
            tip = c['pts'][0 if side == 0 else -1]
            best, bd = None, 1e9
            for cj, o in enumerate(chains):
                pts = o['pts']
                if cj == ci:
                    cut = min(len(pts) // 2, 40)
                    pts = pts[cut:] if side == 0 else pts[:-cut]
                if len(pts) == 0:
                    continue
                d = np.hypot(*(pts - tip).T)
                if d.min() < bd:
                    bd, best = d.min(), pts[d.argmin()]
            if best is not None and bd < merge * 2:
                c['pts'] = np.vstack([best, c['pts']]) if side == 0 else np.vstack([c['pts'], best])
    for d in dots:
        chains.append(dict(pts=np.float64([d]), ends=[True, True], dot=True))
    return chains


def lettering(text, font, size, origin, tilt=0.0, smooth=3.0):
    """Centre lines of one line of text (script or sans: the glyphs are thinned to one stroke). size and origin (left
    end of the baseline) in plane units, tilt in degrees about `origin` (+ = climbing to the right). font = [path,
    weight]. Returns chains with pts in plane units."""
    R = TRACE_RS
    f = load_font(font, int(round(size * R)))
    pad = int(size * R * 0.6)
    l, t, r, b = f.getbbox(text, anchor='ls')
    W, H = r - l + 2 * pad, b - t + 2 * pad
    im = Image.new('L', (W, H), 0)
    ox, oy = pad - l, pad - t
    ImageDraw.Draw(im).text((ox, oy), text, font=f, fill=255, anchor='ls')
    a = cv2.GaussianBlur(np.asarray(im), (0, 0), 1.5) > 127
    chains = trace(thin(a), spur=0.075 * size * R, merge=0.05 * size * R, smooth=smooth * R)
    th = np.radians(-tilt)
    rot = np.float64([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    for c in chains:
        p = (c['pts'] - (ox, oy)) / R
        c['pts'] = p @ rot.T + origin
    return chains


def stroke(points, n=160):
    """A hand-set stroke (an underline, an arrow shaft) as one chain: Catmull-Rom through `points` (plane units)."""
    p = np.float64(points)
    p = np.vstack([p[0] * 2 - p[1], p, p[-1] * 2 - p[-2]])
    pts = []
    for i in range(1, len(p) - 2):
        for t in np.linspace(0, 1, n // (len(p) - 3), endpoint=False):
            a, b, c, d = p[i - 1], p[i], p[i + 1], p[i + 2]
            pts.append(0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t
                              + (-a + 3 * b - 3 * c + d) * t ** 3))
    pts.append(p[-2])
    return [dict(pts=np.float64(pts), ends=[True, True])]


def chain_length(c):
    return float(np.hypot(*np.diff(c['pts'], axis=0).T).sum()) if len(c['pts']) > 1 else 0.0


def sample_points(chains, spacing):
    """Points every `spacing` units along the chains (light samples, standoff candidates)."""
    out = []
    for c in chains:
        p = c['pts']
        if len(p) < 2:
            out.append(p[0])
            continue
        s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
        n = max(int(s[-1] / spacing), 1)
        t = (np.arange(n) + 0.5) * s[-1] / n
        out += list(np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], 1))
    return np.float64(out)


# ---------------------------------------------------------------------------------------------------------------------
# the glass: everything static about the sign, drawn flat in plane space
# ---------------------------------------------------------------------------------------------------------------------
def _draw(chains, extent, rs, trim=0.0, skip_dots=False):
    """Centre lines as a 1 px mask on the art canvas. trim: units cut off every free end."""
    x0, y0, x1, y1 = extent
    m = np.zeros((int((y1 - y0) * rs), int((x1 - x0) * rs)), np.uint8)
    for c in chains:
        p = c['pts']
        if c.get('dot') or len(p) < 2:
            if not skip_dots:
                q = (p.mean(0) - (x0, y0)) * rs
                cv2.circle(m, (int(round(q[0])), int(round(q[1]))), 1, 255, -1)
            continue
        s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
        if trim and s[-1] > trim * 4:        # beads (i dots, full stops) are too short for sleeves: lit end to end
            lo = trim if c['ends'][0] else 0.0
            hi = s[-1] - (trim if c['ends'][1] else 0.0)
            t = np.linspace(lo, hi, max(int((hi - lo) * 2), 2))
            p = np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], 1)
        q = np.round((p - (x0, y0)) * rs * 8).astype(np.int32)
        cv2.polylines(m, [q], False, 255, 1, cv2.LINE_8, shift=3)
    return m


def _dist(mask, rs):
    return cv2.distanceTransform(255 - mask, cv2.DIST_L2, 5) / rs


class Tube:
    """Static art for a set of tube groups (each group strikes on its own). Maps live on a canvas covering `extent`
    (plane units) at `rs` px per unit:
        gain   multiply the plate by this: unlit glass shading, electrode sleeves, standoffs, cable, soft shadows
        spec   add this (x room exposure): the window highlight along the top of the glass
        cover  glass coverage of all groups
        emit   one channel per group: 0..0.5 = lit glass coverage, 0.5..1 = how deep into the hot core
        phase  0..1 left to right across each group (drives partial ignition while it strikes)
    """

    def __init__(self, groups, extent, rs=3, diameter=8.0, electrode=5.0, standoff_every=85.0, cable=None,
                 light=(-0.30, -0.72, 0.62), soften=0.6):
        self.extent, self.rs, self.groups = extent, rs, groups
        r = diameter / 2.0
        x0, y0, x1, y1 = extent
        H, W = int((y1 - y0) * rs), int((x1 - x0) * rs)
        aa = 1.0 / rs
        cover = np.zeros((H, W), np.float32)
        d_all = np.full((H, W), 1e3, np.float32)
        sleeve = np.zeros((H, W), np.float32)
        emit = np.zeros((H, W, len(groups)), np.float32)
        phase = np.zeros((H, W), np.float32)
        gx = (np.arange(W, dtype=np.float32) / rs + x0)[None, :]
        for gi, g in enumerate(groups):
            d = _dist(_draw(g['chains'], extent, rs), rs)
            a = np.clip((r - d) / aa + 0.5, 0, 1)
            d_lit = _dist(_draw(g['chains'], extent, rs, trim=electrode), rs)
            lit = np.clip((r - d_lit) / aa + 0.5, 0, 1) * a
            u = np.clip(1 - d_lit / r, 0, 1)
            core = sstep((u - 0.30) / 0.42)
            emit[..., gi] = lit * (0.5 + 0.5 * core)
            sleeve = np.maximum(sleeve, a * (1 - np.clip((r + 0.6 - d_lit) / aa, 0, 1)))
            near = d < d_all
            d_all = np.where(near, d, d_all)
            cover = np.maximum(cover, a)
            allp = np.vstack([c['pts'] for c in g['chains']])
            lo, hi = allp[:, 0].min(), allp[:, 0].max()
            phase = np.where(a > 0, np.clip((gx - lo) / max(hi - lo, 1), 0, 1), phase)
        # round glass: normal from the distance field
        ds = cv2.GaussianBlur(d_all, (0, 0), 0.5 * rs / 3 + 0.4)
        nx, ny = cv2.Sobel(ds, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(ds, cv2.CV_32F, 0, 1, ksize=3)
        nrm = np.sqrt(nx * nx + ny * ny) + 1e-6
        k = np.clip(d_all / r, 0, 1)
        n3 = np.stack([nx / nrm * k, ny / nrm * k, np.sqrt(np.clip(1 - k * k, 0, 1))], -1)
        L = np.float32(light) / np.linalg.norm(light)
        ndl = np.clip(n3 @ L, 0, 1)
        Hv = (L + np.float32([0, 0, 1]))
        Hv /= np.linalg.norm(Hv)
        spec = np.clip(n3 @ Hv, 0, 1) ** 70 * cover
        # milky unlit glass: a shade darker than the plaster, darker underneath, a dark refraction line at the rim
        body = (0.58 + 0.36 * ndl) * (1 - 0.20 * k ** 6)
        body = body * (1 - sleeve) + 0.30 * (0.7 + 0.5 * ndl) * sleeve          # electrode sleeves: dark rubber boots
        # standoffs: a small clear base behind the tube and a wire tie across it
        base = np.zeros((H, W), np.float32)
        tie = np.zeros((H, W), np.float32)
        self.standoffs = []
        for g in groups:
            for c in g['chains']:
                p = c['pts']
                if c.get('dot') or len(p) < 2:
                    continue
                s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
                n = max(int(round(s[-1] / standoff_every)), 1 if s[-1] > 45 else 0)
                for j in range(n):
                    t = (j + 0.5) * s[-1] / n
                    i = int(np.searchsorted(s, t))
                    i = min(max(i, 1), len(p) - 2)
                    c0 = p[i]
                    tg = p[i + 1] - p[i - 1]
                    tg /= np.linalg.norm(tg) + 1e-9
                    nn = np.float64([-tg[1], tg[0]])
                    self.standoffs.append(c0)
                    q = (c0 - (x0, y0)) * rs
                    cv2.circle(base, (int(round(q[0] * 8)), int(round(q[1] * 8))), int(round((r + 1.7) * rs * 8)), 1.0,
                               -1, cv2.LINE_AA, shift=3)
                    a_, b_ = (c0 - nn * (r + 0.4) - (x0, y0)) * rs, (c0 + nn * (r + 0.4) - (x0, y0)) * rs
                    cv2.line(tie, (int(round(a_[0] * 8)), int(round(a_[1] * 8))),
                             (int(round(b_[0] * 8)), int(round(b_[1] * 8))), 1.0, max(int(round(1.0 * rs)), 1),
                             cv2.LINE_AA, shift=3)
        base = cv2.GaussianBlur(base, (0, 0), 0.25 * rs)
        tie = cv2.GaussianBlur(tie, (0, 0), 0.2 * rs) * cover
        # cable
        cab = np.zeros((H, W), np.float32)
        if cable is not None:
            cp = stroke(cable)[0]['pts']
            q = np.round((cp - (x0, y0)) * rs * 8).astype(np.int32)
            cv2.polylines(cab, [q], False, 1.0, max(int(round(1.5 * rs)), 1), cv2.LINE_AA, shift=3)
            cab = cv2.GaussianBlur(cab, (0, 0), 0.2 * rs)

        def shadow(m, dx, dy, sig, amt):
            M = np.float32([[1, 0, dx * rs], [0, 1, dy * rs]])
            return cv2.GaussianBlur(cv2.warpAffine(m, M, (W, H)), (0, 0), sig * rs) * amt
        on_wall = np.maximum(np.maximum(cover, base * 0.9), cab)
        sh = shadow(cover, 2.2, 5.0, 3.0, 0.17) + shadow(on_wall, 0.8, 1.9, 1.1, 0.16)
        wall = (1 - np.clip(sh, 0, 0.6))
        wall = wall * (1 - cab) + 0.74 * cab                            # white flex, a little greyer than the wall
        rim = np.clip(base - cv2.erode(base, np.ones((3, 3), np.uint8), iterations=max(rs // 2, 1)), 0, 1)
        wall = wall * (1 - base) + (0.90 - 0.16 * rim) * base           # clear acrylic foot
        gain = wall * (1 - cover) + body * (1 - 0.45 * tie) * cover
        blur = soften * rs
        self.gain = cv2.GaussianBlur(gain, (0, 0), blur)
        self.spec = cv2.GaussianBlur(spec * (1 - sleeve) * (1 - tie), (0, 0), blur)
        self.cover = cv2.GaussianBlur(cover, (0, 0), blur)
        self.emit = cv2.GaussianBlur(emit * (1 - 0.40 * tie)[..., None], (0, 0), blur)
        self.phase = phase
        self.sleeve = sleeve

    def layers(self):
        """Two 4-channel float images ready for warpPerspective."""
        a = np.dstack([self.gain, self.spec, self.cover, self.phase]).astype(np.float32)
        e = self.emit
        if e.shape[2] < 4:
            e = np.dstack([e, np.zeros(e.shape[:2] + (4 - e.shape[2],), np.float32)])
        return a, e.astype(np.float32)

    def to_units(self):
        """3x3: art canvas pixel -> plane units."""
        x0, y0 = self.extent[:2]
        return np.float64([[1 / self.rs, 0, x0], [0, 1 / self.rs, y0], [0, 0, 1]])


# ---------------------------------------------------------------------------------------------------------------------
# the light the tube throws on the wall
# ---------------------------------------------------------------------------------------------------------------------
def spill(points, extent, res, height, occluders=(), fill=0.05, fill_radius=320.0, wide=None):
    """Irradiance on the wall plane from an emitter sampled at `points` (plane units), `height` units off the wall.
    A wall point at distance d from a tube point receives height / (d^2 + height^2)^1.5 (inverse square times the
    cosine at the wall). occluders: [(mask on this canvas, height off the wall)]: anything proud of the wall throws a
    soft shadow away from the tube (soft because the tube is long: one hard shadow per sample, summed).
    Returns (lit, unshadowed), both normalised so the unshadowed map peaks at 1."""
    x0, y0, x1, y1 = extent
    W, H = int((x1 - x0) / res), int((y1 - y0) / res)
    X = (np.arange(W, dtype=np.float32) + 0.5) * res + x0
    Y = (np.arange(H, dtype=np.float32) + 0.5) * res + y0
    S = np.zeros((H, W), np.float32)
    S0 = np.zeros((H, W), np.float32)
    maxr = float(np.hypot(W, H))
    nr, na = 512, 720
    h2 = height * height
    for q in points:
        d2 = (X[None, :] - q[0]) ** 2 + (Y[:, None] - q[1]) ** 2
        k = (h2 / (d2 + h2)) ** 1.5
        if wide is not None:        # (height, weight): light off the glass that reaches the wall at a shallow angle
            k += wide[1] * (wide[0] ** 2 / (d2 + wide[0] ** 2)) ** 1.5
        vis = np.ones((H, W), np.float32)
        c = ((q[0] - x0) / res - 0.5, (q[1] - y0) / res - 0.5)
        for mask, oh in occluders:
            flags = cv2.INTER_LINEAR | (cv2.WARP_POLAR_LINEAR if oh >= height else cv2.WARP_POLAR_LOG)
            pol = cv2.warpPolar(mask, (nr, na), c, maxr, flags)
            if oh >= height:
                shp = np.maximum.accumulate(pol, axis=1)
            else:
                # a low object shadows from its far edge out to 1 / (1 - oh / height) times that distance
                n = int(np.ceil(np.log(1.0 / (1.0 - oh / height)) / (np.log(maxr) / nr)))
                ker = np.ones((1, n + 1), np.uint8)
                shp = cv2.dilate(pol, ker, anchor=(n, 0))
            sh = cv2.warpPolar(shp, (W, H), c, maxr, flags | cv2.WARP_INVERSE_MAP)
            vis *= 1 - np.clip(sh, 0, 1)
        S += k * vis
        S0 += k
    cen = np.mean(points, 0)
    wide = fill / (1 + ((X[None, :] - cen[0]) ** 2 + (Y[:, None] - cen[1]) ** 2) / fill_radius ** 2)
    peak = S0.max()
    return S / peak + wide, S0 / peak + wide
