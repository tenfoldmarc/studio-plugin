# spotlight

**What it does:** on a key word the room goes dark and out of focus, the speaker stays lit and sharp in a pool of light, the key words land big (the first tucked behind the head, the next in front on the chest), then the lights come back up.
**Job:** explain (one phrase that has to hit, with a clear in and out).
**Trigger phrases:** "put a spotlight on me when I say X", "kill the lights on this word", "lights down on X, back up on Y".

## Footage it needs
- **Shot:** wide, medium or close, ONE continuous shot of one person, 3 to 6 s. Best on a wide or medium shot with wall above and beside the head (the dark room is what sells it). On a close shot it still works: the pool tightens to a glow around the head.
- **Camera:** still, drifting or handheld all work. The dark room is made from the live picture frame by frame (the speaker is painted out of every frame before the blur) and the pool of light follows the measured head. Nothing is a still plate.
- **Wall:** none needed. Some background above or beside the head gives the first word a place.
- **Cutout:** layered (`assets/subject.webm` is cleaned for a dark room and drawn over it) and measured (head, neck, free room).
- **What breaks it:** a cutout that loses hair, fingers or a prop (the lost part goes dark with the room) or keeps a piece of background (it stays lit: `GAP`, `FLECKS`, or pick another span); a hand raised above the head or two people (the head is taken as the highest thing in the cutout); a hood or long hair over the shoulders (no neck to find, check the green box); a head that fills the frame (no room for words: `CAPTIONS=0` or leave the effect out); a speaker who bobs a lot (words are fixed on screen, so the head slides against the word behind it).

**Slot inputs:** cutout yes, `aroll_hi` no. Python: numpy, scipy, Pillow for `prep.py` and `check.py`; numpy for `onsets.py`; `build.py` needs nothing (Pillow if present, for exact word widths).

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `F_IN` | first frame the lights move | `onsets.py`: onset of the first key word minus 1. 3 or later |
| `F_OUT` | first frame the lights come back, or `None` | onset of the first word said in the normal room; 17+ after `F_IN`, 14+ before the last frame. `None` = dark to the last frame: the slot must END ON A CUT |
| `KEYWORDS` | `(text, frame, place, size, colour)` per word, only words the speaker says | frame = the word's onset. place `'auto'` (first word `'above'`, the rest `'chest'`), `'above'`, `'left'`, `'right'`, `'chest'`, or `('back' or 'front', centre x, baseline y)`. size `'auto'` or px |
| `DARK` | how dark the room gets outside the pool | 0.16; 0.10 nearly night, 0.30 dim. It keeps its colour, never grey |
| `BLUR` | px the room goes out of focus | 11 |
| `POOL` | size of the pool of light | 1 = measured from the head; 0.8 = tighter, darker room |
| `EDGE_CHOKE` | px the cutout edge is pulled in | 1.5. Bright halo on `work/check_edge.jpg`: 2.5. Thin hair eaten: 0.8 |
| `EDGE_SPILL` | px of the outer edge recoloured from inside | 4. Pale line around the speaker: 6. 0 = off |
| `PUSH` | slow push-in while the lights are down | 1.045; 1 = none |
| `GAP` | polygon of background the cutout kept (between the legs) | still camera only; read the points off a frame. `None` = off |
| `FLECKS` | `(first frame, last frame, (x0, y0, x1, y1))`: bright speck showing through a hole in the speaker | only if one shows on the check pictures. `[]` = off |
| `GRADE`, `SOUNDS` | css filter on the whole slot (`''` = off, default); sounds on / off | defaults |

**Switches:** `SAFE=1` draws the safe-zone guide (snapshots only). `CAPTIONS=0` drops the key words (lights only; the reel's own captions carry the words). `SFX=0` drops the sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 1. prints word onsets as frames
# edit: the CLIP block in build.py: F_IN, F_OUT, KEYWORDS
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. measures and bakes (1 to 3 min). LOOK at work/check_edge.jpg (full size) and work/check_sheet.jpg
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # 3. places the words and prints each ink box. It stops if a word is on the face or outside the safe zone
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 1.0,2.4,2.7,3.4,3.7      # your own times: before F_IN, both words on, mid hold, mid release, after
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 4. the clean page (no guide), then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # 5. frame count and plain frames at both ends, writes work/final_sheet.jpg and work/final_edge.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.

## What to look at in the final frames
- `work/check_edge.jpg` and `work/final_edge.jpg` at full size, darkest moment: around the head and hair no bright halo and no pale line; the hand has all its fingers; nothing of the speaker is left dark and nothing of the room is left lit inside the outline.
- Frame 0, the frame before `F_IN`, and (with `F_OUT`) from 8 frames after `F_OUT` to the last frame: plain picture, `check.py` says ok. No dim, no push-in left on.
- Darkest frame: the room is dark blue and soft but still has colour, the speaker is in full colour, skin not red and not blown out. No grain.
- Each key word appears on its word, is one the speaker says, never covers the face, and with `SAFE=1` sits inside the safe zone (top 220, nothing below 1470, sides 35, right 100 from y 1155).
- The render has exactly the `frames` of `clip.json` and the speaker's audio.

## Traps
- `prep.py` bakes `F_IN`, `F_OUT`, `DARK`, `BLUR`, `POOL`, the edge fields, `GAP` and `FLECKS` into the two videos: change one and `build.py` refuses to run until `prep.py` has run again. `KEYWORDS`, `PUSH`, `GRADE`, `SOUNDS` only need `build.py`.
- A blurred copy of the picture still contains the speaker and glows around the sharp cutout. That is why the room is painted out per frame; never swap `room_dark.mp4` for a css blur on the a-roll.
- The cutout switches on hard on the first moving frame and dissolves off over the last 3 frames of the return; the light itself is baked per frame. A fade-in of the cutout pumps the speaker's brightness.
- A tween that starts on frame n still shows its start value on frame n: `build.py` starts everything one frame early, so a key word's `frame` is the first frame it is visible.
- The word behind the head is tucked only a little when the head moves a lot. If the head hides too much of it, give it by hand: `('back', x, baseline y)` a bit higher, or `'left'` / `'right'`.
- `'chest'` words are in front of the speaker and cover a hand that gestures there. Wide shot: the word sits over the lap. Close shot: a third of the way down the chest.
- `GAP` is a fixed polygon: on a moving camera leave it `None` and choose a span where the cutout is clean.
- Sounds: `assets_fx/impact-bass-short.mp3` as the lights fall, stock `whoosh-short` as they return, both at 0.75x and under the voice.
