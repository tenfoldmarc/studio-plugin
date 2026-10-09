#!/usr/bin/env python3
"""Orbit, step 2: crop the covers and MEASURE the ring from the speaker's cutout. Run from the slot folder with any
python that has numpy and Pillow (seconds, run it again after every change to the CLIP block):

  python prep.py

Reads the CLIP block from build.py, clip.json, assets/aroll.mp4, assets/subject.webm, the covers folder. Writes:
  assets/tiles/tNN_b.jpg, tNN_f.jpg   the covers cropped to 9:16 cards (far copy, near copy)
  work/tiles.json                     their order and count labels
  work/ring.json                      ring centre, radii, card size, per-frame follow offsets, face box, warnings
  work/ring.jpg                       CHECK PICTURE at half size: face box red, near cards yellow, far cards cyan,
                                      the border outside the safe zone shaded red, caption block yellow

How the ring is found: on every frame the head is read from the cutout's alpha (top of the silhouette, the run of
pixels under it, the narrowest row before the shoulders = the neck). The face box is everything from the top of the
head to the neck over the ring's time on screen. The ring sits as high as it can while every near card stays under
that box by FACE_GAP, and as wide as the safe zone allows. If it does not fit above y 1470 the cards shrink; if it
still does not fit the shot is too close and the script stops.
"""
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import build as B      # noqa: E402  (the CLIP block lives there)

FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H = B.W, B.H
Q = 4                  # the alpha is measured at 1/4 size
SW, SH = W // Q, H // Q
CLIPJ = json.load(open('clip.json'))
N = int(CLIPJ['frames'])
F0, F1 = B.span(N)
S = B.SAFE
os.makedirs('work', exist_ok=True)
WARN = []


def warn(msg):
    WARN.append(msg)
    print('WARNING: ' + msg)


# ---------------------------------------------------------------------------------------------------------- covers
def count_label(v):
    """a real play count -> the short form a profile grid shows. Strings are used exactly as written."""
    if v is None or isinstance(v, str):
        return v
    n = int(v)
    if n < 10_000:
        return f'{n:,}'
    if n < 100_000:
        return f'{int(n / 100) / 10:.1f}'.rstrip('0').rstrip('.') + 'K'
    if n < 1_000_000:
        return f'{n // 1000}K'
    return f'{int(n / 10_000) / 100:.2f}'.rstrip('0').rstrip('.') + 'M'


def make_tiles():
    src = B.COVERS if os.path.isabs(B.COVERS) else os.path.join(HERE, B.COVERS)
    ok = ('.jpg', '.jpeg', '.png', '.webp')
    files = sorted(f for f in os.listdir(src) if f.lower().endswith(ok) and not f.startswith('.')) \
        if os.path.isdir(src) else []
    if len(files) < 4:
        sys.exit(f'covers: found {len(files)} image(s) in "{B.COVERS}". Put at least 4 of your own reel covers '
                 '(jpg / png / webp) in that folder. Nothing is shipped with the effect: no covers, no orbit.')
    stems = [os.path.splitext(f)[0] for f in files]
    for k in B.COUNTS:
        if k not in files and k not in stems:
            warn(f'COUNTS has "{k}" but there is no cover with that file name')
    files = files[:min(max(int(B.CARDS), 4), 8)]
    tw, th = 2 * B.CARD_W, 2 * round(B.CARD_W * 16 / 9)       # stored at 2x so the near cards stay sharp
    os.makedirs('assets/tiles', exist_ok=True)
    out = []
    for k, f in enumerate(files):
        im = Image.open(os.path.join(src, f)).convert('RGB')
        w, h = im.size
        if w / h > tw / th:                       # wider than a card: keep the part CROP_Y of the way across
            cw = h * tw / th
            left = (w - cw) * B.CROP_Y
            box = (left, 0, left + cw, h)
        else:                                     # taller: keep the part CROP_Y of the way down
            ch = w * th / tw
            top = (h - ch) * B.CROP_Y
            box = (0, top, w, top + ch)
        im = im.crop(tuple(int(round(v)) for v in box)).resize((tw, th), Image.LANCZOS)
        for side in 'bf':
            im.save(os.path.join('assets', 'tiles', f't{k:02d}_{side}.jpg'), quality=88)
        raw = B.COUNTS.get(f, B.COUNTS.get(os.path.splitext(f)[0]))
        out.append({'file': f't{k:02d}', 'src': f, 'label': count_label(raw)})
    json.dump(out, open('work/tiles.json', 'w'), indent=1)
    with_counts = sum(1 for t in out if t['label'])
    print(f'covers: {len(out)} cards in assets/tiles/  counts on {with_counts} of them'
          + ('' if with_counts else ' (COUNTS is empty: cards carry no numbers)'))
    return out


# ------------------------------------------------------------------------------------------------------------ head
def runs(row):
    """[(first x, last x), ...] of the True runs in one row"""
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1))


def head_of(m):
    """(top y, left x, right x, neck y) of the head in one alpha mask (quarter-size px), or None"""
    rows = np.flatnonzero(m.sum(1) > 5)
    if not len(rows):
        return None
    top = int(rows[0])
    l, r = max(runs(m[top]), key=lambda a: a[1] - a[0])
    ls, rs = [l], [r]
    for y in range(top + 1, SH):                  # follow the run that hangs under the head, row by row
        best = max(runs(m[y]), key=lambda a: min(a[1], r) - max(a[0], l), default=None)
        if best is None or min(best[1], r) - max(best[0], l) < 0:
            break
        l, r = best
        ls.append(l)
        rs.append(r)
    wd = np.array(rs) - np.array(ls) + 1
    # the head: the silhouette widens over the crown, then stops widening. That plateau is the head width
    p = next((y for y in range(4, len(wd) - 6) if wd[y] >= 8 and wd[y + 6] <= 1.04 * wd[y]), None)
    if p is None:
        return None
    hw = int(wd[:p + 7].max())
    wide = np.flatnonzero(wd[p:] >= 1.4 * hw)     # the first row that is clearly shoulders
    neck = None
    if len(wide):                                 # face ends on the last row above them that is still head-wide
        slim = np.flatnonzero(wd[:p + int(wide[0])] <= 1.12 * hw)
        neck = int(slim[-1])
    if neck is None or not hw <= neck <= 1.9 * hw:
        neck = int(1.35 * hw)                     # no clear shoulders (close-up, hand at the face): ~1.35 head-widths
    d = max(p + 7, int(.9 * hw))
    return top, int(min(ls[:d])), int(max(rs[:d])), top + neck


def gauss(v, sig):
    k = np.exp(-.5 * (np.arange(-3 * sig, 3 * sig + 1) / sig) ** 2)
    return np.convolve(np.pad(v, 3 * sig, mode='edge'), k / k.sum(), mode='valid')


def card_rect(x, y, sc, tw, th):
    return x - sc * tw / 2, y - sc * th / 2, x + sc * tw / 2, y + sc * th / 2


def hits(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


# ------------------------------------------------------------------------------------------------------------ ring
def measure(n_cards):
    if any(F0 < c <= F1 for c in CLIPJ.get('cut_frames') or []):
        sys.exit('orbit needs ONE continuous shot while the ring is up: there is a cut between F_IN and F_OUT')
    if not os.path.exists('assets/subject.webm'):
        sys.exit('assets/subject.webm is missing: orbit needs the cutout (make the slot without --no-cutout)')
    raw = subprocess.run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', 'assets/subject.webm', '-vf',
                          f'alphaextract,scale={SW}:{SH}:flags=area,format=gray', '-fps_mode', 'passthrough',
                          '-f', 'rawvideo', '-'], capture_output=True).stdout
    M = np.frombuffer(raw, np.uint8).reshape(-1, SH, SW) > 128
    if len(M) != N:
        sys.exit(f'assets/subject.webm: decoded {len(M)} frames, clip.json says {N} (remake the slot)')
    heads = [head_of(m) for m in M]
    if sum(h is None for h in heads[F0:F1 + 1]) > .3 * (F1 - F0 + 1):
        sys.exit('no speaker found in the cutout on a third of the frames: orbit is left out for this clip')
    last = next(h for h in heads[F0:] if h is not None)
    for k in range(N):                            # frames with no head take the nearest earlier one
        if heads[k] is None:
            heads[k] = last
        last = heads[k]
    hd = np.array(heads, float) * Q               # N x (top, left, right, neck) in frame px
    pad = np.pad(hd, ((3, 3), (0, 0)), mode='edge')            # a 7-frame median drops single-frame misreads
    hd = np.median(np.stack([pad[k:k + N] for k in range(7)]), axis=0)
    on = hd[F0:F1 + 1]
    face = [float(np.percentile(on[:, 1], 2)), float(np.percentile(on[:, 0], 2)),
            float(np.percentile(on[:, 2], 98)), float(np.percentile(on[:, 3], 98))]
    head_h = float(np.median(on[:, 3] - on[:, 0]))
    typ = M[F0:F1 + 1].mean(0) > .5               # where the speaker is on most frames of the ring
    y0, y1 = int(face[3] / Q), min(SH, int((face[3] + 1.2 * head_h) / Q))
    col = typ[y0:y1].sum(0)
    chest_x = float(np.average(np.arange(SW), weights=col) * Q) if col.sum() else (face[0] + face[2]) / 2

    # follow: head centre and head top, smoothed hard, only if they travel
    dx = gauss((hd[:, 1] + hd[:, 2]) / 2, 8)
    dy = gauss(hd[:, 0], 8)
    dx -= np.median(dx[F0:F1 + 1])
    dy -= np.median(dy[F0:F1 + 1])
    follows = bool(B.FOLLOW and max(np.ptp(dx[F0:F1 + 1]), np.ptp(dy[F0:F1 + 1])) >= 10)
    if not follows:
        dx[:], dy[:] = 0, 0
    mdx, mdy = float(np.abs(dx[F0:F1 + 1]).max()), float(dy[F0:F1 + 1].max())

    mid = (S['side'] + W - S['side']) / 2
    # centre: mostly the head (that is what the far cards pass behind), a little the chest, pulled up to 40 px
    # towards the middle of the frame so the ring has room on both sides
    body_x = .7 * float(np.median((on[:, 1] + on[:, 2]) / 2)) + .3 * chest_x
    cx = float(B.CX) if B.CX is not None else body_x + float(np.clip(mid - body_x, -40, 40))
    grown = [face[0] - B.FACE_GAP, face[1] - B.FACE_GAP, face[2] + B.FACE_GAP, face[3] + B.FACE_GAP]
    ths = [2 * math.pi * k / 180 for k in range(180)]

    def fit(k, tilt):
        """ring for card scale k and this tilt: (tw, th, rx, ry, cy, bottom)"""
        tw = round(B.CARD_W * k)
        th = round(tw * 16 / 9)
        edge = (B.NEAR + B.FAR) / 2 * tw / 2      # half a card where the ring is widest
        rx_max = min(cx - S['side'] - edge, W - S['side'] - edge - cx) - mdx
        rows = typ[int(face[3] / Q):min(SH, int((face[3] + 2.5 * head_h) / Q))]
        xs = np.flatnonzero(rows.any(0))
        body = max(cx - xs[0] * Q, xs[-1] * Q - cx) if len(xs) else 0
        rx = float(B.RX) if B.RX is not None else max(min(rx_max, body + 2.5 * tw), 1.2 * tw)
        while True:
            ry = tilt * rx
            cy = face[3] + B.FACE_GAP + B.NEAR * th / 2 - ry
            for _ in range(200):                  # lower the ring until no near card touches the face box
                pts = [(cx + rx * math.cos(t), cy + ry * math.sin(t), B.FAR + (B.NEAR - B.FAR) * (math.sin(t) + 1) / 2)
                       for t in ths if math.sin(t) > -.08]
                if not any(hits(card_rect(x, y, sc, tw, th), grown) for x, y, sc in pts):
                    break
                cy += 4
            if B.CY is not None:
                cy = float(B.CY)
            # right-hand strip: nothing right of x 980 from y 1155 down
            bad = any(card_rect(cx + rx * math.cos(t), cy + ry * math.sin(t),
                                B.FAR + (B.NEAR - B.FAR) * (math.sin(t) + 1) / 2, tw, th)[3] + mdy > S['right_from']
                      and card_rect(cx + rx * math.cos(t), cy + ry * math.sin(t),
                                    B.FAR + (B.NEAR - B.FAR) * (math.sin(t) + 1) / 2, tw, th)[2] + mdx > W - S['right']
                      for t in ths)
            if not bad or B.RX is not None or rx <= 1.2 * tw:
                break
            rx -= 8
        return tw, th, rx, ry, cy, cy + ry + B.NEAR * th / 2 + mdy, body

    best = None
    for k in (1, .95, .9, .85, .8, .75, .7, .65, .6):
        for tilt in (B.TILT, B.TILT * .85, B.TILT * .7):
            best = fit(k, tilt)
            if best[5] <= S['bottom'] or B.CY is not None:
                break
        if best[5] <= S['bottom'] or B.CY is not None:
            break
    tw, th, rx, ry, cy, bottom, body = best
    if bottom > S['bottom'] and B.CY is None:
        sys.exit(f'the face reaches down to y {face[3]:.0f}: even at 60% size the near cards would end at y {bottom:.0f}, '
                 f'below the safe line {S["bottom"]}. This shot is too close for orbit: leave the effect out, or use a '
                 'wider shot.')
    if tw < B.CARD_W:
        print(f'cards shrunk to {tw} px wide so the ring fits between the chin and y {S["bottom"]}')
    ring = {'frames': N, 'span': [F0, F1], 'cards': n_cards, 'cx': round(cx, 1), 'cy': round(cy, 1), 'rx': round(rx, 1), 'ry': round(ry, 1),
            'tw': tw, 'th': th, 'face': [round(v) for v in face], 'follows': follows,
            'dx': [round(float(v), 1) for v in dx], 'dy': [round(float(v), 1) for v in dy]}

    # the real thing, frame by frame: near cards against that frame's own face box, every card against the safe zone
    for _ in range(25):
        face_hit, out = set(), set()
        for f in range(F0, F1 + 1):
            fb = [hd[f, 1] - B.FACE_GAP, hd[f, 0] - B.FACE_GAP, hd[f, 2] + B.FACE_GAP, hd[f, 3] + B.FACE_GAP]
            for i in range(n_cards):
                x, y, sc, s = B.ring_pos(ring, i, n_cards, f, F0)
                rc = card_rect(x, y, sc, tw, th)
                if s > -.08 and hits(rc, fb):
                    face_hit.add(f)
                if rc[0] < S['side'] - 1 or rc[2] > W - S['side'] + 1 or rc[1] < S['top'] - 1 or rc[3] > S['bottom'] + 1 \
                        or (rc[3] > S['right_from'] and rc[2] > W - S['right'] + 1):
                    out.add(f)
        if not face_hit or B.CY is not None or ring['cy'] + ry + B.NEAR * th / 2 + mdy + 6 > S['bottom']:
            break
        ring['cy'] = round(ring['cy'] + 6, 1)
    if face_hit:
        warn(f'a near card touches the face box on {len(face_hit)} frame(s) (first f{min(face_hit)}): lower CY or raise FACE_GAP')
    if out:
        warn(f'a card leaves the safe zone on {len(out)} frame(s) (first f{min(out)}): look at work/ring.jpg, '
             'then set CX / RX / CY or a smaller CARD_W')
    if rx < body + .4 * tw:
        warn(f'the speaker is {2 * body:.0f} px wide under the chin and the ring only {2 * rx:.0f}: cards change from '
             'behind to in front while they are still over an arm or shoulder (a soft pop there). A wider shot fixes it')
    if abs(body_x - mid) > 150:
        warn(f'the speaker is off centre (around x {body_x:.0f}): the ring is squeezed against the frame edge')

    cap_h = B.caption_height()
    cap_y = None
    if cap_h:
        under = ring['cy'] + ry + B.NEAR * th / 2 + mdy + 36
        above = face[1] - 44 - cap_h
        cap_y = int(under) if under + cap_h <= S['bottom'] - 6 else (int(above) if above >= S['top'] + 10 else None)
        if cap_y is None and B.CAP_Y is None:
            warn('no room for the caption block under the ring or above the head: captions are left out (CAP_Y forces a place)')
    ring['cap_y'] = cap_y
    ring['warnings'] = WARN
    json.dump(ring, open('work/ring.json', 'w'))
    print(f'ring: centre ({ring["cx"]:.0f}, {ring["cy"]:.0f})  radius {rx:.0f} x {ry:.0f}  cards {tw}x{th}  '
          f'face box x {face[0]:.0f}-{face[2]:.0f} y {face[1]:.0f}-{face[3]:.0f}  near cards top out at y '
          f'{ring["cy"] + ry - B.NEAR * th / 2:.0f}, end at y {ring["cy"] + ry + B.NEAR * th / 2 + mdy:.0f}  '
          f'{"follows the head (" + format(max(np.ptp(dx), np.ptp(dy)), ".0f") + " px of travel)" if follows else "fixed (the shot is steady)"}')
    return ring, cap_h


def check_picture(ring, n_cards, cap_h):
    ref = B.REF if B.REF is not None else (F0 + F1) // 2
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-vf', f"select='eq(n\\,{ref})',scale={W // 2}:{H // 2}",
                          '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    im = Image.frombuffer('RGB', (W // 2, H // 2), raw).convert('RGBA')
    ov = Image.new('RGBA', im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    def box(rc, **kw):
        d.rectangle([v / 2 for v in rc], **kw)
    for rc in ((0, 0, W, S['top']), (0, S['bottom'], W, H), (0, S['top'], S['side'], S['bottom']),
               (W - S['side'], S['top'], W, S['right_from']), (W - S['right'], S['right_from'], W, S['bottom'])):
        box(rc, fill=(255, 0, 0, 60))
    k = min(ref, N - 1)
    cx, cy = ring['cx'] + ring['dx'][k], ring['cy'] + ring['dy'][k]
    d.ellipse([(cx - ring['rx']) / 2, (cy - ring['ry']) / 2, (cx + ring['rx']) / 2, (cy + ring['ry']) / 2],
              outline=(255, 255, 255, 200), width=2)
    box(ring['face'], outline=(255, 40, 40, 255), width=3)
    for i in range(n_cards):
        x, y, sc, s = B.ring_pos(ring, i, n_cards, ref, F0)
        box(card_rect(x, y, sc, ring['tw'], ring['th']), outline=(255, 225, 0, 255) if s > 0 else (0, 220, 255, 255), width=3)
    cap_y = B.CAP_Y if B.CAP_Y is not None else ring['cap_y']
    if cap_h and cap_y is not None:
        box((W / 2 - 260, cap_y, W / 2 + 260, cap_y + cap_h), outline=(255, 225, 0, 255), fill=(255, 225, 0, 50), width=2)
    Image.alpha_composite(im, ov).convert('RGB').save('work/ring.jpg', quality=85)
    print(f'check picture: work/ring.jpg (frame {ref}, half size)')


if __name__ == '__main__':
    tiles = make_tiles()
    ring, cap_h = measure(len(tiles))
    check_picture(ring, len(tiles), cap_h)
