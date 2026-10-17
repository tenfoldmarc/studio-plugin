#!/usr/bin/env python3
"""Download everything the first edit needs, at setup, so the buyer's first reel is not spent waiting on downloads.

Usage:  PY prefetch.py            run it (in the background: it takes minutes, the buyer keeps talking to you)
        PY prefetch.py --again    check every part again, also the ones marked done
        PY prefetch.py --status   one line per part: DONE, RUNNING, FAILED or NOT STARTED, and a total line

What it gets, one time each (about 3 GB in all, how long depends on their connection):
  speech      the two speech models (about 0.5 GB and 1.4 GB): the transcript of the raw clips and of the cut
  renderer    HyperFrames (about 0.4 GB) and the browser it draws and records frames with (about 0.1 to 0.2 GB),
              by building and rendering a one-second test page
  cutout      the quick person cutout model (about 170 MB), by cutting out one test frame
  matting     the clean cutout (about 105 MB, setup.py --matting): almost every effect and the behind-the-speaker looks
The parts run side by side (the renderer before the cutout, which needs it installed). A part that is already there takes a second. Running it twice is harmless, and a part
that failed is simply tried again next time (or at the first edit, which downloads whatever is still missing).
State: <state folder>/prefetch.json, the full output in <state folder>/prefetch.log.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402

PARTS = ('speech', 'renderer', 'cutout', 'matting')
WHAT = {'speech': 'speech models', 'renderer': 'renderer and its browser', 'cutout': 'quick cutout model',
        'matting': 'clean cutout'}
LOCK = threading.Lock()
PAGE = '''<!doctype html>
<html lang="en" data-resolution="portrait">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>*{margin:0;padding:0}html,body{width:1080px;height:1920px;background:#111;overflow:hidden}
#root{position:relative;width:1080px;height:1920px}#t{position:absolute;top:880px;width:1080px;text-align:center;
font:800 96px 'Inter Tight',sans-serif;color:#fff}</style></head>
<body><div id="root" data-composition-id="main" data-start="0" data-duration="1.000" data-width="1080" data-height="1920">
<div id="t">ready</div></div>
<script>const tl = gsap.timeline({ paused: true });
tl.from('#t', {opacity: 0, y: 40, duration: .4}, 0.1);
tl.set({}, {}, 1.000);
window.__timelines["main"] = tl;</script></body></html>
'''


def state_file():
    return os.path.join(skillenv.state_dir(), 'prefetch.json')


def read_state():
    try:
        with open(state_file(), encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def mark(part, status, note=''):
    with LOCK:
        st = read_state()
        st.setdefault('parts', {})[part] = {'status': status, 'note': note, 'at': datetime.datetime.now().isoformat(timespec='seconds')}
        st['pid'] = os.getpid()
        with open(state_file(), 'w', encoding='utf-8') as fh:
            json.dump(st, fh, indent=1)
        print(f'STATUS prefetch {part} {status}' + (f': {note}' if note else ''), flush=True)


def logged(cmd, cwd=None, env=None, timeout=3600):
    """run one command, its output appended to prefetch.log; -> exit code"""
    with LOCK:
        log = open(os.path.join(skillenv.state_dir(), 'prefetch.log'), 'a', encoding='utf-8')
        log.write(f'\n$ {" ".join(str(c) for c in cmd)}\n')
        log.flush()
    try:
        return subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                              timeout=timeout).returncode
    except (OSError, subprocess.SubprocessError) as e:
        log.write(f'{type(e).__name__}: {e}\n')
        return -1
    finally:
        log.close()


def speech():
    code = logged([sys.executable, '-c',
                   "from faster_whisper import WhisperModel\n"
                   "for m in ('small.en', 'medium.en'):\n"
                   "    WhisperModel(m, device='cpu', compute_type='int8')\n"
                   "    print('ready', m, flush=True)\n"])
    return code == 0, '' if code == 0 else 'the speech models did not download'


def work_dir():
    d = os.path.join(skillenv.state_dir(), 'prefetch-work')
    os.makedirs(os.path.join(d, 'renders'), exist_ok=True)
    return d


def renderer():
    d = work_dir()
    tpl = os.path.join(skillenv.SKILL_DIR, 'engine', 'template')
    for n in ('hyperframes.json', 'package.json'):
        shutil.copyfile(os.path.join(tpl, n), os.path.join(d, n))
    fonts = os.path.join(d, 'assets', 'fonts')
    if not os.path.isdir(fonts):
        shutil.copytree(os.path.join(skillenv.SKILL_DIR, 'engine', 'fonts'), fonts)
    with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(PAGE)
    argv, env = skillenv.hyperframes_command(['render', '-o', 'renders/ready.mp4'])
    code = logged(argv, cwd=d, env=env)
    if code != 0 or not os.path.isfile(os.path.join(d, 'renders', 'ready.mp4')):
        return False, 'the test render did not finish'
    argv, env = skillenv.hyperframes_command(['browser', 'ensure'])     # the browser snapshots use, if it is another
    logged(argv, cwd=d, env=env)
    return True, ''


def cutout():
    d = work_dir()
    clip = os.path.join(d, 'person.mp4')
    ff = skillenv.tool('ffmpeg')
    # one short test clip (a grey shape on a plain background) is enough to make the cutout fetch its model
    logged([ff, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=0x8a8a8a:s=360x640:d=0.2:r=10',
            '-vf', 'drawbox=x=120:y=160:w=120:h=320:color=0x30302a:t=fill', '-pix_fmt', 'yuv420p', clip])
    argv, env = skillenv.hyperframes_command(['remove-background', 'person.mp4', '-o', 'person.webm'])
    code = logged(argv, cwd=d, env=env)
    return code == 0, '' if code == 0 else 'the cutout model did not download'


def matting():
    code = logged([sys.executable, os.path.join(HERE, 'setup.py'), '--matting'])
    model = os.path.join(skillenv.models_dir(), 'rvm_resnet50_fp32.onnx')
    ok = code == 0 and os.path.isfile(model)
    return ok, '' if ok else 'the clean cutout did not download'


def status():
    st = read_state()
    parts = st.get('parts') or {}
    alive = False
    pid = st.get('pid')
    if pid:
        try:
            os.kill(int(pid), 0)
            alive = True
        except (OSError, ValueError):
            alive = False
    for p in PARTS:
        s = (parts.get(p) or {}).get('status', 'NOT STARTED')
        if s == 'RUNNING' and not alive:
            s = 'STOPPED'
        print(f'STATUS prefetch {p} {s}  ({WHAT[p]})')
    done = all((parts.get(p) or {}).get('status') == 'DONE' for p in PARTS)
    running = alive and any((parts.get(p) or {}).get('status') == 'RUNNING' for p in PARTS)
    print('STATUS prefetch ' + ('DONE: the first edit downloads nothing' if done else
                                'RUNNING: still downloading' if running else
                                'INCOMPLETE: the first edit downloads what is missing, or run prefetch.py again'))


def main():
    skillenv.utf8_stdio()
    if '--status' in sys.argv:
        status()
        return
    if not skillenv.load().get('ready'):
        sys.exit('Run the setup check first (start.sh / setup.py): it records Python, Node and ffmpeg for this computer.')
    t0 = time.time()
    jobs = {'speech': speech, 'renderer': renderer, 'cutout': cutout, 'matting': matting}
    done = read_state().get('parts') or {}
    results = {}

    def one(part):
        mark(part, 'RUNNING')
        try:
            ok, why = jobs[part]()
        except Exception as e:                 # a part that breaks never stops the others
            ok, why = False, f'{type(e).__name__}: {e}'
        results[part] = ok
        mark(part, 'DONE' if ok else 'FAILED', why)

    todo = [p for p in PARTS if (done.get(p) or {}).get('status') != 'DONE' or '--again' in sys.argv]
    for p in PARTS:
        if p not in todo:
            print(f'STATUS prefetch {p} DONE (already there)', flush=True)
            results[p] = True
    # renderer and cutout both start HyperFrames: two first-time npx installs at once trip over each other (seen on an
    # Intel Mac), so those two run one after the other in one thread; speech and matting run beside them
    def chain(parts):
        for p in parts:
            one(p)

    hf = [p for p in ('renderer', 'cutout') if p in todo]
    threads = [threading.Thread(target=one, args=(p,)) for p in todo if p not in hf]
    if hf:
        threads.append(threading.Thread(target=chain, args=(hf,)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = all(results.values())
    print(f'STATUS prefetch {"DONE" if ok else "INCOMPLETE"} in {time.time() - t0:.0f}s'
          + ('' if ok else ': ' + ', '.join(WHAT[p] for p, r in results.items() if not r) + ' missing. The first edit '
             'downloads them, or run prefetch.py again.'), flush=True)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
