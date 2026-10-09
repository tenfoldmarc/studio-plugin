"""Card designs for the headline wall: sizes, CSS and HTML. Shared by prep.py (measures + lays out) and build.py
(writes the page). No clip-specific values in here.

Kinds: news, post, dark, search, video, clip, quote, mail, chat.  Variants used for hero cards: news_h (no filler
bars), video_h (no source row), dark_h (smaller type).
A headline is plain text with ONE [marked phrase]: the phrase the yellow highlighter swipes.
"""
INK, CREAM = '#14161C', '#FFF8EF'

# font key -> (file in assets/fonts, css family, css weight, css style)
FONTS = {
    'serif':  ('DMSerifDisplay-400-normal.woff2', "'DM Serif Display'", 400, 'normal'),
    'inter5': ('Inter-500-normal.woff2', "'Inter'", 500, 'normal'),
    'inter6': ('Inter-600-normal.woff2', "'Inter'", 600, 'normal'),
    'tight8': ('InterTight-800-normal.woff2', "'Inter Tight'", 800, 'normal'),
    'iserif': ('InstrumentSerif-400-italic.woff2', "'Instrument Serif'", 400, 'italic'),
}

# w = widest the card may be, min_w = narrowest (cards shrink to their text), padx = side padding,
# size / lh / ls = headline type, top / bot = fixed chrome above / below the headline (px, incl. padding).
SPEC = {
    'news':    dict(w=310, min_w=236, padx=24, font='serif',  size=44,   lh=1.02, ls=-.010, top=65,  bot=65),
    'news_h':  dict(w=300, min_w=236, padx=24, font='serif',  size=44,   lh=1.02, ls=-.010, top=63,  bot=24),
    'post':    dict(w=312, min_w=250, padx=22, font='inter5', size=28.5, lh=1.20, ls=-.015, top=78,  bot=58),
    'dark':    dict(w=290, min_w=200, padx=24, font='tight8', size=45,   lh=1.00, ls=-.030, top=49,  bot=26),
    'dark_h':  dict(w=296, min_w=200, padx=22, font='tight8', size=39,   lh=1.00, ls=-.030, top=49,  bot=26),
    'search':  dict(w=380, min_w=200, padx=0,  font='inter5', size=25,   lh=1.00, ls=-.010, top=0,   bot=0),
    'video':   dict(w=256, min_w=230, padx=18, font='inter6', size=23.5, lh=1.16, ls=-.020, top=16,  bot=61),
    'video_h': dict(w=244, min_w=230, padx=18, font='inter6', size=23.5, lh=1.16, ls=-.020, top=16,  bot=27),
    'clip':    dict(w=318, min_w=250, padx=20, font='serif',  size=41,   lh=1.00, ls=0.000, top=58,  bot=81),
    'quote':   dict(w=300, min_w=220, padx=24, font='iserif', size=52,   lh=0.98, ls=-.010, top=26,  bot=66),
    'mail':    dict(w=312, min_w=250, padx=20, font='inter6', size=27,   lh=1.15, ls=-.020, top=75,  bot=75),
    'chat':    dict(w=300, min_w=170, padx=20, font='inter5', size=27,   lh=1.15, ls=-.015, top=14,  bot=72),
}
SEARCH_CHROME = 92          # magnifier + gaps + caret + side padding of the search pill
SEARCH_H = 66
LAYER_SCALE = {'far': .56, 'mid': .80, 'near': 1.0}


def base(kind):
    return kind.split('_')[0]


def text_w(kind, w):
    """width available to the headline inside a card of width w"""
    return w - 2 * SPEC[kind]['padx']


def card_h(kind, nlines, w):
    s = SPEC[kind]
    if base(kind) == 'search':
        return SEARCH_H
    h = s['top'] + s['bot'] + nlines * s['size'] * s['lh']
    if base(kind) == 'video':
        h += (w - 28) * 9 / 16       # 16:9 thumbnail inside 14px side padding
    return h


def plain(text):
    return text.replace('[', '').replace(']', '')


def mark(line):
    """[phrase] -> highlighter span"""
    out, i = '', 0
    while True:
        a = line.find('[', i)
        if a < 0:
            return out + line[i:]
        b = line.find(']', a)
        out += line[i:a] + f'<span class="hl"><i class="mk"></i><b class="tx">{line[a + 1:b]}</b></span>'
        i = b + 1


AV = '<span class="av"></span>'
ICONS = ('<svg class="ic" viewBox="0 0 24 24"><path d="M12 20s-7-4.4-7-9.6A3.9 3.9 0 0 1 12 8a3.9 3.9 0 0 1 7 2.4C19 15.6 12 20 12 20z"/></svg>'
         '<svg class="ic" viewBox="0 0 24 24"><path d="M5 6h14a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 17h-7l-4.5 3.2V17H5a1.5 1.5 0 0 1-1.5-1.5v-8A1.5 1.5 0 0 1 5 6z"/></svg>'
         '<svg class="ic" viewBox="0 0 24 24"><path d="M4 12.5 20 5l-5.2 15-3-6.3z"/></svg>')
MAG = '<svg class="mag" viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6.2"/><path d="M15.2 15.2 20.5 20.5"/></svg>'
PLAY = '<span class="play"><svg viewBox="0 0 24 24"><path d="M8.5 5.5v13l11-6.5z"/></svg></span>'
ZIG = ','.join(f'{100 - k * 100 / 26:.2f}% calc(100% - {0 if k % 2 == 0 else 7}px)' for k in range(27))


def body(kind, lines, src):
    """HTML of one card. lines = the headline already broken into lines (prep.py does the breaking)."""
    t = '<br>'.join(mark(ln) for ln in lines)
    k = base(kind)
    hero = kind.endswith('_h')
    if k == 'news':
        bars = '' if hero else '<div class="bar"></div><div class="bar" style="width:64%"></div>'
        return (f'<div class="k news{" nb" if hero else ""}"><span class="tape"></span><div class="row">{AV}<span class="kick">{src}</span></div>'
                f'<div class="h serif">{t}</div>{bars}</div>')
    if k == 'post':
        return (f'<div class="k post"><div class="row">{AV}<div><div class="nm">{src}</div><div class="bar sub"></div></div></div>'
                f'<div class="h">{t}</div><div class="icons">{ICONS}</div></div>')
    if k == 'dark':
        return f'<div class="k dark{" sm" if hero else ""}"><div class="kick mono">{src}</div><div class="h">{t}</div></div>'
    if k == 'search':
        return f'<div class="k search">{MAG}<span class="h">{t}</span><span class="caret"></span></div>'
    if k == 'video':
        row = '' if hero else f'<div class="row">{AV}<span class="kick">{src}</span></div>'
        return f'<div class="k video{" nb" if hero else ""}"><div class="h">{t}</div><div class="thumb">{PLAY}</div>{row}</div>'
    if k == 'clip':
        return (f'<div class="k clip"><div class="mast">{src}</div><div class="h serif">{t}</div>'
                f'<div class="cols"><div><div class="bar"></div><div class="bar"></div><div class="bar" style="width:70%"></div></div>'
                f'<div><div class="bar"></div><div class="bar"></div><div class="bar" style="width:52%"></div></div></div></div>')
    if k == 'quote':
        return (f'<div class="k quote"><span class="tape"></span><div class="h">{t}</div>'
                f'<div class="row">{AV}<span class="kick">{src}</span></div></div>')
    if k == 'mail':
        return (f'<div class="k mail"><div class="row">{AV}<div><div class="nm">{src}</div><div class="bar sub"></div></div></div>'
                f'<div class="h">{t}</div><div class="bar"></div><div class="bar" style="width:78%"></div>'
                f'<div class="bar" style="width:46%"></div></div>')
    if k == 'chat':
        return f'<div class="k chat"><div class="bub b1 h">{t}</div><div class="bub b2">{src}</div></div>'
    raise ValueError(kind)


def css(accent):
    S = SPEC
    return f'''
.c{{position:absolute}}
.ci{{position:relative;width:100%}}
.k{{position:relative;width:100%;color:{INK};font-family:'Inter';font-weight:500}}
.h{{white-space:nowrap}}
.c.near .k{{box-shadow:0 20px 44px rgba(0,0,0,.46),0 4px 10px rgba(0,0,0,.30)}}
.c.mid .k{{box-shadow:0 14px 30px rgba(0,0,0,.44),0 3px 8px rgba(0,0,0,.28)}}
.c.far .k{{box-shadow:0 12px 24px rgba(0,0,0,.5)}}
.row{{display:flex;align-items:center;gap:10px}}
.av{{flex:none;width:28px;height:28px;border-radius:50%;background:linear-gradient(145deg,#D4D6DB,#A9ADB6)}}
.kick{{font-family:'Inter';font-weight:600;font-size:14px;line-height:17px;letter-spacing:.09em;text-transform:uppercase;color:#7A7E88;white-space:nowrap}}
.mono{{font-family:'JetBrains Mono';font-weight:500;letter-spacing:.06em}}
.nm{{font-weight:600;font-size:19px;line-height:23px;letter-spacing:-.01em;white-space:nowrap}}
.bar{{height:7px;border-radius:4px;background:rgba(20,22,28,.13);margin-top:9px}}
.bar.sub{{width:74px;height:6px;margin-top:6px}}
.serif{{font-family:'DM Serif Display';font-weight:400}}
.hl{{position:relative;display:inline-block;white-space:nowrap}}
.mk{{position:absolute;left:-.1em;right:-.1em;top:.1em;bottom:.03em;background:{accent};border-radius:.1em .3em .14em .26em;
  transform-origin:0 50%}}
.tx{{position:relative;font-weight:inherit;font-style:inherit}}
.tape{{position:absolute;left:50%;top:-13px;width:88px;height:26px;margin-left:-44px;background:rgba(255,255,255,.62);
  box-shadow:0 1px 3px rgba(0,0,0,.18);transform:rotate(-3deg)}}

.news{{background:{CREAM};border-radius:5px;padding:24px {S['news']['padx']}px 26px}}
.news .h{{font-size:{S['news']['size']}px;line-height:{S['news']['lh']};letter-spacing:{S['news']['ls']}em;margin:13px 0 16px}}
.news.nb{{padding:22px {S['news_h']['padx']}px 24px}} .news.nb .h{{margin-bottom:0}}
.post{{background:#fff;border-radius:22px;padding:20px {S['post']['padx']}px 18px}}
.post .av,.mail .av{{width:44px;height:44px}}
.post .h{{font-weight:500;font-size:{S['post']['size']}px;line-height:{S['post']['lh']};letter-spacing:{S['post']['ls']}em;margin-top:14px}}
.icons{{display:flex;gap:26px;margin-top:15px;height:25px}}
.ic{{width:25px;height:25px;fill:none;stroke:#B4B8C1;stroke-width:1.9;stroke-linejoin:round;stroke-linecap:round}}
.dark{{background:{INK};border-radius:20px;padding:20px {S['dark']['padx']}px 24px;color:{CREAM};border:1px solid rgba(255,255,255,.09)}}
.dark .kick{{color:#8B90A0;font-size:13px}}
.dark .h{{font-family:'Inter Tight';font-weight:800;font-size:{S['dark']['size']}px;line-height:{S['dark']['lh']};letter-spacing:{S['dark']['ls']}em;margin-top:10px}}
.dark.sm{{padding:20px {S['dark_h']['padx']}px 24px}} .dark.sm .h{{font-size:{S['dark_h']['size']}px;word-spacing:.08em}}
.search{{background:#fff;border-radius:40px;height:{SEARCH_H}px;padding:0 24px 0 20px;display:flex;align-items:center;gap:13px}}
.mag{{flex:none;width:28px;height:28px;fill:none;stroke:#8B90A0;stroke-width:2.2;stroke-linecap:round}}
.search .h{{font-weight:500;font-size:{S['search']['size']}px;letter-spacing:{S['search']['ls']}em}}
.caret{{width:2px;height:28px;background:{INK};margin-left:-8px;opacity:.55}}
.video{{background:#fff;border-radius:18px;padding:16px 14px 14px}}
.video .h{{font-weight:600;font-size:{S['video']['size']}px;line-height:{S['video']['lh']};letter-spacing:{S['video']['ls']}em;padding:0 4px}}
.thumb{{position:relative;margin:13px 0 12px;border-radius:12px;aspect-ratio:16/9;
  background:linear-gradient(135deg,#C3C7D0 0%,#8D93A1 100%);overflow:hidden}}
.thumb::after{{content:'';position:absolute;left:10px;right:10px;bottom:10px;height:5px;border-radius:3px;background:rgba(255,255,255,.45)}}
.play{{position:absolute;left:50%;top:50%;width:54px;height:54px;margin:-27px 0 0 -27px;border-radius:50%;background:rgba(255,255,255,.94);
  display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(0,0,0,.2)}}
.play svg{{width:26px;height:26px;fill:{INK}}}
.video.nb .thumb{{margin-bottom:0}}
.video .av{{width:22px;height:22px}} .video .kick{{font-size:12.5px}} .video .row{{padding:0 4px;height:22px}}
.clip{{background:#EFE8D8;padding:16px {S['clip']['padx']}px 30px;text-align:center;
  clip-path:polygon(0 0,100% 0,{ZIG},0 100%)}}
.mast{{font-weight:600;font-size:12.5px;line-height:15px;letter-spacing:.24em;text-transform:uppercase;border-top:1.5px solid {INK};
  border-bottom:1.5px solid {INK};padding:6px 0 5px;white-space:nowrap;overflow:hidden}}
.clip .h{{font-size:{S['clip']['size']}px;line-height:{S['clip']['lh']};margin:13px 0 12px}}
.cols{{display:flex;gap:16px;text-align:left}} .cols>div{{flex:1}} .cols .bar{{margin-top:7px;height:6px}}
.quote{{background:{CREAM};border-radius:5px;padding:26px {S['quote']['padx']}px 22px}}
.quote .h{{font-family:'Instrument Serif';font-style:italic;font-weight:400;font-size:{S['quote']['size']}px;line-height:{S['quote']['lh']};letter-spacing:{S['quote']['ls']}em;margin-bottom:16px}}
.mail{{background:#fff;border-radius:14px;padding:18px {S['mail']['padx']}px 22px}}
.mail .h{{font-weight:600;font-size:{S['mail']['size']}px;line-height:{S['mail']['lh']};letter-spacing:{S['mail']['ls']}em;margin:13px 0 14px}}
.chat{{box-shadow:none !important}}
.bub{{display:block;width:fit-content;box-shadow:0 12px 26px rgba(0,0,0,.42),0 3px 8px rgba(0,0,0,.26)}}
.b1{{background:#fff;border-radius:26px 26px 26px 8px;padding:14px {S['chat']['padx']}px 15px;font-size:{S['chat']['size']}px;line-height:{S['chat']['lh']};letter-spacing:{S['chat']['ls']}em;font-weight:500}}
.b2{{background:{INK};color:{CREAM};border-radius:22px 22px 8px 22px;padding:10px 18px 11px;font-size:22px;line-height:26px;margin:10px 0 0 auto;white-space:nowrap}}
'''
