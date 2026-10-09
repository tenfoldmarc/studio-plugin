#!/usr/bin/env python3
"""Couch wall, step 2: crop the covers, measure the room, bake the foreground. Run from the slot folder with a
python that has numpy, scipy and Pillow (the skill's Python has them):

  python prep.py            covers + camera track (cached) + wall matte + check picture + assets/fg.webm
  python prep.py wall       covers + wall matte + check picture only (seconds; after editing WALL / IN_FRONT / WALL_TOL)
  python prep.py --force    redo the camera track too

Reads the CLIP block from build.py, clip.json, assets/aroll.mp4, assets/subject.webm, the covers folder. Writes:
  assets/tiles/tNN.jpg   the covers cropped to grid tiles          work/tiles.json   their order and count labels
  work/track.json        room homography per frame (reference frame px -> frame n px), "static" for a still camera
  work/wall.jpg          LOOK AT THIS: left = where the grid will show (cyan), right = a preview with the real tiles
  assets/fg.webm         the layer that stays IN FRONT of the grid: the speaker plus furniture and floor
  work/prep.json         measured values build.py reads (caption height, drift, wall share)

How the furniture is found (FURNITURE = 'auto'): the speaker is removed from the shot by averaging the frames where
the speaker is not standing, the wall colour is learned from the upper half of that clean picture, and everything that is
wall coloured and connected to it becomes the grid area. Things hanging ON the wall (pictures, lamps) are covered
by the grid; anything that is not wall coloured and reaches the bottom of the frame (sofa, chair, floor, door
frame) stays in front. No OpenCV: numpy + scipy only.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import build as B      # noqa: E402  (the CLIP block lives there)

FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H = 1080, 1920
CLIPJ = json.load(open('clip.json'))
N = int(CLIPJ['frames'])
if CLIPJ.get('cut_frames'):
    sys.exit('couch-wall needs ONE continuous shot: this slot has internal cuts ' + str(CLIPJ['cut_frames']))
REF = B.REF if B.REF is not None else N // 2
FORCE = '--force' in sys.argv
ONLY_WALL = 'wall' in sys.argv
os.makedirs('work', exist_ok=True)


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
                 '(jpg / png / webp) in that folder; 9 or more looks best. Nothing is shipped with the effect.')
    tw, th = B.tile_size()
    os.makedirs('assets/tiles', exist_ok=True)
    out, unknown = [], [k for k in B.COUNTS if k not in files and k not in [os.path.splitext(f)[0] for f in files]]
    for k, f in enumerate(files):
        im = Image.open(os.path.join(src, f)).convert('RGB')
        w, h = im.size
        if w / h > tw / th:                       # wider than a tile: trim the sides
            cw = h * tw / th
            box = ((w - cw) / 2, 0, (w + cw) / 2, h)
        else:                                     # taller (a 9:16 cover): keep the part CROP_Y of the way down
            ch = w * th / tw
            top = (h - ch) * B.CROP_Y
            box = (0, top, w, top + ch)
        im = im.crop(tuple(int(round(v)) for v in box)).resize((tw, th), Image.LANCZOS)
        name = f't{k:02d}.jpg'
        im.save(os.path.join('assets', 'tiles', name), quality=90)
        raw = B.COUNTS.get(f, B.COUNTS.get(os.path.splitext(f)[0]))
        out.append({'file': name, 'src': f, 'label': count_label(raw),
                    'plays': int(raw) if isinstance(raw, (int, float)) else None})
    json.dump(out, open('work/tiles.json', 'w'), indent=1)
    with_counts = sum(1 for t in out if t['label'])
    print(f'covers: {len(out)} tiles {tw}x{th} in assets/tiles/  counts on {with_counts} of them'
          + ('' if with_counts else ' (COUNTS is empty: tiles carry no numbers)'))
    for k in unknown:
        print(f'WARNING: COUNTS has "{k}" but there is no cover with that file name')
    return out


# ---------------------------------------------------------------------------------------------------------- decode
def stream(alpha=False):
    """full-size frames, one at a time: HxWx3 uint8 (picture) or HxW uint8 (the cutout's alpha)"""
    size = W * H * (1 if alpha else 3)
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9', '-i', 'assets/subject.webm', '-vf',
                                  f'alphaextract,scale={W}:{H},format=gray'] if alpha else
                                 ['-i', 'assets/aroll.mp4', '-vf', f'scale={W}:{H}', '-pix_fmt', 'rgb24']) + \
          ['-fps_mode', 'passthrough', '-f', 'rawvideo', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(size)
        if len(b) < size:
            break
        yield np.frombuffer(b, np.uint8).reshape((H, W) if alpha else (H, W, 3))
    p.wait()


def decode_small(path, w, h, alpha=False):
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + \
          ['-i', path, '-vf', ('alphaextract,' if alpha else '') + f'scale={w}:{h}:flags=area,format=gray',
           '-fps_mode', 'passthrough', '-f', 'rawvideo', '-']
    a = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.uint8).reshape(-1, h, w)
    if len(a) != N:
        sys.exit(f'{path}: decoded {len(a)} frames, clip.json says {N} (remake the slot)')
    return a


# ----------------------------------------------------------------------------------------------------------- track
_grid = {}


def grid(h, w):
    if (h, w) not in _grid:
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
        s = w / 2
        Nm = np.array([[1 / s, 0, (.5 - w / 2) / s], [0, 1 / s, (.5 - h / 2) / s], [0, 0, 1]])
        _grid[(h, w)] = (xs, ys, Nm, np.linalg.inv(Nm), (xs + .5 - w / 2) / s, (ys + .5 - h / 2) / s, s)
    return _grid[(h, w)]


def warp(img, Hp, order=1, mode='constant'):
    """out(x) = img(Hp x), Hp in pixel coords of this image size"""
    h, w = img.shape
    xs, ys = grid(h, w)[:2]
    d = Hp[2, 0] * xs + Hp[2, 1] * ys + Hp[2, 2]
    u = (Hp[0, 0] * xs + Hp[0, 1] * ys + Hp[0, 2]) / d
    v = (Hp[1, 0] * xs + Hp[1, 1] * ys + Hp[1, 2]) / d
    return ndimage.map_coordinates(img, [v, u], order=order, mode=mode, cval=0.0)


def align(R, MR, T, MT, Hn, iters, dof):
    """Gauss-Newton fit of T(Hn x) ~ gain * R(x) + bias on MR & warped MT. dof 6 = affine (coarse levels),
    8 = homography (finest level). The gain / bias pair soaks up the exposure shift when the speaker moves."""
    h, w = R.shape
    _, _, Nm, Ni, xn, yn, s = grid(h, w)
    g, b = 0.0, 0.0
    for _ in range(iters):
        Hp = Ni @ Hn @ Nm
        Tw = warp(T, Hp)
        valid = MR & (warp(MT, Hp) > .98)
        if valid.sum() < 400:
            break
        gy, gx = np.gradient(Tw)
        r = (R - (1 + g) * Tw - b)[valid]
        X, Y, GX, GY = xn[valid], yn[valid], gx[valid] * s, gy[valid] * s
        cols = [GX * X, GX * Y, GX, GY * X, GY * Y, GY]
        if dof == 8:
            cols += [-GX * X * X - GY * X * Y, -GX * X * Y - GY * Y * Y]
        J = np.stack(cols + [Tw[valid], np.ones_like(X)], 1)
        sig = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-3
        wgt = np.minimum(1.0, 1.345 * sig / np.maximum(np.abs(r), 1e-6))
        Jw = J * wgt[:, None]
        A = Jw.T @ J
        dp = np.linalg.solve(A + np.eye(dof + 2) * 1e-7 * np.trace(A), Jw.T @ r)
        g, b = g + dp[dof], b + dp[dof + 1]
        p = np.zeros(8)
        p[:dof] = dp[:dof]
        Hn = Hn @ np.array([[1 + p[0], p[1], p[2]], [p[3], 1 + p[4], p[5]], [p[6], p[7], 1]])
        Hn = Hn / Hn[2, 2]
        if np.abs(p).max() < 8e-5:
            break
    return Hn


def pool(a, f=np.mean):
    h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
    return f(a[:h, :w].reshape(h // 2, 2, w // 2, 2), axis=(1, 3))


def track(gray2, alpha2):
    """gray2 / alpha2: uint8 stacks at half size -> list of 3x3 (full-size px, reference -> frame n), worst shift"""
    ymax = B.TRACK_YMAX if B.TRACK_YMAX is not None else 1100

    def levels(n):
        g = ndimage.gaussian_filter(gray2[n].astype(np.float64), .8)
        m = ndimage.binary_erosion(alpha2[n] < 10, iterations=12, border_value=1)
        if n == REF:
            m[int(ymax / 2):] = False          # floor / furniture sit nearer than the wall: keep them out of the fit
        g4, m4 = pool(g), pool(m, np.min).astype(bool)
        g8, m8 = pool(g4), pool(m4, np.min).astype(bool)
        return [(g8, m8, 8, 6), (g4, m4, 5, 6), (g, m, 5, 8)]
    ref = levels(REF)
    Hn = {REF: np.eye(3)}
    for rng in (range(REF - 1, -1, -1), range(REF + 1, N)):
        prev = np.eye(3)
        for n in rng:
            h = prev
            for (R, MR, it, dof), (T, MT, _, _) in zip(ref, levels(n)):
                h = align(R, MR.astype(bool), T, MT.astype(np.float64), h, it, dof)
            Hn[n] = prev = h
            if n % 20 == 0:
                print(f'  track frame {n}', flush=True)
    s = W / 2
    Nm = np.array([[1 / s, 0, (.5 - W / 2) / s], [0, 1 / s, (.5 - H / 2) / s], [0, 0, 1]])
    Ni = np.linalg.inv(Nm)
    out = []
    for n in range(N):
        m = Ni @ Hn[n] @ Nm
        m = np.array([[1, 0, .5], [0, 1, .5], [0, 0, 1]]) @ m @ np.array([[1, 0, -.5], [0, 1, -.5], [0, 0, 1]])
        out.append(m / m[2, 2])
    probes = np.array([[x, y, 1.0] for x in (120, 400, 680, 960) for y in (200, 450, 700, 950)]).T
    worst = 0.0
    for m in out:
        p = m @ probes
        worst = max(worst, float(np.abs(p[:2] / p[2] - probes[:2]).max()))
    return out, worst


# ----------------------------------------------------------------------------------------------- the room without the speaker
def head_of(al):
    """(top y, centre x, width, estimated chin y) of their head from one alpha frame, or None"""
    rows = np.flatnonzero((al > 128).sum(1) > 24)
    if not len(rows):
        return None
    top = int(rows[0])
    band = al[top:min(H, top + 130)] > 128
    xs = np.flatnonzero(band.any(0))
    if not len(xs):
        return None
    cx = float(np.average(np.arange(W), weights=band.sum(0) + 1e-6))
    width = float(np.percentile(band.sum(1), 90))
    return top, cx, width, top + 1.35 * width


def clean_plate(Hs, static):
    """average of the frames where the speaker is NOT standing, in reference-frame coordinates. -> plate, known, ref rgb/alpha"""
    pick = {int(round(v)) for v in np.linspace(0, N - 1, min(N, 14))} | {REF}
    acc = np.zeros((H, W, 3), np.float32)
    ws = np.zeros((H, W), np.float32)
    ref_rgb = ref_al = None
    heads = []
    n = -1
    for n, (rgb, al) in enumerate(zip(stream(), stream(alpha=True))):
        if n == REF:
            ref_rgb, ref_al = rgb.copy(), al.copy()
        if n not in pick:
            continue
        hd = head_of(al)
        if hd:
            heads.append(hd)
        empty = ndimage.grey_dilation(al, size=(13, 13)) < 10         # 6 px clear of any trace of the speaker
        f = rgb.astype(np.float32)
        if not static:
            f = np.dstack([warp(f[..., c].astype(np.float64), Hs[n]) for c in range(3)]).astype(np.float32)
            empty = warp(empty.astype(np.float64), Hs[n]) > .98
        acc += f * empty[..., None]
        ws += empty
    if n + 1 != N or ref_rgb is None:
        sys.exit(f'decoded {n + 1} frames of a-roll / cutout, clip.json says {N} (remake the slot)')
    return acc / np.maximum(ws, 1)[..., None], ws >= 1, ref_rgb, ref_al, heads


def polygon_mask(polys):
    im = Image.new('L', (W, H), 0)
    for poly in polys:
        ImageDraw.Draw(im).polygon([tuple(p) for p in poly], fill=255)
    return np.asarray(im) > 127


def find_wall(P, known):
    """-> boolean grid area G (reference frame): wall coloured, connected to the upper wall, wall-hung things filled"""
    tol = float(B.WALL_TOL)
    Ps = np.dstack([ndimage.gaussian_filter(P[..., c], 1.2) for c in range(3)])
    Y = Ps @ np.array([.299, .587, .114], np.float32)
    Cb, Cr = (Ps[..., 2] - Y) * .564, (Ps[..., 0] - Y) * .713
    yy, xx = np.mgrid[0:H, 0:W]
    xn, yn = (xx / W - .5).astype(np.float32), (yy / H - .5).astype(np.float32)
    top = known & (yy < H * .5)
    if top.sum() < 20000:
        sys.exit('wall: the speaker fills almost all of the upper half of the frame. This effect needs a wide '
                 'shot with visible wall; use FURNITURE = "off" with a WALL rectangle, or another effect.')
    my, mcb, mcr = (float(np.median(v[top])) for v in (Y, Cb, Cr))
    TC, LO, HI = 8 * tol, 1 - .36 * tol, 1 + .35 * tol
    seed = top & (np.hypot(Cb - mcb, Cr - mcr) < TC) & (Y > LO * my) & (Y < HI * my)
    inl = cls = seed
    rng = np.random.default_rng(3)
    for _ in range(3):
        idx = np.flatnonzero(inl)
        if len(idx) < 5000:
            break
        sub = rng.choice(idx, min(len(idx), 40000), replace=False)
        x, y = xn.ravel()[sub], yn.ravel()[sub]
        A2 = np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], 1)
        cy = np.linalg.lstsq(A2, Y.ravel()[sub], rcond=None)[0]
        cb = np.linalg.lstsq(A2[:, :3], Cb.ravel()[sub], rcond=None)[0]
        cr = np.linalg.lstsq(A2[:, :3], Cr.ravel()[sub], rcond=None)[0]
        pY = np.clip(cy[0] + cy[1] * xn + cy[2] * yn + cy[3] * xn * xn + cy[4] * xn * yn + cy[5] * yn * yn,
                     .55 * my, 1.6 * my)            # the wall's own light falloff, never extrapolated far
        pCb, pCr = cb[0] + cb[1] * xn + cb[2] * yn, cr[0] + cr[1] * xn + cr[2] * yn
        cls = known & (np.hypot(Cb - pCb, Cr - pCr) < TC) & (Y > LO * pY) & (Y < HI * pY)
        opened = ndimage.binary_opening(cls, iterations=2)          # cuts hairline bridges to look-alike things
        lab, cnt = ndimage.label(opened)
        hits = np.bincount(lab[seed], minlength=cnt + 1)
        keep = [i for i in range(1, cnt + 1) if hits[i] > .02 * seed.sum()]
        if not keep:
            break
        inl = np.isin(lab, keep)
    wall = ndimage.binary_closing(inl, iterations=3) & known
    # the line where the wall ends in each column (its lowest wall pixel), bridged across columns the speaker hides
    low = np.where(wall.any(0), H - 1 - np.argmax(wall[::-1], axis=0), -1).astype(np.float64)
    good = low >= 0
    if good.sum() < 40:
        sys.exit('wall: no wall found. Set FURNITURE = "off" and give a WALL rectangle by hand.')
    low = ndimage.median_filter(np.interp(np.arange(W), np.flatnonzero(good), low[good]), size=61, mode='nearest')
    G = wall.copy()
    lab, cnt = ndimage.label(known & ~wall)
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None or sl[0].stop >= H - 2:          # reaches the bottom of the frame: floor / furniture
            continue
        ys = slice(max(0, sl[0].start - 4), min(H, sl[0].stop + 4))
        xs = slice(max(0, sl[1].start - 4), min(W, sl[1].stop + 4))
        comp = lab[ys, xs] == i
        ring = ndimage.binary_dilation(comp, iterations=3) & ~comp
        rw, ru = int((ring & wall[ys, xs]).sum()), int((ring & ~known[ys, xs]).sum())
        cy_, cx_ = ndimage.center_of_mass(comp)
        pocket = cls[ys, xs][comp].mean() > .7 and (ys.start + cy_) < low[int(xs.start + cx_)] - 10
        if rw >= max(1, ru) or pocket:                 # hangs on the wall, or a patch of wall seen past the speaker's arm
            G[ys, xs] |= comp
    return G, {'wall_luma': round(my, 1), 'wall_line_min': int(low.min()), 'wall_line_max': int(low.max())}


def furniture_matte(P, known):
    """-> F float32 0..1 in reference coordinates (1 = stays in front of the grid), info dict"""
    info = {}
    if B.FURNITURE == 'auto':
        G, info = find_wall(P, known)
        Fk = ~G
        # places the speaker covers on every frame take the answer of the nearest place that was seen
        idx = ndimage.distance_transform_edt(~known, return_distances=False, return_indices=True)
        Fb = Fk[idx[0], idx[1]]
        for keep_front in (True, False):               # drop specks: furniture crumbs on the wall, wall crumbs in furniture
            m = Fb if keep_front else ~Fb
            lab, cnt = ndimage.label(m)
            if cnt:
                area = np.bincount(lab.ravel())
                small = [i for i in range(1, cnt + 1) if area[i] < 3000]
                if small:
                    Fb = Fb & ~np.isin(lab, small) if keep_front else Fb | np.isin(lab, small)
    elif B.FURNITURE == 'off':
        Fb = np.zeros((H, W), bool)
    else:
        sys.exit('FURNITURE must be "auto" or "off" (add shapes with IN_FRONT / BEHIND)')
    if B.BEHIND:
        Fb &= ~polygon_mask(B.BEHIND)
    if B.IN_FRONT:
        Fb |= polygon_mask(B.IN_FRONT)
    if B.WALL is not None:
        x0, y0, x1, y1 = (int(v) for v in B.WALL)
        box = np.zeros((H, W), bool)
        box[max(0, y0):y1, max(0, x0):x1] = True
        Fb |= ~box
    info['grid_share'] = round(float((~Fb).mean()), 3)
    rows = np.flatnonzero((~Fb).sum(1) > 8)
    info['grid_bottom'] = int(rows[-1]) if len(rows) else 0          # lowest row where a tile can be seen
    if B.EDGE_CHOKE > 0:
        Fb = ndimage.binary_erosion(Fb, iterations=int(B.EDGE_CHOKE), border_value=1)
    b = ndimage.gaussian_filter(Fb.astype(np.float32), 1.3)
    e = np.clip((b - .5) / .45, 0, 1)
    return (e * e * (3 - 2 * e)).astype(np.float32), info


def fix_alpha(a):
    t = np.clip((a - .04) / .30, 0, 1)
    s = t * t * (3 - 2 * t)                               # motion-blurred sleeves go solid, edges stay soft
    lab, cnt = ndimage.label(s > .1)
    if cnt > 1:
        areas = np.bincount(lab.ravel())
        kill = [i for i in range(1, cnt + 1) if areas[i] < 6000]
        if kill:
            s[np.isin(lab, kill)] = 0
    s = ndimage.minimum_filter(s, size=3)                 # 1 px choke: no light wall fringe over the tiles
    return ndimage.gaussian_filter(s, 1.1)


# ---------------------------------------------------------------------------------------------------- check picture
def grid_picture(tiles):
    """the grid as it sits when it lands (no scroll), for the preview"""
    tw, th = B.tile_size()
    seq = B.grid_order(tiles, B.COLS * (H // th + 2))
    im = Image.new('RGB', (W, H), (11, 11, 11))
    d = ImageDraw.Draw(im)
    for i, t in enumerate(seq):
        x, y = (i % B.COLS) * (tw + B.GAP), B.GRID_TOP + (i // B.COLS) * (th + B.GAP)
        im.paste(Image.open(os.path.join('assets', 'tiles', t['file'])), (x, y))
        if t['label']:
            d.text((x + 14, y + th - 40), t['label'], fill=(255, 255, 255))
    return np.asarray(im).astype(np.float32) * B.LOOK[0]


def check_picture(F, ref_rgb, ref_al, tiles, cap_y, cap_h):
    f = ref_rgb.astype(np.float32)
    a = np.maximum(F, fix_alpha(ref_al.astype(np.float32) / 255))[..., None]
    g = .45 * (1 - a)                                      # cyan only where the grid will really be seen on this frame
    left = f * (1 - g) + np.array([0, 190, 230], np.float32) * g
    right = grid_picture(tiles) * (1 - a) + f * a
    sheet = Image.fromarray(np.clip(np.hstack([left, right]), 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(sheet)
    for ox in (0, W):
        for box in ((0, 0, W, 220), (0, 1470, W, H)):                       # caption safe zone (the grid may cross it)
            d.rectangle((ox + box[0], box[1], ox + box[2] - 1, box[3] - 1), outline=(255, 60, 60), width=3)
        d.rectangle((ox + 60, cap_y, ox + W - 60, cap_y + cap_h), outline=(250, 230, 122), width=3)
        if B.WALL is not None:
            d.rectangle((ox + B.WALL[0], B.WALL[1], ox + B.WALL[2], B.WALL[3]), outline=(0, 255, 255), width=4)
    sheet.resize((W, H // 2), Image.LANCZOS).save('work/wall.jpg', quality=88)


# ------------------------------------------------------------------------------------------------------------ bake
def bake(F, Hs, static):
    enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', '30',
                            '-i', '-', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '16', '-g', '30',
                            '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '3', '-metadata:s:v:0', 'alpha_mode=1',
                            'assets/fg.webm'], stdin=subprocess.PIPE)
    n = 0
    for rgb, al in zip(stream(), stream(alpha=True)):
        a = fix_alpha(al.astype(np.float32) / 255)
        # moving camera: the furniture matte rides the room. Edge pixels repeat outward ('nearest'), otherwise a
        # strip of grid would open along the frame border the camera drifts away from
        fm = F if static else warp(F.astype(np.float64), np.linalg.inv(Hs[n]), mode='nearest').astype(np.float32)
        a = np.maximum(a, fm)
        enc.stdin.write(np.dstack([rgb, (a * 255).round().astype(np.uint8)]).tobytes())
        n += 1
        if n % 30 == 0:
            print(f'  bake frame {n}', flush=True)
    enc.stdin.close()
    enc.wait()
    if n != N:
        sys.exit(f'bake: wrote {n} frames, expected {N}')
    print(f'baked assets/fg.webm ({n} frames)')


def main():
    if not os.path.exists('assets/subject.webm'):
        sys.exit('assets/subject.webm is missing: make the slot with fx_new.py WITHOUT --no-cutout')
    tiles = make_tiles()
    if FORCE or not os.path.exists('work/track.json'):
        print('tracking the room against the reference frame ...', flush=True)
        Hs, worst = track(decode_small('assets/aroll.mp4', W // 2, H // 2),
                          decode_small('assets/subject.webm', W // 2, H // 2, alpha=True))
        static = worst < 1.2
        json.dump({'ref': REF, 'static': bool(static), 'max_shift_px': round(worst, 2),
                   'hom': [[float(v) for v in m.ravel()] for m in Hs]}, open('work/track.json', 'w'))
        print(f'track: the wall moves up to {worst:.1f} px over the clip -> ' +
              ('still camera, the grid is simply pinned' if static else 'the grid and the furniture ride the camera'))
    TR = json.load(open('work/track.json'))
    if TR['ref'] != REF or len(TR['hom']) != N:
        sys.exit('work/track.json was made for another reference frame / clip: run prep.py --force')
    static = bool(TR['static'])
    Hs = [np.eye(3) if static else np.array(h).reshape(3, 3) for h in TR['hom']]
    print('reading the room (clean plate, wall, furniture) ...', flush=True)
    P, known, ref_rgb, ref_al, heads = clean_plate(Hs, static)
    F, info = furniture_matte(P, known)
    # caption height: under the lowest chin of the clip, around the chest, block fully above y 1470
    cap_h = B.caption_height()
    if heads:
        top = min(h[0] for h in heads)
        chin = max(h[3] for h in heads)
        auto_y = max(chin + 70, top + .6 * (1470 - top))
    else:
        top, chin, auto_y = None, None, 1040
    auto_y = int(max(240, min(auto_y, 1450 - cap_h)))
    cap_y = int(B.CAP_Y) if B.CAP_Y is not None else auto_y
    check_picture(F, ref_rgb, ref_al, tiles, cap_y, cap_h)
    json.dump({'frames': N, 'ref': REF, 'static': static, 'max_shift_px': TR['max_shift_px'], 'cap_y_auto': auto_y,
               'head_top': top, 'chin': None if chin is None else int(chin), 'tiles': len(tiles), **info},
              open('work/prep.json', 'w'), indent=1)
    print(f"wall: the grid shows on {info['grid_share'] * 100:.0f}% of the frame  {info}")
    print(f'captions: measured top {auto_y} px (head top {top}, chin about {None if chin is None else int(chin)})')
    if info['grid_share'] < .08:
        print('WARNING: very little wall for the grid. Tight shot, or the wall was not recognised: raise WALL_TOL, '
              'or set FURNITURE = "off" and a WALL rectangle.')
    if B.FURNITURE == 'auto' and float((F[int(H * .93):] < .5).mean()) > .02:
        print('WARNING: the grid area reaches the bottom of the frame. Floor or furniture looks like the wall: lower '
              'WALL_TOL, give a WALL rectangle, or draw the furniture in IN_FRONT.')
    print('wrote work/wall.jpg: LOOK AT IT (cyan = grid; furniture, floor and the speaker must stay clear of it)')
    if ONLY_WALL:
        print('wall only: run prep.py without "wall" to bake assets/fg.webm before building')
        return
    bake(F, Hs, static)


if __name__ == '__main__':
    main()
