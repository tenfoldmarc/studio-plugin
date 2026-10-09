#!/usr/bin/env python3
"""Check the FINAL render of a comment-bubble slot (not snapshots): frame count, then two sheets to LOOK at.

    PY check.py            reads renders/<slot folder>.mp4 + work/layout.json

  work/check/full.jpg   12 whole frames on the beats (is their face clear? does each beat land on its word?)
  work/check/band.jpg   the thread region at full size on the same beats (clean edges, no double text, safe zone)
The safe zone and the chin line the layout used are drawn on both. Nothing readable may touch the red lines.
"""
import json
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
os.chdir(os.path.dirname(os.path.abspath(__file__)))
slot = os.path.basename(os.getcwd())
mp4 = sys.argv[1] if len(sys.argv) > 1 else f'renders/{slot}.mp4'
L = json.load(open('work/layout.json'))
want = L['frames']
got = int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                          '-of', 'csv=p=0', mp4], capture_output=True, text=True).stdout.strip() or 0)
print(f'{mp4}: {got} frames, slot wants {want}  ->  {"OK" if got == want else "MISMATCH (the main reel will drift)"}')
os.makedirs('work/check', exist_ok=True)
try:
    FONT = ImageFont.truetype('assets/fonts/Inter-600-normal.woff2', 30)
except OSError:
    FONT = None
b = L['beats']
picks = [('before', round(b['T_IN'] * 30) - 2), ('field in', round((b['T_IN'] + .3) * 30)), ('focus', round(b['T_FOCUS'] * 30) + 3),
         ('first key', round(b['T_TYPE'] * 30) + 2), ('typed', round(b['last_key'] * 30) + 3), ('tap', round(b['T_SEND'] * 30) + 1),
         ('posting', round((b['T_SEND'] + .17) * 30)), ('posted+heart', round((b['T_SEND'] + .5) * 30)), ('dots', round(b['T_DOTS'] * 30) + 4),
         ('reply', round(b['T_REPLY'] * 30) + 5), ('chip', round(b['T_LINK'] * 30) + 5), ('last frame', want - 1)]
picks.sort(key=lambda p: p[1])
y0 = max(0, int(min(L['chin_eff'] - 90, L['y0'] - 90)))
y1 = min(1920, 1500)
full, band = [], []
for name, f in picks:
    f = max(0, min(got - 1, f))
    png = 'work/check/_f.png'
    subprocess.run([FF, '-v', 'error', '-y', '-i', mp4, '-vf', f'select=eq(n\\,{f})', '-frames:v', '1', png], check=True)
    im = Image.open(png).convert('RGB')
    d = ImageDraw.Draw(im)
    for box in ((0, 0, 1080, 220), (0, 1470, 1080, 1920)):
        d.rectangle(box, outline=(255, 0, 0), width=3)
    d.line([(35, 220), (35, 1470)], fill=(255, 0, 0), width=2)
    d.line([(1045, 220), (1045, 1155), (980, 1155), (980, 1470)], fill=(255, 0, 0), width=2)
    d.line([(0, L['chin_eff']), (1080, L['chin_eff'])], fill=(0, 255, 255), width=2)
    tag = f'f{f} {f / 30:.2f}s  {name}'
    d.rectangle((0, y0, 520, y0 + 44), fill=(0, 0, 0))
    d.text((10, y0 + 6), tag, fill=(255, 255, 0), font=FONT)
    band.append(im.crop((0, y0, 1080, y1)).resize((810, (y1 - y0) * 3 // 4), Image.LANCZOS))
    sm = im.resize((360, 640), Image.LANCZOS)
    ds = ImageDraw.Draw(sm)
    ds.rectangle((0, 0, 360, 20), fill=(0, 0, 0))
    ds.text((6, 5), tag, fill=(255, 255, 0))
    full.append(sm)
sheet = Image.new('RGB', (360 * 6, 640 * 2))
for i, im in enumerate(full):
    sheet.paste(im, ((i % 6) * 360, (i // 6) * 640))
sheet.save('work/check/full.jpg', quality=88)
bh = band[0].size[1]
sheet = Image.new('RGB', (810 * 2, bh * 6))
for i, im in enumerate(band):
    sheet.paste(im, ((i % 2) * 810, (i // 2) * bh))
sheet.save('work/check/band.jpg', quality=88)
print('look at: work/check/full.jpg  work/check/band.jpg')
