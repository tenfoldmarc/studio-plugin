#!/usr/bin/env python3
"""The last step of replicating an example: frames of the example on the top row, frames of the buyer's finished
reel on the bottom row, in one picture. Look at it and write the plain list for the buyer: what matches, what could
not be matched.

Usage:  PY side_by_side.py <example file> <project_dir> <render.mp4> [--example-at 1.2,3.0,6.5] [--at 0.8,2.4,5.0]
                           [--n 5] [--out <file.jpg>]

  <example file>   the video or still the buyer showed
  <render.mp4>     the FINAL render (written the short way, "renders/<file>.mp4", it is looked up in the project)
  --example-at     moments of the example to show (seconds). Default: --n moments spread across it
  --at             moments of the result to show. Default: --n moments spread across it. Pick pairs that show the
                   same kind of beat (a caption line, a marked word, a title, a graphic), not the same second: the
                   buyer's reel has its own words and its own length
Writes work/compare/<render name>-vs-example.jpg in the project (or --out).
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

FF, FP = skillenv.tool('ffmpeg'), skillenv.tool('ffprobe')
TW, TH = 360, 640
STILLS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')


def opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def duration(path):
    out = subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path], **skillenv.TEXT).stdout.strip()
    try:
        return float(out.split(',')[0])
    except ValueError:
        return 0.0


def spread(dur, n):
    return [round(dur * (i + .5) / n, 2) for i in range(n)]


def tile(path, t, tmp):
    """one frame as a TW x TH tile (letterboxed, never stretched)"""
    if path.lower().endswith(STILLS):
        im = Image.open(path).convert('RGB')
    else:
        subprocess.run([FF, '-loglevel', 'error', '-y', '-ss', f'{max(t, 0):.3f}', '-i', path, '-frames:v', '1', tmp], check=True)
        im = Image.open(tmp).convert('RGB')
    im.thumbnail((TW, TH))
    out = Image.new('RGB', (TW, TH), '#111')
    out.paste(im, ((TW - im.width) // 2, (TH - im.height) // 2))
    return out


def main():
    skillenv.utf8_stdio()
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for flag in ('--example-at', '--at', '--n', '--out'):
        if opt(flag) in args:
            args.remove(opt(flag))
    if len(args) < 3:
        sys.exit(__doc__)
    example, proj = os.path.abspath(skillenv.path_arg(args[0])), skillenv.path_arg(args[1])
    render = skillenv.project_file(proj, args[2])
    for f in (example, render):
        if not os.path.isfile(f):
            sys.exit(f'not found: {f}')
    n = int(opt('--n', '5'))
    still = example.lower().endswith(STILLS)
    ex_t = [float(x) for x in opt('--example-at', '').split(',') if x] or ([0.0] if still else spread(duration(example), n))
    re_t = [float(x) for x in opt('--at', '').split(',') if x] or spread(duration(render), max(n, len(ex_t)) if not still else n)
    cols = max(len(ex_t), len(re_t))
    work = os.path.join(proj, 'work', 'compare')
    os.makedirs(work, exist_ok=True)
    tmp = os.path.join(work, '_frame.png')
    sheet = Image.new('RGB', (cols * TW, 2 * TH + 56), '#000')
    d = ImageDraw.Draw(sheet)
    d.text((8, 6), 'THE EXAMPLE', fill='#ffffff')
    d.text((8, TH + 34), 'YOUR REEL', fill='#ffffff')
    for i, t in enumerate(ex_t):
        sheet.paste(tile(example, t, tmp), (i * TW, 24))
        d.text((i * TW + 8, 28), 'still' if still else f'{t:.2f}s', fill='#ffe45c')
    for i, t in enumerate(re_t):
        sheet.paste(tile(render, t, tmp), (i * TW, TH + 52))
        d.text((i * TW + 8, TH + 56), f'{t:.2f}s', fill='#ffe45c')
    out = os.path.abspath(skillenv.path_arg(opt('--out'))) if opt('--out') else os.path.join(
        work, os.path.splitext(os.path.basename(render))[0] + '-vs-example.jpg')
    sheet.save(out, quality=90)
    print(f'{len(ex_t)} example frame(s) over {len(re_t)} of the result -> {skillenv.shell_path(out)}')
    print('LOOK at it, then tell the buyer in plain words: what matches (type, colour, placement, rhythm, graphics, '
          'pace) and what could not be matched, one line each.')


if __name__ == '__main__':
    main()
