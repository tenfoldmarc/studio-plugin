"""The sticker kit: small pieces placed anywhere on a slide (iPhone UI bits, paper and scrapbook bits, hand-drawn
marks). render.py calls render(sticker, ctx) for every entry of a slide's "stickers" list and puts the result in a
front layer (over the text) or a back layer ("z": "back", under the text).

Every sticker takes: type, x, y (% of the slide, the sticker's top-left corner, or its centre with
"anchor": "center"), w (width px), size (base type size px), rotate (deg), scale, flip, opacity, color,
z ("front" / "back"), class, style (extra inline CSS). references/stickers.md lists every type and its fields.

The look restyles stickers through the --st-* custom properties in stickers.css (paper, ink, accent, faces, radius).
"""
import html
import json
import math
import random
import re
import urllib.parse


# ------------------------------------------------------------------ small helpers
def _md(text):
    import render   # lazily: render imports this module
    return render.md(text)


def _src(src, ctx):
    import render
    return render.img_src(src, ctx.get('project') or '.')


def esc(s):
    return html.escape(str(s), quote=True)


def num(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fmt(v):
    return f'{v:.1f}'.rstrip('0').rstrip('.') if isinstance(v, float) else str(v)


SAFE_CSS = re.compile(r'^[#\w\s.,%()+\-/\'"]*$')


def css_value(v):
    """A colour or length the buyer wrote, kept only when it cannot break out of the style attribute."""
    s = str(v).strip()
    return s if s and SAFE_CSS.match(s) and ';' not in s and '{' not in s else ''


COLORS = {
    'yellow': '#FFE45C', 'lemon': '#FFF07A', 'pink': '#F9B8CB', 'rose': '#F28BA8', 'hotpink': '#FF4F9A',
    'blue': '#0A84FF', 'sky': '#A9D3FF', 'babyblue': '#BFD9F2', 'green': '#34C759', 'mint': '#BDE8D2',
    'sage': '#B9C7A5', 'red': '#FF3B30', 'orange': '#FF9F0A', 'peach': '#FFC9A8', 'purple': '#AF52DE',
    'lilac': '#D3C1F2', 'white': '#FFFFFF', 'black': '#111111', 'cream': '#F6F0E1', 'ivory': '#FBF7EC',
    'kraft': '#C9A57A', 'grey': '#8E8E93', 'gray': '#8E8E93', 'gold': '#C9A24A', 'silver': '#BFC3C9',
    'brown': '#7A5636', 'navy': '#1F2D4F', 'teal': '#2AA59A',
}


def color(v, default=''):
    if v is None or v == '':
        return default
    s = str(v).strip()
    return COLORS.get(s.lower().replace(' ', '').replace('-', ''), css_value(s) or default)


FONTS = {'hand': 'var(--st-hand-font)', 'script': 'var(--st-script-font)', 'marker': 'var(--st-marker-font)',
         'pen': 'var(--st-pen-font)', 'type': 'var(--st-type-font)', 'typewriter': 'var(--st-type-font)',
         'serif': 'var(--st-serif-font)', 'ui': 'var(--st-ui-font)', 'head': 'var(--font-head, var(--st-ui-font))',
         'body': 'var(--font-body, var(--st-ui-font))', 'mono': 'var(--font-mono, monospace)'}


def font(v, default='hand'):
    return FONTS.get(str(v or default).lower(), FONTS.get(default, 'var(--st-hand-font)'))


def rng_for(st):
    seed = st.get('seed')
    if seed is None:
        seed = json.dumps({k: v for k, v in st.items() if k not in ('x', 'y', 'z', 'rotate', 'scale')},
                          sort_keys=True, default=str)
    return random.Random(str(seed))


def lines_of(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [x for x in str(v).split('\n')]


# ------------------------------------------------------------------ icons (generic shapes, 24x24, drawn here)
STROKE = {
    'search': '<circle cx="10.6" cy="10.6" r="6.6"/><path d="M15.6 15.6 21 21"/>',
    'mic': '<rect x="9" y="2.8" width="6" height="11.4" rx="3"/><path d="M5.6 11.4a6.4 6.4 0 0 0 12.8 0M12 17.9v3.3"/>',
    'up': '<path d="M12 19.5V5M5.8 11.2 12 5l6.2 6.2"/>',
    'right': '<path d="M4.5 12h15M13.2 5.7 19.5 12l-6.3 6.3"/>',
    'left': '<path d="M19.5 12h-15M10.8 5.7 4.5 12l6.3 6.3"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'chevron': '<path d="M15 4.5 7.5 12l7.5 7.5"/>',
    'chevron-right': '<path d="m9 4.5 7.5 7.5L9 19.5"/>',
    'share': '<path d="M12 3.2v11.6M7.6 7.4 12 3l4.4 4.4M8.4 10.2H6.6a1.6 1.6 0 0 0-1.6 1.6v7.6A1.6 1.6 0 0 0 6.6 21h10.8a1.6 1.6 0 0 0 1.6-1.6v-7.6a1.6 1.6 0 0 0-1.6-1.6h-1.8"/>',
    'more': '<circle cx="12" cy="12" r="9.4"/><circle cx="7.6" cy="12" r=".6" fill="currentColor"/><circle cx="12" cy="12" r=".6" fill="currentColor"/><circle cx="16.4" cy="12" r=".6" fill="currentColor"/>',
    'save': '<path d="M12 3.4v11.2M7.6 10.4 12 14.8l4.4-4.4M4.6 15.4v3.4a1.8 1.8 0 0 0 1.8 1.8h11.2a1.8 1.8 0 0 0 1.8-1.8v-3.4"/>',
    'copy': '<rect x="8.6" y="8.6" width="12" height="12" rx="2.4"/><path d="M15.4 8.6V5.8a2.4 2.4 0 0 0-2.4-2.4H5.8a2.4 2.4 0 0 0-2.4 2.4V13a2.4 2.4 0 0 0 2.4 2.4h2.8"/>',
    'trash': '<path d="M3.8 6.4h16.4M9.4 6.4V4.2h5.2v2.2M6.2 6.4l1 13.2a1.6 1.6 0 0 0 1.6 1.5h6.4a1.6 1.6 0 0 0 1.6-1.5l1-13.2M10 10.4v7M14 10.4v7"/>',
    'edit': '<path d="M4 20l1.1-4.6L16 4.5a2.1 2.1 0 0 1 3 3L8.1 18.4zM14.2 6.3l3.5 3.5"/>',
    'reply': '<path d="M9.6 5 3.6 11l6 6M3.6 11h10a7 7 0 0 1 7 7v1"/>',
    'forward': '<path d="m14.4 5 6 6-6 6M20.4 11h-10a7 7 0 0 0-7 7v1"/>',
    'heart': '<path d="M12 20.4s-7.6-4.6-9.3-9.6C1.6 7.4 3.8 3.9 7.3 3.9c2 0 3.6 1.1 4.7 2.8 1.1-1.7 2.7-2.8 4.7-2.8 3.5 0 5.7 3.5 4.6 6.9-1.7 5-9.3 9.6-9.3 9.6z"/>',
    'comment': '<path d="M20.6 11.6a8.5 8.5 0 0 1-12.5 7.5L3.4 20.6l1.6-4.5A8.5 8.5 0 1 1 20.6 11.6z"/>',
    'send': '<path d="M21.4 3 10.3 13.7M21.4 3l-6.7 18-4.4-7.3L2.6 9.6z"/>',
    'bookmark': '<path d="M6 3.4h12v17.4l-6-4.6-6 4.6z"/>',
    'home': '<path d="M3.6 10.4 12 3.4l8.4 7V20a1 1 0 0 1-1 1h-4.8v-6.2H9.4V21H4.6a1 1 0 0 1-1-1z"/>',
    'add': '<rect x="3.4" y="3.4" width="17.2" height="17.2" rx="5"/><path d="M12 8v8M8 12h8"/>',
    'play-square': '<rect x="3.4" y="3.4" width="17.2" height="17.2" rx="5"/><path d="M10 8.6v6.8l5.6-3.4z" fill="currentColor"/>',
    'pin-tack': '<path d="M9 3.6h6M10 3.6l-.6 6.2-3 3.2h11.2l-3-3.2-.6-6.2M12 13v7.4"/>',
    'link': '<path d="M10 14a4.2 4.2 0 0 0 6 0l3-3a4.2 4.2 0 0 0-6-6l-1 1M14 10a4.2 4.2 0 0 0-6 0l-3 3a4.2 4.2 0 0 0 6 6l1-1"/>',
    'star': '<path d="m12 3.2 2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 17l-5.4 2.9 1.1-6.1-4.5-4.2 6.1-.8z"/>',
    'sun': '<circle cx="12" cy="12" r="3.6"/><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4l1.5 1.5M17.1 17.1l1.5 1.5M5.4 18.6l1.5-1.5M17.1 6.9l1.5-1.5"/>',
    'check': '<path d="m5 12.6 4.4 4.4L19 7.4"/>',
    'lock': '<rect x="5" y="10.6" width="14" height="10" rx="2.2"/><path d="M8.2 10.6V7.8a3.8 3.8 0 0 1 7.6 0v2.8"/>',
    'flag': '<path d="M5 21V4.2M5 4.6c4.6-2.2 9.4 2.2 14 0v9c-4.6 2.2-9.4-2.2-14 0"/>',
    'calendar': '<rect x="3.6" y="5" width="16.8" height="15.6" rx="2.6"/><path d="M3.6 9.8h16.8M8 3.2v3.6M16 3.2v3.6"/>',
    'thumb': '<path d="M7.2 10.4v10H4.6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1zM7.2 10.4l3.9-7.2c1.4 0 2.6 1.2 2.3 2.7l-.6 3.4h5.6a2 2 0 0 1 2 2.4l-1.4 7.4a2 2 0 0 1-2 1.7H7.2"/>',
    'music': '<path d="M9 18.2V5.4l11-2v12.4"/><circle cx="6.4" cy="18.2" r="2.6"/><circle cx="17.4" cy="15.8" r="2.6"/>',
}
FILLED = {
    'pin': '<path d="M12 1.8c-4.1 0-7.4 3.2-7.4 7.3 0 5.3 6.2 11.9 6.8 12.5.3.3.9.3 1.2 0 .6-.6 6.8-7.2 6.8-12.5 0-4.1-3.3-7.3-7.4-7.3zm0 10.2a2.9 2.9 0 1 1 0-5.8 2.9 2.9 0 0 1 0 5.8z"/>',
    'heart': '<path d="M12 21.2c-.4-.2-10.2-6-10.2-13 0-3.3 2.5-5.8 5.6-5.8 2 0 3.7 1 4.6 2.6.9-1.6 2.6-2.6 4.6-2.6 3.1 0 5.6 2.5 5.6 5.8 0 7-9.8 12.8-10.2 13z"/>',
    'sparkle': '<path d="M12 .8c.6 5.8 4.6 9.8 10.4 10.4.4 0 .4.6 0 .7-5.8.6-9.8 4.6-10.4 10.4 0 .4-.6.4-.7 0-.6-5.8-4.6-9.8-10.4-10.4-.4 0-.4-.6 0-.7C6.7 10.6 10.7 6.6 11.3.8c0-.4.6-.4.7 0z"/>',
    'play': '<path d="M7 4.6v14.8c0 .8.9 1.3 1.6.9l12-7.4c.6-.4.6-1.4 0-1.8l-12-7.4C7.9 3.3 7 3.8 7 4.6z"/>',
    'pause': '<rect x="5.6" y="4" width="4.4" height="16" rx="1.2"/><rect x="14" y="4" width="4.4" height="16" rx="1.2"/>',
    'prev': '<path d="M11.4 6.2v11.6c0 .7-.8 1.1-1.4.7L2.8 12.8a1 1 0 0 1 0-1.6L10 5.5c.6-.4 1.4 0 1.4.7zM21.4 6.2v11.6c0 .7-.8 1.1-1.4.7l-7.2-5.7a1 1 0 0 1 0-1.6L20 5.5c.6-.4 1.4 0 1.4.7z"/>',
    'next': '<path d="M12.6 6.2v11.6c0 .7.8 1.1 1.4.7l7.2-5.7a1 1 0 0 0 0-1.6L14 5.5c-.6-.4-1.4 0-1.4.7zM2.6 6.2v11.6c0 .7.8 1.1 1.4.7l7.2-5.7a1 1 0 0 0 0-1.6L4 5.5c-.6-.4-1.4 0-1.4.7z"/>',
    'bubble': '<path d="M12 3.2c-5.3 0-9.6 3.6-9.6 8 0 2.5 1.4 4.8 3.6 6.2-.2 1.3-.9 2.6-2 3.4 2.2.1 4.2-.7 5.5-1.8.8.2 1.6.3 2.5.3 5.3 0 9.6-3.6 9.6-8.1S17.3 3.2 12 3.2z"/>',
    'mail': '<path d="M3.4 6.2A2 2 0 0 1 5.2 5h13.6a2 2 0 0 1 1.8 1.2L12 12.4z"/><path d="M3 8.2v9.6A1.4 1.4 0 0 0 4.4 19.2h15.2a1.4 1.4 0 0 0 1.4-1.4V8.2l-8.4 6a1 1 0 0 1-1.2 0z"/>',
    'bell': '<path d="M12 2.6a1.5 1.5 0 0 1 1.5 1.5v.5a6.4 6.4 0 0 1 4.9 6.2v4.4l1.9 2.4a.8.8 0 0 1-.6 1.3H4.3a.8.8 0 0 1-.6-1.3l1.9-2.4v-4.4a6.4 6.4 0 0 1 4.9-6.2v-.5A1.5 1.5 0 0 1 12 2.6zM9.6 20h4.8a2.4 2.4 0 0 1-4.8 0z"/>',
    'cash': '<path d="M12.9 3v1.6c2 .3 3.4 1.5 3.6 3.3h-2.3c-.2-.9-1-1.4-2.2-1.4-1.4 0-2.2.6-2.2 1.5 0 .8.6 1.2 2.2 1.6l1.3.3c2.5.6 3.6 1.7 3.6 3.6 0 2-1.5 3.4-4 3.7V19h-1.7v-1.8c-2.3-.3-3.8-1.6-3.9-3.6h2.4c.2 1 1.1 1.6 2.5 1.6 1.4 0 2.3-.6 2.3-1.6 0-.8-.6-1.3-2.1-1.6l-1.5-.3c-2.3-.5-3.4-1.6-3.4-3.4 0-1.9 1.4-3.3 3.7-3.6V3z"/>',
    'cursor': '<path d="M5.2 2.6v16.6c0 .5.6.8 1 .4l3.9-3.9 2.6 6.1c.1.3.5.4.8.3l2.3-1c.3-.1.4-.5.3-.8l-2.6-6h5.6c.5 0 .8-.6.4-1L6.2 2.2c-.4-.4-1-.1-1 .4z"/>',
    'camera': '<path d="M9.2 4.4h5.6l1.4 2.2h2.8A2.2 2.2 0 0 1 21.2 8.8v9.4a2.2 2.2 0 0 1-2.2 2.2H5a2.2 2.2 0 0 1-2.2-2.2V8.8A2.2 2.2 0 0 1 5 6.6h2.8zM12 17.6a4.2 4.2 0 1 0 0-8.4 4.2 4.2 0 0 0 0 8.4z"/>',
    'note': '<path d="M9 18.2V5.4l11-2v12.4h-.1a2.6 2.6 0 1 1-1.9-2.5V7.6l-7 1.3v9.3a2.6 2.6 0 1 1-2-2.5z"/>',
    'star': '<path d="M12 2.4c.4 0 .7.2.9.6l2.5 5.2 5.6.8c.8.1 1.1 1.1.5 1.7l-4.1 4 1 5.7c.1.8-.7 1.4-1.4 1L12 18.7l-5 2.7c-.7.4-1.5-.2-1.4-1l1-5.7-4.1-4c-.6-.6-.3-1.6.5-1.7l5.6-.8 2.5-5.2c.2-.4.5-.6.9-.6z"/>',
}


def icon(name, cls='', fill=False):
    if fill or (name in FILLED and name not in STROKE):
        body = FILLED.get(name) or FILLED['sparkle']
        return f'<svg class="s-ic {cls}" viewBox="0 0 24 24" fill="currentColor">{body}</svg>'
    body = STROKE.get(name) or STROKE['more']
    return (f'<svg class="s-ic {cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


# ------------------------------------------------------------------ hand-drawn geometry
def smooth(pts, closed=False):
    """Catmull-Rom through the points -> one smooth SVG path."""
    n = len(pts)
    if n < 2:
        return ''
    d = [f'M{pts[0][0]:.1f},{pts[0][1]:.1f}']
    for i in range(n if closed else n - 1):
        p0 = pts[(i - 1) % n] if (closed or i > 0) else pts[i]
        p1, p2 = pts[i], pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if (closed or i + 2 < n) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f'C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}')
    return ' '.join(d) + (' Z' if closed else '')


def ribbon(pts, width, start=0.35, end=0.12, ramp=0.10, fade=0.30):
    """A pen stroke as a filled shape: thin where the pen lands, full in the middle, tapering where it lifts."""
    n = len(pts)
    if n < 2:
        return ''
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        t = i / (n - 1)
        k = min(1.0, t / ramp) if ramp else 1.0
        k2 = min(1.0, (1 - t) / fade) if fade else 1.0
        w = width * (min(start + (1 - start) * k, end + (1 - end) * k2)) / 2
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))

    def cap(p, q, w):
        dx, dy = p[0] - q[0], p[1] - q[1]
        ln = math.hypot(dx, dy) or 1
        return (p[0] + dx / ln * w, p[1] + dy / ln * w)
    c0 = cap(pts[0], pts[1], width * start * 0.45)
    c1 = cap(pts[-1], pts[-2], width * end * 0.45)
    return smooth([c0] + left + [c1] + right[::-1], closed=True)


def rotate_pts(pts, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(x * c - y * s, x * s + y * c) for x, y in pts]


def svg_of(strokes, pad, stroke_w, brush, extra_cls=''):
    """strokes: list of point lists -> an <svg> sized to their bounding box (so x/y place what you see)."""
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    mx, my = min(xs) - pad, min(ys) - pad
    w, h = max(xs) + pad - mx, max(ys) + pad - my
    paths = []
    for s in strokes:
        s = [(x - mx, y - my) for x, y in s]
        if brush == 'marker':
            paths.append(f'<path d="{smooth(s)}" fill="none" stroke="currentColor" stroke-width="{stroke_w:.1f}" '
                         f'stroke-linecap="round" stroke-linejoin="round"/>')
        else:
            paths.append(f'<path d="{ribbon(s, stroke_w)}"/>')
    return (f'<svg class="s-mark {extra_cls}" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.1f} {h:.1f}" '
            f'fill="currentColor">' + ''.join(paths) + '</svg>'), w, h


DIRS = {'right': 0, 'down-right': 45, 'down': 90, 'down-left': 135, 'left': 180, 'up-left': -135, 'up': -90,
        'up-right': -45}


def arrow_strokes(length, bend, style, rng, head):
    pts = []
    N = 70
    if style == 'loop':
        a = length / (2 * math.pi) / 1.0
        b = a * 1.75
        for i in range(N + 1):
            th = math.pi + 2 * math.pi * i / N
            x = a * (th - math.pi) - b * math.sin(th)
            y = b * math.cos(th) + b
            y -= bend * length * 0.35 * math.sin(math.pi * i / N)
            pts.append((x, y))
    elif style == 'zigzag':
        for i in range(N + 1):
            t = i / N
            x = t * length
            y = math.sin(t * math.pi * 3) * length * 0.06 * (1 - t * 0.5)
            pts.append((x, y))
    else:   # a curve
        for i in range(N + 1):
            t = i / N
            x = t * length
            y = -bend * length * 0.42 * 4 * t * (1 - t)
            pts.append((x, y))
    pts = [(x + rng.uniform(-0.4, 0.4), y + rng.uniform(-0.4, 0.4)) for x, y in pts]
    # the head follows the direction the line arrives in
    (x1, y1), (x2, y2) = pts[-4], pts[-1]
    ang = math.atan2(y2 - y1, x2 - x1)
    hl = max(22.0, min(70.0, length * 0.16)) * head
    wings = []
    for side, spread in ((1, 0.52 + rng.uniform(-0.05, 0.05)), (-1, 0.48 + rng.uniform(-0.05, 0.05))):
        a2 = ang + math.pi + side * spread
        tip = (x2 + rng.uniform(-1, 1), y2 + rng.uniform(-1, 1))
        end = (tip[0] + math.cos(a2) * hl, tip[1] + math.sin(a2) * hl)
        mid = ((tip[0] + end[0]) / 2 + side * rng.uniform(0, 1.5), (tip[1] + end[1]) / 2)
        wings.append([end, mid, tip] if side > 0 else [tip, mid, end])
    return [pts] + wings


def ellipse_strokes(w, h, rng, turns=1.13):
    cx, cy = w / 2, h / 2
    rx, ry = w / 2, h / 2
    start = rng.uniform(-2.7, -2.2)
    tilt = rng.uniform(-0.05, 0.05)
    ph = rng.uniform(0, 6.28)
    N = 110
    pts = []
    for i in range(N + 1):
        t = i / N
        a = start - t * turns * 2 * math.pi
        drift = 1.035 - 0.07 * t
        wob = 1 + 0.022 * math.sin(3 * a + ph) + 0.012 * math.sin(5 * a + ph * 2)
        x, y = rx * math.cos(a) * drift * wob, ry * math.sin(a) * drift * wob
        x, y = x * math.cos(tilt) - y * math.sin(tilt), x * math.sin(tilt) + y * math.cos(tilt)
        pts.append((cx + x, cy + y))
    return [pts]


def underline_strokes(w, style, rng):
    N = 80
    if style == 'wave':
        waves = max(3, round(w / 70))
        amp = 9
        return [[(w * i / N, amp * math.sin(i / N * waves * 2 * math.pi) + rng.uniform(-0.6, 0.6)) for i in range(N + 1)]]
    if style == 'scribble':
        turns = max(4, round(w / 55))
        pts = []
        for i in range(turns * 2 + 1):
            x = w * i / (turns * 2) + rng.uniform(-6, 6)
            y = (0 if i % 2 == 0 else 26) + rng.uniform(-3, 3) + i * 0.4
            pts.append((max(0, min(w, x)), y))
        return [pts]
    lift = rng.uniform(10, 18)
    one = [(w * i / N, -lift * (i / N) ** 1.6 + 6 * math.sin(i / N * math.pi) + rng.uniform(-0.3, 0.3)) for i in range(N + 1)]
    if style == 'double':
        two = [(w * 0.08 + w * 0.86 * i / N, 22 - lift * 0.8 * (i / N) ** 1.4 + 4 * math.sin(i / N * math.pi)) for i in range(N + 1)]
        return [one, two]
    return [one]


def heart_pts(size, rng, turns=1.06):
    pts = []
    N = 120
    for i in range(N + 1):
        t = -math.pi * 0.05 + 2 * math.pi * turns * i / N
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        k = 1 + 0.03 * (i / N)
        pts.append((x * size / 34 * k + rng.uniform(-0.5, 0.5), y * size / 34 * k + rng.uniform(-0.5, 0.5)))
    return pts


def star_pts(size, rng, spikes=5, inner=0.46):
    pts = []
    r = size / 2
    for i in range(spikes * 2 + 2):
        a = -math.pi / 2 + i * math.pi / spikes
        rr = r if i % 2 == 0 else r * inner
        pts.append((rr * math.cos(a) + rng.uniform(-r * 0.04, r * 0.04), rr * math.sin(a) + rng.uniform(-r * 0.04, r * 0.04)))
    return pts


# ------------------------------------------------------------------ the wrapper every sticker shares
ANCHORS = {'top-left': (0, 0), 'center': (-50, -50), 'centre': (-50, -50), 'top': (-50, 0), 'bottom': (-50, -100),
           'left': (0, -50), 'right': (-100, -50), 'top-right': (-100, 0), 'bottom-left': (0, -100),
           'bottom-right': (-100, -100)}


def pos(v, default):
    if isinstance(v, str) and re.fullmatch(r'-?\d+(\.\d+)?(px|%)', v.strip()):
        return v.strip()
    return f'{fmt(num(v, default))}%'


def place(st, kind, inner, cls='', css='', size=None, width=None):
    ax, ay = ANCHORS.get(str(st.get('anchor', 'top-left')).lower(), (0, 0))
    tf = []
    if ax or ay:
        tf.append(f'translate({ax}%,{ay}%)')
    if st.get('rotate'):
        tf.append(f'rotate({fmt(num(st["rotate"], 0))}deg)')
    sc = num(st.get('scale'), 1)
    if st.get('flip'):
        tf.append(f'scale({-sc:g},{sc:g})')
    elif sc != 1:
        tf.append(f'scale({sc:g})')
    style = f'left:{pos(st.get("x"), 10)};top:{pos(st.get("y"), 10)};'
    w = st.get('w', width)
    if w is not None and w != 'auto':
        style += f'width:{fmt(num(w, 300))}px;'
    sz = st.get('size', size)
    if sz is not None:
        style += f'font-size:{fmt(num(sz, 40))}px;'
    if tf:
        style += 'transform:' + ' '.join(tf) + ';'
    if st.get('opacity') is not None:
        style += f'opacity:{num(st["opacity"], 1):g};'
    c = color(st.get('color'))
    if c:
        style += f'--c:{c};'
    style += css
    if st.get('style'):
        style += str(st['style']).replace('"', "'")
    extra = ' '.join(c for c in str(st.get('class', '')).split() if re.fullmatch(r'[\w-]+', c))
    classes = ' '.join(x for x in ('sticker', f'st-{kind}', cls, extra) if x)
    return f'<div class="{classes}" style="{esc(style)}">{inner}</div>'


# ------------------------------------------------------------------ the stickers
def k_location(st, ctx):
    style = st.get('look') or st.get('variant') or 'glass'
    text = _md(st.get('text', 'Paris'))
    return place(st, 'location', f'<span class="s-pinwrap">{icon("pin")}</span><span class="s-tx">{text}</span>',
                 f'v-{style}', size=34)


def k_search(st, ctx):
    v = st.get('variant') or st.get('look') or 'ios'
    text = st.get('text', '')
    ph = st.get('placeholder', 'Search')
    tx = (f'<span class="s-tx">{_md(text)}' + ('<i class="s-caret"></i>' if st.get('cursor', True) else '') + '</span>'
          if text else f'<span class="s-tx s-ph">{_md(ph)}</span>')
    right = ''
    if st.get('button', v == 'google'):
        right = f'<span class="s-go">{icon("up" if v == "ios" else "right")}</span>'
    elif v == 'ios':
        right = f'<span class="s-mic">{icon("mic")}</span>'
    return place(st, 'search', f'<span class="s-mag">{icon("search")}</span>{tx}{right}', f'v-{v}', size=38, width=820)


# the iMessage tail, in 1/40 em: x=0 is the bubble's side, y=40 its bottom; it covers the bubble's rounded corner
TAIL = ('<svg class="s-tail" viewBox="-24 0 38 41" aria-hidden="true">'
        '<path d="M-24 0H0V16C0 28 5 36 13.5 40C4 40.8-6 37.5-14 30.5L-24 30.5Z"/></svg>')


def k_bubble(st, ctx):
    v = st.get('variant') or st.get('look') or ('typing' if st.get('typing') else 'text')
    side = 'left' if str(st.get('side', 'right')).lower() in ('left', 'them', 'in') else 'right'
    tone = str(st.get('tone', 'green' if st.get('sms') else '')).lower()
    if v == 'reply':
        text = st.get('text', '')
        tx = f'<span class="s-tx">{_md(text)}</span>' if text else f'<span class="s-tx s-ph">{_md(st.get("placeholder", "Type your text here"))}</span>'
        return place(st, 'bubble', f'<span class="s-plus">{icon("plus")}</span><span class="s-field">{tx}'
                     f'<span class="s-send">{icon("up")}</span></span>', 'v-reply', size=36, width=820)
    tail = TAIL if st.get('tail', True) else ''
    if v == 'typing':
        inner = ('<span class="s-b s-typing"><i></i><i></i><i></i>'
                 + ('<em class="s-t1"></em><em class="s-t2"></em>' if tail else '') + '</span>')
        return place(st, 'bubble', inner, f'v-typing side-{side}', size=40)
    meta = f'<span class="s-meta">{_md(st["meta"])}</span>' if st.get('meta') else ''
    inner = f'<span class="s-b">{_md(st.get("text", "Hey! Did you see this?"))}{tail}</span>{meta}'
    return place(st, 'bubble', inner, f'side-{side} tone-{tone}' + ('' if tail else ' no-tail'), size=40,
                 css=f'max-width:{fmt(num(st.get("max"), 720))}px;' if not st.get('w') else '')


APP_ICONS = {'message': ('bubble', 'linear-gradient(180deg,#67E36F,#25C03A)'), 'messages': ('bubble', 'linear-gradient(180deg,#67E36F,#25C03A)'),
             'mail': ('mail', 'linear-gradient(180deg,#3FA9FF,#1468F2)'), 'bell': ('bell', 'linear-gradient(180deg,#FF6B6B,#E5383B)'),
             'heart': ('heart', 'linear-gradient(180deg,#FF7AA8,#F0386B)'), 'cash': ('cash', 'linear-gradient(180deg,#4BD96B,#1FA846)'),
             'bank': ('cash', 'linear-gradient(180deg,#3A3A3C,#111)'), 'camera': ('camera', 'linear-gradient(180deg,#9A9AA0,#5E5E63)'),
             'music': ('note', 'linear-gradient(180deg,#FF6A88,#F2294F)'), 'calendar': ('calendar', '#fff'),
             'star': ('star', 'linear-gradient(180deg,#FFD34E,#FFA800)'), 'sparkle': ('sparkle', 'linear-gradient(180deg,#B48CFF,#7B4DFF)')}


def app_icon(st, ctx):
    if st.get('icon_src'):
        return f'<span class="s-app s-img"><img src="{esc(_src(st["icon_src"], ctx))}" alt=""></span>'
    name = str(st.get('icon', 'message')).lower()
    if name == 'calendar':
        return ('<span class="s-app s-cal"><b>' + esc(st.get('day', 'MON')) + '</b><span>' + esc(st.get('date', '14'))
                + '</span></span>')
    if name in APP_ICONS:
        g, bg = APP_ICONS[name]
        if color(st.get('icon_color')):
            bg = color(st.get('icon_color'))
        return f'<span class="s-app" style="background:{bg}">{icon(g, fill=True)}</span>'
    letter = esc(str(st.get('app', 'A')).strip()[:1].upper())
    bg = color(st.get('icon_color'), 'linear-gradient(180deg,#5A5A5E,#2C2C2E)')
    return f'<span class="s-app s-letter" style="background:{bg}">{letter}</span>'


def k_notification(st, ctx):
    v = st.get('variant') or st.get('look') or 'banner'
    dark = ' is-dark' if st.get('dark') else ''
    time = esc(st.get('time', 'now'))
    if v == 'message':
        frm = f'<b class="s-ti">{_md(st["title"])}</b>' if st.get('title') else ''
        return place(st, 'notification',
                     f'<div class="s-hd"><i class="s-dot"></i><b>{_md(st.get("app", "New Message"))}</b><span class="s-tm">{time}</span></div>'
                     f'{frm}<div class="s-txt">{_md(st.get("text", ""))}</div>', 'v-message' + dark, size=36, width=900)
    title = f'<b class="s-ti">{_md(st["title"])}</b>' if st.get('title') else ''
    return place(st, 'notification',
                 f'{app_icon(st, ctx)}<div class="s-main"><div class="s-top">{title or "<b class=ti>" + _md(st.get("app", "Messages")) + "</b>"}'
                 f'<span class="s-tm">{time}</span></div><div class="s-txt">{_md(st.get("text", ""))}</div></div>',
                 'v-banner' + dark, size=36, width=920)


def k_notes(st, ctx):
    rows = ''
    for x in st.get('checklist') or []:
        x = x if isinstance(x, dict) else {'text': x}
        t = str(x.get('text', ''))
        done = x.get('done') or t.startswith('[x]')
        t = re.sub(r'^\[[ x]\]\s*', '', t)
        rows += (f'<li class="{"s-done" if done else ""}"><i class="s-ck">{icon("check") if done else ""}</i>'
                 f'<span>{_md(t)}</span></li>')
    date = f'<div class="s-date">{_md(st["date"])}</div>' if st.get('date') else ''
    title = f'<div class="s-ti">{_md(st["title"])}</div>' if st.get('title') else ''
    text = f'<div class="s-txt">{_md(st["text"])}</div>' if st.get('text') else ''
    head = (f'<div class="s-bar"><span class="s-back">{icon("chevron")}<span>{_md(st.get("back", "Notes"))}</span></span>'
            f'<span class="s-acts">{icon("share")}{icon("more")}</span></div>')
    return place(st, 'notes', head + date + title + text + (f'<ul class="s-cl">{rows}</ul>' if rows else ''),
                 'is-dark' if st.get('dark') else '', size=36, width=800)


def k_receipt(st, ctx):
    lines = st.get('lines') or st.get('items') or ['1 good idea', '2 big plans']
    rows = ''
    count = max(int(num(st.get('rows'), 0)), len(lines) + 1)
    for i in range(count):
        x = lines[i] if i < len(lines) else ''
        x = x if isinstance(x, dict) else {'text': x}
        rows += (f'<div class="s-row"><span class="s-q">{_md(x.get("qty", ""))}</span><span class="s-it">{_md(x.get("text", ""))}</span>'
                 f'<span class="s-pr">{_md(x.get("price", ""))}</span></div>')
    total = (f'<div class="s-row s-tot"><span class="s-q"></span><span class="s-lb">Total</span><span class="s-pr">{_md(st["total"])}</span></div>'
             if st.get('total') else '')
    paper = color(st.get('paper'))
    ink = color(st.get('ink'))
    css = (f'--rc-paper:{paper};' if paper else '') + (f'--rc-ink:{ink};' if ink else '')
    no = esc(st.get('number', '0' + str(4200 + rng_for(st).randint(10, 99))))
    return place(st, 'receipt',
                 f'<div class="s-pad"><div class="s-hd"><span class="s-ti">{_md(st.get("title", "Guest Check"))}</span>'
                 f'<span class="s-no">No. <b>{no}</b></span></div>'
                 f'<div class="s-grid"><span><i>Date</i>{_md(st.get("date", ""))}</span><span><i>Table</i>{_md(st.get("table", ""))}</span>'
                 f'<span><i>Guests</i>{_md(st.get("guests", ""))}</span><span><i>Server</i>{_md(st.get("server", ""))}</span></div>'
                 f'<div class="s-rows">{rows}{total}</div>'
                 f'<div class="s-ft">{_md(st.get("footer", "Thank you, come again"))}</div></div>', '', css=css, size=32, width=560)


def k_polaroid(st, ctx):
    src = esc(_src(st.get('src', ''), ctx))
    focus = f' style="object-position:{esc(css_value(st["focus"]))}"' if st.get('focus') else ''
    cap = f'<figcaption style="font-family:{font(st.get("font"), "hand")}">{_md(st.get("caption", ""))}</figcaption>'
    tape = tape_html({'color': st.get('tape_color', 'beige'), 'pattern': st.get('tape_pattern')}, rng_for(st)) if st.get('tape') else ''
    ratio = {'square': '1 / 1', 'portrait': '4 / 5', 'wide': '5 / 4'}.get(str(st.get('ratio', 'square')), '1 / 1')
    return place(st, 'polaroid', f'{tape}<div class="s-ph" style="aspect-ratio:{ratio}"><img src="{src}" alt=""{focus}></div>{cap}',
                 'is-taped' if tape else '', size=round(num(st.get('w'), 440) * 0.105), width=440)


TAPES = {'beige': 'rgba(238,226,198,0.86)', 'kraft': 'rgba(201,165,122,0.92)', 'pink': 'rgba(248,196,210,0.86)',
         'mint': 'rgba(196,232,214,0.86)', 'blue': 'rgba(188,214,242,0.86)', 'yellow': 'rgba(255,233,140,0.86)',
         'lilac': 'rgba(216,200,244,0.86)', 'white': 'rgba(255,255,255,0.62)', 'clear': 'rgba(255,255,255,0.42)',
         'black': 'rgba(30,30,30,0.86)', 'red': 'rgba(222,72,72,0.86)', 'sage': 'rgba(190,204,170,0.88)'}
PATTERNS = {
    'stripes': 'repeating-linear-gradient(-45deg, rgba(255,255,255,0.38) 0 9px, transparent 9px 20px)',
    'dots': 'radial-gradient(circle, rgba(255,255,255,0.6) 3px, transparent 3.6px) 0 0/18px 18px',
    'grid': 'linear-gradient(rgba(255,255,255,0.35) 2px, transparent 2px) 0 0/16px 16px, linear-gradient(90deg, rgba(255,255,255,0.35) 2px, transparent 2px) 0 0/16px 16px',
    'check': 'repeating-conic-gradient(rgba(255,255,255,0.32) 0 25%, transparent 0 50%) 0 0/22px 22px',
    'hearts': 'radial-gradient(circle at 35% 40%, rgba(255,255,255,0.55) 3px, transparent 3.6px) 0 0/26px 22px',
}


def torn_edge(rng, side_pts=9, depth=5.5):
    """A clip-path polygon (in %) with ragged left and right ends, like tape torn off the roll."""
    left = [(rng.uniform(0, depth), 100 * i / side_pts) for i in range(side_pts + 1)]
    right = [(100 - rng.uniform(0, depth), 100 - 100 * i / side_pts) for i in range(side_pts + 1)]
    return 'polygon(' + ','.join(f'{x:.1f}% {y:.1f}%' for x, y in left[::-1] + [(left[0][0], 0)] + right[::-1] + right) + ')'


def tape_html(st, rng):
    c = TAPES.get(str(st.get('color', 'beige')).lower()) or color(st.get('color'), TAPES['beige'])
    pat = PATTERNS.get(str(st.get('pattern') or '').lower(), '')
    bg = (pat + ', ' if pat else '') + f'linear-gradient(180deg, rgba(255,255,255,0.22), rgba(255,255,255,0) 40%, rgba(0,0,0,0.04)), {c}'
    pts = 8
    left = [(rng.uniform(0, 4.5), 100 * i / pts) for i in range(pts + 1)]
    right = [(100 - rng.uniform(0, 4.5), 100 * i / pts) for i in range(pts + 1)]
    poly = 'polygon(' + ','.join(f'{x:.1f}% {y:.1f}%' for x, y in left + right[::-1]) + ')'
    return f'<span class="s-tp" style="background:{bg};clip-path:{poly}"></span>'


def k_tape(st, ctx):
    h = num(st.get('h'), 64)
    return place(st, 'tape', tape_html(st, rng_for(st)), css=f'height:{fmt(h)}px;', width=240)


STICKY = {'yellow': ('#FFF1A6', '#FBE27A'), 'pink': ('#FFD3E0', '#F9B7CB'), 'blue': ('#CFE6FF', '#B3D4F7'),
          'green': ('#D6F2C4', '#BEE5A6'), 'orange': ('#FFD9A8', '#FBC27F'), 'lilac': ('#E6DAFF', '#D3C1F7'),
          'white': ('#FFFFFF', '#F1F0EC'), 'mint': ('#D3F5E6', '#B6EAD3')}


def k_sticky(st, ctx):
    a, b = STICKY.get(str(st.get('color', 'yellow')).lower(), (color(st.get('color'), '#FFF1A6'),) * 2)
    tape = tape_html({'color': st.get('tape_color', 'clear')}, rng_for(st)) if st.get('tape') else ''
    align = 'left' if st.get('align') == 'left' else 'center'
    ink = color(st.get('ink'), '#26231f')
    return place(st, 'sticky', f'{tape}<div class="s-pg"><div class="s-tx" style="text-align:{align};font-family:{font(st.get("font"), "hand")};color:{ink}">'
                 f'{_md(st.get("text", ""))}</div></div>', 'is-taped' if tape else '',
                 css=f'--n1:{a};--n2:{b};', size=round(num(st.get('w'), 400) * 0.125), width=400)


def k_hand(st, ctx):
    ink = color(st.get('color'))
    css = f'font-family:{font(st.get("font"), "hand")};' + (f'color:{ink};' if ink else '')
    if st.get('align'):
        css += f'text-align:{css_value(st["align"])};'
    return place(st, 'hand', _md(st.get('text', 'my advice inside...')), css=css, size=64, width=st.get('w', 'auto'))


def mark(st, strokes, kind, stroke_w, brush):
    s, w, h = svg_of(strokes, stroke_w * 1.2, stroke_w, brush)
    st2 = dict(st)
    st2.pop('w', None)
    return place(st2, kind, s, f'brush-{brush}', width='auto', css='line-height:0;')


def k_circle(st, ctx):
    w = num(st.get('w'), 360)
    h = num(st.get('h'), w * 0.42)
    sw = num(st.get('stroke'), 7)
    return mark(st, ellipse_strokes(w, h, rng_for(st), num(st.get('turns'), 1.13)), 'circle', sw, st.get('brush', 'pen'))


def k_arrow(st, ctx):
    L = num(st.get('w', st.get('length')), 260)
    d = st.get('direction', 'right')
    ang = math.radians(DIRS.get(str(d).lower(), num(d, 0)))
    bend = num(st.get('curve'), 0.45)
    style = st.get('variant') or st.get('look') or 'curve'
    sw = num(st.get('stroke'), 7)
    strokes = arrow_strokes(L, bend, style, rng_for(st), num(st.get('head'), 1))
    strokes = [rotate_pts(s, ang) for s in strokes]
    return mark(st, strokes, 'arrow', sw, st.get('brush', 'pen'))


def k_underline(st, ctx):
    w = num(st.get('w'), 380)
    style = st.get('variant') or st.get('look') or 'swoosh'
    sw = num(st.get('stroke'), 9 if style in ('swoosh', 'double') else 6)
    brush = st.get('brush', 'marker' if style in ('wave', 'scribble') else 'pen')
    return mark(st, underline_strokes(w, style, rng_for(st)), 'underline', sw, brush)


def gloss_svg(shape, c, uid):
    return (f'<svg class="s-glossy" viewBox="0 0 24 24"><defs>'
            f'<radialGradient id="g{uid}" cx="38%" cy="30%" r="80%"><stop offset="0" stop-color="#fff" stop-opacity=".55"/>'
            f'<stop offset=".35" stop-color="{c}" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".28"/></radialGradient>'
            f'</defs><g fill="{c}">{shape}</g><g fill="url(#g{uid})">{shape}</g>'
            f'<ellipse cx="8.4" cy="7.4" rx="2.6" ry="1.5" fill="#fff" opacity=".75" transform="rotate(-35 8.4 7.4)"/></svg>')


def k_icon_shape(st, ctx, kind):
    v = st.get('variant') or st.get('look') or 'flat'
    defaults = {'sparkle': '#FFFFFF', 'star': '#FFD23F', 'heart': '#FF3B5C'}
    c = color(st.get('color'), defaults[kind])
    st = dict(st, color=c)
    w = num(st.get('w'), 84)
    rng = rng_for(st)
    if v in ('outline', 'hand', 'doodle'):
        sw = num(st.get('stroke'), max(4.0, w / 16))
        if kind == 'heart':
            pts = heart_pts(w, rng)
        elif kind == 'star':
            pts = star_pts(w, rng)
            pts = pts + [pts[1]]
        else:   # a sparkle drawn as 4 concave arcs, tip to tip
            r = w / 2
            tips = [(r * math.cos(-math.pi / 2 + q * math.pi / 2), r * math.sin(-math.pi / 2 + q * math.pi / 2)) for q in range(5)]
            pts = []
            for q in range(4):
                (x0, y0), (x2, y2) = tips[q], tips[q + 1]
                am = -math.pi / 4 + q * math.pi / 2
                x1, y1 = r * 0.16 * math.cos(am), r * 0.16 * math.sin(am)
                for i in range(10):
                    t = i / 10
                    x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * x1 + t * t * x2
                    y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t * t * y2
                    pts.append((x + rng.uniform(-0.5, 0.5), y + rng.uniform(-0.5, 0.5)))
            pts += [tips[0], (tips[0][0] + r * 0.06, tips[0][1] + r * 0.12)]
        return mark(st, [pts], kind, sw, 'marker' if kind == 'sparkle' else st.get('brush', 'marker'))
    shape = FILLED[kind]
    count = int(num(st.get('count'), 1))
    if v in ('gloss', 'glossy', '3d'):
        one = gloss_svg(shape, c, abs(hash((kind, c, str(st.get('x')), str(st.get('y'))))) % 10 ** 8)
    else:
        one = f'<svg viewBox="0 0 24 24" fill="currentColor">{shape}</svg>'
    if count > 1:
        inner = (f'<span class="s-s1">{one}</span><span class="s-s2">{one}</span>'
                 + (f'<span class="s-s3">{one}</span>' if count > 2 else ''))
        return place(st, kind, inner, f'is-cluster v-{v}', width=w)
    return place(st, kind, one, f'v-{v}', width=w)


def marker_bg(c, rng):
    """An SVG marker swipe (ragged ends, slightly uneven) as a background image."""
    lean = rng.uniform(0.6, 1.6)
    top = [(rng.uniform(0.4, 1.2), rng.uniform(16, 22))] + [(x, rng.uniform(9, 15)) for x in (12, 30, 50, 70, 88)] \
        + [(rng.uniform(98.6, 99.6), rng.uniform(12, 18))]
    bot = [(100 - lean * rng.uniform(0.2, 0.8), rng.uniform(84, 90))] + [(x, rng.uniform(87, 93)) for x in (82, 62, 40, 20)] \
        + [(lean * rng.uniform(0.6, 1.4), rng.uniform(80, 86))]
    d = 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in top + bot) + 'Z'
    streaks = ''.join(f"<rect x='{rng.uniform(1, 8):.1f}' y='{y:.1f}' width='{rng.uniform(84, 92):.1f}' height='{rng.uniform(5, 9):.1f}' "
                      f"fill='{c}' opacity='{rng.uniform(0.25, 0.45):.2f}'/>" for y in (rng.uniform(14, 22), rng.uniform(70, 78)))
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' preserveAspectRatio='none'>"
           f"<path d='{d}' fill='{c}' opacity='0.86'/>{streaks}</svg>")
    return "url(\"data:image/svg+xml," + urllib.parse.quote(svg, safe=":/=' ,") + "\")"


def k_highlight(st, ctx):
    v = st.get('variant') or st.get('look') or 'marker'
    c = color(st.get('color'), '#FFE45C' if v == 'marker' else '#FFFFFF')
    fnt = font(st.get('font'), 'type' if v == 'strip' else 'ui')
    ink = color(st.get('ink'), '#151515')
    if v == 'strip':
        css = f'--strip:{c};font-family:{fnt};color:{ink};'
        lines = ''.join(f'<span class="s-ln"><span>{_md(x)}</span></span>' for x in lines_of(st.get('text', 'a little note')))
        return place(st, 'highlight', lines, 'v-strip', css=css, size=40, width=st.get('w', 'auto'))
    bg = marker_bg(c, rng_for(st))
    css = f'font-family:{fnt};color:{ink};'
    return place(st, 'highlight', f'<span class="s-hl-tx" style="background-image:{esc(bg)}">{_md(st.get("text", "the part that matters"))}</span>',
                 'v-marker', css=css, size=44, width=st.get('w', 'auto'))


LABEL_ICONS = {'arrow': ('right', False), 'sparkle': ('sparkle', True), 'heart': ('heart', True), 'star': ('star', True),
               'pin': ('pin', True), 'check': ('check', False), 'link': ('link', False), 'lock': ('lock', False),
               'bell': ('bell', True), 'music': ('note', True), 'calendar': ('calendar', False), 'flag': ('flag', False)}


def k_label(st, ctx):
    v = st.get('variant') or st.get('look') or 'solid'
    ic = str(st.get('icon', 'none')).lower()
    lead = st.get('icon_side', 'right') == 'left'
    i_html = ''
    if ic in LABEL_ICONS:
        n, f = LABEL_ICONS[ic]
        i_html = icon(n, fill=f)
    elif ic == 'dot':
        i_html, lead = '<i class="s-dot"></i>', True
    tx = f'<span class="s-tx">{_md(st.get("text", "Swipe"))}</span>'
    inner = (i_html + tx) if lead else (tx + i_html)
    return place(st, 'label', inner, f'v-{v}' + (' is-square' if st.get('shape') == 'square' else ''), size=28)


FOLDERS = {'pink': ('#FFC3D6', '#F59AB8', '#E9799F'), 'blue': ('#9ED3FF', '#5FB2F7', '#3C93E0'),
           'yellow': ('#FFE48A', '#FFCF4D', '#E9B227'), 'green': ('#B8EDB0', '#7DD67A', '#55B856'),
           'purple': ('#E2C8FF', '#C29BFA', '#A274E8'), 'grey': ('#E1E3E8', '#BFC4CC', '#9BA1AB'),
           'black': ('#5A5A60', '#36363B', '#1E1E22'), 'orange': ('#FFD0A0', '#FFAE5C', '#EE8A2E'),
           'red': ('#FFB0AA', '#FF7A70', '#E5544A'), 'beige': ('#F2E3CC', '#E2CBA6', '#CBB088')}


def k_folder(st, ctx):
    c = str(st.get('color', 'pink')).lower()
    if c in FOLDERS:
        hi, mid, lo = FOLDERS[c]
    else:
        mid = color(c, '#F59AB8')
        hi, lo = f'color-mix(in srgb,{mid} 60%,white)', f'color-mix(in srgb,{mid} 82%,black)'
    uid = abs(hash((c, str(st.get('label')), str(st.get('x')), str(st.get('y'))))) % 10 ** 8
    svg = (f'<svg class="s-fd" viewBox="0 0 120 96"><defs>'
           f'<linearGradient id="fb{uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{mid}"/><stop offset="1" stop-color="{lo}"/></linearGradient>'
           f'<linearGradient id="ff{uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{hi}"/><stop offset="1" stop-color="{mid}"/></linearGradient></defs>'
           f'<path d="M6 14a6 6 0 0 1 6-6h28.5a6 6 0 0 1 4.6 2.2l4.3 5.2a6 6 0 0 0 4.6 2.1H108a6 6 0 0 1 6 6V84a6 6 0 0 1-6 6H12a6 6 0 0 1-6-6z" fill="url(#fb{uid})"/>'
           f'<rect x="10" y="22" width="100" height="40" rx="3" fill="#fff" opacity=".92"/>'
           f'<path d="M6 30a6 6 0 0 1 6-6h96a6 6 0 0 1 6 6v54a6 6 0 0 1-6 6H12a6 6 0 0 1-6-6z" fill="url(#ff{uid})"/>'
           f'<path d="M7 31a5 5 0 0 1 5-5h96a5 5 0 0 1 5 5" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.2"/>'
           f'</svg>')
    label = st.get('label', '')
    lab = f'<span class="s-lb{" s-sel" if st.get("selected") else ""}">{_md(label)}</span>' if label else ''
    cur = f'<span class="s-cursor">{icon("cursor", fill=True)}</span>' if st.get('cursor') else ''
    return place(st, 'folder', f'<span class="s-ico">{svg}{cur}</span>{lab}', size=28, width=240)


def corner_svg():
    """A small scroll that sits inside each corner of the double frame (old invitation style)."""
    return ('<svg viewBox="0 0 40 40" class="s-orn" fill="none" stroke="currentColor" stroke-linecap="round">'
            '<path d="M4 34C4 17 17 4 34 4" stroke-width="1.4"/>'
            '<path d="M4 34c0-3.4 2.6-5.2 5-4.2s1.4 4.6-.9 4.2" stroke-width="1.2"/>'
            '<path d="M34 4c-3.4 0-5.2 2.6-4.2 5s4.6 1.4 4.2-.9" stroke-width="1.2"/>'
            '<path d="M11 21c2.5-1 4.4-3 5.4-5.4M21 11c-2.4 1-4.4 2.9-5.4 5.4" stroke-width="1"/>'
            '<path d="M14.6 14.6l1.8-1.8 1.8 1.8-1.8 1.8z" fill="currentColor" stroke="none"/></svg>')


def k_card(st, ctx):
    v = st.get('variant') or st.get('look') or 'simple'
    paper = color(st.get('paper'))
    css = f'--cd-paper:{paper};' if paper else ''
    ink = color(st.get('ink'))
    css += f'--cd-ink:{ink};' if ink else ''
    title = f'<div class="s-ti">{_md(st["title"])}</div>' if st.get('title') else ''
    div = '<div class="s-dv"><i></i><b></b><i></i></div>' if (v == 'invite' and st.get('title') and st.get('text')) else ''
    text = f'<div class="s-txt">{_md(st["text"])}</div>' if st.get('text') else ''
    sign = f'<div class="s-sg">{_md(st["sign"])}</div>' if st.get('sign') else ''
    body = f'<div class="s-in">{title}{div}{text}{sign}</div>'
    if v == 'invite':
        body = (f'<div class="s-frame"></div>' + ''.join(f'<span class="s-cn s-c{i}">{corner_svg()}</span>' for i in range(4)) + body)
    if v == 'torn':
        rng = rng_for(st)
        n = 26
        top = [(100 * i / n, rng.uniform(0, 2.2)) for i in range(n + 1)]
        bot = [(100 - 100 * i / n, 100 - rng.uniform(0, 2.2)) for i in range(n + 1)]
        css += 'clip-path:polygon(' + ','.join(f'{x:.1f}% {y:.1f}%' for x, y in top + bot) + ');'
        return place(st, 'card', f'<div class="s-pg" style="{esc(css)}">{body}</div>', 'v-torn', size=32, width=620)
    return place(st, 'card', f'<div class="s-pg">{body}</div>', f'v-{v}', css=css, size=32, width=620)


MENU_ICONS = {'save': 'save', 'download': 'save', 'copy': 'copy', 'share': 'share', 'more': 'more', 'delete': 'trash',
              'remove': 'trash', 'edit': 'edit', 'reply': 'reply', 'forward': 'forward', 'pin': 'pin-tack', 'like': 'heart',
              'love': 'heart', 'favorite': 'star', 'favourite': 'star', 'link': 'link', 'report': 'flag', 'lock': 'lock'}


def k_menu(st, ctx):
    items = st.get('items') or ['Save', 'Copy', 'More']
    rows = ''
    for x in items:
        if x in ('-', '---', None):
            rows += '<div class="s-gap"></div>'
            continue
        x = x if isinstance(x, dict) else {'text': x}
        t = str(x.get('text', ''))
        key = t.lower().split(' ')[0] if t else ''
        ic = x.get('icon') or MENU_ICONS.get(key, 'more' if key.startswith('more') else '')
        red = ' s-red' if x.get('red') or key in ('delete', 'remove', 'report') else ''
        rows += f'<div class="s-it{red}"><span>{_md(t)}</span>{icon(ic) if ic else ""}</div>'
    return place(st, 'menu', rows, 'is-dark' if st.get('dark') else '', size=38, width=540)


def k_camera(st, ctx):
    v = st.get('variant') or st.get('look') or 'modes'
    if v == 'focus':
        return place(st, 'camera', '<span class="s-fq"><i class="s-t"></i><i class="s-r"></i><i class="s-b"></i><i class="s-l"></i></span>'
                     + (f'<span class="s-sun">{icon("sun")}</span>' if st.get('sun', True) else ''), 'v-focus', width=220,
                     css=f'height:{fmt(num(st.get("h"), num(st.get("w"), 220)))}px;')
    if v == 'shutter':
        return place(st, 'camera', '<span class="s-sh"><i></i></span>', 'v-shutter', width=170)
    if v == 'zoom':
        levels = st.get('levels') or ['.5', '1×', '3']
        act = str(st.get('active', levels[min(1, len(levels) - 1)]))
        return place(st, 'camera', ''.join(f'<span class="s-z{" s-on" if str(l) == act else ""}">{esc(l)}</span>' for l in levels),
                     'v-zoom', size=30)
    modes = st.get('modes') or ['Slo-mo', 'Video', 'Photo', 'Portrait', 'Square']
    act = str(st.get('active', 'Photo')).lower()
    return place(st, 'camera', ''.join(f'<span class="s-m{" s-on" if str(m).lower() == act else ""}">{esc(m)}</span>' for m in modes),
                 'v-modes', size=30)


TAPBACKS = ['heart', 'thumb', 'down', 'haha', 'bang', 'q']


def tapback(name):
    if name == 'heart':
        return icon('heart', fill=True)
    if name == 'thumb':
        return icon('thumb')
    if name == 'down':
        return icon('thumb', 's-flipv')
    if name == 'haha':
        return '<svg class="s-ic" viewBox="0 0 24 24"><text x="12" y="11" text-anchor="middle" font-size="9.8" font-weight="900" fill="currentColor" font-family="Inter,sans-serif">HA</text><text x="12" y="20.6" text-anchor="middle" font-size="9.8" font-weight="900" fill="currentColor" font-family="Inter,sans-serif">HA</text></svg>'
    if name == 'bang':
        return '<svg class="s-ic" viewBox="0 0 24 24"><text x="12" y="19" text-anchor="middle" font-size="19" font-weight="900" fill="currentColor" font-family="Inter,sans-serif">!!</text></svg>'
    if name == 'q':
        return '<svg class="s-ic" viewBox="0 0 24 24"><text x="12" y="19.4" text-anchor="middle" font-size="20" font-weight="900" fill="currentColor" font-family="Inter,sans-serif">?</text></svg>'
    if name in FILLED:
        return icon(name, fill=True)
    return icon(name)


def k_toolbar(st, ctx):
    v = st.get('variant') or st.get('look') or 'reactions'
    if v == 'nav':
        av = ctx.get('avatar') or ''
        prof = f'<span class="s-av"><img src="{esc(av)}" alt=""></span>' if av else '<span class="s-av s-blank"></span>'
        act = int(num(st.get('active'), 1))
        ics = [icon('home'), icon('search'), icon('add'), icon('play-square'), prof]
        return place(st, 'toolbar', ''.join(f'<span class="s-n{" s-on" if i == act else ""}">{x}</span>' for i, x in enumerate(ics, 1)),
                     'v-nav' + (' is-dark' if st.get('dark') else ''), size=40, width=1080)
    if v == 'actions':
        counts = st.get('counts') or []
        names = ['heart', 'comment', 'send']
        liked = st.get('liked')
        parts = ''
        for i, n in enumerate(names):
            c = f'<b>{esc(counts[i])}</b>' if i < len(counts) else ''
            ic = icon('heart', 's-liked', fill=True) if (n == 'heart' and liked) else icon(n)
            parts += f'<span class="s-a">{ic}{c}</span>'
        return place(st, 'toolbar', f'<span class="s-grp">{parts}</span><span class="s-a s-sv">{icon("bookmark")}</span>',
                     'v-actions' + (' is-dark' if st.get('dark') else ''), size=40, width=700)
    icons = st.get('icons') or TAPBACKS
    act = st.get('active')
    out = ''.join(f'<span class="s-r{" s-on" if (act is not None and (str(act) == str(n) or str(act) == str(i))) else ""}">{tapback(str(n))}</span>'
                  for i, n in enumerate(icons, 1))
    return place(st, 'toolbar', out, f'v-{v}' + (' is-dark' if st.get('dark') else ''), size=40)


SEGS = {'0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc', '5': 'afgcd', '6': 'afgedc', '7': 'abc',
        '8': 'abcdefg', '9': 'abcdfg', '-': 'g', 'A': 'abcefg', 'P': 'abefg', 'E': 'adefg', 'H': 'bcefg', 'L': 'def',
        'C': 'adef', 'F': 'aefg', 'b': 'cdefg', 'd': 'bcdeg', 'o': 'cdeg', 'r': 'eg', 'n': 'ceg', 'U': 'bcdef', 'Y': 'bcdfg'}


def seven_seg(text, h=60.0):
    """The orange LCD date of a film camera, drawn segment by segment (digits, ', :, -, . and a few letters)."""
    T, W, gap = h * 0.13, h * 0.5, h * 0.022
    out, x = [], 0.0

    def hseg(x0, y):
        a, b = x0 + T * 0.5 + gap, x0 + W - T * 0.5 - gap
        return f'M{a:.1f},{y:.1f}L{a + T / 2:.1f},{y - T / 2:.1f}H{b - T / 2:.1f}L{b:.1f},{y:.1f}L{b - T / 2:.1f},{y + T / 2:.1f}H{a + T / 2:.1f}Z'

    def vseg(xc, y0, y1):
        a, b = y0 + gap, y1 - gap
        return f'M{xc:.1f},{a:.1f}L{xc + T / 2:.1f},{a + T / 2:.1f}V{b - T / 2:.1f}L{xc:.1f},{b:.1f}L{xc - T / 2:.1f},{b - T / 2:.1f}V{a + T / 2:.1f}Z'
    for ch in str(text):
        up = ch if ch in SEGS else ch.upper()
        if up in SEGS:
            top, mid, bot = T / 2, h / 2, h - T / 2
            L, R = x + T / 2, x + W - T / 2
            parts = {'a': hseg(x, top), 'g': hseg(x, mid), 'd': hseg(x, bot), 'f': vseg(L, top, mid), 'b': vseg(R, top, mid),
                     'e': vseg(L, mid, bot), 'c': vseg(R, mid, bot)}
            out += [parts[s] for s in SEGS[up]]
            x += W + h * 0.12
        elif ch == "'":
            out.append(f'M{x + T * 0.2:.1f},{0:.1f}h{T * 0.8:.1f}l{-T * 0.5:.1f},{h * 0.3:.1f}h{-T * 0.5:.1f}Z')
            x += T * 1.6
        elif ch in ':.':
            r = T * 0.5
            ys = (h * 0.3, h * 0.72) if ch == ':' else (h - r,)
            out += [f'M{x + r:.1f},{y - r:.1f}h{r * 1.2:.1f}v{r * 2:.1f}h{-r * 1.2:.1f}Z' for y in ys]
            x += T * 2.4
        else:
            x += W * 0.62
    w = max(x - h * 0.12, 1)
    return (f'<svg class="s-seg" viewBox="{-h * 0.1:.1f} 0 {w + h * 0.2:.1f} {h:.1f}" width="{(w + h * 0.2) / h:.2f}em" height="1em">'
            f'<g transform="skewX(-7) translate({h * 0.07:.1f} 0)"><path d="{"".join(out)}"/></g></svg>')


def k_stamp(st, ctx):
    v = st.get('variant') or st.get('look') or 'ui'
    text = st.get('text', "'26 05 14" if v == 'film' else ('Approved' if v == 'rubber' else 'Today 9:41 AM'))
    if v == 'ui' and st.get('bold'):
        inner = f'<b>{_md(st["bold"])}</b> {_md(text)}'
    else:
        inner = _md(text)
    if v == 'film':
        return place(st, 'stamp', seven_seg(text), 'v-film', size=44)
    if v == 'rubber':
        rng = rng_for(st)
        return place(st, 'stamp', f'<span class="s-rb" style="--rx:{rng.uniform(0, 100):.0f}%;--ry:{rng.uniform(0, 100):.0f}%">{inner}</span>', 'v-rubber', size=40)
    return place(st, 'stamp', inner, f'v-{v}', size=30 if v == 'ui' else 40)


def k_statusbar(st, ctx):
    bat = max(5, min(100, num(st.get('battery'), 80)))
    inner = (f'<span class="s-tm">{esc(st.get("time", "9:41"))}</span><span class="s-ics">'
             '<svg viewBox="0 0 20 12" class="s-sig"><rect x="0" y="8" width="3.2" height="4" rx=".8"/><rect x="5.4" y="5.6" width="3.2" height="6.4" rx=".8"/>'
             '<rect x="10.8" y="3" width="3.2" height="9" rx=".8"/><rect x="16.2" y="0" width="3.2" height="12" rx=".8"/></svg>'
             '<svg viewBox="0 0 17 12" class="s-wifi"><path d="M8.5 2.4c2.5 0 4.8 1 6.5 2.6l1.3-1.4A11.1 11.1 0 0 0 8.5.4 11.1 11.1 0 0 0 .7 3.6L2 5c1.7-1.6 4-2.6 6.5-2.6z"/>'
             '<path d="M8.5 6.1c1.5 0 2.9.6 3.9 1.5l1.3-1.4A7.6 7.6 0 0 0 8.5 4.1a7.6 7.6 0 0 0-5.2 2.1l1.3 1.4c1-.9 2.4-1.5 3.9-1.5z"/>'
             '<path d="M8.5 9.6c.6 0 1.1.2 1.5.6l-1.5 1.6-1.5-1.6c.4-.4.9-.6 1.5-.6z"/></svg>'
             f'<span class="s-bat"><i style="width:{bat:.0f}%"></i></span></span>')
    return place(st, 'statusbar', inner, 'is-dark' if st.get('dark') else '', size=38, width=1080)


def k_player(st, ctx):
    art = f'<img src="{esc(_src(st["src"], ctx))}" alt="">' if st.get('src') else ''
    p = max(0, min(1, num(st.get('progress'), 0.38)))
    return place(st, 'player',
                 f'<div class="s-top"><span class="s-art">{art}</span><span class="s-meta"><b>{_md(st.get("title", "Song title"))}</b>'
                 f'<span>{_md(st.get("artist", "Artist"))}</span></span></div>'
                 f'<div class="s-bar"><i style="width:{p * 100:.0f}%"></i><b style="left:{p * 100:.0f}%"></b></div>'
                 f'<div class="s-times"><span>{esc(st.get("time", "1:12"))}</span><span>-{esc(st.get("left", "2:04"))}</span></div>'
                 f'<div class="s-ctl">{icon("prev", fill=True)}{icon("pause" if st.get("playing", True) else "play", "s-pp", fill=True)}{icon("next", fill=True)}</div>',
                 'is-light' if st.get('light') else '', size=30, width=820)


def k_clip(st, ctx):
    c = {'silver': ('#E9ECF0', '#9AA1AB'), 'gold': ('#F6DC94', '#B8902F'), 'black': ('#555', '#111'),
         'pink': ('#FFD0DE', '#E27FA0'), 'rosegold': ('#F7D3C4', '#C98C77')}.get(str(st.get('color', 'silver')).lower(), ('#E9ECF0', '#9AA1AB'))
    uid = abs(hash((str(st.get('x')), str(st.get('y')), c))) % 10 ** 8
    path = 'M14 54V12a8 8 0 0 1 16 0v46a12 12 0 0 1-24 0V18'
    svg = (f'<svg viewBox="0 0 36 76" class="s-cl"><defs><linearGradient id="cg{uid}" x1="0" x2="1">'
           f'<stop offset="0" stop-color="{c[1]}"/><stop offset=".45" stop-color="{c[0]}"/><stop offset="1" stop-color="{c[1]}"/></linearGradient></defs>'
           f'<path d="{path}" fill="none" stroke="rgba(0,0,0,.28)" stroke-width="4.4" stroke-linecap="round" transform="translate(1.2 1.6)"/>'
           f'<path d="{path}" fill="none" stroke="url(#cg{uid})" stroke-width="3.6" stroke-linecap="round"/>'
           f'<path d="{path}" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1" stroke-linecap="round" transform="translate(-.6 -.4)"/></svg>')
    return place(st, 'clip', svg, width=70)


KINDS = {
    'location': k_location, 'search': k_search, 'bubble': k_bubble, 'notification': k_notification, 'notes': k_notes,
    'receipt': k_receipt, 'polaroid': k_polaroid, 'tape': k_tape, 'sticky': k_sticky, 'hand': k_hand,
    'circle': k_circle, 'arrow': k_arrow, 'underline': k_underline,
    'sparkle': lambda s, c: k_icon_shape(s, c, 'sparkle'), 'star': lambda s, c: k_icon_shape(s, c, 'star'),
    'heart': lambda s, c: k_icon_shape(s, c, 'heart'),
    'highlight': k_highlight, 'label': k_label, 'folder': k_folder, 'card': k_card, 'menu': k_menu,
    'camera': k_camera, 'toolbar': k_toolbar, 'stamp': k_stamp, 'statusbar': k_statusbar, 'player': k_player,
    'clip': k_clip,
}
ALIASES = {'pin': ('location', {}), 'place': ('location', {}), 'imessage': ('bubble', {}), 'message': ('bubble', {}),
           'reply': ('bubble', {'variant': 'reply'}), 'typing': ('bubble', {'variant': 'typing'}),
           'note': ('notes', {}), 'guestcheck': ('receipt', {}), 'photo': ('polaroid', {}), 'postit': ('sticky', {}),
           'text': ('hand', {}), 'handwriting': ('hand', {}), 'scribble': ('circle', {}), 'pill': ('label', {}),
           'chip': ('label', {}), 'strip': ('highlight', {'variant': 'strip'}), 'marker': ('highlight', {}),
           'focus': ('camera', {'variant': 'focus'}), 'shutter': ('camera', {'variant': 'shutter'}),
           'zoom': ('camera', {'variant': 'zoom'}), 'nav': ('toolbar', {'variant': 'nav'}),
           'reactions': ('toolbar', {'variant': 'reactions'}), 'date': ('stamp', {}), 'paperclip': ('clip', {}),
           'music': ('player', {}), 'banner': ('notification', {}), 'contextmenu': ('menu', {})}


def render(sticker, ctx):
    """-> the HTML of one sticker. Unknown types raise, so render.py shows which one broke."""
    st = dict(sticker or {})
    t = str(st.get('type', '')).lower().replace('-', '').replace('_', '').replace(' ', '')
    if t in ALIASES:
        t, extra = ALIASES[t]
        st = dict(extra, **st)
    fn = KINDS.get(t)
    if not fn:
        raise ValueError(f'unknown sticker type "{sticker.get("type")}". Types: ' + ', '.join(sorted(KINDS)))
    return fn(st, ctx or {})
