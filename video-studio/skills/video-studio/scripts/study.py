#!/usr/bin/env python3
"""Study an example the buyer showed, top to bottom: a video (a reel they like) or a still (a pin, a screenshot).
It pulls out everything that can be measured and lays the whole thing out as pictures to LOOK at. It does not judge
the look: the editing Claude reads the sheets and writes the style down (references/replicate.md).

Usage:  PY study.py <example file> [--out <folder>] [--step 0.5] [--no-words]

  <example file>   a video (mp4, mov, webm) or a picture (png, jpg, webp) the buyer dropped in, or the direct address
                   of one (get_example.py brings it into the state folder first).
  --out            where the study goes. Default: <state folder>/examples/<file name>/
  --step           seconds between sampled frames (default: 0.5, stretched so a long video gives 96 frames at most)
  --no-words       skip the transcript (a video with no speech, or the speech model is not there yet)

What it writes into the folder:
  sheet_01.jpg ...   EVERY sampled frame with its time, 12 to a sheet, in order. Read all of them, not three stills:
                     captions, graphics and framing change from beat to beat.
  cuts.jpg           the frame before and after each cut, side by side, with the cut time
  study.json         size, length, the cut times and shot lengths, pace, loudness over time and where sound cues
                     hit, the words with their times (speech rate, pauses), and the sampled frame times
  frames/            the sampled frames at full size, for a closer look at type and colour
A still gives one sheet (the picture, and a 2x crop of its middle) and its size.
The printed summary is the measured half of the study. The seen half is yours: typeface feel, case, colours, plate,
placement, how captions arrive, graphic elements, grade.
"""
import array
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

FF, FP = skillenv.tool('ffmpeg'), skillenv.tool('ffprobe')
STILLS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')


def opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def probe(path):
    out = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height,r_frame_rate:format=duration', '-of', 'json', path], **skillenv.TEXT).stdout
    try:
        d = json.loads(out)
        st = d['streams'][0]
        a, b = (st.get('r_frame_rate') or '30/1').split('/')
        return int(st['width']), int(st['height']), float(a) / max(float(b), 1), float(d['format'].get('duration') or 0)
    except (ValueError, KeyError, IndexError, ZeroDivisionError):
        return 0, 0, 30.0, 0.0


def sheet(tiles, path, cols=6, tw=270, th=480):
    """tiles = [(label, image file)] -> one picture, `cols` to a row"""
    from PIL import Image, ImageDraw
    rows = (len(tiles) + cols - 1) // cols
    out = Image.new('RGB', (cols * tw, rows * th), '#111')
    for i, (label, f) in enumerate(tiles):
        try:
            im = Image.open(f).convert('RGB')
        except OSError:
            continue
        im.thumbnail((tw, th))
        x, y = (i % cols) * tw + (tw - im.width) // 2, (i // cols) * th + (th - im.height) // 2
        out.paste(im, (x, y))
        d = ImageDraw.Draw(out)
        d.rectangle([(i % cols) * tw, (i // cols) * th, (i % cols) * tw + 74, (i // cols) * th + 16], fill='#000')
        d.text(((i % cols) * tw + 4, (i // cols) * th + 2), label, fill='#fff')
    out.save(path, quality=88)


def loudness(path, win=.1):
    """-> ([dB per window], window seconds) from the audio, or ([], win) when there is none"""
    p = subprocess.run([FF, '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], capture_output=True)
    pcm = array.array('h')
    pcm.frombytes(p.stdout[:len(p.stdout) // 2 * 2])
    if sys.byteorder == 'big':
        pcm.byteswap()
    n = int(16000 * win)
    import math
    out = []
    for i in range(0, len(pcm) - n + 1, n):
        seg = pcm[i:i + n]
        rms = math.sqrt(sum(v * v for v in seg) / n) / 32768
        out.append(round(20 * math.log10(max(rms, 1e-5)), 1))
    return out, win


def main():
    skillenv.utf8_stdio()
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for flag in ('--out', '--step'):
        if opt(flag) in args:
            args.remove(opt(flag))
    if not args:
        sys.exit(__doc__)
    if args[0].strip().lower().startswith(('http://', 'https://')):      # a direct media address: bring it in first
        import get_example
        src = get_example.fetch(args[0])
        if not src:
            sys.exit(2)
    else:
        src = os.path.abspath(skillenv.path_arg(args[0]))
    if not os.path.isfile(src):
        sys.exit(f'not found: {src}')
    name = skillenv.safe_name(os.path.splitext(os.path.basename(src))[0])
    out = os.path.abspath(skillenv.path_arg(opt('--out'))) if opt('--out') else os.path.join(skillenv.examples_dir(), name)
    frames_dir = os.path.join(out, 'frames')
    os.makedirs(frames_dir, exist_ok=True)
    w, h, fps, dur = probe(src)
    quiet = [FF, '-loglevel', 'error', '-y']

    if src.lower().endswith(STILLS) or dur < .2:
        from PIL import Image
        im = Image.open(src).convert('RGB')
        full = os.path.join(frames_dir, 'still.jpg')
        im.save(full, quality=92)
        cw, ch = im.width // 2, im.height // 2
        crop = os.path.join(frames_dir, 'still_middle_2x.jpg')
        im.crop((im.width // 4, im.height // 4, im.width // 4 + cw, im.height // 4 + ch)).resize((im.width, im.height)).save(crop, quality=92)
        sheet([('whole', full), ('middle 2x', crop)], os.path.join(out, 'sheet_01.jpg'), cols=2, tw=540, th=960)
        study = {'kind': 'still', 'file': src, 'width': im.width, 'height': im.height,
                 'aspect': round(im.width / max(im.height, 1), 3)}
        with open(os.path.join(out, 'study.json'), 'w', encoding='utf-8') as fh:
            json.dump(study, fh, indent=1)
        print(f'still  {im.width}x{im.height}  -> {skillenv.shell_path(out)}')
        print('LOOK at sheet_01.jpg. A still shows type, colour, plate, placement and graphic elements. It cannot show '
              'rhythm, animation, pace or sound: ask the buyer about those, or pick calm defaults and say so.')
        return

    step = max(float(opt('--step', '0.5')), dur / 96)
    # stop a little before the end (a seek past the last frame gives nothing) and write full-range jpegs quietly
    times = [round(i * step, 3) for i in range(int(dur / step) + 1) if i * step < dur - .15]
    still = ['-frames:v', '1', '-vf', 'scale=540:-2', '-pix_fmt', 'yuvj420p', '-q:v', '3']
    tiles = []
    for i, t in enumerate(times):
        f = os.path.join(frames_dir, f'f_{i:03d}_{t:07.3f}.jpg')
        subprocess.run(quiet + ['-ss', f'{t:.3f}', '-i', src] + still + [f], stderr=subprocess.DEVNULL)
        if os.path.isfile(f):
            tiles.append((f'{t:.2f}s', f))
    for k in range(0, len(tiles), 12):
        sheet(tiles[k:k + 12], os.path.join(out, f'sheet_{k // 12 + 1:02d}.jpg'))

    # cuts: where the picture changes hard from one frame to the next
    r = subprocess.run([FF, '-hide_banner', '-nostats', '-i', src, '-an', '-vf', "select='gt(scene,0.32)',showinfo", '-f', 'null', '-'],
                       **skillenv.TEXT)
    cuts = sorted({round(float(x), 3) for x in re.findall(r'pts_time:([\d.]+)', r.stderr or '') if .15 < float(x) < dur - .15})
    cut_tiles = []
    for k, c in enumerate(cuts[:24]):
        for tag, t in (('before', max(0, c - 1.5 / fps)), ('after', c + .5 / fps)):
            f = os.path.join(frames_dir, f'cut_{k:02d}_{tag}.jpg')
            subprocess.run(quiet + ['-ss', f'{t:.3f}', '-i', src] + still + [f], stderr=subprocess.DEVNULL)
            if os.path.isfile(f):
                cut_tiles.append((f'{c:.2f}s {tag}', f))
    if cut_tiles:
        sheet(cut_tiles, os.path.join(out, 'cuts.jpg'))
    edges = [0.0] + cuts + [dur]
    shots = [round(b - a, 2) for a, b in zip(edges, edges[1:])]

    # sound: level over time, and the moments it jumps (a cue, a hit, a music entry)
    db, win = loudness(src)
    hits = []
    for i in range(4, len(db)):
        base = sorted(db[max(0, i - 6):i])[len(db[max(0, i - 6):i]) // 2]
        if db[i] - base >= 10 and db[i] > -32 and (not hits or i * win - hits[-1] > .35):
            hits.append(round(i * win, 2))
    loud = sorted(db)
    sound = {'has_audio': bool(db), 'median_db': loud[len(loud) // 2] if loud else None, 'peak_db': loud[-1] if loud else None,
             'quiet_share': round(sum(1 for v in db if v < -45) / len(db), 2) if db else None, 'jumps_at': hits}

    words = []
    if '--no-words' not in sys.argv and db:
        try:
            from faster_whisper import WhisperModel
            wav = os.path.join(out, 'audio.wav')
            subprocess.run(quiet + ['-i', src, '-vn', '-ac', '1', '-ar', '16000', wav])
            segs, _ = WhisperModel('small.en', compute_type='int8').transcribe(wav, word_timestamps=True, vad_filter=True)
            words = [{'text': x.word.strip(), 'start': round(x.start, 2), 'end': round(x.end, 2)} for s in segs for x in (s.words or [])]
        except Exception as e:      # no speech model yet, no speech, or music only: the study still stands
            print(f'note: no transcript ({type(e).__name__}). Run again after the first edit, or pass --no-words.')
    spoken = sum(x['end'] - x['start'] for x in words)
    pauses = [round(b['start'] - a['end'], 2) for a, b in zip(words, words[1:]) if b['start'] - a['end'] > .35]

    study = {'kind': 'video', 'file': src, 'width': w, 'height': h, 'fps': round(fps, 2), 'duration': round(dur, 2),
             'aspect': round(w / max(h, 1), 3), 'frame_times': times, 'cuts': cuts, 'shots': shots,
             'shot_median': sorted(shots)[len(shots) // 2] if shots else None, 'sound': sound, 'loudness_db': db, 'loudness_step': win,
             'words': words, 'words_per_second': round(len(words) / dur, 2) if dur else None,
             'speech_share': round(spoken / dur, 2) if dur else None, 'pauses_over_0.35s': len(pauses)}
    with open(os.path.join(out, 'study.json'), 'w', encoding='utf-8') as fh:
        json.dump(study, fh, indent=1)

    n_sheets = (len(tiles) + 11) // 12
    print(f'video  {w}x{h}  {dur:.2f}s  {fps:.0f}fps  -> {skillenv.shell_path(out)}')
    print(f'frames {len(tiles)} sampled every {step:.2f}s on {n_sheets} sheet(s): sheet_01.jpg to sheet_{n_sheets:02d}.jpg. LOOK at every one')
    print(f'cuts   {len(cuts)}' + (f' at {", ".join(f"{c:.2f}" for c in cuts[:30])}' if cuts else ' (one continuous shot)')
          + (f'   shots {min(shots):.2f} to {max(shots):.2f}s, typical {study["shot_median"]:.2f}s   cuts.jpg shows each one' if cuts else ''))
    if db:
        print(f'sound  typical level {sound["median_db"]} dB, peak {sound["peak_db"]} dB, {sound["quiet_share"] * 100:.0f}% near silent; '
              f'{len(hits)} sudden jump(s)' + (f' at {", ".join(f"{t:.2f}" for t in hits[:20])}' if hits else '')
              + ' (a jump is a sound cue, a hit or music coming in: check it against the frame at that time)')
    else:
        print('sound  none')
    if words:
        print(f'words  {len(words)} in {dur:.1f}s = {study["words_per_second"]} a second, speech fills {study["speech_share"] * 100:.0f}% '
              f'of the time, {len(pauses)} pause(s) over 0.35s')
        print('       first words: ' + ' '.join(f"{x['text']}@{x['start']:.2f}" for x in words[:14]))
    print('next: read the sheets, then write the style down (references/replicate.md, "What to write down")')


if __name__ == '__main__':
    main()
