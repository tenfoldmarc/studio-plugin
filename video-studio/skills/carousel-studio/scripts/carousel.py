#!/usr/bin/env python3
"""Carousel Studio: one command for everything the carousel skill does. Run it with PY (the Studio's own Python).

  PY carousel.py check                                   quiet check: profile, looks, browser. STATUS lines only
  PY carousel.py profile --handle @me [--name "Me"] [--avatar <picture>] [--dir <folder>] [--size 3:4|4:5|1:1]
                         [--verified yes|no] [--look "<default look>"]
  PY carousel.py looks                                   every look: the 3 base looks and the buyer's own
  PY carousel.py preview-looks [--topic "<words>"]       renders the 3 base looks with the buyer's handle, opens them
  PY carousel.py look new "<name>" [--from <look>]       a new look of their own (a folder with look.json/look.css/look.md)
  PY carousel.py look default "<name>"                   the look plain "make a carousel" uses
  PY carousel.py look show "<name>"                      where its files are
  PY carousel.py look rename "<name>" "<new name>"  |  look retire "<name>"  (kept on disk, hidden from the list)
  PY carousel.py new "<title>" [--look "<name>"] [--source <video, link or Studio project>]
                                                         a carousel folder with an empty carousel.json; prints its path
  PY carousel.py render "<carousel folder>" [--only 2,5] [--pdf] [--scale 2] [--look "<name>"] [--no-open]
                                                         PNGs into slides/, a check line per slide, then opens the preview
  PY carousel.py open "<carousel folder>"                opens the swipe preview again
  PY carousel.py transcript "<video, link or Studio project>" [--out "<carousel folder>"]
                                                         what was said, with times (reuses a Studio edit's words.json)
  PY carousel.py frames "<video or Studio project>" --at 3.2,7.5 [--out "<carousel folder>"] [--sharp]
  PY carousel.py frames "<video or Studio project>" --sheet 24 [--out "<carousel folder>"]
                                                         stills from the video (--sheet: a numbered contact sheet to pick from)
  PY carousel.py photos "<files or folders>" ... --out "<carousel folder>"
                                                         the buyer's photos into assets/photos/pNN.jpg (HEIC too), in the
                                                         order given, plus assets/photo-sheet.jpg to pick from
  PY carousel.py faces "<photos>" ... | faces --out "<carousel folder>"
                                                         where each face is ("x,y,w,h" %), for the "face" field and --faces
  PY carousel.py cutout "<picture>" [--out "<file.png>"] [--top 0.55]
                                                         the person cut out of a still, trimmed (--top: head to waist only)

Everything the buyer keeps (profile, own looks, the browser path) lives in <Studio state>/carousels/. Carousels go to
the folder in the profile (default ~/Carousels). Nothing is written into the skill folder. Standard library only.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, 'engine'))
import render as R  # noqa: E402
skillenv = R.skillenv

BASE_LOOKS = ('horizon', 'paper', 'poster')


def say(line):
    print(line, flush=True)


def opt(name, default=None, args=None):
    a = sys.argv if args is None else args
    if name in a:
        i = a.index(name)
        return a[i + 1] if i + 1 < len(a) else default
    return default


def flag(name):
    return name in sys.argv


def positional(n):
    """The n-th argument that is not an option or an option's value (0 = the subcommand)."""
    out, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
            continue
        if a.startswith('--'):
            skip = a not in ('--pdf', '--no-open', '--sharp')
            continue
        out.append(a)
    return out[n] if len(out) > n else None


def prof_file():
    return os.path.join(R.state_root(), 'profile.json')


def carousels_dir(prof=None):
    prof = prof if prof is not None else R.profile()
    return skillenv.path_arg(prof.get('carouselsDir') or '~/Carousels')


def open_path(p):
    try:
        if sys.platform == 'darwin':
            subprocess.Popen(['open', p])
        elif os.name == 'nt':
            os.startfile(p)   # noqa: the Windows way to open a file with its app
        else:
            subprocess.Popen(['xdg-open', p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        say(f'NOTE could not open it by itself. It is here: {p}')


# ------------------------------------------------------------------ check / profile
def cmd_check():
    prof = R.profile()
    if prof.get('handle'):
        say(f'STATUS carousel profile OK handle {prof["handle"]} folder {carousels_dir(prof)}'
            + (' avatar yes' if prof.get('avatar') and os.path.isfile(prof['avatar']) else ' avatar no'))
    else:
        say('STATUS carousel profile MISSING (first carousel: run the carousel setup in SKILL.md)')
    own = [l for l in R.all_looks() if l['saved']]
    default = prof.get('defaultLook')
    say(f'STATUS carousel looks {len(own)} of their own' + (f', default "{default}"' if default else ', no default yet'))
    b = R.browser_path()
    say('STATUS carousel browser OK' if b else
        'STATUS carousel browser MISSING: the slide renderer could not be downloaded (offline?). Tell the buyer, try again when online')


def square_avatar(src):
    out = os.path.join(R.state_root(), 'avatar.jpg')
    ff = skillenv.tool('ffmpeg')
    r = subprocess.run([ff, '-loglevel', 'error', '-y', '-i', src, '-vf',
                        "crop='min(iw,ih)':'min(iw,ih)',scale=400:400", '-frames:v', '1', '-q:v', '2', out],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(out):
        raise SystemExit(f'STATUS avatar FAILED: could not read that picture ({(r.stderr or "").strip()[:200]})')
    return out


def cmd_profile():
    prof = R.profile()
    for key, name in (('handle', '--handle'), ('name', '--name'), ('size', '--size')):
        v = opt(name)
        if v is not None:
            prof[key] = v
    if prof.get('handle') and not prof['handle'].startswith('@'):
        prof['handle'] = '@' + prof['handle']
    if opt('--size') and opt('--size') not in R.SIZES:
        raise SystemExit('size is one of: ' + ', '.join(R.SIZES))
    if opt('--dir'):
        prof['carouselsDir'] = opt('--dir')
    if opt('--verified'):
        prof['verified'] = opt('--verified').lower() in ('yes', 'true', '1', 'y')
    if opt('--look'):
        folder = R.find_look(opt('--look'))
        if not folder:
            raise SystemExit(f'STATUS look MISSING "{opt("--look")}"')
        prof['defaultLook'] = R.read_json(os.path.join(folder, 'look.json'), {}).get('name', opt('--look'))
    if opt('--avatar'):
        src = skillenv.path_arg(opt('--avatar'))
        if not os.path.isfile(src):
            raise SystemExit(f'STATUS avatar FAILED: no file at {src}')
        prof['avatar'] = square_avatar(src)
    prof.setdefault('carouselsDir', '~/Carousels')
    R.write_json(prof_file(), prof)
    say(f'STATUS profile SAVED handle {prof.get("handle", "-")} folder {carousels_dir(prof)} '
        f'look {prof.get("defaultLook", "-")} size {prof.get("size", "3:4")}')


# ------------------------------------------------------------------ looks
def cmd_looks():
    """Every look, one line each: who it suits, photo-led or type-led, niches. Claude picks the setup previews from it."""
    default = R.profile().get('defaultLook', '')
    for l in R.all_looks():
        mark = ' (default)' if R.slug(l['name']) == R.slug(default) else ''
        kind = 'their own' + (f', built on {l["extends"]}' if l.get('extends') else '') if l['saved'] else 'base look'
        say(f'{l["name"]}{mark}  [{kind}; {"needs photos" if l["kind"] == "photo" else "type-led"}; for {"/".join(l["for"])}; '
            f'{", ".join(l["niches"][:6])}]  {l["about"][:160]}')


FALLBACK_SAMPLE = [
    {'layout': 'hook', 'label': 'The starter list', 'headline': '5 things I wish\n[[I knew]]\nbefore I started',
     'sub': 'The short list nobody gave me.'},
    {'label': 'Tip 01', 'headline': 'Start before\n[[you feel ready.]]',
     'sub': 'Ready is a feeling that shows up [[after]] you start, not before.',
     'items': ['Pick the smallest version you can finish **this week.**', 'Show it to **three real people.**',
               'Fix what they actually **tripped on.**']},
    {'headline': 'Want the\n[[full list?]]', 'sub': 'Save this. Then comment the word below.',
     'keyword': 'LIST', 'keywordPost': "and I'll send you all 5."},
]
SAFE_FACE = '30,8,40,34'


def parse_faces(text):
    """--faces "1=30,8,40,34;2=25,10,45,38" -> {1: '30,8,40,34', ...}"""
    out = {}
    for part in (text or '').split(';'):
        if '=' in part:
            k, v = part.split('=', 1)
            if k.strip().isdigit():
                out[int(k)] = v.strip()
    return out


def cmd_preview_looks():
    """The setup preview: the chosen looks, each on its own 3 sample slides, made with the buyer's handle and (for
    the photo-led looks) the buyer's own photos. Opens a gallery page."""
    prof = R.profile()
    looks = R.all_looks()
    want = [w.strip() for w in (opt('--looks') or '').split(',') if w.strip()]
    if want:
        chosen = []
        for w in want:
            hit = next((l for l in looks if R.slug(l['name']) == R.slug(w) or l['key'] == R.slug(w)), None)
            if hit:
                chosen.append(hit)
            else:
                say(f'NOTE no look called "{w}"')
    else:
        chosen = [l for l in looks if not l['saved']]
    stamp = time.strftime('%Y%m%d-%H%M%S')
    root = os.path.join(R.state_root(), 'look-previews', stamp)
    photos = []
    args = []
    for a in sys.argv[2:]:   # everything after --photos up to the next option
        args.append(a)
    if '--photos' in args:
        i = args.index('--photos') + 1
        raw = []
        while i < len(args) and not args[i].startswith('--'):
            raw.append(args[i])
            i += 1
        os.makedirs(os.path.join(root, 'photos'), exist_ok=True)
        for k, src in enumerate(photo_inputs(raw)[:6], 1):
            dst = os.path.join(root, 'photos', f'p{k}.jpg')
            if to_jpeg(src, dst):
                photos.append(dst)
    faces = parse_faces(opt('--faces'))
    shown = []
    for l in chosen:
        if l['kind'] == 'photo' and not photos:
            say(f'NOTE {l["name"]} skipped: it is photo-led and no photos were given (--photos ...)')
            continue
        sample = R.read_json(os.path.join(l['folder'], 'sample.json'), None)
        if sample is None and l.get('extends'):
            bf = R.find_look(l['extends'])
            sample = R.read_json(os.path.join(bf, 'sample.json'), None) if bf else None
        text = json.dumps(sample or FALLBACK_SAMPLE)
        for k in (1, 2, 3):
            p = photos[(k - 1) % len(photos)] if photos else ''
            text = text.replace(f'{{photo{k}}}', p.replace('\\', '/')).replace(f'{{face{k}}}', faces.get(k, SAFE_FACE))
        text = text.replace('{handle}', prof.get('handle') or '@yourhandle')
        if opt('--topic'):
            slides = json.loads(text)
            slides[0]['headline'] = opt('--topic')
            text = json.dumps(slides)
        proj = os.path.join(root, l['key'])
        os.makedirs(proj, exist_ok=True)
        R.write_json(os.path.join(proj, 'carousel.json'), {'title': l['name'], 'slug': l['key'], 'look': l['folder'],
                                                          'slides': json.loads(text),
                                                          'profile': {'handle': prof.get('handle') or '@yourhandle'}})
        res = R.render(proj, quiet=True)
        # their photos are new to the sample: a sticker that lands on a face is dropped and the slide made again
        hit = [i for i, _, q in res if i and any(n.startswith('TEXT OVER THE FACE') for n in q.get('notes', []))]
        if hit:
            cj = R.read_json(os.path.join(proj, 'carousel.json'), {})
            changed = [i for i in hit if cj['slides'][i - 1].pop('stickers', None) is not None]
            if changed:
                R.write_json(os.path.join(proj, 'carousel.json'), cj)
                again = {i: q for i, _, q in R.render(proj, only=changed, quiet=True)}
                res = [(i, p, again.get(i, q)) for i, p, q in res]
        bad = [n for _, _, q in res for n in q.get('notes', []) if not n.startswith(('shrunk', 'picture made', 'moved text off'))]
        if bad:
            say(f'NOTE {l["name"]}: ' + '; '.join(bad))
        pngs = sorted(os.path.join(proj, 'slides', f) for f in os.listdir(os.path.join(proj, 'slides')) if f.endswith('.png'))
        shown.append((l, pngs, os.path.join(proj, 'work', 'sheet.jpg')))
    if not shown:
        raise SystemExit('STATUS looks PREVIEW FAILED: nothing to show')
    sections = ''.join(
        f'<section><h2>{k}. {html_escape(l["name"])}</h2><p>{html_escape(l["about"])}</p><div class="row">'
        + ''.join(f'<img src="{R.uri(p)}">' for p in pngs) + '</div></section>' for k, (l, pngs, _) in enumerate(shown, 1))
    page = ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Pick your carousel look</title><style>*{box-sizing:border-box;margin:0}body{background:#f2f2f0;color:#151515;'
            'font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:32px 16px}'
            '@media(prefers-color-scheme:dark){body{background:#0e0e0e;color:#f2f2f2}}h1{font-size:28px;margin:0 auto 6px;max-width:1180px}'
            '.lead{max-width:1180px;margin:0 auto 28px;opacity:.7}section{max-width:1180px;margin:0 auto 40px}h2{font-size:20px}'
            'section p{opacity:.7;margin:4px 0 14px;max-width:760px}.row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}'
            '.row img{width:100%;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.15)}</style></head><body>'
            '<h1>Pick your carousel look</h1><p class="lead">Each look on three sample slides'
            + (', made with your photos' if photos else '') + '. Tell Claude the number or the name. You can change anything after.</p>'
            + sections + '</body></html>')
    gallery = os.path.join(root, 'looks.html')
    with open(gallery, 'w', encoding='utf-8') as f:
        f.write(page)
    ff = skillenv.tool('ffmpeg')
    sheet = os.path.join(root, 'all-looks.jpg')
    ins = []
    for _, _, s in shown:
        ins += ['-i', s]
    subprocess.run([ff, '-loglevel', 'error', '-y'] + ins + ['-filter_complex',
                    ''.join(f'[{k}:v]' for k in range(len(shown))) + (f'vstack=inputs={len(shown)}' if len(shown) > 1 else 'null'),
                    '-q:v', '3', sheet])
    say(f'STATUS looks PREVIEW {gallery} ({len(shown)} looks: ' + ', '.join(l["name"] for l, _, _ in shown) + f'). Sheet: {sheet}')
    if not flag('--no-open'):
        open_path(gallery)


def html_escape(s):
    import html as _h
    return _h.escape(str(s or ''))


LOOK_MD = """# {name}

What it is, in one plain line per area. Written when the look was built; "Standing notes" grows with every
"always" the buyer says. Read it before every carousel in this look.

- Based on: {base}
- Made from: (their examples / their words / a base look)
- Ground and colour:
- Type:
- Hierarchy (what is loud, what is quiet):
- Layouts it likes:
- Chrome (handle, counter, swipe cue):
- Copy feel (caps or not, length, tone):

## Standing notes
"""


def cmd_look():
    sub = positional(1)
    name = positional(2)
    if sub == 'new':
        if not name:
            raise SystemExit('look new "<name>" [--from <look>]')
        base = opt('--from')
        folder = os.path.join(R.state_root(), 'looks', R.slug(name))
        if os.path.exists(folder):
            raise SystemExit(f'STATUS look EXISTS "{name}" at {folder}')
        os.makedirs(os.path.join(folder, 'assets'))
        meta = {'name': name, 'about': '', 'vars': {}}
        if base:
            bf = R.find_look(base)
            if not bf:
                raise SystemExit(f'STATUS look MISSING "{base}"')
            meta['extends'] = os.path.basename(bf) if bf.startswith(os.path.join(SKILL, 'looks')) else R.read_json(
                os.path.join(bf, 'look.json'), {}).get('name', base)
            css = '/* Changes on top of the base look. Everything in the base can be overridden here. */\n'
        else:
            meta['fonts'] = []
            css = '/* A look of its own: start from engine/base.css classes (see references/looks.md). */\n'
        R.write_json(os.path.join(folder, 'look.json'), meta)
        with open(os.path.join(folder, 'look.css'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(css)
        with open(os.path.join(folder, 'look.md'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(LOOK_MD.format(name=name, base=meta.get('extends', 'nothing (its own look)')))
        say(f'STATUS look NEW "{name}" {folder}')
        return
    folder = R.find_look(name or '')
    if not folder:
        raise SystemExit(f'STATUS look MISSING "{name}". Looks: ' + ', '.join(l['name'] for l in R.all_looks()))
    meta = R.read_json(os.path.join(folder, 'look.json'), {})
    if sub == 'default':
        prof = R.profile()
        prof['defaultLook'] = meta.get('name', name)
        R.write_json(prof_file(), prof)
        say(f'STATUS look DEFAULT "{prof["defaultLook"]}"')
    elif sub == 'show':
        say(f'STATUS look "{meta.get("name")}" {folder}')
        for f in sorted(os.listdir(folder)):
            say(f'  {f}')
        if meta.get('extends'):
            say(f'  built on: {meta["extends"]} ({R.find_look(meta["extends"])})')
    elif sub in ('rename', 'retire'):
        if not folder.startswith(os.path.join(R.state_root(), 'looks')):
            raise SystemExit('the base looks cannot be changed; make a look of their own from one: look new "<name>" --from <look>')
        if sub == 'rename':
            meta['name'] = positional(3) or meta['name']
        else:
            meta['retired'] = True
        R.write_json(os.path.join(folder, 'look.json'), meta)
        say(f'STATUS look {sub.upper()}D "{meta["name"]}"')
    else:
        raise SystemExit(__doc__)


# ------------------------------------------------------------------ carousels
def cmd_new():
    title = positional(1)
    if not title:
        raise SystemExit('new "<title>" [--look "<name>"] [--source <video or project>]')
    prof = R.profile()
    root = carousels_dir(prof)
    base = R.slug(title)[:48].strip('-')
    folder, k = os.path.join(root, base), 2
    while os.path.exists(folder):
        folder, k = os.path.join(root, f'{base}-{k}'), k + 1
    os.makedirs(os.path.join(folder, 'work'))
    os.makedirs(os.path.join(folder, 'assets'))
    look = opt('--look') or prof.get('defaultLook') or 'horizon'
    if not R.find_look(look):
        raise SystemExit(f'STATUS look MISSING "{look}"')
    data = {'title': title, 'slug': os.path.basename(folder), 'look': look, 'caption': '', 'slides': []}
    if opt('--source'):
        data['source'] = opt('--source')
    R.write_json(os.path.join(folder, 'carousel.json'), data)
    say(f'STATUS carousel NEW {folder} look "{look}"')


def cmd_render():
    project = skillenv.path_arg(positional(1) or '')
    if not os.path.isfile(os.path.join(project, 'carousel.json')):
        raise SystemExit(f'STATUS render FAILED: no carousel.json in {project}')
    only = [int(x) for x in opt('--only', '').split(',') if x.strip().isdigit()] or None
    res = R.render(project, only=only, scale=float(opt('--scale', '1')), pdf=flag('--pdf'), look_override=opt('--look'))
    problems = 0
    for i, png, qa in sorted(res, key=lambda r: r[0]):
        notes = qa.get('notes', [])
        hard = [n for n in notes if not n.startswith(('shrunk', 'picture made smaller', 'ROOM TO FILL', 'moved text off'))]
        problems += bool(hard)
        label = f'slide {i:02d}' if i else 'carousel'
        say(f'CHECK {label} ' + ('OK' if not notes else '; '.join(notes)) + (f' (smallest text {qa["minText"]}px)' if qa.get('minText') else ''))
    data = R.read_json(os.path.join(project, 'carousel.json'), {})
    say(f'STATUS render DONE {len(data.get("slides", []))} slides in {os.path.join(project, "slides")}'
        + (f', {problems} with something to fix' if problems else '') + f'. Contact sheet: {os.path.join(project, "work", "sheet.jpg")}')
    if not flag('--no-open') and not problems:
        open_path(os.path.join(project, 'preview.html'))
    elif problems:
        say('NOTE not opened: fix the slides above first (cut words, split the slide), render again')


def cmd_open():
    project = skillenv.path_arg(positional(1) or '')
    p = os.path.join(project, 'preview.html')
    if not os.path.isfile(p):
        raise SystemExit('STATUS open FAILED: render it first')
    open_path(p)
    say(f'STATUS opened {p}')


# ------------------------------------------------------------------ from a video
def resolve_source(src):
    """-> (kind, path). kind: 'project' (a Studio edit folder), 'file' (a video), or a link fetched to a file."""
    p = skillenv.path_arg(src)
    if os.path.isdir(p) and (os.path.isfile(os.path.join(p, 'words.json')) or os.path.isdir(os.path.join(p, 'renders'))):
        return 'project', p
    if os.path.isfile(p):
        return 'file', p
    if re.match(r'^https?://', src):
        r = subprocess.run([sys.executable, os.path.join(skillenv.SKILL_DIR, 'scripts', 'get_example.py'), src, '--name', 'carousel-source'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        m = re.search(r'STATUS example READY (.+)', r.stdout)
        if m:
            return 'file', m.group(1).strip()
        raise SystemExit('STATUS source FAILED: ' + (re.search(r'STATUS example FAILED (.+)', r.stdout).group(1)
                                                     if 'FAILED' in r.stdout else 'could not fetch that link'))
    raise SystemExit(f'STATUS source MISSING: {src} is not a video file, a Studio project folder or a link')


def project_video(p):
    """The clean cut of a Studio edit (no captions burned in), else its newest render."""
    clean = os.path.join(p, 'assets', 'aroll.mp4')
    if os.path.isfile(clean):
        return clean, True
    rd = os.path.join(p, 'renders')
    vids = sorted((os.path.join(rd, f) for f in os.listdir(rd) if f.endswith('.mp4')), key=os.path.getmtime) if os.path.isdir(rd) else []
    if not vids:
        raise SystemExit(f'STATUS source FAILED: no video in {p}')
    return vids[-1], False


def sentences(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r'[.!?]$', w['text']) or (len(cur) > 22 and w['text'].endswith(',')):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [{'start': c[0]['start'], 'end': c[-1]['end'], 'text': ' '.join(x['text'] for x in c).strip()} for c in out]


def cmd_transcript():
    src = positional(1)
    if not src:
        raise SystemExit('transcript "<video, link or Studio project>" [--out "<carousel folder>"]')
    kind, path = resolve_source(src)
    words = None
    if kind == 'project' and os.path.isfile(os.path.join(path, 'words.json')):
        words = R.read_json(os.path.join(path, 'words.json'), [])
        say(f'STATUS transcript FROM the Studio edit (fixed by hand during the edit): {path}')
    else:
        video = project_video(path)[0] if kind == 'project' else path
        from faster_whisper import WhisperModel   # the Studio's own Python has it
        work = skillenv.path_arg(opt('--out')) if opt('--out') else os.path.join(R.state_root(), 'work')
        os.makedirs(os.path.join(work, 'work'), exist_ok=True)
        wav = os.path.join(work, 'work', 'source.wav')
        subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-i', video, '-vn', '-ac', '1', '-ar', '16000', wav], check=True)
        say('STATUS transcript LISTENING (about a quarter of the video length, one time)')
        m = WhisperModel('small.en', device='cpu', compute_type='int8')
        segs, _ = m.transcribe(wav, word_timestamps=True, vad_filter=False)
        words = [{'text': w.word.strip(), 'start': round(w.start, 2), 'end': round(w.end, 2)} for s in segs for w in s.words]
    lines = sentences(words)
    if opt('--out'):
        out = skillenv.path_arg(opt('--out'))
        R.write_json(os.path.join(out, 'work', 'transcript.json'), {'source': src, 'kind': kind, 'sentences': lines, 'words': words})
        say(f'STATUS transcript SAVED {os.path.join(out, "work", "transcript.json")}')
    for s in lines:
        say(f'[{s["start"]:6.1f} - {s["end"]:6.1f}] {s["text"]}')


def probe_len(video):
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', video],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def grab(video, t, out, ff):
    subprocess.run([ff, '-loglevel', 'error', '-y', '-ss', f'{max(0, t):.3f}', '-i', video, '-frames:v', '1', '-q:v', '2', out])
    return os.path.isfile(out)


def cmd_frames():
    src = positional(1)
    if not src:
        raise SystemExit('frames "<video or project>" --at 3.2,7.5 | --sheet 24 [--out "<carousel folder>"] [--sharp]')
    kind, path = resolve_source(src)
    video, clean = project_video(path) if kind == 'project' else (path, True)
    if not clean:
        say('NOTE this edit has no clean cut, so stills come from the finished reel (its captions show). Better: the raw clip.')
    ff = skillenv.tool('ffmpeg')
    out = os.path.join(skillenv.path_arg(opt('--out')), 'assets') if opt('--out') else os.path.join(R.state_root(), 'work', 'frames')
    os.makedirs(out, exist_ok=True)
    length = probe_len(video)
    if opt('--sheet'):
        n = max(4, min(60, int(opt('--sheet'))))
        times = [length * (k + 0.5) / n for k in range(n)]
        files = []
        for k, t in enumerate(times):
            f = os.path.join(out, f'pick-{k + 1:02d}.jpg')
            if grab(video, t, f, ff):
                files.append((k + 1, t, f))
        tile = os.path.join(out, 'pick-sheet.jpg')
        pick_sheet(files, tile)
        say(f'STATUS frames SHEET {tile} ({len(files)} stills, numbered left to right; pick-NN.jpg next to it, times:)')
        say('  ' + ', '.join(f'{k}={t:.1f}s' for k, t, _ in files))
        return
    times = [float(x) for x in (opt('--at') or '').split(',') if x.strip()]
    if not times:
        raise SystemExit('give --at 3.2,7.5 or --sheet 24')
    for t in times:
        f = os.path.join(out, f'frame-{t:.2f}s.jpg')
        if flag('--sharp'):   # the least blurry of 7 stills around that moment (a bigger JPEG = more detail)
            best, best_size = None, -1
            for d in (-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3):
                tmp = os.path.join(out, f'_try{d:+.1f}.jpg')
                if grab(video, t + d, tmp, ff) and os.path.getsize(tmp) > best_size:
                    best, best_size = tmp, os.path.getsize(tmp)
            if best:
                shutil.move(best, f)
            for d in (-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3):
                tmp = os.path.join(out, f'_try{d:+.1f}.jpg')
                if os.path.exists(tmp):
                    os.remove(tmp)
        else:
            grab(video, t, f, ff)
        say(f'STATUS frame {f}' if os.path.isfile(f) else f'STATUS frame FAILED at {t}s')


def pick_sheet(files, out, ratio=(9, 16)):
    """A numbered grid of stills or photos (drawn by the slide browser, so it needs no font support in ffmpeg).
    files: (number, label, path); each cell has the given shape and shows the whole picture inside it."""
    cells = ''.join(f'<figure><img src="{R.uri(f)}"><figcaption><b>{k}</b> {t if isinstance(t, str) else f"{t:.1f}s"}'
                    '</figcaption></figure>' for k, t, f in files)
    page = ('<!doctype html><html><head><meta charset="utf-8"><style>*{margin:0;box-sizing:border-box}'
            'body{width:1800px;background:#111;font:600 26px/1 sans-serif;color:#fff;display:grid;'
            'grid-template-columns:repeat(6,1fr);gap:8px;padding:8px}figure{position:relative;background:#222;border-radius:6px;'
            f'aspect-ratio:{ratio[0]}/{ratio[1]}}}'
            'img{width:100%;height:100%;object-fit:contain;display:block;border-radius:6px}figcaption{position:absolute;left:8px;top:8px;'
            'background:rgba(0,0,0,.75);padding:6px 10px;border-radius:6px}b{color:#FF8E5C;margin-right:6px}'
            '</style></head><body>' + cells + '</body></html>')
    hf = os.path.splitext(out)[0] + '.html'
    with open(hf, 'w', encoding='utf-8') as f:
        f.write(page)
    rows = (len(files) + 5) // 6
    h = 8 + rows * (int((1800 - 56) / 6 * ratio[1] / ratio[0]) + 9)
    png = os.path.splitext(out)[0] + '.png'
    R.shoot(R.browser_path(), hf, png, (1800, h), 1)
    subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-i', png, '-q:v', '3', out])
    for p in (hf, png):
        if os.path.exists(p):
            os.remove(p)


PHOTO_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.avif', '.tif', '.tiff', '.gif', '.bmp')


def photo_inputs(args):
    """Files and folders as given -> photo files, in the order given (a folder's photos by name)."""
    out = []
    for a in args:
        p = skillenv.path_arg(a)
        if os.path.isdir(p):
            out += [os.path.join(p, f) for f in sorted(os.listdir(p), key=str.lower)
                    if f.lower().endswith(PHOTO_EXT) and not f.startswith('.')]
        elif os.path.isfile(p) and p.lower().endswith(PHOTO_EXT):
            out.append(p)
        else:
            say(f'NOTE skipped (not a photo or not found): {a}')
    return out


def to_jpeg(src, dst, longest=2400):
    """Any photo -> a sRGB JPEG no longer than `longest` px, the right way up (phone photos carry a rotation tag).
    HEIC (iPhone): Pillow cannot read it, so a Mac converts with sips and other systems with ffmpeg."""
    from PIL import Image, ImageOps
    tmp = None
    if src.lower().endswith(('.heic', '.heif', '.avif')):
        tmp = dst + '.convert.png'
        if sys.platform == 'darwin':
            subprocess.run(['sips', '-s', 'format', 'png', src, '--out', tmp], capture_output=True)
        if not os.path.isfile(tmp):
            subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-i', src, '-frames:v', '1', tmp],
                           capture_output=True)
        if not os.path.isfile(tmp):
            return None
        src = tmp
    try:
        im = ImageOps.exif_transpose(Image.open(src))
        im = im.convert('RGB')
        im.thumbnail((longest, longest), Image.LANCZOS)
        im.save(dst, 'JPEG', quality=90)
        return im.size
    except OSError:
        return None
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)   # our own temporary conversion


def cmd_photos():
    """photos <files or folders> --out "<carousel folder>" : copy the buyer's photos in, ready for slides, plus a sheet."""
    args, skip = [], False
    for a in sys.argv[2:]:
        if skip:
            skip = False
            continue
        if a.startswith('--'):
            skip = a in ('--out',)
            continue
        args.append(a)
    if not args or not opt('--out'):
        raise SystemExit('photos "<file or folder>" ["<more>" ...] --out "<carousel folder>"')
    project = skillenv.path_arg(opt('--out'))
    folder = os.path.join(project, 'assets', 'photos')
    os.makedirs(folder, exist_ok=True)
    manifest_file = os.path.join(project, 'assets', 'photos.json')
    manifest = R.read_json(manifest_file, [])
    seen = {m['source'] for m in manifest}
    start = len(manifest)
    for src in photo_inputs(args):
        if src in seen:
            continue
        n = len(manifest) + 1
        dst = os.path.join(folder, f'p{n:02d}.jpg')
        size = to_jpeg(src, dst)
        if not size:
            say(f'NOTE could not read {os.path.basename(src)} (damaged, or a format this computer cannot open)')
            continue
        w, h = size
        shape = 'portrait' if h > w * 1.08 else 'landscape' if w > h * 1.08 else 'square'
        manifest.append({'n': n, 'file': os.path.relpath(dst, project).replace(os.sep, '/'), 'source': src,
                         'w': w, 'h': h, 'shape': shape})
    R.write_json(manifest_file, manifest)
    files = [(m['n'], m['shape'], os.path.join(project, m['file'])) for m in manifest]
    sheet = os.path.join(project, 'assets', 'photo-sheet.jpg')
    if files:
        pick_sheet(files, sheet, ratio=(4, 5))
    say(f'STATUS photos {len(manifest) - start} added, {len(manifest)} in this carousel, in the order given '
        f'(assets/photos/p01.jpg ...). Sheet: {sheet}')
    for m in manifest:
        say(f'  p{m["n"]:02d}  {m["shape"]:9} {m["w"]}x{m["h"]}  from {os.path.basename(m["source"])}')


def find_face(src, work):
    """Where the face is in a photo, as 'x,y,w,h' in % of the photo, or None (nobody in it). The person is cut out
    with the Studio's cutout model and the head is read off the silhouette, the same way the reel editor finds it."""
    sys.path.insert(0, os.path.join(skillenv.SKILL_DIR, 'scripts'))
    import layout as L   # the video Studio's head finder
    from PIL import Image
    os.makedirs(work, exist_ok=True)
    matte = os.path.join(work, os.path.splitext(os.path.basename(src))[0] + '-matte.png')
    if not os.path.isfile(matte):
        argv, env = skillenv.hyperframes_command(['remove-background', src, '-o', matte])
        subprocess.run(argv, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if not os.path.isfile(matte):
        return None
    alpha = Image.open(matte).convert('RGBA').getchannel('A')
    w = 270
    h = max(8, round(alpha.size[1] * w / alpha.size[0]))
    L.SW, L.SH, L.S = w, h, 1
    rows, area = L.main_blob(alpha.resize((w, h)))
    if area < 0.02 * w * h:
        return None
    head = L.read_head(rows)
    if not head:
        return None
    x, y = head['left'] / w * 100, head['top'] / h * 100
    fw, fh = head['width'] / w * 100, (head['chin'] - head['top']) / h * 100
    return f'{x:.0f},{y:.0f},{fw:.0f},{fh:.0f}'


def cmd_faces():
    """faces "<photos>" ... | faces --out "<carousel folder>": mark where every face is, for the "face" field."""
    files = [a for a in sys.argv[2:] if not a.startswith('--') and a != opt('--out')]
    project = skillenv.path_arg(opt('--out')) if opt('--out') else None
    manifest_file = os.path.join(project, 'assets', 'photos.json') if project else None
    manifest = R.read_json(manifest_file, []) if manifest_file else []
    if not files and manifest:
        files = [os.path.join(project, m['file']) for m in manifest]
    files = photo_inputs(files) if files else []
    if not files:
        raise SystemExit('faces "<photo>" ["<photo>" ...]  or  faces --out "<carousel folder>" (after photos)')
    work = os.path.join(project, 'work', 'faces') if project else os.path.join(R.state_root(), 'work', 'faces')
    say(f'STATUS faces LOOKING at {len(files)} photos (a few seconds each)')
    found = []
    for k, f in enumerate(files, 1):
        face = find_face(f, work)
        found.append(face)
        for m in manifest:
            if os.path.normpath(os.path.join(project, m['file'])) == os.path.normpath(f):
                m['face'] = face
        say(f'  {k}  {os.path.basename(f)}  ' + (f'face {face}' if face else 'no person found'))
    if manifest_file and manifest:
        R.write_json(manifest_file, manifest)
    say('STATUS faces DONE --faces "' + ';'.join(f'{k}={f}' for k, f in enumerate(found, 1) if f) + '"'
        + ('  (also saved in assets/photos.json)' if manifest_file else ''))


def cmd_cutout():
    src = skillenv.path_arg(positional(1) or '')
    if not os.path.isfile(src):
        raise SystemExit('cutout "<picture>" [--out "<file.png>"] [--top 0.55]')
    out = skillenv.path_arg(opt('--out')) if opt('--out') else os.path.splitext(src)[0] + '-cutout.png'
    argv, env = skillenv.hyperframes_command(['remove-background', src, '-o', out])
    r = subprocess.run(argv, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if not os.path.isfile(out):
        raise SystemExit('STATUS cutout FAILED: ' + (r.stderr or r.stdout).strip()[-300:])
    from PIL import Image   # the Studio's Python has Pillow: trim the empty space around the person
    im = Image.open(out).convert('RGBA')
    box = im.getchannel('A').point(lambda a: 255 if a > 24 else 0).getbbox()
    if box:
        im = im.crop(box)
    top = float(opt('--top', '1'))   # keep only the top part (0.55 = head to about the waist): a closer, stronger cover
    if 0.2 <= top < 1:
        im = im.crop((0, 0, im.size[0], int(im.size[1] * top)))
    im.save(out)
    say(f'STATUS cutout {out} ({im.size[0]}x{im.size[1]}, '
        'trimmed to the person. On a slide: "image": {"src": ..., "fit": "cutout", "place": "stage"})')


def main():
    skillenv.utf8_stdio()
    cmd = positional(0)
    table = {'check': cmd_check, 'profile': cmd_profile, 'looks': cmd_looks, 'preview-looks': cmd_preview_looks,
             'look': cmd_look, 'new': cmd_new, 'render': cmd_render, 'open': cmd_open, 'transcript': cmd_transcript,
             'frames': cmd_frames, 'cutout': cmd_cutout, 'photos': cmd_photos, 'faces': cmd_faces}
    if cmd not in table:
        sys.exit(__doc__)
    table[cmd]()


if __name__ == '__main__':
    main()
