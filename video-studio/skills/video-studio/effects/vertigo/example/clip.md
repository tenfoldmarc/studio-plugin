# Vertigo: the demo clip (maker-side only)

`demo.mp4` and `stills/` show Marc. They are maker-side only and never ship to a buyer.

- Source: an armchair talking head, wide-ish, still camera on a tripod, a door with glass panes and a plain wall behind.
- Line (3.6 s): "And the funniest thing is I suck at design and I'm not a tech bro at all."
- The demo was the lab build (a hand-drawn chair outline, hand clone stamps on the door panes). The package replaces
  all of that with measured values: the seat line pins the chair, the plate fill is automatic.

CLIP block values that reproduce the demo's move in the package:

| Field | Value |
|---|---|
| `PUSH_WORD` | `'suck'` (push from 0.96 s) |
| `PEAK_WORD` | `'design'` (lands 1.58 s) |
| `RELEASE_WORD` | `'not'` (snap 2.32 s) |
| `SCALE` | `1.33` (the auto choice for a wide shot with an open wall) |
| `CAPTIONS` | `[(2.20, [('SUCK', 1.06, False), ('AT', 1.30, False), ('DESIGN', 1.46, True)]), (2.70, [('NOT', 2.36, False), ('A', 2.54, False)]), (3.50, [('TECH', 2.70, True), ('BRO', 2.84, True)])]` |
| `FONT` / `WEIGHT` / `CASE` | `'Inter Tight'` / `900` / `'upper'` |
| `INK` / `ACCENT` | `'#FFFFFF'` / `'#FAE67A'` |
| `SFX_GAIN` | `1.0` (riser into the push, soft air on the snap) |
