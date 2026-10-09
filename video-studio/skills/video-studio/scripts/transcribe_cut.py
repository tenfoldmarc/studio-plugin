#!/usr/bin/env python3
"""Word timings for the assembled cut -> <project>/words.json (medium.en; these drive every caption).

Usage:  PY transcribe_cut.py <project_dir> ["prompt with names: Claude, Claude Code, skill"]
Whisper mishears proper nouns ("Claude" -> "cloud"/"claws", "skill" -> "scale", "design" -> "this line"):
pass them in the prompt and still fix captions by hand from what the speaker actually said.
"""
import json
import os
import subprocess
import sys

from faster_whisper import WhisperModel

sys.dont_write_bytecode = True   # no __pycache__ next to the scripts (a plugin's folder is not ours to write in)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

skillenv.utf8_stdio()
proj = skillenv.path_arg(sys.argv[1])
wav = os.path.join(proj, 'work', 'aroll.wav')
os.makedirs(os.path.join(proj, 'work'), exist_ok=True)
prompt = sys.argv[2] if len(sys.argv) > 2 else 'Claude, Claude Code, skill.'
subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-i', os.path.join(proj, 'assets', 'aroll.mp4'), '-vn', '-ac', '1',
                '-ar', '16000', wav], check=True)
m = WhisperModel('medium.en', compute_type='int8')
s, _ = m.transcribe(wav, word_timestamps=True, vad_filter=False, initial_prompt=prompt)
ws = []
for x in s:
    for w in x.words:
        t = w.word.strip()
        if ws and t[:1] in '-.' and len(t) > 1 and t[1:2].isdigit():   # Whisper splits "GPT" "-6" and "5" ".1"
            ws[-1]['text'] += t
            ws[-1]['end'] = round(w.end, 3)
            continue
        ws.append({'text': t, 'start': round(w.start, 3), 'end': round(w.end, 3)})
with open(os.path.join(proj, 'words.json'), 'w', encoding='utf-8') as fh:
    json.dump(ws, fh, indent=1)
# keep Whisper's untouched output too: words.json is then cleaned and marked by hand (see references/captions.md)
with open(os.path.join(proj, 'work', 'words_raw.json'), 'w', encoding='utf-8') as fh:
    json.dump(ws, fh, indent=1)
print(' '.join(f"{w['text']}@{w['start']:.2f}" for w in ws))
