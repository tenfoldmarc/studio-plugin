#!/usr/bin/env python3
"""freeze-label tools. build.py imports this file; run on its own it prints the slot's words with their start frames
(snapped to the audio), which is what the CLIP block in build.py wants:

    PY bake_freeze.py

What lives here (numpy, scipy, Pillow, ffmpeg only):
  onsets()      word starts snapped to the audio
  pick_hold()   scores the frames right after the freeze word (sharpness, head motion) and picks the one to hold;
                writes work/freeze_pick.jpg so a person can check the eyes
  measure()     head box, neck, tie points (cap, head sides, shoulders, chest, hands) from the cutout of the HELD frame
  bake()        the frozen plates as VIDEOS made from the a-roll's own YUV pixels (assets/freeze/plain.mp4 and
                treat.mp4), so the renderer colours them exactly like the live picture
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
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
W, H, FPS = 1080, 1920, 30
AROLL = os.path.join(HERE, 'assets', 'aroll.mp4')
SUBJECT = os.path.join(HERE, 'assets', 'subject.webm')
SIZE = {'gray': W * H, 'rgb24': W * H * 3, 'yuv444p': W * H * 3, 'yuv420p': W * H * 3 // 2}
# the freeze look: room blur (px), dim at the speaker / mid / frame edge (0 = none), soft shadow behind the speaker.
# Colour is never touched: the frozen picture stays in full colour in every look.
LOOKS = {'off': None,
         'subtle': dict(blur=3.5, dim=(.05, .16, .28), shadow=.18),
         'strong': dict(blur=5.5, dim=(.20, .40, .58), shadow=.30)}


def stop(msg):
    print('!! ' + msg)
    sys.exit(1)


def grab(src, a, b, pix, alpha=False):
    """frames a..b (inclusive) of a slot video as raw bytes, one item per frame"""
    vf = f"select='between(n,{a},{b})'" + (f',alphaextract,scale={W}:{H}' if alpha else '')
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + \
          ['-i', src, '-vf', vf, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', pix, '-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    n, size = b - a + 1, SIZE[pix]
    if len(raw) != n * size:
        stop(f'could not read frames {a}..{b} of {os.path.basename(src)} (got {len(raw) // size} of {n}). '
             + ('Is the cutout finished (assets/.cutout_done)?' if alpha else 'Is assets/aroll.mp4 1080x1920?'))
    return [raw[i * size:(i + 1) * size] for i in range(n)]


def alpha_of(f):
    return np.frombuffer(grab(SUBJECT, f, f, 'gray', alpha=True)[0], np.uint8).reshape(H, W).astype(np.float32) / 255


def tags():
    out = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=pix_fmt,color_range,color_space,color_transfer,color_primaries', '-of', 'json', AROLL],
                         capture_output=True, text=True).stdout
    return json.loads(out)['streams'][0]


# ---- words ---------------------------------------------------------------------------------------------------------
def onsets():
    """words.json plus `onset`: the word start snapped to the audio (spectral flux near Whisper's time)"""
    wp = os.path.join(HERE, 'words.json')
    if not os.path.exists(wp):
        return []
    words = json.load(open(wp))
    raw = subprocess.run([FF, '-v', 'error', '-i', AROLL, '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop, win = 160, 512
    k = (len(a) - win) // hop
    for w in words:
        w['onset'] = w['start']
    if k < 8:
        return words
    idx = np.arange(win)[None, :] + hop * np.arange(k)[:, None]
    mag = np.abs(np.fft.rfft(a[idx] * np.hanning(win), axis=1))[:, 1:257]
    band = np.log1p(200 * mag.reshape(k, 32, 8).mean(2))
    flux = np.r_[0, 0, np.maximum(band[2:] - band[:-2], 0).sum(1)]
    for w in words:
        c = w['start'] * 100
        i = np.arange(max(2, int(c) - 14), min(k, int(c) + 22))
        if i.size:
            b = int(i[np.argmax(flux[i] * np.exp(-.5 * ((i - c) / 10.0) ** 2))])
            w['onset'] = round((b * hop + win / 2 - hop) / 16000, 3)
    return words


def word_frame(say, words, what):
    """'word' or 'word#2' (second time it is said) or a frame number -> frame"""
    if isinstance(say, (int, float)) and not isinstance(say, bool):
        return int(say)
    name, _, nth = str(say).partition('#')
    norm = lambda t: ''.join(ch for ch in t.lower() if ch.isalnum())
    hits = [w for w in words if norm(w['text']) == norm(name)]
    if len(hits) < int(nth or 1):
        stop(f"{what}: '{say}' is not in the slot's words. Words (frame): "
             + ' '.join(f"{w['text']}({round(w['onset'] * FPS)})" for w in words))
    return int(round(hits[int(nth or 1) - 1]['onset'] * FPS))


# ---- the speaker on one frame ----------------------------------------------------------------------------------------
def silhouette(m):
    """walk down the cutout from its top, following the run of pixels that holds the head.
    -> top row, left / right edge per row, head width (widest row before the neck), neck row (or None)"""
    solid = (m.sum(1) >= 8).astype(np.float32)
    ok = np.flatnonzero(np.convolve(solid, np.ones(7, np.float32), 'valid') >= 7)
    if ok.size == 0:
        return None
    top, c, L, R = int(ok[0]), None, [], []
    for y in range(top, H):
        idx = np.flatnonzero(m[y])
        if idx.size == 0:
            break
        cut = np.flatnonzero(np.diff(idx) > 1)
        s, e = np.r_[idx[0], idx[cut + 1]], np.r_[idx[cut], idx[-1]]
        k = int(np.argmax(e - s)) if c is None else int(np.argmin(np.where((s <= c) & (c <= e), 0, np.minimum(abs(s - c), abs(e - c)))))
        L.append(s[k]); R.append(e[k]); c = (s[k] + e[k]) / 2
    L, R = np.array(L, float), np.array(R, float)
    ws = ndimage.uniform_filter1d(R - L + 1, 9, mode='nearest')
    cm = np.maximum.accumulate(ws)
    k = np.arange(len(ws))
    cand = np.flatnonzero((k > 0.6 * cm) & (ws < 0.88 * cm))
    hw = neck = None
    if cand.size:
        j = int(cand[0]); hw = float(cm[j])
        seg = ws[j:min(len(ws), int(2.2 * hw))]
        sh = np.flatnonzero(seg > 1.2 * hw)
        end = int(sh[0]) if sh.size else len(seg)
        neck = j + (int(np.argmin(seg[:end])) if end > 0 else 0)
    return top, L, R, hw, neck


def _inside(m, x, y, cx, cy):
    """slide a point towards (cx, cy) until it sits on the cutout"""
    for t in np.linspace(0, 1, 40):
        px, py = x + (cx - x) * t, y + (cy - y) * t
        if 0 <= int(py) < H and 0 <= int(px) < W and m[int(py), int(px)]:
            return float(px), float(py)
    return None


def _hands(yuv, m, top, neck, hw, hcx, ncx):
    """skin-coloured areas below the neck, colour sampled from the speaker's own face -> hand_left / hand_right"""
    Y, U, V = yuv
    y0, y1, x0, x1 = int(top + .42 * neck), int(top + .82 * neck), int(hcx - .2 * hw), int(hcx + .2 * hw)
    fm = m[y0:y1, x0:x1]
    if fm.sum() < 60:
        return {}
    ym, um, vm = (float(np.median(c[y0:y1, x0:x1][fm])) for c in (Y, U, V))
    s = m & (np.abs(U - um) < 7) & (np.abs(V - vm) < 8) & (Y > .5 * ym) & (Y < 1.7 * ym)
    s[:int(top + neck + .25 * hw)] = False
    s = ndimage.binary_closing(ndimage.binary_opening(s, iterations=2), iterations=3)
    lab, n = ndimage.label(s)
    if n == 0:
        return {}
    area = ndimage.sum(s, lab, range(1, n + 1))
    cen = ndimage.center_of_mass(s, lab, range(1, n + 1))
    got = []
    for i in np.argsort(-area):
        cy, cx = cen[i]
        collar = abs(cx - ncx) < .45 * hw and cy < top + neck + .9 * hw
        if area[i] >= (.2 * hw) ** 2 and not collar and len(got) < 2:
            if lab[int(cy), int(cx)] != i + 1:                    # centroid off the blob: nearest blob pixel
                py, px = np.nonzero(lab == i + 1)
                j = int(np.argmin((py - cy) ** 2 + (px - cx) ** 2))
                cy, cx = py[j], px[j]
            got.append((float(cx), float(cy)))
    got.sort()
    if len(got) == 2:
        return {'hand_left': got[0], 'hand_right': got[1]}
    return {('hand_left' if g[0] < ncx else 'hand_right'): g for g in got}


def measure(a, yuv=None, head=None):
    """a = cutout alpha (0..1) of one frame. -> dict(box, head, neck, hw, anchors) in picture px.
    head = optional (x0, y0, x1, y1) typed by hand when the outline cannot be found."""
    lab, n = ndimage.label(a > .5)
    if n == 0:
        stop('the cutout is empty on this frame: no speaker to label. Check assets/subject.webm.')
    m = lab == (1 + int(np.argmax(ndimage.sum(a > .5, lab, range(1, n + 1)))))
    ys, xs = np.nonzero(m)
    box = (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1))
    if head is not None:
        hx0, top, hx1, hy1 = (float(v) for v in head)
        hw, neck = hx1 - hx0, int(hy1 - top)
        ncx = (hx0 + hx1) / 2
    else:
        sil = silhouette(m)
        if sil is None or sil[3] is None or sil[4] is None or not 40 <= sil[3] <= 950 or sil[4] < .5 * sil[3]:
            return dict(box=box, head=None, mask=m, anchors={})
        top, Lr, Rr, hw, neck = sil
        hx0, hx1 = float(np.percentile(Lr[:neck], 4)), float(np.percentile(Rr[:neck], 96))
        hw, hy1 = hx1 - hx0, float(top + neck)
        ncx = float(Lr[neck] + Rr[neck]) / 2
    hcx, hh = (hx0 + hx1) / 2, float(neck)
    # head points sit ABOVE the brow line (cap, temples), never on the face
    A = {'cap': (hcx, top + .10 * hh)}
    ty = int(top + .20 * hh)
    run = np.flatnonzero(m[ty, max(0, int(hx0) - 4):int(hx1) + 4]) + max(0, int(hx0) - 4)
    if run.size:
        A['head_left'], A['head_right'] = (run[0] + .12 * hw, float(ty)), (run[-1] - .12 * hw, float(ty))
    ch = _inside(m, ncx, top + neck + .95 * hw, ncx, top + neck + .2 * hw)
    if ch:
        A['chest'] = ch
    for name, sx in (('shoulder_left', -1), ('shoulder_right', 1)):
        p = _inside(m, ncx + sx * .75 * hw, top + neck + .42 * hw, ncx, top + neck + .42 * hw)
        if p:
            A[name] = p
    if yuv is not None:
        A.update(_hands(yuv, m, top, neck, hw, hcx, ncx))
    return dict(box=box, head=(hx0, float(top), hx1, hy1), hw=hw, hh=hh, mask=m, anchors=A)


# ---- which frame to hold -------------------------------------------------------------------------------------------
def pick_hold(freeze_f, n, head, hold):
    """hold = 'auto' or a number of frames after the freeze word. -> (held frame, warnings)"""
    a, b = max(0, freeze_f - 3), min(n - 1, freeze_f + 8)
    g = [np.frombuffer(x, np.uint8).reshape(H, W).astype(np.float32) for x in grab(AROLL, a, b, 'gray')]
    x0, y0, x1, y1 = (int(v) for v in head)
    cr = [im[max(0, y0):y1, max(0, x0):x1] for im in g]
    sharp = np.array([np.abs(np.diff(c, axis=1)).mean() + np.abs(np.diff(c, axis=0)).mean() for c in cr])
    d = np.array([np.abs(cr[i] - cr[i - 1]).mean() for i in range(1, len(cr))])
    move = np.array([max(d[max(0, i - 1)], d[min(len(d) - 1, i)]) for i in range(len(cr))])
    rel = sharp / sharp.max()
    cands = list(range(freeze_f, min(n - 1, freeze_f + 5) + 1))
    if hold == 'auto':
        f = max(cands, key=lambda c: rel[c - a] - .02 * (c - freeze_f) - .01 * move[c - a])
    else:
        f = min(n - 1, freeze_f + int(hold))
    warn = []
    if rel[f - a] < .86:
        warn.append(f'held frame {f} is soft: {rel[f - a]:.0%} as sharp as the sharpest frame nearby (motion blur). '
                    f'The sharpest is HOLD = {int(np.argmax(rel[[c - a for c in cands]]))}: check its eyes on work/freeze_pick.jpg first.')
    if move[f - a] > 4 and move[f - a] > 2 * np.median(move):
        warn.append(f'the head is moving fast on held frame {f} (frame difference {move[f - a]:.1f}): look for blur.')
    # contact sheet of the candidates: the eyes cannot be measured, a person has to look
    pw = x1 - x0
    px0, px1, py0, py1 = max(0, x0 - pw // 4), min(W, x1 + pw // 4), max(0, y0 - pw // 6), min(H, y1 + pw // 6)
    tw = 180
    th = int(tw * (py1 - py0) / (px1 - px0))
    sheet = Image.new('RGB', (tw * len(cands), th + 26), (20, 22, 28))
    dr = ImageDraw.Draw(sheet)
    for i, c in enumerate(cands):
        im = Image.fromarray(g[c - a][py0:py1, px0:px1].astype(np.uint8)).resize((tw, th), Image.LANCZOS)
        sheet.paste(im, (i * tw, 26))
        dr.text((i * tw + 6, 7), f"f{c}  sharp {rel[c - a]:.0%}" + ('  HELD' if c == f else ''), fill=(250, 230, 122) if c == f else (220, 220, 220))
        if c == f:
            dr.rectangle((i * tw, 26, i * tw + tw - 1, th + 25), outline=(250, 230, 122), width=3)
    sheet.save(os.path.join(HERE, 'work', 'freeze_pick.jpg'), quality=88)
    return f, warn


# ---- the frozen plates -----------------------------------------------------------------------------------------------
def _encode(frame_bytes, pix, n, out, tg):
    # the a-roll's colour tags go on the INPUT side: as output options ffmpeg converts the pixels (a visible colour jump)
    cmd = [FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', pix, '-s', f'{W}x{H}', '-r', str(FPS)]
    for opt, key in (('-color_range', 'color_range'), ('-colorspace', 'color_space'), ('-color_primaries', 'color_primaries'),
                     ('-color_trc', 'color_transfer')):
        if tg.get(key) and tg[key] != 'unknown':
            cmd += [opt, tg[key]]
    cmd += ['-i', '-', '-c:v', 'libx264', '-crf', '12', '-preset', 'fast', '-g', '15', '-pix_fmt', 'yuv420p']
    p = subprocess.Popen(cmd + ['-an', out], stdin=subprocess.PIPE)
    for _ in range(n):
        p.stdin.write(frame_bytes)
    p.stdin.close()
    if p.wait() != 0:
        stop(f'ffmpeg could not write {out}')


def bake(hold, n, look, a, centre):
    """plain.mp4 = the held frame n times, bit for bit the a-roll's pixels. treat.mp4 = the same frame with the room
    softened and dimmed behind the speaker (all the maths in the a-roll's own YUV, so no colour matrix is involved)."""
    out_dir = os.path.join(HERE, 'assets', 'freeze')
    os.makedirs(out_dir, exist_ok=True)
    st = os.stat(AROLL)
    key = json.dumps([hold, n, look, LOOKS.get(look), st.st_size, int(st.st_mtime), int(os.stat(SUBJECT).st_mtime), 3])
    kp = os.path.join(HERE, 'work', 'freeze_key.json')
    have = os.path.exists(os.path.join(out_dir, 'plain.mp4')) and (look == 'off' or os.path.exists(os.path.join(out_dir, 'treat.mp4')))
    if have and os.path.exists(kp) and open(kp).read() == key:
        return False
    tg = tags()
    if tg.get('pix_fmt') != 'yuv420p':
        stop(f"assets/aroll.mp4 is {tg.get('pix_fmt')}, expected yuv420p (make the slot with fx_new.py).")
    _encode(grab(AROLL, hold, hold, 'yuv420p')[0], 'yuv420p', n, os.path.join(out_dir, 'plain.mp4'), tg)
    subprocess.run([FF, '-v', 'error', '-y', '-i', AROLL, '-vf', f"select='eq(n,{hold})'", '-frames:v', '1', '-q:v', '3',
                    os.path.join(HERE, 'work', 'hold.jpg')], check=True)
    lk = LOOKS[look]
    if lk:
        yuv = np.frombuffer(grab(AROLL, hold, hold, 'yuv444p')[0], np.uint8).reshape(3, H, W).astype(np.float32)
        black = np.array([0.0 if tg.get('color_range') == 'pc' else 16.0, 128.0, 128.0], np.float32)[:, None, None]
        # the room with the speaker filled out from what surrounds them (or the blur drags a dark fringe around them)
        hole = ndimage.maximum_filter((a > .04).astype(np.float32), size=31)
        hole = np.clip(ndimage.gaussian_filter(hole, 3) * 1.6, 0, 1)
        keep, Q = 1 - hole, 6
        small = lambda v: v.reshape(H // Q, Q, W // Q, Q).mean((1, 3))
        keep_s, fill_s, got = small(keep), np.zeros((3, H // Q, W // Q), np.float32), np.zeros((H // Q, W // Q), np.float32)
        src_s = np.stack([small(yuv[c] * keep) for c in range(3)])
        for sigma in (14, 40, 110, 280):
            den = ndimage.gaussian_filter(keep_s, sigma / Q)
            est = np.stack([ndimage.gaussian_filter(src_s[c], sigma / Q) for c in range(3)]) / np.maximum(den, 1e-6)
            conf = np.clip(den / .08, 0, 1) * (1 - got)
            fill_s += est * conf
            got += conf
        fill = np.stack([np.asarray(Image.fromarray(fill_s[c]).resize((W, H), Image.BICUBIC)) for c in range(3)])
        bg = yuv * keep + fill * hole
        bg = np.stack([ndimage.gaussian_filter(bg[c], lk['blur']) for c in range(3)])
        # dim: lightest on the speaker, deeper towards the frame edges; plus a soft shadow under the cutout
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.hypot((xx - centre[0]) / (.60 * W), (yy - centre[1]) / (.46 * H))
        d = np.interp(r, [0, .62, 1], lk['dim']).astype(np.float32)
        sh = ndimage.gaussian_filter(ndimage.shift(a, (10, 0), order=1), 13) * lk['shadow']
        bg = black + (bg - black) * ((1 - d) * (1 - sh))
        # the speaker on top, matte choked so no light rim of the old room sits on the dimmed one
        t = np.clip((a - .42) / .52, 0, 1)
        t = ndimage.gaussian_filter(t * t * (3 - 2 * t), .8)
        out = np.clip(bg * (1 - t) + yuv * t + .5, 0, 255).astype(np.uint8)
        _encode(out.tobytes(), 'yuv444p', n, os.path.join(out_dir, 'treat.mp4'), tg)
    open(kp, 'w').write(key)
    return True


if __name__ == '__main__':
    ws = onsets()
    if not ws:
        stop('no words.json in this slot: make the slot with fx_new.py (it transcribes), or pass frame numbers in the CLIP block.')
    print('words (frame at the start of each, snapped to the audio):')
    print('  ' + '  '.join(f"{w['text']}@{round(w['onset'] * FPS)}" for w in ws))
    print('cutout: ' + ('ready' if os.path.exists(os.path.join(HERE, 'assets', '.cutout_done')) else 'NOT finished yet (wait for assets/.cutout_done)'))
