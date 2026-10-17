# Neon Sign: the demo clip (maker side only)

`demo.mp4` and `stills/` show Marc and are for the maker only: they never ship to buyers and never appear in a reel.
`demo.mp4` is the approved lab render (`reel-edit/fx-lab/neon-sign/renders/neon-sign-phone.mp4`).

Source: DJI c2 (wide, green sofa, still camera with two small nudges), 1728x3072, in 32.8 s, 132 frames (4.4 s).
Spoken line: "you need edits like this, like this, or like that."

The lab look: "like / this." in a hand-bent script (SignPainter, a Mac system font) on the plaster left of the head,
butter yellow FAE67A, 196 px letters, a swash underline that strikes on the second "like THIS", one step brighter on
"like THAT" with a low thump, a slow 4.5 percent push-in, shadows of the framed print and the two wall lights hand-traced.

The same clip through the package (`pack/tests/neon-sign/demo/`, the lab's own cutout), CLIP block:
```
LINES = [('like', 'like'), ('this.', 'this')]
UNDERLINE = 'this#2'
STEP_ON = 'that'
OUT = 'cut'          # the lab demo ends lit; in a reel use 'auto' or cut away right after
```
Everything else default (Marck Script stands in for SignPainter; no push-in; no hand-traced shadows). build.py chose
BESIDE, left of the head, 134 px letters (the open plaster between the trim and the head; the lab placed 196 px by
hand partly over the trim). Strikes measured on the audio: "like" 0.82 s, "this" 1.23 s, underline 2.31 s (the lab's
hand values were frames 21, 33 and 65: 0.70, 1.10, 2.17 s plus their flicker lead-in).
