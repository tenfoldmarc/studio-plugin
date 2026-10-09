# sticker (Freeze Sticker)

**What it does:** on one word the picture freezes and the speaker becomes a die-cut sticker (white border around their outline, soft shadow, slight tilt) slapped onto a colour page, with handwritten notes written on around it. The voice runs on under the freeze.
**Job:** CTA (also a punchline beat). The frames before `F_FREEZE` are untouched a-roll. **Default `F_OUT = None`: the slot ENDS ON THE STICKER, so the reel ends or cuts there.** With an `F_OUT` frame the sticker is flung off and the plain live picture is back from exactly that frame (a hard cut).
**Trigger phrases:** "turn me into a sticker on this line", "freeze me into a sticker", "freeze sticker".

## Nothing is shown that the user did not give
The notes are the user's OWN words: ask for them (one or two, 2 to 5 words each). The defaults are placeholders. Never write a number, a result, a handle or a comment keyword the speaker does not say in this clip. No notes from the user = run it with `NOTES = []` (sticker only).

## Footage it needs
- **Shot:** medium or wide is best (head and chest with air around them). A close-up works, with a large sticker and room for one or two short notes.
- **Camera:** still, drifting or moving all work (one frame is frozen; nothing is tracked).
- **Wall:** none needed.
- **Cutout:** layered and measured: the sticker IS the cutout of the freeze frame (`assets/subject.webm`), and its outline places everything.
- **What breaks it:** a freeze frame with motion blur, closed eyes or a hand across the face (pick another frame); a cutout that lost hair, fingers or a sleeve on that frame (dented border: `bake.py` prints "ragged"); a speaker cut by BOTH sides of the frame (the sticker cannot be smaller than the screen, notes get little room); a head cut by the top of the frame (flat top); two people (only the larger one is kept); a tight close-up where the head is over 760 px tall on screen (no room for notes).

**Slot inputs:** cutout yes, `aroll_hi` no. Python: numpy, scipy and Pillow for `bake.py`, numpy and Pillow for `onsets.py` and `check.py`; `build.py` needs nothing.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `F_FREEZE` | frame the picture freezes | `onsets.py`, "onset" of the word; then LOOK at `work/frames.jpg` and move it 1 to 3 frames to the best still |
| `F_OUT` | `None` (default, ends on the sticker) or the frame the live picture is back | onset of a later word, 24+ after `F_FREEZE`, 2+ before the last frame |
| `NOTES` | list of `(text, frame, side)` | the user's words; frame = onset of the word the note lands on, `None` = right after the freeze; side `'auto'`, `'top'`, `'left'`, `'right'`; `*stars*` around a word = accent colour and underline |
| `STAMP` | one short word in a boxed stamp above the first note | the user's word; `''` = off |
| `ARROW`, `TICKS` | arrow from the first note to the body, three small lines by the head | on by default; the arrow is left out when it has no clear path |
| `BACKDROP`, `PAGE` | `'page'` = colour page in `PAGE`; `'footage'` = the frozen picture blurred and dimmed | a colour that sets the speaker off; never orange, never a grey |
| `INK`, `ACCENT` | handwriting colour, colour of starred words | white and butter yellow |
| `SIZE`, `PLACE`, `TILT` | sticker scale, nudge in px, degrees | `'auto'`; change only after looking at `work/check.jpg` |
| `BORDER`, `CHOKE` | border px on screen; px shaved off the cutout edge | 20 and 2; `CHOKE` 3 or 4 if a rim of the room shows |
| `CUT_Y` | straight die-cut across the body at this a-roll y: the sticker floats whole | `None` = the body runs off the bottom of the screen |
| `HEAD` | `(top_y, chin_y)` in a-roll px | only when the green box on `work/check.jpg` is not on the head |
| `GRADE`, `SOUNDS` | css filter on the live frames (`''` = off, default), sounds on/off | defaults |

**Switches:** `SAFE=1` draws the safe-zone guide (snapshots only). `CAPTIONS=0` drops the notes, stamp, arrow and ticks (sticker only). `SFX=0` drops the sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 1. word onsets as frames
# edit: put the word's onset in F_FREEZE (and note frames, F_OUT) in the CLIP block of build.py
PY "SK/scripts/fx_run.py" "<slot>" bake.py frames      # 2. LOOK at work/frames.jpg: eyes open, no motion blur, a good expression. This one still is the whole effect: move F_FREEZE if not
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. bakes the sticker and lays out the notes (5 s). Read its warnings, LOOK at work/check.jpg: border whole, green box on the head, notes clear of the sticker
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # page with the safe guide
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 1.0,1.4,1.5,1.8,2.4      # your own times: just before the freeze, the freeze, landed, each note written
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 4. clean page (no guide), then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.

## What to look at in the final frames
- Frame 0 and the frame before `F_FREEZE`: plain picture. With `F_OUT`: that frame and the last one too (`check.py` prints it).
- `work/final_edge.jpg` at full size: the white border runs unbroken around hair, ears and fingers, no rim of the room inside it, no dent where the cutout lost something.
- Notes: readable, written on their words, never on the sticker, never on each other, inside the safe zone (top 220, nothing below 1470, sides 35, right 100 from y 1155). The body may run below 1470, text may not.
- No straight cut edge of the body visible at the bottom or sides of the screen while the sticker rests.
- The render has exactly the `frames` of `clip.json` and the speaker's audio (ffprobe it).

## Traps
- Any change in the CLIP block (even a note's wording) needs `bake.py` again: `build.py` refuses to run until then.
- The size is measured, not typed: a speaker cut by the frame on both sides forces a size of 1.0 or more. `CUT_Y` above the point where the shoulders leave the frame frees it (head-and-neck sticker that floats).
- A raised hand above the head, a hood or long hair can fool the head finder (green box): set `HEAD`.
- Parts of the cutout not joined to the body on the freeze frame (a hand in the air) are left out, and `bake.py` says so.
- With `F_OUT`, the sticker flies off the top in 6 frames; a body that runs off the bottom shows its straight cut edge for those frames (blurred, by design).
- `GRADE` stays on every live frame, including the plain ones: leave it off unless the reel is graded the same way. Sounds are the stock template ones at 0.75x volume, under the voice.
