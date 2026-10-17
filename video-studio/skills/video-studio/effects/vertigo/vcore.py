#!/usr/bin/env python3
"""Shared machinery for Vertigo (prep.py, build.py and bake.py import it). Nothing clip-specific lives here.

The move: one push (room grows to `scale` around a point behind the head), a slow creep while it holds, then a
damped spring back through about 0.9x that is faded to exactly 1.0 so the slot hands back plain footage.
The warp: output pixel -> source pixel, uniform scale about ORIGIN, weighted by a vertical "pin" field: 0 above the
shoulders (the far room stretches fully), 1 from the seat down (the chair, sofa, desk and floor at the speaker's
depth stay put, like they would in a real dolly zoom). The pin is vertical only, so the map never folds over.
"""
import json
import math
import os
import shutil
import subprocess

import numpy as np

W, H, FPS = 1080, 1920, 30
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
DEC = 'scale=in_color_matrix=bt709:in_range=tv:flags=accurate_rnd+full_chroma_int,format=bgr24'


def here(*p):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *p)


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, dtype=np.float32) - a) / max(1e-6, (b - a)), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def count_frames(path):
    r = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
                        'stream=nb_read_frames', '-of', 'csv=p=0', path], capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


def decode_video(path, out_path, n_max=None):
    """Decode to a raw uint8 memmap (N, H, W, 3) BGR on disk; returns the memmap."""
    n = count_frames(path) if n_max is None else n_max
    mm = np.lib.format.open_memmap(out_path, mode='w+', dtype=np.uint8, shape=(n, H, W, 3))
    p = subprocess.Popen([FF, '-v', 'error', '-i', path, '-vf', DEC, '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
    fs = H * W * 3
    for i in range(n):
        b = p.stdout.read(fs)
        if len(b) < fs:
            mm = mm[:i]
            break
        mm[i] = np.frombuffer(b, np.uint8).reshape(H, W, 3)
    p.stdout.close()
    p.wait()
    return mm


def decode_alpha(path, out_path, n):
    mm = np.lib.format.open_memmap(out_path, mode='w+', dtype=np.uint8, shape=(n, H, W))
    p = subprocess.Popen([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', path, '-vf', 'alphaextract', '-f', 'rawvideo',
                          '-pix_fmt', 'gray', '-'], stdout=subprocess.PIPE)
    fs = H * W
    got = 0
    for i in range(n):
        b = p.stdout.read(fs)
        if len(b) < fs:
            break
        mm[i] = np.frombuffer(b, np.uint8).reshape(H, W)
        got += 1
    p.stdout.close()
    p.wait()
    if got < n:                       # a short cutout: hold its last frame (prep prints the mismatch)
        mm[got:] = mm[max(0, got - 1)]
    return mm, got


# ------------------------------------------------------------------------------------------------ the curve
def vertigo(t, c):
    """Room scale at time t (seconds). c = the curve dict build.py writes into work/curve.json. 1.0 = untouched."""
    t0, tp, tr, s = c['t_start'], c['t_peak'], c['t_release'], c['scale']
    if t <= t0:
        return 1.0
    if t <= tp:
        u = (t - t0) / (tp - t0)
        e = u * u * u * (u * (u * 6 - 15) + 10)                   # smootherstep: slow in, slow out
        return 1.0 + (s - 1.0) * e
    top = s + c['creep'] * min(1.0, (min(t, tr) - tp) / max(1e-6, tr - tp)) ** 0.85
    if t <= tr:
        return top
    a, tt = top - 1.0, t - tr
    wd = math.pi / c['spring_t_min']
    z = c['spring_zeta']
    wn = wd / math.sqrt(1 - z * z)
    y = a * math.exp(-z * wn * tt) * (math.cos(wd * tt) + (z * wn / wd) * math.sin(wd * tt))
    fade = 1.0 - float(smoothstep(c['settle'][0], c['settle'][1], tt))
    return 1.0 + y * fade


# ------------------------------------------------------------------------------------------------ the warp
class Warp:
    def __init__(self, origin, shoulder_y, seat_y, squeeze=0.10, lens_k=0.10):
        gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        self.ox, self.oy = float(origin[0]), float(origin[1])
        self.dx, self.dy = gx - self.ox, gy - self.oy
        ea, eb = max(self.ox, W - self.ox), max(self.oy, H - self.oy)
        self.reach = float(np.hypot(ea, eb))
        self.rho = np.sqrt((self.dx / ea) ** 2 + (self.dy / eb) ** 2).astype(np.float32)   # 0 origin, 1 frame edge
        pin = np.maximum(smoothstep(shoulder_y, seat_y, gy), smoothstep(H - 150, H - 5, gy))
        self.free = (1.0 - pin).astype(np.float32)                    # how much each row takes part in the stretch
        self.pinch = (1.0 - smoothstep(0.75, 1.6, self.rho)).astype(np.float32)
        self.rho2 = (np.minimum(self.rho, 1.3) ** 2).astype(np.float32)
        self.edge_m = smoothstep(0.42, 1.10, self.rho).astype(np.float32)[..., None]
        self.squeeze, self.lens_k = squeeze, lens_k

    def maps(self, s):
        """Inverse map (output pixel -> source pixel) for room scale s."""
        if s >= 1.0:
            k = s - 1.0
            ly = 1.0 + k * (1.0 + self.lens_k * self.rho2) * self.free
            lx = 1.0 + k * (1.0 + self.lens_k * self.rho2) * (1.0 - self.squeeze) * self.free
        else:                                    # undershoot: the few px past the frame edge are mirrored
            ly = 1.0 + (s - 1.0) * np.minimum(self.pinch, self.free)
            lx = ly
        return (self.ox + self.dx / lx).astype(np.float32), (self.oy + self.dy / ly).astype(np.float32)


def mirror_fill(img, hole, band=110.0):
    """Fill `hole` (bool HxW) of one picture from the picture itself: the room right outside the outline mirrored
    in (keeps edges at the right height and direction), fading into a soft inpaint deeper in. Used per frame when the
    camera moves too much for one clean plate ("live" fill)."""
    import cv2
    h8 = hole.astype(np.uint8) * 255
    if not hole.any():
        return img.astype(np.float32)
    small = cv2.resize(img, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    hs = cv2.dilate(cv2.resize(h8, (W // 4, H // 4), interpolation=cv2.INTER_NEAREST), np.ones((3, 3), np.uint8))
    deep = cv2.resize(cv2.inpaint(small, hs, 5, cv2.INPAINT_TELEA), (W, H), interpolation=cv2.INTER_CUBIC)
    dist, lab = cv2.distanceTransformWithLabels(h8, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.where(~hole)
    lut_y = np.zeros(lab.max() + 1, np.int32)
    lut_x = np.zeros(lab.max() + 1, np.int32)
    lut_y[lab[ys, xs]], lut_x[lab[ys, xs]] = ys, xs
    py, px = np.where(hole)
    by, bx = lut_y[lab[py, px]], lut_x[lab[py, px]]
    qy, qx = np.clip(2 * by - py, 0, H - 1), np.clip(2 * bx - px, 0, W - 1)
    bad = hole[qy, qx]
    qy[bad], qx[bad] = by[bad], bx[bad]
    out = img.astype(np.float32).copy()
    mir = out.copy()                               # real room outside the hole, so the blur does not darken the seam
    mir[py, px] = img[qy, qx]
    mir = cv2.GaussianBlur(mir, (0, 0), 1.2)
    m = (1 - smoothstep(band * 0.55, band, dist))[..., None]
    fill = mir * m + deep.astype(np.float32) * (1 - m)
    out[hole] = fill[hole]
    return out


def load_json(p):
    with open(p) as f:
        return json.load(f)
