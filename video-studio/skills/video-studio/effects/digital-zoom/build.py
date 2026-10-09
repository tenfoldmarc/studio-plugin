#!/usr/bin/env python3
"""digital-zoom: word-timed digital zooms that aim at their face (slow creep, hard snap with real zoom blur, whip pull-back).

Run order, from the slot folder (exact commands in effect.md):
  onsets.py -> edit the CLIP block below -> track.py -> build.py -> bake.py -> hyperframes render -> post.py

  build.py   ZOOMS + work/headtrack.json -> work/camera.json (one crop per sub-frame) + index.html (grade, captions, whoosh)
  SAFE=1      draw the IG safe zone, the eye target and the chin line (snapshots only, never for the render)
  CAPTIONS=0  no caption words (the main reel captions the slot)
  SFX=0       no whoosh
  GRADE=0     no grade / vignette / flash (the main reel grades the slot: use this when the slot sits inside a graded reel)
  HI=0        ignore assets/aroll_hi.mp4 and work from the 1080 a-roll (scale is capped lower)
"""
import json
import math
import os
import shutil
import subprocess
import sys

FPS = 30


def F(n):
    """time of frame n (so the CLIP block can be written in frames)"""
    return n / FPS


def zoom(t_start, t_land, scale, kind, **kw):
    """One camera move. Times in seconds (use F(frame)), scale relative to the full frame (1.0 = the wide).
    kind 'creep': slow eased move that settles on t_land.
         'snap' : hard punch, arrives at full speed on t_land, overshoots and recoils. Gets the whoosh.
         'pull' : fast whip (most of the travel in the first third), small after-settle. Usually back to 1.0.
    Optional: drift=<log-scale per second the shot keeps creeping after it lands; 0 holds it dead still>,
              over=<snap overshoot / pull settle, as a fraction>, sfx=False <no whoosh on this snap>."""
    return dict(t0=t_start, t1=t_land, scale=scale, kind=kind, **kw)


# ==== CLIP (edit this) ====
# The values below are the demo clip ("and you don't need to be techy or know anything about video editing in order
# to use it", 138 frames, wide shot on the floor). Replace all of them for a new clip.

# The zooms, in order. zoom(t_start, t_land, scale, kind). Frames come from `onsets.py` (audio envelope per frame):
#   creep: t_start = first word of the line, t_land = 2 frames AFTER the vowel of the word it lands on
#   snap : t_land = the vowel of the stressed syllable, t_start = 3 frames before it
#   pull : t_start = onset of the word it leaves on, t_land = about 9 frames later
# Scale: build.py prints the lossless limit for this source and caps anything past MAX_UPSCALE times that.
ZOOMS = [
    zoom(F(1), F(37), 1.62, 'creep'),       # starts on "and", motion dies on the vowel of "TECH-y" (f35)
    zoom(F(83), F(86), 2.26, 'snap'),       # leaves on the "v", peak lands on the vowel of "VI-deo" (f86)
    zoom(F(108), F(117), 1.0, 'pull'),      # leaves on "in" (f108), wide again before "order" ends
]
# Where the speaker's eyes sit on screen while the shot is tight (x, y). 540 = centred, 640 = upper third line. On a close-up
# selfie go a little higher (about 620) so the chin leaves room for captions. build.py prints from which scale the frame
# can hold the speaker there ("aim: ..."): start a snap above that scale, or the snap also slides the picture.
EYE = (540, 640)
# How tightly the camera follows the speaker's head: gaussian sigma in frames. 5 = an operator following the speaker. Raise to 8-10 if
# the background swims on a still tripod shot, lower to 3 on handheld footage where the face must stay pinned.
FOLLOW = 5
# Optional manual aim, only if work/track_check.jpg shows the cross off the speaker's eyes: (frame, x, y) of the point between
# the speaker's eyes in that frame of assets/aroll.mp4. None = automatic from the cutout.
AIM = None
# How far past the lossless zoom of the source a scale may go (1.5 = 150% upscale, still clean with the unsharp pass).
MAX_UPSCALE = 1.5
# Captions (dropped with CAPTIONS=0). One tuple per group: (last frame on screen or None, lines).
#   line = (top px, size, words), size 'sm' 84px | 'lg' 190px | 'big' 236px | a number of px, word = (frame it is spoken, text, 'y' yellow or '').
#   Keep every top below the chin: build.py prints "clearance" per group and warns when a group is too close, too low or too wide.
#   A group that ends where a snap starts is pushed through, one that ends where a pull starts is left behind.
CAPS = [
    (54, [(1000, 'sm', [(8, 'you', ''), (13, 'don’t', ''), (18, 'need', ''), (23, 'to', ''), (26, 'be', '')]),
          (1082, 'big', [(33, 'techy', 'y')])]),
    (83, [(1000, 'sm', [(56, 'or', ''), (59, 'know', ''), (65, 'anything', ''), (78, 'about', '')])]),
    (108, [(1062, 'lg', [(86, 'video', '')]),
           (1228, 'lg', [(95, 'editing', 'y')])]),
    (None, [(1000, 'sm', [(110, 'in', ''), (113, 'order', ''), (120, 'to', '')]),
            (1082, 'big', [(123, 'use', ''), (130, 'it.', '')])]),
]
# Whoosh volume on each snap, relative to the template (0.75 gain is applied on top). 0 = none. Keep it under the speaker's voice.
WHOOSH = 0.26
# Grade on the picture (dropped with GRADE=0). A soft contrast base look, a touch lighter so skin stays natural.
GRADE = 'contrast(1.06) saturate(.93) brightness(.98)'
# ==== END CLIP ====


# =====================================================================================================================
# MACHINERY (nothing clip-specific below)
# =====================================================================================================================
HERE = os.path.dirname(os.path.abspath(__file__))
NAME = os.path.basename(HERE)
FP = shutil.which('ffprobe') or 'ffprobe'
ON = {k: os.environ.get(k, '1') != '0' for k in ('CAPTIONS', 'SFX', 'GRADE', 'HI')}
SAFE = bool(os.environ.get('SAFE')) and os.environ.get('SAFE') != '0'
SHUTTER = 0.62         # fraction of a frame the virtual shutter is open on fast moves (forward from the frame time)
BLUR_FROM, BLUR_FULL, BLUR_FLOOR = 28, 95, .1    # px/frame of corner travel where the blur starts / is full; floor
NMAX = 48              # most sub-frame samples averaged for one frame (fewer shows as stepped streaks on hard edges)
CHIN_K = 0.80          # chin below the eye line, in head widths (caption clearance check)
CHIN_GAP = 40          # px a caption line must stay under the chin
DRIFT = {'creep': .022, 'snap': .035, 'pull': 0}   # default slow push after a landing (log-scale per second)
WHOOSH_FILE, WHOOSH_CREST = 'whoosh-short', .16     # stock template sound; its loudest point is 0.16s in
SFX_GAIN = 0.75
YEL = '#FAE67A'


def probe(path, entries):
    return subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', entries, '-of', 'csv=p=0',
                           os.path.join(HERE, path)], capture_output=True, text=True).stdout.strip()


CLIPJ = json.load(open(os.path.join(HERE, 'clip.json'))) if os.path.exists(os.path.join(HERE, 'clip.json')) else {}
NFR = int(CLIPJ.get('frames') or probe('assets/aroll.mp4', 'stream=nb_frames'))
DUR = NFR / FPS
if CLIPJ.get('cut_frames'):
    print(f"!! clip.json lists cuts at {CLIPJ['cut_frames']}: a digital zoom wants one continuous shot (the face track resets at a cut)")
SRC = 'assets/aroll_hi.mp4' if ON['HI'] and os.path.exists(os.path.join(HERE, 'assets/aroll_hi.mp4')) else 'assets/aroll.mp4'
HW, HH = (int(v) for v in probe(SRC, 'stream=width,height').split(',')[:2])
COVER = max(1080 / HW, 1920 / HH)                    # aroll.mp4 = the source scaled to cover 1080x1920, centre-cropped
LOSSLESS = 1 / COVER
OFFX, OFFY = (HW - 1080 / COVER) / 2, (HH - 1920 / COVER) / 2
MAXS = LOSSLESS * MAX_UPSCALE
NOTES = []

# ---------------------------------------------------------------- checks on the CLIP block
if not ZOOMS:
    sys.exit('ZOOMS is empty: add at least one zoom(...) to the CLIP block')
for i, z in enumerate(ZOOMS):
    if z['kind'] not in DRIFT:
        sys.exit(f"zoom {i + 1}: kind must be creep, snap or pull (got {z['kind']!r})")
    if not z['t0'] < z['t1']:
        sys.exit(f'zoom {i + 1}: t_start must be before t_land')
    if i and z['t0'] < ZOOMS[i - 1]['t0']:
        sys.exit(f'zoom {i + 1} starts before zoom {i}: list them in order')
    if z['t1'] > DUR + 1e-6:
        sys.exit(f"zoom {i + 1} lands at frame {z['t1'] * FPS:.0f} but the clip has {NFR} frames: edit the CLIP block for this clip")
    if z['scale'] < 1:
        sys.exit(f'zoom {i + 1}: scale below 1.0 would show the edge of the picture')
    peak = z['scale'] * (1 + z.get('over', .04)) if z['kind'] == 'snap' else z['scale']
    if peak > MAXS + 1e-6:
        new = round(MAXS / (peak / z['scale']), 3)
        NOTES.append(f"zoom {i + 1}: {z['scale']}x capped to {new}x (source {HW}x{HH} is lossless to {LOSSLESS:.2f}x, "
                     f"MAX_UPSCALE {MAX_UPSCALE} allows {MAXS:.2f}x at the peak)")
        z['scale'] = max(1.0, new)
T_LAST = F(NFR - 1)


# ---------------------------------------------------------------- scale curve
def _creep(u, k=.74):
    """ease with a late inflection: gathers speed for 3/4 of the move, then brakes into the word"""
    u = min(1, max(0, u))
    return u * u / k if u < k else 1 - (1 - u) ** 2 / (1 - k)


def _snap(u):
    return min(1, max(0, u)) ** 1.5      # still accelerating when it arrives: reads as a hit


def _pull(u):
    u = min(1, max(0, u)) ** 1.2         # one soft frame to get going, then expo out
    return 1 - (1 - u) ** 3.6


def _smooth(x):
    x = min(1, max(0, x))
    return x * x * (3 - 2 * x)


def _drift(z, dt, tau=.25):
    """slow continued push after a landing, eased in so there is no kink. Only while zoomed in."""
    rate = z.get('drift', DRIFT[z['kind']]) if z['scale'] > 1.001 else 0
    return rate * (dt - tau * (1 - math.exp(-dt / tau))) if dt > 0 else 0


def _seg(z, ls_from, t, last):
    """log-scale of zoom z at time t >= z.t0, coming from log-scale ls_from"""
    t0, t1, tgt = z['t0'], z['t1'], math.log(z['scale'])
    u, dt = (t - t0) / (t1 - t0), t - t1
    way = 1 if tgt >= ls_from else -1
    if z['kind'] == 'creep':
        return ls_from + (tgt - ls_from) * _creep(u) + _drift(z, dt)
    if z['kind'] == 'snap':
        over = way * math.log(1 + z.get('over', .04))
        if u < 1:
            return ls_from + (tgt + over - ls_from) * _snap(u)
        return tgt + over * math.exp(-dt / (2.2 / FPS)) + _drift(z, dt)        # recoil from the peak
    settle = -way * math.log(1 + z.get('over', .028))                           # pull: lands a hair short, then settles
    if u < 1:
        return ls_from + (tgt + settle - ls_from) * _pull(u)
    fade = 1 - _smooth(dt / max(1e-6, T_LAST - t1)) if last else 1              # the last move ends EXACTLY on its scale
    return tgt + settle * math.exp(-dt / .22) * fade + _drift(z, dt)


def scale_at(t):
    ls = 0.0
    for i, z in enumerate(ZOOMS):
        if t < z['t0']:
            break
        nxt = ZOOMS[i + 1]['t0'] if i + 1 < len(ZOOMS) else None
        if nxt is not None and t >= nxt:
            ls = _seg(z, ls, nxt, False)     # where this move had got to when the next one took over
            continue
        ls = _seg(z, ls, t, nxt is None)
        break
    return min(MAXS, max(1.0, math.exp(ls)))


# ---------------------------------------------------------------- head track -> smooth face path
def _gauss(vals, sigma):
    r = max(1, int(3 * sigma))
    ker = [math.exp(-.5 * (k / max(sigma, 1e-3)) ** 2) for k in range(-r, r + 1)]
    out = []
    for i in range(len(vals)):
        acc = w = 0
        for k in range(-r, r + 1):
            j = min(len(vals) - 1, max(0, i + k))
            acc += ker[k + r] * vals[j]; w += ker[k + r]
        out.append(acc / w)
    return out


def _median(vals, r=2):
    return [sorted(vals[max(0, i - r):i + r + 1])[len(vals[max(0, i - r):i + r + 1]) // 2] for i in range(len(vals))]


HT_PATH = os.path.join(HERE, 'work/headtrack.json')
if not os.path.exists(HT_PATH):
    sys.exit('work/headtrack.json is missing: run track.py first')
HT = json.load(open(HT_PATH))
if HT['frames'] != NFR:
    sys.exit(f"head track has {HT['frames']} frames, the clip has {NFR}: run track.py again")
if (HT.get('aim') or None) != (list(AIM) if AIM else None):
    sys.exit('AIM changed since the last track: run track.py again')
HEAD_W = HT['head_w']
FX = _gauss(_median([o['eye_x'] for o in HT['track']]), FOLLOW)
FY = _gauss(_median([o['eye_y'] for o in HT['track']]), FOLLOW)


def face_at(t):
    x = min(NFR - 1, max(0, t * FPS))
    i = min(NFR - 2, int(x)); a = x - i
    return FX[i] * (1 - a) + FX[i + 1] * a, FY[i] * (1 - a) + FY[i + 1] * a


def _reach(eye, face, size):
    """scale from which the crop can move far enough to put a face at `face` on the screen position `eye`"""
    return (size - eye) / max(1, size - face) if eye < face else eye / max(1, face)


# At 1.0x the frame cannot move at all, so the aim blends in as the crop frees up. S_REACH is the scale from which EYE
# is reachable for where the speaker usually sits; the blend finishes a little after it. (Fixed at .35 it finished too late on
# an off-centre close-up: a snap from 1.1x then spent its 3 frames sliding the frame and smeared the speaker's face.)
_MX, _MY = sorted(FX)[len(FX) // 2], sorted(FY)[len(FY) // 2]
S_REACH = max(_reach(EYE[0], _MX, 1080), _reach(EYE[1], _MY, 1920))
AIM_RANGE = min(.35, max(.12, 1.25 * (S_REACH - 1)))


def camera_at(t):
    """-> scale, crop left/top in 1080-space, eye position on screen"""
    s = scale_at(t)
    fx, fy = face_at(t)
    w = _smooth((s - 1) / AIM_RANGE)
    ex, ey = fx + (EYE[0] - fx) * w, fy + (EYE[1] - fy) * w
    left = min(1080 - 1080 / s, max(0, fx - ex / s))
    top = min(1920 - 1920 / s, max(0, fy - ey / s))
    return s, left, top, (fx - left) * s, (fy - top) * s


def solve():
    frames = []
    for f in range(NFR):
        t = F(f)
        s, l, tp, ex, ey = camera_at(t)

        def travel(dt):
            """how far the picture moves on screen in dt seconds (worst corner)"""
            s2, l2, t2, _, _ = camera_at(t + dt)
            return max(math.hypot((l + cx / s - l2) * s2 - cx, (tp + cy / s - t2) * s2 - cy)
                       for cx, cy in ((0, 0), (1080, 0), (0, 1920), (1080, 1920)))

        # blur only what is fast: a creep stays crisp (a soft creep just looks out of focus), a snap streaks
        speed = travel(1 / FPS)                              # px per frame
        shutter = SHUTTER * min(1, max(BLUR_FLOOR, (speed - BLUR_FROM) / (BLUR_FULL - BLUR_FROM)))
        d = travel(shutter / FPS)
        n = min(NMAX, max(1, math.ceil(d / 2.2)))
        boxes = []
        for j in range(n):
            sj, lj, tj, _, _ = camera_at(t + shutter / FPS * j / n)
            boxes.append([round(OFFX + lj / COVER, 3), round(OFFY + tj / COVER, 3),
                          round(OFFX + (lj + 1080 / sj) / COVER, 3), round(OFFY + (tj + 1920 / sj) / COVER, 3)])
        frames.append({'f': f, 'scale': round(s, 5), 'eye': [round(ex, 1), round(ey, 1)], 'blur_px': round(d, 1), 'boxes': boxes,
                       'chin': round(ey + CHIN_K * HEAD_W * s, 1)})
    return frames


CAM = solve()
os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
json.dump({'name': NAME, 'src': SRC, 'w': 1080, 'h': 1920, 'fps': FPS, 'lossless': LOSSLESS, 'frames': CAM},
          open(os.path.join(HERE, 'work/camera.json'), 'w'))
SNAP_START = [round(z['t0'] * FPS) for z in ZOOMS if z['kind'] == 'snap']
SNAP_LAND = [round(z['t1'] * FPS) for z in ZOOMS if z['kind'] == 'snap']
PULL_START = [round(z['t0'] * FPS) for z in ZOOMS if z['kind'] == 'pull']


# ---------------------------------------------------------------- captions
def T(frame, lead=1.4):
    """tween start so the word is already half formed ON its frame (a tween that starts on the frame shows nothing there)"""
    return max(0, (frame - lead) / FPS)


def _px(size):
    """caption size in px: a name ('sm' 84, 'lg' 190, 'big' 236) or a number"""
    return {'sm': 84, 'lg': 190, 'big': 236}.get(size, size) if isinstance(size, str) else size


def captions():
    html, tw = [], []
    for g, (last, lines) in enumerate(CAPS):
        gid = f'g{g}'
        rows = []
        for li, (top, size, words) in enumerate(lines):
            spans = []
            px = _px(size)
            small = px <= 100
            for k, (fr, txt, cls) in enumerate(words):
                wid = f'c{g}x{li}x{k}'
                spans.append(f'<span id="{wid}" class="w {cls}">{txt}</span>')
                tw.append(f"gsap.set('#{wid}',{{autoAlpha:0}});")
                # blur stays <= 18px: a bigger blur at low alpha shows up as a grey smudge for a frame, not as a word
                if not small and any(0 <= fr - s <= 1 for s in SNAP_LAND):
                    # lands with a snap: one soft oversized frame while the picture is still travelling, crisp on the hit
                    tw.append(f"tl.fromTo('#{wid}',{{autoAlpha:0,scale:1.5,filter:'blur(18px)'}},{{autoAlpha:1,scale:1,filter:'blur(0px)',"
                              f"duration:.13,ease:'expo.out',immediateRender:false}},{T(fr):.3f});")
                elif not small:
                    tw.append(f"tl.fromTo('#{wid}',{{autoAlpha:0,scale:1.3,filter:'blur(16px)'}},{{autoAlpha:1,scale:1,filter:'blur(0px)',"
                              f"duration:.2,ease:'power3.out',immediateRender:false}},{T(fr):.3f});")
                else:
                    tw.append(f"tl.fromTo('#{wid}',{{autoAlpha:0,scale:1.2,y:8,filter:'blur(14px)'}},{{autoAlpha:1,scale:1,y:0,filter:'blur(0px)',"
                              f"duration:.18,ease:'power3.out',immediateRender:false}},{T(fr):.3f});")
            cls_size = size if isinstance(size, str) else ('sm' if small else 'lg')
            fs = '' if isinstance(size, str) else f';font-size:{px}px'
            rows.append(f'<div class="line {cls_size}" style="top:{top}px{fs}">{"".join(spans)}</div>')
        oy = sum(l[0] for l in lines) / len(lines) + 90
        html.append(f'<div id="{gid}" class="grp" style="transform-origin:540px {oy:.0f}px">{"".join(rows)}</div>')
        if last is None or last >= NFR - 1:
            continue
        t_out = F(last)
        if any(abs(last - s) <= 1 for s in SNAP_START):      # the snap goes straight through it
            tw.append(f"tl.to('#{gid}',{{autoAlpha:0,scale:1.5,filter:'blur(18px)',duration:.085,ease:'none'}},{t_out - .5 / FPS:.3f});")
            t_kill = t_out + .07
        elif any(abs(last - s) <= 1 for s in PULL_START):    # the pull-back leaves it behind
            tw.append(f"tl.to('#{gid}',{{autoAlpha:0,scale:.62,filter:'blur(20px)',duration:.12,ease:'power2.out'}},{t_out - .004:.3f});")
            t_kill = t_out + .12
        else:
            tw.append(f"tl.to('#{gid}',{{autoAlpha:0,scale:.96,filter:'blur(16px)',duration:.12,ease:'power2.in'}},{t_out - .12:.3f});")
            t_kill = t_out
        tw.append(f"tl.set('#{gid}',{{autoAlpha:0}},{t_kill + .002:.3f});")
    return html, tw


def clearance():
    """captions may never touch their face: the lowest chin position while each group is up vs the group's top line"""
    rep = []
    for g, (last, lines) in enumerate(CAPS):
        f0 = min(fr for _, _, ws in lines for fr, _, _ in ws)
        f1 = min(NFR - 1, last if last is not None else NFR - 1)
        if f0 > f1:
            rep.append(f'group {g + 1}: !! first word at frame {f0} is after the group ends ({f1})')
            continue
        chin = max(c['chin'] for c in CAM[f0:f1 + 1])
        top = min(l[0] for l in lines)
        low = max(l[0] + _px(l[1]) * 1.05 for l in lines)
        wide = ''
        for ltop, size, ws in lines:                         # rough width (Inter Tight 800/900, tight tracking), centred on 540
            px = _px(size)
            est = px * (.50 if px <= 100 else .53) * len(' '.join(w[1] for w in ws))
            limit = 980 if ltop + px > 1155 else 1045        # the right 100px column is closed from y 1155 down
            if 540 + est / 2 > limit or 540 - est / 2 < 35:
                wide += (f'  !! "{" ".join(w[1] for w in ws)}" is about {est:.0f}px wide (x {540 - est / 2:.0f}-{540 + est / 2:.0f}), past the '
                         f'safe zone (x 35-{limit} at that height): use a smaller size (a number of px works) or fewer words')
        rep.append(f'group {g + 1} (f{f0}-{f1}): chin {chin:.0f}, top line {top} ({top - chin:+.0f}px)'
                   + ('  !! TOO CLOSE TO HIS CHIN: move it down' if top - chin < CHIN_GAP else '')
                   + (f'  !! runs to y {low:.0f}, past the 1470 safe line' if low > 1470 else '') + wide)
    return rep


# ---------------------------------------------------------------- look: vignette breathes with the zoom
def look():
    smax = max(1.02, max(c['scale'] for c in CAM))

    def vig(c):
        return .25 + .75 * math.log(c['scale']) / math.log(smax)

    kf = ','.join(f"{{opacity:{vig(c):.3f},duration:{1 / FPS:.5f},ease:'none'}}" for c in CAM[1:])
    tw = [f"gsap.set('#vigin',{{opacity:{vig(CAM[0]):.3f}}});", f"tl.to('#vigin',{{keyframes:[{kf}]}},0);", "gsap.set('#flash',{opacity:0});"]
    for z in ZOOMS:
        if z['kind'] == 'snap':       # a breath of exposure as the punch lands
            tw += [f"tl.to('#flash',{{opacity:.16,duration:{1 / FPS - .003:.4f},ease:'none'}},{z['t1'] - 1 / FPS:.4f});",
                   f"tl.to('#flash',{{opacity:0,duration:.3,ease:'power2.out'}},{z['t1']:.4f});"]
    return tw


def audio():
    wav = os.path.join(HERE, f'assets/sfx/{WHOOSH_FILE}.mp3')
    if not (ON['SFX'] and WHOOSH and os.path.exists(wav)):
        return []
    length = float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', wav],
                                  capture_output=True, text=True).stdout)
    out, lanes = [], []
    hits = [z for z in ZOOMS if z['kind'] == 'snap' and z.get('sfx', True)]
    for k, z in enumerate(hits):
        t = z['t1'] - .5 / FPS - WHOOSH_CREST          # the crest falls on the last travelling frame
        skip = max(0, -t)
        t = max(0, t)
        d = min(length - skip, DUR - t)
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0); lane = len(lanes) - 1
        lanes[lane] = t + d
        vol = WHOOSH * (z['sfx'] if isinstance(z.get('sfx'), (int, float)) and not isinstance(z.get('sfx'), bool) else 1)
        out.append(f'<audio id="sfx{k}" src="assets/sfx/{WHOOSH_FILE}.mp3" data-start="{t:.3f}" data-media-start="{skip:.3f}" '
                   f'data-duration="{d:.3f}" data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


GRADE_CSS = f';filter:{GRADE}' if ON['GRADE'] and GRADE else ''
CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#stage{{position:absolute;inset:0;z-index:0}}
#bgv{{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover{GRADE_CSS}}}
.fx{{position:absolute;inset:0;pointer-events:none}}
#tone{{z-index:2;background:linear-gradient(180deg,rgba(20,55,75,.14),rgba(60,40,20,.07));mix-blend-mode:soft-light}}
#vig{{z-index:2;background:radial-gradient(95% 62% at 50% 44%,rgba(0,0,0,0) 58%,rgba(0,0,0,.26) 100%)}}
#vigin{{z-index:2;background:radial-gradient(80% 54% at 50% 36%,rgba(0,0,0,0) 50%,rgba(0,0,0,.30) 100%),
  linear-gradient(180deg,rgba(0,0,0,0) 52%,rgba(0,0,0,.16) 80%,rgba(0,0,0,.20) 100%)}}
#grad{{z-index:2;background:linear-gradient(180deg,rgba(0,0,0,.16) 0%,rgba(0,0,0,0) 15%,rgba(0,0,0,0) 54%,rgba(0,0,0,.20) 100%)}}
#flash{{z-index:3;background:#FFF8EF;mix-blend-mode:soft-light}}
.grp{{position:absolute;inset:0;z-index:8}}
.line{{position:absolute;left:0;right:0;text-align:center;white-space:nowrap;color:#fff;font-family:'Inter Tight';font-weight:900;
  letter-spacing:-.05em;line-height:.9;text-shadow:0 10px 40px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.38)}}
.w{{display:inline-block;margin:0 .1em;transform-origin:50% 62%}}
.sm{{font-size:84px;font-weight:800;letter-spacing:-.04em}}
.lg{{font-size:190px;letter-spacing:-.035em}}
.big{{font-size:236px;letter-spacing:-.04em}}
.y{{color:{YEL}}}
'''

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div>'
              '<div id="dbgeye" style="position:absolute;left:0;top:0;width:60px;height:2px;margin:-1px 0 0 -30px;background:#0ff"></div>'
              '<div id="dbgchin" style="position:absolute;left:340px;top:0;width:400px;height:2px;background:#0f0"></div></div>')


def debug_tw():
    kf_e = ','.join(f"{{x:{c['eye'][0]},y:{c['eye'][1]},duration:{1 / FPS:.5f},ease:'none'}}" for c in CAM[1:])
    kf_c = ','.join(f"{{y:{c['chin']},duration:{1 / FPS:.5f},ease:'none'}}" for c in CAM[1:])
    return [f"gsap.set('#dbgeye',{{x:{CAM[0]['eye'][0]},y:{CAM[0]['eye'][1]}}});", f"tl.to('#dbgeye',{{keyframes:[{kf_e}]}},0);",
            f"gsap.set('#dbgchin',{{y:{CAM[0]['chin']}}});", f"tl.to('#dbgchin',{{keyframes:[{kf_c}]}},0);"]


def build():
    c_html, c_tw = captions() if ON['CAPTIONS'] and CAPS else ([], [])
    tweens = (look() if ON['GRADE'] else []) + c_tw + (debug_tw() if SAFE else [])
    grade = ('<div id="tone" class="fx"></div><div id="vig" class="fx"></div><div id="vigin" class="fx"></div>'
             '<div id="grad" class="fx"></div>\n  <div id="flash" class="fx"></div>') if ON['GRADE'] else ''
    nl = '\n'
    return f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{CSS}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio())}
  <div id="stage">
    <video id="bgv" src="assets/zoom.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video>
  </div>
  {grade}
{nl.join(c_html)}
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(tweens)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''


open(os.path.join(HERE, 'index.html'), 'w').write(build())

# frames worth looking at in the final render (post.py reads this)
marks, stills = {0, NFR - 1}, []
for z in ZOOMS:
    a, b = round(z['t0'] * FPS), round(z['t1'] * FPS)
    marks |= {max(0, a - 1), a, min(NFR - 1, b), min(NFR - 1, b + 1), min(NFR - 1, b + 4)}
    marks |= set(range(a, min(NFR, b + 1))) if z['kind'] != 'creep' else {(a + b) // 2}
    stills.append(min(NFR - 1, b + (4 if z['kind'] != 'snap' else 2)))
    if z['kind'] == 'snap':
        stills.append(max(0, b - 1))
if ON['CAPTIONS']:
    marks |= {min(NFR - 1, fr + 2) for _, lines in CAPS for _, _, ws in lines for fr, _, _ in ws[-1:]}
stills = list(dict.fromkeys(stills + sorted(marks)))         # no duplicates, landings first
json.dump({'name': NAME, 'frames': NFR, 'marks': sorted(marks), 'stills': stills[:3]},
          open(os.path.join(HERE, 'work/marks.json'), 'w'))

print(f'wrote index.html + work/camera.json   slot "{NAME}"  {NFR} frames  head width {HEAD_W:.0f}px')
print(f'  picture: {SRC} {HW}x{HH}  lossless to {LOSSLESS:.2f}x, scale capped at {MAXS:.2f}x'
      + ('' if SRC.endswith('_hi.mp4') else '   (no aroll_hi: 1080 source, every zoom is an upscale, keep them modest)'))
for nline in NOTES:
    print('  !! ' + nline)
print(f'  aim: their eyes sit around ({_MX:.0f},{_MY:.0f}); EYE {EYE} is reachable from {S_REACH:.2f}x, fully framed from {1 + AIM_RANGE:.2f}x')
for i, z in enumerate(ZOOMS):
    s0 = scale_at(z['t0'])
    if z['kind'] == 'snap' and s0 < 1 + .75 * AIM_RANGE and math.hypot(EYE[0] - _MX, EYE[1] - _MY) > 60:
        print(f'  note: zoom {i + 1} snaps from {s0:.2f}x, before the frame can hold the speaker on EYE: it will also slide the picture and smear their '
              f'face for the two travelling frames. Let a creep reach about {1 + AIM_RANGE:.2f}x first, or move EYE closer to their eyes.')
print('  switches: ' + ' '.join(f'{k}={"1" if v else "0"}' for k, v in ON.items()) + f' SAFE={"1" if SAFE else "0"}')
shown = sorted(marks)
for f in shown:
    c = CAM[f]
    print(f"  f{f:3d}  scale {c['scale']:.3f}  eye ({c['eye'][0]:.0f},{c['eye'][1]:.0f})  chin {c['chin']:.0f}  blur {c['blur_px']:5.1f}px  x{len(c['boxes'])}")
if CAM[-1]['scale'] > 1.004:
    print(f"  note: the slot ends at {CAM[-1]['scale']:.2f}x, so the reel cuts back to the wide on the next frame (add a pull to end on 1.0)")
if ON['CAPTIONS'] and CAPS:
    for line in clearance():
        print('  clearance  ' + line)
elif not ON['CAPTIONS'] and CLIPJ.get('project'):
    # In a reel the slot is built with CAPTIONS=0 and the reel's own captions stay on, in the caption style the
    # buyer picked. They do not move with the zoom, so check that the chin stays clear of their band.
    try:
        _lay = json.load(open(os.path.join(CLIPJ['project'], 'layout.json'), encoding='utf-8'))
        _band = int(_lay['bands']['Y_CHEST']) + int(_lay.get('lift') or 0)
    except (OSError, ValueError, KeyError, TypeError):
        _band = None
    if _band:
        _chin = max(c['chin'] for c in CAM)
        if _chin + 100 > _band:
            print(f"  !! reel captions: at the tightest zoom the chin reaches y {_chin:.0f} and the reel's captions sit from about "
                  f"y {_band - 76}: they would touch the face. Use a smaller scale, or build with captions on (no CAPTIONS=0, "
                  'fill CAPS) and add the slot with fx_add.py --captions hide')
        else:
            print(f"  reel captions: the reel's own captions stay on (band y {_band}); the chin stays above y {_chin:.0f}, clear of them")
print('next: bake.py (needed after any change to ZOOMS / EYE / FOLLOW / AIM / HI; not for captions, grade or sound)')
