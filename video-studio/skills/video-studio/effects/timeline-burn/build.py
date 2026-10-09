#!/usr/bin/env python3
"""TIMELINE BURN: a video-editing timeline assembles in front of the speaker (lower third, under the chin), a cursor
makes two slow edits, the timeline overheats, catches fire on a spoken word, burns from right to left and crumbles
into embers. Then the plain picture is back.

  F_IN       the timeline assembles (0.5 s), the playhead starts to scrub, the room dims a little (DIM)
  edits      a cursor trims one clip and drags another (only when there are 2.3 s or more before the burn)
  heat       the last 0.8 s before the word: clips glow, the playhead stutters, sparks pop, the panel shivers
  BURN_AT    the word: flash, a fire front crosses the timeline, clips char and drop, the panel cracks and falls
  + 28 fr    everything is gone and the picture is plain again (F_OUT, printed by the build)

Layers: a-roll < dim < the timeline (built in the page from the settings below, nothing pre-rendered).
The timeline is a generic one: it copies no real editing app. Every word, label, count and colour on it is a setting.

Run order (from the slot folder, see effect.md):
  python build.py words   every spoken word with its frame          -> BURN_AT   (build.py level A B = voice level per frame)
  python build.py         measures the face, lays the timeline out, writes index.html + work/layout.jpg
                          (SAFE=1 safe-zone guide, SFX=0 no sounds, DIM=0 no dimming)
  python check.py         after the render: frame count, plain edges, burn frame, face, contact sheet, phone copy
"""
import html as html_mod
import json
import os
import random
import re
import shutil
import subprocess
import sys

# ==== STYLE (the look of everything the effect draws: set it to the reel's style before you build) ====
FONT = 'JetBrains Mono'   # typeface of every word on the timeline (track labels, timecodes, clip names). One of the
                          # fonts in assets/fonts/fonts.css, or the reel's own font once it is added to that file
WEIGHT = 500              # font weight (must exist for FONT in fonts.css)
CASE = 'upper'            # 'upper', 'lower' or 'as-typed'
TEXT = '#F7F4EE'          # colour of the words, the ruler ticks and the playhead ('#RRGGBB')
LABEL_PX = 20             # size of the track labels (design px: on screen it is this times PANEL_W / 954)
NAME_PX = 20              # size of clip names, when a track has any
ACCENT = '#FAE67A'        # the one accent: trim handle and the playhead as it heats up. Use the reel's accent colour
PANEL = 'rgba(14,15,18,.92)'           # the timeline's glass
PANEL_EDGE = 'rgba(170,190,235,.26)'   # its hairline border
PALETTE = {               # clip colours (top, bottom of each clip). A track picks one by name in TRACKS, or gives its
    'teal': ('#4C9B99', '#33706F'),    # own ('#top', '#bottom') pair. Swap these for the reel's colours.
    'violet': ('#7E73BA', '#584E90'),
    'amber': ('#B99C5E', '#8C7340'),
    'slate': ('#69788F', '#48546A'),
    'green': ('#3E8E85', '#2A6560'),
}
# The fire itself (flash, flames, embers, char) stays fire coloured: it is the effect, not a style choice.
# Where the timeline sits is PANEL_W / PANEL_X / PANEL_Y in the CLIP block.
# ==== END STYLE ====

# ==== CLIP (edit this) ====
BURN_AT = None       # REQUIRED. The spoken word the timeline catches fire on, or a frame number. 'word' = the first
                     # time it is said in the slot, 'word#2' = the second time. List the words: python build.py words
F_IN = None          # frame the timeline starts to assemble. None = 72 frames (2.4 s) before the burn, never before
                     # frame 2. At least 30 frames before the burn; under 69 frames the cursor edits are left out.
TRACKS = [           # the timeline, top to bottom (2 to 6 tracks). Per track:
                     #   label  short text left of the track (4 characters or fewer reads best); '' = none
                     #   kind   'video' (filmstrip clips), 'title' (short text clips) or 'audio' (waveform)
                     #   color  a PALETTE name, or a ('#top', '#bottom') pair
                     #   clips  how many clips (laid out for you from SEED), or a list of (start, end) or
                     #          (start, end, 'name') with start / end from 0 to 1 across the track
                     #   names  optional names for the clips, left to right (the speaker's own words; [] = none)
    dict(label='V2', kind='video', color='teal', clips=4, names=[]),
    dict(label='V1', kind='video', color='violet', clips=4, names=[]),
    dict(label='T1', kind='title', color='amber', clips=5, names=[]),
    dict(label='A1', kind='audio', color='green', clips=2, names=[]),
]
RULER = 'auto'       # timecodes over the tracks. 'auto' = 00:00, 00:01 ... ; a list of up to 8 strings = your own;
                     # None = tick marks only
EDIT = True          # the cursor that trims one clip and drags another before the heat. False = no cursor
DIM = 0.4            # how much the picture darkens while the timeline is up (0 = off, 0.4 = dimmed room, 0.6 = dark).
                     # It eases in from F_IN and is fully back before the slot hands over. Set 0 when the reel's own
                     # look is already dark.
PANEL_W = 848        # width of the timeline on screen, px. 848 centred is the widest that keeps its glow inside the
                     # right-hand button column of the safe zone
PANEL_X = 540        # x of its centre
PANEL_Y = None       # y of its top edge. None = measured: as low as the safe zone allows, under the chin
CAPTION_ROOM = 130   # px kept clear between the chin and the timeline for the reel's own caption line. 0 = keep none
                     # (then hide the reel's captions for this slot)
FACE = None          # (x0, y0, x1, y1) box around the head on the 1080x1920 frame, over the whole effect. None =
                     # measured from the cutout (assets/subject.webm). Type it when the red box in work/layout.jpg is
                     # wrong, or when the slot was made without a cutout
SEED = 7             # changes the clip layout, the cracks and the embers. Any whole number
VOICE = True         # the speaker's audio from the clip. False = silent slot (the reel plays the voice)
SOUNDS = 'auto'      # 'auto' = a soft whoosh as it assembles, a click on each edit, one bass hit on the burn (stock
                     # template sounds). Or your own list of (stock name, frame, volume). [] = none
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
FPS = 30
W, H = 1080, 1920
SAFE_T, SAFE_B, SAFE_L, SAFE_R, SAFE_R_LOW, SAFE_R_Y = 220, 1470, 35, 1045, 980, 1155
CELL = 4
GW, GH = W // CELL, H // CELL
# the timeline is drawn at this size and scaled to PANEL_W
DPW, DPX, DPY, DTX, DTY, DTW, LANE, CLIP_H, GAP = 954, 28, 76, 70, 44, 872, 65, 50, 8
LEAD_DEFAULT, LEAD_MIN, LEAD_EDIT, TAIL = 72, 30, 69, 28     # frames: before the burn (default, least, for the edits), after it
CAP_LINE = 96        # height kept for one caption line of the reel
SFX_GAIN = 0.75
F = lambda fr: fr / FPS - 0.002      # a hair early so a set() can never fire a frame late

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def run(cmd):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        sys.exit('ffmpeg failed:\n' + r.stderr.decode(errors='replace')[-600:])
    return r.stdout


def probe(path, entries):
    return subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries', entries,
                           '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.strip()


# ------------------------------------------------------------------ words
def voice_db():
    """level of the voice per frame, in dB"""
    import numpy as np
    raw = run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'])
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 48000 // FPS
    return np.array([20 * np.log10(np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(len(a) // hop)])


def word_frames(nfr):
    """words.json with the frame each word really starts on: the frame nearest the transcript's guess where the voice
    comes up out of a dip (4 dB or more over the two frames before it). The transcript alone runs 1 to 5 frames off,
    mostly early, so a later rise wins a tie. No rise within reach = the transcript's guess."""
    import numpy as np
    if not os.path.exists('words.json'):
        return []
    words = json.load(open('words.json'))
    db = voice_db()
    if not len(db):
        return [dict(text=w['text'], frame=round(w['start'] * FPS), guess=round(w['start'] * FPS)) for w in words]
    floor, loud = np.percentile(db, 10), np.percentile(db, 90)
    thr = floor + .45 * (loud - floor)
    out = []
    for w in words:
        f = round(w['start'] * FPS)
        best = None
        for n in range(max(2, f - 4), min(len(db), f + 6)):
            if db[n] >= thr and db[n] - min(db[n - 1], db[n - 2]) >= 4 and db[n - 1] <= db[n] - 2:
                score = abs(n - f) - (.5 if n >= f else 0)
                if best is None or score < best[0]:
                    best = (score, n)
        out.append(dict(text=w['text'], frame=min(nfr - 1, best[1] if best else f), guess=f))
    for i in range(1, len(out)):
        out[i]['frame'] = min(nfr - 1, max(out[i]['frame'], out[i - 1]['frame'] + 1))
    return out


def print_level(a, b):
    """the voice level frame by frame, to confirm a word's first frame by eye: python build.py level 80 104"""
    db = voice_db()
    for f in range(max(0, a), min(len(db), b + 1)):
        print(f'{f:5d} {db[f]:6.1f} ' + '#' * max(0, int((db[f] + 60) / 2)))


def norm(s):
    return re.sub(r'[^a-z0-9]+', '', str(s).lower())


def burn_frame(nfr):
    if BURN_AT is None:
        sys.exit('BURN_AT is not set: type the word the timeline burns on (or a frame) in the CLIP block of build.py.\n'
                 'List the words of this slot with:  python build.py words')
    if isinstance(BURN_AT, (int, float)):
        return int(BURN_AT), f'frame {int(BURN_AT)}'
    want, _, nth = str(BURN_AT).partition('#')
    nth = int(nth) if nth.strip().isdigit() else 1
    words = word_frames(nfr)
    hits = [w for w in words if norm(w['text']) == norm(want)]
    if len(hits) < nth:
        said = ' '.join(f"{w['text']}@{w['frame']}" for w in words) or '(no words.json in this slot)'
        sys.exit(f'BURN_AT = {BURN_AT!r}: that word is not said {"that often " if hits else ""}in this slot.\nWords: {said}\n'
                 'Use a word from the list, or a frame number.')
    return hits[nth - 1]['frame'], f'"{hits[nth - 1]["text"]}"'


# ------------------------------------------------------------------ the face (so nothing is ever drawn on it)
def measure_face(nfr, f0, f1):
    """(x0, y0, x1, y1) around the head over frames f0..f1, from the cutout's alpha; plus a note when it is a guess"""
    if FACE:
        return [int(v) for v in FACE], 'typed in the CLIP block'
    if not os.path.exists('assets/subject.webm'):
        sys.exit('There is no cutout in this slot (assets/subject.webm) and FACE is not set. The effect has to know where '
                 'the face is so it never draws on it: re-make the slot with a cutout, or type FACE = (x0, y0, x1, y1).')
    import numpy as np
    from scipy import ndimage
    # -c:v libvpx-vp9 BEFORE -i, or the alpha plane is dropped
    raw = run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', 'assets/subject.webm', '-vf',
               f'alphaextract,scale={GW}:{GH}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'])
    a = np.frombuffer(raw, np.uint8).reshape(-1, GH, GW)
    if len(a) != nfr:
        sys.exit(f'the cutout has {len(a)} frames, the clip has {nfr}: re-make the slot.')
    seg = a[f0:f1 + 1] > 127
    keep = np.zeros_like(seg)
    for i, m in enumerate(seg):            # the biggest shape only: lamps and frames the matte caught are dropped
        lab, n = ndimage.label(m)
        if n:
            keep[i] = lab == 1 + int(np.argmax(ndimage.sum(m, lab, range(1, n + 1))))
    rows = keep.any(axis=2)
    has = rows.any(axis=1)
    if has.mean() < .9:
        sys.exit('The cutout is empty on many frames of this slot. Check assets/subject.webm, or type FACE in the CLIP block.')
    tops = np.array([int(np.argmax(r)) for r in rows[has]])
    top_min, top_hi = int(np.percentile(tops, 1)), int(np.percentile(tops, 98))
    M = keep.mean(axis=0) >= .5            # where the speaker is at least half of the time
    wd = ndimage.uniform_filter1d(M.sum(axis=1).astype(float), 5)
    top = int(np.argmax(M.any(axis=1)))
    note = 'measured from the cutout'
    # the head ends where the outline narrows to the neck; the shoulders start where it widens past the head again
    peak, neck = 0.0, None
    for y in range(top, GH):
        if wd[y] > peak:
            if neck is not None and wd[y] > peak * 1.12:
                break
            if neck is None:
                peak = wd[y]
        elif wd[y] < .88 * peak and y - top > 5 and (neck is None or wd[y] < wd[neck]):
            neck = y
    shoulders = float(wd[top:min(GH, top + int(4 * peak))].max()) if peak else 0
    if neck is None or shoulders < 1.3 * peak:
        # no neck in the outline (a hand at the face, a hood, long hair, a raised knee): take the head from the top of
        # the outline. Its width is the usual width before the outline suddenly widens; a head is about 1.5 widths tall
        m = float(wd[top:top + 8].max())
        for y in range(top + 6, GH):
            m = float(np.median(wd[top + 3:y]))
            if wd[y] > 1.6 * m:
                break
        peak = max(m, 6.0)
        neck = top + int(1.5 * peak)
        note = 'NO NECK FOUND in the outline (hand at the face, hood, long hair, raised knee): the head box is estimated from the top of the outline. Check the red box in work/layout.jpg, type FACE if it is off'
    chin = min(GH - 1, neck + (top_hi - top_min))          # the lowest the chin gets while the head moves
    band = M[top:top + max(3, int(.5 * (neck - top)))]     # the upper half of the head: a hand at the chin stays out of it
    xs = np.where(band.any(axis=0))[0]
    if not len(xs):
        sys.exit('could not find the head in the cutout: type FACE in the CLIP block.')
    cx = (xs[0] + xs[-1] + 1) / 2
    half = min((xs[-1] + 1 - xs[0]) / 2, .75 * peak) * 1.2 + 2      # 20% wider for the head moving
    return [max(0, int((cx - half) * CELL)), top_min * CELL, min(W, int((cx + half) * CELL)), int(chin * CELL)], note


# ------------------------------------------------------------------ the timeline's clips
def hex_rgb(c):
    m = re.fullmatch(r'#([0-9a-fA-F]{6})', str(c).strip())
    if not m:
        sys.exit(f'{c!r}: colours in the STYLE block are written as #RRGGBB')
    v = m.group(1)
    return f'{int(v[0:2], 16)},{int(v[2:4], 16)},{int(v[4:6], 16)}'


def cased(s):
    s = str(s)
    return s.upper() if CASE == 'upper' else s.lower() if CASE == 'lower' else s


def make_clips(rng, notes):
    """every clip as dict(tr, x, w, c, k, name) in design px across the DTW wide track area"""
    if not 2 <= len(TRACKS) <= 6:
        sys.exit(f'TRACKS has {len(TRACKS)} entries: use 2 to 6 tracks.')
    clips, tracks = [], []
    for tr, t in enumerate(TRACKS):
        kind = t.get('kind', 'video')
        if kind not in ('video', 'title', 'audio'):
            sys.exit(f'track {tr + 1}: kind is {kind!r}; use "video", "title" or "audio"')
        col = t.get('color', {'video': 'teal', 'title': 'amber', 'audio': 'green'}[kind])
        if isinstance(col, str):
            if col not in PALETTE:
                sys.exit(f'track {tr + 1}: colour {col!r} is not in PALETTE ({", ".join(PALETTE)})')
            col = PALETTE[col]
        for c in col:
            hex_rgb(c)
        spec = t.get('clips', {'video': 4, 'title': 5, 'audio': 2}[kind])
        names = [str(n) for n in (t.get('names') or [])]
        row = []
        if isinstance(spec, int):
            n = max(1, min(spec, 10))
            if kind == 'title':
                ws = [rng.uniform(84, 132) for _ in range(n)]
                k = min(1.0, DTW * .62 / sum(ws))
                ws = [max(44, w * k) for w in ws]
                spare = DTW - sum(ws)
                gs = [rng.uniform(.3, 1) for _ in range(n + 1)]
                if n > 1:
                    gs[rng.randrange(1, n)] *= 3.2          # one wide gap: room for the cursor to drag a clip into
                gs = [spare * g / sum(gs) for g in gs]
                x = 0.0
                for i, w in enumerate(ws):
                    x += gs[i]
                    row.append((x, w))
                    x += w
            else:
                ws = [rng.uniform(.7, 1.3) if kind == 'video' else rng.uniform(.9, 1.1) for _ in range(n)]
                lead = rng.uniform(0, 24) if kind == 'video' else 0.0
                big, at = (rng.uniform(56, 80), rng.randrange(1, n)) if kind == 'video' and n >= 3 else (0.0, -1)
                total = DTW - lead - GAP * (n - 1) - big
                x = lead
                for i, w in enumerate(ws):
                    if i == at:
                        x += big
                    w = total * w / sum(ws)
                    row.append((x, w))
                    x += w + GAP
        else:
            for item in spec:
                a, b = float(item[0]), float(item[1])
                if not 0 <= a < b <= 1:
                    sys.exit(f'track {tr + 1}: clip {item!r} must be (start, end) with 0 <= start < end <= 1')
                row.append((a * DTW, (b - a) * DTW))
                if len(item) > 2:
                    names += [''] * (len(row) - 1 - len(names)) + [str(item[2])]
            row.sort()
        for i, (x, w) in enumerate(row):
            x, w = round(x), max(40, round(w))
            name = names[i] if i < len(names) else ''
            if name and len(name) * NAME_PX * .62 > w - 24:
                notes.append(f'track {tr + 1}: the name {name!r} does not fit its clip ({w} px) and is left off. Shorten it, lower NAME_PX or make the clip longer')
                name = ''
            clips.append(dict(tr=tr, x=x, w=w, c=list(col), k={'video': 'v', 'title': 't', 'audio': 'a'}[kind],
                              name=html_mod.escape(cased(name))))
        label = cased(t.get('label', ''))
        tracks.append(dict(label=html_mod.escape(label), px=min(LABEL_PX, int(60 / (.62 * max(1, len(label)))))))
        if len(label) > 5:
            notes.append(f'track {tr + 1}: the label {label!r} is long for the 70 px label column and is drawn small. 4 characters or fewer reads best')
    return clips, tracks


def pick_edits(clips):
    """(index of the clip the cursor trims, index it drags): -1 = none. Adds wf / xf (final width / x) to those clips"""
    trim, drag = -1, -1
    by_tr = {}
    for i, c in enumerate(clips):
        by_tr.setdefault(c['tr'], []).append(i)
    cand = [i for i, c in enumerate(clips) if c['k'] == 'v' and c['w'] >= 120 and i != by_tr[c['tr']][-1]] \
        or [i for i, c in enumerate(clips) if c['w'] >= 120]
    if cand:
        trim = min(cand, key=lambda i: abs(clips[i]['x'] + clips[i]['w'] - DTW * .5))
        clips[trim]['wf'] = round(clips[trim]['w'] * .68)
    best = None
    for i, c in enumerate(clips):
        if i == trim:
            continue
        row = by_tr[c['tr']]
        nxt = clips[row[row.index(i) + 1]]['x'] if i != row[-1] else DTW
        gap = nxt - (c['x'] + c['w'])
        if gap >= 70 and c['w'] <= 240:
            score = (0 if c['k'] == 't' else 1, abs(c['x'] - DTW * .3))
            if best is None or score < best[0]:
                best = (score, i, gap)
    if best:
        drag = best[1]
        clips[drag]['xf'] = clips[drag]['x'] + round(min(136, best[2] - 14))
    return trim, drag


# ------------------------------------------------------------------ page
CSS = r'''
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden;background:#000}
#root{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}
.full{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}
#dim{position:absolute;left:0;top:0;width:1080px;height:1920px;opacity:0;
  background:radial-gradient(ellipse 85% 65% at 50% 42%,rgba(9,11,19,.9),rgba(4,5,10,1))}
/* nothing the effect draws can leave this box: it is the safe zone */
#fxclip{position:absolute;left:[[CLIP_L]]px;top:[[CLIP_T]]px;width:[[CLIP_W]]px;height:[[CLIP_H]]px;overflow:hidden;
  font-family:'[[FONT]]',monospace;font-weight:[[WEIGHT]];font-variant-ligatures:none;color:[[TEXT]]}
#base{position:absolute;left:[[BASE_L]]px;top:[[BASE_T]]px;width:1010px;height:[[BH]]px;transform-origin:0 0;transform:scale([[S]])}
#rig,#asm,#fx,#smoke{position:absolute;left:0;top:0;width:1010px;height:[[BH]]px}
#rig{transform-origin:505px [[RIGY]]px}
#pshadow{position:absolute;left:28px;top:76px;width:954px;height:[[PH]]px;border-radius:22px;
  box-shadow:0 12px 22px rgba(0,0,0,.50),0 0 18px rgba(150,180,255,.16)}
#panelbox{position:absolute;left:28px;top:76px;width:954px;height:[[PH]]px}
#whole,#shards{position:absolute;left:0;top:0;width:954px;height:[[PH]]px}
.pbg{position:absolute;left:0;top:0;width:954px;height:[[PH]]px;border-radius:22px;
  background:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,0) 36%),[[PANEL]];
  border:1px solid [[EDGE]];box-shadow:inset 0 1px 0 rgba(255,255,255,.08)}
.heatwash{position:absolute;left:1px;top:1px;width:952px;height:[[PHm2]]px;border-radius:21px;opacity:0;
  background:radial-gradient(ellipse 78% 120% at 100% 50%,rgba(229,72,77,.36),rgba(240,130,50,.13) 50%,rgba(240,130,50,0) 78%)}
.rulerline{position:absolute;left:1px;top:36px;width:952px;height:1px;background:rgba(255,255,255,.08)}
.ruler{position:absolute;left:70px;top:0;width:872px;height:36px}
.ticks{position:absolute;left:0;top:24px;width:872px;height:12px;
  background:linear-gradient(90deg,rgba([[TEXT_RGB]],.62) 0,rgba([[TEXT_RGB]],.62) 2px,transparent 2px) 0 0/110px 12px repeat-x,
             linear-gradient(90deg,rgba([[TEXT_RGB]],.30) 0,rgba([[TEXT_RGB]],.30) 1px,transparent 1px) 0 6px/22px 6px repeat-x}
.tc{position:absolute;top:5px;font-size:13px;line-height:16px;color:rgba([[TEXT_RGB]],.50);white-space:nowrap}
.lane{position:absolute;left:70px;width:872px;height:58px;border-radius:10px;background:rgba(255,255,255,.04);
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.035)}
.lab{position:absolute;left:0;width:70px;height:58px;line-height:58px;text-align:center;white-space:nowrap;
  color:rgba([[TEXT_RGB]],.66)}
.shard{position:absolute;left:0;top:0;width:954px;height:[[PH]]px}
.srim{position:absolute;left:0;top:0;width:954px;height:[[PH]]px;background-color:#FFF3C4}
.sbody{position:absolute;left:0;top:0;width:954px;height:[[PH]]px}
.schar{position:absolute;left:0;top:0;width:954px;height:[[PH]]px;background-color:#0B0909;opacity:0}
#tracks{position:absolute;left:98px;top:120px;width:872px;height:[[TRH]]px}
#clips{position:absolute;left:0;top:0;width:872px;height:[[TRH]]px;z-index:0}
.clip{position:absolute;height:50px;border-radius:9px}
.body{position:absolute;left:0;top:0;width:100%;height:100%;border-radius:9px;overflow:hidden;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.16),inset 0 1px 0 rgba(255,255,255,.22)}
.thumbs{position:absolute;left:0;top:14px;width:100%;height:36px;
  background:repeating-linear-gradient(90deg,rgba(255,255,255,.13) 0,rgba(255,255,255,0) 26px,rgba(0,0,0,.10) 40px,rgba(0,0,0,.34) 40px,rgba(0,0,0,.34) 42px)}
.cbar{position:absolute;left:0;top:0;width:100%;height:14px;background:rgba(0,0,0,.26)}
.cbar i{position:absolute;left:9px;top:5px;height:4px;border-radius:2px;background:rgba(255,255,255,.62)}
.tacc{position:absolute;left:0;top:0;width:5px;height:100%;background:rgba(255,246,214,.75)}
.tl1,.tl2{position:absolute;left:15px;height:5px;border-radius:3px;background:rgba(255,250,235,.80)}
.tl1{top:16px}.tl2{top:29px;background:rgba(255,250,235,.48)}
.wave{position:absolute;left:0;top:0}
.named .thumbs,.named .wave{opacity:.38}
.cname{position:absolute;left:13px;top:0;height:50px;line-height:50px;font-size:[[NAME_PX]]px;white-space:nowrap;
  color:[[TEXT]];text-shadow:0 1px 3px rgba(0,0,0,.45)}
.hot1,.hot2{position:absolute;left:0;top:0;width:100%;height:100%;opacity:0}
.hot1{background:linear-gradient(90deg,rgba(236,160,60,.40),rgba(243,150,48,.96))}
.hot2{background:linear-gradient(90deg,rgba(229,72,77,.55),rgba(255,92,36,1))}
.trimh{position:absolute;right:-2px;top:-3px;width:6px;height:56px;border-radius:3px;background:[[ACCENT]];
  box-shadow:0 0 10px rgba([[ACCENT_RGB]],.8);opacity:0}
.burn{position:absolute;left:0;top:0;width:0;height:50px;opacity:0}
.bglow{position:absolute;left:-96px;top:0;width:96px;height:50px;
  background:linear-gradient(90deg,rgba(255,150,50,0),rgba(255,170,60,.55) 60%,rgba(255,226,140,.95))}
.brim{position:absolute;left:-8px;top:0;width:40px;height:50px;background:linear-gradient(90deg,#FFFBEA,#FFF3C4 8px,#FAE67A 16px,#FF8A2B 30px)}
.bchar{position:absolute;left:0;top:0;height:50px}
#frags{position:absolute;left:0;top:0;width:872px;height:[[TRH]]px}
.frag{position:absolute;height:50px;opacity:0}
.frim{position:absolute;left:0;top:0;width:100%;height:100%;background-color:#FFE08A}
.fchar{position:absolute;left:0;top:0;width:100%;height:100%}
#ph{position:absolute;left:0;top:-38px;width:0;height:[[PHH]]px}
#phl{position:absolute;left:-1.5px;top:12px;width:3px;height:[[PHL]]px;border-radius:2px;background-color:[[TEXT]];
  box-shadow:0 0 10px rgba([[TEXT_RGB]],.55)}
#phh{position:absolute;left:-9px;top:0;width:18px;height:20px;background-color:[[TEXT]];
  clip-path:polygon(0 0,100% 0,100% 58%,50% 100%,0 58%)}
#phg{position:absolute;left:-30px;top:-6px;width:60px;height:[[PHG]]px;opacity:0;
  background:radial-gradient(ellipse 50% 50% at 50% 50%,rgba(255,200,110,.55),rgba(255,120,40,.18) 55%,rgba(255,120,40,0) 100%)}
#cur{position:absolute;left:0;top:0;width:26px;height:30px;opacity:0;transform-origin:2px 2px}
#panelfx{position:absolute;left:28px;top:76px;width:954px;height:[[PH]]px}
#flash{position:absolute;left:0;top:0;width:954px;height:[[PH]]px;border-radius:22px;opacity:0;
  background:linear-gradient(90deg,rgba(255,246,216,0) 30%,rgba(255,246,216,.12) 55%,rgba(255,246,216,.50) 84%,rgba(255,250,232,.96))}
#fstreak{position:absolute;left:-560px;top:[[FSTK]]px;width:600px;height:4px;border-radius:2px;opacity:0;transform-origin:93.3% 50%;
  background:linear-gradient(90deg,rgba(255,246,206,0),rgba(255,236,170,.55) 60%,rgba(255,255,255,1) 93.3%,rgba(255,246,206,0));
  box-shadow:0 0 12px 2px rgba(255,190,90,.35)}
#fclip{position:absolute;left:0;top:0;width:954px;height:[[PH]]px;border-radius:22px;overflow:hidden}
#ftrail{position:absolute;left:0;top:0;width:220px;height:[[PH]]px;opacity:0;
  background:linear-gradient(90deg,rgba(255,243,196,.62),rgba(255,160,60,.22) 40%,rgba(255,120,40,0))}
#fline{position:absolute;left:0;top:-8px;width:0;height:[[FLH]]px;opacity:0}
#fcore{position:absolute;left:-3px;top:0;width:6px;height:[[FLH]]px;border-radius:3px;background:#FFFFFF;
  box-shadow:0 0 14px 5px rgba(255,246,206,.95),0 0 30px 8px rgba(255,150,50,.65)}
#flames{position:absolute;left:0;top:0;width:1010px;height:[[BH]]px}
.flm{position:absolute;opacity:0;transform-origin:50% 92%;
  background:
    radial-gradient(ellipse 13% 44% at 54% 44%,rgba(255,240,190,.80) 0,rgba(255,176,70,.50) 48%,rgba(255,130,40,0) 100%),
    radial-gradient(ellipse 27% 38% at 50% 66%,rgba(255,252,236,.96) 0,rgba(250,230,122,.86) 28%,rgba(255,146,46,.55) 62%,rgba(229,72,45,0) 100%),
    radial-gradient(ellipse 50% 24% at 50% 82%,rgba(255,150,50,.62) 0,rgba(229,72,45,.30) 55%,rgba(229,72,45,0) 100%)}
#firewash{position:absolute;left:0;top:0;width:520px;height:330px;opacity:0;
  background:radial-gradient(ellipse 50% 50% at 50% 50%,rgba(255,170,70,.50),rgba(255,96,36,.22) 50%,rgba(255,96,36,0) 100%)}
.em{position:absolute;border-radius:50%;opacity:0}
.e1{background:radial-gradient(circle,#FFFFFF 0,#FFF3C4 40%,#FAE67A 75%);
  box-shadow:0 0 6px 2px rgba(255,200,90,.95),0 0 16px 5px rgba(255,110,40,.60)}
.e2{background:radial-gradient(circle,#FFF3C4 0,#FAE67A 45%,#FF9A3D 90%);
  box-shadow:0 0 5px 2px rgba(255,150,50,.90),0 0 14px 4px rgba(229,72,45,.55)}
.e3{background:radial-gradient(circle,#FAE67A 0,#FF8A2B 55%,#E5484D 100%);
  box-shadow:0 0 5px 1px rgba(255,110,40,.85),0 0 12px 3px rgba(200,40,30,.50)}
.ash{position:absolute;opacity:0}
.stk{position:absolute;height:2.5px;border-radius:2px;opacity:0;
  background:linear-gradient(90deg,rgba(255,150,50,0),#FAE67A 55%,#FFFFFF);
  box-shadow:0 0 6px 1px rgba(255,170,70,.85)}
.pop{position:absolute;width:26px;height:26px;margin:-13px 0 0 -13px;border-radius:50%;opacity:0;
  background:radial-gradient(circle,#FFFFFF 0,rgba(255,243,196,.95) 22%,rgba(255,150,50,.55) 50%,rgba(255,120,40,0) 72%)}
.smk{position:absolute;border-radius:50%;opacity:0}
'''

BODY = r'''
  <div id="dim"></div>
  <div id="fxclip">
   <div id="base">
    <div id="rig">
      <div id="asm">
        <div id="pshadow"></div>
        <div id="panelbox"><div id="whole"></div><div id="shards"></div></div>
        <div id="tracks">
          <div id="clips"></div>
          <div id="frags"></div>
          <div id="ph"><div id="phg"></div><div id="phl"></div><div id="phh"></div></div>
          <div id="cur"><svg width="26" height="30" viewBox="0 0 26 30"><path d="M2 2 L2 23 L7.6 18.2 L11.4 27 L15.2 25.3 L11.5 16.8 L19 16.6 Z" fill="#F7F4EE" stroke="#0E0F12" stroke-width="1.8" stroke-linejoin="round"/></svg></div>
        </div>
        <div id="panelfx">
          <div id="flash"></div>
          <div id="fclip"><div id="ftrail"></div></div>
          <div id="fline"><div id="fstreak"></div><div id="fcore"></div></div>
        </div>
      </div>
    </div>
    <div id="firewash"></div>
    <div id="flames"></div>
    <div id="smoke"></div>
    <div id="fx"></div>
   </div>
  </div>
'''

JS = r'''
/* timeline burn: assemble, edit, overheat, ignite, crumble. Everything random-looking comes from one seeded generator,
   so every frame is the same on every render. All times hang off two anchors: T0 (assemble) and T_IGN (the word). */
const CFG = /*CFG*/;
const FR = f => f / 30 - 0.002;
function mulberry(seed){ let a = seed >>> 0; return function(){ a |= 0; a = a + 0x6D2B79F5 | 0;
  let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
  return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const R = mulberry(CFG.seed);
const rr = (a, b) => a + (b - a) * R();
const lerp = (a, b, u) => a + (b - a) * u;
const $ = id => document.getElementById(id);

/* geometry (design px; #base is scaled to the screen size) */
const PX = 28, PY = 76, PW = 954, PH = CFG.PH;
const TX = 70, TY = 44, TW = 872;
const OX = PX + TX, OY = PY + TY;
const LANE = 65, CH = 50, NT = CFG.tracks.length, TRH = NT * LANE - 7;

/* time */
const T0 = CFG.t0, T_IGN = CFG.tIgn, IGF = CFG.ignFrame, HK = CFG.hk, T_END = CFG.tEnd;
const A  = t => T0 + t;                          /* assemble / edit clock */
const Hh = t => T_IGN - (2.398 - t) * HK;        /* heat clock: 1.60 .. 2.398 lands on the word */
const P  = t => T_IGN + (t - 2.398);             /* after the word */
const T_B0 = T_IGN + 0.022, B_DUR = 0.27;
const V  = (TW + 80) / B_DUR;
const tf = x => T_B0 + (TW + 40 - x) / V;        /* when the fire front reaches track x */
const T_SWAP = FR(IGF + 1);

/* nothing may rise onto the face: highest allowed y for something spanning xa..xb */
const FACE = CFG.face, AIR = CFG.airTop;
const capY = (xa, xb) => (xb > FACE[0] - 24 && xa < FACE[2] + 24) ? Math.max(AIR, FACE[3] + 14) : AIR;

function chromeHTML(){
  let h = '<div class="pbg"></div><div class="heatwash"></div><div class="rulerline"></div><div class="ruler"><div class="ticks"></div>';
  CFG.ruler.forEach((s, k) => { h += `<span class="tc" style="left:${k * 110 + 6}px">${s}</span>`; });
  h += '</div>';
  CFG.tracks.forEach((t, k) => {
    h += `<div class="lane" style="top:${TY + k * LANE}px"></div><div class="lab" style="top:${TY + k * LANE}px;font-size:${t.px}px">${t.label}</div>`; });
  return h;
}
$('whole').innerHTML = chromeHTML();

/* shards: jittered partition of the panel */
const NC = 7, NR = CFG.NR, SH = [];
(function(){
  const Pt = [];
  for (let r = 0; r <= NR; r++){ Pt.push([]); for (let c = 0; c <= NC; c++){
    let x = PW * c / NC, y = PH * r / NR;
    if (c > 0 && c < NC) x += rr(-30, 30);
    if (r > 0 && r < NR) y += rr(-24, 24);
    Pt[r].push([x, y]); } }
  const HM = [], VM = [];
  for (let r = 0; r <= NR; r++){ HM.push([]); for (let c = 0; c < NC; c++){
    const a = Pt[r][c], b = Pt[r][c + 1];
    HM[r].push([(a[0] + b[0]) / 2 + rr(-10, 10), (a[1] + b[1]) / 2 + ((r > 0 && r < NR) ? rr(-14, 14) : 0)]); } }
  for (let r = 0; r < NR; r++){ VM.push([]); for (let c = 0; c <= NC; c++){
    const a = Pt[r][c], b = Pt[r + 1][c];
    VM[r].push([(a[0] + b[0]) / 2 + ((c > 0 && c < NC) ? rr(-15, 15) : 0), (a[1] + b[1]) / 2 + rr(-8, 8)]); } }
  const arc = (cx, cy, a0) => [0, 1, 2, 3, 4].map(k => { const a = (a0 + k * 22.5) * Math.PI / 180;
    return [cx + 22 * Math.cos(a), cy + 22 * Math.sin(a)]; });
  const corner = (r, c) => {
    if (r === 0 && c === 0) return arc(22, 22, 180);
    if (r === 0 && c === NC) return arc(PW - 22, 22, 270);
    if (r === NR && c === NC) return arc(PW - 22, PH - 22, 0);
    if (r === NR && c === 0) return arc(22, PH - 22, 90);
    return [Pt[r][c]];
  };
  let html = '';
  const chrome = chromeHTML().replace('class="heatwash"', 'class="heatwash" style="opacity:1"');
  for (let r = 0; r < NR; r++) for (let c = 0; c < NC; c++){
    const pts = [].concat(corner(r, c), [HM[r][c]], corner(r, c + 1), [VM[r][c + 1]],
                          corner(r + 1, c + 1), [HM[r + 1][c]], corner(r + 1, c), [VM[r][c]]);
    const cx = (Pt[r][c][0] + Pt[r][c + 1][0] + Pt[r + 1][c + 1][0] + Pt[r + 1][c][0]) / 4;
    const cy = (Pt[r][c][1] + Pt[r][c + 1][1] + Pt[r + 1][c + 1][1] + Pt[r + 1][c][1]) / 4;
    const poly = 'polygon(' + pts.map(p => `${p[0].toFixed(1)}px ${p[1].toFixed(1)}px`).join(',') + ')';
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const xl = Math.min(...xs), xr = Math.max(...xs), yt = Math.min(...ys), yb = Math.max(...ys);
    const i = SH.length;
    SH.push({ i, r, c, cx, cy, xl, xr, w: xr - xl, h: yb - yt });
    const hot = [];
    for (let k = 0; k < 5; k++){ const a = pts[(R() * pts.length) | 0];
      hot.push(`radial-gradient(circle at ${a[0].toFixed(0)}px ${a[1].toFixed(0)}px,rgba(255,246,206,.98),rgba(255,190,80,.55) ${rr(14, 26).toFixed(0)}px,rgba(255,150,50,0) ${rr(36, 64).toFixed(0)}px)`); }
    const spots = [];
    for (let k = 0; k < 5; k++)
      spots.push(`radial-gradient(circle at ${rr(xl + 8, xr - 8).toFixed(0)}px ${rr(yt + 8, yb - 8).toFixed(0)}px,rgba(255,${(96 + rr(0, 70)) | 0},30,${rr(.40, .80).toFixed(2)}),rgba(255,90,30,0) ${rr(5, 12).toFixed(0)}px)`);
    html += `<div class="shard" id="sh${i}"><div class="srim" id="shr${i}" style="clip-path:${poly};background-image:${hot.join(',')}"></div>`
          + `<div class="sbody" id="shb${i}" style="clip-path:${poly}">${chrome}<div class="schar" id="shc${i}" style="background-image:${spots.join(',')}"></div></div></div>`;
  }
  $('shards').innerHTML = html;
})();

/* clips */
const CLIPS = CFG.clips, I_TRIM = CFG.trim, I_DRAG = CFG.drag;
function zig(n, amp){ const z = []; for (let j = 0; j <= n; j++) z.push([rr(0, amp), CH * j / n]); return z; }
function emberSpots(W){
  let g = [];
  const n = Math.max(2, Math.round(W / 34));
  for (let j = 0; j < n; j++)
    g.push(`radial-gradient(circle at ${rr(8, W + 40).toFixed(0)}px ${rr(6, 44).toFixed(0)}px,rgba(255,${(90 + rr(0, 70)) | 0},30,${rr(.45, .85).toFixed(2)}),rgba(255,90,30,0) ${rr(5, 11).toFixed(0)}px)`);
  return g.join(',');
}
(function(){
  let html = '', fhtml = '';
  CLIPS.forEach((c, i) => {
    const W = c.w, Wf = c.wf || c.w, Xf = c.xf != null ? c.xf : c.x, top = c.tr * LANE + 4;
    c.Wf = Wf; c.Xf = Xf; c.top = top;
    let inner = '';
    if (c.k === 'v') inner = `<div class="thumbs"></div><div class="cbar"><i style="width:${Math.min(52, W * 0.3) | 0}px"></i></div>`;
    else if (c.k === 't') inner = '<div class="tacc"></div>' + (c.name ? '' : `<i class="tl1" style="width:${(W * 0.52) | 0}px"></i><i class="tl2" style="width:${(W * 0.34) | 0}px"></i>`);
    else { let d = ''; const n = Math.floor((W - 8) / 4);
      for (let j = 0; j < n; j++){ const a = 2.5 + 19 * Math.abs(Math.sin(j * 0.37) * Math.sin(j * 0.11 + 1.3 + i)) * (0.45 + 0.55 * R());
        const x = 5 + j * 4; d += `M${x} ${(25 - a).toFixed(1)}V${(25 + a).toFixed(1)}`; }
      inner = `<svg class="wave" width="${W}" height="50" viewBox="0 0 ${W} 50"><path d="${d}" stroke="rgba(214,255,244,.66)" stroke-width="2" stroke-linecap="round" fill="none"/></svg>`; }
    if (c.name) inner += `<span class="cname">${c.name}</span>`;
    const z = zig(6, 13);
    const charPoly = 'polygon(' + z.map(p => `${p[0].toFixed(1)}px ${p[1].toFixed(1)}px`).join(',') + `,${Wf + 80}px 50px,${Wf + 80}px 0px)`;
    const rimPoly  = 'polygon(' + z.map(p => `${p[0].toFixed(1)}px ${p[1].toFixed(1)}px`).join(',') + ',40px 50px,40px 0px)';
    const charBg = `${emberSpots(Wf)},linear-gradient(90deg,#FF6A1F 0,#B32A0C 7px,#3A0F08 20px,#110B0A 44px,#0B0909 100%)`;
    html += `<div class="clip" id="c${i}" style="left:${c.x}px;top:${top}px;width:${W}px">`
          + `<div class="body${c.name ? ' named' : ''}" id="cb${i}" style="background:linear-gradient(180deg,${c.c[0]},${c.c[1]})">${inner}`
          + `<div class="hot1" id="h1_${i}"></div><div class="hot2" id="h2_${i}"></div>`
          + `<div class="burn" id="bn${i}"><div class="bglow"></div><div class="brim" style="clip-path:${rimPoly}"></div>`
          + `<div class="bchar" style="width:${Wf + 80}px;clip-path:${charPoly};background:${charBg}"></div></div></div>`
          + (i === I_TRIM ? '<div class="trimh" id="trimh"></div>' : '') + `</div>`;
    const n = Math.max(1, Math.round(Wf / 60));
    const cuts = [];
    for (let j = 0; j <= n; j++){
      const base = Wf * j / n, amp = (j === 0 || j === n) ? 0 : 9;
      cuts.push([0, 13, 25, 38, 50].map(y => [base + (amp ? rr(-amp, amp) : 0), y]));
    }
    c.frags = [];
    for (let j = 0; j < n; j++){
      const L = cuts[j], Rr = cuts[j + 1];
      const x0 = Wf * j / n, x1 = Wf * (j + 1) / n, mid = (x0 + x1) / 2, fw = x1 - x0;
      const topE = [[x0 + fw * rr(.22, .40), rr(1, 7)], [x0 + fw * rr(.58, .78), rr(0, 6)]];
      const botE = [[x0 + fw * rr(.58, .78), rr(43, 50)], [x0 + fw * rr(.22, .40), rr(44, 49)]];
      const pts = L.slice().reverse().concat(topE, Rr, botE);
      const poly = 'polygon(' + pts.map(p => `${p[0].toFixed(1)}px ${p[1].toFixed(1)}px`).join(',') + ')';
      const id = `f${i}_${j}`;
      c.frags.push({ id, x0, x1, mid, fw });
      const hot = [];
      for (let k = 0; k < 3; k++){ const a = pts[(R() * pts.length) | 0];
        hot.push(`radial-gradient(circle at ${a[0].toFixed(0)}px ${a[1].toFixed(0)}px,rgba(255,250,226,.98),rgba(255,200,90,.5) ${rr(8, 14).toFixed(0)}px,rgba(255,150,50,0) ${rr(22, 36).toFixed(0)}px)`); }
      fhtml += `<div class="frag" id="${id}" style="left:${Xf}px;top:${top}px;width:${Wf}px">`
             + `<div class="frim" id="${id}r" style="clip-path:${poly};background-image:${hot.join(',')}"></div>`
             + `<div class="fchar" id="${id}c" style="clip-path:${poly};background:${emberSpots(Wf)},#0C0A0A"></div></div>`;
    }
  });
  $('clips').innerHTML = html;
  $('frags').innerHTML = fhtml;
})();

/* particles (base coordinates) */
const PART = { embers: [], ash: [], streaks: [], sparks: [], pops: [], smoke: [], flames: [] };
(function(){
  let html = '', sm = '';
  const laneY = () => { const k = (R() * NT) | 0; return k * LANE + rr(6, 52); };
  const keepIn = p => { const lo = 44 - p.x, hi = 966 - p.x;
    p.dx = Math.max(lo, Math.min(hi, p.dx)); p.sway = Math.max(lo, Math.min(hi, p.sway)); };
  const span = p => capY(p.x + Math.min(0, p.dx, p.sway) - 14, p.x + Math.max(0, p.dx, p.sway) + 14);
  for (let i = 0; i < 78; i++){
    const u = R();
    const tb = T_B0 - 0.015 + u * (B_DUR + 0.10);
    const fx = TW + 40 - V * Math.max(0, Math.min(B_DUR, tb - T_B0));
    let x = fx + rr(-20, 150);
    if (x < 6 || x > TW - 6) x = x < 6 ? rr(6, 260) : rr(TW - 200, TW - 6);
    const y = laneY();
    const s = rr(3, 8);
    const longLived = i < 9, high = !longLived && i % 3 === 0;
    let dur = longLived ? rr(0.66, 0.92) : (high ? rr(0.44, 0.62) : rr(0.28, 0.48));
    if (!longLived) dur = Math.max(0.24, Math.min(dur, P(rr(3.0, 3.12)) - tb));
    const p = { id: 'em' + i, tb: longLived ? P(rr(2.48, 2.66)) : tb, x: OX + (longLived ? rr(140, 760) : x),
      y: OY + (longLived ? rr(60, TRH - 23) : y), s: longLived ? rr(4, 7) : s, dur,
      rise: longLived ? rr(300, 470) : (high ? rr(380, 560) : rr(120, 320)),
      dx: rr(-30, 70), sway: rr(-28, 28), cls: 'e' + (1 + ((R() * 3) | 0)) };
    keepIn(p);
    p.dur = Math.min(p.dur, T_END - 0.02 - p.tb);
    p.rise = Math.max(20, Math.min(p.rise, p.y - span(p) - 24));
    PART.embers.push(p);
    html += `<i class="em ${p.cls}" id="${p.id}" style="left:${(p.x - p.s / 2).toFixed(1)}px;top:${(p.y - p.s / 2).toFixed(1)}px;width:${p.s.toFixed(1)}px;height:${p.s.toFixed(1)}px"></i>`;
  }
  const ashCol = ['#55535A', '#47454B', '#3B393F', '#5C4E46', '#4A4040'];
  for (let i = 0; i < 44; i++){
    const tb = T_B0 + 0.05 + R() * (B_DUR + 0.14);
    const fx = TW + 40 - V * Math.max(0, Math.min(B_DUR, tb - T_B0 - 0.05));
    let x = fx + rr(-10, 200);
    if (x < 6 || x > TW - 6) x = x < 6 ? rr(6, 300) : rr(TW - 240, TW - 6);
    const w = rr(5, 10), h = rr(2, 4.5);
    const p = { id: 'as' + i, tb, x: OX + x, y: OY + laneY(), w, h, dur: Math.min(rr(0.46, 0.80), T_END - 0.02 - tb), rise: rr(90, 380),
      dx: rr(-30, 60), sway: rr(-34, 34), rot: rr(-260, 260) };
    keepIn(p);
    p.rise = Math.max(20, Math.min(p.rise, p.y - span(p) - 16));
    PART.ash.push(p);
    html += `<i class="ash" id="${p.id}" style="left:${p.x.toFixed(1)}px;top:${p.y.toFixed(1)}px;width:${w.toFixed(1)}px;height:${h.toFixed(1)}px;`
          + `background:${ashCol[(R() * ashCol.length) | 0]};border-radius:${(rr(20, 60)) | 0}% ${(rr(30, 70)) | 0}% ${(rr(20, 60)) | 0}% ${(rr(30, 70)) | 0}%"></i>`;
  }
  for (let i = 0; i < 18; i++){
    const tb = T_IGN + R() * 0.2;
    const fx = TW + 10 - (TW + 30) * Math.pow(Math.max(0, tb - T_IGN) / 0.17, 1.6);
    const x = Math.max(10, Math.min(TW, fx + rr(-10, 40)));
    const ang = rr(-155, -25);
    const len = rr(10, 18);
    let dist = rr(70, 190);
    const cx = Math.cos(ang * Math.PI / 180), sy = Math.sin(ang * Math.PI / 180);
    if (OX + x + cx * dist > 960) dist = Math.max(20, (960 - OX - x) / cx);
    if (OX + x + cx * dist < 50)  dist = Math.max(20, (50 - OX - x) / cx);
    const p = { id: 'sk' + i, tb, x: OX + x, y: OY + laneY(), ang, dist, len, dur: rr(0.16, 0.28) };
    const lim = capY(Math.min(p.x, p.x + cx * dist) - 20, Math.max(p.x, p.x + cx * dist) + 20);
    if (p.y + sy * p.dist < lim + 12) p.dist = Math.max(16, (p.y - lim - 12) / -sy);
    PART.streaks.push(p);
    html += `<i class="stk" id="${p.id}" style="left:${(p.x - len).toFixed(1)}px;top:${p.y.toFixed(1)}px;width:${len.toFixed(1)}px;transform-origin:100% 50%"></i>`;
  }
  /* sparks popping off the hot right side in the last frames before the word */
  const popF = [...new Set([21, 17, 13, 10, 8, 6, 4, 3, 2, 1].map(d => IGF - Math.max(1, Math.round(d * HK))))];
  popF.forEach((f, i) => {
    const t = FR(f);
    const x = OX + rr(520 - i * 6, 862), y = OY + ((R() * NT) | 0) * LANE + rr(2, 10);
    PART.pops.push({ id: 'pp' + i, t, x, y });
    html += `<i class="pop" id="pp${i}" style="left:${x.toFixed(1)}px;top:${y.toFixed(1)}px"></i>`;
    const n = i < 3 ? 2 : 3;
    for (let j = 0; j < n; j++){
      const s = rr(3, 5.5);
      const p = { id: `sp${i}_${j}`, t, x, y, s, dx: rr(-58, 58), sway: 0, up: rr(40, 110), down: rr(20, 60), d1: rr(0.12, 0.18), d2: rr(0.16, 0.24) };
      keepIn(p);
      p.up = Math.max(10, Math.min(p.up, p.y - span(p) - 16));
      PART.sparks.push(p);
      html += `<i class="em e1" id="${p.id}" style="left:${(x - s / 2).toFixed(1)}px;top:${(y - s / 2).toFixed(1)}px;width:${s.toFixed(1)}px;height:${s.toFixed(1)}px"></i>`;
    }
  });
  /* smoke: soft radial blobs (no blur filters) */
  const wisps = [ [800, PY + 42, 1.80], [690, PY + 40, 1.98], [886, PY + 44, 2.12], [760, PY + 42, 2.24] ];
  wisps.forEach((w, i) => {
    const rise = Math.max(20, Math.min(rr(100, 150), w[1] - 84 - capY(w[0] - 40, w[0] + 60)));
    PART.smoke.push({ id: 'sw' + i, kind: 'wisp', x: w[0], y: w[1], t: Hh(w[2]), dx: rr(8, 26), rise });
    sm += `<i class="smk" id="sw${i}" style="left:${w[0] - 15}px;top:${w[1] - 55}px;width:30px;height:110px;`
        + `background:radial-gradient(ellipse 50% 50% at 50% 50%,rgba(214,216,224,.30),rgba(200,204,214,.12) 50%,rgba(200,204,214,0) 100%)"></i>`;
  });
  const puffs = [ [770, PY + PH * .43, 2.47], [520, PY + PH * .385, 2.57], [270, PY + PH * .42, 2.67] ];
  puffs.forEach((w, i) => {
    const rise = Math.max(20, Math.min(rr(120, 170), w[1] - 108 - capY(w[0] - 170, w[0] + 190)));
    PART.smoke.push({ id: 'sp_' + i, kind: 'puff', x: w[0], y: w[1], t: P(w[2]), dx: rr(-14, 30), rise });
    sm += `<i class="smk" id="sp_${i}" style="left:${w[0] - 130}px;top:${(w[1] - 86).toFixed(0)}px;width:260px;height:172px;`
        + `background:radial-gradient(ellipse 50% 50% at 50% 50%,rgba(150,110,92,.50),rgba(96,90,92,.34) 42%,rgba(80,80,86,0) 100%)"></i>`;
  });
  /* flame tongues: born on the fire front, standing on a clip row */
  let fl = '';
  for (let i = 0; i < 30; i++){
    const tb = T_B0 + (i + rr(0, 0.9)) / 30 * B_DUR;
    const fx = TW + 40 - V * (tb - T_B0);
    const big = i % 3 === 1;
    const w = big ? rr(64, 96) : rr(30, 52);
    let h = big ? rr(150, 210) : rr(70, 120);
    const x = Math.max(30, Math.min(TW - 30, fx + rr(-10, 50)));
    const baseY = rr(Math.max(40, h - 60), TRH - 3);
    const lift = rr(14, 40);
    const lim = capY(OX + x - w / 2, OX + x + w / 2);
    h = Math.max(40, Math.min(h, (OY + baseY - lift - lim) / 1.28));
    PART.flames.push({ id: 'fl' + i, tb, d: big ? rr(0.14, 0.20) : rr(0.10, 0.17), lift, sk: rr(-18, 18) });
    fl += `<i class="flm" id="fl${i}" style="left:${(OX + x - w / 2).toFixed(1)}px;top:${(OY + baseY - h).toFixed(1)}px;width:${w.toFixed(1)}px;height:${h.toFixed(1)}px"></i>`;
  }
  $('flames').innerHTML = fl;
  $('fx').innerHTML = html;
  $('smoke').innerHTML = sm;
})();

/* ---------- initial states (outside the timeline) ---------- */
gsap.set('#fxclip', { autoAlpha: 0 });
gsap.set('#asm', { opacity: 0, scale: 0.93, y: 22, transformOrigin: '505px ' + CFG.rigY + 'px' });
gsap.set('#whole .lane', { scaleX: 0, transformOrigin: '0% 50%' });
gsap.set('#whole .lab', { opacity: 0, x: -10 });
gsap.set('#whole .ruler', { clipPath: 'inset(0% 100% 0% 0%)' });
gsap.set('#shards', { opacity: 0 });
CLIPS.forEach((c, i) => {
  gsap.set('#c' + i, { opacity: 0, x: -26, scaleX: 0.7, transformOrigin: '0% 50%' });
  gsap.set('#bn' + i, { x: c.Wf + 14 });
  c.frags.forEach(f => {
    gsap.set('#' + f.id, { transformOrigin: `${f.mid.toFixed(1)}px 25px` });
    gsap.set('#' + f.id + 'c', { transformOrigin: `${f.mid.toFixed(1)}px 25px` });
  });
});
SH.forEach(s => {
  gsap.set('#sh' + s.i, { transformOrigin: `${s.cx.toFixed(1)}px ${s.cy.toFixed(1)}px` });
  gsap.set('#shb' + s.i, { transformOrigin: `${s.cx.toFixed(1)}px ${s.cy.toFixed(1)}px` });
});
gsap.set('#ph', { x: 30, opacity: 0, scaleY: 0, transformOrigin: '50% 0%' });
gsap.set('#cur', { x: 590, y: TRH - 17 });
gsap.set(['#fline', '#ftrail'], { x: TX + 856 });
gsap.set('#firewash', { x: 500, y: PY + PH / 2 - 165 });
PART.streaks.forEach(p => gsap.set('#' + p.id, { rotation: p.ang }));

/* ---------- timeline ---------- */
const tl = gsap.timeline({ paused: true });
tl.set('#fxclip', { autoAlpha: 1 }, FR(CFG.fIn));
tl.set('#fxclip', { autoAlpha: 0 }, FR(CFG.fOut));
if (CFG.dim > 0){
  tl.to('#dim', { opacity: CFG.dim, duration: 0.5, ease: 'power2.out' }, FR(CFG.fIn));
  tl.to('#dim', { opacity: 0, duration: 0.42, ease: 'power2.inOut' }, T_IGN + 0.44);
}

/* assemble */
tl.to('#asm', { opacity: 1, duration: 0.13, ease: 'power2.out' }, A(0.034));
tl.to('#asm', { scale: 1, y: 0, duration: 0.38, ease: 'back.out(1.7)' }, A(0.034));
tl.to('#whole .lane', { scaleX: 1, duration: 0.30, ease: 'power3.out', stagger: 0.03 }, A(0.07));
tl.to('#whole .lab', { opacity: 1, x: 0, duration: 0.20, ease: 'power2.out', stagger: 0.04 }, A(0.12));
tl.to('#whole .ruler', { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.32, ease: 'power2.out' }, A(0.10));
(function(){
  const perTrack = CFG.tracks.map(() => 0);
  CLIPS.forEach((c, i) => {
    const t = A(0.13 + c.tr * 0.02 + perTrack[c.tr] * 0.04); perTrack[c.tr]++;
    tl.to('#c' + i, { opacity: 1, duration: 0.10, ease: 'power1.out' }, t);
    tl.to('#c' + i, { x: 0, scaleX: 1, duration: 0.26, ease: 'back.out(1.9)' }, t);
  });
})();
tl.to('#ph', { opacity: 1, duration: 0.06 }, A(0.24));
tl.to('#ph', { scaleY: 1, duration: 0.18, ease: 'power3.out' }, A(0.24));

/* playhead: scrub, then stutter while it overheats */
tl.to('#ph', { x: 566, duration: Hh(1.60) - A(0.30), ease: 'none' }, A(0.30));
(function(){
  const K = [ [1.60, 566], [1.70, 606], [1.72, 592], [1.80, 592], [1.82, 640], [1.90, 668], [1.92, 652], [1.99, 652],
              [2.01, 704], [2.08, 730], [2.10, 713], [2.15, 713], [2.17, 762], [2.22, 782], [2.24, 768], [2.28, 796],
              [2.30, 786], [2.33, 826], [2.355, 818], [2.385, 856] ];
  for (let j = 1; j < K.length; j++)
    tl.to('#ph', { x: K[j][1], duration: (K[j][0] - K[j - 1][0]) * HK, ease: 'none' }, Hh(K[j - 1][0]));
})();
tl.to('#phl', { backgroundColor: '#FFF3C4', boxShadow: '0 0 16px 3px rgba(255,190,90,.95)', duration: 0.6 * HK, ease: 'power1.in' }, Hh(1.72));
tl.to('#phh', { backgroundColor: CFG.accent, duration: 0.6 * HK, ease: 'power1.in' }, Hh(1.72));
tl.to('#phg', { opacity: 1, duration: 0.6 * HK, ease: 'power2.in' }, Hh(1.76));

/* a human editor, slowly: trim one clip, drag another, then feel the heat and leave */
if (CFG.gag){
  let cx = 590, cy = TRH - 17;
  tl.to('#cur', { opacity: 1, duration: 0.10 }, A(0.46));
  if (I_TRIM >= 0){
    const c = CLIPS[I_TRIM];
    cx = c.x + c.w - 1; cy = c.top + 23;
    tl.to('#cur', { x: cx, y: cy, duration: 0.21, ease: 'power2.inOut' }, A(0.46));
    tl.to('#cur', { scale: 0.86, duration: 0.03 }, A(0.698));
    tl.to('#trimh', { opacity: 1, duration: 0.04 }, A(0.698));
    tl.to('#c' + I_TRIM, { boxShadow: '0 0 0 1.5px rgba(247,244,238,.85)', duration: 0.04 }, A(0.698));
    tl.to('#c' + I_TRIM, { width: c.Wf, duration: 0.27, ease: 'power1.inOut' }, A(0.715));
    cx = c.x + c.Wf - 1; cy += 2;
    tl.to('#cur', { x: cx, y: cy, duration: 0.27, ease: 'power1.inOut' }, A(0.715));
    tl.to('#cur', { scale: 1, duration: 0.04 }, A(0.995));
    tl.to('#trimh', { opacity: 0, duration: 0.08 }, A(0.995));
    tl.to('#c' + I_TRIM, { boxShadow: '0 0 0 0px rgba(247,244,238,0)', duration: 0.10 }, A(0.995));
  }
  if (I_DRAG >= 0){
    const d = CLIPS[I_DRAG], by = d.Xf - d.x;
    cx = d.x + d.w / 2; cy = d.top + 28;
    tl.to('#cur', { x: cx, y: cy, duration: 0.16, ease: 'power2.inOut' }, A(1.02));
    tl.set('#c' + I_DRAG, { transformOrigin: '50% 50%', zIndex: 5 }, A(1.185));
    tl.to('#cur', { scale: 0.86, duration: 0.03 }, A(1.19));
    tl.to('#c' + I_DRAG, { scale: 1.06, y: -4, boxShadow: '0 10px 18px rgba(0,0,0,.55), 0 0 0 1.5px rgba(247,244,238,.9)', duration: 0.07, ease: 'power2.out' }, A(1.19));
    tl.to('#c' + I_DRAG, { x: by, duration: 0.29, ease: 'power2.inOut' }, A(1.225));
    cx += by; cy -= 2;
    tl.to('#cur', { x: cx, y: cy, duration: 0.29, ease: 'power2.inOut' }, A(1.225));
    tl.to('#c' + I_DRAG, { scale: 1, y: 0, boxShadow: '0 0px 0px rgba(0,0,0,0), 0 0 0 0px rgba(247,244,238,0)', duration: 0.10, ease: 'back.out(2.4)' }, A(1.525));
    tl.to('#cur', { scale: 1, duration: 0.04 }, A(1.525));
  }
  const tb = Math.max(Hh(1.58), A(1.58));
  tl.to('#cur', { x: cx + 14, y: cy + 12, duration: 0.10, ease: 'power1.inOut' }, tb);
  tl.to('#cur', { x: cx + 92, y: cy + 108, duration: 0.165, ease: 'power2.in' }, tb + 0.105);
  tl.to('#cur', { opacity: 0, duration: 0.10 }, tb + 0.17);
}

/* overheat */
tl.to('#whole .heatwash', { opacity: 1, duration: 0.74 * HK, ease: 'power1.in' }, Hh(1.62));
tl.to('#pshadow', { boxShadow: '0 12px 22px rgba(0,0,0,.50), 0 0 20px rgba(255,112,44,.44)', duration: 0.7 * HK, ease: 'power1.in' }, Hh(1.66));
CLIPS.forEach((c, i) => {
  const xn = (c.Xf + c.Wf / 2) / TW;
  const t1 = 1.60 + (1 - xn) * 0.36;
  tl.to('#h1_' + i, { opacity: 0.50 + 0.38 * xn, duration: 0.30 * HK, ease: 'power1.inOut' }, Hh(t1));
  const t2 = t1 + 0.20;
  const d2 = Math.max(0.12, 2.37 - t2) * HK;
  tl.to('#h2_' + i, { opacity: 0.16 + 0.80 * xn * xn, duration: d2, ease: 'power1.in' }, Hh(t2));
  tl.to('#c' + i, { boxShadow: `0 0 ${(8 + 14 * xn).toFixed(0)}px rgba(255,${(150 - 60 * xn) | 0},40,${(0.18 + 0.55 * xn).toFixed(2)})`,
    duration: d2, ease: 'power1.in' }, Hh(t2));
});
(function(){                                     /* heat shimmer: per-frame jitter that grows */
  const n = Math.max(4, Math.round(22 * HK));
  for (let k = 1; k <= n; k++){
    const a = Math.pow(k / n, 1.7);
    tl.set('#rig', { skewX: (R() - 0.5) * 1.3 * a, x: (R() - 0.5) * 5.5 * a, y: (R() - 0.5) * 3.2 * a,
      scaleY: 1 + (R() - 0.5) * 0.02 * a }, FR(IGF - n - 1 + k));
  }
})();
PART.pops.forEach(p => {
  tl.set('#' + p.id, { opacity: 1, scale: 0.3 }, p.t);
  tl.to('#' + p.id, { scale: 1.25, duration: 0.07, ease: 'power2.out' }, p.t);
  tl.to('#' + p.id, { opacity: 0, duration: 0.09, ease: 'power1.in' }, p.t + 0.04);
});
PART.sparks.forEach(p => {
  const d = p.d1 + p.d2;
  tl.set('#' + p.id, { opacity: 1 }, p.t);
  tl.to('#' + p.id, { x: p.dx, duration: d, ease: 'none' }, p.t);
  tl.to('#' + p.id, { y: -p.up, duration: p.d1, ease: 'power2.out' }, p.t);
  tl.to('#' + p.id, { y: -p.up + p.down, duration: p.d2, ease: 'power2.in' }, p.t + p.d1);
  tl.to('#' + p.id, { opacity: 0, scale: 0.4, duration: d * 0.5, ease: 'power1.in' }, p.t + d * 0.5);
});
PART.smoke.forEach(s => {
  const id = '#' + s.id;
  if (s.kind === 'wisp'){
    tl.fromTo(id, { opacity: 0, scaleX: 0.6, scaleY: 0.7, y: 0, x: 0 },
      { opacity: 1, duration: 0.16, ease: 'power1.out', immediateRender: false }, s.t);
    tl.to(id, { y: -s.rise, x: s.dx, scaleX: 1.7, scaleY: 1.5, duration: 0.56, ease: 'power1.out' }, s.t);
    tl.to(id, { opacity: 0, duration: 0.30, ease: 'power1.in' }, s.t + 0.26);
  } else {
    tl.fromTo(id, { opacity: 0, scale: 0.55, y: 0, x: 0 },
      { opacity: 0.9, duration: 0.14, ease: 'power1.out', immediateRender: false }, s.t);
    tl.to(id, { y: -s.rise, x: s.dx, scale: 1.25, duration: 0.60, ease: 'power1.out' }, s.t);
    tl.to(id, { opacity: 0, duration: 0.38, ease: 'power1.in' }, s.t + 0.20);
  }
});

/* ignition: on the word */
tl.set('#rig', { skewX: 0, scaleY: 1, x: -4, y: 3 }, T_IGN);
tl.set('#rig', { x: 3, y: -2 }, FR(IGF + 1));
tl.set('#rig', { x: -2, y: 1 }, FR(IGF + 2));
tl.set('#rig', { x: 0, y: 0 }, FR(IGF + 3));
tl.set('#ph', { opacity: 0 }, T_IGN);
tl.set('#flash', { opacity: 1 }, T_IGN);
tl.to('#flash', { opacity: 0, duration: 0.11, ease: 'power2.out' }, T_IGN + 0.004);
tl.set(['#fline', '#ftrail'], { opacity: 1 }, T_IGN);
tl.to(['#fline', '#ftrail'], { x: -30, duration: 0.19, ease: 'power1.in' }, T_IGN);
tl.to(['#fline', '#ftrail'], { opacity: 0, duration: 0.05 }, T_IGN + 0.15);
tl.fromTo('#fstreak', { opacity: 1, scaleX: 0.55 }, { opacity: 0, scaleX: 1, duration: 0.10, ease: 'power2.out', immediateRender: false }, T_IGN);
tl.to('#firewash', { opacity: 1, duration: 0.05 }, T_IGN);
tl.to('#firewash', { x: -10, duration: B_DUR + 0.05, ease: 'none' }, T_B0 - 0.02);
tl.to('#firewash', { opacity: 0, duration: 0.24, ease: 'power1.in' }, T_B0 + B_DUR - 0.06);
PART.flames.forEach(f => {
  const id = '#' + f.id;
  tl.fromTo(id, { opacity: 0, scaleX: 0.5, scaleY: 0.22 },
    { opacity: 1, scaleX: 1, scaleY: 1, duration: 0.07, ease: 'power2.out', immediateRender: false }, f.tb);
  tl.to(id, { scaleY: 1.3, scaleX: 0.55, y: -f.lift, skewX: f.sk, duration: f.d, ease: 'power1.in' }, f.tb + 0.07);
  tl.to(id, { opacity: 0, duration: f.d * 0.7, ease: 'power1.in' }, f.tb + 0.07 + f.d * 0.3);
});
tl.to('#pshadow', { opacity: 0, duration: 0.12 }, T_SWAP);

/* the fire front through every clip, then the pieces fall */
CLIPS.forEach((c, i) => {
  const W = c.Wf, x0 = c.Xf;
  const tA = tf(x0 + W + 14), tB = tf(x0 - 52);
  tl.set('#bn' + i, { opacity: 1 }, tA);
  tl.to('#bn' + i, { x: -52, duration: tB - tA, ease: 'none' }, tA);
  tl.to('#c' + i, { boxShadow: '0 0 0px rgba(255,120,40,0)', duration: 0.04 }, tA);
  const u = NT > 1 ? c.tr / (NT - 1) : 0;
  c.frags.forEach((f, j) => {
    const tr = tf(x0 + f.x0 - 16) + 0.012;
    const id = '#' + f.id;
    tl.set(id, { opacity: 1 }, tr);
    if (j === 0) tl.set('#c' + i, { opacity: 0 }, tr);
    else tl.set('#cb' + i, { clipPath: `inset(0px ${(W - f.x0).toFixed(1)}px 0px 0px)` }, tr);
    tl.to(id + 'c', { scaleX: 1 - 5 / f.fw, scaleY: 0.90, x: rr(-1.8, 1.8), y: rr(-1.6, 1.6), duration: 0.06, ease: 'power2.out' }, tr);
    const fd = rr(0.22, 0.29);
    const fall = rr(lerp(90, 40, u), lerp(150, 64, u));
    const nearL = x0 + f.x0 < 70, nearR = x0 + f.x1 > TW - 70;
    tl.to(id, { y: fall, duration: fd, ease: 'power2.in' }, tr + 0.015);
    tl.to(id, { x: nearL ? rr(8, 34) : (nearR ? rr(-34, -8) : rr(-18, 30)), rotation: rr(-58, 58), scale: rr(0.45, 0.75), duration: fd, ease: 'power1.in' }, tr + 0.015);
    tl.to(id + 'r', { backgroundColor: '#9A2209', duration: fd * 0.7, ease: 'power1.out' }, tr + 0.02);
    tl.to(id, { opacity: 0, duration: fd * 0.66, ease: 'power1.in' }, tr + 0.015 + fd * 0.34);
  });
});

/* the panel cracks and drops */
tl.set('#whole', { opacity: 0 }, T_SWAP);
tl.set('#shards', { opacity: 1 }, T_SWAP);
SH.forEach(s => {
  const tr = Math.max(T_SWAP + 0.06, tf(s.xl - TX) + 0.02) + s.r * 0.012 + rr(0, 0.012);
  const tc = Math.max(T_SWAP, tr - 0.10);
  const b = '#shb' + s.i, w = '#sh' + s.i;
  tl.to(b, { scaleX: 1 - 5.5 / s.w, scaleY: 1 - 5.5 / s.h, x: rr(-1.2, 1.2), y: rr(-1.2, 1.2), duration: 0.07, ease: 'power2.out' }, tc);
  tl.to('#shc' + s.i, { opacity: 1, duration: 0.07, ease: 'none' }, Math.max(T_SWAP, tf(s.xr - TX) - 0.01));
  tl.to('#shr' + s.i, { backgroundColor: '#F0641C', duration: 0.09, ease: 'none' }, tc + 0.04);
  tl.to('#shr' + s.i, { backgroundColor: '#6E1408', duration: 0.14, ease: 'none' }, tc + 0.13);
  const fd = rr(0.21, 0.27);
  const edge = s.c === 0 || s.c === NC - 1;
  const dxs = s.c === 0 ? rr(10, 34) : (s.c === NC - 1 ? rr(-34, -10) : rr(-14, 26));
  const rot = edge ? rr(-9, 9) : rr(-26, 26);
  const u = NR > 1 ? s.r / (NR - 1) : 0;
  tl.to(w, { y: rr(lerp(92, 30, u), lerp(132, 46, u)), duration: fd, ease: 'power2.in' }, tr);
  tl.to(w, { x: dxs, rotation: s.r === NR - 1 ? rot * 0.5 : rot, scale: rr(0.55, 0.78), duration: fd, ease: 'power1.in' }, tr);
  tl.to(w, { opacity: 0, duration: fd * 0.66, ease: 'power1.in' }, tr + fd * 0.34);
});

/* embers, ash, streaks */
PART.embers.forEach(p => {
  const id = '#' + p.id;
  tl.set(id, { opacity: 1 }, p.tb);
  tl.to(id, { y: -p.rise, duration: p.dur, ease: 'power1.out' }, p.tb);
  tl.to(id, { x: p.sway, duration: p.dur * 0.5, ease: 'sine.inOut' }, p.tb);
  tl.to(id, { x: p.dx, duration: p.dur * 0.5, ease: 'sine.inOut' }, p.tb + p.dur * 0.5);
  tl.to(id, { opacity: 0, scale: 0.35, duration: p.dur * 0.55, ease: 'power1.in' }, p.tb + p.dur * 0.45);
});
PART.ash.forEach(p => {
  const id = '#' + p.id;
  tl.set(id, { opacity: 0.9 }, p.tb);
  tl.to(id, { y: -p.rise, rotation: p.rot, duration: p.dur, ease: 'power1.out' }, p.tb);
  tl.to(id, { x: p.sway, duration: p.dur * 0.5, ease: 'sine.inOut' }, p.tb);
  tl.to(id, { x: p.dx, duration: p.dur * 0.5, ease: 'sine.inOut' }, p.tb + p.dur * 0.5);
  tl.to(id, { opacity: 0, duration: p.dur * 0.5, ease: 'power1.in' }, p.tb + p.dur * 0.5);
});
PART.streaks.forEach(p => {
  const id = '#' + p.id, a = p.ang * Math.PI / 180;
  tl.set(id, { opacity: 1 }, p.tb);
  tl.to(id, { x: Math.cos(a) * p.dist, y: Math.sin(a) * p.dist, duration: p.dur, ease: 'power2.out' }, p.tb);
  tl.to(id, { opacity: 0, scaleX: 0.3, duration: p.dur * 0.5, ease: 'power1.in' }, p.tb + p.dur * 0.5);
});

tl.set({}, {}, CFG.dur);
window.__timelines = window.__timelines || {};
window.__timelines["main"] = tl;
'''


def fill(tpl, vals):
    def rep(m):
        if m.group(1) not in vals:
            sys.exit(f'internal: no value for [[{m.group(1)}]]')
        return str(vals[m.group(1)])
    return re.sub(r'\[\[(\w+)\]\]', rep, tpl)


def place(face, ph):
    """where the timeline sits: (scale, top y, caption line y or None, notes)"""
    s = PANEL_W / DPW
    hs = ph * s
    chin = face[3]
    low, pref = SAFE_B - 24 - hs, SAFE_B - 60 - hs          # lowest allowed top, preferred top (room for pieces to fall)
    need_cap = chin + 36 + CAPTION_ROOM + 22
    need_min = chin + 60
    notes, cap = [], None
    if PANEL_Y is not None:
        top = float(PANEL_Y)
        if top < need_min:
            sys.exit(f'PANEL_Y = {PANEL_Y}: the timeline would sit {max(0, chin - top):.0f} px into the face (chin at y {chin}). '
                     f'Use {need_min:.0f} or more, or None.')
        if top > low:
            sys.exit(f'PANEL_Y = {PANEL_Y}: the timeline ({hs:.0f} px tall) would run under y {SAFE_B}. Use {low:.0f} or less, or None.')
    elif CAPTION_ROOM > 0 and pref >= need_cap:
        top = pref
    elif CAPTION_ROOM > 0 and low >= need_cap:
        top = need_cap
    elif low >= need_min:
        top = max(need_min, min(pref, low))
    else:
        sys.exit(f'No room for the timeline: the chin is at y {chin} and a {hs:.0f} px tall timeline has to end above y {SAFE_B}. '
                 'Use a wider shot, fewer TRACKS or a smaller PANEL_W. A tight selfie does not fit this effect.')
    if CAPTION_ROOM > 0 and top - 22 - CAP_LINE >= chin + 30:
        cap = int(min(1376, top - 22 - CAP_LINE))
    x0, x1 = PANEL_X - PANEL_W / 2, PANEL_X + PANEL_W / 2
    glow = 18 * s
    r_lim = SAFE_R_LOW if top + hs + glow > SAFE_R_Y else SAFE_R
    if x0 - glow < SAFE_L or x1 + glow > r_lim:
        sys.exit(f'The timeline (x {x0:.0f}..{x1:.0f} plus {glow:.0f} px of glow) leaves the safe zone (x {SAFE_L}..{r_lim} at this height). '
                 f'Use PANEL_W {int((r_lim - SAFE_L - 2 * glow) // 2 * 2)} or less, centred on x {(SAFE_L + r_lim) // 2}.')
    return s, top, cap, r_lim, notes


def sounds(f_in, f_burn, gag, trim, drag):
    if SOUNDS != 'auto':
        return [(str(n), int(f), float(v)) for n, f, v in (SOUNDS or [])]
    out = [('whoosh-short', f_in + 1, .12)]
    if gag and trim >= 0:
        out.append(('click', f_in + 21, .12))
    if gag and drag >= 0:
        out.append(('click', f_in + 36, .12))
    out.append(('impact-bass-1', f_burn - 1, .30))
    return out


def audio(sfx, dur):
    if os.environ.get('SFX') == '0':
        return []
    out, lanes = [], []
    for k, (name, frame, vol) in enumerate(sorted(sfx, key=lambda x: x[1])):
        path = f'assets/sfx/{name}.mp3'
        if not os.path.exists(path):
            print(f'  (sound {name} is not in assets/sfx: skipped)')
            continue
        t = max(0.0, frame / FPS)
        if t >= dur - .05:
            continue
        d = min(float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                     capture_output=True, text=True).stdout.strip() or 1), dur - t)
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="{path}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{20 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


def layout_picture(L):
    """work/layout.jpg: one frame with the face box (red), the timeline (white), the caption line (yellow), safe zone"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    f = min(L['frames'] - 1, L['f_burn'] - 6)
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-vf', f"select='eq(n,{f})',scale=540:960", '-frames:v', '1',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    if len(raw) != 540 * 960 * 3:
        return
    im = Image.frombytes('RGB', (540, 960), raw)
    d = ImageDraw.Draw(im)
    h = lambda box: [v / 2 for v in box]
    d.rectangle(h([SAFE_L, SAFE_T, SAFE_R, SAFE_B]), outline=(90, 90, 90))
    d.line(h([SAFE_R_LOW, SAFE_R_Y, SAFE_R_LOW, SAFE_B]), fill=(90, 90, 90))
    d.rectangle(h(L['face']), outline=(255, 40, 40), width=2)
    d.rectangle(h(L['panel']), outline=(255, 255, 255), width=2)
    if L['caption_y'] is not None:
        d.rectangle(h([120, L['caption_y'], 960, L['caption_y'] + CAP_LINE]), outline=(250, 230, 122), width=2)
    im.save('work/layout.jpg', quality=88)


def main():
    os.chdir(HERE)
    clip = json.load(open('clip.json'))
    nfr = int(clip['frames'])
    if len(sys.argv) > 1 and sys.argv[1] == 'words':
        ws = word_frames(nfr)
        print(f'{nfr} frames. Word, frame it starts on (transcript guess):')
        for w in ws:
            print(f"  {w['frame']:4d}  {w['text']}" + (f"   ({w['guess']})" if w['guess'] != w['frame'] else ''))
        print('Type the burn word (or its frame) into BURN_AT. It needs 30 or more frames before it and 30 after it in the slot.')
        print('To confirm a frame by eye: python build.py level <first frame> <last frame>  (a word starts where the bars come up out of a dip)')
        return
    if len(sys.argv) > 3 and sys.argv[1] == 'level':
        print_level(int(sys.argv[2]), int(sys.argv[3]))
        return
    dur = nfr / FPS - .001      # 1 ms short on purpose: the renderer rounds the length UP to whole frames
    f_burn, said = burn_frame(nfr)
    f_in = max(2, f_burn - LEAD_DEFAULT) if F_IN is None else int(F_IN)
    f_out = f_burn + TAIL
    if f_in < 1:
        sys.exit('F_IN must be 1 or more: frame 0 of the slot has to be the plain picture.')
    if f_burn - f_in < LEAD_MIN:
        sys.exit(f'The timeline needs {LEAD_MIN} frames or more to assemble and heat up before it burns: F_IN is {f_in}, the burn '
                 f'is on frame {f_burn}. Start the slot earlier (re-make it with an earlier in point) or pick a later word.')
    if f_out > nfr - 2:
        sys.exit(f'The burn ({said if said.startswith("frame") else f"{said}, frame {f_burn}"}) needs {TAIL + 2} more frames of slot after it to crumble and hand back the plain '
                 f'picture; this slot has {nfr - 1 - f_burn}. Re-make the slot at least {f_out + 2 - nfr} frames longer.')
    lead = (f_burn - f_in) / FPS
    hk = max(.3, min(1.0, (lead - .6) / .8))
    notes = []
    rng = random.Random(int(SEED))
    clips, tracks = make_clips(rng, notes)
    gag = bool(EDIT) and f_burn - f_in >= LEAD_EDIT
    trim, drag = pick_edits(clips) if gag else (-1, -1)
    gag = gag and (trim >= 0 or drag >= 0)
    if EDIT and not gag:
        notes.append(f'the cursor edits are left out: they need {LEAD_EDIT} frames before the burn (there are {f_burn - f_in}) and a clip to work on')

    face, face_note = measure_face(nfr, f_in, min(nfr - 1, f_out))
    nt = len(TRACKS)
    ph = DTY + nt * LANE + 8
    s, top, cap_y, r_lim, pnotes = place(face, ph)
    notes += pnotes
    bx, by = PANEL_X - PANEL_W / 2 - DPX * s, top - DPY * s          # #base origin on the canvas
    panel = [round(PANEL_X - PANEL_W / 2), round(top), round(PANEL_X + PANEL_W / 2), round(top + ph * s)]
    if RULER == 'auto':
        ruler = [f'00:0{k}' for k in range(8)]
    else:
        ruler = [html_mod.escape(cased(x)) for x in (RULER or [])][:8]
    dim = 0.0 if os.environ.get('DIM') == '0' else max(0.0, min(.8, float(DIM)))
    cfg = dict(seed=int(SEED) * 7919 + 20261, PH=ph, NR=max(2, round(ph / 104)), rigY=DPY + ph / 2,
               t0=round(f_in / FPS, 4), tIgn=round(F(f_burn), 4), ignFrame=f_burn, hk=round(hk, 4),
               tEnd=round(F(f_out) - .005, 4), fIn=f_in, fOut=f_out, dur=round(dur, 3), dim=dim, accent=ACCENT,
               tracks=tracks, ruler=ruler, clips=clips, trim=trim, drag=drag, gag=gag,
               face=[round((face[0] - bx) / s, 1), round((face[1] - by) / s, 1), round((face[2] - bx) / s, 1), round((face[3] - by) / s, 1)],
               airTop=round((SAFE_T + 14 - by) / s, 1))
    trh = nt * LANE - 7
    vals = dict(CLIP_L=SAFE_L, CLIP_T=SAFE_T, CLIP_W=r_lim - SAFE_L, CLIP_H=SAFE_B - SAFE_T,
                BASE_L=f'{bx - SAFE_L:.2f}', BASE_T=f'{by - SAFE_T:.2f}', S=f'{s:.5f}', BH=ph + 158, RIGY=f'{DPY + ph / 2:.0f}',
                PH=ph, PHm2=ph - 2, TRH=trh, PHH=trh + 44, PHL=trh + 32, PHG=trh + 57, FLH=ph + 16, FSTK=ph // 2 + 6,
                FONT=FONT, WEIGHT=WEIGHT, TEXT=TEXT, TEXT_RGB=hex_rgb(TEXT), ACCENT=ACCENT, ACCENT_RGB=hex_rgb(ACCENT),
                PANEL=PANEL, EDGE=PANEL_EDGE, NAME_PX=NAME_PX)
    sfx = sounds(f_in, f_burn, gag, trim, drag)
    voice = (f'<audio id="voice" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" '
             f'data-track-index="2" data-volume="1"></audio>') if VOICE else ''
    nl = '\n'
    page = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{fill(CSS, vals)}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="{W}" data-height="{H}">
  {voice}
{nl.join(audio(sfx, dur))}
  <video id="aroll" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="0"></video>
{BODY}
{SAFE_GUIDE if os.environ.get('SAFE') == '1' else ''}
</div>
<script>{JS.replace('/*CFG*/', json.dumps(cfg))}</script>
</body>
</html>
'''
    open('index.html', 'w').write(page)
    os.makedirs('work', exist_ok=True)
    L = dict(frames=nfr, f_in=f_in, f_burn=f_burn, f_out=f_out, burn_word=said, face=face, face_note=face_note, panel=panel,
             scale=round(s, 4), caption_y=cap_y, dim=dim, edits=gag, right_limit=r_lim)
    json.dump(L, open('work/layout.json', 'w'), indent=1)
    layout_picture(L)

    print(f'wrote index.html  {nfr} frames ({dur:.3f}s)  timeline in on f{f_in}, burns on f{f_burn} ({said}), plain picture back on f{f_out}')
    print(f'  timeline x {panel[0]}..{panel[2]}  y {panel[1]}..{panel[3]}  ({len(clips)} clips on {nt} tracks, scale {s:.2f})  '
          f'face x {face[0]}..{face[2]} y {face[1]}..{face[3]} ({face_note})  gap chin to timeline {panel[1] - face[3]} px')
    print(f'  cursor edits: {"on" if gag else "off"}   dim: {dim if dim else "off"}   sounds: '
          + ('off (SFX=0)' if os.environ.get('SFX') == '0' else ', '.join(f'{n}@f{f}' for n, f, _ in sfx) or 'none'))
    print('  captions: the effect draws no spoken words (its labels are part of the timeline), so the reel\'s captions stay on.')
    if cap_y is not None:
        print(f'  The timeline sits where chest captions go: add the slot with fx_add.py --caption-y {max(236, cap_y)} '
              f'(the reel\'s captions move to the line above the timeline, y {cap_y}..{cap_y + CAP_LINE}). Check one reel snapshot inside the slot.')
    else:
        print(f'  !! No room for a caption line between the chin (y {face[3]}) and the timeline (y {panel[1]}): add the slot with '
              f'fx_add.py --captions hide (no captions for frames {f_in}..{f_out}), or make room with a smaller PANEL_W / fewer TRACKS.')
    for n in notes:
        print('  !! ' + n)
    if 'NO NECK' in face_note:
        print('  !! ' + face_note)
    snaps = sorted({f_in + 6, f_in + 30, (f_in + f_burn) // 2 + 8, f_burn - 4, f_burn, f_burn + 3, f_burn + 8, f_burn + 16})
    print('look at work/layout.jpg (red = face, white = timeline, yellow = caption line)')
    print('snapshot times: ' + ','.join(f'{(n + .5) / FPS:.3f}' for n in snaps if 0 <= n < nfr))
    print(f'render to renders/{os.path.basename(HERE)}.mp4')


if __name__ == '__main__':
    main()
