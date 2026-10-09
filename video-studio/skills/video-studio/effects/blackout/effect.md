# blackout

**What it does:** the clip starts in its normal look, the room dims on a line while the speaker stays lit, the punch word slams in behind the head with a flash and a small camera kick, and the lights snap back on at the next cut (or the next line).
**Job:** hook (one line that builds to one word, then a hard reset into the next shot).
**Trigger phrases:** "dim the room when I say X and bring the lights back on the next line", "black out the room and slam X behind my head", "lights down for this line, snap them back on at the cut".
**Blackout or Spotlight:** Blackout only dims the room (still sharp, about half brightness), lands ONE word with a flash and a kick, and snaps the lights back hard: pick it for a punch word that leads into a cut. Spotlight takes the room near dark and out of focus under a pool of light, lands up to three words and eases back up: pick it for a phrase inside one continuous shot.

## Footage it needs
- **Shot:** wide, medium or close, one person, 3 to 6 s: a line of 1 to 3 s that ends on the punch word, then the next line or the next shot. Best wide or medium with room above the head. On a close shot the word sits just above the head.
- **Camera:** still, drifting or handheld all work. The room is the live picture with a filter and the speaker is the live cutout, nothing is a still plate. The word is fixed on screen.
- **Wall:** none needed. About 240 px of picture between the safe top (y 220) and the top of the head gives the word its place.
- **Cutout:** layered (drawn lit over the dim room, edge cleaned by `prep.py`) and measured (head, neck, open room).
- **What breaks it:** a cutout that keeps background beside the head or between arm and body (it stays lit: pick another span) or loses hair or fingers (they dim with the room); a hand above the head or two people (the head is the highest thing in the cutout); a head that reaches the safe top (no room: `WORD_PLACE` `'left'` / `'right'` / `'chest'`, or `CAPTIONS=0`); a room that is already dark (nothing to dim); a line under about 0.5 s before the punch.

**Slot inputs:** cutout yes, `aroll_hi` no. Python: numpy, scipy, Pillow (`prep.py`, `check.py`, and `build.py` to measure the word); numpy for `onsets.py`.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `F_DIM` | first frame the room starts to dim | `onsets.py`: onset of the first word of the line. 3 or later |
| `DIM_FRAMES` | frames the dim takes | 24 (0.8 s). Shorter on a short line: down by `F_PUNCH` |
| `F_PUNCH`, `PUNCH` | frame the punch word is said, and the word | its onset; typed as the speaker says it, only a word the speaker says. `''` = no word |
| `F_SNAP` | frame the lights snap back | `'auto'` = the first cut after `F_PUNCH` in `clip.json`. No cut: onset of the next line. 12+ frames after `F_PUNCH`, 14+ before the last frame. `None` = dim to the last frame: the slot must END ON A CUT |
| `DIM`, `COOL`, `EDGE_DARK` | room brightness, how much it cools, darkness from the edges and floor | 0.46, 1, 1. `DIM` 0.30 darker, 0.60 lighter; the others 0 = off |
| `PUSH`, `KICK` | slow push-in to the punch; camera kick on it | 1.055 (1 = none); 1 (0.5 softer, 0 = none) |
| `FLASH`, `FLASH_COLOUR`, `SNAP_FLASH`, `SNAP_COLOUR` | the flash on the punch and the one when the lights return | 0.28 warm white, 0.5 white. 0 = none |
| `EDGE_CHOKE`, `EDGE_SPILL` | px the cutout edge is pulled in; px recoloured from inside | 1.5 and 3. Pale rim on `work/check_edge.jpg`: 2.5. Thin hair eaten: 0.8 |
| `GRADE`, `SOUNDS` | css filter on the whole slot (`''` = off, default); sounds on / off | defaults |

## WORD STYLE block (right under the CLIP block)
The punch word repeats one word the speaker says; it is the centre of the look but the effect works without it. **The reel's style wins:** when the reel has a caption style or an overall style, copy that style's typeface, case, weight and colour into this block, or build with `CAPTIONS=0` and let the reel's captions say the word. The defaults are only for a reel with no style of its own. A wide typeface in capitals makes a long word small (13 letters came out at 74 px): when `build.py` says "very small", pick a shorter punch word the speaker says, or build with `CAPTIONS=0`.
`WORD_FONT` + `WORD_FONT_FILE` (a face in `assets/fonts`), `WORD_WEIGHT`, `WORD_ITALIC`, `WORD_CASE` (`'lower'`, `'upper'`, `'title'`, `'as-typed'`), `WORD_TRACK`, `WORD_COLOUR`, `WORD_GLOW` (`'auto'`, a colour, `''`), `WORD_PLACE` (`'auto'`, `'behind'`, `'left'`, `'right'`, `'chest'`, or `('back' or 'front', centre x, baseline y)`), `WORD_SIZE` (`'auto'` or px).

**Switches:** `SAFE=1` draws the safe-zone guide and the word's measured ink box (snapshots only). `CAPTIONS=0` turns the effect's own word off: the room still dims, flashes, kicks and snaps back, and the reel's captions carry the words. `SFX=0` drops the sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 1. prints word onsets as frames
# edit: the CLIP block in build.py: F_DIM, F_PUNCH, PUNCH, F_SNAP. Then the WORD STYLE block under it: the reel's own style when it has one
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. measures the speaker, cleans the cutout edge (about 1 min). LOOK at work/check_edge.jpg (full size) and work/check_sheet.jpg
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # 3. places the word and prints its ink box. It stops if the word is on the face or outside the safe zone
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 1.4,2.52,2.72,3.35,3.39,3.75      # your own times: before F_DIM, the punch frame, word settled, last dim frame, the snap frame, after
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 4. the clean page (no guide), then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # 5. frame count, plain frames at both ends, how dim the room got; writes work/final_sheet.jpg and work/final_edge.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.

## What to look at in the final frames
- Frame 0, the frame before `F_DIM`, and from 11 frames after `F_SNAP` to the last frame: plain picture, `check.py` says ok. No dim, no push-in left on.
- The dim starts on `F_DIM` and is down before the punch; the room keeps its colour (dim and cool, never grey or black), the speaker is in full colour.
- On `F_PUNCH` the word is on screen, big and soft, with the flash; 6 frames later it is sharp, behind the head, inside the safe zone (top 220, nothing below 1470, sides 35, right 100 from y 1155). It never covers the face.
- The last dim frame is `F_SNAP` minus 1; on `F_SNAP` the room is lit with the flash over it and the word is gone.
- `work/final_edge.jpg` at full size: no pale rim around head and hair, nothing of the speaker left dim, nothing of the room left lit.
- The render has exactly the `frames` of `clip.json` and the speaker's audio.

## Traps
- `prep.py` bakes `F_DIM`, `F_PUNCH`, `F_SNAP`, `EDGE_CHOKE` and `EDGE_SPILL`: change one and `build.py` refuses to run until `prep.py` has run again. Everything else only needs `build.py`.
- Run `build.py` with the same Python as `prep.py`: it measures the word with Pillow. Without Pillow it falls back to rough table values and says so.
- On the punch frame the word is 1.9x and blurred for 2 to 3 frames and may reach past the safe zone: that is the slam. It is judged where it settles.
- The word is fixed on screen. A speaker who moves a lot slides behind it; the head is measured only while the word is up, so pick the place from `work/check_sheet.jpg` if it sits wrong.
- A first snapshot can show the picture grey (the video has not decoded yet). Judge the room on the later ones and on the render.
- In a reel, make the slot ACROSS the cut: from before the line to about 0.5 s into the next shot, so the snap and its 11 settle frames land on the new shot and the slot ends plain.
- Sounds: `assets_fx/impact-bass-short.mp3` on the punch, stock `click` and `whoosh-short` on the snap, all at 0.75x and under the voice.
