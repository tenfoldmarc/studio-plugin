#!/usr/bin/env python3
"""Where is the speaker, and where can captions go? -> <project>/layout.json  (and a picture to check it by eye)

Usage:  PY layout.py <project_dir> [--fps 2] [--quick]

Works on any clip, nothing is typed in per clip:
  1. Takes about 2 frames per second of assets/aroll.mp4 (90 frames at most) and gets a person cutout of JUST those
     frames (a few seconds, not the minutes a full cutout takes). If assets/subject.webm (a full cutout) is already
     there it reads that instead. When the clean cutout is installed (setup.py --matting) the sample frames are cut
     out with it (40 frames at most, about a minute): it is not fooled by a picture or poster behind the head.
     --quick forces the quick cutout.
  2. In every sampled frame it keeps the biggest blob only (a face in a painting or poster is a separate, smaller
     blob and is ignored), and reads the head off the silhouette: head top, head width, chin, centre, body sides.
  3. Works out the three caption bands from that: above the head, over the chest, lower third, plus the open wall
     beside the speaker, each with a fallback when there is no room.
  4. Writes layout.json and work/layout/check.jpg: sampled frames with the face box (green), the bands (blue) and the
     Reels safe zone (red) drawn on. LOOK at check.jpg once. If the green box is not on the face, fix "head" and
     "bands" in layout.json by hand (plain numbers, 1080x1920) or make a clean cutout (rvm_cut.py) and run this again.

layout.json:
  head      top / chin / cx / width / left / right of the head in the footage (medians; top_min and chin_max = extremes)
  bands     HEAD_TOP, Y_ABOVE_HEAD (null = no room), Y_CHEST, Y_LOWER, WALL_LEFT / WALL_RIGHT ([x, y, width] or null).
            These are what the caption engine reads. They are screen positions AFTER any lift.
  fits      which placements have room: above_head, behind_head, chest ("yes" / "tight"), lower, wall_left, wall_right
  lift      close-up fallback: pixels the picture is lifted so captions get the collar band under the chin (0 = none)
  shot      wide / medium / close   (from the head width; a first guess, used by the effect footage check)
  camera    how much the background moves between samples, and still / drifting / moving (a first guess)
  segments  head top / chin / centre per segment of the cut (punch-ins move the head)
  faceless  true when nobody is on camera (voice over b-roll)
"""
import json
import os
import statistics
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

FF, FP = skillenv.tool('ffmpeg'), skillenv.tool('ffprobe')
SW, SH, S = 270, 480, 4                      # analysis size and its scale to the 1080x1920 frame
SAFE_TOP, SAFE_BOTTOM = 220, 1470


def duration(f):
    return float(subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=duration', '-of',
                                 'csv=p=0', f], **skillenv.TEXT).stdout.strip().split(',')[0])


def main_blob(im):
    """the biggest connected blob of the matte -> {y: (left, right)} in analysis pixels, and its area"""
    w, h = im.size
    data = im.point(lambda v: 255 if v > 128 else 0).tobytes()
    seen, best = bytearray(w * h), []
    for i in range(w * h):
        if data[i] and not seen[i]:
            stack, comp = [i], []
            seen[i] = 1
            while stack:
                j = stack.pop()
                comp.append(j)
                x = j % w
                for k in (j - w, j + w, j - 1 if x else -1, j + 1 if x < w - 1 else -1):
                    if 0 <= k < w * h and data[k] and not seen[k]:
                        seen[k] = 1
                        stack.append(k)
            if len(comp) > len(best):
                best = comp
    rows = {}
    for j in best:
        y, x = divmod(j, w)
        lo, hi = rows.get(y, (x, x))
        rows[y] = (min(lo, x), max(hi, x))
    return rows, len(best)


def read_head(rows):
    """head top, width, chin, centre and body sides from one silhouette (analysis pixels), or None"""
    if not rows:
        return None
    top, bottom = min(rows), max(rows)

    def width(y):
        return rows[y][1] - rows[y][0] + 1 if y in rows else 0
    # head width: going down from the top, the first depth d where the silhouette is no wider than 2d. On a round
    # head that is exactly its widest row, and it does not need a visible neck (long hair, hoods, beards).
    d = 3
    while top + d < bottom and width(top + d) > 2 * d:
        d += 1
    hw = max(2 * d, 8)
    if top + d >= bottom and width(top + d) > 2 * d:
        hw = width(min(top + SH // 6, bottom))              # the head leaves the frame: take what is there
    # chin: just above the narrowest row (the neck) between 0.9 and 1.7 head widths down; else by proportion
    lo, hi = top + int(.9 * hw), min(top + int(1.7 * hw), bottom)
    chin = top + int(1.35 * hw)
    has_neck = False                                        # no neck under the head = the chin is a guess by proportion
    if hi > lo:
        neck = min(range(lo, hi + 1), key=width)
        if width(neck) < .9 * hw:
            chin = neck - int(.08 * hw)
            has_neck = True
    chin = int(min(max(chin, top + 1.05 * hw), top + 1.75 * hw, SH - 1))
    face = [rows[y] for y in range(top + int(.3 * hw), min(top + int(.8 * hw), bottom) + 1) if y in rows]
    if not face:
        return None
    left, right = min(r[0] for r in face), max(r[1] for r in face)
    # how far the speaker reaches sideways at face height (for the open wall beside them). The band scales with the
    # head: from just under the brow to a little past the chin (0.47 to 1.1 head heights below the top). On a head
    # of 300 px that is the 140 to 330 px it always was; a fixed 330 px ran into the shoulders on a wide shot,
    # where the head is small, and reported open wall as closed.
    hh = max(chin - top, 8)
    side = [rows[y] for y in range(top + int(.47 * hh), min(top + int(1.1 * hh), bottom) + 1) if y in rows] or face
    return dict(top=top * S, width=(right - left + 1) * S, chin=chin * S, cx=(left + right) * S // 2, left=left * S,
                right=right * S, side_left=min(r[0] for r in side) * S, side_right=max(r[1] for r in side) * S,
                neck=has_neck)


def clean_cutout_ready():
    """True when the clean cutout (setup.py --matting) is installed: then the sample frames are cut out with it.
    It is not fooled by a picture, poster or mirror behind the head the way the quick cutout can be."""
    import importlib.util
    try:
        if not os.path.isfile(os.path.join(skillenv.models_dir(), 'rvm_resnet50_fp32.onnx')):
            return False
        return all(importlib.util.find_spec(m) for m in ('numpy', 'onnxruntime', 'scipy'))
    except (ImportError, ValueError, OSError):
        return False


def pct(values, p):
    v = sorted(values)
    return v[min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))]


def bands_from(head):
    """the caption bands for a head (footage coordinates) -> (bands, fits, lift, notes). Screen coordinates."""
    notes = []
    chin_max, top_med, top_min = head['chin_max'], head['top'], head['top_min']
    # chest band: a caption block starts up to 76px above Y_CHEST and has to clear the chin by 24px
    lift = int(min(max(chin_max + 100 - 1170, 0), 260))
    chin, top, tmin = chin_max - lift, top_med - lift, top_min - lift
    if chin + 100 <= 1170:
        y_chest, chest = 1170, 'yes'
    else:
        y_chest, chest = max(chin - 20, 1215), 'tight'
        notes.append('The face fills the frame. Captions only have the collar band under the chin: use a caption '
                     'style that shows one line at a time (Vanity, Keyword, Golden Hour, Karaoke, Arcade).')
    if lift:
        notes.append(f'Close-up: the picture is lifted {lift}px so captions get room under the chin. The strip that '
                     'opens at the bottom is filled with the colour of the frame edge and sits under the Instagram caption.')
    above = tmin - 104 >= 236
    behind = (top - 226) / .6084 >= 110
    if not above:
        notes.append('No room above the head: Bubblegum puts its word over the chest instead.')
    if not behind:
        notes.append('No room above the head for words behind it: Bold lands its big words over the chest instead.')
    lw = head['side_left'] - 36 - 70
    rx = head['side_right'] + 36
    rw = 1010 - rx
    wall_left = [70, max(236, top + 138), int(min(lw, 340))] if lw >= 240 else None
    wall_right = [int(rx), max(236, top + 182), int(min(rw, 300))] if rw >= 240 else None
    if not (wall_left and wall_right):
        notes.append('Open wall beside the speaker: ' + ('left only' if wall_left else 'right only' if wall_right else 'none')
                     + '. Field Notes uses the spots that exist and the chest band for the rest.')
    bands = dict(HEAD_TOP=int(top), Y_ABOVE_HEAD=int(tmin - 104) if above else None, Y_CHEST=int(y_chest), Y_LOWER=1376,
                 WALL_LEFT=wall_left, WALL_RIGHT=wall_right)
    fits = dict(above_head=above, behind_head=behind, chest=chest, lower=chin + 30 <= 1376,
                wall_left=bool(wall_left), wall_right=bool(wall_right))
    return bands, fits, lift, notes


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    aroll = os.path.join(proj, 'assets', 'aroll.mp4')
    subject = os.path.join(proj, 'assets', 'subject.webm')
    if not os.path.isfile(aroll):
        sys.exit(f'{aroll} not found: run assemble.py first.')
    work = os.path.join(proj, 'work', 'layout')
    os.makedirs(work, exist_ok=True)
    for n in os.listdir(work):                       # our own stale samples from an earlier run of this script
        if n[:2] in ('a_', 'f_') and n.endswith('.png'):
            os.replace(os.path.join(work, n), os.path.join(work, 'old_' + n))
    dur = duration(aroll)
    fps = 2.0
    if '--fps' in sys.argv:
        fps = float(sys.argv[sys.argv.index('--fps') + 1])
    fps = min(fps, 90 / max(dur, 1))
    clean = not os.path.isfile(subject) and '--quick' not in sys.argv and clean_cutout_ready()
    if clean:
        fps = min(fps, 40 / max(dur, 1))             # the clean cutout takes about 1.2s a frame: 40 samples at most
    quiet = [FF, '-loglevel', 'error', '-y']
    subprocess.run(quiet + ['-i', aroll, '-vf', f'fps={fps:.4f},scale={SW}:{SH}', os.path.join(work, 'f_%03d.png')], check=True)
    if os.path.isfile(subject):
        source = 'cutout'
        subprocess.run(quiet + ['-c:v', 'libvpx-vp9', '-i', subject, '-vf', f'fps={fps:.4f},alphaextract,scale={SW}:{SH}',
                                os.path.join(work, 'a_%03d.png')], check=True)
    else:
        source = 'probe'
        subprocess.run(quiet + ['-i', aroll, '-an', '-vf', f'fps={fps:.4f},setpts=N/30/TB', '-r', '30', '-c:v', 'libx264',
                                '-crf', '16', '-pix_fmt', 'yuv420p', os.path.join(work, 'probe.mp4')], check=True)
        probe_webm = os.path.join(work, 'probe.webm')
        if os.path.isfile(probe_webm):
            os.replace(probe_webm, os.path.join(work, 'old_probe.webm'))
        if clean:                                    # the clean cutout is installed: use it for the sample frames
            samples = max(1, int(dur * fps))
            print(f'measuring with the clean cutout: about {samples} sample frames, roughly {max(20, int(samples * 1.5 + 20))} seconds',
                  flush=True)
            r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rvm_cut.py'), proj,
                                '--src', 'work/layout/probe.mp4', '--out', 'work/layout/probe.webm'], **skillenv.TEXT)
            if r.returncode == 0 and os.path.isfile(probe_webm):
                source = 'clean probe'
            else:
                print('note: the clean cutout did not run on the sample frames, using the quick one instead')
        if source == 'probe':
            argv, env = skillenv.hyperframes_command(['remove-background', 'work/layout/probe.mp4', '-o', 'work/layout/probe.webm'])
            r = subprocess.run(argv, cwd=proj, env=env, **skillenv.TEXT)
            if r.returncode != 0 or not os.path.isfile(probe_webm):
                print((r.stdout or '')[-1500:] + (r.stderr or '')[-1500:])
                sys.exit('The quick cutout of the sample frames failed (output above). Run setup.py, then try again.')
        subprocess.run(quiet + ['-c:v', 'libvpx-vp9', '-i', os.path.join(work, 'probe.webm'), '-vf',
                                f'alphaextract,scale={SW}:{SH}', os.path.join(work, 'a_%03d.png')], check=True)
    alphas = sorted(n for n in os.listdir(work) if n.startswith('a_') and n.endswith('.png'))
    frames = sorted(n for n in os.listdir(work) if n.startswith('f_') and n.endswith('.png'))
    n = min(len(alphas), len(frames))
    if not n:
        sys.exit('No sample frames came out of the clip.')

    try:
        with open(os.path.join(proj, 'segments.json'), encoding='utf-8') as fh:
            segs = [dict(id=s['id'], t0=s['frame'] / 30, t1=(s['frame'] + s['frames']) / 30) for s in json.load(fh)]
    except (OSError, ValueError, KeyError):
        segs = [dict(id='all', t0=0.0, t1=dur)]

    heads, masks = [], []
    for k in range(n):
        rows, area = main_blob(Image.open(os.path.join(work, alphas[k])).convert('L'))
        h = read_head(rows) if area >= .03 * SW * SH else None
        if h and h['width'] < 60:
            h = None
        heads.append(h)
        m = Image.new('L', (SW, SH), 0)
        px = m.load()
        for y, (lo, hi) in rows.items():
            for x in range(lo, hi + 1):
                px[x, y] = 255
        masks.append(m)
    found = [h for h in heads if h]
    faceless = len(found) < .4 * n

    def seg_of(k):
        t = k / fps
        return next((i for i, s in enumerate(segs) if s['t0'] - .01 <= t < s['t1']), len(segs) - 1)

    # how much the room moves between samples (the speaker is masked out). A first guess, not a tracker.
    moves = []
    for k in range(n - 1):
        if seg_of(k) != seg_of(k + 1):
            continue
        a = Image.open(os.path.join(work, frames[k])).convert('L')
        b = Image.open(os.path.join(work, frames[k + 1])).convert('L')
        keep = ImageChops.invert(ImageChops.lighter(masks[k], masks[k + 1]).filter(ImageFilter.MaxFilter(9)))
        if ImageStat.Stat(keep).sum[0] > 255 * .1 * SW * SH:
            moves.append(ImageStat.Stat(ImageChops.difference(a, b), mask=keep).mean[0])
    motion = round(statistics.median(moves), 2) if moves else None
    verdict = 'unknown' if motion is None else 'still' if motion < 3 else 'drifting' if motion < 8 else 'moving'

    edge = Image.open(os.path.join(work, frames[0])).convert('RGB').crop((0, SH - 8, SW, SH))
    fill = '#%02x%02x%02x' % tuple(int(v) for v in ImageStat.Stat(edge).mean)

    out = dict(version=1, source=source, frames=n, fps=round(fps, 3), faceless=faceless, fill=fill,
               camera=dict(motion=motion, verdict=verdict))
    if faceless:
        out.update(head=None, shot='none', lift=0, segments=[],
                   bands=dict(HEAD_TOP=452, Y_ABOVE_HEAD=344, Y_CHEST=1170, Y_LOWER=1376,
                              WALL_LEFT=[70, 596, 300], WALL_RIGHT=[740, 640, 280]),
                   fits=dict(above_head=True, behind_head=False, chest='yes', lower=True, wall_left=True, wall_right=True),
                   notes=['Nobody on camera in most of the reel: captions use the standard bands. Styles that go behind '
                          'the speaker or pop the speaker out of a card cannot be used.'])
    else:
        med = lambda key: int(statistics.median(h[key] for h in found))      # noqa: E731
        head = dict(top=med('top'), top_min=pct([h['top'] for h in found], .1), chin=med('chin'),
                    chin_max=pct([h['chin'] for h in found], .9), cx=med('cx'), width=med('width'), left=med('left'),
                    right=med('right'), side_left=pct([h['side_left'] for h in found], .1),
                    side_right=pct([h['side_right'] for h in found], .9))
        bands, fits, lift, notes = bands_from(head)
        # cheap sanity check on the head box. No neck under the head in most samples means the chin was placed by
        # proportion: normal with long hair, a hood or a scarf, but also what happens when a picture frame, poster or
        # lamp right behind the head joins the outline and the box starts too high.
        # A second sign, on a still camera: a speaker's head moves a little from sample to sample (talking, nodding).
        # When the top third of the head box hardly changes while the rest of it does, the top of the box is not the
        # head: it is something that hangs behind it.
        guessed = sum(1 for h in found if not h.get('neck'))
        why = []
        if guessed >= .5 * len(found):
            why.append(f'in {guessed} of {len(found)} sample frames no neck was found under the head (normal with long '
                       'hair or a hood)')
        if verdict == 'still':
            bl, br, bt, bc = head['left'] // S, head['right'] // S, head['top'] // S, head['chin'] // S
            tops, lows = [], []
            for k in range(n - 1):
                if seg_of(k) != seg_of(k + 1) or bc - bt < 12 or br - bl < 8:
                    continue
                diff = ImageChops.difference(Image.open(os.path.join(work, frames[k])).convert('L'),
                                             Image.open(os.path.join(work, frames[k + 1])).convert('L'))
                tops.append(ImageStat.Stat(diff.crop((bl, bt, br, bt + int(.3 * (bc - bt))))).mean[0])
                lows.append(ImageStat.Stat(diff.crop((bl, bt + int(.45 * (bc - bt)), br, bc))).mean[0])
            if len(tops) >= 3 and statistics.median(lows) >= 3 and statistics.median(tops) < .3 * statistics.median(lows):
                why.append('the top third of the box does not move while the face under it does, so the box probably '
                           'starts above the head')
        if source != 'cutout' and why:
            unsure = ('CHECK THE HEAD BOX: ' + '; and '.join(why) + '. Something right behind the head (a framed picture, '
                      'a poster, a lamp) can join the outline. In check.jpg the green box must run from the top of the '
                      'head to the chin. If it does not, correct "head" and "bands" in layout.json'
                      + ('.' if source == 'clean probe' else ', or run setup.py --matting once and this script again.'))
            notes.insert(0, unsure)
        ratio = head['width'] / 1080
        per = []
        for i, s in enumerate(segs):
            hs = [h for k, h in enumerate(heads) if h and seg_of(k) == i]
            per.append(dict(id=s['id'], t0=round(s['t0'], 3), t1=round(s['t1'], 3),
                            head_top=int(statistics.median(h['top'] for h in hs)) if hs else None,
                            chin=int(statistics.median(h['chin'] for h in hs)) if hs else None,
                            cx=int(statistics.median(h['cx'] for h in hs)) if hs else None))
        tops = [p['head_top'] for p in per if p['head_top'] is not None]
        if tops and max(tops) - min(tops) > 120:
            notes.append('The head sits at very different heights across the cuts (punch-ins). The bands are the ones '
                         'that are safe in every segment; check the tightest segment in the frames.')
        out.update(head=head, shot='wide' if ratio < .24 else 'medium' if ratio < .42 else 'close', lift=lift,
                   bands=bands, fits=fits, segments=per, notes=notes)
    with open(os.path.join(proj, 'layout.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1)
        fh.write('\n')

    # the picture to check it by eye: up to 4 samples at half size (big enough to see whether the box ends on the
    # chin), face box green, bands blue, safe zone red
    picks = sorted(set(round(i * (n - 1) / 3) for i in range(4))) if n > 4 else list(range(n))
    C = 2                                            # check tiles are 540x960: frame pixels / 2
    TW, TH = 1080 // C, 1920 // C
    sheet = Image.new('RGB', (TW * len(picks), TH), '#000')
    lift = out['lift']
    for col, k in enumerate(picks):
        big = os.path.join(work, f'c_{col}.png')
        r = subprocess.run(quiet + ['-ss', f'{k / fps:.3f}', '-i', aroll, '-frames:v', '1', '-vf', f'scale={TW}:{TH}', big])
        if r.returncode == 0 and os.path.isfile(big):
            im = Image.open(big).convert('RGB')
        else:                                        # could not seek there: enlarge the analysis frame instead
            im = Image.open(os.path.join(work, frames[k])).convert('RGB').resize((TW, TH))
        d = ImageDraw.Draw(im)
        d.rectangle([35 // C, SAFE_TOP // C, (1080 - 35) // C, SAFE_BOTTOM // C], outline='#ff3030', width=2)
        d.line([(1080 - 100) // C, 1155 // C, (1080 - 100) // C, SAFE_BOTTOM // C], fill='#ff3030', width=2)
        if heads[k]:
            h = heads[k]
            d.rectangle([h['left'] // C, h['top'] // C, h['right'] // C, h['chin'] // C], outline='#30ff60', width=3)
            d.text((h['left'] // C + 4, h['chin'] // C + 4), f"top {h['top']}  chin {h['chin']}", fill='#30ff60')
        for name in ('Y_ABOVE_HEAD', 'Y_CHEST', 'Y_LOWER'):
            y = out['bands'].get(name)
            if y is not None:
                d.line([40 // C, (y + lift) // C, 1040 // C, (y + lift) // C], fill='#40a0ff', width=2)
                d.text((44 // C, (y + lift) // C + 3), name, fill='#40a0ff')
        for name in ('WALL_LEFT', 'WALL_RIGHT'):
            wall = out['bands'].get(name)
            if wall:
                d.rectangle([wall[0] // C, (wall[1] + lift) // C, (wall[0] + wall[2]) // C, (wall[1] + lift + 180) // C],
                            outline='#ffd040', width=2)
        sheet.paste(im, (col * TW, 0))
    check = os.path.join(work, 'check.jpg')
    sheet.save(check, quality=88)

    print(f'layout.json written ({source}, {n} frames sampled)')
    if faceless:
        print('nobody on camera')
    else:
        h = out['head']
        print(f"head top {h['top']} (highest {h['top_min']})  chin {h['chin']} (lowest {h['chin_max']})  centre x {h['cx']}  "
              f"width {h['width']}  -> {out['shot']} shot")
    print('bands  ' + '  '.join(f'{k}={v}' for k, v in out['bands'].items()))
    print('fits   ' + '  '.join(f'{k}={v}' for k, v in out['fits'].items()) + f'  lift={out["lift"]}')
    print(f'camera {verdict} (background change {motion})')
    for note in out['notes']:
        print('NOTE   ' + note)
    print(f'look at {check}: the green box must run from the top of the head to the chin (not start above the head, '
          'not stop at the nose), blue lines = caption bands, red = Reels safe zone')


if __name__ == '__main__':
    main()
