# Word Pile: the approved demo (maker side only)

`demo.mp4` and `stills/` show Marc and name real editing apps: they are maker-side only, never shipped to buyers
as material and never used as defaults.

- Source: DJI 4K, medium shot on the green sofa, still camera, black jeans (`fx-lab/word-pile/`, v2 = floor line).
- Line: "Now you don't need CapCut, DaVinci, Premiere Pro, or an expensive video editor that you have to pay
  hundreds of dollars every single video."
- CLIP block for that clip in the packaged build.py:

```
SLABS = [
    ('CAPCUT', 'CapCut', 1.0),
    ('DAVINCI', 'DaVinci', 1.0),
    ('PREMIERE PRO', 'Premiere', 1.2),
    ('EXPENSIVE\nEDITOR', 'expensive', 2.6),
]
T_SWEEP = 'every'
```
Everything else default (Inter Tight 900 caps, cream on dark slabs, butter yellow heavy slab, cream line at y 1420).
The package plans the same layout the lab art-directed by hand: the three dark slabs stack at the right end of the
line, the heavy slab gets the left end to itself and slams the line. Re-built with the package in
`pack/tests/word-pile/demo/`.
