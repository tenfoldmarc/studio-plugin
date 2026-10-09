#!/usr/bin/env python3
"""Bake the zoom-through camera move into the a-roll -> assets/plate.mp4 (same frame count, no audio).

Run from the slot folder with the skill's Python (PY) (numpy + Pillow + scipy, no OpenCV):
  PY bake.py sheet    transition frames only, half res -> work/bake/sheet.jpg   (about 30s: tune build.py here)
  PY bake.py          full bake -> assets/plate.mp4 + work/bake/f_NNN.jpg for every transition frame

Every transition frame is the average of many sub-frame camera positions (true motion blur, summed in linear light
so lamps and windows streak like they would through a lens). One sub-frame is:
  shot A scaled up about POINT_A, melting into the colour at that point once it is deep (the pass-through),
  shot B scaled down about POINT_B; around it, its own border colours stretched outward along the zoom rays and
  falling off into the dark (an edge stretch, never a mirror tile),
  B seen through a soft round portal that opens out of the zoom point.
BAKE_WORKERS=n sets the process count (default 4).
"""
import multiprocessing as mp
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

import build as B

FF = shutil.which('ffmpeg') or 'ffmpeg'
SRC = 'assets/aroll.mp4'
GAMMA = 2.2
LUT = (np.arange(256, dtype=np.float32) / 255.0) ** GAMMA
LUMA = np.array([.2126, .7152, .0722], np.float32)
PAD = 4                       # edge-replicated border on every warp source, so bilinear never pulls in black
_GRID = {}


def grid(w, h):
    """Pixel-centre coordinates (continuous, centre of pixel 0 = 0.5)."""
    if (w, h) not in _GRID:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        _GRID[(w, h)] = (xx + .5, yy + .5)
    return _GRID[(w, h)]


def reader(w, h, start=0, count=None):
    cmd = [FF, '-v', 'error', '-i', SRC, '-vf',
           "select='gte(n,%d)',scale=%d:%d:flags=area:in_color_matrix=bt709:in_range=tv,format=rgb24" % (start, w, h),
           '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24']
    if count:
        cmd += ['-frames:v', str(count)]
    return subprocess.Popen(cmd + ['-'], stdout=subprocess.PIPE)


def read(p, w, h):
    buf = p.stdout.read(w * h * 3)
    if len(buf) < w * h * 3:
        return None
    return np.frombuffer(buf, np.uint8).reshape(h, w, 3)


def one(idx, w, h):
    p = reader(w, h, idx, 1)
    fr = read(p, w, h)
    p.wait()
    if fr is None:
        raise SystemExit('could not read frame %d of %s' % (idx, SRC))
    return fr


# ---- optional light per-shot grades (gamma space) ---------------------------------------------------------------------
def grade(img, look, q):
    if not look:
        return img
    x = img.astype(np.float32) / 255.0
    lum = (x @ LUMA)[..., None]
    if look == 'girl':      # warm, soft, a touch lifted
        x = lum + (x - lum) * .93
        x = (x - .5) * .95 + .5 + .012
        x = x * np.array([1.045, 1.008, .95], np.float32)
    elif look == 'dude':    # darker, cooler, more contrast, the room falls back around the middle of the frame
        h, w = img.shape[:2]
        xc, yc = grid(w, h)
        d = np.sqrt(((xc - 520 * q) / (1000 * q)) ** 2 + ((yc - 1040 * q) / (1300 * q)) ** 2)
        t = np.clip((d - .34) / (1.08 - .34), 0, 1)
        x = lum + (x - lum) * .86
        x = (x - .46) * 1.09 + .46
        x = x * .93
        x = x + ((1 - np.clip(lum, 0, 1)) ** 2) * np.array([-.014, .004, .02], np.float32)
        x = x * (1 - .36 * t * t * (3 - 2 * t))[..., None]
    else:
        raise SystemExit('unknown grade %r (None, girl, dude)' % look)
    return (np.clip(x, 0, 1) * 255 + .5).astype(np.uint8)


# ---- warps (Pillow AFFINE takes the output -> input map, pixel centres at +0.5) -------------------------------------
def inv_affine(s, rot, px, py, cx, cy):
    """Coefficients (a,b,c,d,e,f): input = M * output, for screen = c + s * R(rot) * (src - p)."""
    th = np.deg2rad(rot)
    co, si = np.cos(th) / s, np.sin(th) / s
    px, py, cx, cy = px + .5, py + .5, cx + .5, cy + .5
    return (co, si, px - (co * cx + si * cy), -si, co, py - (-si * cx + co * cy))


def padded(u8, pad=PAD):
    return Image.fromarray(np.pad(u8, ((pad, pad), (pad, pad), (0, 0)), mode='edge'))


def warp(img, coef, size, k=1.0, pad=PAD, out_scale=1.0, resample=Image.BILINEAR):
    """img is a padded source at 1/k of full size; out_scale > 1 renders a smaller output (coarse grids)."""
    a, b, c, d, e, f = coef
    co = (a * out_scale / k, b * out_scale / k, c / k + pad, d * out_scale / k, e * out_scale / k, f / k + pad)
    return img.transform(size, Image.AFFINE, co, resample=resample)


def pyramid(u8):
    out, im = [], Image.fromarray(u8)
    for _ in range(6):
        out.append(padded(np.asarray(im)))
        im = im.resize((max(1, im.width // 2), max(1, im.height // 2)), Image.BOX)
    return out


def sstep(x):
    return x * x * (3 - 2 * x)


def transition_frame(task):
    """One transition frame = average of sub-frame composites across the shutter. Runs in a worker process."""
    f, a_u8, b_u8, fog, q, maxn = task
    h, w = a_u8.shape[:2]
    xc, yc = grid(w, h)
    a_img = padded(a_u8)
    b_pyr = pyramid(b_u8)
    # the fill around shot B while it is smaller than the frame: its own border colours stretched outward along the
    # rays from the zoom point (never a mirror tile). Sampled from a soft quarter-size copy on a quarter-size grid.
    qw, qh = max(1, w // 4), max(1, h // 4)
    soft = Image.fromarray(b_u8).resize((qw, qh), Image.BOX).filter(ImageFilter.GaussianBlur(B.FILL_BLUR * q / 4.0))
    soft = np.asarray(soft).astype(np.float32)
    gx, gy = grid(qw, qh)
    gx, gy = gx * (w / float(qw)), gy * (h / float(qh))      # quarter grid in full-size continuous coordinates
    inset = 6.0 * q
    v = abs(B.speed(f))
    smear = (np.exp(v * B.SHUTTER) - 1.0) * 1150 * q
    n = int(min(maxn, max(2, np.ceil(smear / (4.0 * q)))))
    acc = np.zeros((h, w, 3), np.float32)
    c0 = B.cam(f)
    dist = np.sqrt((xc - (c0['cx'] * q + .5)) ** 2 + (yc - (c0['cy'] * q + .5)) ** 2)
    far = float(np.hypot(max(c0['cx'], B.W - c0['cx']), max(c0['cy'], B.H - c0['cy']))) * q
    pa, pb = (B.POINT_A[0] * q, B.POINT_A[1] * q), (B.POINT_B[0] * q, B.POINT_B[1] * q)
    for j in range(n):
        c = B.cam(f + ((j + .5) / n - .5) * B.SHUTTER)
        gate = B.smooth(np.log(B.PORT_GATE[0]), np.log(B.PORT_GATE[1]), np.log(c['sA']))
        r_in = B.PORT_IN * q * gate * c['sB'] ** B.PORT_G
        r_out = B.PORT_OUT * q * gate * c['sB'] ** B.PORT_G
        need_a, need_b = r_in < far, r_out > .6
        cx, cy = c['cx'] * q, c['cy'] * q
        if need_b:
            sb = c['sB']
            cb = inv_affine(sb, c['rotB'], pb[0], pb[1], cx, cy)
            lvl = int(min(len(b_pyr) - 1, max(0, np.floor(np.log2(1.0 / max(sb, 1e-6)) + .35))))
            bw = LUT[np.asarray(warp(b_pyr[lvl], cb, (w, h), k=2.0 ** lvl))]
            if sb < .9995:
                # where the picture does not reach: pull every pixel back along its ray from the zoom point until it
                # is inside the picture, so the border colours streak outward in the direction of the zoom
                ppx, ppy = pb[0] + .5, pb[1] + .5
                dx = cb[0] * gx + cb[1] * gy + (cb[2] - ppx)
                dy = cb[3] * gx + cb[4] * gy + (cb[5] - ppy)
                with np.errstate(divide='ignore', invalid='ignore'):
                    tx = np.where(dx > 0, (w - inset - ppx) / dx, np.where(dx < 0, (inset - ppx) / dx, np.inf))
                    ty = np.where(dy > 0, (h - inset - ppy) / dy, np.where(dy < 0, (inset - ppy) / dy, np.inf))
                t = np.clip(np.minimum(tx, ty), 0.0, 1.0)
                coords = [(ppy + dy * t) * (qh / float(h)) - .5, (ppx + dx * t) * (qw / float(w)) - .5]
                # falls off with how far past the border the pixel is (t = 1 on the border, 0.25 = four times as far)
                dark = (1.0 - B.EDGE_DARK * sstep(np.clip((1.0 - t) / .75, 0, 1))) ** (1 / GAMMA)
                fill = np.stack([ndimage.map_coordinates(soft[..., ch], coords, order=1, mode='nearest') * dark
                                 for ch in range(3)], axis=-1)
                bg = Image.fromarray(np.clip(fill + .5, 0, 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
                bg = LUT[np.asarray(bg)]
                # signed distance (source px) to the picture's own rectangle: < 0 inside, > 0 outside
                sx = np.abs(cb[0] * xc + cb[1] * yc + (cb[2] - w / 2.0)) - w / 2.0
                sy = np.abs(cb[3] * xc + cb[4] * yc + (cb[5] - h / 2.0)) - h / 2.0
                fe = B.FEATHER * q * (1.0 - sb) ** .7 + 1.0
                cov = sstep(np.clip(-np.maximum(sx, sy) / fe, 0, 1))[..., None]
                bw = bg + (bw - bg) * cov
        if need_a:
            ca_ = inv_affine(c['sA'], c['rotA'], pa[0], pa[1], cx, cy)
            aw = LUT[np.asarray(warp(a_img, ca_, (w, h)))]
            fogw = B.smooth(np.log(B.FOG_FROM), np.log(B.FOG_TO), np.log(c['sA']))
            if fogw > 0:    # diving into the fabric: what is left of shot A melts into the colour at the point
                aw += (fog - aw) * np.float32(fogw)
        if need_a and need_b:
            m = sstep(np.clip((r_out - dist) / (r_out - r_in), 0, 1))[..., None]
            acc += aw + (bw - aw) * m
        elif need_b:
            acc += bw
        else:
            acc += aw
    out = np.clip(acc / n, 0, 1)
    # chromatic fringe that grows with speed: red a hair bigger, blue a hair smaller, about the zoom point
    ca = B.CHROMA * v
    if ca > 5e-4:
        for ch, sgn in ((0, 1.0), (2, -1.0)):
            src = Image.fromarray(np.pad(out[..., ch], 16, mode='edge').astype(np.float32))
            a, b_, c_, d, e, f_ = inv_affine(1.0 + sgn * ca, 0, c0['cx'] * q, c0['cy'] * q, c0['cx'] * q, c0['cy'] * q)
            out[..., ch] = np.asarray(src.transform((w, h), Image.AFFINE, (a, b_, c_ + 16, d, e, f_ + 16), resample=Image.BILINEAR))
    return f, (np.power(np.clip(out, 0, 1), 1 / GAMMA) * 255 + .5).astype(np.uint8), n


def clean(u8, shot, f, q):
    """Frame outside the transition: just the slow creep (one bicubic resample about the dive point)."""
    c = B.cam(f)
    s, p = (c['sA'], B.POINT_A) if shot == 'A' else (c['sB'], B.POINT_B)
    if abs(s - 1) < 1e-5:
        return u8
    h, w = u8.shape[:2]
    co = inv_affine(max(s, 1.0), 0, p[0] * q, p[1] * q, p[0] * q, p[1] * q)
    return np.asarray(warp(padded(u8), co, (w, h), resample=Image.BICUBIC))


def label(tile, text):
    d = ImageDraw.Draw(tile)
    try:
        font = ImageFont.load_default(size=30)
    except TypeError:
        font = ImageFont.load_default()
    d.text((11, 9), text, fill=(0, 0, 0), font=font)
    d.text((10, 8), text, fill=(255, 235, 60), font=font)
    return tile


def main():
    sheet = len(sys.argv) > 1 and sys.argv[1] == 'sheet'
    q = 0.5 if sheet else 1.0
    w, h = int(B.W * q), int(B.H * q)
    maxn = 36 if sheet else 72
    os.makedirs('work/bake', exist_ok=True)
    a_last = grade(one(B.CUT - 1, w, h), B.GRADE_A, q)       # shot A frozen on its last frame after the cut
    b_first = grade(one(B.CUT, w, h), B.GRADE_B, q)          # shot B frozen on its first frame before the cut
    x0, y0, r = int(B.POINT_A[0] * q), int(B.POINT_A[1] * q), max(2, int(10 * q))
    patch = a_last[max(0, y0 - r):y0 + r, max(0, x0 - r):x0 + r].reshape(-1, 3)
    fog = LUT[np.median(patch, axis=0).astype(np.uint8)]
    first = B.F0 + 1 if sheet else 0
    last = B.F1 - 1 if sheet else B.NFRAMES - 1
    src = reader(w, h, first, last - first + 1)
    enc = None
    if not sheet:
        enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (w, h),
                                '-r', '30', '-i', '-', '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
                                '-c:v', 'libx264', '-preset', 'medium', '-crf', '12', '-g', '15', '-bf', '0',
                                '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
                                '-color_range', 'tv', '-movflags', '+faststart', 'assets/plate.mp4'], stdin=subprocess.PIPE)
    workers = max(1, int(os.environ.get('BAKE_WORKERS', '4')))
    tasks, tiles = [], []
    pool = mp.Pool(workers) if workers > 1 else None
    for f in range(first, last + 1):
        raw = read(src, w, h)
        if raw is None:
            raise SystemExit('ran out of frames at %d: clip.json says %d' % (f, B.NFRAMES))
        shot = 'A' if f < B.CUT else 'B'
        g = grade(raw, B.GRADE_A if shot == 'A' else B.GRADE_B, q)
        if f <= B.F0:
            enc.stdin.write(clean(g, 'A', f, q).tobytes())
        elif f >= B.F1:
            enc.stdin.write(clean(g, 'B', f, q).tobytes())
        else:
            tasks.append((f, g if shot == 'A' else a_last, g if shot == 'B' else b_first, fog, q, maxn))
            if f == B.F1 - 1:       # the whole transition is in hand: bake it across the workers, keep the order
                done = pool.imap(transition_frame, tasks) if pool else map(transition_frame, tasks)
                for ff, out, n in done:
                    c = B.cam(ff)
                    print('f%d  A x%.2f  B x%.3f  %d sub-frames' % (ff, c['sA'], c['sB'], n), flush=True)
                    im = Image.fromarray(out)
                    if not sheet:
                        im.save('work/bake/f_%03d.jpg' % ff, quality=92)
                        enc.stdin.write(out.tobytes())
                    tiles.append(label(im.resize((360, 640), Image.BOX), str(ff)))
    src.wait()
    if pool:
        pool.close()
    if enc:
        enc.stdin.close()
        enc.wait()
    cols = 6
    rows = (len(tiles) + cols - 1) // cols
    sh = Image.new('RGB', (360 * cols, 640 * rows))
    for i, t in enumerate(tiles):
        sh.paste(t, (360 * (i % cols), 640 * (i // cols)))
    sh.save('work/bake/sheet.jpg', quality=88)
    print('done: work/bake/sheet.jpg' + ('' if sheet else ' + assets/plate.mp4 (%d frames)' % B.NFRAMES))


if __name__ == '__main__':
    main()
