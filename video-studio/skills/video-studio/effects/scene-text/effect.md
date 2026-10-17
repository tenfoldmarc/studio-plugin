# scene-text ("Scene Text")

**What it does:** a small word prints across the speaker's real wall like sage wallpaper, spreading out from behind his head, behind him and behind whatever hangs on the wall. Then 1 to 3 big painted words land on the wall on the frames he says them, lit like the plaster, with a block shade and a tiny camera punch. The print lifts off, the big words follow, and the slot ends on the plain picture. Quiet on purpose: Marc liked it for being subtle.
**Job:** hook or emphasis on one short line (3 to 6 s) with a word worth printing and 1 to 3 words worth painting.
**Trigger phrases:** "paint STAND OUT on the wall behind me", "cover my wall in the word yapping", "scene text on this line".

## Footage it needs
- Shot: wide, medium or close selfie. Camera: still or handheld drift (tracked, the print stays stuck to the wall). Not a moving camera or a walk.
- Wall: needs some plain wall behind or beside him (beside / above / both). Cutout: layered (his cutout keeps him in front) and measured (head, where he goes).
- Breaks on: no plain wall (busy shelves edge to edge, all window), a camera that travels, him leaving the frame. `scene.py measure` stops with the reason.

## Adapting to the footage (measured by `scene.py measure`, printed; CLIP entries override)
- Wide / medium: the print fills the wall, the big words stack (one per line, same width) beside or above his head, at most about 2.5 head widths wide.
- Tight selfie close-up: print letters scale with his head (up to 52 px); the big words go side by side on the open strip above or beside the head, with a wider gap from it (a close-up never tucks a word behind the head).
- Still camera: everything locked. Handheld drift: a background-only track pins print and words to the wall. More than 300 px of travel: declines.
- Open wall: print everywhere on it. Busy shelf, pictures, lamps, windows, furniture, floor: the wall map keeps them in front, so the print reads as behind them; only solid things cut the big words (thin trim and corner lines do not).
- Plain dark wall: the print is lifted in (lighter sage) instead of multiplied. Light wall: multiplied (the default look).
- Room perspective: vertical lines (doors, panels, corners) set a keystone so the wall text leans with the room; too few lines = flat on.
- Off-centre speaker / two-thirds framing: the big-word block goes to the biggest open wall near his head, whichever side. No room for the block anywhere: print only, and it says so (caption the big words in the main reel).
- Declines with one line: under 6% open plain wall, a travelling camera, or him out of shot for a fifth of the slot.

## Slot inputs
`assets/aroll.mp4`, cutout `assets/subject.webm` (required), `clip.json`, `words.json`, `assets/fonts/fonts.css` (the Studio's font set), stock sounds `whoosh-short`, `impact-bass-1`. No `aroll_hi`. Python: numpy, Pillow, opencv-python-headless (`requirements.txt`). No absolute paths, no system fonts, no shipped media.

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `PRINT_TEXT`, `PRINT_FRAME` | the small printed word (1 or 2 short words) and the frame it starts spreading | the line's loudest idea; frame from `python3 onsets.py` ("swap"), at least 2 |
| `HERO` | 0 to 3 big words, `(frame it lands, 'WORD')` | onsets.py; a frame late beats a frame early. `[]` = print only |
| `CLEAR_FRAME`, `OUT_FRAME` | print lifts off; big words gone | `None` = last word + 32, + 14 (always 12 frames before the end) |
| `HOLD_TO_END` | big words stay to the last frame | only when the slot ends the reel or ends on a cut |
| `FONT`, `WEIGHT`, `BOLDEN` | big-word font (from fonts.css), weight, extra stroke | default Bebas Neue 400 + 0.035 (stand-in for the demo's condensed poster face). With the buyer's caption font, BOLDEN 0 for heavy faces |
| `CASE`, `ACCENT`, `INK` | case of all words, big-word paint, block-shade colour | defaults `'upper'`, `#FAE67A`, `#14161C`; take the buyer's caption colours |
| `PRINT_FONT`, `PRINT_WEIGHT`, `PRINT_INK`, `PRINT_SIZE` | the print's font, weight, colour, size | Inter Tight 900, sage `#6F8263` (the default), size `None` = from his head |
| `HERO_BOX`, `HERO_LAYOUT` | `(x, y, w)` of the big-word block; `'stack'` / `'line'` / `'auto'` | leave `None` / `'auto'` unless work/measure.jpg shows a better spot |
| `KEYSTONE`, `PRINT_MODE` | wall perspective (`'auto'`, `None`, or the `(x, y)` where verticals meet); `'multiply'` / `'lift'` / `'auto'` | leave on auto |
| `BUMP`, `VOL_PRINT`, `VOL_HIT` | camera punch per big word; sound levels (x0.75 applied) | 0 turns one off |

**Switches:** `SAFE=1` (build.py: safe-zone guide in snapshots; scene.py still: guide on stills). `SFX=0` no sounds. `CAPTIONS=0` and `GRADE` change nothing: the big words are the caption for those words (do not caption them again), and there is no grade, so the slot edges match the a-roll.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 2. word frames from the audio (check words.json: Whisper can mishear or invent a line)
PY "SK/scripts/fx_run.py" "<slot>" scene.py measure      # 3. camera, wall map, head, perspective, variant. LOOK at work/measure.jpg
# edit: the CLIP block (PRINT_TEXT/FRAME, HERO always); re-run measure to see the block
PY "SK/scripts/fx_run.py" "<slot>" scene.py still SAFE=1      # 5. six key frames -> work/stills/sheet1.jpg
PY "SK/scripts/fx_run.py" "<slot>" scene.py bake      # 6. assets/fx.mp4 (all cores; about 6 to 8 s per slot second on an M-series Mac, 6 workers)
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 7. index.html (same switches you want in the render, e.g. SFX=0)
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 8. frame count, phone copy, work/qa/sheet.jpg from the final mp4
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Re-bake after any CLIP change except sounds (build.py only).

## What to look at (work/qa/sheet.jpg)
- Each big word appears on its frame, never before; the print spreads from behind his head and sits behind him, his hair and hands clean.
- Pictures, lamps, shelves and windows stay in front of the print; the big words read whole, inside the safe zone, never over his face.
- Handheld: print and words stay stuck to the wall (no swimming against the picture frames).
- First and last frame identical to the a-roll (unless `HOLD_TO_END`). Frame count equals `clip.json`.

## Traps
- Whisper can hallucinate a whole line on a short slot (it did on the selfie test). Check words.json against what he says.
- A light grey or beige object flat on the wall (a frosted lamp shade, a pale poster) can read as wall and get printed on. If it shows, it is small; accept it or pick another line.
- The print is multiplied: a pale `PRINT_INK` is quiet, a deep one loud. Never orange; no black and white.
- Long big words on a close-up: the side-by-side line can run out of room, then the stack is tried, then print only.
