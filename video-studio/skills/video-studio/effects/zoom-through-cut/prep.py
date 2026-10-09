#!/usr/bin/env python3
"""Measure what zoom-through needs from the footage -> work/measure.json, and draw it -> work/measure.jpg.

Run from the slot folder:  PY prep.py
Needs assets/aroll.mp4, assets/subject.webm (their cutout) and clip.json with "cut_frames" (two_shot.py writes both).

  point_a    darkest flat patch on their torso or lap on the LAST frame of shot A, dark all around it too
             (where the camera dives in: hands in front of their chest are avoided)
  point_b    darkest flat patch on their torso on the FIRST frame of shot B  (where shot B opens out from)
  cap_top_a / cap_top_b   y for a caption block just under their chin, taken from the lowest chin across the shot
                          (null when their head cannot be read; build.py drops a block that would pass y 1470)
  cap_x      their centre line (caption centre)

Always open work/measure.jpg: the cross must sit on dark, flat fabric (not skin, not a hand), the green line must be
under their chin in both shots. If not, set POINT_A / POINT_B / "top" by hand in the CLIP block of build.py.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

FF = shutil.which('ffmpeg') or 'ffmpeg'
SW, SH, K = 270, 480, 4          # analysis size and its factor to 1080x1920
CHIN_DROP = 0.25                 # chin bottom = neck row + this share of the head height (top of head to neck);
                                 # the narrowest row sits at the jaw on a close-up and at the chin on a wide shot
CHIN_GAP = 30                    # px of air between the speaker's chin and the caption block
VIEW_H, VIEW_W = 64, 36          # analysis px of shot A the camera still sees on the cut frame (about a ninth of it)


def frames(path, vf, pix, ch, extra=()):
    cmd = [FF, '-v', 'error'] + list(extra) + ['-i', path, '-vf', vf, '-f', 'rawvideo', '-pix_fmt', pix, '-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (SW * SH * ch)
    return np.frombuffer(raw[:n * SW * SH * ch], np.uint8).reshape((n, SH, SW, ch) if ch > 1 else (n, SH, SW))


def body_profile(mask):
    """Head top, neck row, head width and centre from one silhouette (analysis px). None when it cannot be read."""
    rows = np.where(mask.sum(axis=1) > 5)[0]
    if len(rows) < 20:
        return None
    top = int(rows[0])
    cx = float(np.median(np.where(mask[top:top + 6].any(axis=0))[0]))
    width = np.zeros(SH, np.float32)
    centre = np.full(SH, cx, np.float32)
    for y in range(top, SH):                       # the run of mask pixels that contains the speaker's centre line
        xs = np.where(mask[y])[0]
        if len(xs) == 0:
            break
        breaks = np.where(np.diff(xs) > 2)[0]
        runs = np.split(xs, breaks + 1)
        run = min(runs, key=lambda r: 0 if r[0] <= cx <= r[-1] else min(abs(r[0] - cx), abs(r[-1] - cx)))
        width[y] = len(run)
        centre[y] = (run[0] + run[-1]) / 2.0
        if y - top < 40:
            cx = .8 * cx + .2 * centre[y]
    width = ndimage.uniform_filter1d(width, 3)
    widest = 0.0
    for y in range(top + 8, SH):
        widest = max(widest, float(width[y - 6]))
        step = int(np.clip(.2 * widest, 6, 30))     # look back a fifth of a head: works for a wide shot and a close-up
        if y - step <= top:
            continue
        above = width[y - step]
        if width[y] == 0 or above == 0:
            break
        # shoulders: the silhouette widens fast (22% in one step) once we are at least 0.7 head-widths below the top
        if y - top > .7 * above and width[y] > 1.22 * above:
            peak = top + int(np.argmax(width[top:y - step + 1]))
            neck = peak + int(np.argmin(width[peak:y]))
            return {'top': top, 'neck': neck, 'head_w': float(width[peak]), 'cx': float(centre[neck])}
    return None


def dive_point(rgb, mask, prof, dive=False):
    """Centre of the darkest, flattest patch of their torso (analysis px).

    dive=True (shot A): the camera ends up INSIDE this patch, so what counts is everything it sees around the point
    on the cut frame (VIEW_H x VIEW_W), not just the patch. Hands in front of their chest lose to a dark thigh or a
    clear stretch of jacket, and the search reaches down to their lap."""
    lum = rgb.astype(np.float32) @ np.array([.2126, .7152, .0722], np.float32)
    if prof:
        head_h = max(12, prof['neck'] - prof['top'])
        reach = 2.6 if dive else 1.35
        y0, y1 = prof['neck'] + int(.15 * head_h), min(SH - 2, prof['neck'] + int(reach * head_h))
        win = int(np.clip(.34 * prof['head_w'], 7, 46)) | 1
        cx = prof['cx']
    else:                                           # no readable head: the middle of whatever the cutout holds
        ys, xs = np.where(mask)
        if len(ys) == 0:
            return None
        y0, y1 = int(np.percentile(ys, 30)), int(np.percentile(ys, 70))
        win, cx = 15, float(np.median(xs))
    if y1 - y0 < win:
        y0 = max(0, y1 - win - 2)
    mean = ndimage.uniform_filter(lum, win)
    std = np.sqrt(np.maximum(ndimage.uniform_filter(lum * lum, win) - mean * mean, 0))
    inside = ndimage.uniform_filter(mask.astype(np.float32), win)
    xx = np.abs(np.arange(SW, dtype=np.float32) - cx)[None, :] / SW
    score = mean + 2.0 * std + 60.0 * xx            # dark, flat, near the speaker's centre line
    if dive:                                        # ... and dark all around it, with a mild pull towards the speaker's chest
        view = ndimage.uniform_filter(lum, (VIEW_H, VIEW_W))
        yy = np.maximum(0.0, np.arange(SH, dtype=np.float32) - y0)[:, None] / SH
        score = .5 * mean + .5 * view + 2.0 * std + 60.0 * xx + 40.0 * yy
    band = np.zeros_like(mask)
    band[y0:y1 + 1] = True
    for need in (.985, .9, .6):
        ok = band & (inside >= need)
        if ok.any():
            y, x = np.unravel_index(np.argmin(np.where(ok, score, 1e9)), score.shape)
            return int(x), int(y), win
    return None


def main():
    if not os.path.exists('assets/subject.webm'):
        sys.exit('assets/subject.webm is missing: run two_shot.py without --no-cutout, or set POINT_A / POINT_B by hand')
    clip = json.load(open('clip.json'))
    cut = (clip.get('cut_frames') or [None])[0]
    if cut is None:
        sys.exit('clip.json has no "cut_frames": run two_shot.py first')
    rgb = frames('assets/aroll.mp4', 'scale=%d:%d:flags=area' % (SW, SH), 'rgb24', 3)
    alpha = frames('assets/subject.webm', 'alphaextract,scale=%d:%d:flags=area' % (SW, SH), 'gray', 1, ('-c:v', 'libvpx-vp9'))
    n = min(len(rgb), len(alpha))
    if n != clip['frames'] or len(rgb) != len(alpha):
        print('warning: a-roll %d frames, cutout %d, clip.json %d' % (len(rgb), len(alpha), clip['frames']))
    masks = alpha[:n] > 127
    out, draw = {'cut': cut}, {}
    for shot, idx, span in (('a', cut - 1, range(0, cut)), ('b', cut, range(cut, n))):
        prof = body_profile(masks[idx])
        pt = dive_point(rgb[idx], ndimage.binary_erosion(masks[idx], iterations=2), prof, dive=(shot == 'a'))
        if pt is None:
            sys.exit('no subject found on frame %d: set POINT_%s by hand in the CLIP block' % (idx, shot.upper()))
        out['point_' + shot] = [pt[0] * K + K // 2, pt[1] * K + K // 2]
        profs = [p for p in (body_profile(masks[i]) for i in list(span)[::5]) if p]
        top = None
        if len(profs) >= max(2, len(list(span)[::5]) // 2):
            # the lowest chin in the shot (ignoring a stray frame); the chin hangs ~0.3 head-heights under the
            # narrowest row of the silhouette
            low = [p['neck'] + CHIN_DROP * (p['neck'] - p['top']) for p in profs]
            top = int(np.percentile(low, 90) * K) + CHIN_GAP        # build.py drops the block if it cannot fit
        out['cap_top_' + shot] = top
        draw[shot] = (idx, pt, prof, top)
        print('shot %s frame %d: point %s  win %dpx  neck %s  caption top %s'
              % (shot.upper(), idx, out['point_' + shot], pt[2] * K, prof['neck'] * K if prof else None, top))
    cxs = [d[2]['cx'] * K for d in draw.values() if d[2]]
    out['cap_x'] = int(np.mean(cxs)) if cxs else 520
    os.makedirs('work', exist_ok=True)
    json.dump(out, open('work/measure.json', 'w'), indent=1)

    tiles = []
    for shot in ('a', 'b'):
        idx, pt, prof, top = draw[shot]
        raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-vf', "select='eq(n,%d)',scale=540:960" % idx,
                              '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
        im = Image.frombytes('RGB', (540, 960), raw)
        d = ImageDraw.Draw(im)
        for y in (110, 735):                                        # safe zone top / bottom
            d.line([(0, y), (540, y)], fill=(255, 60, 60), width=1)
        x, y, win = pt[0] * 2 + 1, pt[1] * 2 + 1, pt[2]
        d.rectangle([x - win, y - win, x + win, y + win], outline=(255, 235, 60), width=2)
        d.line([(x - 26, y), (x + 26, y)], fill=(255, 235, 60), width=2)
        d.line([(x, y - 26), (x, y + 26)], fill=(255, 235, 60), width=2)
        if prof:
            d.line([(0, prof['neck'] * 2), (540, prof['neck'] * 2)], fill=(90, 170, 255), width=1)
        if top is not None:
            d.line([(40, top // 2), (500, top // 2)], fill=(80, 230, 120), width=3)
        d.text((12, 12), 'shot %s  frame %d' % (shot.upper(), idx), fill=(255, 235, 60))
        tiles.append(im)
    sheet = Image.new('RGB', (1080, 960))
    sheet.paste(tiles[0], (0, 0))
    sheet.paste(tiles[1], (540, 0))
    sheet.save('work/measure.jpg', quality=90)
    print('wrote work/measure.json and work/measure.jpg (yellow = dive point, blue = neck, green = caption top)')


if __name__ == '__main__':
    main()
