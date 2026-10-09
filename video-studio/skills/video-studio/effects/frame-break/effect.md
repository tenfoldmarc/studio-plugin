# frame-break

**What it does:** the whole video shrinks into a floating card that looks like a phone post, over a blurred copy of the room. The speaker's head rises over the card's top edge and reaching hands pass its sides, then the card grows back to full frame.
**Job:** hook (also a CTA beat: "follow", "comment WORD"). Set `F_IN` and `F_OUT`: the frames before the shrink and from `F_OUT` on are untouched a-roll. With `F_OUT = None` the card stays and the effect is meant to END ON A CUT (last shot of a reel, or the reel cuts away on the slot's last frame).
**Trigger phrases:** "shrink the video into a card and let me break out of it", "make me pop out of the frame", "frame break".

## Nothing is shown that the user did not give
The card carries icons only: no like, comment or share counts, ever. No name row, no line of text, no Follow button unless the user gives their own handle (`NAME`) and wording. Never make up a handle, a count or a comment author.

## Footage it needs
- **Shot:** medium or wide, ONE continuous shot, 3 to 6 s, head in the upper half with some room above it. Best with a hand gesture that reaches sideways at chest height or higher.
- **Camera:** still, drifting or moving all work (picture and cutout move together; nothing is tracked).
- **Wall:** none needed.
- **Cutout:** layered (`assets/subject.webm` is drawn over the card) and measured (head, body outline, hands).
- **What breaks it:** a tight close-up (the head fills the frame, so the card ends up under the chin and little rises out of it); a head touching the top of the frame (nothing to stand above the edge); a cutout that loses hair or fast fingers (the lost part stays inside the card and the edge of the pop-out flickers); two people; a hood or long hair over the shoulders (no neck to find: set `HEAD`). Hands that never leave the body: still works, as a head pop-out only, and `prep.py` prints that.

**Slot inputs:** cutout yes, `aroll_hi` no. Python: numpy and Pillow for `prep.py` and `onsets.py`; `build.py` needs nothing.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `F_IN` | frame the card has landed | `onsets.py`, "onset" of the word; 23 or later (the shrink takes 21 frames) |
| `F_OUT` | frame the picture is full frame again, or `None` | onset of a later word, 45+ after `F_IN`, 2+ before the last frame |
| `HEAD_OUT` | how much head stands above the card edge, in head heights | `'auto'` = 0.3 (medium shot) to 1.0 (wide shot); 1.5 = head and shoulders |
| `CARD` | card rectangle in a-roll px, or `None` = measured | read off `work/check.jpg` (1/3 size) only if the cyan box is wrong |
| `SCALE` | card size on screen | `'auto'` fills the safe zone; a number only shrinks it |
| `HEAD` | `(top_y, chin_y)` by hand | only when the green box is not on the head |
| `SIDE_POP` | hands may pass the card's sides | `False` = only what is above the top edge comes out |
| `ICONS` | like / comment / share icons on the card | no counts either way |
| `NAME`, `CARD_LINE` | the user's handle and one short line | ask the user; `''` = not drawn |
| `FOLLOW_AT` | frame of "follow": the Follow button is tapped | needs `NAME`; `None` = off |
| `COMMENT` | `('WORD', frame)`: keyword pops out of the comment icon | the word the speaker says, its onset; `None` = off |
| `LIKE_AT` | frame the heart fills | `None` = off |
| `TILT`, `GRADE`, `SOUNDS` | card tilt (0 = flat), css filter (`''` = off, default), sounds on/off | defaults |

**Switches:** `SAFE=1` draws the safe-zone guide (snapshots only). `CAPTIONS=0` drops the text on the card (`CARD_LINE` and the `COMMENT` word). `SFX=0` drops the sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 1. word onsets as frames -> F_IN, F_OUT (and FOLLOW_AT ...)
# edit: the CLIP block in build.py
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. measure + bake (about 1 min). LOOK at work/check.jpg:. cyan card under the head, green box on the head, pink = what comes out. Wrong? change HEAD_OUT / CARD / HEAD,. try with prep.py and the argument "measure" (5 s), then run prep.py once more without it
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # 3. page with the safe guide
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 0.0,1.5,2.0,3.0,4.0      # use your own times
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 4. clean page (no guide), then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # 5. plain frames at both ends vs the a-roll + work/final_sheet.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.

## What to look at in the final frames
- Frame 0, the frame before the shrink, and (with `F_OUT`) the frame of `F_OUT` and the last frame: plain picture, same as the a-roll, no rim, no dark edge.
- The frame of `F_IN`: card landed and sharp, icons arriving. The face is never covered by an icon, the name row or the comment word.
- Head at full size: the part above the card edge has a clean outline against the dark room and does not slide against the part inside the card. Hands: fingers that pass the side edge are whole, not cut by a straight line.
- With `SAFE=1`: card, icons and text inside the safe zone (top 220, nothing below 1470, sides 35, right 100 from y 1155). `build.py` prints the card's screen box.
- The render has exactly the `frames` of `clip.json` and the speaker's audio (ffprobe it).

## Traps
- Changing `F_IN` or `F_OUT` changes which frames are measured: `build.py` refuses to run until `prep.py` has run again.
- The cutout is only kept down to a line under the shoulders (yellow lines on the check sheet). Below it, everything outside the card is hidden on purpose, so a hand gesturing at belly height is clipped by the card like the rest of the picture.
- Shoulders wider than the card fade out softly just outside its sides. If that reads as a ghost, give a wider `CARD` or set `SIDE_POP = False`.
- A hand raised above the head makes the card smaller on screen (everything that rises out has to fit under the top 220 px). Pick the span of the slot so a stray high wave is not in it.
- `GRADE` stays on for the whole slot, including the plain frames at both ends. Leave it off unless the reel is graded the same way.
- Sounds are the stock template ones at 0.75x volume: a whoosh in, a whoosh back, a soft click on the follow tap, a pop on the comment word.
