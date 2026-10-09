#!/usr/bin/env python3
"""The self-check after a render: pull a few frames out of the FINAL mp4, draw the Reels safe zone and the face box
on them, and measure what can be measured. One picture to look at instead of opening the video.

Usage:  PY frames_check.py <project_dir> <render.mp4> [--at 1.2,3.4,5.6] [--n 6]

  --at   the moments to check (seconds). Default: the middle of --n words spread across the reel, so a caption is
         on screen in every frame. Add the moments of every effect slot and every title yourself.

<render.mp4> may be written the short way, "renders/<file>.mp4": it is looked up inside the project folder.

Writes work/check/<render name>.jpg  (six frames a row: red = Reels safe zone, green = the face).
What to confirm in the picture, every time:
  1. nothing covers the face (eyes to chin)          3. text is readable against what is behind it
  2. nothing sits in the red area                     4. a cutout, if used, has a clean edge (no halo, no missing hand)
Fix what fails, or drop that element and say why. Only frames from the final render count as proof.

It also prints two numbers per frame when the footage itself was left untouched (a caption style with no overall
style): how much of the unsafe area and of the face box changed compared with the raw cut. Captions are high
contrast, so anything above about 1.5% means something is drawn there: look at that frame. Frames inside an effect
slot get no numbers (the effect moves or regrades the picture on purpose): those are judged by eye.
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

FF = skillenv.tool('ffmpeg')
FW, FH, S = 360, 640, 3          # size of each frame in the sheet, and its scale to 1080x1920


def read(path, fallback):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def grab(video, t, out):
    subprocess.run([FF, '-loglevel', 'error', '-y', '-ss', f'{max(t, 0):.3f}', '-i', video, '-frames:v', '1', '-vf',
                    f'scale={FW}:{FH}', out], check=True)
    return Image.open(out).convert('RGB')


def changed(a, b, box):
    """share of the pixels in box (frame pixels) that differ strongly between two frames"""
    x0, y0, x1, y1 = [int(v / S) for v in box]
    if x1 <= x0 or y1 <= y0:
        return 0.0
    d = ImageChops.difference(a.convert('L').crop((x0, y0, x1, y1)), b.convert('L').crop((x0, y0, x1, y1)))
    hist = d.histogram()
    return sum(hist[60:]) / max(1, sum(hist))


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    render = skillenv.project_file(proj, sys.argv[2])       # "renders/x.mp4" is read inside the project
    if not os.path.isfile(render):
        sys.exit(f'render not found: {render}')
    words = read(os.path.join(proj, 'words.json'), [])
    layout = read(os.path.join(proj, 'layout.json'), {})
    built = read(os.path.join(proj, 'work', 'build.json'), {})
    fx_slots = [s for s in (read(os.path.join(proj, 'plan.json'), {}) or {}).get('slots') or [] if not s.get('off')]
    n = int(sys.argv[sys.argv.index('--n') + 1]) if '--n' in sys.argv else 6
    if '--at' in sys.argv:
        times = [float(x) for x in sys.argv[sys.argv.index('--at') + 1].split(',') if x]
    elif words:
        idx = sorted(set(round(i * (len(words) - 1) / max(n - 1, 1)) for i in range(n)))
        times = [round((words[i]['start'] + words[i]['end']) / 2, 2) for i in idx]
    else:
        times = [1.0]
    out_dir = os.path.join(proj, 'work', 'check')
    os.makedirs(out_dir, exist_ok=True)
    head, lift = layout.get('head'), int(layout.get('lift') or 0)
    segs = layout.get('segments') or []
    raw_ok = bool(built.get('untouched_footage'))
    face_ok = bool(built.get('face_in_place', True)) and head
    aroll = os.path.join(proj, 'assets', 'aroll.mp4')
    unsafe = [(0, 0, 1080, 220), (0, 1470, 1080, 1920), (0, 220, 35, 1470), (1045, 220, 1080, 1155), (980, 1155, 1080, 1470)]
    per_row = 6                                    # six frames a row keeps every frame big enough to read the text
    rows_n = (len(times) + per_row - 1) // per_row
    sheet = Image.new('RGB', (FW * min(len(times), per_row), FH * rows_n), '#000')
    flagged = []
    for col, t in enumerate(times):
        im = grab(render, t, os.path.join(out_dir, f'r_{col}.png'))
        face = None
        if face_ok:
            seg = next((s for s in segs if s['t0'] - .02 <= t < s['t1'] and s.get('head_top') is not None), None)
            top = (seg['head_top'] if seg else head['top']) - lift
            chin = (seg['chin'] if seg else head['chin']) - lift
            dx = (seg['cx'] - head['cx']) if seg and seg.get('cx') is not None else 0
            face = (head['left'] + dx, top + .22 * (chin - top), head['right'] + dx, chin)     # brow to chin: hair and caps may be overlapped
        line = f'{t:6.2f}s'
        in_slot = next((s for s in fx_slots if float(s['from']) - .001 <= t < float(s['to'])), None)
        if in_slot:
            # an effect moves, regrades or covers the picture on purpose: the two numbers would always fire
            line += f"   inside the {in_slot.get('key') or in_slot.get('slot')} effect: no automatic numbers, judge this frame by eye"
        elif raw_ok and os.path.isfile(aroll):
            raw = grab(aroll, t, os.path.join(out_dir, f'a_{col}.png'))
            u = max(changed(im, raw, box) for box in unsafe)
            line += f'   unsafe area changed {u * 100:4.1f}%'
            f = changed(im, raw, face) if face else 0.0
            if face:
                line += f'   face box changed {f * 100:4.1f}%'
            if u > .015 or f > .015:
                line += '   << LOOK AT THIS FRAME'
                flagged.append(t)
        print(line)
        d = ImageDraw.Draw(im)
        d.rectangle([35 // S, 220 // S, 1045 // S, 1470 // S], outline='#ff3030')
        d.line([980 // S, 1155 // S, 980 // S, 1470 // S], fill='#ff3030')
        d.line([980 // S, 1155 // S, 1045 // S, 1155 // S], fill='#ff3030')
        if face:
            d.rectangle([int(v / S) for v in face], outline='#30ff60', width=2)
        d.text((8, 6), f'{t:.2f}s', fill='#ffffff')
        sheet.paste(im, ((col % per_row) * FW, (col // per_row) * FH))
    name = os.path.splitext(os.path.basename(render))[0]
    path = os.path.join(out_dir, name + '.jpg')
    sheet.save(path, quality=88)
    if not raw_ok:
        print('This look regrades or moves the picture, so the two automatic numbers are skipped: judge from the picture.')
    if not face_ok and head:
        print('This look moves the speaker inside the frame, so no face box is drawn: check the face by eye.')
    print(f'{len(times)} frames from the final render -> {path}')
    print('LOOK at it: nothing on the face, nothing in the red area, text readable, cutout edge clean.'
          + (f'  Flagged: {flagged}' if flagged else ''))


if __name__ == '__main__':
    main()
