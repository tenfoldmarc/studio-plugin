# Shatter 3D: the demo clip (maker-side only)

`demo.mp4` and `stills/` show Marc. They are maker-side reference only: they do not ship to buyers.

- Source: DJI 4K, armchair by the green sofa, medium shot, still camera (`dji_mimo_20261007_170044...MP4`, in 23.58 s, 169 frames, `--hi`).
- Line: "I'm terribly sorry to say, but video editors are absolutely cooked."
- `demo.mp4` is the approved lab render (v2, glass ending), hand-placed tiles. The package lays the tiles out from the
  measured head instead; `pack/tests/shatter-3d/demo/` is the package run on the same clip.

CLIP block values for this clip (everything else default):
| field | value | note |
|---|---|---|
| `T_BREAK` | 'absolutely' | Whisper 3.12 s, audio onset 3.30 s (frame 99; the lab used 98) |
| `T_HIT` | 'cooked' | Whisper 3.82 s, audio onset 4.26 s (frame 128, same as the lab) |
| `ENDING` | 'glass' | cracks frames 139 to 141, glass falls 142 to 161, clean from 162 |
| measured | medium, head 192 px, face tile (360, 325, 675, 790) | the lab's hand-placed face tile was (360, 300, 690, 770) |
| close-ups | eyes to the right, hands to the lower left | as in the lab |
| `IMPACT` | auto: on the hands (739, 890) | the lab used (585, 905) |
