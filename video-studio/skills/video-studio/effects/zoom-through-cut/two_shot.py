#!/usr/bin/env python3
"""Make a zoom-through slot hold TWO shots with a hard cut between them (fx_new.py only cuts one span).

Run from the slot folder with the skill's Python (PY) (it transcribes and mattes):

  A) the two shots come from different places (two files, or two takes in one file):
     fx_new.py made the slot with shot A only (--no-cutout --no-transcribe). Add shot B:
       PY two_shot.py --src <video> (--in SEC | --frame F) --frames N_B
     -> work/shotA.mp4, work/shotB.mp4, assets/aroll.mp4 = A + B (30fps CFR, their audio, straight cut)

  B) the cut is already inside the slot's a-roll (fx_new.py cut one span of the assembled reel across a cut):
       PY two_shot.py --detect            (or --cut K if you know the first frame of shot B)

Both write clip.json ("frames", "cut_frames": [K], "parts"), words.json for the whole slot and assets/subject.webm
(cutout, recurrent state reset on the cut). --no-cutout / --no-transcribe skip those steps.

"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np

FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
AROLL = 'assets/aroll.mp4'

ap = argparse.ArgumentParser()
ap.add_argument('--src')
ap.add_argument('--in', dest='t_in', type=float)
ap.add_argument('--frame', type=int)
ap.add_argument('--frames', type=int)
ap.add_argument('--detect', action='store_true')
ap.add_argument('--cut', type=int)
ap.add_argument('--no-cutout', action='store_true')
ap.add_argument('--no-transcribe', action='store_true')
ap.add_argument('--prompt', default='Claude, Claude Code, skill.')
a = ap.parse_args()


def count(path):
    r = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                        'stream=nb_read_frames', '-of', 'csv=p=0', path], capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


clip = json.load(open('clip.json'))
if a.src:
    if a.frames is None or (a.t_in is None) == (a.frame is None):
        sys.exit('with --src pass --frames N and exactly one of --in SEC / --frame F')
    os.makedirs('work', exist_ok=True)
    if not os.path.exists('work/shotA.mp4'):        # first run: the slot's a-roll is shot A
        shutil.copy2(AROLL, 'work/shotA.mp4')
        json.dump(clip, open('work/clipA.json', 'w'), indent=1)
    clip_a = json.load(open('work/clipA.json'))
    na = count('work/shotA.mp4')
    rate = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate', '-of',
                           'csv=p=0', a.src], capture_output=True, text=True).stdout.strip() or '30/1'
    num, den = (float(x) for x in (rate.split('/') + ['1'])[:2])
    t0 = a.t_in if a.t_in is not None else a.frame / (num / den)
    dur_b = a.frames / 30.0
    fit = 'scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1'
    # same recipe as fx_new.py, so shot B is cut exactly like shot A
    subprocess.run([FF, '-v', 'error', '-y', '-ss', '%.4f' % max(0.0, t0 - 0.001), '-i', a.src, '-t', '%.4f' % (dur_b + .2),
                    '-vf', 'fps=30,' + fit, '-frames:v', str(a.frames), '-fps_mode', 'cfr', '-r', '30', '-c:v', 'libx264',
                    '-crf', '14', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-af', 'apad,atrim=0:%.4f' % dur_b,
                    '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-b:a', '192k', 'work/shotB.mp4'], check=True)
    if count('work/shotB.mp4') != a.frames:
        sys.exit('shot B came out short: the source ends before the span you asked for')
    total = na + a.frames
    fc = ('[0:v][1:v]concat=n=2:v=1:a=0,setpts=N/30/TB[v];'
          '[0:a]atrim=0:%.5f,asetpts=N/SR/TB[a0];[1:a]atrim=0:%.5f,asetpts=N/SR/TB[a1];[a0][a1]concat=n=2:v=0:a=1[au]'
          % (na / 30.0, dur_b))
    subprocess.run([FF, '-v', 'error', '-y', '-i', 'work/shotA.mp4', '-i', 'work/shotB.mp4', '-filter_complex', fc,
                    '-map', '[v]', '-map', '[au]', '-frames:v', str(total), '-fps_mode', 'cfr', '-r', '30', '-c:v', 'libx264',
                    '-crf', '12', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2',
                    '-b:a', '192k', '-movflags', '+faststart', AROLL], check=True)
    if count(AROLL) != total:
        sys.exit('joined a-roll has %d frames, expected %d' % (count(AROLL), total))
    cut = na
    clip.update({'frames': total, 'duration': round(total / 30.0, 4), 'cut_frames': [cut],
                 'parts': [{'src': clip_a.get('src'), 'in': clip_a.get('in'), 'first_frame': 0, 'frames': na},
                           {'src': os.path.abspath(a.src), 'in': round(t0, 4), 'first_frame': na, 'frames': a.frames}]})
    print('a-roll: %d + %d = %d frames, cut on frame %d' % (na, a.frames, total, cut))
else:
    cut = a.cut
    if cut is None:
        if not a.detect:
            sys.exit('pass --src ... to add shot B, or --detect / --cut K when the cut is already in the a-roll')
        raw = subprocess.run([FF, '-v', 'error', '-i', AROLL, '-vf', 'scale=72:128:flags=area', '-f', 'rawvideo',
                              '-pix_fmt', 'gray', '-'], capture_output=True).stdout
        fr = np.frombuffer(raw, np.uint8).reshape(-1, 128, 72).astype(np.float32)
        diff = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
        cut = int(np.argmax(diff)) + 1
        if diff[cut - 1] < 5 * max(.2, float(np.median(diff))):
            sys.exit('no clear hard cut found (best guess frame %d): pass --cut K' % cut)
        print('cut detected on frame %d (frame difference %.1f, median %.2f)' % (cut, diff[cut - 1], float(np.median(diff))))
    clip['cut_frames'] = [cut]
json.dump(clip, open('clip.json', 'w'), indent=1)

if not a.no_transcribe:
    try:
        from faster_whisper import WhisperModel
        subprocess.run([FF, '-v', 'error', '-y', '-i', AROLL, '-vn', '-ac', '1', '-ar', '16000', 'work/aroll.wav'], check=True)
        model = WhisperModel('medium.en', compute_type='int8')
        segs, _ = model.transcribe('work/aroll.wav', word_timestamps=True, vad_filter=False, initial_prompt=a.prompt)
        ws = [{'text': w.word.strip(), 'start': round(w.start, 3), 'end': round(w.end, 3)} for s in segs for w in s.words]
        json.dump(ws, open('words.json', 'w'), indent=1)
        print('words: ' + ' '.join('%s@%.2f' % (w['text'], w['start']) for w in ws))
        print('  (the cut is at %.2fs; Whisper word starts can be 0.1 to 0.3s early: confirm onsets on the audio)' % (cut / 30.0))
    except ImportError:
        print('words: faster-whisper is not in this python, words.json not written')

if not a.no_cutout:
    r = subprocess.run([sys.executable, os.path.join('_shared', 'rvm_cut.py'), '.'])
    c = count('assets/subject.webm') if r.returncode == 0 else 0
    print('cutout: %d frames' % c + ('' if c == clip['frames'] else '  !! FRAME MISMATCH'))
    if c == clip['frames']:
        open('assets/.cutout_done', 'w').close()
print('next: prep.py, then look at work/measure.jpg')
