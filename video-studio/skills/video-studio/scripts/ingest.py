#!/usr/bin/env python3
"""Register raw clips for a video-studio project, make contact sheets, transcribe every clip.

Usage (run with PY, the skill's Python from .platform.json; it has faster-whisper):
  PY ingest.py <project_dir> <clip files or one folder> [--newest N]

Writes into <project_dir>:
  sources.json             {"c1": "/abs/original.MP4", ...}  (ordered oldest -> newest by file time)
  work/sheet_cN.jpg        8 frames across each clip; work/sheets.jpg stacks them (look at it: setups, angles)
  words_cN.json            word timestamps per clip (small.en)
  transcript.txt           per-clip segment transcript + speech regions (silencedetect) for picking takes
Originals are never modified. Everything is read straight from them (no proxies).
"""
import json
import os
import subprocess
import sys

from faster_whisper import WhisperModel

sys.dont_write_bytecode = True   # no __pycache__ next to the scripts (a plugin's folder is not ours to write in)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

FF, FP = skillenv.tool('ffmpeg'), skillenv.tool('ffprobe')
VIDEO_EXT = ('.mp4', '.mov', '.m4v')


def probe(f):
    out = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate',
                          '-show_entries', 'format=duration', '-of', 'json', f], **skillenv.TEXT).stdout
    j = json.loads(out)
    s = j['streams'][0]
    return s['width'], s['height'], s['r_frame_rate'], float(j['format']['duration'])


def speech_regions(f):
    out = subprocess.run([FF, '-hide_banner', '-i', f, '-af', 'silencedetect=n=-38dB:d=0.35', '-f', 'null', '-'],
                         **skillenv.TEXT).stderr
    marks = [(l.split('silence_')[1].split(':')[0], float(l.split(': ')[1].split(' ')[0]))
             for l in out.splitlines() if 'silence_start' in l or 'silence_end' in l]
    return ' '.join(f"{k[0].upper()}{v:.2f}" for k, v in marks)   # S=silence start, E=silence end


def main():
    skillenv.utf8_stdio()
    proj, args = skillenv.path_arg(sys.argv[1]), sys.argv[2:]
    newest = None
    if '--newest' in args:
        i = args.index('--newest'); newest = int(args[i + 1]); args = args[:i] + args[i + 2:]
    files = []
    for a in map(skillenv.path_arg, args):
        if os.path.isdir(a):
            files += [os.path.join(a, f) for f in os.listdir(a) if f.lower().endswith(VIDEO_EXT)]
        else:
            files.append(a)
    files = sorted(set(os.path.abspath(f) for f in files), key=os.path.getmtime)
    if newest:
        files = files[-newest:]
    work = os.path.join(proj, 'work')
    os.makedirs(work, exist_ok=True)
    sources = {f'c{k + 1}': f for k, f in enumerate(files)}
    with open(os.path.join(proj, 'sources.json'), 'w', encoding='utf-8') as fh:
        json.dump(sources, fh, indent=1)

    sheets = []
    for cid, f in sources.items():
        w, h, fr, d = probe(f)
        print(f'{cid}  {w}x{h} {fr} {d:.1f}s  {os.path.basename(f)}')
        sh = os.path.join(work, f'sheet_{cid}.jpg')
        subprocess.run([FF, '-loglevel', 'error', '-y', '-i', f, '-vf', f'fps=8/{d},scale=200:-2,tile=8x1', '-frames:v', '1', sh], check=True)
        sheets.append(sh)
    ins = sum((['-i', s] for s in sheets), [])
    stack = ['-filter_complex', f'vstack={len(sheets)}'] if len(sheets) > 1 else []
    subprocess.run([FF, '-loglevel', 'error', '-y', *ins, *stack, os.path.join(work, 'sheets.jpg')], check=True)

    m = WhisperModel('small.en', compute_type='int8')
    lines = []
    for cid, f in sources.items():
        wav = os.path.join(work, f'{cid}.wav')
        subprocess.run([FF, '-loglevel', 'error', '-y', '-i', f, '-vn', '-ac', '1', '-ar', '16000', wav], check=True)
        segs, _ = m.transcribe(wav, word_timestamps=True, vad_filter=False)
        words = []
        lines.append(f'===== {cid}  {os.path.basename(f)}')
        for s in segs:
            lines.append(f'[{s.start:6.2f}-{s.end:6.2f}] {s.text.strip()}')
            for w in s.words:
                t = w.word.strip()
                if words and t[:1] in '-.' and len(t) > 1 and t[1:2].isdigit():   # "GPT" "-6" / "5" ".1"
                    words[-1]['text'] += t; words[-1]['end'] = round(w.end, 3); continue
                words.append({'text': t, 'start': round(w.start, 3), 'end': round(w.end, 3)})
        with open(os.path.join(proj, f'words_{cid}.json'), 'w', encoding='utf-8') as fh:
            json.dump(words, fh, indent=1)
        lines.append('words: ' + ' '.join(f"{w['text']}@{w['start']:.2f}" for w in words))
        lines.append('speech map: ' + speech_regions(f))
    with open(os.path.join(proj, 'transcript.txt'), 'w', encoding='utf-8') as fh:   # utf-8: Whisper emits curly quotes, notes
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
