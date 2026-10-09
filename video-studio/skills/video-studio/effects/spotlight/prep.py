#!/usr/bin/env python3
"""spotlight prep. Run from the slot folder after the CLIP block in build.py is filled (numpy, scipy, Pillow):

    python prep.py            measure + bake (1 to 3 min)
    python prep.py measure    measure only (10 s): work/measure.json, for a first look at the numbers

Reads   assets/aroll.mp4, assets/subject.webm (the cutout made by fx_new.py), clip.json, the CLIP block of build.py
Writes  work/measure.json          head / neck / free room per frame and as one summary (build.py places the words from it)
        assets/room_dark.mp4       the room with the lights down, frame by frame from the LIVE picture: the speaker is
                                   painted out of every frame before it is blurred (a blurred speaker would glow around
                                   the sharp cutout), then cooled, dimmed and lit by a pool that follows the speaker.
                                   Nothing is a still plate, so a drifting or handheld camera works.
        assets/subject_spot.webm   the cutout for a dark room: edge pulled in and feathered, outer edge recoloured from
                                   inside, lifted, warm top rim, lower body falling off. The fall and the return of the
                                   light are baked in frame by frame (build.ramp).
        work/check_sheet.jpg       measure picture + 5 frames of room + speaker (no words)
        work/check_edge.jpg        FULL SIZE crops in the darkest moment: head / hair, and the fastest moving edge (hand)
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import build as B

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H = 1080, 1920
N = json.load(open('clip.json'))['frames']
END = B.end_frame(N)                     # first plain frame after the release
SPAN = (B.F_IN, min(N, END) - 1)         # frames on which the baked layers are on screen
LUMA = np.array([.2126, .7152, .0722], np.float32)
MEASURE_ONLY = sys.argv[1:] == ['measure']
if not os.path.exists('assets/subject.webm'):
    sys.exit('no assets/subject.webm: this effect needs the cutout (make the slot without --no-cutout)')
if B.F_OUT is not None and END + 5 > N - 1:
    sys.exit(f'F_OUT {B.F_OUT} is too late for {N} frames: {N - B.EASE_OUT_FR - 5} or earlier, or None')


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def reader(src, pix, alpha=False):
    # the picture is read as bt709 and room_dark.mp4 is written and tagged bt709, so the browser shows both alike
    vf = [] if alpha else ['-vf', 'scale=in_color_matrix=bt709,format=rgb24']
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + ['-i', src] + vf + ['-f', 'rawvideo', '-pix_fmt', pix, '-']
    ch = {'rgb24': 3, 'rgba': 4}[pix]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    while True:
        buf = p.stdout.read(W * H * ch)
        if len(buf) < W * H * ch:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, ch)
    p.wait()


def resize(a, w, h, how=Image.BILINEAR):
    """float image (2D or 3 channel) to w x h"""
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32), 'F').resize((w, h), how))
    return np.dstack([resize(a[..., c], w, h, how) for c in range(a.shape[2])])


# ------------------------------------------------------------------------------------------------ 1. measure
def head_of(m):
    """m: half-size boolean matte. Returns head top, centre x, width, neck row (half-size px) or None."""
    rows = m.sum(1)
    ok = (rows > 5) & (np.roll(rows, -1) > 5) & (np.roll(rows, -2) > 5)
    ys = np.where(ok[:-2])[0]
    if not len(ys):
        return None
    top = int(ys[0])
    xs = np.where(m[top + 1])[0]
    cx = float(xs.mean())
    rw, mid = [], []
    for y in range(top, m.shape[0]):
        xs = np.where(m[y])[0]
        if not len(xs):
            break
        cuts = np.where(np.diff(xs) > 3)[0]
        starts, ends = np.r_[xs[0], xs[cuts + 1]], np.r_[xs[cuts], xs[-1]]
        k = int(np.argmin(np.where((starts <= cx) & (ends >= cx), 0, np.minimum(abs(starts - cx), abs(ends - cx)))))
        rw.append(ends[k] - starts[k] + 1)
        mid.append((starts[k] + ends[k]) / 2)
        cx = .7 * cx + .3 * mid[-1]
    rw = ndimage.median_filter(np.array(rw, np.float32), 5)
    # head = widest run before the outline narrows (neck) and then grows clearly wider than the head (shoulders)
    wmax, ymax, sh, dip = 0.0, 0, None, 0
    for i, w in enumerate(rw):
        if dip >= 3:
            if w > 1.2 * wmax:
                sh = i
                break
        elif w > wmax:
            wmax, ymax, dip = float(w), i, 0
        elif w < .9 * wmax and i > 8:
            dip += 1
    if sh is None:                                   # no shoulders found (hood, long hair, head only): a guess
        return top, mid[ymax], wmax, min(m.shape[0] - 1, top + ymax + int(.6 * wmax)), False
    neck = ymax + int(np.argmin(rw[ymax:sh]))
    return top, mid[ymax], wmax, top + neck, True


def measure():
    f0, f1 = SPAN
    track, small, lo, hi = {}, {}, np.full(H // 2, W, np.float32), np.zeros(H // 2, np.float32)
    for n, fr in enumerate(reader('assets/subject.webm', 'rgba', True)):
        if not (f0 <= n <= f1):
            continue
        a = fr[::2, ::2, 3]
        m = a > 127
        h = head_of(m)
        if h is None:
            sys.exit(f'frame {n}: the cutout is empty. This effect needs the speaker cut out on every frame of the hold.')
        track[n] = h
        small[n] = a[::4, ::4].astype(np.float32) / 255              # 1/8 size, for the moving-edge search
        any_row = m.any(1)
        lo = np.where(any_row, np.minimum(lo, m.argmax(1) * 2), lo)
        hi = np.where(any_row, np.maximum(hi, (m.shape[1] - 1 - m[:, ::-1].argmax(1)) * 2), hi)
    if len(track) != f1 - f0 + 1:
        sys.exit(f'assets/subject.webm has no frames {f0}..{f1}: cutout and a-roll do not match')
    fr_ids = sorted(track)
    t = np.array([track[n][:4] for n in fr_ids], np.float32) * 2    # full-size px
    sm = ndimage.gaussian_filter1d(t, 2.5, axis=0, mode='nearest')
    med = np.median(t, axis=0)
    top, hx, hw, neck = (float(v) for v in med)
    hh = max(40.0, neck - top)
    y0, y1 = int(max(0, top - .2 * hh) / 2), int(min(H - 2, neck) / 2)
    summary = {
        'head_x': round(hx, 1), 'head_top': round(top, 1), 'head_top_min': float(t[:, 0].min()),
        'head_top_range': float(t[:, 0].max() - t[:, 0].min()), 'head_w': round(hw, 1), 'head_h': round(hh, 1),
        'neck_y': round(neck, 1), 'neck_y_max': float(t[:, 3].max()),
        'free_left': float(lo[y0:y1 + 1].min() - 26 - 41), 'free_right': float(1039 - hi[y0:y1 + 1].max() - 26),
        'neck_found': bool(all(track[n][4] for n in fr_ids)),
        'drift_px': float(np.hypot(sm[:, 1].max() - sm[:, 1].min(), sm[:, 0].max() - sm[:, 0].min())),
    }
    # pool of light: lit disc reaches a margin above the head and to its sides, centre near the collarbone. On a
    # close shot that pool would light most of the room, so it is tightened until at most ~32% of the visible room
    # is lit (the room has to read as dark), then scaled by POOL.
    dark = [n for n in fr_ids if B.ramp(n) > .999] or [fr_ids[len(fr_ids) // 2]]
    st = np.stack([small[n] for n in dark])
    bg = st.mean(0) < .5
    y8, x8 = np.mgrid[0:bg.shape[0], 0:bg.shape[1]].astype(np.float32) * 8 + 4
    for k in np.arange(1.0, .39, -.05):
        share = float(fields(hx, top, pool_of(hh, hw, k), x8, y8)[0][bg].mean()) if bg.any() else 0
        if share <= .32:
            break
    summary['pool'] = [round(float(v), 3) for v in pool_of(hh, hw, float(k) * float(B.POOL))]
    summary['pool_auto'], summary['lit_share'] = round(float(k), 2), round(share, 3)
    # check frames: the first fully dark one for the hair; for the hand, the fully dark frame where the fastest
    # moving part of the outline (outside the head) is most present
    var = st.var(0)
    yy, xx = np.mgrid[0:var.shape[0], 0:var.shape[1]]
    var[(abs(xx * 8 - hx) < hw * .7) & (yy * 8 < neck + .15 * hh)] = 0
    cw, ch_ = 540, 480
    score = ndimage.uniform_filter(var, (ch_ // 8, cw // 8), mode='constant')
    by, bx = np.unravel_index(int(score.argmax()), score.shape)
    hand_box = [int(min(max(bx * 8 - cw // 2, 0), W - cw)), int(min(max(by * 8 - ch_ // 2, 0), H - ch_))]
    win = st[:, hand_box[1] // 8:(hand_box[1] + ch_) // 8, hand_box[0] // 8:(hand_box[0] + cw) // 8]
    edge = np.abs(np.diff(win, axis=2)).sum((1, 2)) + np.abs(np.diff(win, axis=1)).sum((1, 2))
    hand_f = dark[int(edge.argmax())]
    hair_box = [int(min(max(hx - cw // 2, 0), W - cw)), int(min(max(top - 110, 0), H - ch_))]
    M = {'frames': N, 'stamp': B.stamp(), 'baked': False, 'span': list(SPAN), 'summary': summary,
         'track': {str(n): [round(float(v), 1) for v in sm[i]] for i, n in enumerate(fr_ids)},
         'left_edge': [float(v) for v in lo], 'right_edge': [float(v) for v in hi],
         'check': {'hair': [dark[0]] + hair_box, 'hand': [hand_f] + hand_box, 'crop': [cw, ch_]}}
    json.dump(M, open('work/measure.json', 'w'))
    s = summary
    print(f"measured f{f0}..f{f1}: head top y {s['head_top']:.0f} (moves {s['head_top_range']:.0f} px), centre x {s['head_x']:.0f}, "
          f"head {s['head_w']:.0f} x {s['head_h']:.0f}, neck y {s['neck_y']:.0f}, drift {s['drift_px']:.0f} px, "
          f"free room beside the head: left {s['free_left']:.0f} px, right {s['free_right']:.0f} px, pool tightness {s['pool_auto']} "
          f"({s['lit_share'] * 100:.0f}% of the visible room lit)")
    if not s['neck_found']:
        print('  !! no clear neck / shoulders on some frames (hood, long hair, hands at the head): check the green box')
    return M


# ------------------------------------------------------------------------------------------------ 2. bake
def pool_of(hh, hw, k):
    """pool for a head of this size: [centre y under the head top, radius x, radius y, penumbra end, tightness,
    falloff reach (on a close shot the speaker fills the frame: the falloff must not swallow shoulders and hands)]"""
    m_ = min(max(.45 * hh, 90), 140) * k
    cy_off = min(.9 * hh, 420)
    ry = (cy_off + m_) / B.POOL_EDGE[0]
    rx = min(ry * .9, (hw / 2 + 1.8 * m_) / B.POOL_EDGE[0])
    return [cy_off, rx, ry, B.POOL_EDGE[0] + (B.POOL_EDGE[1] - B.POOL_EDGE[0]) * min(1.0, k), min(1.0, k), max(1.0, hh / 260)]


def fields(hx, top, pool, xx, yy):
    """light for one frame, from the speaker's (smoothed) position: lit wall 0..1, beam haze, falloff"""
    cy_off, rx, ry, edge1, tight, reach = pool
    px, py, k = hx, top + cy_off, rx / 450 * tight
    r = np.sqrt(((xx - px) / rx) ** 2 + ((yy - py) / ry) ** 2)
    disc = 1 - smooth(r, B.POOL_EDGE[0], edge1)
    half = 70 * k + (yy + 420) * .30 * k
    cone = np.exp(-((xx - hx) / half) ** 2 * 1.5) * (1 - smooth(yy, py - 200 * k, py + ry * .9))
    lit = np.maximum(disc, cone * B.CONE_ON_WALL)
    haze = np.exp(-((xx - hx) / (half * .8)) ** 2 * 1.6) * (1 - smooth(yy, py - 420 * k, py + 260 * k)) * B.BEAM_HAZE
    r2 = np.sqrt(((xx - hx) / (560 * max(1, k) * reach)) ** 2 + ((yy - (py + 110 * k)) / (930 * max(1, k) * reach)) ** 2)
    fall = B.FALLOFF * smooth(r2, .62, 1.22)
    return lit, haze, fall


def bake(M):
    S, chk = M['summary'], M['check']
    f0, f1 = SPAN
    hw_, hh_ = W // 2, H // 2
    yh, xh = np.mgrid[0:hh_, 0:hw_].astype(np.float32) * 2 + .5       # half-size grid in full-size px
    warm, fallc, navy = (np.array(c, np.float32) / 255 for c in (B.WARM, B.FALL_RGB, B.NAVY))
    cool, pwarm = np.array(B.ROOM_TINT, np.float32), np.array(B.POOL_TINT, np.float32)
    gap = None
    if B.GAP:
        im = Image.new('L', (W, H), 0)
        ImageDraw.Draw(im).polygon([tuple(p) for p in B.GAP], fill=255)
        gap = ndimage.gaussian_filter(np.asarray(im).astype(np.float32) / 255, 1.6)

    def enc(path, pix, args):
        return subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', pix, '-s', f'{W}x{H}', '-r', '30',
                                 '-i', '-'] + args + [path], stdin=subprocess.PIPE)

    e_room = enc('assets/room_dark.mp4', 'rgb24', ['-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p', '-c:v', 'libx264',
                                                  '-crf', '12', '-preset', 'medium', '-g', '15', '-colorspace', 'bt709',
                                                  '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv', '-an'])
    e_subj = enc('assets/subject_spot.webm', 'rgba', ['-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '16',
                                                      '-g', '30', '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '3',
                                                      '-metadata:s:v:0', 'alpha_mode=1'])
    black, empty = np.zeros((H, W, 3), np.uint8).tobytes(), np.zeros((H, W, 4), np.uint8).tobytes()
    sheet_f = sorted({max(0, f0 - 1), f0 + 1, chk['hair'][0], chk['hand'][0], min(f1, (B.F_OUT or f1) + 2), min(N - 1, f1 + 3)})
    tiles, crops, n = {}, {}, -1
    for n, (pic, cut) in enumerate(zip(reader('assets/aroll.mp4', 'rgb24'), reader('assets/subject.webm', 'rgba', True))):
        if not (f0 <= n <= f1):
            e_room.stdin.write(black)
            e_subj.stdin.write(empty)
            if n in sheet_f:
                tiles[n] = pic[::6, ::6].copy()
            continue
        r = B.ramp(n)
        top, hx, _, _ = M['track'][str(n)]
        full = pic.astype(np.float32) / 255
        a_raw = cut[..., 3].astype(np.float32) / 255

        # ---- room: paint the speaker out of this frame, blur, grade, light
        sig = B.BLUR * r
        ph = full.reshape(hh_, 2, hw_, 2, 3).mean((1, 3))
        ah = a_raw.reshape(hh_, 2, hw_, 2).max((1, 3))
        grow = int(round((4 + 1.6 * sig) / 2))
        hole = ndimage.maximum_filter(ah > .03, size=2 * grow + 1)
        q = 4                                                          # fill at 1/8 size, row-wise: rooms are built in
        small, known = ph[::q, ::q], (~hole[::q, ::q]).astype(np.float32)   # horizontal bands (wall, sofa back, floor)
        res = np.broadcast_to((small * known[..., None]).sum((0, 1)) / max(1.0, known.sum()), small.shape).copy()
        for s_ in (80, 40, 20, 10, 5, 2.5, 1.2):
            sg = (max(.6, s_ / 7), s_)
            den = ndimage.gaussian_filter(known, sg)
            num = np.dstack([ndimage.gaussian_filter(small[..., c] * known, sg) for c in range(3)])
            conf = smooth(den, .04, .35)[..., None]
            res = res * (1 - conf) + num / np.maximum(den, 1e-5)[..., None] * conf
        fill = resize(res, hw_, hh_, Image.BICUBIC)
        hm = ndimage.gaussian_filter(hole.astype(np.float32), 2.5)[..., None]
        room = ph * (1 - hm) + fill * hm
        room = np.dstack([ndimage.gaussian_filter(room[..., c], max(.01, sig / 2), mode='nearest') for c in range(3)])
        lit, haze, fall = fields(hx, top, S['pool'], xh, yh)
        lit = ndimage.gaussian_filter(lit, 5)[..., None]
        luma = (room * LUMA).sum(-1, keepdims=True)
        g = (luma + (room - luma) * B.ROOM_SAT) * (cool + (pwarm - cool) * lit)
        g = g * (B.DARK + (B.ROOM_LIT - B.DARK) * lit) + navy * (1 - lit) * B.NAVY_LIFT
        hz = ndimage.gaussian_filter(haze, 5)[..., None]
        g = g * (1 - hz) + warm * hz
        g = g * (1 - fall[..., None]) + fallc * fall[..., None]
        room = room * (1 - r) + g * r
        up = resize(room, W, H, Image.BICUBIC)
        wmix = float(smooth(np.float32(sig), .6, 3.0))                 # barely blurred frames keep full-size detail
        if wmix < .999:
            fl, hzf, ff_ = (resize(x, W, H) for x in (lit[..., 0], hz[..., 0], fall))
            lu = (full * LUMA).sum(-1, keepdims=True)
            gf = (lu + (full - lu) * B.ROOM_SAT) * (cool + (pwarm - cool) * fl[..., None])
            gf = gf * (B.DARK + (B.ROOM_LIT - B.DARK) * fl[..., None]) + navy * (1 - fl[..., None]) * B.NAVY_LIFT
            gf = gf * (1 - hzf[..., None]) + warm * hzf[..., None]
            gf = gf * (1 - ff_[..., None]) + fallc * ff_[..., None]
            up = up * wmix + (full * (1 - r) + gf * r) * (1 - wmix)
        room8 = (up.clip(0, 1) * 255 + .5).astype(np.uint8)
        e_room.stdin.write(room8.tobytes())

        # ---- speaker: work inside the box of the cutout
        ys, xs = np.where(a_raw.max(1) > 0)[0], np.where(a_raw.max(0) > 0)[0]
        out = np.zeros((H, W, 4), np.uint8)
        if len(ys):
            by0, by1, bx0, bx1 = max(0, ys[0] - 24), min(H, ys[-1] + 25), max(0, xs[0] - 24), min(W, xs[-1] + 25)
            sl = (slice(by0, by1), slice(bx0, bx1))
            a, rgb = a_raw[sl], cut[sl][..., :3].astype(np.float32)
            e = min(1.0, r * 4)                                        # edge clean-up eases off with the last of the light
            ck = float(B.EDGE_CHOKE)
            a1 = ndimage.grey_erosion(a, size=(3, 3)) if ck >= 1 else a
            if ck >= 2.5:
                a1 = ndimage.grey_erosion(a1, size=(3, 3))
            a1 = ndimage.gaussian_filter(a1, 1.0)
            lo_ = .12 + .2 * max(0.0, ck - 1 - (1 if ck >= 2.5 else 0)) if ck >= 1 else .12 * ck
            a1 = np.clip((a1 - lo_) / (1 - lo_), 0, 1)
            for (q0, q1, (x0, y0, x1, y1)) in (B.FLECKS or []):       # optional hand patch, see effect.md
                if not (q0 <= n <= q1):
                    continue
                bx, by = slice(x0 - bx0, x1 - bx0), slice(y0 - by0, y1 - by0)
                mk = (rgb[by, bx] @ LUMA) > 100
                cols = np.where(mk.any(0))[0]
                if not len(cols):
                    continue
                mk[:, :max(0, cols.max() - 10)] = False
                rows = np.where(mk.any(1))[0]
                if mk.sum() > 110 or rows.max() - rows.min() > 18:   # not a fleck (a hand or cuff fills the box)
                    continue
                hole2 = np.zeros(a.shape, bool)
                hole2[by, bx] = mk
                hole2 = ndimage.binary_dilation(hole2, iterations=3)
                okm = ((a1 > .5) & ~hole2 & ((rgb @ LUMA) < 70)).astype(np.float32)
                den = ndimage.gaussian_filter(okm, 5)
                patch = np.dstack([ndimage.gaussian_filter(rgb[..., c] * okm, 5) for c in range(3)]) / np.maximum(den, 1e-3)[..., None]
                rgb = np.where(hole2[..., None], patch, rgb)
                a1 = np.where(hole2, 1.0, a1).astype(np.float32)
            solid = a1
            if gap is not None:
                a1 = a1 * (1 - gap[sl])
            if B.EDGE_SPILL:                                           # outer px are mixed with the bright wall: recolour
                sp = int(B.EDGE_SPILL)                                 # them from just inside the silhouette
                inner = (ndimage.grey_erosion(solid, size=(2 * sp + 1, 2 * sp + 1)) > .95).astype(np.float32)
                den = ndimage.gaussian_filter(inner, .75 * sp)
                fillc = np.dstack([ndimage.gaussian_filter(rgb[..., c] * inner, .75 * sp) for c in range(3)]) / np.maximum(den, 1e-3)[..., None]
                wv = (np.clip(1 - ndimage.gaussian_filter(inner, .3 * sp), 0, 1) * (den > .03))[..., None]
                rgb2 = rgb * (1 - wv) + fillc * wv
            else:
                rgb2 = rgb
            af = a * (1 - e) + a1 * e
            base = (rgb * (1 - e) + rgb2 * e) / 255
            # lit state: lift (soft shoulder so skin highlights do not clip), warm rim on up-facing edges, falloff
            lb, lc, ls = B.SUBJ_LIFT
            x = (base * lb - .5) * lc + .5
            lum = (x * LUMA).sum(-1, keepdims=True)
            x = lum + (x - lum) * ls
            x = np.where(x > .8, .8 + .2 * (1 - np.exp(-(x - .8) / .2)), x)
            wide = ndimage.gaussian_filter(solid, 4)
            above, below = np.roll(wide, 7, axis=0), np.roll(wide, -7, axis=0)
            above[:7] = 0
            yy_, xx_ = np.mgrid[by0:by1, bx0:bx1].astype(np.float32)
            rim_w = 1 - smooth(yy_, top + 2.2 * S['head_h'], top + 3.5 * S['head_h'])
            rim = np.clip(ndimage.gaussian_filter(af * np.clip((below - above) * 1.15, 0, 1) ** 1.3 * rim_w, .8), 0, 1)[..., None]
            x = x * (1 - rim) + (1 - (1 - x) * (1 - warm * B.RIM_GAIN)) * rim
            _, _, fall_f = fields(hx, top, S['pool'], xx_, yy_)
            x = x * (1 - fall_f[..., None]) + fallc * fall_f[..., None]
            x = base * (1 - r) + x * r
            out[sl] = np.dstack([(x.clip(0, 1) * 255 + .5).astype(np.uint8), (af * 255 + .5).astype(np.uint8)])
        e_subj.stdin.write(out.tobytes())

        if n in sheet_f or n in (chk['hair'][0], chk['hand'][0]):
            al = out[..., 3:4].astype(np.float32) / 255
            comp = (room8 * (1 - al) + out[..., :3] * al + .5).astype(np.uint8)
            if n in sheet_f:
                tiles[n] = comp[::6, ::6].copy()
            cw, ch_ = chk['crop']
            for key in ('hair', 'hand'):
                if chk[key][0] == n:
                    _, cx0, cy0 = chk[key]
                    crops[key] = comp[cy0:cy0 + ch_, cx0:cx0 + cw].copy()
    for e_ in (e_room, e_subj):
        e_.stdin.close()
        e_.wait()
    if n + 1 != N:
        sys.exit(f'read {n + 1} frames, clip.json says {N}: a-roll and cutout do not match')

    # ---- check pictures
    cw, ch_ = chk['crop']
    edge = Image.new('RGB', (cw * 2 + 8, ch_ + 30), (20, 20, 20))
    d = ImageDraw.Draw(edge)
    for i, key in enumerate(('hair', 'hand')):
        if key in crops:
            edge.paste(Image.fromarray(crops[key]), (i * (cw + 8), 30))
        d.text((i * (cw + 8) + 6, 9), f'{"head / hair" if key == "hair" else "fastest moving edge (hand)"}  f{chk[key][0]}  1:1', fill=(255, 255, 0))
    edge.save('work/check_edge.jpg', quality=95)
    tw_, th_ = W // 6, H // 6
    ids = sorted(tiles)
    sheet = Image.new('RGB', (tw_ * (len(ids) + 1), th_), (0, 0, 0))
    first = Image.fromarray(tiles[ids[1] if len(ids) > 1 else ids[0]]).convert('RGB')
    d = ImageDraw.Draw(first)
    hx, top, hw, neck = S['head_x'] / 6, S['head_top'] / 6, S['head_w'] / 6, S['neck_y'] / 6
    d.rectangle([hx - hw / 2, top, hx + hw / 2, neck], outline=(0, 255, 0))
    cy_off, rx, ry = (v / 6 for v in S['pool'][:3])
    d.ellipse([hx - rx * B.POOL_EDGE[0], top + cy_off - ry * B.POOL_EDGE[0], hx + rx * B.POOL_EDGE[0], top + cy_off + ry * B.POOL_EDGE[0]], outline=(255, 255, 0))
    l, t, r_, b, y2, r2 = (v / 6 for v in B.SAFE_BOX)
    d.line([l, t, r_, t, r_, y2, r2, y2, r2, b, l, b, l, t], fill=(255, 60, 60))
    _, cx0, cy0 = chk['hand']
    d.rectangle([cx0 / 6, cy0 / 6, (cx0 + cw) / 6, (cy0 + ch_) / 6], outline=(0, 200, 255))
    d.text((4, 4), 'green head, yellow pool,\nred safe zone, blue hand crop', fill=(255, 255, 0))
    sheet.paste(first, (0, 0))
    for i, f in enumerate(ids):
        im = Image.fromarray(tiles[f])
        ImageDraw.Draw(im).text((4, 4), f'f{f}', fill=(255, 255, 0))
        sheet.paste(im, (tw_ * (i + 1), 0))
    sheet.save('work/check_sheet.jpg', quality=90)
    M['baked'] = True
    json.dump(M, open('work/measure.json', 'w'))
    print(f'baked f{f0}..f{f1} -> assets/room_dark.mp4, assets/subject_spot.webm ({N} frames each)')
    print('LOOK at work/check_edge.jpg (full size: no bright halo, no missing hair or fingers) and work/check_sheet.jpg')


if __name__ == '__main__':
    os.makedirs('work', exist_ok=True)
    M = measure()
    if MEASURE_ONLY:
        print('measure only: run prep.py without an argument to bake')
    else:
        bake(M)
