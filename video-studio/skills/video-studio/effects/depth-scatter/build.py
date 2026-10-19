#!/usr/bin/env python3
"""DEPTH SCATTER (hook): the opening words land one by one at different sizes and heights over the chest, and each
earlier word falls out of focus (soft, dimmer) as the next one lands, like a camera racking past them. Then they all
cut out together.

Run from the slot folder (effect.md has the full run order):
    python3 build.py      writes index.html   (SAFE=1 safe-zone guide, SFX=0 no sounds, CAPTIONS=0 accepted:
                                               the words ARE the effect, so they always draw)
"""
import vgfx as V

# ==== STYLE (the reel's look wins: match this block to the reel's caption style before building) ====
# Fonts must be families that assets/fonts/fonts.css provides. The defaults are the Viral Guy look: cream Inter
# Tight with tight tracking, Inter for small labels, Instrument Serif italic as the second voice, deep ink cards.
STYLE = dict(
    font='Inter Tight',            # main words
    weight=700,
    tracking=-0.035,               # letter spacing of the main words, em
    big_weight=800,                # the huge words (numbers, the word that matters)
    big_tracking=-0.055,
    case='as-said',                # 'as-said', 'lower' or 'upper'
    small_font='Inter',            # small labels, chips, sub lines
    small_weight=500,
    serif_font='Instrument Serif', # the second voice (Serif Flow nodes)
    serif_italic=True,
    ink='#E9DAC8',                 # text colour (cream). White reels: '#FFFFFF'
    accent=None,                   # colour of the huge words; None = same as ink. Never orange
    card='#101B1B',                # full-frame card / dark fills (deep ink)
    shadow=True,                   # soft shadow under words that sit on footage
)
# ==== END STYLE ====

# ==== CLIP (edit this) ====
WORDS = None        # None = the slot's first spoken phrase (up to 6 words, ends at a pause or a full stop).
                    # Or [(text, seconds), ...]: each word lands at its seconds (slot time). Two short words can
                    # share one entry ("got me"). 3 to 6 entries read best
T_OUT = None        # when all the words cut out (slot seconds). None = 0.25 s after the last word ends
Y = None            # centre of the cluster, screen px. None = the chest band from layout.json, clear of the chin
SIZES = (70, 92, 58, 106, 64, 84)   # font size of each word in turn, px. The biggest should fall on the word that matters
SOFT = 3            # blur (px) of the earlier words once the next one lands. 0 = no depth
# ==== END CLIP ====


def auto_words(s):
    out, cur = [], []
    for w in s.words:
        if cur and (w['start'] - cur[-1]['end'] > .35 or len(cur) >= 6):
            break
        cur.append(w)
        if w['text'][-1:] in '.?!':
            break
    # a short word said within 0.15 s of the next one rides with it
    k = 0
    while k < len(cur):
        if k + 1 < len(cur) and cur[k + 1]['start'] - cur[k]['start'] < .15 and len(V.bare(cur[k]['text'])) <= 3:
            out.append((V.bare(cur[k]['text']) + ' ' + V.bare(cur[k + 1]['text']), cur[k]['start'], cur[k + 1]['end']))
            k += 2
        else:
            out.append((V.bare(cur[k]['text']), cur[k]['start'], cur[k]['end']))
            k += 1
    return out


def main():
    s = V.Slot()
    print('words: ' + s.word_list())
    print(s.where())
    if WORDS:
        items = [(t, float(at), float(at) + .3) for t, at in WORDS]
    else:
        items = auto_words(s)
    if len(items) < 2:
        V.die('Depth Scatter needs a spoken phrase of at least 2 words at the start of the slot')
    t_out = T_OUT if T_OUT is not None else min(s.dur, items[-1][2] + .25)
    y = s.band(340, Y)
    if y is None:
        V.die('there is no room under or above the face on this clip for the scattered words')
    p = V.Page(s)
    p.css.append(V.style_css(STYLE) + '\n.sc{position:absolute;transform:translate(-50%,-50%)}')
    # two loose rows, words laid left to right, each a little higher or lower than the last
    n = len(items)
    rows = [items[:(n + 1) // 2], items[(n + 1) // 2:]]
    k = 0
    placed = []
    for r, row in enumerate(rows):
        sizes = [SIZES[(k + i) % len(SIZES)] for i in range(len(row))]
        widths = [len(t) * sz * .6 for (t, _, _), sz in zip(row, sizes)]
        gap = 56
        total = sum(widths) + gap * (len(row) - 1)
        scale = min(1.0, (1080 - 2 * V.SAFE_SIDE - 60) / max(total, 1))
        x = 540 - total * scale / 2 + (-40 if r == 0 else 40) * scale
        for i, ((text, at, _), sz, wd) in enumerate(zip(row, sizes, widths)):
            cx = x + wd * scale / 2
            cy = y + (-80 if r == 0 else 80) + (-14, 12, -6, 16, -10, 8)[(k + i) % 6]
            placed.append((text, at, cx, cy, int(sz * scale)))
            x += (wd + gap) * scale
        k += len(row)
    ids = []
    for text, at, cx, cy, sz in sorted(placed, key=lambda z: z[1]):
        i = p.nid('sc')
        p.html.append(f'<div id="{i}" class="sc vg-word" style="left:{cx:.0f}px;top:{cy:.0f}px;font-size:{sz}px">'
                      f'{V.esc(V.cased(text, STYLE["case"]))}</div>')
        p.enter(f'#{i}', at, {'filter': 'blur(14px)', 'scale': 1.08}, {'filter': 'blur(0px)', 'scale': 1}, .14, t_out=t_out)
        for old in ids:
            if SOFT:
                p.js.append(f"tl.to('{old}',{{filter:'blur({SOFT}px)',opacity:.62,duration:.14}},{V.T(at):.3f});")
        ids.append(f'#{i}')
        print(f'  {text!r} lands at {at:.2f}s, {sz}px, centre ({cx:.0f}, {cy:.0f})')
    p.write()
    print(f'snapshot at: {",".join(f"{at + .2:.2f}" for _, at, _, _, _ in placed)},{max(0, t_out - .05):.2f}')
    s.hide_hint([(0, t_out)])


if __name__ == '__main__':
    main()
