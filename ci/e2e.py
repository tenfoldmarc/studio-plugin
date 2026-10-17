#!/usr/bin/env python3
"""End-to-end test of Claude Creator Studio on one machine, the way a new buyer meets it: the setup starter on a
computer with nothing installed for the Studio, then a named style, one full edit with custom motion, the self
checks, the study of an example, saving the style, and a second reel that picks the style up by itself.

It runs on GitHub's Windows, Intel Mac and Apple Silicon machines (.github/workflows/studio-e2e.yml) and on a Mac
by hand:  python3 ci/e2e.py --state /tmp/somewhere/video-studio  (the folder name must end in video-studio; leave
--state out on a CI machine so the real per-user folder is used, exactly like a buyer).

No footage of anyone ships with this: the test clip is a generated test picture with the computer's own text to
speech as the voice. Prints one line per step and a summary; exits 1 at the first step that fails. Standard library.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(ROOT, 'video-studio', 'skills', 'video-studio')
WIN = platform.system() == 'Windows'
OUT = os.path.abspath(os.environ.get('E2E_OUT') or os.path.join(ROOT, 'ci', 'out'))
LINE = ('Now if you want the link to get all the video effects that Claude can create for you, '
        'just comment video and I will send it to you. It takes one minute.')
T0 = time.time()
RESULTS = []


def opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv[:-1] else default


ENV = dict(os.environ)
if opt('--state'):
    ENV['CLAUDE_PLUGIN_DATA'] = os.path.abspath(opt('--state'))
ENV['PYTHONIOENCODING'] = 'utf-8'


def log(msg):
    print(msg, flush=True)


def run(name, cmd, must=None, allow_fail=False, env=None, timeout=3600):
    """one step: run it, keep its output, check it"""
    log(f'\n##### {name}  [t+{time.time() - T0:.0f}s]\n$ ' + ' '.join(f'"{c}"' if ' ' in str(c) else str(c) for c in cmd))
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding='utf-8', errors='replace',
                           env=env or ENV, timeout=timeout)
        out, code = (p.stdout or '') + (p.stderr or ''), p.returncode
    except (OSError, subprocess.SubprocessError) as e:
        out, code = f'{type(e).__name__}: {e}', -1
    tail = '\n'.join(l for l in out.splitlines() if l.strip())[-6000:]
    log(tail)
    ok = code == 0 and (must is None or re.search(must, out) is not None)
    RESULTS.append({'step': name, 'ok': ok, 'code': code, 'optional': allow_fail})
    log(f'----- {"PASS" if ok else ("FAIL (allowed)" if allow_fail else "FAIL")}: {name} (exit {code}'
        + (f', looked for /{must}/' if must and not ok else '') + ')')
    if not ok and not allow_fail:
        finish(1)
    return out


def finish(code):
    os.makedirs(OUT, exist_ok=True)
    summary = {'os': platform.platform(), 'machine': platform.machine(), 'seconds': round(time.time() - T0),
               'passed': all(r['ok'] or r['optional'] for r in RESULTS), 'steps': RESULTS}
    with open(os.path.join(OUT, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, indent=1)
    log('\n' + '\n'.join(f'{"ok  " if r["ok"] else ("skip" if r["optional"] else "FAIL")}  {r["step"]}' for r in RESULTS))
    log(f'\nRESULT {"PASSED" if summary["passed"] and code == 0 else "FAILED"} in {summary["seconds"]}s on {summary["os"]}')
    sys.exit(code)


def starter(name):
    if WIN:
        return run(name, ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                          os.path.join(SK, 'scripts', 'start.ps1')], must=r'STATUS state ')
    return run(name, ['sh', os.path.join(SK, 'scripts', 'start.sh')], must=r'STATUS state ')


def speech(path):
    """the computer's own voice saying LINE, as a wav or aiff"""
    if WIN:
        ps = ('Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
              f"$s.Rate = 0; $s.SetOutputToWaveFile('{path}'); $s.Speak('{LINE}'); $s.Dispose()")
        run('make the test voice (Windows speech)', ['powershell', '-NoProfile', '-Command', ps])
    else:
        run('make the test voice (macOS say)', ['say', '-o', path, LINE])


def main():
    work = os.path.join(OUT, 'work')
    os.makedirs(work, exist_ok=True)
    home = os.path.expanduser('~')

    # 1. the first run of the setup, as a buyer's Claude runs it, then once more (the every-run check)
    out = starter('setup, first run')
    state = re.search(r'STATUS state (.+?) \(', out).group(1).strip()
    log(f'state folder: {state}')
    rec = json.load(open(os.path.join(state, '.platform.json'), encoding='utf-8'))
    py, ff = rec['python'], rec['ffmpeg']
    if not rec.get('ready'):
        log('setup says not ready')
        finish(1)
    out = starter('setup, second run (styles line)')
    if 'STATUS styles' not in out:
        RESULTS.append({'step': 'setup prints a STATUS styles line', 'ok': False, 'code': 0, 'optional': False})
        finish(1)
    S = lambda n: os.path.join(SK, 'scripts', n)      # noqa: E731

    # 2. the buyer's answers to the two setup questions
    projects = os.path.join(OUT, 'reel-edits') if opt('--state') else os.path.join(home, 'reel-edits-e2e')
    with open(os.path.join(state, 'config.json'), 'w', encoding='utf-8') as fh:
        json.dump({'clipsDir': work, 'projectsDir': projects, 'setupDate': time.strftime('%Y-%m-%d')}, fh)

    # 3. a test clip: a moving test picture with the computer's voice (nobody's footage)
    voice = os.path.join(work, 'voice.wav' if WIN else 'voice.aiff')
    speech(voice)
    clip = os.path.join(work, 'raw clip 1.mp4')            # a space in the name, like real files
    run('make the test clip', [ff, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=1080x1920:r=30',
                               '-i', voice, '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', clip])

    # 4. an example to replicate: the test clip itself stands in for a downloaded reel (links: step 12)
    out = run('example from a file', [py, S('get_example.py'), clip], must=r'STATUS example READY')
    ex = re.search(r'STATUS example READY (.+?)  \(', out).group(1).strip()
    run('study the example (motion strips)', [py, S('study.py'), ex], must=r'video\s+1080x1920')

    # 5. a named style
    run('new named style', [py, S('my_styles.py'), 'new', 'CI Soft Lowercase'], must=r'SAVED')
    run('list styles', [py, S('my_styles.py'), 'list'], must=r'CI Soft Lowercase')

    # 6. one full edit, step by step as SKILL.md lays it out
    proj = os.path.join(projects, 'e2e-reel')
    os.makedirs(proj, exist_ok=True)
    run('1 ingest (first speech model)', [py, S('ingest.py'), proj, clip])
    dur = float(subprocess.run([rec['ffprobe'], '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', clip],
                               capture_output=True, text=True).stdout.strip())
    with open(os.path.join(proj, 'edl.json'), 'w', encoding='utf-8') as fh:
        json.dump([{'id': 'all', 'clip': 'c1', 'in': 0.0, 'out': round(dur - .05, 2), 'zoom': 1.0, 'cx': .5, 'cy': .5,
                    'line': LINE}], fh)
    run('3 assemble', [py, S('assemble.py'), proj])
    run('4 words (second speech model)', [py, S('transcribe_cut.py'), proj, 'Claude, video'])
    run('4 marks', [py, S('marks.py'), proj])
    run('5 layout (renderer + quick cutout model)', [py, S('layout.py'), proj])
    run('6 init in the named style', [py, S('init_project.py'), proj, '--my-style', 'ci soft'], must=r'CI Soft Lowercase')
    plan_path = os.path.join(proj, 'plan.json')
    plan = json.load(open(plan_path, encoding='utf-8'))
    plan['caption'] = {
        'font': 'Inter Tight', 'weight': 700, 'case': 'lower', 'size': 64, 'words': 3, 'chars': 20,
        'color': '#FFFFFF', 'accent': '#F2E36B', 'mark': 'accent', 'mark_scale': 1.5, 'position': 'chest',
        'motion': [{'target': 'self', 'tween': 'from', 'vars': {'filter': 'blur(12px)', 'opacity': 0, 'duration': .1}},
                   {'target': '.w', 'tween': 'from', 'vars': {'yPercent': 40, 'duration': .2, 'stagger': .04}}],
        'mark_motion': {'tween': 'fromTo', 'from': {'scale': 1.4}, 'vars': {'scale': 1, 'duration': .22, 'ease': 'back.out(3)'}}}
    plan['layers'] = [{'id': 'tag', 'anchor': 'top', 'from': .3, 'to': 2.5,
                       'html': "<div class='tg'><span class='ch'>E</span><span class='ch'>2</span><span class='ch'>E</span></div>",
                       'css': ".tg{display:inline-block;font:800 54px 'Inter Tight';color:#111;background:#F2E36B;padding:10px 26px;border-radius:14px}.tg .ch{display:inline-block}",
                       'motion': [{'target': 'self', 'tween': 'from', 'vars': {'scale': 0, 'duration': .4, 'ease': 'elastic.out(1, 0.5)'}},
                                  {'target': '.ch', 'tween': 'from', 'at': .15, 'vars': {'y': 30, 'opacity': 0, 'stagger': .05, 'duration': .2}}]}]
    plan['motion'] = [{'on': 'marks', 'target': 'footage', 'tween': 'to',
                       'vars': {'scale': 1.05, 'duration': .12, 'yoyo': True, 'repeat': 1, 'transformOrigin': '50% 35%'}}]
    json.dump(plan, open(plan_path, 'w', encoding='utf-8'), indent=1)
    run('8 build with the safe guide', [py, S('build_reel.py'), proj, '--safe'], must=r'saved style "CI Soft Lowercase"')
    run('8 lint', [py, S('hf.py'), proj, 'lint'], must=r'0 errors')
    run('8 snapshot (renderer browser)', [py, S('hf.py'), proj, 'snapshot', '--at', '0.2,1.5,3.0', '--no-end',
                                          '--describe', 'false'])
    run('9 clean build', [py, S('build_reel.py'), proj], must=r'saved style')
    run('9 render', [py, S('hf.py'), proj, 'render', '-o', 'renders/e2e-reel-v1.mp4', '--quality', 'high'])
    run('9 self-check', [py, S('frames_check.py'), proj, 'renders/e2e-reel-v1.mp4'])
    run('9 cuts check + phone copy', [py, S('check_cuts.py'), proj, 'renders/e2e-reel-v1.mp4', '--phone'], must=r'audio')
    run('side by side with the example', [py, S('side_by_side.py'), ex, proj, 'renders/e2e-reel-v1.mp4'])

    # 7. save the dialed-in style; a second reel uses it as the default without being told
    run('save the style from the reel', [py, S('my_styles.py'), 'save', 'CI Soft Lowercase', '--from-project', proj],
        must=r'UPDATED')
    proj2 = os.path.join(projects, 'e2e-reel-2')
    os.makedirs(proj2, exist_ok=True)
    for n in ('assets', 'words.json', 'layout.json', 'segments.json'):
        src = os.path.join(proj, n)
        (shutil.copytree if os.path.isdir(src) else shutil.copyfile)(src, os.path.join(proj2, n))
    run('second reel: init (default style)', [py, S('init_project.py'), proj2], must=r'the default style')
    run('second reel: build', [py, S('build_reel.py'), proj2], must=r'saved style "CI Soft Lowercase" \(the default style\)')
    if 'blur(12px)' not in open(os.path.join(proj2, 'index.html'), encoding='utf-8').read():
        RESULTS.append({'step': 'second reel carries the style motion', 'ok': False, 'code': 0, 'optional': False})
        finish(1)
    run('second reel: lint', [py, S('hf.py'), proj2, 'lint'], must=r'0 errors')

    # 8. the rest of the style commands
    run('styles: duplicate', [py, S('my_styles.py'), 'duplicate', 'ci soft', 'CI Copy'], must=r'COPIED')
    run('styles: default', [py, S('my_styles.py'), 'default', 'CI Copy'], must=r'DEFAULT')
    run('styles: rename', [py, S('my_styles.py'), 'rename', 'CI Copy', 'CI Renamed'], must=r'RENAMED')
    run('styles: retire', [py, S('my_styles.py'), 'retire', 'CI Renamed'], must=r'RETIRED')
    run('styles: list', [py, S('my_styles.py'), 'list'], must=r'CI Soft Lowercase')
    starter('setup, with a style saved')

    # 9. a link to a public post (sites often refuse cloud machines, so this one may fail without failing the test)
    run('example from a link (allowed to fail on a cloud machine)',
        [py, S('get_example.py'), opt('--link') or 'https://www.youtube.com/watch?v=jNQXAC9IVRw'],   # "Me at the zoo"
        must=r'STATUS example READY', allow_fail=True, timeout=900)

    # keep what a person should look at
    keep = os.path.join(OUT, 'look')
    os.makedirs(keep, exist_ok=True)
    for src in (os.path.join(proj, 'renders', 'e2e-reel-v1-phone.mp4'), os.path.join(proj, 'snapshots', 'contact-sheet.jpg'),
                os.path.join(proj, 'work', 'check', 'e2e-reel-v1.jpg'), os.path.join(proj, 'work', 'layout', 'check.jpg')):
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(keep, os.path.basename(src)))
    cmp_dir = os.path.join(proj, 'work', 'compare')
    for n in (os.listdir(cmp_dir) if os.path.isdir(cmp_dir) else []):
        if n.endswith('.jpg'):
            shutil.copyfile(os.path.join(cmp_dir, n), os.path.join(keep, n))
    exdir = os.path.join(state, 'examples', re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.splitext(os.path.basename(ex))[0]))
    for n in (os.listdir(exdir) if os.path.isdir(exdir) else []):
        if n.startswith('motion_01'):
            shutil.copyfile(os.path.join(exdir, n), os.path.join(keep, n))
    finish(0)


if __name__ == '__main__':
    main()
