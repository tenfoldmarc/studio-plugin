"""The carousel renderer: carousel.json + a look -> one PNG per slide, a contact sheet, an optional PDF and the
preview page. Used by scripts/carousel.py; nothing here talks to the buyer.

A slide is plain data (see references/slides.md). Text fields take a little markup:
  [[words]]  accent        ((words))  quiet (the look decides: often a smaller serif italic)
  **words**  strong        ~~words~~  struck        `words`  code chip        a new line = a line break
In a headline every line is its own line on the slide, and a line that is all [[...]] or all ((...)) takes that
look as a whole line.
"""
import concurrent.futures
import html
import json
import os
import pathlib
import re
import subprocess
import sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(ENGINE)
STUDIO_SCRIPTS = os.path.join(os.path.dirname(SKILL), 'video-studio', 'scripts')
sys.path.insert(0, STUDIO_SCRIPTS)
import skillenv  # noqa: E402
sys.path.insert(0, ENGINE)
try:
    import stickers as STICKERS  # noqa: E402  the sticker kit (engine/stickers.py)
except ImportError:
    STICKERS = None

SIZES = {'3:4': (1080, 1440), '4:5': (1080, 1350), '1:1': (1080, 1080)}
LAYOUTS = ('hook', 'content', 'statement', 'cta', 'custom')
ARROW = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" '
         'stroke-linejoin="round"><path d="M4 12h15"/><path d="M13 6l6 6-6 6"/></svg>')


# ------------------------------------------------------------------ places
def state_root():
    d = os.path.join(skillenv.state_dir(), 'carousels')
    os.makedirs(d, exist_ok=True)
    return d


def looks_dirs():
    """Saved looks first (the buyer's), then the ones the skill ships."""
    return [os.path.join(state_root(), 'looks'), os.path.join(SKILL, 'looks')]


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-') or 'carousel'


def uri(p):
    return pathlib.Path(os.path.abspath(p)).as_uri()


# ------------------------------------------------------------------ looks
def find_look(name):
    """-> folder of the look called `name` (its folder name or the name in its look.json), or None."""
    want = slug(name)
    for root in looks_dirs():
        if not os.path.isdir(root):
            continue
        for d in sorted(os.listdir(root)):
            folder = os.path.join(root, d)
            meta = read_json(os.path.join(folder, 'look.json'), None)
            if meta is None:
                continue
            if d == want or slug(meta.get('name', '')) == want:
                return folder
    return None


def all_looks():
    out = []
    for i, root in enumerate(looks_dirs()):
        if not os.path.isdir(root):
            continue
        for d in sorted(os.listdir(root)):
            meta = read_json(os.path.join(root, d, 'look.json'), None)
            if meta is not None and not meta.get('retired'):
                base = {}
                if meta.get('extends'):   # a look of their own inherits what it is from the look it builds on
                    bf = find_look(meta['extends'])
                    base = read_json(os.path.join(bf, 'look.json'), {}) if bf else {}
                out.append({'key': d, 'name': meta.get('name', d), 'saved': i == 0, 'folder': os.path.join(root, d),
                            'about': meta.get('about') or base.get('about', ''), 'extends': meta.get('extends'),
                            'kind': meta.get('kind') or base.get('kind', 'type'),
                            'for': meta.get('for') or base.get('for', ['everyone']),
                            'niches': meta.get('niches') or base.get('niches', []),
                            'imageStyle': meta.get('imageStyle') or base.get('imageStyle', '')})
    return out


def load_look(name, seen=None):
    """-> dict(vars, css[list of (folder, text)], decor, fonts[list], folders). Follows "extends" to the base look."""
    folder = name if os.path.isdir(str(name)) else find_look(name)
    if not folder:
        raise SystemExit(f'STATUS look MISSING "{name}". Looks there are: ' + ', '.join(l['name'] for l in all_looks()))
    seen = seen or set()
    if folder in seen:
        raise SystemExit(f'look "{name}" extends itself')
    seen.add(folder)
    meta = read_json(os.path.join(folder, 'look.json'), {})
    base = load_look(meta['extends'], seen) if meta.get('extends') else {'vars': {}, 'css': [], 'decor': '',
                                                                          'fonts': [], 'folders': []}
    look = {'vars': dict(base['vars']), 'css': list(base['css']), 'decor': base['decor'], 'fonts': list(base['fonts']),
            'folders': base['folders'] + [folder], 'name': meta.get('name', os.path.basename(folder)),
            'size': meta.get('size') or base.get('size') or '3:4'}
    look['vars'].update(meta.get('vars', {}))
    for f in meta.get('fonts', []):
        look['fonts'].append(dict(f, _folder=folder))
    css_file = os.path.join(folder, meta.get('css', 'look.css'))
    if os.path.isfile(css_file):
        look['css'].append((folder, open(css_file, encoding='utf-8').read()))
    decor_file = os.path.join(folder, 'decor.html')
    if os.path.isfile(decor_file):
        look['decor'] = open(decor_file, encoding='utf-8').read()
    return look


def font_file(name, near):
    """A font file by name: next to the look, then the carousel fonts, the Studio's fonts, the buyer's fetched fonts."""
    for d in (near, os.path.join(SKILL, 'fonts'), os.path.join(skillenv.SKILL_DIR, 'engine', 'fonts'),
              skillenv.my_fonts_dir()):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def font_faces(look):
    out, missing = [], []
    for f in look['fonts']:
        p = font_file(f['file'], f['_folder'])
        if not p:
            missing.append(f['file'])
            continue
        bits = [f"font-family:'{f['family']}'", f"src:url('{uri(p)}') format('woff2')",
                f"font-weight:{f.get('weight', '400')}", f"font-style:{f.get('style', 'normal')}"]
        if f.get('stretch'):
            bits.append(f"font-stretch:{f['stretch']}")
        out.append('@font-face{' + ';'.join(bits) + ';font-display:block}')
    return '\n'.join(out), missing


def rebase_urls(css, folder):
    """url(assets/x.png) in a look's CSS -> an absolute file address, so assets next to the look load."""
    def fix(m):
        u = m.group(2)
        if re.match(r'^(data:|https?:|file:|#)', u):
            return m.group(0)
        return f"url('{uri(os.path.join(folder, u))}')"
    return re.sub(r"url\((['\"]?)([^'\")]+)\1\)", fix, css)


# ------------------------------------------------------------------ text
INLINE = [
    (re.compile(r'`(.+?)`'), r'<code>\1</code>'),
    (re.compile(r'\[\[(.+?)\]\]'), r'<em class="ac">\1</em>'),
    (re.compile(r'\(\((.+?)\)\)'), r'<span class="q">\1</span>'),
    (re.compile(r'\*\*(.+?)\*\*'), r'<strong>\1</strong>'),
    (re.compile(r'~~(.+?)~~'), r'<s>\1</s>'),
]


def md(text, breaks=True):
    if text is None:
        return ''
    s = html.escape(str(text), quote=False)
    for rx, rep in INLINE:
        s = rx.sub(rep, s)
    return s.replace('\n', '<br>') if breaks else s


def headline(text, cls='hl'):
    if not text:
        return ''
    lines = []
    for raw in str(text).split('\n'):
        raw = raw.strip()
        if not raw:
            continue
        kind = ''
        if re.fullmatch(r'\[\[.+\]\]', raw) and raw.count('[[') == 1:
            kind, raw = ' ac', raw[2:-2]
        elif re.fullmatch(r'\(\(.+\)\)', raw) and raw.count('((') == 1:
            kind, raw = ' q', raw[2:-2]
        lines.append(f'<span class="ln{kind}">{md(raw, False)}</span>')
    return f'<h1 class="{cls}">' + ''.join(lines) + '</h1>'


# ------------------------------------------------------------------ slide parts
def img_src(src, project):
    if not src:
        return ''
    if re.match(r'^(https?:|data:|file:)', src):
        return src
    p = src if os.path.isabs(os.path.expanduser(src)) else os.path.join(project, src)
    return uri(os.path.expanduser(p))


def items_html(items):
    if not items:
        return ''
    if isinstance(items, list):
        items = {'style': 'bullets', 'list': items}
    style = items.get('style', 'bullets')
    lst = items.get('list', [])
    norm = [x if isinstance(x, dict) else {'text': x} for x in lst]
    if style == 'chips':
        return '<div class="items chips">' + ''.join(f'<span class="chip">{md(x.get("text") or x.get("title"))}</span>' for x in norm) + '</div>'
    if style == 'compare':
        one = ' one' if items.get('columns') == 1 or len(norm) <= 2 else ''
        return f'<div class="items compare{one}">' + ''.join(
            f'<div class="pair"><s class="old">{md(x.get("before"))}</s><i class="ar">&rarr;</i>'
            f'<span class="new">{md(x.get("after"))}</span></div>' for x in norm) + '</div>'
    if style == 'versus':
        cols = items.get('columns') or norm[:2]
        out = []
        for i, c in enumerate(cols[:2]):
            rows = ''.join(f'<li>{md(r)}</li>' for r in c.get('list', []))
            out.append(f'<div class="col c{i + 1}"><b class="t">{md(c.get("title"))}</b><ul>{rows}</ul></div>')
        return '<div class="items versus">' + ''.join(out) + '</div>'
    if style == 'grid':
        return '<div class="items grid">' + ''.join(
            f'<div class="card{" hot" if x.get("hot") else ""}">'
            + (f'<span class="tag">{md(x.get("tag"))}</span>' if x.get('tag') else '')
            + (f'<b class="t">{md(x.get("title"))}</b>' if x.get('title') else '')
            + (f'<span class="d">{md(x.get("text"))}</span>' if x.get('text') else '') + '</div>' for x in norm) + '</div>'
    tag = 'ol' if style in ('rows', 'steps') else 'ul'
    out = []
    for n, x in enumerate(norm, 1):
        mark = {'bullets': '<i class="dot"></i>', 'check': '<i class="dot ck">&#10003;</i>',
                'rows': f'<span class="n">{x.get("n", n)}</span>', 'steps': f'<span class="n">{x.get("n", n)}</span>'}.get(style, '<i class="dot"></i>')
        inner = ''
        if x.get('title'):
            inner += f'<b class="t">{md(x["title"])}</b>'
        if x.get('text'):
            inner += f'<span class="d">{md(x["text"])}</span>' if x.get('title') else md(x['text'])
        out.append(f'<li{" class=hot" if x.get("hot") else ""}>{mark}<div class="tx">{inner}</div></li>')
    return f'<{tag} class="items {style}">' + ''.join(out) + f'</{tag}>'


def media_html(m, project):
    if not m:
        return '', ''
    if isinstance(m, str):
        m = {'src': m}
    fit = m.get('fit', 'frame')
    src = img_src(m.get('src'), project)
    focus = f' style="object-position:{html.escape(str(m["focus"]))}"' if m.get('focus') else ''
    if m.get('face'):   # where the face is in the photo ("x,y,w,h" in % of the photo): the render keeps text off it
        focus += f' data-face="{html.escape(str(m["face"]))}"'
    if fit == 'bleed':   # the whole slide; the look decides how much it is dimmed (--bleed-dim) unless "dim" is set
        dim = f' style="--dim:{m["dim"]}"' if m.get('dim') is not None else ''
        return '', f'<div class="bleed"{dim}><img src="{src}" alt=""{focus}></div>'
    if fit == 'half':    # one half (or "share") of the slide, edge to edge; the text takes the other part
        side = m.get('side', 'top') if m.get('side') in ('top', 'bottom', 'left', 'right') else 'top'
        share = float(m.get('share', 0.5))
        return '', (f'<div class="bleed half side-{side}" style="--share:{share}"><img src="{src}" alt=""{focus}>'
                    + (f'<span class="half-cap">{md(m["caption"])}</span>' if m.get('caption') else '') + '</div>')
    if m.get('place') == 'stage':   # standing on the bottom edge of the slide, behind the text (a person cut-out)
        h = m.get('height', '58%')
        h = f'{int(h)}px' if isinstance(h, (int, float)) else h
        side = {'left': 'flex-start', 'right': 'flex-end'}.get(m.get('align', 'center'), 'center')
        return '', f'<figure class="stage-img {fit}" style="height:{h};justify-content:{side}"><img src="{src}" alt=""></figure>'
    cap = f'<figcaption>{md(m["caption"])}</figcaption>' if m.get('caption') else ''
    lab = f'<div class="media-label">{md(m["label"])}</div>' if m.get('label') else ''
    style = ''
    if m.get('height'):
        style = f' style="height:{int(m["height"])}px;flex:0 0 auto"'
    cls = 'framed' if fit == 'frame' else fit   # "frame" is a word looks use for their own decoration
    return f'{lab}<figure class="media {cls}"{style}><img src="{src}" alt=""{focus}>{cap}</figure>', ''


COLLAGES = ('pair', 'trio', 'grid', 'stack', 'strip', 'scatter', 'row')


def photos_html(p, project):
    """Several photos as one block: {"layout": "pair|trio|grid|stack|strip|scatter|row", "frame": "plain|polaroid|tape|card",
    "list": ["assets/a.jpg", {"src": ..., "caption": "...", "rotate": -4, "focus": "50% 30%"}], "height": 640, "place": "middle|bleed"}"""
    if not p:
        return '', ''
    if isinstance(p, list):
        p = {'list': p}
    items = [x if isinstance(x, dict) else {'src': x} for x in p.get('list', [])]
    if not items:
        return '', ''
    layout = p.get('layout') if p.get('layout') in COLLAGES else {1: 'row', 2: 'pair', 3: 'trio'}.get(len(items), 'grid')
    frame = p.get('frame', 'plain')
    cells = []
    for k, x in enumerate(items, 1):
        rot = f'--rot:{float(x["rotate"])}deg;' if x.get('rotate') is not None else ''
        focus = f'object-position:{html.escape(str(x["focus"]))};' if x.get('focus') else ''
        cap = f'<figcaption>{md(x["caption"])}</figcaption>' if x.get('caption') else ''
        cells.append(f'<figure class="ph ph{k} f-{frame}" style="{rot}"><img src="{img_src(x.get("src"), project)}" alt="" '
                     f'style="{focus}">{cap}</figure>')
    style = f' style="height:{int(p["height"])}px;flex:0 0 auto"' if p.get('height') else ''
    block = f'<div class="collage c-{layout} n{len(items)}"{style}>' + ''.join(cells) + '</div>'
    if p.get('place') == 'bleed':
        return '', f'<div class="bleed collage-bleed">{block}</div>'
    return block, ''


def stickers_html(s, ctx):
    """Small decorations placed anywhere on the slide (engine/stickers.py has every kind and its fields)."""
    lst = s.get('stickers') or []
    if not lst or STICKERS is None:
        return ''
    front, back = [], []
    for k in lst:
        try:
            h = STICKERS.render(k, ctx)
        except Exception as e:   # one broken sticker never stops the slide; the check line says which
            h = f'<div class="sticker-error" data-error="{html.escape(str(e))}"></div>'
        (back if k.get('z') == 'back' else front).append(h)
    return ((f'<div class="stickers back">' + ''.join(back) + '</div>' if back else '')
            + (f'<div class="stickers front">' + ''.join(front) + '</div>' if front else ''))


def slide_html(s, i, n, ctx):
    layout = s.get('layout') or ('hook' if i == 1 else 'cta' if i == n else 'content')
    if layout not in LAYOUTS:
        layout = 'content'
    project, prof = ctx['project'], ctx['profile']
    label = s.get('label', '')
    zt, zm, zb = [], [], []
    if label:
        zt.append(f'<div class="label"><i></i><span>{md(label)}</span></div>')
    if s.get('kicker'):
        zt.append(f'<div class="kicker">{md(s["kicker"])}</div>')
    zt.append(headline(s.get('headline'), 'hl' + (' wrap' if s.get('wrap') else '')))
    if s.get('headline') and s.get('rule', True):
        zt.append('<div class="rule"></div>')
    if s.get('sub'):
        zt.append(f'<p class="sub">{md(s["sub"])}</p>')
    media, bleed = media_html(s.get('image'), project)
    place = (s.get('image') or {}).get('place', 'middle') if isinstance(s.get('image'), dict) else 'middle'
    if media and place == 'top':
        zt.insert(0, media)
    if s.get('big'):
        b = s['big'] if isinstance(s['big'], dict) else {'num': s['big']}
        zm.append(f'<div class="big"><span class="num">{md(b.get("num"))}</span>'
                  + (f'<span class="bs">{md(b.get("text"))}</span>' if b.get('text') else '') + '</div>')
    if s.get('quote'):
        q = s['quote'] if isinstance(s['quote'], dict) else {'text': s['quote']}
        zm.append(f'<blockquote class="quote"><p>{md(q.get("text"))}</p>'
                  + (f'<cite>{md(q.get("by"))}</cite>' if q.get('by') else '') + '</blockquote>')
    if media and place == 'middle':
        zm.append(media)
    collage, collage_bleed = photos_html(s.get('photos'), project)
    if collage:
        zm.append(collage)
    bleed += collage_bleed
    zm.append(items_html(s.get('items')))
    if s.get('html'):
        zm.append(s['html'])
    if media and place == 'bottom':
        zb.append(media)
    if s.get('payload'):
        p = s['payload'] if isinstance(s['payload'], dict) else {'text': s['payload']}
        zb.append(f'<div class="payload"><div class="pl-label"><i></i>{md(p.get("label", "Copy this"))}</div>'
                  f'<div class="pl-text">{md(p.get("text"))}</div></div>')
    if s.get('callout'):
        zb.append(f'<div class="callout">{md(s["callout"])}</div>')
    if layout == 'cta' or s.get('keyword'):
        kw = s.get('keyword', '')
        bits = []
        if kw:
            bits.append(f'<div class="cw-pre">{md(s.get("keywordPre", "Comment the word"))}</div>')
            bits.append(f'<div class="kw">{md(kw)}</div>')
        if s.get('keywordPost'):
            bits.append(f'<div class="cw-post">{md(s["keywordPost"])}</div>')
        follow = s.get('follow', f'Follow {prof.get("handle")} for more' if prof.get('handle') else '')
        if follow:
            bits.append(f'<div class="follow">{md(follow)}</div>')
        if bits:
            zb.append('<div class="cta-word">' + ''.join(bits) + '</div>')
    if s.get('note'):
        zb.append(f'<div class="note">{md(s["note"])}</div>')

    def zone(cls, parts):
        parts = [p for p in parts if p]
        return f'<section class="{cls}">' + ''.join(parts) + '</section>' if parts else ''
    body = zone('zt', zt) + zone('zm', zm) + zone('zb', zb)

    handle = md(prof.get('handle', ''))
    av = ctx['avatar']
    avatar = f'<img class="av" src="{av}" alt="">' if av else (
        f'<span class="av initial">{html.escape((prof.get("name") or prof.get("handle") or "?").lstrip("@")[:1].upper())}</span>' if handle else '')
    tick = '<span class="tick">&#10003;</span>' if prof.get('verified') else ''
    swipe_txt = s.get('swipe') or ('End' if i == n else 'Swipe')
    tag = md(s.get('tag', label or ctx.get('tag', '')))
    half_side = re.search(r'bleed half side-(\w+)', bleed)
    share = re.search(r'--share:([0-9.]+)', bleed)   # the text moves with the photo's share, so the slide needs it too
    share_css = f';--share:{share.group(1)}' if half_side and share else ''
    classes = ['slide', f'L-{layout}', f's{i}'] + (['is-first'] if i == 1 else []) + (['is-last'] if i == n else []) + \
        [f'has-{k}' for k in ('zt', 'zm', 'zb') if f'class="{k}"' in body] + \
        [f'has-{k}' for k in ('image', 'photos', 'items', 'payload', 'callout', 'big', 'quote', 'keyword', 'label', 'sub', 'stickers') if s.get(k)] + \
        (['has-stage'] if 'stage-img' in bleed else []) + (['has-bleed'] if 'class="bleed' in bleed else []) + \
        (['has-half', 'half-' + half_side.group(1)] if half_side else []) + \
        [c for c in str(s.get('class', '')).split() if c]
    ghost = f'<div class="ghost">{md(s["ghost"])}</div>' if s.get('ghost') else ''
    return (f'<div class="{" ".join(classes)}" style="--i:{i};--n:{n};--progress:{100 * i / n:.1f}%{share_css}">'
            f'<div class="decor">{ctx["decor"]}</div>{bleed}{ghost}{stickers_html(s, ctx)}'
            f'<div class="chrome top"><span class="tag"><i></i><span>{tag}</span></span>'
            f'<span class="count"><b>{i:02d}</b> / {n:02d}</span>'
            f'<span class="who top-who">{avatar}<span class="hn">{handle}</span>{tick}</span></div>'
            f'<main class="body">{body}</main>'
            f'<div class="chrome bottom"><span class="who">{avatar}<span class="hn">{handle}</span>{tick}</span>'
            f'<span class="foot">{md(ctx.get("footer", ""))}</span>'
            f'<span class="swipe"><span class="st">{md(swipe_txt)}</span><span class="sa">{ARROW}</span></span></div>'
            f'<div class="progress"><i></i></div></div>')


def page(s, i, n, ctx):
    w, h = ctx['size']
    vars_css = ';'.join(f'{k}:{v}' for k, v in ctx['look']['vars'].items())
    look_css = '\n'.join(rebase_urls(t, f) for f, t in ctx['look']['css'])
    return ('<!doctype html><html><head><meta charset="utf-8"><style>'
            f'{ctx["faces"]}\n{ctx["base"]}\n{ctx.get("stickers_css", "")}\n'
            f':root{{--w:{w}px;--h:{h}px;{vars_css}}}\n{look_css}\n'   # the look's vars after the sticker defaults, so they win
            f'{ctx.get("css", "")}\n{s.get("css", "")}</style></head><body>'
            f'{slide_html(s, i, n, ctx)}<script type="application/json" id="qa"></script>'
            f'<script>{ctx["fit"]}</script></body></html>')


# ------------------------------------------------------------------ browser
def browser_path():
    """The headless browser the Studio already downloaded for HyperFrames; remembered in the state folder."""
    rec_file = os.path.join(state_root(), 'browser.json')
    rec = read_json(rec_file, {})
    if rec.get('path') and os.path.isfile(rec['path']):
        return rec['path']
    for sub in (['browser', 'path'], ['browser', 'ensure'], ['browser', 'path']):
        try:
            argv, env = skillenv.hyperframes_command(sub)
            out = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=900).stdout
        except (OSError, subprocess.SubprocessError, SystemExit):
            continue
        for line in reversed(out.splitlines()):
            cand = re.sub(r'\x1b\[[0-9;]*m', '', line).strip().strip('"')
            if cand and os.path.isfile(cand):
                write_json(rec_file, {'path': cand})
                return cand
    return None


def shoot(browser, html_file, png, size, scale):
    w, h = size
    cmd = [browser, '--headless', '--disable-gpu', '--hide-scrollbars', '--allow-file-access-from-files',
           '--no-first-run', '--no-default-browser-check', '--run-all-compositor-stages-before-draw',
           f'--force-device-scale-factor={scale}', f'--window-size={w},{h}', '--virtual-time-budget=8000',
           f'--screenshot={png}', '--dump-dom', uri(html_file)]
    if sys.platform.startswith('linux'):
        cmd.insert(1, '--no-sandbox')
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    m = re.search(r'<script type="application/json" id="qa">(.*?)</script>', r.stdout, re.S)
    qa = {'notes': ['the check did not run']}
    if m and m.group(1).strip():
        try:
            qa = json.loads(html.unescape(m.group(1)))
        except ValueError:
            pass
    if not os.path.isfile(png):
        qa = {'notes': ['NOT RENDERED: ' + (r.stderr.strip().splitlines() or ['unknown error'])[-1]]}
    return qa


# ------------------------------------------------------------------ the whole carousel
def read_json(p, fallback=None):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return fallback


def write_json(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write('\n')


def profile():
    return read_json(os.path.join(state_root(), 'profile.json'), {})


def render(project, only=None, scale=1, pdf=False, look_override=None, out_dir=None, quiet=False):
    """-> list of (index, png, qa). Writes slides/<slug>-NN.png, work/sheet.jpg and preview.html."""
    project = os.path.abspath(project)
    data = read_json(os.path.join(project, 'carousel.json'))
    if not data or not data.get('slides'):
        raise SystemExit('STATUS render FAILED: no slides in carousel.json yet')
    prof = dict(profile(), **(data.get('profile') or {}))
    look = load_look(look_override or data.get('look') or prof.get('defaultLook') or 'horizon')
    size = SIZES.get(data.get('size') or prof.get('size') or look['size'], SIZES['3:4'])
    faces, missing = font_faces(look)
    av = prof.get('avatar')
    ctx = {'project': project, 'profile': prof, 'look': look, 'size': size, 'faces': faces,
           'base': open(os.path.join(ENGINE, 'base.css'), encoding='utf-8').read(),
           'fit': open(os.path.join(ENGINE, 'fit.js'), encoding='utf-8').read(),
           'decor': look['decor'], 'avatar': uri(av) if av and os.path.isfile(av) else '',
           'stickers_css': rebase_urls(open(os.path.join(ENGINE, 'stickers.css'), encoding='utf-8').read(), ENGINE)
           if os.path.isfile(os.path.join(ENGINE, 'stickers.css')) else '',
           'footer': data.get('footer', ''), 'tag': data.get('tag', ''), 'css': data.get('css', '')}
    browser = browser_path()
    if not browser:
        raise SystemExit('STATUS render FAILED: no headless browser. Run the Studio setup check, then '
                         'PY "SK/scripts/prefetch.py" renderer, then try again.')
    name = slug(data.get('slug') or os.path.basename(project))
    out_dir = out_dir or os.path.join(project, 'slides')
    work = os.path.join(project, 'work', 'html')
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    slides = data['slides']
    n = len(slides)
    jobs = []
    for i, s in enumerate(slides, 1):
        if only and i not in only:
            continue
        hf = os.path.join(work, f'{i:02d}.html')
        with open(hf, 'w', encoding='utf-8', newline='\n') as f:
            f.write(page(s, i, n, ctx))
        png = os.path.join(out_dir, f'{name}-{i:02d}.png')
        if os.path.exists(png):
            os.remove(png)   # our own render output, rebuilt from carousel.json
        jobs.append((i, hf, png))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda j: (j[0], j[2], shoot(browser, j[1], j[2], size, scale)), jobs))
    for f in missing:
        results.append((0, '', {'notes': [f'FONT MISSING: {f} (a stand-in face was used)']}))
    pngs = [os.path.join(out_dir, f'{name}-{i:02d}.png') for i in range(1, n + 1)]
    pngs = [p for p in pngs if os.path.isfile(p)]
    if not only:   # the carousel got shorter: slides past the end are our own old renders, not part of it any more
        for p in os.listdir(out_dir):
            m = re.fullmatch(re.escape(name) + r'-(\d+)\.png', p)
            if m and int(m.group(1)) > n:
                os.remove(os.path.join(out_dir, p))
    sheet(pngs, os.path.join(project, 'work', 'sheet.jpg'), ratio=size[1] / size[0])
    preview_page(project, data, prof, [os.path.relpath(p, project) for p in pngs], size)
    if pdf:
        make_pdf(browser, project, pngs, size, os.path.join(project, f'{name}.pdf'))
    return results


def sheet(pngs, out, per_row=5, w=360, ratio=4 / 3):
    if not pngs:
        return
    ff = skillenv.tool('ffmpeg')
    rows = [pngs[i:i + per_row] for i in range(0, len(pngs), per_row)]
    args, filt = [], []
    for r in rows:
        for p in r:
            args += ['-i', p]
    idx = 0
    row_labels = []
    for ri, r in enumerate(rows):
        parts = []
        for _ in r:
            filt.append(f'[{idx}:v]scale={w}:-2,pad={w + 8}:ih+8:4:4:0x808080[v{idx}]')
            parts.append(f'[v{idx}]')
            idx += 1
        while len(parts) < per_row and len(rows) > 1:   # keep every row the same width
            filt.append(f'color=c=0x808080:s={w + 8}x{int(round(w * ratio / 2)) * 2 + 8}:d=1[e{ri}_{len(parts)}]')
            parts.append(f'[e{ri}_{len(parts)}]')
        if len(parts) > 1:
            filt.append(''.join(parts) + f'hstack=inputs={len(parts)}[r{ri}]')
        else:
            filt.append(parts[0] + f'null[r{ri}]')
        row_labels.append(f'[r{ri}]')
    if len(rows) > 1:
        filt.append(''.join(row_labels) + f'vstack=inputs={len(rows)}[out]')
    else:
        filt.append(row_labels[0] + 'null[out]')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run([ff, '-loglevel', 'error', '-y'] + args + ['-filter_complex', ';'.join(filt), '-map', '[out]',
                    '-frames:v', '1', '-q:v', '3', out], check=False)


def make_pdf(browser, project, pngs, size, out):
    """One page per finished slide (the PNGs themselves, so the PDF is exactly what was checked)."""
    w, h = size
    doc = ('<!doctype html><html><head><meta charset="utf-8"><style>'
           f'@page{{size:{w}px {h}px;margin:0}} *{{margin:0;padding:0}} '
           f'img{{display:block;width:{w}px;height:{h}px;break-after:page}}</style></head><body>'
           + ''.join(f'<img src="{uri(p)}">' for p in pngs) + '</body></html>')
    hf = os.path.join(project, 'work', 'html', 'all.html')
    with open(hf, 'w', encoding='utf-8', newline='\n') as f:
        f.write(doc)
    subprocess.run([browser, '--headless', '--disable-gpu', '--allow-file-access-from-files', '--no-pdf-header-footer',
                    '--virtual-time-budget=8000', f'--print-to-pdf={out}', uri(hf)], capture_output=True, timeout=180)


def preview_page(project, data, prof, rel_pngs, size):
    tpl = open(os.path.join(ENGINE, 'preview.html'), encoding='utf-8').read()
    av = prof.get('avatar')
    info = {'title': data.get('title') or os.path.basename(project), 'handle': prof.get('handle', ''),
            'name': prof.get('name', ''), 'avatar': uri(av) if av and os.path.isfile(av) else '',
            'slides': [p.replace(os.sep, '/') for p in rel_pngs], 'ratio': f'{size[0]} / {size[1]}',
            'caption': data.get('caption', ''), 'folder': os.path.join(project, 'slides')}
    with open(os.path.join(project, 'preview.html'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(tpl.replace('/*DATA*/null', json.dumps(info, ensure_ascii=False)))
