#!/usr/bin/env python3
"""PROMPT BOX (explain): a glass input field appears over the chest with a small label notched into its top border,
and what the speaker tells the AI ("edit it in my style") types itself in, with a caret that blinks when it stops.

Run from the slot folder (effect.md has the full run order):
    python3 build.py      writes index.html   (SAFE=1 safe-zone guide, SFX=0 no sounds, CAPTIONS=0 accepted:
                                               the typed text IS the effect, so it always draws)
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
TEXT = ''           # what types into the box: the speaker's own words, as they would type them. Required.
                    # Up to about 60 characters (two lines); longer text gets a smaller size by itself
LABEL = ''          # small label in the gap of the top border ("step two", "prompt"). '' = a plain border
T_TYPE = None       # when the first letter appears (slot seconds). None = when the first word of TEXT is said
T_DONE = None       # when the last letter appears. None = when the last word of TEXT ends (at least 0.03 s a letter)
T_OUT = None        # when the box cuts out. None = 0.4 s after T_DONE, or the slot end
Y = None            # centre of the box, screen px. None = the chest band from layout.json
WIDTH = 740         # box width, px (kept inside the safe zone)
SIZE = 50           # text size, px
SOUND = 0.0         # volume of soft key clicks while it types. 0 = silent (the look is quiet)
# ==== END CLIP ====


def main():
    s = V.Slot()
    print('words: ' + s.word_list())
    print(s.where())
    if not TEXT.strip():
        V.die('write TEXT in the CLIP block: what the speaker says they type or tell the AI')
    first = V.bare(TEXT.split()[0]).lower()
    last = V.bare(TEXT.split()[-1]).lower()
    w0 = next((w for w in s.words if V.bare(w['text']).lower() == first), None)
    t_type = T_TYPE if T_TYPE is not None else (w0['start'] if w0 else .1)
    w1 = next((w for w in s.words if w['start'] >= t_type - .01 and V.bare(w['text']).lower() == last), None)
    t_done = T_DONE if T_DONE is not None else (w1['end'] if w1 else t_type + len(TEXT) * .05)
    t_done = max(t_done, t_type + len(TEXT) * .03)
    t_out = T_OUT if T_OUT is not None else min(s.dur, t_done + .4)
    size = SIZE if len(TEXT) <= 26 else max(34, int(SIZE * 26 / len(TEXT) ** .9))
    lines = 1 if len(TEXT) * size * .5 < WIDTH - 80 else 2
    height = int(lines * size * 1.15 + 64)
    y = s.band(height, Y)
    if y is None:
        V.die('there is no room under or above the face on this clip for the box')
    width = min(WIDTH, 1080 - 2 * V.SAFE_RIGHT)
    left = int((1080 - width) / 2)
    p = V.Page(s)
    ink, card = STYLE['ink'], STYLE['card']
    p.css.append(V.style_css(STYLE) + f'''
.pb{{position:absolute;left:{left}px;width:{width}px;transform:translateY(-50%);border:2px solid {ink}A6;
  border-top-color:{'transparent' if LABEL else ink + 'A6'};border-radius:26px;background:{card}6B;padding:32px 40px 28px}}
.pb .top{{position:absolute;left:24px;right:24px;top:-19px;height:36px;display:flex;align-items:center;gap:14px}}
.pb .top i{{flex:1;height:2px;background:{ink}A6}}
.pb .top span{{font-size:28px}}
.pb .tx{{font-size:{size}px;line-height:1.15;white-space:pre-wrap;min-height:{int(size * 1.15)}px}}
.pb .ch{{display:none}}
.pb .caret{{display:inline-block;width:4px;height:{int(size * 1.04)}px;background:{ink};vertical-align:-{int(size * .16)}px;margin-left:4px}}''')
    i = p.nid('pb')
    chars = ''.join(f'<span id="{i}k{k}" class="ch">{V.esc(c)}</span>' for k, c in enumerate(TEXT))
    top = f'<div class="top"><i></i><span class="vg-small">{V.esc(LABEL)}</span><i></i></div>' if LABEL else ''
    p.html.append(f'<div id="{i}" class="pb" style="top:{y}px">{top}<div class="tx vg-word" style="letter-spacing:-.02em">'
                  f'{chars}<span id="{i}cr" class="caret"></span></div></div>')
    t_in = max(0.0, t_type - .12)
    p.enter(f'#{i}', t_in, {'scale': .96}, {'scale': 1}, .16, t_out=t_out)
    step = (t_done - t_type) / len(TEXT)
    for k in range(len(TEXT)):
        at = t_type + k * step
        p.js.append(f"tl.set('#{i}k{k}',{{display:'inline'}},{V.T(at):.3f});")
        if SOUND and TEXT[k] != ' ' and k % 3 == 0:
            p.sound('key-press', at, SOUND)
    t = t_done + .2
    while t < t_out - .2:
        p.js.append(f"tl.set('#{i}cr',{{opacity:0}},{V.T(t):.3f}); tl.set('#{i}cr',{{opacity:1}},{V.T(t + .25):.3f});")
        t += .5
    print(f'  box in at {t_in:.2f}s, types {len(TEXT)} letters {t_type:.2f}s to {t_done:.2f}s, out at {t_out:.2f}s, centre y {y}')
    p.write()
    print(f'snapshot at: {t_type + .05:.2f},{(t_type + t_done) / 2:.2f},{t_done + .1:.2f},{max(0, t_out - .05):.2f}')
    s.hide_hint([(t_in, t_out)])


if __name__ == '__main__':
    main()
