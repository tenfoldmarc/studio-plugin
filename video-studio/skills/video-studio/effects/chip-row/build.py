#!/usr/bin/env python3
"""CHIP ROW (explain): as the speaker lists things ("your brand colours, your fonts, links to creators"), an
outlined pill pops in for each one, in a row under the captions. The reel's own captions keep running above it.

Run from the slot folder (effect.md has the full run order):
    python3 build.py      writes index.html   (SAFE=1 safe-zone guide, SFX=0 no sounds, CAPTIONS=0 accepted:
                                               the chips ARE the effect, so they always draw)
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
CHIPS = []          # [(text, seconds), ...]: one pill per thing listed, each popping in when it is said (slot
                    # seconds). The speaker's own words, shortened: 1 to 3 words each, 2 to 4 pills. Required
T_OUT = None        # when the row cuts out (slot seconds). None = the end of the slot
Y = None            # centre of the row, screen px. None = just under the reel's caption line (layout.json)
SIZE = 30           # chip text size, px; the row shrinks by itself when it is wider than the frame
SOUND = 0.12        # volume of the soft click on each chip. 0 = silent
# ==== END CLIP ====


def main():
    s = V.Slot()
    print('words: ' + s.word_list())
    print(s.where())
    if not CHIPS:
        V.die('write CHIPS in the CLIP block: the things the speaker lists and when each is said')
    t_out = T_OUT if T_OUT is not None else s.dur
    # under the reel's caption line, which keeps running: its top sits on the chest band
    y = Y if Y is not None else s.chest + 150
    y = min(y, V.SAFE_BOTTOM - 40)
    if y - 30 < s.chin + 20:
        y = s.band(60)
        if y is None:
            V.die('there is no room under or above the face on this clip for the chips')
    width = sum(len(t) * SIZE * .56 + 2 * SIZE * .9 for t, _ in CHIPS) + 16 * (len(CHIPS) - 1)
    scale = min(1.0, (1080 - 2 * V.SAFE_SIDE - 2 * V.SAFE_RIGHT) / width)
    size = int(SIZE * scale)
    p = V.Page(s)
    ink, card = STYLE['ink'], STYLE['card']
    p.css.append(V.style_css(STYLE) + f'''
.cr{{position:absolute;left:{V.SAFE_SIDE}px;right:{V.SAFE_RIGHT}px;display:flex;justify-content:center;gap:{int(16 * scale)}px;transform:translateY(-50%)}}
.cr .chip{{font-size:{size}px;padding:{int(size * .4)}px {int(size * .87)}px;border-radius:999px;border:2px solid {ink}B3;background:{card}59}}''')
    i = p.nid('cr')
    p.html.append(f'<div id="{i}" class="cr" style="top:{y}px">' +
                  ''.join(f'<span id="{i}c{k}" class="chip vg-small">{V.esc(V.cased(t, STYLE["case"]))}</span>' for k, (t, _) in enumerate(CHIPS)) + '</div>')
    for k, (text, at) in enumerate(CHIPS):
        p.enter(f'#{i}c{k}', float(at), {'y': 14, 'scale': .9}, {'y': 0, 'scale': 1}, .2, 'back.out(2.2)', t_out=t_out)
        if SOUND:
            p.sound('click-soft', float(at), SOUND)
        print(f'  chip {text!r} at {float(at):.2f}s')
    print(f'  row centre y {y}, {size}px text, out at {t_out:.2f}s')
    p.write()
    print('snapshot at: ' + ','.join(f'{float(at) + .25:.2f}' for _, at in CHIPS) + f',{max(0, t_out - .05):.2f}')
    print('in a reel: the reel\'s captions stay on (slot.json says keep); check they do not touch the row')


if __name__ == '__main__':
    main()
