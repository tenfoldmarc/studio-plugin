#!/usr/bin/env python3
"""clone / bake: the pixel layers. Config comes from the CLIP block in build.py, measurements from prep.py.

    PY bake.py        (2 to 4 min for a 5 s slot; heavy: one at a time)

Writes
  assets/fg.webm          the speaker (RVM alpha, tightened) UNION everything below the furniture edge -> the clones can stand
                          BEHIND the furniture. The edge = OCCLUDER_LINE snapped per column to the real edge on a clean
                          plate, then moved with the camera drift.
  assets/clone_<id>.webm  their cutout from frame (i - lag), scaled, placed, locked to the room (drift removed at the
                          source frame, re-applied at the output frame), a touch softer, darkened where the real speaker
                          stands in front, with a soft shadow on the wall behind. Cropped to build.canvas(c).
  work/track.json         camera drift per frame (px), work/bake.json per-frame visible extents of every clone,
  work/bake_debug/        occluder overlay + clean plate to look at when something is off.

Steps: (1) camera drift on the band of the picture the clones live in (masked translation Lucas-Kanade, numpy only);
(2) clean plate of the room = mean of the frames where the speaker is not on a pixel; it is used to cap RVM's alpha on
motion-blurred hands (RVM calls them opaque: over the plate nobody sees it, over a clone it is a pale smear) and to
un-mix the true colour of their edge pixels, applied in fg.webm ONLY where a clone sits behind the speaker, so everywhere else
fg over the plate stays pixel-identical to the source; (3) the layers.
"""
import json
import os
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

import build as C

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H = 1080, 1920
N = C.N
M = C.M
if M is None or not os.path.exists(os.path.join(HERE, 'work/alpha_half.npy')):
    raise SystemExit('run prep.py first (work/measure.json, work/alpha_half.npy)')
AX, AY = M['anchor']
SRC_CUT = dict(l=M['src_x'][0] <= 3, r=M['src_x'][1] >= W - 4)      # is the real speaker cut by the frame edge?

# ---- tuning (same for every clip) -----------------------------------------------------------------------------------
SGN = -1 if C.LIGHT_FROM == 'right' else 1      # shadows fall away from the light
MAIN_SHADOW = .42                # how much the real speaker darkens a clone right behind the speaker
MAIN_SHADOW_OFF = (14 * SGN, 8)
WALL_SHADOW = .24                # the clone's own shadow on the wall
WALL_SHADOW_OFF = (10 * SGN, 9)
SOFT = .75                       # source blur (px) before the down-scale: anti-alias + "a bit further back"
EDGE_SEARCH = 14                 # px above / below OCCLUDER_LINE the real furniture edge is looked for
EDGE_RAMP = 3.0                  # softness of the occluder edge, px


def tighten(a, lo, hi):
    return np.clip((a - lo) / (hi - lo), 0, 1)


def shift2(a, dx, dy):
    """integer shift with zero fill"""
    out = np.zeros_like(a)
    h, w = a.shape[:2]
    xs0, xs1 = max(0, -dx), min(w, w - dx)
    ys0, ys1 = max(0, -dy), min(h, h - dy)
    out[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx] = a[ys0:ys1, xs0:xs1]
    return out


def reader(args):
    return subprocess.Popen([FF, '-loglevel', 'error'] + args + ['-f', 'rawvideo', '-'], stdout=subprocess.PIPE)


def writer(path, w, h, crf):
    return subprocess.Popen([FF, '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{w}x{h}', '-r', '30', '-i', '-',
                             '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', str(crf), '-g', '15', '-auto-alt-ref', '0',
                             '-row-mt', '1', '-cpu-used', '3', '-metadata:s:v:0', 'alpha_mode=1', path], stdin=subprocess.PIPE)


def blur_full(a, sigma):
    """cheap big blur of a full-frame float map: quarter res gaussian"""
    im = Image.fromarray((a * 255).astype(np.uint8)).resize((W // 4, H // 4), Image.BILINEAR)
    im = im.filter(ImageFilter.GaussianBlur(sigma / 4)).resize((W, H), Image.BILINEAR)
    return np.asarray(im, np.float32) / 255


# ---- 1. camera drift -------------------------------------------------------------------------------------------------
def track_drift(A):
    """Translation of the room relative to frame 0, per frame, in full-res px: a room point at p in frame 0 sits at
    p + TR[f] in frame f. Measured only on the band the clones live in (their heads down to just under the furniture
    edge), with the speaker masked out, so a table edge or a rug at the lens cannot bias it."""
    hw, hh = W // 2, H // 2
    raw = subprocess.run([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-vf', f'scale={hw}:{hh}:flags=area',
                          '-pix_fmt', 'gray', '-f', 'rawvideo', '-'], capture_output=True).stdout
    G = np.frombuffer(raw, np.uint8).reshape(-1, hh, hw)
    person = ndimage.binary_dilation((A > 8).any(axis=0), iterations=15)
    ya = int(max(0, min(c['top'] for c in C.CLONES) - 150) // 2)
    yb = int(min(H, max(y for _, y in C.OCCLUDER_LINE) + 120) // 2)
    mask = ~person
    mask[:ya] = False
    mask[yb:] = False
    mask[:, :12] = False
    mask[:, -12:] = False
    if mask.mean() < .03:
        print('!! track: almost nothing of the room is free of the speaker in the clone band; using the whole frame')
        mask = ~person
        mask[:12] = mask[-12:] = False
        mask[:, :12] = mask[:, -12:] = False
    w0 = mask.astype(np.float32)
    ref = ndimage.gaussian_filter(G[0].astype(np.float32), 1.2)
    gy, gx = np.gradient(ref)
    ref0 = ref - (ref * w0).sum() / w0.sum()
    d = np.zeros(2)
    out = [[0.0, 0.0]]
    for f in range(1, len(G)):
        cur = ndimage.gaussian_filter(G[f].astype(np.float32), 1.2)
        for _ in range(15):
            wp = ndimage.shift(cur, (-d[1], -d[0]), order=1, mode='nearest')
            r = (wp - (wp * w0).sum() / w0.sum()) - ref0
            w = w0 / (1 + (r / 10) ** 2)                      # robust: lighting flicker, the speaker's shadow on the wall
            a11, a12, a22 = (w * gx * gx).sum(), (w * gx * gy).sum(), (w * gy * gy).sum()
            lam = 1e-3 * (a11 + a22) + 1e-6
            det = (a11 + lam) * (a22 + lam) - a12 * a12
            b1, b2 = -(w * gx * r).sum(), -(w * gy * r).sum()
            step = np.array([((a22 + lam) * b1 - a12 * b2) / det, ((a11 + lam) * b2 - a12 * b1) / det])
            d = d + step
            if np.abs(step).max() < 2e-3:
                break
        out.append([float(d[0] * 2), float(d[1] * 2)])
    TR = ndimage.gaussian_filter1d(np.array(out), 1.2, axis=0, mode='nearest')
    json.dump([[round(float(x), 3), round(float(y), 3)] for x, y in TR], open(os.path.join(HERE, 'work/track.json'), 'w'))
    span = np.abs(TR).max(axis=0)
    print(f'camera drift: up to {span[0]:.1f} px sideways, {span[1]:.1f} px vertical over the clip'
          + ('   !! more than 40 px: this effect wants a still camera, check the result' if span.max() > 40 else ''), flush=True)
    return TR


# ---- 2. clean plate, occluder, alpha / colour clean-up ----------------------------------------------------------------
def clean_plate(TR):
    """The room without the speaker, in frame-0 coordinates: per pixel the mean of every (second) frame where their dilated
    matte is empty. Pixels the speaker covers the whole clip stay invalid."""
    dec_a = reader(['-i', os.path.join(HERE, 'assets/aroll.mp4'), '-pix_fmt', 'rgb24'])
    dec_s = reader(['-c:v', 'libvpx-vp9', '-i', os.path.join(HERE, 'assets/subject.webm'), '-vf', 'alphaextract', '-pix_fmt', 'gray'])
    acc = np.zeros((H, W, 3), np.float32)
    cnt = np.zeros((H, W), np.float32)
    aq = []                                  # quarter-res alpha of every frame (to know where the speaker is MOVING)
    for i in range(N):
        rgb = np.frombuffer(dec_a.stdout.read(W * H * 3), np.uint8).reshape(H, W, 3)
        a = np.frombuffer(dec_s.stdout.read(W * H), np.uint8).reshape(H, W)
        aq.append(a[::4, ::4].copy())
        if i % 2:
            continue
        free = ~ndimage.binary_dilation(a > 5, iterations=7)
        dx, dy = int(round(-TR[i][0])), int(round(-TR[i][1]))
        free = shift2(free, dx, dy)
        acc += shift2(rgb, dx, dy) * free[..., None]
        cnt += free
    dec_a.wait(); dec_s.wait()
    B = acc / np.maximum(cnt, 1)[..., None]
    Image.fromarray(B.astype(np.uint8)).resize((540, 960)).save(os.path.join(HERE, 'work/bake_debug/clean_plate.jpg'))
    return B, cnt >= 2, aq


def occluder_matte(B0, valid0, frame0):
    """1 below the furniture edge, 0 above it, in frame-0 coordinates. Every column the clean plate knows is snapped
    to the strongest light/dark step within EDGE_SEARCH px of OCCLUDER_LINE; the columns the speaker always covers follow the
    hand-drawn line, shifted by what the neighbouring columns measured."""
    lum = ndimage.gaussian_filter(B0.mean(axis=2), 1.0)
    grad = np.gradient(lum, axis=0)
    xs = np.arange(W)
    rough = np.array([C.line_y(x) for x in xs], np.float32)

    def pick(sign):
        e = np.full(W, np.nan, np.float32)
        s = np.zeros(W, np.float32)
        for x in xs:
            y0, y1 = int(max(1, rough[x] - EDGE_SEARCH)), int(min(H - 1, rough[x] + EDGE_SEARCH + 1))
            if not valid0[y0:y1, x].all():
                continue
            g = grad[y0:y1, x] * sign if sign else np.abs(grad[y0:y1, x])
            k = int(np.argmax(g))
            if g[k] < 2.5:
                continue
            dlt = 0.
            if 0 < k < len(g) - 1:
                den = g[k - 1] - 2 * g[k] + g[k + 1]
                dlt = float(np.clip(.5 * (g[k - 1] - g[k + 1]) / den, -1, 1)) if abs(den) > 1e-6 else 0.
            e[x] = y0 + k + dlt
            s[x] = grad[y0 + k, x]
        return e, s

    e, s = pick(0)
    ok = ~np.isnan(e)
    if ok.sum() < 20:
        print('!! occluder: the clean plate shows almost none of the furniture edge; using OCCLUDER_LINE as drawn')
        e = rough.copy()
    else:
        sign = 1.0 if np.median(s[ok]) > 0 else -1.0          # light wall over dark furniture, or the reverse
        e, s = pick(sign)
        ok = ~np.isnan(e)
        off = e - rough
        idx = xs[ok]
        med = ndimage.median_filter(off[idx], 31, mode='nearest')
        ok[idx[np.abs(off[idx] - med) >= 7]] = False          # a column that jumped to some other edge
        off_all = np.interp(xs, xs[ok], off[ok])
        off_all = ndimage.median_filter(off_all, 5, mode='nearest')
        e = rough + off_all
        print(f'occluder edge snapped on {int(ok.sum())} of {W} columns; correction to the drawn line: '
              f'median {np.median(off[ok]):+.1f} px, max {np.abs(off[ok]).max():.1f} px'
              + ('   !! large: re-read the points from the grid frame' if np.abs(off[ok]).max() > EDGE_SEARCH - 2 else ''))
    yy = np.arange(H, dtype=np.float32)[:, None]
    m = np.clip((yy - e[None, :]) / EDGE_RAMP + .5, 0, 1).astype(np.float32)
    dbg = frame0.astype(np.float32)
    dbg[..., 0] = dbg[..., 0] * (1 - .5 * m) + 255 * .5 * m
    ya, yb = int(max(0, e.min() - 260)), int(min(H, e.max() + 160))
    Image.fromarray(dbg.astype(np.uint8)).crop((0, ya, W, yb)).save(os.path.join(HERE, 'work/bake_debug/occluder_overlay.jpg'), quality=90)
    return m


def refine_alpha(a, rgb, B, valid, a_prev, a_next):
    """RVM calls a motion-blurred hand ~opaque although half of each pixel is wall. Where the clean plate is plain
    light wall, cap alpha by how far the pixel actually is from the wall colour (skin vs wall is ~60 apart, so a real
    hand keeps alpha 1), but only on pixels NOT covered one frame earlier or later: that is where motion blur lives.
    A hand held still keeps RVM's alpha (a pale palm is close to wall colour and would get holes otherwise)."""
    Bf = B.astype(np.float32)
    wall = valid & (Bf.mean(axis=2) > 95) & ((Bf.max(axis=2) - Bf.min(axis=2)) < 40)
    moving = ndimage.binary_dilation(np.minimum(a_prev, a_next) < 128, iterations=2)
    moving = np.repeat(np.repeat(moving, 4, axis=0), 4, axis=1)[:H, :W]
    sel = wall & moving & (a > .02)
    if not sel.any():
        return a
    ys, xs = np.where(sel)
    y0, y1, x0, x1 = max(0, ys.min() - 12), min(H, ys.max() + 12), max(0, xs.min() - 12), min(W, xs.max() + 12)
    box = (slice(y0, y1), slice(x0, x1))
    d = np.sqrt(((rgb[box].astype(np.float32) - Bf[box]) ** 2).sum(axis=2))
    t = np.clip((ndimage.gaussian_filter(d, 1.2) - 10) / 38, 0, 1)
    cap = t * t * (3 - 2 * t)
    red = np.where(wall[box] & (a[box] > .02), a[box] - np.minimum(a[box], cap), 0)      # how much alpha comes off
    red = ndimage.grey_opening(red, size=(9, 9))                 # drop specks: only real smear areas survive
    w = ndimage.gaussian_filter(moving[box].astype(np.float32), 3)   # soft edge on the 4px mask blocks
    out = a.copy()
    out[box] = a[box] - red * w
    return out


def decontaminate(rgb, sub, a, B, valid):
    """True foreground colour for their semi-transparent pixels (edges, motion-blurred hands): C = a*F + (1-a)*B -> F."""
    edge = (a > .02) & (a < .98)
    F = rgb.astype(np.float32)
    F[edge] = sub[..., :3][edge]                                   # RVM's own estimate first
    e1 = edge & valid & (a >= .25)
    a1 = a[e1][:, None]
    F[e1] = np.clip((rgb[e1].astype(np.float32) - (1 - a1) * B[e1]) / a1, 0, 255)
    # very thin pixels: un-mixing divides by ~0, so borrow the colour of the nearest solid ones
    w = (a >= .25).astype(np.float32)
    ys, xs = np.where(edge)
    if len(ys):
        y0, y1, x0, x1 = max(0, ys.min() - 16), min(H, ys.max() + 16), max(0, xs.min() - 16), min(W, xs.max() + 16)
        ww = w[y0:y1, x0:x1]
        num = ndimage.gaussian_filter(F[y0:y1, x0:x1] * ww[..., None], (4, 4, 0), truncate=2.5)
        den = ndimage.gaussian_filter(ww, 4, truncate=2.5)
        e2 = (edge[y0:y1, x0:x1]) & (a[y0:y1, x0:x1] < .25) & (den > .05)
        sub_f = F[y0:y1, x0:x1]
        sub_f[e2] = num[e2] / den[e2][:, None]
    return np.clip(F, 0, 255)


# ---- 3. one clone frame ------------------------------------------------------------------------------------------------
def render_clone(c, i, ring, TR, main_occ, matte_i, a_main):
    x0, y0, cw, ch = C.canvas(c)
    s = c['scale']
    src = max(0, i - C.lag_at(c, i))
    col, a = ring[src]
    ti, ts = TR[i], TR[src]
    # canvas px (u, v) -> comp P = (x0+u, y0+v) -> source p = (P - (x, top) - ti) / s + anchor + ts
    cx = (x0 - c['x'] - ti[0]) / s + AX + ts[0]
    cy = (y0 - c['top'] - ti[1]) / s + AY + ts[1]
    # crop the source to what the canvas needs (+ pad) before the blur
    sx0, sy0 = int(max(0, np.floor(cx) - 6)), int(max(0, np.floor(cy) - 6))
    sx1, sy1 = int(min(W, np.ceil(cx + cw / s) + 6)), int(min(H, np.ceil(cy + ch / s) + 6))
    pa = tighten(ndimage.gaussian_filter(tighten(a[sy0:sy1, sx0:sx1], .10, .95), 1.0), .08, .92)   # round off the matte's small lumps
    pm = np.dstack([col[sy0:sy1, sx0:sx1].astype(np.float32) * pa[..., None], pa * 255]).round().astype(np.uint8)   # premultiplied
    im = Image.fromarray(pm, 'CMYK').filter(ImageFilter.GaussianBlur(SOFT))    # CMYK = 4 plain channels, no alpha logic
    im = im.transform((cw, ch), Image.AFFINE, (1 / s, 0, cx - sx0, 0, 1 / s, cy - sy0), resample=Image.BICUBIC)
    arr = np.asarray(im, np.float32) / 255
    ca = arr[..., 3]
    rgb = arr[..., :3] / np.maximum(ca[..., None], 1e-4)
    rgb = np.clip((rgb - .5) * .97 + .5, 0, 1) * .975                     # a touch flatter and darker: further back
    occ = shift2(main_occ, *MAIN_SHADOW_OFF)[y0:y0 + ch, x0:x0 + cw]      # the real speaker: contact shadow on the clone
    rgb = rgb * (1 - MAIN_SHADOW * occ[..., None])
    sh = np.asarray(Image.fromarray((ca * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(15)), np.float32) / 255
    sh = shift2(sh, *WALL_SHADOW_OFF) * WALL_SHADOW
    oa = ca + (1 - ca) * sh
    orgb = rgb * (ca / np.maximum(oa, 1e-4))[..., None]
    out = np.dstack([orgb, oa])
    # what is actually seen: above the furniture and not behind the real speaker, in comp coordinates
    vis = (ca > .5) & (matte_i[y0:y0 + ch, x0:x0 + cw] < .5)
    seen = vis & (a_main[y0:y0 + ch, x0:x0 + cw] < .5)
    sy, sx = np.where(seen)
    ext = [int(sx.min() + x0), int(sx.max() + x0), int(sy.min() + y0), int(sy.max() + y0)] if len(sx) else None
    # if the speaker's own cutout is cut by the source frame edge, the clone carries that straight cut: is the cut end in view?
    cut = 0
    for side, src_x in (('l', 0), ('r', W - 1)):
        if SRC_CUT[side]:
            u = int(round(c['x'] + s * (src_x - ts[0] - AX) + ti[0])) - x0
            if 3 <= u < cw - 3:
                cut = max(cut, int(seen[:, u - 3:u + 4].any(axis=1).sum()))
    # how much of the clone's head the real speaker hides
    ys, xs = np.where(vis)
    hid = 0.
    if len(ys):
        head = vis.copy()
        head[int(ys.min() + M['head_h'] * s):] = False
        hid = float((head & (a_main[y0:y0 + ch, x0:x0 + cw] > .5)).sum() / max(head.sum(), 1))
    return (np.clip(out, 0, 1) * 255).round().astype(np.uint8), ext, hid, ca, cut


def main():
    os.makedirs(os.path.join(HERE, 'work/bake_debug'), exist_ok=True)
    for c in C.CLONES:
        if not (0 < c['word_f'] < N):
            raise SystemExit(f"clone {c['id']}: word_f {c['word_f']} is outside the clip (0..{N - 1}). Is the CLIP block still the demo's?")
    A = np.load(os.path.join(HERE, 'work/alpha_half.npy'))
    if len(A) != N:
        raise SystemExit('work/alpha_half.npy is from another clip: run prep.py again')
    TR = track_drift(A)
    B0, valid0, AQ = clean_plate(TR)
    print('clean plate: valid on', round(float(valid0.mean()), 3), 'of the frame', flush=True)
    dec_a = reader(['-i', os.path.join(HERE, 'assets/aroll.mp4'), '-pix_fmt', 'rgb24'])
    dec_s = reader(['-c:v', 'libvpx-vp9', '-i', os.path.join(HERE, 'assets/subject.webm'), '-pix_fmt', 'rgba'])
    enc_fg = writer(os.path.join(HERE, 'assets/fg.webm'), W, H, 14)
    encs = {c['id']: writer(os.path.join(HERE, f"assets/clone_{c['id']}.webm"), C.canvas(c)[2], C.canvas(c)[3], 14) for c in C.CLONES}
    ring, report, matte = {}, [], None
    maxlag = max(c['lag'] for c in C.CLONES)
    for i in range(N):
        rgb = np.frombuffer(dec_a.stdout.read(W * H * 3), np.uint8).reshape(H, W, 3)
        sub = np.frombuffer(dec_s.stdout.read(W * H * 4), np.uint8).reshape(H, W, 4)
        a = sub[..., 3].astype(np.float32) / 255
        dxi, dyi = int(round(TR[i][0])), int(round(TR[i][1]))
        Bi, vi = shift2(B0, dxi, dyi), shift2(valid0, dxi, dyi)
        a = refine_alpha(a, rgb, Bi, vi, AQ[max(i - 1, 0)], AQ[min(i + 1, N - 1)])
        col = decontaminate(rgb, sub, a, Bi, vi)     # float32, true fg colour
        ring[i] = (col, a)
        ring.pop(i - maxlag - 2, None)
        if matte is None:
            matte = occluder_matte(B0, valid0, rgb)
        m = ndimage.shift(matte, (TR[i][1], TR[i][0]), order=1, mode='nearest')
        a_main = tighten(a, .06, .96)
        fa = np.maximum(a_main, m)
        main_occ = blur_full(a_main, 30)
        row = dict(f=i)
        K = np.zeros((H, W), np.float32)          # where a clone sits right behind the speaker
        for c in C.CLONES:
            x0, y0, cw, ch = C.canvas(c)
            if not C.present(c, i):
                encs[c['id']].stdin.write(bytes(cw * ch * 4))
                continue
            frame, ext, hid, ca, cut = render_clone(c, i, ring, TR, main_occ, m, a_main)
            encs[c['id']].stdin.write(frame.tobytes())
            K[y0:y0 + ch, x0:x0 + cw] = np.maximum(K[y0:y0 + ch, x0:x0 + cw], ca)
            row[c['id']] = dict(ext=ext, head_hidden=round(hid, 3), src=max(0, i - C.lag_at(c, i)), cut=cut)
        # the speaker's colour: the untouched pixel where the plate is behind the speaker (exact), the un-mixed colour where a clone is
        rgbf = rgb.astype(np.float32)
        K = np.clip(K * 1.5, 0, 1)[..., None]
        person = rgbf * (1 - K) + col * K
        frgb = person * (1 - m[..., None]) + rgbf * m[..., None]
        enc_fg.stdin.write(np.dstack([frgb.round().astype(np.uint8), (fa * 255).round().astype(np.uint8)]).tobytes())
        report.append(row)
        if i % 30 == 0:
            print('frame', i, flush=True)
    for e in [enc_fg] + list(encs.values()):
        e.stdin.close()
        e.wait()
    json.dump(report, open(os.path.join(HERE, 'work/bake.json'), 'w'))
    bad = False
    for c in C.CLONES:
        rows = [r[c['id']] for r in report if c['id'] in r and r[c['id']]['ext']]
        if not rows:
            print(f"!! clone {c['id']}: never visible (hidden by the furniture line or off frame). Check x / top / OCCLUDER_LINE")
            bad = True
            continue
        xa, xb = min(r['ext'][0] for r in rows), max(r['ext'][1] for r in rows)
        # running off a frame edge is only acceptable on a side where the real speaker is cut by the frame too
        off_l, off_r = xa < 6, xb > 1074
        clip = (off_l and not SRC_CUT['l']) or (off_r and not SRC_CUT['r'])
        like_him = (off_l or off_r) and not clip
        bad |= clip
        print(f"clone {c['id']}: canvas {C.canvas(c)}  seen x {xa} to {xb}  y {min(r['ext'][2] for r in rows)} to {max(r['ext'][3] for r in rows)}"
              + ('   !! CLIPPED by the frame edge: move x inward or lower the scale' if clip else
                 '   runs off the frame edge on a side where the real speaker does too: acceptable, look at it' if like_him else '   ok (inside 6..1074)'))
        cut = max(r['cut'] for r in rows)
        if cut > 25:
            bad = True
            print(f"   !! their cutout is cut by the source frame edge and that straight cut is in view on this clone (up to {cut} px tall):"
                  f" move x so the cut end is off-frame or behind the real speaker")
        worst = sorted(rows, key=lambda r: -r['head_hidden'])[:3]
        print(f"   head hidden by the real speaker: max {worst[0]['head_hidden']:.0%} (source frames {[r['src'] for r in worst]})"
              + ('   !! their body covers this clone\'s face for a stretch: move x away from the speaker' if worst[0]['head_hidden'] > .6 else ''))
    print('bake done' + (' WITH WARNINGS' if bad else '') + ': look at work/bake_debug/occluder_overlay.jpg, then build.py')


if __name__ == '__main__':
    main()
