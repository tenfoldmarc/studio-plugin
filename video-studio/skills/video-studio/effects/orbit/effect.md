# orbit

**What it does:** the speaker's own reel covers circle around them in a ring. On the far side the cards pass behind the speaker, on the near side they pass in front at chest height, always under the face.
**Job:** hook ("I post every day", "all of these came from one skill", "you need edits like this"). Works anywhere: set `F_IN` and `F_OUT` and the frames before and after are untouched a-roll.
**Trigger phrases:** "put my reels in orbit around me", "make my reels circle me", "orbit".

## First step: the covers are the user's own
Ask for a folder of their reel cover images (jpg / png / webp, at least 4, 6 is the default ring; 9:16 is best, anything else is cropped to 9:16). Copy them into `covers/` in the slot. The effect ships no covers. **No covers from the user = leave the effect out**, do not invent or borrow any. Cards carry no numbers unless the user gives real view counts for `COUNTS`: never estimate or round up a count.

## Footage it needs
- **Shot:** wide or medium, speaker centred, with the chin above about y 1000 so a card fits between chin and y 1470. One continuous shot while the ring is up.
- **Camera:** still or drifting (the ring follows the head once it travels more than 10 px). Not for a moving, walking camera.
- **Wall:** none needed. The ring floats in the room; whatever is behind the speaker stays as it is.
- **Cutout:** layered. Far cards sit under `assets/subject.webm`, near cards over it; the ring itself is measured from the cutout's alpha.
- **What breaks it:** a close-up selfie (the face reaches too low, `prep.py` stops and says so); a speaker who fills the frame width (cards swap from behind to in front while still over an arm, `prep.py` warns); a speaker far off centre; a hand held above the head (it is read as the head); a weak cutout (hair or fingers lost: far cards show through them); a second person in the shot.

**Slot inputs:** cutout yes, `aroll_hi` no. Python: numpy and Pillow for `prep.py` and `onsets.py`; `build.py` needs nothing. No OpenCV.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `COVERS` | folder with the user's cover images | default `covers` inside the slot; file-name order is ring order |
| `COUNTS` | optional real view counts per file | from the user's own insights; `{}` = no numbers, no play icons |
| `CARDS` | cards on the ring, 4 to 8 | 6 |
| `F_IN` | frame the ring lands on | `onsets.py`: onset of the word (5 or later) |
| `F_OUT` | frame the plain picture is back, or `None` | onset of a later word, at least 45 after `F_IN`, at most frames - 2 |
| `CAPS`, `CAP_Y` | the effect's own caption words and their top | spoken words, frames from `onsets.py`; `None` = measured, yellow box on `work/ring.jpg` |
| `CX`, `CY`, `RX` | ring centre and half width | `None` = measured from the cutout; type px only to overrule what `work/ring.jpg` shows |
| `TILT` | ring height / width | .33; smaller is flatter |
| `CARD_W`, `NEAR`, `FAR` | card width at the front, size at front and back | 190, 1.0, .6; `prep.py` shrinks the card by itself if the ring does not fit |
| `FACE_GAP` | px kept clear between near cards and the face box | 30 |
| `REV`, `DIR`, `PHASE` | seconds per turn, direction, start angle | 5.2, 1, .35 |
| `FOLLOW` | ring follows the head when the shot drifts | `True` |
| `CROP_Y`, `FAR_DIM` | which part of a non 9:16 cover is kept, far card brightness | .5, .75 |
| `GRADE` | optional look while the ring is up | `None` = off |
| `VOICE`, `REF`, `SOUNDS` | speaker audio on/off, frame on the check picture, sounds | defaults |

**Switches:** `SAFE=1` draws the safe-zone guide (snapshots only). `CAPTIONS=0` drops the effect's caption words. `SFX=0` drops its sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# first: ask the buyer for a folder of their own reel cover images (their saved covers, or covers exported from their profile) and copy them into <slot>/covers/ (fx_new.py --buyer-files <folder> does the copy). No covers from the buyer = no Orbit: leave it out and say so
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # copy the user's reel covers into ./covers  (create the folder; 4 or more images); 1. word onsets as frames -> F_IN, F_OUT, CAPS in build.py
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. cards + ring measured from the cutout (seconds)
# edit: LOOK at work/ring.jpg (red face box on the whole head, no yellow near card on it, no card in the red border), read the WARNING lines, fix the CLIP block and run prep.py again until it is right.
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0      # 3. page with the safe guide
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 1.0,1.5,2.0,2.5,3.0,3.5
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # 4. clean page (no guide), then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Any python with numpy and Pillow works in place of the venv path. Pick snapshot times inside the ring's time on screen.

## What to look at in the final frames
- Frame 0, the frame before `F_IN - 4`, the frame of `F_OUT` and the last frame: plain picture, no card, no dark edge.
- The frame of `F_IN`: the first cards are up and clearly visible on the word.
- Six frames spread over the hold: no near card on the face (chin included), far cards really hidden by head and shoulders, never drawn over them.
- At full size, one frame with a far card next to the hair or a hand: clean cutout edge, no card showing through. At the left and right ends of the ring a card changes from behind to in front beside the body, not on an arm.
- Everything inside the safe zone (top 220, bottom 1470, sides 35, right 100 from y 1155). Numbers on cards only if `COUNTS` was filled. The render has exactly the `frames` of `clip.json` (ffprobe it).

## Traps
- The face box is measured from the silhouette, not from a face detector: it runs from the top of the head (cap, hair) to the narrowest row above the shoulders. A high collar, a hood or a hand at the chin hides the neck; then the box is 1.35 head-widths tall. If the red box on `work/ring.jpg` ends above the chin, raise `FACE_GAP` or type `CY`.
- Near cards cross the chest, so they cover gesturing hands for a moment. That is the look; if a hand gesture carries the line, pick another moment.
- `prep.py` must be run again after any change to `F_IN`, `F_OUT`, `CARDS` or the ring fields: `build.py` refuses a `work/ring.json` measured for other frames.
- With `CX`, `CY` or `RX` typed in, nothing is corrected for you: the warnings are the only guard. `F_OUT = None` keeps the ring to the last frame: only when the reel cuts away there.
- Sounds are stock template sounds at 0.75x template volume: one whoosh and a soft pop in, one whoosh out.
