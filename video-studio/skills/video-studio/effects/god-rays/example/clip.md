# God Rays: the approved demo (maker side only)

`demo.mp4` and `stills/` show Marc. They are for the maker and the importer, never shipped to buyers or shown as the
buyer's own result.

- Source: a DJI 4K clip, low angle under a bright grey ceiling, camera moving, 152 frames (0.30 s to 5.35 s).
- Line: "All you need is Claude and the right skill, ..." (Whisper heard "card" for "Claude").
- Lab CLIP values: light opens 0.57 s ("Claude" at 0.70 s in the audio), falls from 1.74 s (end of "skill"), words
  CLAUDE (caps, 0.72 s) and "and the right skill" (serif, 0.94 s), room one stop down, beams warm white with a quarter butter.
- The same clip rebuilt with this package (`pack/tests/god-rays/demo/`): CLIP block
  `T_IN = 'card'`, `T_OUT = 'skill'`, `TEXT = [('Claude', 'caps', None), ('and the right skill', 'serif', 'and')]`,
  everything else default. build.py measured a medium shot, bright wall (median 127) -> one stop, light scale 107 px
  (the lab head radius was 103 to 139 px), light at 0.60 s. Same look as the approved demo with the shipped fonts
  (Montserrat 500 for the lab's Montserrat 600, Instrument Serif italic as before).
