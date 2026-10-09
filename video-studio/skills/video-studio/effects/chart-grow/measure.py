#!/usr/bin/env python3
"""chart-grow / measure.py: everything build.py places the chart with. numpy + scipy + Pillow only. Run once per slot.

    measure.py           words with their measured start frame, where the speaker is, how much the camera moves
    measure.py -v        also prints the loudness of every frame (to settle the kick word by eye)

Reads  assets/subject.webm (cutout alpha), assets/aroll.mp4 (picture + sound), words.json, clip.json
Writes work/measure.json  frames, words (+ `frame` = start snapped to the sound), head box, camera track, drift
       work/measure.npz   the speaker's silhouette on every frame and the wall brightness, both at 1/8 size
       work/measure.jpg   first / middle / last frame with the silhouette edge and the safe zone drawn in
Camera track: patches of wall (never the speaker) from the middle frame are found again in every frame by
normalised correlation, then a move + zoom + roll is fitted to them. No optical flow library.
"""
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
FPS = 30
MW, MH = 135, 240            # silhouette grid (1/8 size)
TW, TH = 540, 960            # camera track size (1/2 size)
P, R = 40, 8                 # patch side and search reach in track pixels (reach = 16 px of camera move per frame)


def decode(name, w, h, alpha=False):
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + \
          ['-i', os.path.join('assets', name), '-vf', ('alphaextract,' if alpha else '') + f'scale={w}:{h}:flags=area',
           '-pix_fmt', 'gray', '-f', 'rawvideo', '-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[:n * w * h], np.uint8).reshape(n, h, w)


def loudness():
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    x = np.frombuffer(raw[:len(raw) // 2 * 2], np.int16).astype(np.float32) / 32768
    hop = 480                                                    # 10 ms
    n = len(x) // hop
    rms = np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
    return 20 * np.log10(rms + 1e-9)


def word_frames(words, db):
    """Whisper word starts run up to 0.35 s early. Snap each to the biggest rise of the voice between 0.10 s before
    and 0.40 s after Whisper's start (never before the word in front). No clear rise = keep Whisper's time."""
    sm = np.convolve(db, np.ones(3) / 3, mode='same')
    prev = -1
    for i, w in enumerate(words):
        a = max(prev + 4, int(w['start'] * 100) - 10, 2)
        b = min(len(sm) - 2, int(min(w['start'] + .40, w['end'] - .05) * 100))     # never into the next word
        rises = [(k, sm[k + 1] - sm[k - 2]) for k in range(a, max(a, b)) if sm[k + 1] > -45]
        jump = max((j for _, j in rises), default=0.0)
        best = next((k for k, j in rises if j >= .7 * jump), None)                 # first big rise, not a later syllable
        if best is None or jump < 6:
            best = max(int(w['start'] * 100), prev + 4)
        prev = best
        w['onset'] = round(best / 100, 2)
        w['frame'] = int(round(best / 100 * FPS))
        w['rise_db'] = round(float(jump), 1)
    return words


def head_box(m):
    """rough head box from one silhouette (1/8 grid): top row, then down to where the shoulders open out"""
    rows = np.where(m.sum(axis=1) >= 2)[0]
    if len(rows) == 0:
        return None
    top = int(rows[0])
    wid = m.sum(axis=1)
    bot = min(MH - 1, top + 40)
    for r in range(top + 8, min(MH, top + 80)):
        if wid[r] > 1.6 * np.median(wid[top + 3:r]):
            bot = r
            break
    cols = np.where(m[top:bot].any(axis=0))[0]
    return [int(cols[0]) * 8, top * 8, int(cols[-1] + 1) * 8, bot * 8]


def camera_track(gray, masks):
    """[a, b, tx, ty] per frame (full-size px): a point p of the middle frame sits at (a*px - b*py + tx, b*px + a*py + ty)."""
    n = len(gray)
    ref = n // 2
    g = gray.astype(np.float32)
    big = [np.kron(ndimage.binary_dilation(m, iterations=5), np.ones((4, 4), bool)) for m in masks]   # speaker, grown 40 px
    gy, gx = np.gradient(g[ref])
    cand = []
    for y in range(R + 2, TH - P - R - 2, 20):
        for x in range(R + 2, TW - P - R - 2, 20):
            if big[ref][y:y + P, x:x + P].any():
                continue
            sx, sy = gx[y:y + P, x:x + P], gy[y:y + P, x:x + P]
            a, b, c = float((sx * sx).sum()), float((sy * sy).sum()), float((sx * sy).sum())
            cand.append(((a + b - math.sqrt((a - b) ** 2 + 4 * c * c)) / 2, x, y))       # corner strength, not just an edge
    cand.sort(reverse=True)
    cand = [c for c in cand[:70] if c[0] > .01 * cand[0][0]] if cand else []
    ident = [1.0, 0.0, 0.0, 0.0]
    if len(cand) < 8:
        return [ident] * n, ref, dict(patches=len(cand), note='too little wall texture to track: chart is pinned to the screen')
    tpl = []
    for _, x, y in cand:
        t = g[ref][y:y + P, x:x + P]
        t = t - t.mean()
        tpl.append((t, float(np.sqrt((t * t).sum())) + 1e-6))
    pc = np.array([[x + P / 2, y + P / 2] for _, x, y in cand], np.float64)
    out = [None] * n
    out[ref] = ident
    low = n
    for order in (range(ref + 1, n), range(ref - 1, -1, -1)):
        cur = ident
        for f in order:
            a, b, tx, ty = cur
            src, dst = [], []
            for i, (t, tn) in enumerate(tpl):
                qx = a * pc[i, 0] - b * pc[i, 1] + tx
                qy = b * pc[i, 0] + a * pc[i, 1] + ty
                x0, y0 = int(round(qx - P / 2)) - R, int(round(qy - P / 2)) - R
                if x0 < 0 or y0 < 0 or x0 + P + 2 * R > TW or y0 + P + 2 * R > TH:
                    continue
                if big[f][y0 + R:y0 + R + P, x0 + R:x0 + R + P].mean() > .1:
                    continue
                win = sliding_window_view(g[f][y0:y0 + P + 2 * R, x0:x0 + P + 2 * R], (P, P))
                num = np.einsum('ijkl,kl->ij', win, t)
                var = (win * win).sum(axis=(2, 3)) - win.sum(axis=(2, 3)) ** 2 / (P * P)
                sc = num / (np.sqrt(np.maximum(var, 1e-6)) * tn)
                j, k = np.unravel_index(int(sc.argmax()), sc.shape)
                if sc[j, k] < .6 or j in (0, 2 * R) or k in (0, 2 * R):
                    continue
                dy = .5 * (sc[j - 1, k] - sc[j + 1, k]) / (sc[j - 1, k] - 2 * sc[j, k] + sc[j + 1, k] - 1e-9)
                dx = .5 * (sc[j, k - 1] - sc[j, k + 1]) / (sc[j, k - 1] - 2 * sc[j, k] + sc[j, k + 1] - 1e-9)
                src.append(pc[i])
                dst.append([x0 + k + dx + P / 2, y0 + j + dy + P / 2])
            src, dst = np.array(src), np.array(dst)
            keep = np.ones(len(src), bool)
            sol = None
            for _ in range(4):
                if keep.sum() < 6:
                    sol = None
                    break
                s_, d_ = src[keep], dst[keep]
                A = np.zeros((2 * len(s_), 4))
                A[0::2] = np.c_[s_[:, 0], -s_[:, 1], np.ones(len(s_)), np.zeros(len(s_))]
                A[1::2] = np.c_[s_[:, 1], s_[:, 0], np.zeros(len(s_)), np.ones(len(s_))]
                sol = np.linalg.lstsq(A, d_.reshape(-1), rcond=None)[0]
                px = sol[0] * src[:, 0] - sol[1] * src[:, 1] + sol[2]
                py = sol[1] * src[:, 0] + sol[0] * src[:, 1] + sol[3]
                res = np.hypot(px - dst[:, 0], py - dst[:, 1])
                keep = res < max(.5, 2.5 * float(np.median(res[keep])))
            if sol is not None:
                cur = [float(v) for v in sol]
                low = min(low, int(keep.sum()))
            out[f] = cur
    arr = np.array(out)
    arr[:, 2:] *= 1080 / TW
    pad = np.pad(arr, ((3, 3), (0, 0)), mode='edge')                 # 1-frame gaussian: kills match jitter
    ker = np.exp(-np.arange(-3, 4) ** 2 / 2.0)
    arr = np.stack([np.convolve(pad[:, c], ker / ker.sum(), mode='valid') for c in range(4)], axis=1)
    return [[round(float(v), 6) for v in r] for r in arr], ref, dict(patches=len(cand), fewest_matched=low)


def main():
    if not os.path.exists('assets/subject.webm'):
        sys.exit('chart-grow needs the cutout (assets/subject.webm): make the slot without --no-cutout')
    os.makedirs('work', exist_ok=True)
    nf = json.load(open('clip.json'))['frames']
    alpha = decode('subject.webm', MW, MH, alpha=True)
    if len(alpha) != nf:
        sys.exit(f'cutout has {len(alpha)} frames, the slot has {nf}: the cutout would drift. Re-make the slot.')
    masks = alpha > 96
    gray = decode('aroll.mp4', TW, TH)[:nf]
    luma = np.asarray(Image.fromarray(gray[nf // 2]).resize((MW, MH), Image.BOX))

    db = loudness()
    words = json.load(open('words.json')) if os.path.exists('words.json') else []
    words = word_frames(words, db)
    track, ref, info = camera_track(gray, masks)
    arr = np.array(track)
    cx = arr[:, 0] * 540 - arr[:, 1] * 960 + arr[:, 2]
    cy = arr[:, 1] * 540 + arr[:, 0] * 960 + arr[:, 3]
    drift = float(np.hypot(cx - cx[0], cy - cy[0]).max())
    zoom = float(np.hypot(arr[:, 0], arr[:, 1]).max() / np.hypot(arr[:, 0], arr[:, 1]).min() - 1)
    still = drift < 3 and zoom < .004
    union = masks.any(axis=0)
    hb = head_box(masks[nf // 2])
    share = float(union[27:184, 4:131].mean())                     # how much of the safe zone the speaker ever covers
    np.savez_compressed('work/measure.npz', masks=masks, luma=luma)
    json.dump(dict(frames=nf, words=words, head=hb, track=track, track_ref=ref, track_info=info, drift_px=round(drift, 1),
                   zoom=round(zoom, 4), still=bool(still), covered=round(share, 3),
                   voice_db=round(float(np.sort(db)[-10:].mean()), 1)), open('work/measure.json', 'w'))     # the speaker's loudest 0.1 s

    # picture: first / middle / last frame, silhouette edge, safe zone
    full = decode('aroll.mp4', 360, 640)
    sheet = Image.new('RGB', (1080, 640))
    for k, f in enumerate((0, nf // 2, nf - 1)):
        im = Image.fromarray(full[min(f, len(full) - 1)]).convert('RGB')
        d = ImageDraw.Draw(im)
        edge = masks[f] ^ ndimage.binary_erosion(masks[f])
        for y, x in zip(*np.where(edge)):
            d.rectangle([x * 8 / 3, y * 8 / 3, x * 8 / 3 + 2, y * 8 / 3 + 2], fill=(250, 230, 122))
        d.line([(35 / 3, 220 / 3), (1045 / 3, 220 / 3), (1045 / 3, 1155 / 3), (980 / 3, 1155 / 3), (980 / 3, 1470 / 3),
                (35 / 3, 1470 / 3), (35 / 3, 220 / 3)], fill=(255, 90, 90), width=2)
        sheet.paste(im, (k * 360, 0))
    sheet.save('work/measure.jpg', quality=85)

    if '-v' in sys.argv:
        for f in range(nf):
            seg = db[int(f * 100 / FPS):int((f + 1) * 100 / FPS) + 1]
            d = float(seg.max()) if len(seg) else -90
            mark = ' '.join(w['text'] for w in words if w['frame'] == f)
            print(f'{f:4d} {f / FPS:5.2f}s {d:6.1f} dB ' + '#' * max(0, int((d + 60) / 1.5)) + ('   <- ' + mark if mark else ''))
    print(f'{nf} frames ({nf / FPS:.2f}s)')
    print(f'{"word":14s} {"whisper":>7s} {"frame":>5s}  rise dB')
    for w in words:
        print(f"{w['text']:14s} {int(round(w['start'] * FPS)):7d} {w['frame']:5d}  {w['rise_db']:6.1f}" +
              ('   (no clear rise: Whisper kept, check with -v)' if w['rise_db'] < 6 else ''))
    print(f'speaker: head box x {hb[0]}..{hb[2]}  y {hb[1]}..{hb[3]} (middle frame); covers {share:.0%} of the safe zone over the slot'
          if hb else 'speaker: NOT FOUND in the cutout')
    print(f'camera: {"still" if still else "moving"} (drift {drift:.1f} px, zoom {zoom * 100:.2f}%, {info}).',
          'Chart is pinned.' if still else 'Chart is glued to the wall with the track.')
    if share > .62:
        print('!! tight shot: the speaker covers most of the frame. build.py will say if there is any wall to draw on.')
    print('wrote work/measure.json, work/measure.npz, work/measure.jpg')


main()
