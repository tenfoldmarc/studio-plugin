# Paper Cut: the approved demo (maker side only)

`demo.mp4` and `stills/` show Marc. They are maker-side reference only: never ship them to a buyer or show them as
the buyer's result.

Demo clip: DJI 4K, low angle, sitting on the floor (medium shot, still camera), 125 frames (4.17 s).
Spoken line: "I mean, just look at this video, it was 100% edited by Claude."
The lab build hand-placed everything; the packaged build.py measures it. The same look in the package's CLIP block:

```
T_IN = 'look'                      # the paper rips in on "look" (lab: frame 14)
T_OUT = 3.90                       # the tear (lab: frame 117 of 125)
ROWS = [
    [('1', 1.60), ('0', 1.87), ('0', 2.07), ('%', 2.20)],         # one / hun / dred / per, read off the loudness
    [('ED', 2.63), ('IT', 2.77), ('ED', 2.93), (' BY', 3.10)],     # syllables of "edited", then "by"
    'CLAUDE',                                                       # lands on the spoken word
]
LAYOUT = 'auto'                    # measures as ABOVE: the cutout shrinks toward its corner (lab: 0.80, bottom left)
FONT = 'mix'                       # the lab used macOS system faces (Impact, Didot, Rockwell ...); the package uses
                                   # the shipped stand-ins (Bebas Neue, DM Serif Display, Archivo 900, Newsreader ...)
MATTE_KILL_POLYS = [[(0, 0), (250, 0), (250, 622), (0, 574)],          # a wall picture the matte grabbed
                    [(955, 0), (1080, 0), (1080, 1262), (955, 1262)]]  # a cabinet edge right of the hand
MATTE_PLATE = dict(roi=(690, 1060, 1080, 1262), frames=list(range(52, 90, 3)), thr=20, min_area=2200)
```
Everything else default (INK, ACCENT red, ACCENT2 blue, HIGHLIGHT yellow, ELLIPSE on the '100%' row, TAPE on).
The lab also had a hand opening `MATTE_OPEN_ROI = (800, 1000, 1080, 1262, 92)` for a thin strip; the package keeps
the code path (`matte.open_roi` in the plan) but does not expose it: kill polygons cover the same case.
