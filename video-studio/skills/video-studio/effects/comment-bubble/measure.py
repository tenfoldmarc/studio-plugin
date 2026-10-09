#!/usr/bin/env python3
"""Measure what comment-bubble needs from a slot, so nothing is placed by eye:

  1. word onsets from the audio energy (Whisper starts are 0.1 to 0.6s off)  -> printed, with a paste-ready CLIP block
  2. head box + chin line per frame, from the cutout alpha (assets/subject.webm)  -> work/measure.json
  3. a check sheet with the chin line and head box drawn on 8 frames              -> work/measure_check.jpg

Run from the slot folder with the skill's Python (PY) (numpy + PIL):
    PY measure.py           add --env to print the 20 ms energy envelope
No cutout in the slot (fx_new.py --no-cutout)? It still prints the onsets; set CHIN_Y by hand in build.py.

How the chin is found (no face model): walk down the silhouette from the top of the head, following the head's own
run of pixels (a raised hand beside the head is a separate run and is ignored). The head is the widest stretch before
the outline tapers towards the neck. Chin = head_top + CHIN_K x head_width. CHIN_K = 1.5 fits a speaker with a cap on,
close-up and wide (checked on both); it lands on the chin or up to ~35 px below it, never above the mouth. Frames
where no taper is found (a hand on the face, a hood) or the width jumps are filled from their neighbours and drawn
red on the sheet. LOOK at the sheet: the line must sit on or just under their chin. If not, set CHIN_Y in build.py.
"""
import json
import os
import shutil
import subprocess
import sys
import wave

import numpy as np

FF = shutil.which('ffmpeg') or 'ffmpeg'
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('work', exist_ok=True)
AW, AH = 270, 480          # alpha analysis size (1/4 of the frame)
K = 1080 / AW
CHIN_K = 1.5               # chin = head_top + CHIN_K * head_width
NECK_RATIO = 0.85          # the outline must narrow to this fraction of the head width for the head to count as found


# ---------------------------------------------------------------------------------------------------- audio
def envelope():
    subprocess.run([FF, '-v', 'error', '-y', '-i', 'assets/aroll.mp4', '-vn', '-ac', '1', '-ar', '16000', 'work/onsets.wav'], check=True)
    wv = wave.open('work/onsets.wav')
    x = np.frombuffer(wv.readframes(wv.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    hop = 160                                  # 10 ms
    n = len(x) // hop
    return 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-6)


def refine(db, t, t_next):
    """audio onset of a word Whisper put at t: the first 10 ms step in [t-0.06, t+0.32] (and before the next word)
    where the level jumps 8 dB over the previous 50 ms and is at speech level. Nothing found -> Whisper's time."""
    floor = np.percentile(db, 10)
    speech = max(floor + 14, np.percentile(db, 75) - 16)
    a = max(5, int(round((t - .06) * 100)))
    b = min(len(db) - 1, int(round(min(t + .32, t_next - .03 if t_next else 1e9) * 100)))
    for i in range(a, b + 1):
        if db[i] >= speech and db[i] - db[i - 5:i].min() >= 8:
            return round(i / 100, 2), True
    return t, False


def word_end(db, t_end):
    """where a word stops sounding: the start of the quietest moment in [whisper end - 0.05, whisper end + 0.12]
    (Whisper ends words a little early; a dip inside the word, like vi-deo, must not count as the end)"""
    a, b = max(0, int(round((t_end - .05) * 100))), min(len(db), int(round((t_end + .12) * 100)) + 1)
    seg = db[a:b]
    return round((a + int(np.argmax(seg <= seg.min() + 3))) / 100, 2)


db = envelope()
if '--env' in sys.argv:
    for i in range(0, len(db), 2):
        print(f'{i / 100:5.2f} {db[i]:6.1f} ' + '#' * int(max(0, db[i] + 60) / 1.5))
res = {'duration': round(len(db) / 100, 2)}
words = json.load(open('words.json')) if os.path.exists('words.json') else []
ons = []
print('word            whisper   audio onset   frame')
for i, wd in enumerate(words):
    nxt = words[i + 1]['start'] if i + 1 < len(words) else None
    t, ok = refine(db, wd['start'], nxt)
    ons.append({'text': wd['text'], 'whisper': wd['start'], 'onset': t, 'refined': ok})
    print(f"{wd['text']:14s}  {wd['start']:6.2f}    {t:6.2f} {'*' if ok else ' '}      {round(t * 30):4d}")
print('(* = moved to the energy onset; no star = no clear attack found, check it with --env)')
res['onsets'] = ons

# paste-ready times, if the line has the usual shape "... comment KEYWORD and I'll send you the THING"
low = [o['text'].lower().strip('.,!?') for o in ons]
ic = next((i for i, w in enumerate(low) if w.startswith('comment')), None)
if ic is not None and ic + 1 < len(ons):
    kw = ons[ic + 1]
    letters = sum(ch.isalnum() for ch in kw['text'])
    t_focus = ons[ic]['onset']
    t_type = round(kw['onset'] - .03, 2)
    kw_end = max(word_end(db, words[ic + 1]['end']), kw['onset'] + .15)
    gap = round(min(.11, max(.05, (kw_end - t_type - .1) / max(1, letters - 1))), 3)
    t_send = round(max(kw_end, t_type + (letters - 1) * gap + .1), 2)
    isend = next((i for i in range(ic + 2, len(ons)) if low[i].startswith('send')), None)
    t_reply = round((ons[isend]['onset'] if isend is not None else t_send + .5) - .03, 2)
    t_reply = max(t_reply, round(t_send + .32, 2))             # the post needs 0.3s before the reply can land
    t_dots = round(min(max(t_send + .2, t_reply - .2), t_reply - .12), 2)
    ilink = None
    if isend is not None:
        ilink = next((i for i in range(isend + 1, len(ons)) if low[i] not in ('you', 'the', 'a', 'my', 'it', 'over')), None)
    t_link = round((ons[ilink]['onset'] - .03) if ilink is not None else t_reply + .35, 2)
    t_link = max(t_link, round(t_reply + .28, 2))
    print('\nsuggested CLIP times (check them against the table above, then paste):')
    print(f"KEYWORD = '{''.join(ch for ch in kw['text'].upper() if ch.isalnum())}'")
    print(f'T_IN = {max(.05, round(t_focus - .43, 2)):.2f}\nT_FOCUS = {t_focus:.2f}\nT_TYPE = {t_type:.2f}\nKEY_GAP = {gap}\nT_SEND = {t_send:.2f}'
          f'\nT_DOTS = {t_dots:.2f}\nT_REPLY = {t_reply:.2f}\nT_LINK = {t_link:.2f}'
          + (f"      # on \"{ons[ilink]['text']}\"" if ilink is not None else ''))
    print(f'(keyword sounds {kw["onset"]:.2f} to {kw_end:.2f}; slot is {res["duration"]:.2f}s, {res["duration"] - t_link:.2f}s after the chip lands)')
else:
    print('\nno "comment <keyword>" found in words.json: set the times by hand from the table')


# ---------------------------------------------------------------------------------------------------- head + chin
def runs(row):
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def head_profile(mask):
    """follow the head's run of pixels down from the top of the silhouette: [(y, x0, x1)]"""
    rows = np.flatnonzero(mask.sum(1) >= 3)
    if len(rows) == 0:
        return []
    prof, x0, x1 = [], None, None
    for y in range(rows[0], AH):
        rs = [r for r in runs(mask[y]) if r[1] - r[0] >= 2]
        if not rs:
            if prof:
                break
            continue
        if x0 is None:
            r = max(rs, key=lambda r: r[1] - r[0])
        else:
            best = max(((min(r[1], x1) - max(r[0], x0), r) for r in rs), key=lambda o: o[0])
            if best[0] <= 0:
                break
            r = best[1]
        x0, x1 = r
        prof.append((y, x0, x1))
    return prof


def measure_frame(mask):
    prof = head_profile(mask)
    if len(prof) < 12:
        return None
    w = np.array([p[2] - p[1] for p in prof], dtype=float)
    ws = np.array([np.median(w[max(0, i - 2):i + 3]) for i in range(len(w))])
    m, i_w, found = 0.0, 0, False
    for i, v in enumerate(ws):
        if v > m:
            m, i_w = v, i
        elif i - i_w > 2 and v < NECK_RATIO * m and i > 0.6 * m:      # past the widest row, clearly narrower, far enough down
            found = True
            break
    if not found:
        return None
    top = prof[0][0]
    cx = (prof[i_w][1] + prof[i_w][2]) / 2
    return {'top': round(top * K), 'head_w': round(m * K), 'cx': round(cx * K), 'chin': round((top + CHIN_K * m) * K), 'clean': True}


if os.path.exists('assets/subject.webm'):
    p = subprocess.run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', 'assets/subject.webm', '-vf',
                        f'alphaextract,scale={AW}:{AH}', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True)
    A = np.frombuffer(p.stdout, dtype=np.uint8)
    A = A[:len(A) // (AW * AH) * AW * AH].reshape(-1, AH, AW)
    per = [measure_frame(A[f] > 128) for f in range(len(A))]
    good = [q for q in per if q]
    if good:
        wmed = float(np.median([q['head_w'] for q in good]))
        per = [q if q and .72 * wmed <= q['head_w'] <= 1.3 * wmed else None for q in per]      # width jumps = hand merged in
        idx = [i for i, q in enumerate(per) if q]
        if idx:
            for i in range(len(per)):                                                           # fill gaps from the nearest good frame
                if per[i] is None:
                    j = min(idx, key=lambda k: abs(k - i))
                    per[i] = dict(per[j], clean=False)
            res['frames'] = per
            ch = np.array([q['chin'] for q in per])
            print(f'\ncutout: {len(per)} frames, head found on {len(idx)} ({100 * len(idx) // len(per)}%)')
            print(f"chin y: median {int(np.median(ch))}  lowest {int(ch.max())}  highest {int(ch.min())}   "
                  f"head width {int(np.median([q['head_w'] for q in per]))}  head centre x {int(np.median([q['cx'] for q in per]))}")
            if len(idx) < .4 * len(per):
                print('  ! head found on under 40% of the frames: trust the check sheet, not the numbers, or set CHIN_Y by hand')
            try:
                from PIL import Image, ImageDraw
                n = len(per)
                tiles = []
                for f in [round(i * (n - 1) / 7) for i in range(8)]:
                    png = 'work/_measure_tile.png'
                    subprocess.run([FF, '-v', 'error', '-y', '-i', 'assets/aroll.mp4', '-vf', f'select=eq(n\\,{f}),scale=540:960',
                                    '-frames:v', '1', png], check=True)
                    im = Image.open(png).convert('RGB')
                    d = ImageDraw.Draw(im)
                    q = per[f]
                    d.line([(0, q['chin'] / 2), (540, q['chin'] / 2)], fill=(0, 255, 120) if q['clean'] else (255, 80, 80), width=3)
                    d.rectangle([(q['cx'] - q['head_w'] / 2) / 2, q['top'] / 2, (q['cx'] + q['head_w'] / 2) / 2, q['chin'] / 2],
                                outline=(250, 230, 122), width=2)
                    d.text((8, 8), f"f{f}  chin {q['chin']}  {'measured' if q['clean'] else 'FILLED from a neighbour'}", fill=(255, 255, 255))
                    tiles.append(im)
                sheet = Image.new('RGB', (540 * 4, 960 * 2))
                for i, im in enumerate(tiles):
                    sheet.paste(im, ((i % 4) * 540, (i // 4) * 960))
                sheet.save('work/measure_check.jpg', quality=86)
                print('check sheet: work/measure_check.jpg  (the line must sit on or just under their chin; red = filled frame)')
                # avatar candidates: the same square head crop build.py makes, on 12 frames, to pick AVATAR_FRAME from
                crops = []
                for f in [round(i * (n - 1) / 11) for i in range(12)]:
                    q = per[f]
                    side = int(min(1.5 * q['head_w'], 1080))
                    x = int(min(max(0, q['cx'] - side / 2), 1080 - side))
                    y = int(min(max(0, q['top'] - .06 * side), 1920 - side))
                    png = 'work/_measure_tile.png'
                    subprocess.run([FF, '-v', 'error', '-y', '-i', 'assets/aroll.mp4', '-vf',
                                    f'select=eq(n\\,{f}),crop={side}:{side}:{x}:{y},scale=240:240:flags=lanczos', '-frames:v', '1', png], check=True)
                    im = Image.open(png).convert('RGB')
                    d = ImageDraw.Draw(im)
                    d.rectangle((0, 0, 70, 22), fill=(0, 0, 0))
                    d.text((6, 5), f'f{f}', fill=(255, 255, 0))
                    crops.append(im)
                sheet = Image.new('RGB', (240 * 6, 240 * 2))
                for i, im in enumerate(crops):
                    sheet.paste(im, ((i % 6) * 240, (i // 6) * 240))
                sheet.save('work/avatar_check.jpg', quality=88)
                print('avatar candidates: work/avatar_check.jpg  (set AVATAR_FRAME to one with their eyes open, looking at the lens)')
            except ImportError:
                print("PIL missing: no check sheet (run with the skill's Python (PY))")
    if 'frames' not in res:
        print('\ncutout: no head found in the alpha. Set CHIN_Y by hand in build.py.')
else:
    print('\nno assets/subject.webm: set CHIN_Y by hand in build.py (y of the bottom of their chin, the lowest it gets in the slot)')

json.dump(res, open('work/measure.json', 'w'))
print('wrote work/measure.json')
