#!/usr/bin/env python3
"""Trial reel variations: N finished reels from one edited reel, each one changing ONE thing an Instagram trial reel
can test: the hook, the caption style, the effect set, or the saved style. references/variations.md has the why.

Usage:
  PY variations.py plan "<project>" --count 8 [--change hook,captions,effects,style] [--fresh]
        a proposed mix -> <project>/variations.json, printed in plain words. A variations.json that is already there
        is kept (the buyer may have changed it) unless --fresh. Show the buyer the mix, change it with them, then make.
  PY variations.py make "<project>" [--only <n|id>]
        one working copy per variation in <project>/work/variations/<trial name>/, with its change applied. A new hook
        is cut again from the originals, the reel's fixed and marked words are carried over, any new words are
        transcribed, and the speaker is found again. Prints CHECK lines for what needs you.
  PY variations.py render "<project>" [--only <n|id>] [--redo]
        builds, lints and renders the variations ONE AFTER ANOTHER (never in parallel: a reel render takes the whole
        computer), runs the self-check on each, and copies the finished reels into <project>/trial-reels/ as
        trial-01-<id>.mp4 ... next to what-changed.txt. Run it in the background. A trial already in trial-reels/ is
        skipped unless --redo. Only one make or render runs per project at a time.
  PY variations.py list "<project>"
        the short list for the buyer: each file and what is different in it.

variations.json (the plan writes it; edit it like edl.json):
  {"count": 8, "variations": [
    {"id": "hook-take-2", "change": "hook", "what": "Opens on your other take of the first line", "edl": [...]},
    {"id": "hook-punch-in", "change": "hook", "what": "Opens punched in close on your face", "punch": 1.2},
    {"id": "hook-skip-so", "change": "hook", "what": "Starts on \\"here\\" instead of \\"So\\"", "trim": 0.367},
    {"id": "captions-karaoke", "change": "captions", "what": "Karaoke captions", "caption": "karaoke"},
    {"id": "effects-none", "change": "effects", "what": "No effects", "effects": []},
    {"id": "style-hype", "change": "style", "what": "In your Hype style", "myStyle": "Hype"},
    {"id": "style-fireside", "change": "style", "what": "In the Fireside look", "style": "fireside"}]}
  hook      "edl" (the whole edl, any takes and order), "punch" (zoom on the first part), "trim" (seconds cut off
            the start of the first part)
  captions  "caption": a caption style key, or a custom caption spec (references/replicate.md)
  effects   "effects": the effect keys this trial keeps ([] = none). A key the reel has no slot for yet is made in
            the trial's own folder with fx_new.py / fx_add.py (make prints the commands).
  style     "myStyle": one of the buyer's saved styles, or "style": a built-in overall style key
  any       "plan": fields merged into the trial's plan.json last (a new pinned title for a new opening line)
  "what" is what the buyer reads. Plain words, no em dashes.
Standard library only (plus the scripts it runs).
"""
import copy
import ctypes
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import skillenv  # noqa: E402

FPS = 30
KINDS = ('hook', 'captions', 'effects', 'style')
# caption styles to try, most different from each other first. Bold goes behind the head: only with a cutout.
CAPTION_ORDER = ('karaoke', 'keyword', 'loud-lowercase', 'anchor', 'cool-dude', 'golden-hour', 'outline', 'signature',
                 'terminal', 'spec-sheet', 'weight-shift', 'arcade', 'low-key', 'vanity', 'moodboard', 'cool-girl',
                 'field-notes', 'bubblegum', 'bold')
CAPTION_NAMES = {'arcade': 'Arcade', 'low-key': 'Low Key', 'field-notes': 'Field Notes', 'anchor': 'Anchor',
                 'loud-lowercase': 'Loud Lowercase', 'vanity': 'Vanity', 'bubblegum': 'Bubblegum',
                 'moodboard': 'Moodboard', 'golden-hour': 'Golden Hour', 'spec-sheet': 'Spec Sheet', 'bold': 'Bold',
                 'cool-girl': 'Cool Girl', 'cool-dude': 'Cool Dude', 'karaoke': 'Karaoke', 'signature': 'Signature',
                 'keyword': 'Keyword', 'weight-shift': 'Weight Shift', 'terminal': 'Terminal', 'outline': 'Outline'}
FILLERS = {'so', 'now', 'okay', 'ok', 'um', 'uh', 'alright', 'well', 'and', 'but', 'look', 'hey', 'yeah', 'like',
           'right', 'listen', 'basically', 'actually', 'honestly'}
# what a working copy never gets: renders, checks, the trials themselves, and the effects' own working folders
SKIP_TOP = {'renders', 'snapshots', 'work', 'trial-reels', 'fx', '.transcode-cache', 'node_modules', 'index.html',
            'variations.json'}
# a hook trial gets a new cut, so these are made again in its folder, never copied
REMADE = {os.path.join('assets', 'aroll.mp4'), os.path.join('assets', 'subject.webm'), 'words.json', 'layout.json',
          'segments.json', 'edl.json'}
# the parts of plan.json that are the LOOK of a saved style: a style trial drops them so the other style shows
LOOK_KEYS = ('caption', 'style_key', 'grade', 'css')


def read(path, fallback=None):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(data, fh, indent=1)
        fh.write('\n')


def opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv[:-1] else default


def slug(text):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', str(text).lower())).strip('-')[:40] or 'trial'


def plain(text):
    """what the buyer reads: no em or en dashes"""
    return re.sub(r'\s*[' + chr(0x2014) + chr(0x2013) + r']\s*', ', ', str(text or '')).strip()


def trial_name(i, v):
    return f'trial-{i + 1:02d}-{slug(v.get("id") or v.get("change") or "trial")}'


def bare(text):
    return re.sub(r"[^a-z0-9']", '', str(text).lower())


def dur_of(proj):
    segs = read(os.path.join(proj, 'segments.json'), []) or []
    return sum(s.get('frames', 0) for s in segs) / FPS


# ---------------------------------------------------------------------------------------------------- one at a time

def pid_alive(pid):
    if not pid or int(pid) == os.getpid():
        return False
    if os.name == 'nt':                      # os.kill(pid, 0) would send Ctrl+C on Windows: ask the kernel instead
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259                 # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def lock(proj, what):
    path = os.path.join(proj, 'work', 'variations', '.busy.json')
    held = read(path, {}) or {}
    if pid_alive(held.get('pid')):
        sys.exit(f'STATUS variations BUSY: a "{held.get("what")}" run started {held.get("started")} is still going '
                 '(renders run one after another, never two at once). Wait for it to finish.')
    write(path, {'pid': os.getpid(), 'what': what, 'started': time.strftime('%Y-%m-%d %H:%M:%S')})
    return path


def unlock(path):
    held = read(path, {}) or {}
    if held.get('pid') == os.getpid():
        os.replace(path, path + '.done')


# ---------------------------------------------------------------------------------------------------- the plan

def current_caption(proj, plan):
    """the caption style the reel is built with now ('custom' for a custom spec), from the last build"""
    built = read(os.path.join(proj, 'work', 'build.json'), {}) or {}
    if built.get('caption'):
        return built['caption'], built.get('style')
    c = plan.get('caption')
    return ('custom' if isinstance(c, dict) else c), None


def find_takes(proj, seg):
    """other takes of the line in the first part of the cut: windows of words in each clip's transcript that read
    like it, away from the take already used. -> [(clip, in, out, score)]"""
    want = [bare(w) for w in str(seg.get('line') or '').split() if bare(w)]
    if len(want) < 3:
        return []
    srcs = read(os.path.join(proj, 'sources.json'), {}) or {}
    found = []
    for clip in srcs:
        ws = read(os.path.join(proj, f'words_{clip}.json'), []) or []
        toks = [bare(w.get('text')) for w in ws]
        n = len(want)
        best = []
        for i in range(0, max(0, len(ws) - n + 1)):
            for m in (n - 1, n, n + 1):
                if m < 3 or i + m > len(ws):
                    continue
                r = difflib.SequenceMatcher(None, want, toks[i:i + m]).ratio()
                if r >= .7:
                    best.append((r, i, i + m))
        best.sort(reverse=True)
        taken = []
        for r, a, b in best:
            t0, t1 = ws[a]['start'], ws[b - 1]['end']
            if clip == seg.get('clip') and t0 < seg['out'] and t1 > seg['in']:
                continue                                          # the take already in the reel
            if any(t0 < y and t1 > x for x, y in taken):
                continue
            taken.append((t0, t1))
            found.append((clip, round(max(0.0, t0 - .08), 3), round(t1 + .12, 3), round(r, 2)))
    found.sort(key=lambda f: -f[3])
    return found[:3]


def pools(proj, kinds):
    """every variation that can be proposed without the buyer, kind by kind, best first"""
    plan = read(os.path.join(proj, 'plan.json'), {}) or {}
    edl = read(os.path.join(proj, 'edl.json'), []) or []
    words = read(os.path.join(proj, 'words.json'), []) or []
    has_cut = os.path.isfile(os.path.join(proj, 'assets', 'subject.webm'))
    out = {k: [] for k in KINDS}
    ideas = []
    if 'hook' in kinds and edl:
        first = edl[0]
        for n, (clip, a, b, r) in enumerate(find_takes(proj, first), 2):
            new = copy.deepcopy(edl)
            new[0].update({'clip': clip, 'in': a, 'out': b})
            out['hook'].append({'id': f'hook-take-{n}', 'change': 'hook',
                                'what': 'Opens on your other take of the first line', 'edl': new})
        if len(words) >= 4 and bare(words[0]['text']) in FILLERS:
            t = round((words[1]['start'] - .06) * FPS) / FPS
            if 0 < t < float(first['out']) - float(first['in']) - .5:
                out['hook'].append({'id': f'hook-skip-{bare(words[0]["text"])}', 'change': 'hook',
                                    'what': f'Starts straight on "{words[1]["text"].strip(",.?!")}" instead of '
                                            f'"{words[0]["text"].strip(",.?!")}"', 'trim': round(t, 3)})
        out['hook'].append({'id': 'hook-punch-in', 'change': 'hook', 'what': 'Opens punched in close on your face',
                            'punch': 1.2})
        if len(edl) > 2:
            ideas.append('a different line first (the strongest line of the reel as the opening, then the rest): '
                         'write its "edl" by hand')
        ideas.append('another opening cut from the raw clips (a bolder first sentence the buyer said in another take)')
    if 'captions' in kinds:
        now, _ = current_caption(proj, plan)
        for key in CAPTION_ORDER:
            if key == now or (key == 'bold' and not has_cut):
                continue
            out['captions'].append({'id': f'captions-{key}', 'change': 'captions',
                                    'what': f'{CAPTION_NAMES[key]} captions', 'caption': key})
    if 'effects' in kinds:
        import fxlib
        names = {k: e.get('name', k) for k, e in fxlib.index().items()}
        picks = skillenv.effective_picks(proj)[0]
        where, _ = fxlib.reel_parts(proj)
        # only the effects that play in this reel: a slot outside the parts the buyer allowed is left out of every build
        slots = [s for s in plan.get('slots') or [] if not s.get('off') and s.get('key')
                 and os.path.isfile(os.path.join(proj, *str(s.get('src', '')).split('/')))
                 and fxlib.part_verdict(picks, s['key'], where, float(s['from']), float(s['to']))[0]]
        keys = list(dict.fromkeys(s['key'] for s in slots))
        if keys:
            out['effects'].append({'id': 'effects-none', 'change': 'effects', 'what': 'No effects', 'effects': []})
        if len(keys) > 1:
            for k in keys:
                out['effects'].append({'id': f'effects-only-{k}', 'change': 'effects',
                                       'what': f'Only the {names.get(k, k)} effect', 'effects': [k]})
        in_plan = {s.get('key') for s in plan.get('slots') or []}
        sections = picks.get('effectSections') or {}
        for k in picks.get('effects') or []:
            # an effect the buyer only allows in parts this reel does not have would never show
            allowed = not sections or any(where.get(p) for p in fxlib.PARTS if k in (sections.get(p) or []))
            if k not in in_plan and k in names and allowed:
                out['effects'].append({'id': f'effects-add-{k}', 'change': 'effects',
                                       'what': f'Adds the {names[k]} effect', 'effects': keys + [k]})
    if 'style' in kinds:
        now, _ = skillenv.project_style(proj)
        for s in skillenv.saved_styles():
            if now and s['slug'] == now['slug']:
                continue
            out['style'].append({'id': f'style-{s["slug"]}', 'change': 'style', 'what': f'In your {s["name"]} style',
                                 'myStyle': s['name']})
    return out, ideas


def cmd_plan(proj):
    path = os.path.join(proj, 'variations.json')
    if os.path.isfile(path) and '--fresh' not in sys.argv:
        print(f'variations.json is already there and was kept (add --fresh for a new proposal)')
        return cmd_list(proj, planned=True)
    count = int(opt('--count', '8'))
    kinds = [k.strip() for k in (opt('--change') or ','.join(KINDS)).split(',') if k.strip()]
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        sys.exit(f'--change takes {", ".join(KINDS)} (not {", ".join(bad)})')
    out = os.path.join(proj, 'trial-reels')
    older = [n for n in (os.listdir(out) if os.path.isdir(out) else []) if n.startswith('trial-') or n == 'what-changed.txt']
    if older:                                    # a new plan: the reels of the last one move aside, never deleted
        aside = os.path.join(out, f'earlier-{time.strftime("%Y%m%d-%H%M%S")}')
        os.makedirs(aside, exist_ok=True)
        for n in older:
            os.replace(os.path.join(out, n), os.path.join(aside, n))
        print(f'the trial reels of the last plan moved to {aside}')
    pool, ideas = pools(proj, kinds)
    chosen = []
    while len(chosen) < count and any(pool[k] for k in kinds):
        for k in kinds:
            if pool[k] and len(chosen) < count:
                chosen.append(pool[k].pop(0))
    write(path, {'count': count, 'variations': chosen})
    empty = [k for k in kinds if not any(v['change'] == k for v in chosen)]
    print(f'PLAN {len(chosen)} variations of {count} asked -> {path}')
    cmd_list(proj, planned=True)
    for k in empty:
        why = {'hook': 'no edl.json', 'captions': 'no other caption style fits',
               'effects': 'no effect plays in this reel and no other picked effect fits it',
               'style': 'there is only one saved style'}[k]
        print(f'NONE  {k}: {why}')
    if len(chosen) < count:
        print(f'SHORT only {len(chosen)} can be proposed without the buyer. The rest need a call: another take, a new '
              'line order, an effect to add, another style.')
    for i in ideas:
        print(f'IDEA  hook: {i}')


# ---------------------------------------------------------------------------------------------------- one working copy

def copy_tree(src, dst, hook):
    """the reel project into a trial folder: every file a build needs, never the renders or work"""
    n = 0
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        if rel == '.':
            dirs[:] = [d for d in dirs if d not in SKIP_TOP]
        for f in files:
            r = os.path.normpath(os.path.join(rel, f))
            if rel == '.' and f in SKIP_TOP or hook and r in REMADE:
                continue
            os.makedirs(os.path.join(dst, rel), exist_ok=True)
            shutil.copyfile(os.path.join(root, f), os.path.join(dst, r))
            n += 1
    for d in ('renders', 'work'):
        os.makedirs(os.path.join(dst, d), exist_ok=True)
    return n


def run(cmd, label):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding='utf-8', errors='replace')
    out = (p.stdout or '') + (p.stderr or '')
    if p.returncode != 0:
        print(f'FAILED {label} (exit {p.returncode}):')
        print('\n'.join(out.strip().splitlines()[-25:]))
    return p.returncode == 0, out


class Remap:
    """reel time in the edited reel -> reel time in a trial with another cut, through the source clips"""

    def __init__(self, old, new):
        self.old, self.new = old, new

    def src(self, t):
        for s in self.old:
            a = s['frame'] / FPS
            if a - 1e-6 <= t <= a + s['frames'] / FPS + 1e-6:
                return s, s['in'] + (t - a)
        return None, None

    def where(self, t):
        """-> [(new segment, new time)] for every place the moment at reel time t is in the trial"""
        s, x = self.src(t)
        if s is None:
            return []
        return [(n, round(n['frame'] / FPS + (x - n['in']), 3)) for n in self.new
                if n['clip'] == s['clip'] and n['in'] - 1e-6 <= x <= n['out'] + 1e-6]

    def span(self, a, b, same_look=False):
        """a stretch [a, b] -> its start in the trial when the whole stretch is there in one piece, else None.
        same_look: the part must also be framed exactly as before (an effect render was made from those frames)"""
        for n, t in self.where(a):
            # a part of the cut holds a frame or two more than its source span (frame rounding): allow for it
            if t + (b - a) <= (n['frame'] + n['frames']) / FPS + 2.5 / FPS:
                if same_look:
                    s, _ = self.src(a)
                    if any(round(float(s.get(k, d)), 4) != round(float(n.get(k, d)), 4)
                           for k, d in (('zoom', 1), ('cx', .5), ('cy', .5))):
                        continue
                return t
        return None

    def uncovered(self):
        """stretches of the trial (trial time) that the edited reel never had: new words to transcribe"""
        gaps = []
        for n in self.new:
            have = sorted((max(n['in'], s['in']), min(n['out'], s['out'])) for s in self.old
                          if s['clip'] == n['clip'] and s['in'] < n['out'] and s['out'] > n['in'])
            cur = n['in']
            for a, b in have + [(n['out'], n['out'])]:
                if a - cur > .25:
                    base = n['frame'] / FPS - n['in']
                    gaps.append((round(base + cur, 3), round(base + a, 3)))
                cur = max(cur, b)
        return gaps


def new_edl(proj, v):
    edl = copy.deepcopy(read(os.path.join(proj, 'edl.json'), []) or [])
    if v.get('edl'):
        return copy.deepcopy(v['edl'])
    if not edl:
        sys.exit('edl.json is missing: a hook trial is cut from the reel\'s edl')
    first = edl[0]
    if v.get('trim'):
        first['in'] = round(float(first['in']) + float(v['trim']), 3)
    if v.get('punch'):
        lay = read(os.path.join(proj, 'layout.json'), {}) or {}
        head = lay.get('head') or {}
        z0, z = float(first.get('zoom', 1)), float(first.get('zoom', 1)) * float(v['punch'])
        cx0, cy0 = float(first.get('cx', .5)), float(first.get('cy', .5))
        fx = (head.get('cx', 540) / 1080 - .5) / z0 + cx0          # the face, as a fraction of the source frame
        fy = ((head.get('top', 500) + head.get('chin', 800)) / 2 / 1920 - .5) / z0 + cy0
        tight = {'zoom': round(z, 3), 'cx': round(min(max(fx, 0), 1), 3),
                 'cy': round(min(max(fy + .08 / z, 0), 1), 3)}      # the face a little above the middle
        # only the opening is tight: cut back to the usual framing in the longest pause between 1 and 3 seconds
        d0 = float(first['out']) - float(first['in'])
        ws = [w for w in read(os.path.join(proj, 'words.json'), []) or [] if w['end'] <= d0]
        gaps = [(b['start'] - a['end'], (a['end'] + b['start']) / 2) for a, b in zip(ws, ws[1:])
                if 1.0 <= (a['end'] + b['start']) / 2 <= min(3.0, d0 - 1.0)]
        if gaps:
            t = round(max(gaps, key=lambda g: (g[0], -g[1]))[1] * FPS) / FPS
            rest = {**first, 'id': f'{first.get("id", "open")}-rest', 'in': round(float(first['in']) + t, 3)}
            first.update({**tight, 'out': round(float(first['in']) + t, 3)})
            edl.insert(1, rest)
        else:
            first.update(tight)
    return edl


def make_hook(proj, folder, v, plan, checks):
    """cut the trial again, then carry the reel's words, effects, layers and sounds over to the new times"""
    old_segs = read(os.path.join(proj, 'segments.json'), []) or []
    write(os.path.join(folder, 'edl.json'), new_edl(proj, v))
    py, S = sys.executable, lambda n: os.path.join(HERE, n)   # noqa: E731
    ok, _ = run([py, S('assemble.py'), folder], 'cutting the new opening')
    if not ok:
        return False
    new_segs = read(os.path.join(folder, 'segments.json'), []) or []
    m = Remap(old_segs, new_segs)

    # words: every word the reel had (fixed and marked by hand) moves to its new time; new stretches are transcribed
    old_words = read(os.path.join(proj, 'words.json'), []) or []
    words = []
    for w in old_words:
        for n, t in m.where(w['start']):          # a word said twice in the trial (a teaser opening) is in it twice
            if t + (w['end'] - w['start']) <= (n['frame'] + n['frames']) / FPS + .05:
                words.append({**w, 'start': t, 'end': round(t + w['end'] - w['start'], 3)})
    gaps = m.uncovered()
    if gaps:
        names = ', '.join(dict.fromkeys(w['text'].strip(',.?!') for w in old_words if w.get('e') == 'key'))
        ok, _ = run([py, S('transcribe_cut.py'), folder, names or 'Claude, Claude Code'], 'transcribing the new opening')
        if not ok:
            return False
        fresh = read(os.path.join(folder, 'words.json'), []) or []
        add = [w for w in fresh if any(a - .05 <= (w['start'] + w['end']) / 2 <= b + .05 for a, b in gaps)]
        new_ids = {id(w) for w in add}
        words = sorted(words + add, key=lambda w: w['start'])
        new_idx = [i for i, w in enumerate(words) if id(w) in new_ids]
        import marks
        for i, mk, _ in marks.guess(words):
            if i in new_idx:
                words[i]['e'] = mk
        checks.append('new words from another take, fix any mishearing and the marks in words.json: '
                      + ' '.join(words[i]['text'] for i in new_idx))
    words.sort(key=lambda w: w['start'])
    write(os.path.join(folder, 'words.json'), words)

    # effects, timed layers, sound cues and timed reel motion follow their moment, or leave when it was cut
    for s in plan.get('slots') or []:
        if s.get('off'):
            continue
        t = m.span(float(s['from']), float(s['to']), same_look=True)
        if t is None:
            s['off'] = True
            checks.append(f'the {s.get("key") or s.get("src")} effect sat on a part this opening changed, so it is '
                          'off in this trial. Make it again in this folder (fx_new.py) if it belongs.')
            continue
        t = round(t * FPS) / FPS                  # a slot starts on a frame
        d = round(t - float(s['from']), 4)
        end = sum(n['frames'] for n in new_segs) / FPS
        s['from'], s['to'] = round(t, 4), round(min(float(s['to']) + d, end), 4)
        if 'frame' in s:
            s['frame'] = int(round(s['from'] * FPS))
        if 'frames' in s:
            s['frames'] = min(int(s['frames']), int(round((s['to'] - s['from']) * FPS)))
        for c in s.get('sfx') or []:
            c['at'] = round(float(c['at']) + d, 3)
        if s.get('hide_captions'):
            s['hide_captions'] = [[round(a + d, 3), round(b + d, 3)] for a, b in s['hide_captions']]
    kept = []
    for layer in plan.get('layers') or []:
        if not isinstance(layer, dict) or layer.get('from') is None:
            kept.append(layer)
            continue
        a = float(layer['from'])
        b = float(layer['to']) if layer.get('to') is not None else a
        t = m.span(a, b)
        if t is None:
            checks.append(f'the layer "{layer.get("id", "?")}" was on words this opening cut, so it is left out')
            continue
        layer['from'] = t
        if layer.get('to') is not None:
            layer['to'] = round(t + b - a, 3)
        kept.append(layer)
    if 'layers' in plan:
        plan['layers'] = kept
    for key in ('sounds', 'motion'):
        keep = []
        for c in plan.get(key) or []:
            if not isinstance(c, dict) or c.get('on') or c.get('at') is None:
                keep.append(c)
                continue
            hit = m.where(float(c['at']))
            if hit:
                keep.append({**c, 'at': hit[0][1]})
        if key in plan:
            plan[key] = keep
    if v.get('edl'):
        checks.append('the pinned title is the hook as two short lines: rewrite "title" in this trial\'s plan.json '
                      'if the opening line changed')
    if os.path.isfile(os.path.join(proj, 'assets', 'subject.webm')):
        # the reel has a person cutout (a look behind the speaker): the new cut gets its own, or the look would fall
        # back and the trial would test two things at once
        print(f'      cutting the speaker out of the new cut (slow: about 36s of work per second of reel)', flush=True)
        ok, out = run([py, S('rvm_cut.py'), folder], 'the person cutout of the new cut')
        if not ok:
            return False
        checks += [line.strip() for line in out.splitlines() if line.strip().startswith('head check:')]

    # where the speaker is: the reel's own layout.json (its head box may have been checked and fixed by hand) with
    # its per-part head positions moved to the new cut. Only a clip the reel never used is measured again.
    if derive_layout(proj, folder, old_segs, new_segs, checks):
        return True
    ok, _ = run([py, S('layout.py'), folder], 'finding the speaker in the new cut')
    checks.append(f'the speaker was measured again for this cut: LOOK at "{folder}/work/layout/check.jpg" (the green '
                  'box must run from the top of the head to the chin) and fix layout.json if it does not')
    return ok


def derive_layout(proj, folder, old_segs, new_segs, checks):
    """layout.json for a trial cut from the reel's layout.json. -> False when a part of the new cut comes from a
    clip the reel never used, or a punch-in would bring the chin down to the chest captions (measure it then)."""
    lay = read(os.path.join(proj, 'layout.json'))
    if not isinstance(lay, dict) or lay.get('faceless') or not lay.get('head'):
        return False
    old_per = lay.get('segments') or []
    head, chest = lay['head'], (lay.get('bands') or {}).get('Y_CHEST')

    def eff(c, z):                                   # the crop centre after assemble.py keeps it inside the frame
        return min(max(float(c), .5 / z), 1 - .5 / z) if z > 1 else .5

    def move(y, axis, a, b):
        """a screen coordinate in framing a -> the same point of the source in framing b (9:16 sources)"""
        if y is None:
            return None
        k, size = ('cx', 1080) if axis == 'x' else ('cy', 1920)
        za, zb = float(a.get('zoom', 1)), float(b.get('zoom', 1))
        f = (y / size - .5) / za + eff(a.get(k, .5), za)
        return int(round(((f - eff(b.get(k, .5), zb)) * zb + .5) * size))

    per = []
    for n in new_segs:
        same = [(i, s) for i, s in enumerate(old_segs) if s['clip'] == n['clip']]
        if not same:
            return False
        i, s = next(((i, s) for i, s in same if s['in'] < n['out'] and s['out'] > n['in']), same[0])
        o = old_per[i] if i < len(old_per) else {}
        top, chin, cx = o.get('head_top', head.get('top')), o.get('chin', head.get('chin')), o.get('cx', head.get('cx'))
        per.append({'id': n['id'], 't0': round(n['frame'] / FPS, 3), 't1': round((n['frame'] + n['frames']) / FPS, 3),
                    'head_top': move(top, 'y', s, n), 'chin': move(chin, 'y', s, n), 'cx': move(cx, 'x', s, n)})
    lift = int(lay.get('lift') or 0)
    if chest and any(p['chin'] is not None and p['chin'] - lift > chest - 60 for p in per):
        return False
    lay['segments'] = per
    write(os.path.join(folder, 'layout.json'), lay)
    return True


def cmd_make(proj):
    data = read(os.path.join(proj, 'variations.json'))
    if not isinstance(data, dict) or not data.get('variations'):
        sys.exit('No variations.json in the project: run variations.py plan first.')
    base_plan = read(os.path.join(proj, 'plan.json'), {}) or {}
    _, overall = current_caption(proj, base_plan)
    vdir = os.path.join(proj, 'work', 'variations')
    held = lock(proj, 'make')
    made, failed = 0, []
    try:
        for i, v in enumerate(data['variations']):
            name = trial_name(i, v)
            if not picked(i, v):
                continue
            folder = os.path.join(vdir, name)
            mark = os.path.join(folder, 'variation.json')
            if os.path.isdir(folder):
                if (read(mark, {}) or {}).get('entry') == v and '--redo' not in sys.argv:
                    print(f'KEPT  {name}: made before with the same change')
                    made += 1
                    continue
                old = os.path.join(vdir, '_replaced', f'{name}-{time.strftime("%Y%m%d-%H%M%S")}')
                os.makedirs(os.path.dirname(old), exist_ok=True)
                os.replace(folder, old)                  # never deleted: moved aside
            hook = bool(v.get('edl') or v.get('trim') or v.get('punch'))
            n = copy_tree(proj, folder, hook)
            plan = copy.deepcopy(base_plan)
            checks = []
            if hook and not make_hook(proj, folder, v, plan, checks):
                failed.append(name)
                continue
            if v.get('caption') is not None:
                plan['caption'] = v['caption']
                if not v.get('style') and not v.get('myStyle'):
                    plan['style_key'] = overall          # keep the overall style the reel is in, swap its captions
                if v['caption'] == 'bold' and not os.path.isfile(os.path.join(folder, 'assets', 'subject.webm')):
                    checks.append(f'Bold needs a person cutout: rvm_cut.py "{folder}"')
            if v.get('effects') is not None:
                keep = set(v['effects'])
                have = set()
                for s in plan.get('slots') or []:
                    if s.get('key') and s['key'] not in keep:
                        s['off'] = True
                    elif s.get('key') and not s.get('off'):
                        have.add(s['key'])
                for k in sorted(keep - have):
                    checks.append(f'add the {k} effect in this trial: fx_new.py {k} --project "{folder}" --from <sec> '
                                  f'--to <sec>, then fx_add.py "{folder}" "<slot>" (effects/INDEX.md)')
            if v.get('myStyle'):
                s, many = skillenv.find_style(v['myStyle'])
                if not s:
                    print(f'FAILED {name}: no saved style called "{v["myStyle"]}"'
                          + (' (it could be: ' + ', '.join(x['name'] for x in many) + ')' if many else ''))
                    failed.append(name)
                    continue
                plan['myStyle'] = s['slug']
                for k in LOOK_KEYS:
                    if v.get('caption') is None or k != 'caption':
                        plan.pop(k, None)
                plan['motion'] = [x for x in plan.get('motion') or [] if not (isinstance(x, dict) and x.get('on'))]
                dropped = [x for x in plan.get('layers') or [] if isinstance(x, dict)]
                plan['layers'] = []
                if dropped:
                    checks.append(f'{len(dropped)} layer(s) of the reel\'s own style were left out. Write this reel\'s '
                                  f'graphic elements in {s["name"]} (its style.md, "Graphic elements")')
                checks.append(f'effects that show words were restyled for the old style: look inside every slot and '
                              f'turn off ("off": true) any that does not match {s["name"]}')
            if v.get('style'):
                listed = {x.get('key'): x.get('captionStyle') for x in
                          (read(os.path.join(SK, 'picker', 'data', 'styles.json'), {}) or {}).get('styles', [])}
                if v['style'] not in listed:
                    print(f'FAILED {name}: no built-in overall style "{v["style"]}" ({", ".join(listed)})')
                    failed.append(name)
                    continue
                plan['style_key'] = v['style']
                if v.get('caption') is None:
                    plan['caption'] = listed[v['style']] or 'none'
                if v['style'] in ('chalk-talk', 'show-and-tell') and not os.path.isfile(
                        os.path.join(folder, 'assets', 'subject.webm')):
                    checks.append(f'this look lifts the speaker off the room and needs a person cutout: rvm_cut.py "{folder}"')
                checks.append('write the words this look shows on screen into plan.json "style" (references/styles.md)')
            if isinstance(v.get('plan'), dict):
                plan.update(copy.deepcopy(v['plan']))
            write(os.path.join(folder, 'plan.json'), plan)
            write(mark, {'name': name, 'entry': v, 'made': time.strftime('%Y-%m-%d %H:%M:%S'), 'checks': checks})
            made += 1
            print(f'MADE  {name}: {plain(v.get("what"))}   ({n} files)')
            print(f'      {folder}')
            for c in checks:
                print(f'CHECK {name}: {c}')
    finally:
        unlock(held)
    print(f'MADE {made} of {sum(1 for i, v in enumerate(data["variations"]) if picked(i, v))}'
          + (f'   FAILED: {", ".join(failed)}' if failed else ''))
    if failed:
        sys.exit(1)


# ---------------------------------------------------------------------------------------------------- the queue

def picked(i, v):
    only = opt('--only')
    if not only:
        return True
    want = [x.strip() for x in only.split(',')]
    return str(i + 1) in want or f'{i + 1:02d}' in want or v.get('id') in want or trial_name(i, v) in want


def fingerprint(folder):
    h = hashlib.sha1()
    for n in ('index.html', 'segments.json'):
        try:
            with open(os.path.join(folder, n), 'rb') as fh:
                h.update(fh.read())
        except OSError:
            pass
    return h.hexdigest()


def write_list(proj, data):
    out = os.path.join(proj, 'trial-reels')
    rows = [(trial_name(i, v) + '.mp4', v) for i, v in enumerate(data.get('variations') or [])]
    rows = [(f, v) for f, v in rows if os.path.isfile(os.path.join(out, f))]
    if not rows:
        return None
    w = max(len(f) for f, _ in rows)
    lines = ['Trial reels: the same clips, one thing different in each.', '']
    lines += [f'{f.ljust(w)}   {v.get("change", "").capitalize()}: {plain(v.get("what"))}' for f, v in rows]
    path = os.path.join(out, 'what-changed.txt')
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    return path


def cmd_render(proj):
    data = read(os.path.join(proj, 'variations.json'))
    if not isinstance(data, dict) or not data.get('variations'):
        sys.exit('No variations.json in the project: run variations.py plan, then make.')
    vdir, out = os.path.join(proj, 'work', 'variations'), os.path.join(proj, 'trial-reels')
    os.makedirs(out, exist_ok=True)
    todo = [(i, v) for i, v in enumerate(data['variations']) if picked(i, v)]
    py, S = sys.executable, lambda n: os.path.join(HERE, n)   # noqa: E731
    sec = dur_of(proj)
    slots = any(not s.get('off') for s in (read(os.path.join(proj, 'plan.json'), {}) or {}).get('slots') or [])
    each = sec / 10 * (80 if slots else 45)
    print(f'QUEUE {len(todo)} trial(s), one after another. About {max(1, round(len(todo) * each / 60))} min on an Apple '
          f'Silicon Mac for this {sec:.0f}s reel, longer on Intel and Windows.')
    held = lock(proj, 'render')
    seen, done, failed, t_all = {}, 0, [], time.time()
    try:
        # the reel itself, built fresh in a copy (its own index.html is never touched), so a trial that changes
        # nothing that shows is caught before it renders
        base = os.path.join(vdir, '_reel')
        copy_tree(proj, base, False)
        if run([py, S('build_reel.py'), base], 'building the reel itself for comparison')[0]:
            seen[fingerprint(base)] = 'the reel itself'
        for k, (i, v) in enumerate(todo, 1):
            name = trial_name(i, v)
            folder, final = os.path.join(vdir, name), os.path.join(out, name + '.mp4')
            tag = f'TRIAL {k}/{len(todo)} {name}'
            if not os.path.isfile(os.path.join(folder, 'variation.json')):
                print(f'{tag} FAILED: not made yet (variations.py make)')
                failed.append(name)
                continue
            if os.path.isfile(final) and '--redo' not in sys.argv:
                print(f'{tag} KEPT: already in trial-reels (--redo to render it again)')
                seen.setdefault(fingerprint(folder), name)
                done += 1
                continue
            t0 = time.time()
            print(f'{tag} building', flush=True)
            ok, log = run([py, S('build_reel.py'), folder], 'build')
            for line in log.splitlines():
                if line.startswith('NOTE'):
                    print(f'      {line}')
            if ok:
                ok, log = run([py, S('hf.py'), folder, 'lint'], 'lint')
                if ok and not re.search(r'\b0 errors?\b', log):
                    print('\n'.join(log.strip().splitlines()[-15:]))
                    ok = False
            if not ok:
                failed.append(name)
                print(f'{tag} FAILED at the build')
                continue
            fp = fingerprint(folder)
            if fp in seen:
                print(f'{tag} FAILED: it comes out the same as {seen[fp]}. Change something real in variations.json.')
                failed.append(name)
                continue
            seen[fp] = name
            print(f'{tag} rendering', flush=True)
            ok, log = run([py, S('hf.py'), folder, 'render', '-o', f'renders/{name}.mp4', '--quality', 'high'], 'render')
            rendered = os.path.join(folder, 'renders', name + '.mp4')
            if not ok or not os.path.isfile(rendered):
                failed.append(name)
                print(f'{tag} FAILED at the render')
                continue
            ok, log = run([py, S('frames_check.py'), folder, f'renders/{name}.mp4'], 'self-check')
            sheet = os.path.join(folder, 'work', 'check', name + '.jpg')
            shutil.copyfile(rendered, final)
            done += 1
            write_list(proj, data)
            print(f'{tag} DONE in {time.time() - t0:.0f}s -> {final}')
            print(f'      self-check: LOOK at {sheet}' if os.path.isfile(sheet) else '      self-check: no sheet (see above)')
    finally:
        unlock(held)
    path = write_list(proj, data)
    print(f'STATUS variations {"DONE" if not failed else "INCOMPLETE"} {done} of {len(todo)} in {out} '
          f'({time.time() - t_all:.0f}s)' + (f'   FAILED: {", ".join(failed)}' if failed else ''))
    if path:
        print(f'list: {path}')
    if failed:
        sys.exit(1)


def cmd_list(proj, planned=False):
    data = read(os.path.join(proj, 'variations.json'), {}) or {}
    vs = data.get('variations') or []
    if not vs:
        print('No variations planned yet (variations.py plan).')
        return
    out = os.path.join(proj, 'trial-reels')
    for i, v in enumerate(vs):
        f = trial_name(i, v) + '.mp4'
        state = '' if planned else ('  [ready]' if os.path.isfile(os.path.join(out, f)) else '  [not rendered]')
        print(f'{f:42} {v.get("change", "?"):9} {plain(v.get("what"))}{state}')


def main():
    skillenv.utf8_stdio()
    cmds = {'plan': cmd_plan, 'make': cmd_make, 'render': cmd_render, 'list': cmd_list}
    if len(sys.argv) < 3 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[2])
    if not os.path.isfile(os.path.join(proj, 'plan.json')):
        sys.exit(f'{proj} is not an edited reel yet (no plan.json): edit the reel first, then make its variations.')
    cmds[sys.argv[1]](proj)


if __name__ == '__main__':
    main()
