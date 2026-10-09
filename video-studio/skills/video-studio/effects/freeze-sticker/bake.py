#!/usr/bin/env python3
"""sticker bake: turns the freeze frame into a die-cut sticker and lays out the handwritten notes around it.
Run from the slot folder with a python that has numpy, scipy and Pillow (no OpenCV):

    python bake.py frames     work/frames.jpg: the frames around F_FREEZE with a sharpness score. LOOK, pick the frame
    python bake.py            the bake (about 20 s): assets/sticker/sticker.png, shadow.png, (back.jpg), sticker.json,
                              and work/check.jpg (the layout, half size). LOOK at it before you render

It reads the CLIP block of build.py. Change anything in that block = run bake.py again (build.py refuses otherwise).
What is measured here, not typed: the outline (largest blob of the cutout, small holes filled, dents closed), which
frame edges cut the speaker, the head, how big the sticker is and where it sits, where every note has room.
"""
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H, PAD, G = 1080, 1920, 260, 4
TOP = 640                  # where the top of the head goes on screen when the footage allows (room for a note above)
MAXS, MINS = 150, 56       # biggest and smallest handwriting, px
FONT = 'assets/fonts/Caveat-600-normal.woff2'
VP9 = ('-c:v', 'libvpx-vp9')

block = open('build.py').read().split('# ==== CLIP (edit this) ====')[1].split('# ==== END CLIP ====')[0]
C = {}
exec(block, C)
N = json.load(open('clip.json'))['frames']
F, F_OUT = C['F_FREEZE'], C['F_OUT']
if not 2 <= F <= N - 20:
    sys.exit(f'F_FREEZE = {F}: it has to be between 2 and {N - 20} (2 plain frames before it, 20 frames of sticker after)')
if F_OUT is not None and not F + 24 <= F_OUT <= N - 2:
    sys.exit(f'F_OUT = {F_OUT}: it has to be between {F + 24} and {N - 2}, or None')
warn = []


def say(msg):
    warn.append(msg)
    print('  !! ' + msg)


def grab(path, frames, fmt, pre=(), extra=''):
    sel = '+'.join(f'eq(n\\,{f})' for f in frames)
    raw = subprocess.run([FF, '-v', 'error', *pre, '-i', path, '-vf', f"select='{sel}'{extra},scale={W}:{H}", '-fps_mode',
                          'passthrough', '-f', 'rawvideo', '-pix_fmt', fmt, '-'], capture_output=True).stdout
    c = 3 if fmt == 'rgb24' else 1
    if len(raw) < len(frames) * W * H * c:
        sys.exit(f'could not read frame(s) {frames} of {path}' + (' (no cutout? the slot needs assets/subject.webm)' if pre else ''))
    return np.frombuffer(raw, np.uint8)[:len(frames) * W * H * c].reshape(len(frames), H, W, c)


def edt(b):
    return ndimage.distance_transform_edt(b)


os.makedirs('work', exist_ok=True)
os.makedirs('assets/sticker', exist_ok=True)

# ------------------------------------------------------------------ "frames": help picking the still
if len(sys.argv) > 1 and sys.argv[1] == 'frames':
    fs = [f for f in range(F - 3, F + 4) if 0 <= f < N]
    rgb = grab('assets/aroll.mp4', fs, 'rgb24')
    al = grab('assets/subject.webm', fs, 'gray', VP9, ',alphaextract')[..., 0]
    ys, xs = np.where(al[fs.index(F)] > 127)
    if not len(ys):
        sys.exit(f'the cutout is empty on frame {F}')
    y0, y1 = ys.min(), min(H, ys.min() + max(300, int((ys.max() - ys.min()) * .55)))
    x0, x1 = max(0, xs.min() - 20), min(W, xs.max() + 20)
    th = 300
    tw_ = max(60, int((x1 - x0) * th / (y1 - y0)))
    sheet = Image.new('RGB', (tw_ * len(fs), th + 26), (20, 20, 24))
    sc = []
    for i, f in enumerate(fs):
        g = rgb[i, y0:y1, x0:x1].astype(np.float32).mean(2)
        m = al[i, y0:y1, x0:x1] > 127
        e = np.abs(np.diff(g, axis=0))[:, :-1] + np.abs(np.diff(g, axis=1))[:-1]
        sc.append(float((e * m[:-1, :-1]).sum() / max(1, m.sum())))
        sheet.paste(Image.fromarray(rgb[i, y0:y1, x0:x1]).resize((tw_, th), Image.LANCZOS), (tw_ * i, 26))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(fs):
        tag = f'f{f}  sharp {sc[i]:.1f}' + ('  <- sharpest' if sc[i] == max(sc) else '') + ('  (F_FREEZE)' if f == F else '')
        d.text((tw_ * i + 6, 7), tag, fill=(255, 235, 90) if f == F else (230, 230, 230))
    sheet.save('work/frames.jpg', quality=90)
    print('frame  sharpness (higher = less motion blur)')
    for f, s in zip(fs, sc):
        print(f'f{f:4d}  {s:6.2f}' + ('   <- F_FREEZE' if f == F else '') + ('   <- sharpest' if s == max(sc) else ''))
    print('sheet: work/frames.jpg  (eyes open? mouth not mid-word in an odd shape? hands not smeared? then keep it)')
    sys.exit(0)

# ------------------------------------------------------------------ the outline
rgb = grab('assets/aroll.mp4', [F], 'rgb24')[0].astype(np.float32) / 255
al = grab('assets/subject.webm', [F], 'gray', VP9, ',alphaextract')[0, ..., 0]
m = al > 127
lab, n = ndimage.label(m)
if n == 0 or m.sum() < 0.01 * W * H:
    sys.exit(f'the cutout is (nearly) empty on frame {F}: no speaker to make a sticker of')
sizes = ndimage.sum(m, lab, range(1, n + 1))
main = lab == 1 + int(np.argmax(sizes))
lost = (m.sum() - main.sum()) / main.sum()
if lost > .02:
    say(f'{lost * 100:.0f}% of the cutout is not joined to the body on this frame (a hand in the air? a second person?): '
        'it is left out of the sticker. Pick a frame where it touches the body, or accept it')
holes = ndimage.binary_fill_holes(main) & ~main
hl, hn = ndimage.label(holes)
if hn:
    hs = ndimage.sum(holes, hl, range(1, hn + 1))
    small = np.isin(hl, 1 + np.where(hs < .004 * main.sum())[0])
    if small.any():
        print(f'filled {int((hs < .004 * main.sum()).sum())} small hole(s) in the cutout ({int(small.sum())} px)')
    main |= small
CUT_Y = C['CUT_Y']
if CUT_Y is not None:
    CUT_Y = int(CUT_Y)
    main[CUT_Y:] = False
    for r in range(max(0, CUT_Y - 70), CUT_Y):          # one straight base: fill the dips (between the legs, under an arm)
        xs_ = np.where(main[r])[0]
        if len(xs_):
            main[r, xs_.min():xs_.max() + 1] = True
if not main.any():
    sys.exit('CUT_Y is above the speaker: nothing left')
edge_px = {'top': int(main[0].sum()), 'bottom': int(main[H - 1].sum()), 'left': int(main[:, 0].sum()), 'right': int(main[:, W - 1].sum())}
cuts = {k for k, v in edge_px.items() if v > 12}
if CUT_Y is not None:
    cuts.discard('bottom')
smooth = edt(edt(~main) <= 8) > 8                       # close 8 px, then open 8 px: the outline without its dents
smooth = edt(~(edt(smooth) > 8)) <= 8
per = lambda b: max(1, int((b & ~ndimage.binary_erosion(b)).sum()))
ragged = per(main) / per(smooth)
print(f'outline: {int(main.sum())} px, raggedness {ragged:.2f} (1.0 = smooth, over 1.35 = torn), '
      f'cut by the frame: {", ".join(sorted(cuts)) or "nowhere"}')
if ragged > 1.35:
    say(f'the outline is ragged ({ragged:.2f}): the cutout lost hair, fingers or a sleeve on this frame. The white border '
        'smooths small dents, big ones show. Try a frame 2 to 5 earlier or later, or accept it after looking at work/check.jpg')
if 'bottom' in cuts:
    print('  the body runs off the bottom of the frame (normal): that cut edge is kept below the screen, no border on it')
for side in ('left', 'right', 'top'):
    if side in cuts:
        say(f'the speaker is cut by the {side} edge of the frame ({edge_px[side]} px): that edge gets no border and is kept '
            'off screen, which limits how small the sticker can be' if side != 'top' else
            'the head is cut by the top of the frame: the sticker will have a flat top. Use footage with air above the head')

# ------------------------------------------------------------------ the head (for sizing and for keeping ink off the face)
ys_all = np.where(main.any(1))[0]
ytop, ybot = int(ys_all[0]), int(ys_all[-1])
xc = float(np.where(main[ytop])[0].mean())
runs = []
for y in range(ytop, ybot + 1):
    idx = np.where(main[y])[0]
    if not len(idx):
        break
    br = np.where(np.diff(idx) > 3)[0]
    st, en = np.r_[idx[0], idx[br + 1]], np.r_[idx[br], idx[-1]]
    k = int(np.argmin(np.where((st <= xc) & (en >= xc), 0, np.minimum(np.abs(st - xc), np.abs(en - xc)))))
    runs.append((int(st[k]), int(en[k])))
    xc = .8 * xc + .2 * (st[k] + en[k]) / 2
wid = ndimage.uniform_filter1d(np.array([b - a + 1 for a, b in runs], float), 9, mode='nearest')
mx, ym, dipped, shoulders = 0.0, 0, False, None
for i, v in enumerate(wid):
    if v >= mx:
        if dipped or (mx > 0 and i > 1.1 * mx and v > 1.25 * mx):
            shoulders = i
            break
        mx, ym = v, i
    elif v < .88 * mx:
        dipped = True
if C['HEAD']:
    hy0, hy1 = int(C['HEAD'][0]), int(C['HEAD'][1])
    xs_ = np.where(main[hy0:hy1].any(0))[0]
    hx0, hx1 = int(xs_.min()), int(xs_.max())
else:
    hy0 = ytop
    if dipped:
        end = shoulders if shoulders is not None else len(wid)
        hy1 = min(ybot, max(ytop + ym + int(np.argmin(wid[ym:end])), ytop + int(1.3 * mx)))   # a hand by the jaw hides the neck
    else:
        hy1 = min(ybot, ytop + int(1.35 * mx))
        say('no neck found under the head (hood, long hair, a hand by the face?): the head box is a guess. Check the green '
            'box on work/check.jpg and set HEAD = (top_y, chin_y) if it is off')
    hx0, hx1 = runs[ym]
hh, hcx = max(40, hy1 - hy0), (hx0 + hx1) / 2

# ------------------------------------------------------------------ where the sticker sits and how big it is
tilt = C['TILT']
if not isinstance(tilt, (int, float)):
    tilt = 4.0 if ('right' in cuts and 'left' not in cuts) else -4.0     # lean away from a cut side
th = math.radians(tilt)
co, si = math.cos(th), math.sin(th)


def xf(pts, S, A, T):
    d = np.asarray(pts, float).reshape(-1, 2) - A
    return np.stack([A[0] + T[0] + S * (co * d[:, 0] - si * d[:, 1]), A[1] + T[1] + S * (si * d[:, 0] + co * d[:, 1])], 1)


ey, ex = np.where(main & ~ndimage.binary_erosion(main))
outline = np.stack([ex, ey], 1)[::5].astype(float)
bleed = 'bottom' in cuts
bw, bh = ex.max() - ex.min(), ey.max() - ey.min()
fixed = isinstance(C['SIZE'], (int, float))
if bleed:
    A = np.array([float(np.where(main[H - 1])[0].mean()), float(H)])
    S = (H + 10 - TOP) / max(200.0, H - hy0)
    S = min(max(S, min(1.3, 200 / hh), .62), 1.3)
else:
    A = np.array([(ex.min() + ex.max()) / 2, (ey.min() + ey.max()) / 2])
    S = min(1.3, 900 / bw, 800 / bh)
if fixed:
    S = float(C['SIZE'])
for _ in range(16):
    T = np.zeros(2)
    o = xf(outline, S, A, T)
    if bleed:
        T[1] = TOP - xf([hcx, hy0], S, A, T)[0, 1]
        b = xf(np.stack([np.where(main[H - 1])[0], np.full(edge_px['bottom'], H - 1)], 1), S, A, T)[:, 1].min()
        T[1] += max(0, H + 4 - b)
        T[0] = 540 - xf([hcx, (hy0 + hy1) / 2], S, A, T)[0, 0]
    else:
        T[1] = 1440 - o[:, 1].max()
        T[0] = 540 - (o[:, 0].min() + o[:, 0].max()) / 2
    lo, hi = o[:, 0].min() + T[0], o[:, 0].max() + T[0]
    if not cuts & {'left', 'right'}:
        if hi - lo > W - 70:
            T[0] += 540 - (lo + hi) / 2
        elif lo < 35:
            T[0] += 35 - lo
        elif hi > W - 35:
            T[0] -= hi - (W - 35)
    if 'left' in cuts:
        v = xf(np.stack([np.zeros(edge_px['left']), np.where(main[:, 0])[0]], 1), S, A, T)[:, 0].max()
        T[0] -= max(0, v + 4)
    if 'right' in cuts:
        v = xf(np.stack([np.full(edge_px['right'], W - 1), np.where(main[:, W - 1])[0]], 1), S, A, T)[:, 0].min()
        if v < W + 4:
            if 'left' in cuts and not fixed:
                S *= 1.03                      # cut on both sides: the sticker cannot be narrower than the screen
                continue
            if 'left' in cuts:
                say('SIZE is too small to hide both cut sides: a straight cut edge shows at the right')
            else:
                T[0] += W + 4 - v
    break
T += np.array(C['PLACE'], float)
head_s = xf([[hx0, hy0], [hx1, hy0], [hx0, hy1], [hx1, hy1]], S, A, T)
HX0, HY0, HX1, HY1 = head_s[:, 0].min(), head_s[:, 1].min(), head_s[:, 0].max(), head_s[:, 1].max()
HCX, HCY = (HX0 + HX1) / 2, (HY0 + HY1) / 2
print(f'head (a-roll px): x {hx0} to {hx1}, y {hy0} to {hy1}.  sticker: size {S:.2f}, tilt {tilt:+.0f} deg, '
      f'{"runs off the bottom of the screen" if bleed else "floats whole"}, head on screen y {HY0:.0f} to {HY1:.0f}')
if HY1 > 1470:
    say('the face reaches below y 1470 (covered by the app): lower SIZE or move it up with PLACE')
if (HY1 - HY0) > 760:
    say('very tight close-up: the head fills the screen, little room for notes. Use one short note or wider footage')

# ------------------------------------------------------------------ bake: die-cut border, photo, shadow
BORDER, CLOSE, CHOKE = C['BORDER'] / S, 14 / S, float(C['CHOKE'])
binm = np.pad(main, PAD, mode='edge')
for side, sl in (('top', np.s_[:PAD]), ('bottom', np.s_[-PAD:]), ('left', np.s_[:, :PAD]), ('right', np.s_[:, -PAD:])):
    if side not in cuts:
        binm[sl] = False
RGB = np.pad(rgb, ((PAD, PAD), (PAD, PAD), (0, 0)), mode='edge')
d_sub = edt(binm)
sub = ndimage.gaussian_filter(np.clip((d_sub - CHOKE) / 1.5, 0, 1), .7)          # the photo: choked, 1 px feather
grown = ndimage.binary_fill_holes(edt(~binm) <= BORDER + CLOSE)                  # grow, fill, shrink back: dents close
cut = ndimage.gaussian_filter(np.clip(edt(grown) - CLOSE + .5, 0, 1), .6)
paper = np.array([1.0, .995, .985], np.float32)
edge = cut * np.clip(1 - edt(cut > .5) / 2.5, 0, 1)                              # hairline at the outer edge
col = np.ones_like(RGB) * paper * (1 - edge[..., None] * .10)
col = col * (1 - np.clip(ndimage.gaussian_filter(sub, 3.0) - sub, 0, 1)[..., None] * .35)   # print shade at the photo
col = RGB * sub[..., None] + col * (1 - sub[..., None])
alpha = np.maximum(cut, sub)
ys, xs = np.where(alpha > .004)
y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
stk = Image.fromarray((np.clip(np.dstack([col, alpha])[y0:y1, x0:x1], 0, 1) * 255 + .5).astype(np.uint8), 'RGBA')
stk.save('assets/sticker/sticker.png')
sh = ndimage.gaussian_filter(cut, 16 / S)
sy, sx = np.where(sh > .004)
sy0, sy1, sx0, sx1 = sy.min(), sy.max() + 1, sx.min(), sx.max() + 1
shimg = np.zeros((sy1 - sy0, sx1 - sx0, 4), np.float32)
shimg[..., :3] = (.04, .05, .10)
shimg[..., 3] = sh[sy0:sy1, sx0:sx1]
Image.fromarray((shimg * 255 + .5).astype(np.uint8), 'RGBA').save('assets/sticker/shadow.png')
frame_img = Image.fromarray((rgb * 255).astype(np.uint8))
if C['BACKDROP'] == 'footage':
    bk = frame_img.resize((W // 2, H // 2)).filter(ImageFilter.GaussianBlur(16)).resize((W, H), Image.BICUBIC)
    Image.fromarray((np.asarray(bk).astype(np.float32) * .5).astype(np.uint8)).save('assets/sticker/back.jpg', quality=86)
elif C['BACKDROP'] != 'page':
    sys.exit("BACKDROP is 'page' or 'footage'")


def rgb_of(hexs):
    hexs = hexs.lstrip('#')
    return tuple(int(hexs[i:i + 2], 16) for i in (0, 2, 4))


pr, pg, pb = (v / 255 for v in rgb_of(C['PAGE']))
mxc, mnc = max(pr, pg, pb), min(pr, pg, pb)
sat = 0 if mxc == 0 else (mxc - mnc) / mxc
if C['BACKDROP'] == 'page':
    if sat < .18:
        say('PAGE is a grey: the rule is no black and white. Pick a colour')
    elif pr == mxc and pg > pb and .25 < (pg - pb) / (mxc - mnc) < .75:
        say('PAGE is an orange: the rule is no orange. Pick another colour')


# ------------------------------------------------------------------ the sticker on the screen grid (for the layout)
def coeffs(g):
    k = g / 2 - A - T
    return (co * g / S, si * g / S, PAD + A[0] + (co * k[0] + si * k[1]) / S,
            -si * g / S, co * g / S, PAD + A[1] + (-si * k[0] + co * k[1]) / S)


gw, gh = W // G, H // G
stk_q = np.asarray(Image.fromarray((cut * 255).astype(np.uint8)).transform((gw, gh), Image.AFFINE, coeffs(G), Image.BILINEAR)) > 60
safe = np.zeros((gh, gw), bool)
safe[(220 + 14) // G:(1470 - 14) // G, (35 + 14) // G:(W - 35 - 14) // G] = True
safe[1155 // G:, (W - 100 - 14) // G:] = False
occ = (edt(~stk_q) <= 30 / G) | ~safe
near = edt(~stk_q) <= 14 / G

_fonts = {}


def tw(s, size):
    if size not in _fonts:
        try:
            _fonts[size] = ImageFont.truetype(FONT, size)
        except Exception:
            _fonts[size] = None
    f = _fonts[size]
    return f.getlength(s) if f else .40 * size * len(s)


def tokens(text):
    out, em = [], False
    for part in re.split(r'(\*)', text):
        if part == '*':
            em = not em
        else:
            out += [(w, em) for w in part.split()]
    return out


def wraps(tok, nl):
    n_ = len(tok)
    if nl == 1:
        return [[tok]]
    if nl == 2:
        return [[tok[:i], tok[i:]] for i in range(1, n_)]
    return [[tok[:i], tok[i:j], tok[j:]] for i in range(1, n_) for j in range(i + 1, n_)]


def side_cost(side, cx, cy, w, h):
    if side == 'top':
        return np.abs(cx - 540) * .6 + np.abs(cy + h / 2 - (HY0 - 46)), cy + h / 2 > HY0 - 8
    if side == 'left':
        return np.hypot(cx + w / 2 - (HX0 - 40), cy - HCY), cx + w / 2 > HX0
    return np.hypot(cx - w / 2 - (HX1 + 40), cy - HCY), cx - w / 2 < HX1


def place(tok, side, cap, extra_top, floor_y):
    """biggest handwriting that has a clear box on its side: (x, y, w, h, size, lines) in screen px, or None"""
    sides = ('top', 'left', 'right') if side == 'auto' else (side,)
    ii = np.zeros((gh + 1, gw + 1), np.int32)
    ii[1:, 1:] = occ.cumsum(0).cumsum(1)
    fallback = None
    for size in range(cap, MINS - 1, -6):
        for nl in range(1, min(3, len(tok)) + 1):
            best = None
            for lines in wraps(tok, nl):
                ws_ = [tw(' '.join(w for w, _ in ln), size) for ln in lines]
                key = (round(max(ws_) / 12), max(ws_) - min(ws_))        # narrowest block, then the most even lines
                if best is None or key < best[0]:
                    best = (key, max(ws_), lines)
            _, tw_, lines = best
            w, h = tw_ + 28, nl * size * .92 + extra_top * size + .06 * tw_ + 14
            cw, ch = math.ceil(w / G), math.ceil(h / G)
            if cw >= gw or ch >= gh:
                continue
            room = (ii[ch:, cw:] - ii[:-ch, cw:] - ii[ch:, :-cw] + ii[:-ch, :-cw]) == 0
            if not room.any():
                continue
            yy, xx = np.mgrid[0:room.shape[0], 0:room.shape[1]]
            cx, cy = xx * G + w / 2, yy * G + h / 2
            cost = np.full(room.shape, 1e9)
            for s_ in sides:
                c_, bad = side_cost(s_, cx, cy, w, h)
                bad = bad | (cy + h / 2 <= floor_y)          # a later note never sits above an earlier one (reading order)
                cost = np.minimum(cost, np.where(bad, 1e9, c_))
            cost = np.where(room, cost, 2e9)
            k = np.unravel_index(int(np.argmin(cost)), cost.shape)
            if cost[k] < 1e9:
                return (int(k[1] * G), int(k[0] * G), int(w), int(h), size, lines)
            if fallback is None:                      # room, but not on the side asked for
                d2 = np.where(room, np.hypot(cx - HCX, cy - HCY), 2e9)
                k = np.unravel_index(int(np.argmin(d2)), d2.shape)
                fallback = (int(k[1] * G), int(k[0] * G), int(w), int(h), size, lines)
    return fallback


CAPS_ON = [(t, f, s) for t, f, s in C['NOTES'] if t and t.strip()]
stamp = (C['STAMP'] or '').strip()
occ0 = occ.copy()
notes = []
for attempt in range(4):
    occ, notes, ok = occ0.copy(), [], True
    for i, (text, fr, side) in enumerate(CAPS_ON):
        cap = int((MAXS if i == 0 else MAXS * .72) * (.85 ** attempt))
        p = place(tokens(text), side, cap, .62 if (stamp and i == 0) else 0, max([n_['y'] + n_['h'] for n_ in notes], default=-1))
        if p is None:
            ok = False
            continue
        x, y, w, h, size, lines = p
        occ[max(0, (y - 20) // G):(y + h + 20) // G + 1, max(0, (x - 20) // G):(x + w + 20) // G + 1] = True
        notes.append({'i': i, 'x': x, 'y': y, 'w': w, 'h': h, 'size': size, 'lines': lines, 'frame': fr,
                      'rot': (-3, 2, -2, 3)[i % 4], 'stamp': stamp if i == 0 else ''})
    if ok:
        break
for i, (text, fr, side) in enumerate(CAPS_ON):
    nn = [n_ for n_ in notes if n_['i'] == i]
    if not nn:
        say(f'no room for note {i + 1} ("{text}"): shorten it, drop it, or make the sticker smaller with SIZE')
    else:
        n_ = nn[0]
        cxn = n_['x'] + n_['w'] / 2
        got = 'top' if n_['y'] + n_['h'] <= HY0 else ('left' if cxn < HCX else 'right')
        if side != 'auto' and got != side:
            say(f'note {i + 1} had no room on the {side}: it sits {got}')
        print(f'note {i + 1}: {n_["size"]} px, {len(n_["lines"])} line(s), box x {n_["x"]} to {n_["x"] + n_["w"]}, y {n_["y"]} to {n_["y"] + n_["h"]}')

# ------------------------------------------------------------------ doodles: arrow from the first note, ticks by the head
arrow, ticks = None, []


def in_boxes(px, py, skip=None, grow=10):
    return any(n_ is not skip and n_['x'] - grow <= px <= n_['x'] + n_['w'] + grow and n_['y'] - grow <= py <= n_['y'] + n_['h'] + grow
               for n_ in notes)


def is_safe(px, py):
    return 0 <= int(py) // G < gh and 0 <= int(px) // G < gw and bool(safe[int(py) // G, int(px) // G])


if C['ARROW'] and notes and notes[0]['i'] == 0:
    n0 = notes[0]
    by, bx = np.where(stk_q & ~ndimage.binary_erosion(stk_q))
    pts = np.stack([bx * G + G / 2, by * G + G / 2], 1)
    ok = np.array([py > HY1 + 24 and is_safe(px, py) for px, py in pts]) if len(pts) else np.zeros(0, bool)
    if ok.any():
        pts = pts[ok]
        ctr = np.array([n0['x'] + n0['w'] / 2, n0['y'] + n0['h'] / 2])
        tgt = pts[int(np.argmin(np.hypot(*(pts - ctr).T)))]
        st = np.array([min(max(tgt[0], n0['x'] + 30), n0['x'] + n0['w'] - 30), min(max(tgt[1], n0['y']), n0['y'] + n0['h'])])
        st += (tgt - st) / max(1, np.hypot(*(tgt - st))) * 14
        en = tgt + (st - tgt) / max(1, np.hypot(*(st - tgt))) * 30
        ln = np.hypot(*(en - st))
        perp = np.array([-(en - st)[1], (en - st)[0]]) / max(1, ln)
        for sgn in sorted((1, -1), key=lambda s_: -np.hypot(*((st + en) / 2 + perp * s_ * .24 * ln - (HCX, HCY)))):
            ct = (st + en) / 2 + perp * sgn * .24 * ln
            cur = [(1 - t) ** 2 * st + 2 * t * (1 - t) * ct + t * t * en for t in np.linspace(.08, 1, 14)]
            clear = all(not (HX0 - 16 <= px <= HX1 + 16 and HY0 - 16 <= py <= HY1 + 16) and not in_boxes(px, py, skip=n0, grow=6)
                        and is_safe(px, py) for px, py in cur)
            if ln >= 110 and clear:
                tg = (en - ct) / max(1, np.hypot(*(en - ct)))
                hd = []
                for a_ in (math.radians(152), math.radians(-152)):
                    hd.append(en + 42 * np.array([tg[0] * math.cos(a_) - tg[1] * math.sin(a_), tg[0] * math.sin(a_) + tg[1] * math.cos(a_)]))
                arrow = {'d': f'M{st[0]:.0f} {st[1]:.0f} Q {ct[0]:.0f} {ct[1]:.0f}, {en[0]:.0f} {en[1]:.0f}',
                         'head': f'M{hd[0][0]:.0f} {hd[0][1]:.0f} L {en[0]:.0f} {en[1]:.0f} L {hd[1][0]:.0f} {hd[1][1]:.0f}',
                         'poly': [[float(st[0]), float(st[1])]] + [[float(p_[0]), float(p_[1])] for p_ in cur]}
                break
    if arrow is None:
        print('  (no clear path for the arrow from the first note to the body: no arrow drawn)')
if C['TICKS']:
    left_side = not (notes and notes[0]['x'] + notes[0]['w'] / 2 < HCX and notes[0]['y'] + notes[0]['h'] > HY0)
    for deg in ((-152, -134, -116) if left_side else (-28, -46, -64)):
        dx, dy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        r = 0
        while r < 900:
            px, py = HCX + dx * r, HCY + dy * r
            if not (0 <= px < W and 0 <= py < H) or not near[int(py) // G, int(px) // G]:
                break
            r += 4
        p0, p1 = (HCX + dx * (r + 8), HCY + dy * (r + 8)), (HCX + dx * (r + 54), HCY + dy * (r + 54))
        if all(is_safe(*p_) and not in_boxes(*p_) for p_ in (p0, p1)):
            ticks.append(f'M{p0[0]:.0f} {p0[1]:.0f} L {p1[0]:.0f} {p1[1]:.0f}')

# ------------------------------------------------------------------ write
meta = {'sig': hashlib.sha1((block + str(N)).encode()).hexdigest(), 'frame': F, 'S': round(S, 4), 'tilt': tilt,
        'A': [round(float(A[0]), 1), round(float(A[1]), 1)], 'T': [round(float(T[0]), 1), round(float(T[1]), 1)],
        'pivot': [round(float(hcx), 1), float(hy1)], 'bleed': bleed, 'cuts': sorted(cuts), 'ragged': round(ragged, 3),
        'sticker': {'left': int(x0 - PAD), 'top': int(y0 - PAD), 'w': int(x1 - x0), 'h': int(y1 - y0)},
        'shadow': {'left': int(sx0 - PAD), 'top': int(sy0 - PAD), 'w': int(sx1 - sx0), 'h': int(sy1 - sy0)},
        'head': [int(hx0), int(hy0), int(hx1), int(hy1)], 'head_screen': [round(float(v)) for v in (HX0, HY0, HX1, HY1)],
        'notes': notes, 'arrow': arrow, 'ticks': ticks, 'warnings': warn}
json.dump(meta, open('assets/sticker/sticker.json', 'w'), indent=1)

# check sheet, half size: page, sticker in its pose, safe zone (red), head (green), note boxes (yellow)
g = 2
if C['BACKDROP'] == 'footage':
    sheet = Image.open('assets/sticker/back.jpg').resize((W // g, H // g))
else:
    sheet = Image.new('RGB', (W // g, H // g), rgb_of(C['PAGE']))
full = Image.fromarray((np.clip(np.dstack([col, alpha]), 0, 1) * 255).astype(np.uint8), 'RGBA')
sheet.paste(full.transform((W // g, H // g), Image.AFFINE, coeffs(g), Image.BILINEAR), (0, 0),
            full.getchannel('A').transform((W // g, H // g), Image.AFFINE, coeffs(g), Image.BILINEAR))
d = ImageDraw.Draw(sheet)
for box in ((35, 220, W - 35, 1470), (W - 100, 1155, W - 35, 1470)):
    d.rectangle([v // g for v in box], outline=(255, 40, 40), width=2)
d.rectangle([int(v) // g for v in (HX0, HY0, HX1, HY1)], outline=(60, 255, 90), width=2)
for n_ in notes:
    d.rectangle([n_['x'] // g, n_['y'] // g, (n_['x'] + n_['w']) // g, (n_['y'] + n_['h']) // g], outline=(255, 235, 90), width=2)
    try:
        f_ = ImageFont.truetype(FONT, n_['size'] // g)
    except Exception:
        f_ = None
    top = n_['y'] + (.62 * n_['size'] if n_['stamp'] else 0) + .03 * n_['w']
    for k, ln in enumerate(n_['lines']):
        d.text(((n_['x'] + 14) // g, (top + k * n_['size'] * .92) // g), ' '.join(w for w, _ in ln), fill=(255, 255, 255), font=f_)
if arrow:
    d.line([(px / g, py / g) for px, py in arrow['poly']], fill=(255, 255, 255), width=3)
sheet.save('work/check.jpg', quality=88)
print(f'baked frame {F}: assets/sticker/  |  layout: work/check.jpg (red = safe zone, green = head, yellow = note boxes)')
print(f'{len(warn)} warning(s).  next: python3 build.py')
