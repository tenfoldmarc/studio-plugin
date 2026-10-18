#!/usr/bin/env python3
"""glass-type machinery: one word as thick clear glass letters standing on the speaker's wall, bending the room behind
them (lamp, window, shelves), with a dark glass rim, a rim light, a soft backing shade and a shadow + caustic on the
wall. The speaker stays in front of it. Reads the CLIP block at the top of build.py.

Run from the slot folder with the effect's python (numpy, Pillow, opencv-python-headless; see effect.md):
  python glass.py measure          camera track, zoom check, clean plate, his head, where the word fits, level or not,
                                   the light behind it, the timing -> work/plan.json, work/measure.jpg (LOOK at it)
  python glass.py still 40 60 80   those frames -> work/stills/sheet.jpg (SAFE=1 draws the safe zone). No numbers =
                                   six key frames
  python glass.py bake             every frame -> assets/fx.mp4 (WORKERS=n, default up to 4)
Nothing random: the same slot and CLIP block give the same frames on any machine.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from multiprocessing import Pool, cpu_count

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
W, H, FPS = 1080, 1920, 30
HW, HH = W // 2, H // 2               # analysis size
CAP = 400                             # glyph canvas: ink height of the word, px
F_LENS = 1500.0                       # lens in px (a phone's main camera at 1080 wide; 20% off changes nothing visible)
SS = 2                                # supersampling of the glass (thin highlights alias at 1)
NSWEEP = 10                        # depth samples through the slab
IN_DUR, OUT_DUR = 0.72, 0.62          # arrival and leaving, seconds
LEAD = 0.03                           # the glass starts this long before the word's audio onset
SAFE_BOX = (35, 220, 1045, 1470)      # Reels safe zone; plus the right column x > 980 from y 1155
cv2.setNumThreads(1)


def P(*a):
    return os.path.join(HERE, *a)


def say(msg):
    print('  ' + msg, flush=True)


def clip_block():
    src = open(P('build.py'), encoding='utf-8').read()
    a, b = src.index('# ==== CLIP (edit this) ===='), src.index('# ==== END CLIP ====')
    ns = {}
    exec(compile(src[a:b], 'build.py CLIP block', 'exec'), ns)
    return ns


def n_frames():
    return int(json.load(open(P('clip.json')))['frames'])


# ------------------------------------------------------------------------------------------------------------ frame IO
def reader(path, w, h, alpha=False, first=None, last=None):
    """Frames as numpy arrays (rgb24, or the VP9 alpha plane as gray). first/last: only that run (inclusive)."""
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else [])
    if first:
        cmd += ['-ss', f'{(first - 0.5) / FPS:.5f}']
    cmd += ['-i', path]
    vf = (['alphaextract'] if alpha else []) + ([f"select='between(n,0,{last - first})'"] if first is not None else [])
    vf += [f'scale={w}:{h}:flags=area'] if (w, h) != (W, H) else []
    if vf:
        cmd += ['-vf', ','.join(vf)]
    pix, ch = ('gray', 1) if alpha else ('rgb24', 3)
    # accurate_rnd: swscale's fast YUV->RGB path comes out about 2 levels dark
    cmd += ['-fps_mode', 'passthrough', '-sws_flags', 'accurate_rnd+full_chroma_int+bicubic', '-f', 'rawvideo',
            '-pix_fmt', pix, '-']
    n = w * h * ch
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=n)
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            a = np.frombuffer(buf, np.uint8)
            yield a.reshape(h, w) if ch == 1 else a.reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.terminate()
        p.wait()


def writer(path):
    vf = ('scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,'
          'setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709')
    cmd = [FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-an', '-vf', vf, '-c:v', 'libx264', '-preset', 'slow', '-crf', '12', '-g', '15', '-bf', '0',
           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
           '-movflags', '+faststart', path]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def count_frames(path):
    out = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                          'stream=nb_read_frames', '-of', 'csv=p=0', path], capture_output=True, text=True).stdout
    return int(out.strip() or 0)


# ------------------------------------------------------------------------------------------------------------ helpers
def sstep(a, b, x):
    t = np.clip((np.asarray(x, np.float32) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_out(u, p=3.0):
    u = min(max(u, 0.0), 1.0)
    return 1.0 - (1.0 - u) ** p


def ease_io(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * u * (u * (u * 6 - 15) + 10)


def ell(k):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def hexrgb(h):
    h = str(h).lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def lum(img):
    return (img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722) / 255.0


def m3(m):
    return np.vstack([m, [0, 0, 1.0]])


def norm(s):
    return re.sub(r'[^a-z0-9%]', '', str(s).lower())


def cased(text, case):
    return text.upper() if case == 'upper' else text.lower() if case == 'lower' else text.title() if case == 'title' else text


# ------------------------------------------------------------------------------------------------------------ fonts
def font_faces():
    css_path = P('assets', 'fonts', 'fonts.css')
    if not os.path.exists(css_path):
        sys.exit('assets/fonts/fonts.css is missing: the slot was not made with fx_new.py')
    faces = []
    for blk in re.findall(r'@font-face\s*{(.*?)}', open(css_path, encoding='utf-8').read(), re.S):
        fam = re.search(r"font-family:\s*['\"]?([^;'\"]+)", blk)
        src = re.search(r"url\(\s*['\"]?([^'\")]+)", blk)
        if not (fam and src):
            continue
        wt = re.search(r'font-weight:\s*(\d+)(?:\s+(\d+))?', blk)
        st = re.search(r'font-style:\s*(\w+)', blk)
        lo = int(wt.group(1)) if wt else 400
        faces.append(dict(family=fam.group(1).strip(), lo=lo, hi=int(wt.group(2)) if wt and wt.group(2) else lo,
                          style=st.group(1) if st else 'normal', path=P('assets', 'fonts', src.group(1))))
    return faces


def load_font(family, weight, size):
    faces = [f for f in font_faces() if f['family'].lower() == family.lower() and os.path.exists(f['path'])]
    if not faces:
        have = sorted({f['family'] for f in font_faces() if os.path.exists(f['path'])})
        sys.exit(f'font "{family}" is not in assets/fonts/fonts.css (or its file is missing). Pick one of: {", ".join(have)}')
    same = [f for f in faces if f['style'] == 'normal'] or faces
    best = min(same, key=lambda f: 0 if f['lo'] <= weight <= f['hi'] else min(abs(f['lo'] - weight), abs(f['hi'] - weight)))
    font = ImageFont.truetype(best['path'], size)
    try:                                       # variable files open at their default weight: set the one asked for
        vals = []
        for ax in font.get_variation_axes():
            name = ax.get('name', b'')
            name = name.decode('latin-1') if isinstance(name, bytes) else str(name)
            vals.append(min(max(weight, ax['minimum']), ax['maximum']) if name.lower().startswith('weight')
                        else ax.get('default', ax['minimum']))
        font.set_variation_by_axes(vals)
    except Exception:
        pass
    return font


def glyph_canvas(C):
    """The word as a 0..1 mask, cropped tight, ink height ~CAP px; and each letter's x span (canvas px)."""
    text = cased(C['TEXT'], C['CASE'])
    stretch, track = float(C['STRETCH']), float(C['TRACKING'])
    probe = load_font(C['FONT'], C['WEIGHT'], 300)
    hb = probe.getbbox('H')
    ft = load_font(C['FONT'], C['WEIGHT'], max(20, int(round(300 * CAP / stretch / max(1, hb[3] - hb[1])))))
    hb = ft.getbbox('H')
    caph = hb[3] - hb[1]
    xs, x = [], 0.0
    for ch in text:
        xs.append(x)
        x += ft.getlength(ch) + track * ft.size
    pad = 60
    im = Image.new('L', (int(x) + pad * 2, int(caph * 1.9) + pad * 2), 0)
    d = ImageDraw.Draw(im)
    spans = []
    for ch, xx in zip(text, xs):
        d.text((pad + xx, pad + caph * 0.45 - hb[1]), ch, font=ft, fill=255)
        bb = d.textbbox((pad + xx, pad + caph * 0.45 - hb[1]), ch, font=ft)
        if ch.strip():
            spans.append((bb[0], bb[2]))
    a = np.asarray(im)
    ys, xs_ = np.where(a > 128)
    if not len(ys):
        sys.exit(f'"{text}" draws nothing in font {C["FONT"]}')
    y0, x0 = ys.min(), xs_.min()
    a = a[y0:ys.max() + 1, x0:xs_.max() + 1]
    a = cv2.resize(a, (a.shape[1], int(round(a.shape[0] * stretch))), interpolation=cv2.INTER_CUBIC)
    spans = [(s - x0 + 4, e - x0 + 4) for s, e in spans]
    return np.pad(a, 4).astype(np.float32) / 255, spans


class Slab:
    """Height field of the word: rounded bevel (steep at the rim) + a soft pillow so each stroke is a weak lens."""

    def __init__(self, a, bevel):
        self.h, self.w = a.shape
        self.a = cv2.GaussianBlur(a, (0, 0), 0.7)
        d = cv2.distanceTransform((a > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
        x = np.clip((d - 0.5) / bevel, 0, 1)
        bev = np.sqrt(1 - (1 - x) ** 2)                              # quarter circle: steep at the rim, flat on top
        self.bev = cv2.GaussianBlur(bev.astype(np.float32), (0, 0), 1.6)
        stroke = float(np.percentile(d[d > 0], 97)) * 2              # widest stroke, px
        pil = cv2.GaussianBlur(a, (0, 0), stroke * 0.30)
        pil = pil / max(1e-6, pil.max())
        self.stroke = stroke
        self.tprof = (0.82 * self.bev + 0.18 * pil * self.a).astype(np.float32)
        hf = cv2.GaussianBlur(bevel * 0.9 * self.bev, (0, 0), 1.2)    # front face: flat top, rounded shoulder
        gu = cv2.Scharr(hf, cv2.CV_32F, 1, 0) / 32.0
        gv = cv2.Scharr(hf, cv2.CV_32F, 0, 1) / 32.0
        rim = np.clip(np.hypot(gu, gv), 0, 2.0)                      # 0 on the flat face, large on the bevel
        self.grad = np.dstack([gu, gv, rim]).astype(np.float32)
        self.rim = rim.astype(np.float32)


# ------------------------------------------------------------------------------------------------------------ timing
def audio_env():
    raw = subprocess.run([FF, '-v', 'error', '-i', P('assets', 'aroll.mp4'), '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 160
    n = len(a) // hop
    return np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)


def onset(w, env):
    """Whisper's start can be 0.1 to 0.4 s off: take the rise of the loudness after the dip before the word."""
    s, e = w['start'], max(w['end'], w['start'] + 0.1)
    j0, j1 = int(s * 100), min(len(env) - 1, int(e * 100) + 1)
    pk_i = j0 + int(np.argmax(env[j0:j1 + 1])) if j1 > j0 else j0
    i0, i1 = max(0, int((s - 0.12) * 100)), min(len(env) - 1, int((s + 0.12) * 100), pk_i)
    if i1 <= i0:
        return s
    im = i0 + int(np.argmin(env[i0:i1 + 1]))
    pk = env[im:min(len(env), int((e + 0.1) * 100)) + 1].max()
    thr = env[im] + 0.35 * (pk - env[im])
    for i in range(im, min(len(env), int((e + 0.1) * 100))):
        if env[i] >= thr:
            return i / 100.0
    return s


def resolve(v, words, env, default_text=None):
    """a word ('design', 'design#2'), seconds, or 'auto' (the word that matches TEXT) -> (seconds, how)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v), 'seconds'
    if v in (None, 'auto'):
        v = default_text
    key, nth = (str(v).split('#') + ['1'])[:2]
    hits = [w for w in words if norm(w['text']) == norm(key)]
    if not hits:                                     # 'design' also finds 'designs' / 'designer'
        hits = [w for w in words if norm(w['text']).startswith(norm(key)) or norm(key).startswith(norm(w['text'])) and len(norm(w['text'])) > 3]
    if len(hits) < int(nth):
        sys.exit(f'"{v}" is not in words.json, so the glass cannot find its word. Set T_IN to the spoken word or to '
                 'seconds. Words: ' + ' '.join(w['text'] for w in words))
    w = hits[int(nth) - 1]
    t = onset(w, env)
    return t, f'"{w["text"]}" whisper {w["start"]:.2f}s, audio onset {t:.2f}s'


# ------------------------------------------------------------------------------------------------------------ measure
def track(grays, alphas):
    """Camera motion of the room (similarity fitted to the background only). Per frame a 3x3: reference -> that frame
    (analysis px). Also the number of frames it could not follow."""
    n = len(grays)
    acc = [np.eye(3)]
    weak = 0
    for f in range(1, n):
        bg = (cv2.dilate((alphas[f - 1] > 10).astype(np.uint8), ell(31)) == 0).astype(np.uint8) * 255
        bg[:8], bg[-8:], bg[:, :8], bg[:, -8:] = 0, 0, 0, 0
        pts = cv2.goodFeaturesToTrack(grays[f - 1], 500, 0.01, 7, mask=bg)
        T = np.eye(3)
        ok_f = False
        if pts is not None and len(pts) >= 12:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(grays[f - 1], grays[f], pts, None, winSize=(21, 21), maxLevel=3)
            ok = st[:, 0] == 1
            if ok.sum() >= 10:
                m, inl = cv2.estimateAffinePartial2D(pts[ok], nxt[ok], method=cv2.RANSAC, ransacReprojThreshold=1.2)
                if m is not None and inl is not None and inl.sum() >= 8:
                    T, ok_f = m3(m), True
        weak += 0 if ok_f else 1
        acc.append(T @ acc[-1])
    r = n // 2
    inv_r = np.linalg.inv(acc[r])
    return [a @ inv_r for a in acc], r, weak


def full_res(Mh):
    S = np.array([[2, 0, 0.5], [0, 2, 0.5], [0, 0, 1]], np.float64)
    return S @ Mh @ np.linalg.inv(S)


def head_of(alpha_h):
    """Head of the cutout in one frame (analysis size): top y, centre x, width. None if nobody is in the frame."""
    rows = np.flatnonzero((alpha_h > 128).sum(1) >= 6)
    if not len(rows):
        return None
    top = rows[0]
    band = alpha_h[top + 20:top + 70] > 128
    ws, cs = [], []
    for r in band:
        xs = np.flatnonzero(r)
        if len(xs):
            ws.append(xs[-1] - xs[0] + 1)
            cs.append((xs[-1] + xs[0]) / 2)
    if not ws:
        return None
    return top, float(np.median(cs)), float(np.median(ws))


def wall_slope(plate, person, band):
    """Angle (deg, image y down) of the room's long near-level lines around the word's height, and how sure."""
    g = cv2.GaussianBlur(cv2.cvtColor(plate, cv2.COLOR_RGB2GRAY), (0, 0), 1.5)
    e = cv2.Canny(g, 30, 90)
    e[cv2.dilate(person, ell(31)) > 0] = 0
    y0, y1 = max(0, int(band[0])), min(H, int(band[1]))
    m = np.zeros_like(e)
    m[y0:y1] = 1
    e = e * m
    segs = cv2.HoughLinesP(e, 1, np.pi / 720, 60, minLineLength=140, maxLineGap=6)
    if segs is None:
        return 0.0, 0.0, 0
    ang, wt = [], []
    for x1, y1_, x2, y2 in segs.reshape(-1, 4).astype(np.float64):
        a = math.degrees(math.atan2(y2 - y1_, x2 - x1))
        a = (a + 90) % 180 - 90
        if abs(a) < 25:
            ang.append(a)
            wt.append(math.hypot(x2 - x1, y2 - y1_))
    if not ang:
        return 0.0, 0.0, 0
    ang, wt = np.array(ang), np.array(wt)
    med = float(np.average(ang, weights=wt))
    sd = float(np.sqrt(np.average((ang - med) ** 2, weights=wt)))
    return med, float(wt.sum()), sd


def measure():
    C = clip_block()
    N = n_frames()
    os.makedirs(P('work', 'cache'), exist_ok=True)
    t0 = time.time()
    text = cased(C['TEXT'], C['CASE'])
    for bad in (chr(8212), chr(8211)):
        if bad in text:
            sys.exit('TEXT: no long dashes on screen')
    if norm(text) in ('fr' + 'ee', 'cour' + 'se'):
        sys.exit(f'"{text}" is on the never-on-screen list')
    if len(text) > 12 or ' ' in text.strip():
        say(f'!! "{text}": this is a one-word effect; long words get small. Split the idea or pick the key word.')

    # ---- timing (word onset on the audio)
    words = json.load(open(P('words.json'))) if os.path.exists(P('words.json')) else []
    env = audio_env()
    t_in, how = resolve(C['T_IN'], words, env, default_text=C['TEXT'])
    f_in = int(round((t_in - LEAD) * FPS))
    if f_in < 4:
        say(f'!! the glass would start on frame {f_in}: moved to frame 4 so the slot opens on the plain picture. '
            'Start the slot earlier for a clean landing.')
        f_in = 4
    t_in = f_in / FPS + LEAD
    end_cap = (N - 6) / FPS - OUT_DUR                   # gone 6 frames before the slot ends
    if C['T_OUT'] == 'cut':
        t_out = 1e9
    elif C['T_OUT'] in (None, 'auto'):
        t_out = min(t_in + IN_DUR + float(C['HOLD']), end_cap)
    else:
        t_out, _ = resolve(C['T_OUT'], words, env)
        t_out = min(t_out, end_cap)
    if t_out != 1e9 and t_out - t_in < 0.9:
        say(f'!! the glass only stays {t_out - t_in:.2f} s: the slot ends too soon after the word. Give it 1.5 s more footage.')
    f_end = N if t_out == 1e9 else min(N, int(math.ceil((t_out + OUT_DUR) * FPS)) + 1)
    say(f'timing: lands on {how}; starts frame {f_in}, leaves from {t_out * FPS if t_out < 1e9 else N:.0f}, '
        f'gone by frame {f_end} of {N}')

    # ---- read the slot at analysis size
    rgbs, grays, alphas = [], [], []
    for rgb, a in zip(reader(P('assets', 'aroll.mp4'), HW, HH), reader(P('assets', 'subject.webm'), HW, HH, alpha=True)):
        rgbs.append(rgb.copy())
        grays.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
        alphas.append(a.copy())
    if len(rgbs) != N:
        sys.exit(f'read {len(rgbs)} frames of a-roll + cutout, clip.json says {N}: remake the slot (cutout missing or short)')

    # ---- camera: still, handheld drift (tracked), zoom or a moving camera (declines)
    mats, ref, weak = track(grays, alphas)
    corners = np.array([[0, 0, 1], [HW, 0, 1], [0, HH, 1], [HW, HH, 1], [HW / 2, HH / 2, 1]], np.float64).T
    drift = max(float(np.abs((m @ corners)[:2] / (m @ corners)[2] - corners[:2]).max()) for m in mats) * 2
    # a handheld phone breathes in and out a few % (the track follows it); a punch-in is a jump, a lens zoom a steady
    # one-way change while the glass is up. Those two decline.
    scales = np.array([math.sqrt(abs(np.linalg.det(m[:2, :2]))) for m in mats])
    a0, a1 = max(0, f_in - 5), min(N - 1, f_end + 5)
    sw = scales[a0:a1 + 1]
    steps = sw[1:] / sw[:-1] - 1
    jump = float(np.abs(steps).max()) if len(steps) else 0.0
    net = float(sw[-1] / sw[0] - 1) if len(sw) > 1 else 0.0
    mono = float((np.sign(steps) == np.sign(net)).mean()) if len(steps) and net else 0.0
    zoom = float(scales.max() / scales.min() - 1)
    if jump > 0.03 or (abs(net) > 0.06 and mono > 0.7):
        sys.exit(f'GLASS TYPE DECLINES: the picture zooms inside this slot ({"a punch-in, " + f"{jump * 100:.0f}% in one frame" if jump > 0.03 else f"{net * 100:+.0f}% while the glass is up"}). '
                 'The glass would swim against the wall. Use a stretch without the zoom, or end the slot before it.')
    if drift > 300 or weak > N * 0.25:
        sys.exit(f'GLASS TYPE DECLINES: the camera moves too much in this slot ({drift:.0f} px, {weak} frames it could not '
                 'follow). The glass has to stand still on the wall: use a steadier stretch (tripod or a phone held fairly still).')
    still = drift < 4.0
    if still:
        mats = [np.eye(3) for _ in mats]
    lost = sum(1 for a in alphas if (a > 128).sum() < 400)
    if lost > N * 0.2:
        sys.exit('GLASS TYPE DECLINES: you are out of the shot (or the cutout lost you) for a fifth of this slot.')

    # ---- where he is while the glass is up (reference frame), his head
    act = range(max(0, f_in), min(N, f_end))
    pers = np.zeros((HH, HW), np.uint8)
    heads = []
    for f in act:
        inv = np.linalg.inv(mats[f])[:2]
        al = alphas[f] if still else cv2.warpAffine(alphas[f], inv, (HW, HH), flags=cv2.INTER_LINEAR)
        pers = np.maximum(pers, al)
        h = head_of(al)
        if h:
            heads.append(h)
    if not heads:
        sys.exit('GLASS TYPE DECLINES: no person found in assets/subject.webm while the glass is up.')
    hs = np.array(heads)
    head = dict(top=float(hs[:, 0].min() * 2), cx=float(np.median(hs[:, 1]) * 2), w=float(np.median(hs[:, 2]) * 2))
    person = cv2.resize(((pers > 30) * 255).astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST)
    row = person[1400] > 0
    span = (np.flatnonzero(row)[-1] - np.flatnonzero(row)[0]) / W if row.any() else 0
    framing = 'close' if head['w'] > 330 or span > 0.85 else 'wide' if head['w'] < 130 else 'medium'
    side = 'centre' if 380 <= head['cx'] <= 700 else ('left' if head['cx'] < 380 else 'right')

    # ---- the room without him, full size, in the reference frame
    acc = np.zeros((H, W, 3), np.float32)
    cnt = np.zeros((H, W), np.float32)
    for f, (rgb, a) in enumerate(zip(reader(P('assets', 'aroll.mp4'), W, H), reader(P('assets', 'subject.webm'), W, H, alpha=True))):
        if f % 2:
            continue
        free = (cv2.dilate((a > 6).astype(np.uint8), ell(25)) == 0).astype(np.float32)
        if not still:
            inv = np.linalg.inv(full_res(mats[f]))[:2]
            rgb = cv2.warpAffine(rgb, inv, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            free = cv2.warpAffine(free, inv, (W, H), flags=cv2.INTER_NEAREST, borderValue=0)
        acc += rgb.astype(np.float32) * free[..., None]
        cnt += free
    seen = cnt >= 2
    plate = np.zeros((H, W, 3), np.uint8)
    plate[seen] = (acc[seen] / cnt[seen][:, None]).clip(0, 255).astype(np.uint8)
    q = cv2.resize(plate, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    qh = cv2.resize((~seen).astype(np.uint8) * 255, (W // 4, H // 4), interpolation=cv2.INTER_NEAREST)
    fill = cv2.resize(cv2.inpaint(q, qh, 5, cv2.INPAINT_TELEA), (W, H), interpolation=cv2.INTER_CUBIC)
    plate[~seen] = fill[~seen]
    Lp = lum(plate.astype(np.float32))

    # ---- where the word fits: biggest box on open wall, near his head, inside the safe zone
    mask, spans = glyph_canvas(C)
    gh, gw = mask.shape
    aspect = gw / gh
    pq = cv2.dilate((person > 0).astype(np.uint8), ell(9))[::4, ::4].astype(np.float32)   # quarter size
    ii = cv2.integral(pq)
    hq, wq = pq.shape

    def rect_occ(x0, y0, w, h):
        a, b, c, d = int(x0 / 4), int(y0 / 4), int((x0 + w) / 4), int((y0 + h) / 4)
        a, b, c, d = max(0, a), max(0, b), min(wq, max(a + 1, c)), min(hq, max(b + 1, d))
        return float(ii[d, c] - ii[b, c] - ii[d, a] + ii[b, a]) / max(1, (c - a) * (d - b))

    def glyph_occ(x0, y0, w, h):
        a, b = int(x0 / 4), int(y0 / 4)
        gq = cv2.resize(mask, (max(1, int(w / 4)), max(1, int(h / 4))), interpolation=cv2.INTER_AREA)
        sub = pq[b:b + gq.shape[0], a:a + gq.shape[1]]
        gq = gq[:sub.shape[0], :sub.shape[1]]
        tot = float((gq * sub).sum()) / max(1e-6, float(gq.sum()))
        worst = 0.0
        for s, e in spans:                                # no letter may be hidden behind him
            cs, ce = int(s / gw * gq.shape[1]), max(int(s / gw * gq.shape[1]) + 1, int(e / gw * gq.shape[1]))
            g = gq[:, cs:ce]
            worst = max(worst, float((g * sub[:, cs:ce]).sum()) / max(1e-6, float(g.sum())))
        return tot, worst

    def inside(x0, y0, w, h, m=10):
        x1, y1 = x0 + w, y0 + h
        if x0 < SAFE_BOX[0] + 25 or x1 > SAFE_BOX[2] - 25 or y0 < SAFE_BOX[1] + 30 + m or y1 > SAFE_BOX[3] - 40:
            return False
        return not (y1 > 1155 - 20 and x1 > 980 - 15)

    place = C['PLACE']
    cands = []
    if isinstance(place, (tuple, list)):
        x0, y0, w = (float(v) for v in place[:3])
        h = w / aspect
        cands = [(1e9, x0, y0, w, h)]
    else:
        h_max = min(330.0, 0.20 * H)
        h_min = 64.0
        hh = h_max
        while hh >= h_min:
            w = hh * aspect
            if w <= 950:
                for y0 in range(260, int(1440 - hh), 12):
                    for x0 in range(64, int(1016 - w) + 1, 12):
                        if not inside(x0, y0, w, hh):
                            continue
                        occ = rect_occ(x0, y0, w, hh)
                        if occ > 0.45:
                            continue
                        cx, cy = x0 + w / 2, y0 + hh / 2
                        above = (y0 + hh) <= head['top'] + 0.25 * head['w']
                        if place == 'above' and not above:
                            continue
                        if place == 'left' and cx > head['cx'] - 0.3 * head['w']:
                            continue
                        if place == 'right' and cx < head['cx'] + 0.3 * head['w']:
                            continue
                        gap = 0.30 * head['w'] + 0.12 * hh            # breathing room between the letters and the head
                        near = abs(cy - max(300 + hh / 2, head['top'] - gap - hh / 2)) / H + 0.5 * abs(cx - head['cx']) / W
                        sd = float(Lp[int(y0):int(y0 + hh), int(x0):int(x0 + w)].std())
                        score = hh * (1 - 1.2 * occ) * (1 - 0.6 * near) * (1 + 0.15 * min(1.0, sd / 0.18)) + (8 if above else 0)
                        over_head = abs(cx - head['cx']) < w / 2 + head['w'] / 2
                        if over_head and head['top'] - 0.6 * gap < y0 + hh < head['top'] + 0.6 * head['w']:
                            score *= 0.85                              # letters sitting on his hair look stuck to him
                        cands.append((score, x0, y0, w, hh))
            hh *= 0.93
        cands.sort(key=lambda c: -c[0])
    best = None
    for sc, x0, y0, w, h in cands[:400]:
        tot, worst = glyph_occ(x0, y0, w, h)
        if isinstance(place, (tuple, list)) or (tot <= float(C['MAX_HIDDEN']) and worst <= 0.30):
            best = (x0, y0, w, h, tot, worst)
            break
    if best is None:
        sys.exit('GLASS TYPE DECLINES: this needs some open wall above or beside you for one word; in this clip you fill '
                 'the frame where the word would go. Try a wider shot, a shorter word, or another effect.')
    x0, y0, w, h, tot, worst = best
    if h < 90:
        say(f'!! the word only fits {h:.0f} px tall here: it will read, but small. A shorter word reads bigger.')

    # ---- level unless the wall really slopes
    lv = C['LEVEL']
    slope, sure, sd = wall_slope(plate, person, (y0 - 0.6 * h, y0 + 1.6 * h))
    if lv is True or lv == 'level':
        roll, why = 0.0, 'level (CLIP)'
    elif isinstance(lv, (int, float)) and not isinstance(lv, bool):
        roll, why = float(lv), 'from CLIP'
    elif sure >= 700 and sd < 3.0 and abs(slope) >= 3.0:
        roll = float(np.clip(0.6 * slope, -4.0, 4.0))
        why = f'the wall slopes {slope:+.1f} deg here ({sure:.0f} px of lines agree): follows it at {roll:+.1f} deg'
    else:
        roll, why = 0.0, (f'level (the lines here average {slope:+.1f} deg over {sure:.0f} px, spread {sd:.1f} deg: '
                          'not a clear wall slope)' if sure else 'level (no wall lines here)')

    # ---- the light behind the word: decides backing shade, rim strength and shadow
    pad = int(0.25 * h)
    by0, by1, bx0, bx1 = max(0, int(y0) - pad), min(H, int(y0 + h) + pad), max(0, int(x0) - pad), min(W, int(x0 + w) + pad)
    Lb = Lp[by0:by1, bx0:bx1]
    pb = person[by0:by1, bx0:bx1] == 0
    Lb = Lb[pb] if pb.sum() > 100 else Lb.ravel()
    L50, L90 = float(np.median(Lb)), float(np.percentile(Lb, 90))
    gy = cv2.Sobel(cv2.GaussianBlur(Lp, (0, 0), 1.5), cv2.CV_32F, 0, 1)
    gx = cv2.Sobel(cv2.GaussianBlur(Lp, (0, 0), 1.5), cv2.CV_32F, 1, 0)
    tex = float(np.median(np.hypot(gx, gy)[by0:by1, bx0:bx1]))
    bright = float((Lb > 0.80).mean())
    busy = tex > 0.012 or bright > 0.08
    room = ('window or lamp' if bright > 0.08 else 'busy' if tex > 0.012 else 'dark plain wall' if L50 < 0.28 else 'plain wall')

    def auto(v, val):
        return float(val) if v in (None, 'auto') else float(v)

    backing = auto(C['BACKING'], 0.10 + 0.32 * float(sstep(0.45, 0.85, L90)))
    rim_dark = auto(C['RIM_DARK'], 0.30 + 0.40 * float(sstep(0.45, 0.85, L90)))
    rim_light = auto(C['RIM_LIGHT'], 0.55 + 0.55 * (1 - float(sstep(0.25, 0.65, L50))) + (0.25 if not busy else 0))
    shadow = auto(C['SHADOW'], (0.0 if L50 < 0.18 else 0.17 + (0.07 if not busy else 0)))
    top = plate[:H // 3].reshape(-1, 3).astype(np.float32)
    lo = plate[2 * H // 3:].reshape(-1, 3).astype(np.float32)
    env_hi = np.percentile(top, 85, axis=0) * 0.92 + 18
    env_lo = np.median(lo, axis=0) * 0.85

    plan = dict(N=N, f_in=f_in, t_in=round(t_in, 3), t_out=round(t_out, 3) if t_out < 1e9 else None, f_end=f_end,
                box=[round(x0, 1), round(y0, 1), round(w, 1), round(h, 1)], hidden=round(tot, 3), roll=round(roll, 2),
                still=still, drift_px=round(drift, 1), zoom=round(zoom, 4), weak=weak, framing=framing, side=side,
                head={k: round(v, 1) for k, v in head.items()}, room=room, L50=round(L50, 3), L90=round(L90, 3),
                tex=round(tex, 4), backing=round(backing, 3), rim_dark=round(rim_dark, 3), rim_light=round(rim_light, 3),
                shadow=round(shadow, 3), env_hi=[round(v, 1) for v in env_hi], env_lo=[round(v, 1) for v in env_lo])
    json.dump(plan, open(P('work', 'plan.json'), 'w'), indent=1, default=lambda v: v.item() if hasattr(v, 'item') else float(v))
    np.save(P('work', 'cache', 'track.npy'), np.array([full_res(m) for m in mats]))
    cv2.imwrite(P('work', 'cache', 'plate.png'), plate[..., ::-1])

    f_land = f_in + int(IN_DUR * FPS)
    f_out = N if plan['t_out'] is None else int(plan['t_out'] * FPS)
    marks = sorted({0, max(0, f_in - 1), f_in + 6, f_land, (f_land + f_out) // 2, f_out + 8, N - 1})
    json.dump(dict(marks=marks, stills=[f_land, (f_land + f_out) // 2, min(N - 1, f_out + 4)]),
              open(P('work', 'marks.json'), 'w'))

    print(f'camera: {"still" if still else "handheld"} (drift {drift:.1f} px, scale breathes {zoom * 100:.1f}%' +
          (f', {weak} weak frames' if weak else '') + ')' + ('' if still else ': the glass is pinned to the wall by the track'))
    print(f'framing: {framing} (head {head["w"]:.0f} px wide, top y {head["top"]:.0f}, centre x {head["cx"]:.0f}, {side})')
    print(f'word: "{text}" in a box x {x0:.0f}..{x0 + w:.0f}, y {y0:.0f}..{y0 + h:.0f} ({h:.0f} px tall), '
          f'{tot * 100:.0f}% of it behind him (worst letter {worst * 100:.0f}%)')
    print(f'perspective: {why}')
    print(f'behind the word: {room} (median light {L50:.2f}, brightest {L90:.2f}) -> backing {backing:.2f}, dark rim '
          f'{rim_dark:.2f}, rim light {rim_light:.2f}, shadow {shadow:.2f}')
    prev = plate.astype(np.float32) * 0.8
    prev[person > 0] = prev[person > 0] * 0.4 + np.array([40, 90, 230], np.float32) * 0.6
    cv2.rectangle(prev, (int(x0), int(y0)), (int(x0 + w), int(y0 + h)), (255, 225, 60), 5)
    cv2.rectangle(prev, (35, 220), (1045, 1470), (255, 60, 60), 2)
    cv2.imwrite(P('work', 'measure.jpg'), cv2.resize(prev.clip(0, 255).astype(np.uint8), (540, 960))[..., ::-1])
    print(f'measure: {time.time() - t0:.0f} s. LOOK at work/measure.jpg (blue = where he goes, yellow = the word)')


# ------------------------------------------------------------------------------------------------------------ the glass
class Glass:
    def __init__(self, plan, C, ss=SS):
        self.pl, self.C, self.ss = plan, C, ss
        mask, _ = glyph_canvas(C)
        x0, y0, w, h = plan['box']
        scale = w / mask.shape[1]                                     # canvas px -> frame px
        bevel = max(float(C['BEVEL']), 4.5 / scale)                   # never thinner than 4.5 frame px
        self.slab = Slab(mask, bevel)
        self.hpx = h
        self.scale = scale
        self.cx, self.cy = W / 2.0, y0 + h / 2.0                      # principal point on the word: its centre line is level
        self.K = np.array([[F_LENS, 0, self.cx], [0, F_LENS, self.cy], [0, 0, 1.0]])
        a = math.radians(plan['roll'])
        self.r1 = np.array([math.cos(a), math.sin(a), 0.0])
        self.r2 = np.array([-math.sin(a), math.cos(a), 0.0])
        self.n = np.cross(self.r1, self.r2)
        gw, gh = self.slab.w, self.slab.h
        Z = F_LENS / scale
        c = Z * np.array([(x0 + w / 2 - self.cx) / F_LENS, (y0 + h / 2 - self.cy) / F_LENS, 1.0])
        self.o0 = c - gw / 2 * self.r1 - gh / 2 * self.r2
        self.zmid = Z
        self.cam = np.load(P('work', 'cache', 'track.npy'))
        self.plate = cv2.imread(P('work', 'cache', 'plate.png'))[..., ::-1].astype(np.float32)
        m = 0.55 * h + 70
        self.roi_ref = np.array([[x0 - m, y0 - m], [x0 + w + m, y0 - m], [x0 - m, y0 + h + 1.2 * m], [x0 + w + m, y0 + h + 1.2 * m]])
        self.ink = hexrgb(C['INK'])
        self.accent = hexrgb(C['ACCENT'])
        tint = hexrgb(C['TINT']) / 255.0
        self.absorb = (0.012 + 0.25 * (1 - tint)).astype(np.float32)
        self.env_hi = np.array(plan['env_hi'], np.float32)
        self.env_lo = np.array(plan['env_lo'], np.float32)
        ld = np.array(C['LIGHT_FROM'], np.float64)
        self.l2 = ld / np.linalg.norm(ld)                             # image-plane direction the light comes from

    def t_out(self):
        return self.pl['t_out'] if self.pl['t_out'] is not None else 1e9

    def pose(self, t):
        gw, gh = self.slab.w, self.slab.h
        t_in, t_out = self.pl['t_in'] - LEAD, self.t_out()
        u_in = (t - t_in) / IN_DUR
        u_out = (t - t_out) / OUT_DUR
        e_in = ease_out(u_in, 3.2)
        e_out = ease_io(u_out)
        m = ease_out(u_in / 0.78, 2.4) * (1.0 - e_out)
        tilt = -7.0 + 10.0 * e_in + 0.6 * math.sin((t - t_in) * 2.2) - 5.0 * e_out
        th = t - (t_in + min(t_out, t_in + 3) + OUT_DUR) / 2
        yaw = 1.3 * th * float(self.C['DRIFT'])
        rise = 46.0 * (1 - e_in) + 30.0 * e_out
        shift = 14.0 * th * float(self.C['DRIFT'])
        e1, e2, e3 = self.r1, self.r2, self.n
        e2t, e3t = rot(e2, e1, tilt), rot(e3, e1, tilt)
        e1y, e3y = rot(e1, e2t, yaw), rot(e3t, e2t, yaw)
        pb = self.o0 + gw / 2 * e1 + gh * e2 + rise * e2 + shift * e1
        o = pb - gw / 2 * e1y - gh * e2t
        sweep = -0.14 + 1.36 * float(sstep(0.0, 1.0, (t - t_in - 0.04) / 0.90))
        sweep += 0.05 * max(0.0, t - t_in - 0.94)
        return dict(e1=e1y, e2=e2t, e3=e3y, o=o, m=m, key=sweep)

    def homog(self, ps, s, depth):
        return self.K @ np.stack([ps['e1'], ps['e2'], ps['o'] + s * depth * ps['e3']], axis=1)

    def active(self, f):
        return self.pose(f / FPS)['m'] >= 1e-4

    def roi(self, f):
        c = np.hstack([self.roi_ref, np.ones((4, 1))]) @ self.cam[f].T
        c = c[:, :2] / c[:, 2:]
        x0, y0 = int(max(0, np.floor(c[:, 0].min()))), int(max(0, np.floor(c[:, 1].min())))
        x1, y1 = int(min(W, np.ceil(c[:, 0].max()))), int(min(H, np.ceil(c[:, 1].max())))
        return x0, y0, x1, y1

    def render(self, room, f):
        """room: float32 RGB full frame WITHOUT the person. -> (roi, delta) to add to the room inside roi."""
        t = f / FPS
        ps = self.pose(t)
        m = ps['m']
        if m < 1e-4:
            return None
        ss, sl, C = self.ss, self.slab, self.C
        gw, gh = sl.w, sl.h
        x0, y0, x1, y1 = self.roi(f)
        rw, rh = x1 - x0, y1 - y0
        if rw < 8 or rh < 8:
            return None
        F = F_LENS
        depth = float(C['DEPTH']) * m
        to_ss = np.array([[ss, 0, (ss - 1) / 2.0 - x0 * ss], [0, ss, (ss - 1) / 2.0 - y0 * ss], [0, 0, 1.0]])
        A = to_ss @ self.cam[f]
        size = (rw * ss, rh * ss)
        lin = cv2.INTER_LINEAR
        xs = (np.arange(rw * ss, dtype=np.float32) + 0.5) / ss - 0.5 + x0
        ys = (np.arange(rh * ss, dtype=np.float32) + 0.5) / ss - 0.5 + y0
        gx, gy = np.meshgrid(xs, ys)
        ix, iy = np.meshgrid(np.arange(rw * ss, dtype=np.float32), np.arange(rh * ss, dtype=np.float32))
        xp, yp = (gx - self.cx) / F, (gy - self.cy) / F
        view = np.stack([xp, yp, np.ones_like(xp)], -1)
        view /= np.linalg.norm(view, axis=-1, keepdims=True)
        # --- glass along every view ray: sweep the cross-section through the slab's depth
        tn = np.zeros((rh * ss, rw * ss), np.float32)
        cov = np.zeros_like(tn)
        for k in range(NSWEEP):
            hm = A @ self.homog(ps, (k + 0.5) / NSWEEP, depth)
            tn += cv2.warpPerspective(sl.tprof, hm, size, flags=lin)
            cov = np.maximum(cov, cv2.warpPerspective(sl.a, hm, size, flags=lin))
        tn /= NSWEEP
        h_front = A @ self.homog(ps, 0.0, depth)
        h_back = A @ self.homog(ps, 1.0, depth)
        front = cv2.warpPerspective(sl.a, h_front, size, flags=lin)
        cov = np.maximum(cov, front)
        hi = np.linalg.inv(h_front)
        zinv = (hi[2, 0] * ix + hi[2, 1] * iy + hi[2, 2]).astype(np.float32)
        z = np.clip(1.0 / np.maximum(zinv, 1e-9), self.zmid * 0.5, self.zmid * 1.8)
        scale = (F / z).astype(np.float32)
        tpx = tn * depth * scale
        tb = cv2.GaussianBlur(tpx, (0, 0), 1.1 * ss)
        gxs = cv2.Scharr(tb, cv2.CV_32F, 1, 0) * (ss / 32.0)
        gys = cv2.Scharr(tb, cv2.CV_32F, 0, 1) * (ss / 32.0)
        gmag = np.sqrt(gxs * gxs + gys * gys) + 1e-6
        ior = float(C['IOR'])
        amax = 1.05 * max(m, 1e-3) ** 0.9
        alpha = amax * np.tanh((ior - 1) * 0.55 * gmag / amax)
        defl = np.tan(alpha) * 150.0 * scale
        dxr, dyr = gxs / gmag * defl, gys / gmag * defl
        # --- wall at frame resolution: backing shade, soft shadow + caustic (light through glass is moved, not removed)
        fsize = (rw, rh)
        cov_f = cv2.resize(cov, fsize, interpolation=cv2.INTER_AREA)
        dx_f = cv2.resize(dxr, fsize, interpolation=cv2.INTER_AREA)
        dy_f = cv2.resize(dyr, fsize, interpolation=cv2.INTER_AREA)
        lit_room = room.copy()
        part = lit_room[y0:y1, x0:x1]
        # the light behind the glass decides how hard the rim and the backing work (a window needs them, a wall less)
        Lr = cv2.GaussianBlur(lum(part), (0, 0), 6)
        light = np.ones((rh, rw), np.float32)
        if self.pl['shadow'] > 0:
            l = np.array([-self.l2[0], -self.l2[1], 1.0]) * np.array([0.42, 0.42, 1.0])
            l /= np.linalg.norm(l)
            tt = 190.0 / max(0.2, float(l @ self.n))
            pc = ps['o'] + 0.5 * gw * ps['e1'] + 0.5 * gh * ps['e2']
            qa, qb = self.K @ pc, self.K @ (pc + tt * l)
            lsx, lsy = qb[0] / qb[2] - qa[0] / qa[2], qb[1] / qb[2] - qa[1] / qa[2]
            sel = cov_f > 0.02
            fxg, fyg = np.meshgrid(np.arange(rw, dtype=np.float32), np.arange(rh, dtype=np.float32))
            dm = np.hypot(dx_f[sel], dy_f[sel])
            cthrow = np.minimum(dm, 70.0) / np.maximum(dm, 1e-3) * (190.0 / 150.0)
            px = fxg[sel] + lsx + dx_f[sel] * cthrow
            py = fyg[sel] + lsy + dy_f[sel] * cthrow
            ok = (px >= 0) & (px < rw - 1) & (py >= 0) & (py < rh - 1)
            idx = (py[ok] + 0.5).astype(np.int64) * rw + (px[ok] + 0.5).astype(np.int64)
            acc = np.bincount(idx, weights=cov_f[sel][ok] * 0.92, minlength=rh * rw).reshape(rh, rw).astype(np.float32)
            shcov = cv2.warpAffine(cov_f, np.float32([[1, 0, lsx], [0, 1, lsy]]), fsize, flags=lin)
            pen = max(3.0, 0.02 * self.hpx)
            lit = (0.55 * (cv2.GaussianBlur(acc, (0, 0), pen) - cv2.GaussianBlur(shcov, (0, 0), pen))
                   + 0.45 * (cv2.GaussianBlur(acc, (0, 0), pen * 2.6) - cv2.GaussianBlur(shcov, (0, 0), pen * 2.6)))
            light = 1.0 + self.pl['shadow'] * m * np.minimum(lit, 0.45)
            light -= 0.035 * m * cv2.GaussianBlur(shcov, (0, 0), 30)
            no_sh = cv2.GaussianBlur((Lr > 0.80).astype(np.float32), (0, 0), 4)   # daylight in a window takes no shadow
            light = 1.0 + (light - 1.0) * (1 - no_sh)
        part *= light[..., None]
        # backing: a soft shade of the word's own shape on what is behind it, so it reads over a bright window
        if self.pl['backing'] > 0:
            bs = max(3.0, 0.07 * self.hpx)
            bk = cv2.warpAffine(cov_f, np.float32([[1, 0, 0.02 * self.hpx], [0, 1, 0.035 * self.hpx]]), fsize, flags=lin)
            bk = np.clip(cv2.GaussianBlur(bk, (0, 0), bs) * 1.5, 0, 1)
            kb = self.pl['backing'] * m * bk * (0.45 + 0.55 * sstep(0.35, 0.8, Lr))
            part[:] = part * (1 - kb[..., None]) + self.ink * kb[..., None]
        # --- thick pane at an angle: everything behind it steps sideways
        e3 = ps['e3'].astype(np.float32)
        vdn = view @ e3
        wv = view - vdn[..., None] * e3
        sin_i = np.linalg.norm(wv, axis=-1)
        cos_i = np.abs(vdn)
        tan_i = sin_i / np.maximum(cos_i, 1e-4)
        sin_r = sin_i / ior
        tan_r = sin_r / np.sqrt(1 - sin_r * sin_r)
        lat = (tn * depth) * (tan_i - tan_r) * cos_i
        wn = wv / np.maximum(sin_i[..., None], 1e-5)
        dX = -lat[..., None] * wn
        sx = scale * (dX[..., 0] - xp * dX[..., 2])
        sy = scale * (dX[..., 1] - yp * dX[..., 2])
        # --- refract the room: 5 wavelengths, red bends least
        disp = float(C['DISPERSION'])
        wts = np.array([[0.52, 0.36, 0.12, 0.00, 0.00],               # R
                        [0.00, 0.22, 0.56, 0.22, 0.00],               # G
                        [0.00, 0.00, 0.12, 0.36, 0.52]], np.float32)  # B
        refr = np.zeros((rh * ss, rw * ss, 3), np.float32)
        for j, lm in enumerate((-1.0, -0.5, 0.0, 0.5, 1.0)):
            kk = 1.0 + disp * lm
            mx = (gx + sx * (1 + 0.35 * disp * lm) + dxr * kk).astype(np.float32)
            my = (gy + sy * (1 + 0.35 * disp * lm) + dyr * kk).astype(np.float32)
            refr += cv2.remap(lit_room, mx, my, lin, borderMode=cv2.BORDER_REFLECT_101) * wts[:, j][None, None, :]
        behind = cv2.remap(lit_room, gx, gy, lin, borderMode=cv2.BORDER_REFLECT_101)
        Lb = cv2.GaussianBlur(lum(behind), (0, 0), 3 * ss)
        edge = sstep(0.5, 2.2, gmag)
        absorb = np.exp(-tn[..., None] * self.absorb * (0.4 + 0.6 * m))
        glass = refr * absorb * (1 - 0.20 * edge * m)[..., None]
        # --- front face: bevel normals in 3D -> fresnel reflection of the room + the key light
        g2 = cv2.warpPerspective(sl.grad, h_front, size, flags=lin)
        e1f, e2f = ps['e1'].astype(np.float32), ps['e2'].astype(np.float32)
        nrm = -e3[None, None, :] - (g2[..., 0:1] * e1f + g2[..., 1:2] * e2f) * np.float32(0.35 + 0.65 * m)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        vn = np.sum(view * nrm, -1)
        refl = view - 2 * vn[..., None] * nrm
        fres = 0.04 + 0.96 * (1 - np.clip(-vn, 0, 1)) ** 5
        up = (-self.r2).astype(np.float32)
        hemi = 0.5 + 0.5 * (refl @ up)
        env = self.env_lo + (self.env_hi - self.env_lo) * sstep(0.25, 0.85, hemi)[..., None]
        pk = ps['o'] + ps['key'] * gw * ps['e1'] + 0.5 * gh * ps['e2']
        vk = pk / np.linalg.norm(pk)
        lk = vk - 2 * (vk @ -ps['e3']) * -ps['e3']
        ax_a = ps['e1'] - (ps['e1'] @ lk) * lk
        ax_a /= np.linalg.norm(ax_a)
        ax_b = np.cross(lk, ax_a)
        ax_a = ax_a * math.cos(0.21) + ax_b * math.sin(0.21)
        ax_b = np.cross(lk, ax_a)
        rimn = np.clip(g2[..., 2], 0, 1)
        rough = 0.015 + 0.11 * rimn
        strip = np.exp(-0.5 * ((refl @ ax_a.astype(np.float32)) / rough) ** 2
                       - 0.5 * ((refl @ ax_b.astype(np.float32)) / 0.34) ** 2) * (refl @ lk.astype(np.float32) > 0)
        ceil = np.clip(refl @ up, 0, 1)
        spec = strip * (float(C['KEY_GAIN']) * (1 - rimn) + 0.85 * rimn * np.sqrt(0.015 / rough)) + 0.16 * ceil ** 5 * rimn
        front_w = front * m
        glass = (glass * (1 - fres * front_w)[..., None]
                 + (env * fres[..., None] + self.accent * spec[..., None]) * front_w[..., None])
        b2 = cv2.warpPerspective(sl.rim, h_back, size, flags=lin)
        back_line = sstep(0.5, 1.6, b2) * (1 - front) * cov
        glass += back_line[..., None] * m * np.array([24, 22, 20], np.float32)
        # --- readability: the dark rim every thick glass edge has (stronger over light), a thin rim light on the
        #     bevels that face the light (stronger over dark), and a hairline just outside the edge
        rpx = int(round(np.clip(1.4 + 0.012 * self.hpx, 1.8, 4.5) * ss))
        inner = cv2.erode(front, ell(2 * rpx + 1))
        ring = np.clip(front - inner, 0, 1)
        ring = cv2.GaussianBlur(ring, (0, 0), 0.6 * ss)
        kd = self.pl['rim_dark'] * m * (0.35 + 0.65 * sstep(0.30, 0.80, Lb)) * ring
        glass = glass * (1 - kd[..., None]) + self.ink * kd[..., None]
        gn = np.hypot(g2[..., 0], g2[..., 1]) + 1e-6
        facing = np.clip(-(g2[..., 0] * self.l2[0] + g2[..., 1] * self.l2[1]) / gn, 0, 1) * np.clip(rimn * 1.4, 0, 1)
        rl = self.pl['rim_light'] * m * facing ** 1.5 * front * (0.45 + 0.55 * (1 - sstep(0.4, 0.9, Lb)))
        glass += self.accent * (0.42 * rl)[..., None]
        out_ss = behind * (1 - cov[..., None]) + glass * cov[..., None]
        outer = np.clip(cv2.dilate(cov, ell(2 * ss + 1)) - cov, 0, 1)
        ko = 0.55 * self.pl['rim_dark'] * m * outer * (0.3 + 0.7 * sstep(0.35, 0.8, Lb))
        out_ss = out_ss * (1 - ko[..., None]) + self.ink * ko[..., None]
        over = cv2.resize(out_ss - behind, fsize, interpolation=cv2.INTER_AREA)
        delta = (lit_room[y0:y1, x0:x1] - room[y0:y1, x0:x1]) + over
        return (x0, y0, x1, y1), cv2.GaussianBlur(delta, (0, 0), 0.5)

    def frame(self, f, orig, alpha):
        """orig: uint8 RGB frame, alpha: uint8 cutout. -> uint8 RGB with the glass behind him."""
        if not self.active(f):
            return orig
        inv_plate = cv2.warpPerspective(self.plate, self.cam[f], (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        hole = cv2.dilate((alpha > 4).astype(np.uint8) * 255, ell(9))
        hole = cv2.GaussianBlur(hole, (0, 0), 1.6).astype(np.float32)[..., None] / 255
        room = orig.astype(np.float32) * (1 - hole) + inv_plate * hole
        r = self.render(room, f)
        if r is None:
            return orig
        (x0, y0, x1, y1), delta = r
        a = alpha[y0:y1, x0:x1].astype(np.float32)[..., None] / 255
        out = orig.astype(np.float32)
        out[y0:y1, x0:x1] += delta * (1 - a)
        return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def rot(v, axis, deg):
    a = math.radians(deg)
    axis = axis / np.linalg.norm(axis)
    return v * math.cos(a) + np.cross(axis, v) * math.sin(a) + axis * np.dot(axis, v) * (1 - math.cos(a))


def safe_guide(img):
    img = img.copy()
    cv2.rectangle(img, (35, 220), (W - 35, 1470), (255, 40, 40), 3)
    cv2.rectangle(img, (W - 100, 1155), (W - 35, 1470), (255, 40, 40), 3)
    return img


# ------------------------------------------------------------------------------------------------------------ run
_G = None


def _load_plan():
    if not os.path.exists(P('work', 'plan.json')):
        sys.exit('work/plan.json is missing: run `glass.py measure` first')
    return json.load(open(P('work', 'plan.json')))


def _init():
    global _G
    _G = Glass(_load_plan(), clip_block())


def _chunk(span):
    a, b = span
    out = []
    for k, (rgb, al) in enumerate(zip(reader(P('assets', 'aroll.mp4'), W, H, first=a, last=b),
                                      reader(P('assets', 'subject.webm'), W, H, alpha=True, first=a, last=b))):
        out.append(_G.frame(a + k, rgb, al).tobytes())
    return a, out


def stills(frames):
    pl = _load_plan()
    if not frames:
        f_land = pl['f_in'] + int(IN_DUR * FPS)
        f_out = pl['N'] if pl['t_out'] is None else int(pl['t_out'] * FPS)
        frames = [0, pl['f_in'] + 5, f_land, (f_land + f_out) // 2, f_out + 8, pl['N'] - 1]
    frames = sorted({min(max(0, f), pl['N'] - 1) for f in frames})
    _init()
    os.makedirs(P('work', 'stills'), exist_ok=True)
    tiles = []
    safe = os.environ.get('SAFE', '0') == '1'
    for f in frames:
        _, fr = _chunk((f, f))
        img = np.frombuffer(fr[0], np.uint8).reshape(H, W, 3)
        if safe:
            img = safe_guide(img)
        Image.fromarray(img).save(P('work', 'stills', f'f_{f:03d}.jpg'), quality=92)
        t = cv2.resize(img, (180, 320), interpolation=cv2.INTER_AREA)
        cv2.putText(t, f'f{f}', (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        tiles.append(t)
    sheet = np.hstack(tiles)
    Image.fromarray(sheet).save(P('work', 'stills', 'sheet.jpg'), quality=90)
    print('wrote work/stills/sheet.jpg (' + ', '.join(f'f{f}' for f in frames) + ')')


def bake():
    pl = _load_plan()
    n = pl['N']
    t0 = time.time()
    workers = int(os.environ.get('WORKERS', 0)) or max(1, min(4, cpu_count() - 1))
    size = 8
    spans = [(a, min(n - 1, a + size - 1)) for a in range(0, n, size)]
    out = P('assets', 'fx.mp4')
    w = writer(out)
    with Pool(workers, initializer=_init) as pool:
        for a, frames in pool.imap(_chunk, spans):
            for fr in frames:
                w.stdin.write(fr)
            print(f'  frames {a}..{a + len(frames) - 1}', flush=True)
    w.stdin.close()
    w.wait()
    got = count_frames(out)
    secs = time.time() - t0
    json.dump(dict(seconds=round(secs, 1), per_slot_second=round(secs / (n / FPS), 1), workers=workers),
              open(P('work', 'bake_time.json'), 'w'))
    print(f'wrote assets/fx.mp4: {got} frames ({"ok" if got == n else "!! expected " + str(n)}), {secs:.0f} s, '
          f'{secs / (n / FPS):.1f} s per second of slot, {workers} workers')
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'measure':
        measure()
    elif cmd == 'still':
        stills([int(v) for v in sys.argv[2:]])
    elif cmd == 'bake':
        bake()
    else:
        sys.exit(__doc__)
