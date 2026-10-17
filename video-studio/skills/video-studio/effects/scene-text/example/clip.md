# scene-text: the demo (maker-side only)

`demo.mp4` and `stills/` show Marc. They are maker-side reference for the importer and never ship to buyers.

**Source:** DJI 4K clip c2 (wide, green sofa, still camera), 29.83 s to 34.5 s, 140 frames.
**Line:** "because everybody's yapping nowadays. So if you want to stand out, ... like this"

The approved lab demo was built by hand (picture-frame corners for the plane, hand outlines of the wall lights, a
hand-drawn couch line, a two-layer parallax push-in, words held to the end). The package measures all of that instead
and drops the parallax (see test.md). The same clip run through the package (`tests/scene-text/demo/`) with:

```
PRINT_TEXT = 'YAPPING'
PRINT_FRAME = 20                     # "yapping" 0.65 s
HERO = [(69, 'STAND'), (77, 'OUT')]  # "stand" 2.29 s, "out" 2.57 s
FONT, WEIGHT, BOLDEN = 'Bebas Neue', 400, 0.035
PRINT_INK = '#6F8263'                # sage, Marc's pick 2026-10-13 (the default)
everything else on auto / None
```
Measured: still camera, medium framing, 24% open wall, multiply, flat on; big words stacked left of his head.
