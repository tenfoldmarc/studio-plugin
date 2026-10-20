#!/usr/bin/env python3
"""End-to-end test of Creator Studio on one machine, the way a new buyer meets it: the setup starter on a
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


for _s in (sys.stdout, sys.stderr):                  # a Windows console is cp1252: the renderer prints symbols
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


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
    run('prefetch every download at setup', [py, S('prefetch.py')], must=r'STATUS prefetch DONE in')
    run('prefetch status', [py, S('prefetch.py'), '--status'], must=r'DONE: the first edit downloads nothing')

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

    # 7b. one of the new effects, inside the reel: OpenCV installed per effect, a process-pool bake, render, added to
    # the reel (Code Scan runs without a person in shot, so the test picture is enough)
    run('effect: install its packages (OpenCV)', [py, S('setup.py'), '--fx', 'code-scan'], must=r'effect packages OK')
    run('effect: make the slot', [py, S('fx_new.py'), 'code-scan', '--project', proj, '--from', '1.0', '--to', '5.0',
                                  '--no-cutout'], must=r'slot ready')
    slot = os.path.join(proj, 'fx', 'code-scan')
    R = S('fx_run.py')
    run('effect: build', [py, R, slot, 'build.py'])
    run('effect: bake (process pool)', [py, R, slot, 'bake.py'])
    run('effect: lint', [py, R, slot, 'hf', 'lint'], must=r'0 errors')
    run('effect: render', [py, R, slot, 'hf', 'render', '--video-frame-format', 'png'])
    run('effect: check', [py, R, slot, 'post.py'], must=r'frames: aroll (\d+), render \1\b')
    run('effect: add to the reel', [py, S('fx_add.py'), proj, slot])
    run('reel with the effect: build', [py, S('build_reel.py'), proj], must=r'slots=1')
    run('reel with the effect: lint', [py, S('hf.py'), proj, 'lint'], must=r'0 errors')
    run('reel with the effect: render', [py, S('hf.py'), proj, 'render', '-o', 'renders/e2e-reel-v2.mp4', '--quality', 'high'])

    # 7c. trial reel variations: a mix proposed for 8, then 3 made (a new opening cut, other captions, no effects)
    # and rendered one after another into one folder with what-changed.txt
    V = S('variations.py')
    run('variations: propose 8', [py, V, 'plan', proj, '--count', '8', '--fresh'], must=r'PLAN 8 variations of 8')
    out = run('variations: propose 3', [py, V, 'plan', proj, '--count', '3', '--change', 'hook,captions,effects',
                                        '--fresh'], must=r'PLAN 3 variations of 3')
    for kind in ('hook', 'captions', 'effects'):
        if not re.search(rf'trial-0\d-\S+\.mp4\s+{kind}\s', out):
            RESULTS.append({'step': f'variations: the mix has a {kind} trial', 'ok': False, 'code': 0, 'optional': False})
            finish(1)
    run('variations: make', [py, V, 'make', proj], must=r'MADE 3 of 3')
    run('variations: render one after another', [py, V, 'render', proj], must=r'STATUS variations DONE 3 of 3',
        timeout=5400)
    trials = os.path.join(proj, 'trial-reels')
    made = sorted(n for n in os.listdir(trials) if n.endswith('.mp4'))
    sizes = {}
    for n in made:
        d = float(subprocess.run([rec['ffprobe'], '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                  os.path.join(trials, n)], capture_output=True, text=True).stdout.strip() or 0)
        with open(os.path.join(trials, n), 'rb') as fh:
            sizes[n] = (round(d, 2), hash(fh.read()))
        log(f'{n}  {d:.2f}s')
    listed = open(os.path.join(trials, 'what-changed.txt'), encoding='utf-8').read()
    # every trial is its own video (2.2.0): no two speeds alike and none 1.0, and each finished trial is its own cut
    # played at its own speed. Not "three different lengths": a hook trial changes the cut too, so a shorter cut at one
    # speed can land on the same length as the full cut at another (it did, on a CI voice).
    own_speed = True
    speeds = []
    for n in made:
        name = n[:-4]
        entry = json.load(open(os.path.join(proj, 'work', 'variations', name, 'variation.json'), encoding='utf-8'))['entry']
        sp = float((entry.get('unique') or {}).get('speed', 1))
        speeds.append(sp)
        pre = os.path.join(proj, 'work', 'variations', name, 'renders', name + '.mp4')      # the render before its own speed
        d0 = float(subprocess.run([rec['ffprobe'], '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', pre],
                                  capture_output=True, text=True).stdout.strip() or 0)
        log(f'{n}  cut {d0:.2f}s at {sp:g}x -> {sizes[n][0]:.2f}s (expected {d0 / sp:.2f}s)')
        own_speed = own_speed and abs(d0 / sp - sizes[n][0]) <= .1
    ok = (len(made) == 3 and [n[:9] for n in made] == ['trial-01-', 'trial-02-', 'trial-03-']
          and all(d > 3 for d, _ in sizes.values()) and len({h for _, h in sizes.values()}) == 3
          and len(set(speeds)) == 3 and all(abs(s - 1) > 1e-6 for s in speeds) and own_speed
          and 'its own speed, framing and colour' in listed
          and all(n in listed for n in made) and chr(0x2014) not in listed)
    RESULTS.append({'step': 'variations: 3 distinct reels and the list', 'ok': ok, 'code': 0, 'optional': False})
    log(f'----- {"PASS" if ok else "FAIL"}: 3 distinct trial reels in one folder\n{listed}')
    if not ok:
        finish(1)
    run('variations: list', [py, V, 'list', proj], must=r'trial-03-\S+\.mp4 .*x speed, framed .*\[ready\]')
    # the buyer posted trial 2: it is never rendered again, and a fresh plan keeps it
    run('variations: mark trial 2 posted', [py, V, 'posted', proj, '2'], must=r'POSTED trial-02-')
    run('variations: a posted trial is never rendered again', [py, V, 'render', proj, '--only', '2', '--redo'],
        must=r'POSTED: kept exactly as it is')

    # 7d. posting: no Zernio key on a CI machine, so only the parts that need none. A plan for the trial reels skips
    # the posted trial 2 and leaves every caption for Claude to write. Before the fresh plan below: that one moves
    # the finished trials into trial-reels/earlier-<date>/
    P = S('post.py')
    out = run('posting: check without a key (exits 1)', [py, P, 'check'], allow_fail=True)
    ok = 'STATUS posting NO KEY' in out and 'Traceback' not in out
    RESULTS.append({'step': 'posting: no key says so plainly', 'ok': ok, 'code': 0, 'optional': False})
    if not ok:
        finish(1)
    posting = os.path.join(proj, 'posting.json')
    run('posting: a plan for the trial reels', [py, P, 'new', posting, trials, '--platforms', 'instagram,tiktok',
                                                '--trial', '--every', '5m', '--force'],
        must=r'SKIPPED trial-02-.*\n(.*\n)*STATUS new WRITTEN .*: 2 post')
    pj = json.load(open(posting, encoding='utf-8'))
    ok = (pj['defaults'] == {'platforms': ['instagram', 'tiktok'], 'trial': True, 'graduation': 'manual'}
          and [p['when'] for p in pj['posts']] == ['now', '5m'] and all(p['caption'] == 'WRITE ME' for p in pj['posts'])
          and all(os.path.isfile(os.path.join(proj, p['file'])) for p in pj['posts']))
    RESULTS.append({'step': 'posting: the plan file', 'ok': ok, 'code': 0, 'optional': False})
    log(f'----- {"PASS" if ok else "FAIL"}: posting plan\n{json.dumps(pj, indent=1)}')
    if not ok:
        finish(1)
    run('variations: a fresh plan keeps the posted trial', [py, V, 'plan', proj, '--count', '2', '--change', 'captions',
                                                           '--fresh'], must=r'KEPT  1 posted trial')

    # 8. the rest of the style commands
    run('styles: duplicate', [py, S('my_styles.py'), 'duplicate', 'ci soft', 'CI Copy'], must=r'COPIED')
    run('styles: default', [py, S('my_styles.py'), 'default', 'CI Copy'], must=r'DEFAULT')
    run('styles: rename', [py, S('my_styles.py'), 'rename', 'CI Copy', 'CI Renamed'], must=r'RENAMED')
    run('styles: retire', [py, S('my_styles.py'), 'retire', 'CI Renamed'], must=r'RETIRED')
    run('styles: list', [py, S('my_styles.py'), 'list'], must=r'CI Soft Lowercase')
    starter('setup, with a style saved')

    # 8b. carousels: the setup a buyer meets on their first carousel, the 3 base looks, a look of their own, then a
    # carousel from the reel above (transcript, stills, every kind of slide), rendered to PNGs and a PDF
    CS = os.path.join(ROOT, 'video-studio', 'skills', 'carousel-studio', 'scripts', 'carousel.py')
    carousels = os.path.join(OUT, 'carousels')
    run('carousel: check before setup', [py, CS, 'check'], must=r'STATUS carousel profile MISSING[\s\S]*browser OK')
    run('carousel: profile', [py, CS, 'profile', '--handle', 'e2e_test', '--name', 'E2E', '--dir', carousels],
        must=r'STATUS profile SAVED handle @e2e_test')
    run('carousel: the 3 base looks', [py, CS, 'looks'], must=r'Horizon[\s\S]*Paper[\s\S]*Poster')
    run('carousel: preview the 3 looks', [py, CS, 'preview-looks', '--no-open'], must=r'STATUS looks PREVIEW')
    run('carousel: a look of their own', [py, CS, 'look', 'new', 'CI Paper Blue', '--from', 'paper'], must=r'STATUS look NEW')
    blue = os.path.join(state, 'carousels', 'looks', 'ci-paper-blue', 'look.json')
    meta = json.load(open(blue, encoding='utf-8'))
    meta['vars'] = {'--accent': '#2F6BFF'}
    json.dump(meta, open(blue, 'w', encoding='utf-8'))
    run('carousel: make it the default', [py, CS, 'look', 'default', 'CI Paper Blue'], must=r'DEFAULT "CI Paper Blue"')
    out = run('carousel: new, from the reel', [py, CS, 'new', 'E2E from the reel', '--source', proj],
              must=r'STATUS carousel NEW .* look "CI Paper Blue"')
    cdir = re.search(r'STATUS carousel NEW (.+?) look ', out).group(1).strip()
    run('carousel: transcript from the edit', [py, CS, 'transcript', proj, '--out', cdir], must=r'FROM the Studio edit')
    run('carousel: still sheet', [py, CS, 'frames', proj, '--sheet', '6', '--out', cdir], must=r'STATUS frames SHEET')
    run('carousel: one still', [py, CS, 'frames', proj, '--at', '1.0', '--out', cdir], must=r'STATUS frame .*frame-1.00s.jpg')
    run('carousel: the buyer\'s photos in', [py, CS, 'photos', os.path.join(cdir, 'assets', 'frame-1.00s.jpg'), '--out', cdir],
        must=r'STATUS photos 1 added')
    run('carousel: find faces (the test picture has nobody in it)', [py, CS, 'faces', '--out', cdir],
        must=r'STATUS faces DONE')
    run('carousel: setup preview with their photos', [py, CS, 'preview-looks', '--photos',
        os.path.join(cdir, 'assets', 'photos', 'p01.jpg'), '--no-open'], must=r'STATUS looks PREVIEW .*looks\.html')
    cj = os.path.join(cdir, 'carousel.json')
    data = json.load(open(cj, encoding='utf-8'))
    data['slides'] = [
        {'layout': 'hook', 'label': 'E2E', 'headline': 'Every kind\n[[of slide]]\n((in one carousel))', 'note': 'Swipe'},
        {'label': 'List', 'headline': 'Rows and [[a callout]]', 'items': {'style': 'rows', 'list': [
            {'title': 'One', 'text': 'First row.'}, {'title': 'Two', 'text': 'Second row.'}]}, 'callout': 'A punchline.'},
        {'label': 'Picture', 'headline': 'A still from [[the reel]]', 'image': {'src': 'assets/frame-1.00s.jpg', 'height': 520}},
        {'label': 'Keep', 'headline': 'Copy [[this]]', 'payload': {'label': 'Paste this', 'text': 'A short prompt to copy.'},
         'items': {'style': 'compare', 'list': [{'before': 'Old', 'after': 'New'}]}},
        {'headline': 'Want [[it?]]', 'keyword': 'E2E', 'keywordPost': 'and the test passes.'}]
    json.dump(data, open(cj, 'w', encoding='utf-8'), indent=1)
    out = run('carousel: render with the PDF', [py, CS, 'render', cdir, '--pdf', '--no-open'], must=r'STATUS render DONE 5 slides')
    pngs = sorted(n for n in os.listdir(os.path.join(cdir, 'slides')) if n.endswith('.png'))
    dims = [subprocess.run([rec['ffprobe'], '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                            '-of', 'csv=p=0', os.path.join(cdir, 'slides', n)], capture_output=True, text=True).stdout.strip()
            for n in pngs]
    ok = (len(pngs) == 5 and set(dims) == {'1080,1440'} and 'with something to fix' not in out
          and os.path.isfile(os.path.join(cdir, 'preview.html')) and os.path.isfile(os.path.join(cdir, 'work', 'sheet.jpg'))
          and any(n.endswith('.pdf') for n in os.listdir(cdir)))
    RESULTS.append({'step': 'carousel: 5 clean 1080x1440 slides, preview, sheet and PDF', 'ok': ok, 'code': 0, 'optional': False})
    log(f'----- {"PASS" if ok else "FAIL"}: carousel files {pngs} {dims}')
    if not ok:
        finish(1)
    run('carousel: one slide again in a base look', [py, CS, 'render', cdir, '--only', '2', '--look', 'horizon', '--no-open'],
        must=r'CHECK slide 02 ')
    run('carousel: cut out the person (allowed to fail: the test picture has nobody in it)',
        [py, CS, 'cutout', os.path.join(cdir, 'assets', 'frame-1.00s.jpg')], must=r'STATUS cutout', allow_fail=True)
    run('carousel: check after setup', [py, CS, 'check'], must=r'profile OK handle @e2e_test[\s\S]*default "CI Paper Blue"')

    # 9. a link to a public post (sites often refuse cloud machines, so this one may fail without failing the test)
    run('example from a link (allowed to fail on a cloud machine)',
        [py, S('get_example.py'), opt('--link') or 'https://www.youtube.com/watch?v=jNQXAC9IVRw'],   # "Me at the zoo"
        must=r'STATUS example READY', allow_fail=True, timeout=900)

    # keep what a person should look at
    keep = os.path.join(OUT, 'look')
    os.makedirs(keep, exist_ok=True)
    trials = os.path.join(proj, 'trial-reels')
    for root, _, files in (os.walk(trials) if os.path.isdir(trials) else []):    # earlier-<date>/ holds the last plan's reels
        for n in files:
            shutil.copyfile(os.path.join(root, n), os.path.join(keep, n))
    vdir = os.path.join(proj, 'work', 'variations')
    for n in (os.listdir(vdir) if os.path.isdir(vdir) else []):
        sheet = os.path.join(vdir, n, 'work', 'check', n + '.jpg')
        if os.path.isfile(sheet):
            shutil.copyfile(sheet, os.path.join(keep, 'check-' + n + '.jpg'))
    for src in (os.path.join(proj, 'renders', 'e2e-reel-v1-phone.mp4'), os.path.join(proj, 'renders', 'e2e-reel-v2.mp4'), os.path.join(proj, 'snapshots', 'contact-sheet.jpg'),
                os.path.join(proj, 'work', 'check', 'e2e-reel-v1.jpg'), os.path.join(proj, 'work', 'layout', 'check.jpg')):
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(keep, os.path.basename(src)))
    for src, name in ((os.path.join(cdir, 'work', 'sheet.jpg'), 'carousel-sheet.jpg'),
                      (os.path.join(state, 'carousels', 'look-previews', 'the-3-looks.jpg'), 'carousel-3-looks.jpg')):
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(keep, name))
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
