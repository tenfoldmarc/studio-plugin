# sticky-text

**What it does:** a tag glued to the speaker's cap, to the side of the speaker's head, or to the speaker's chest. It travels, tilts and scales with the speaker on every frame, so it reads as stuck to the speaker and not floating on the screen.
**Job:** explain (name the thing the speaker is talking about and pin it to the speaker).
**Trigger phrases:** "stick a tag that says X to my cap", "pin a label on my chest that follows me", "put a tag next to my head that moves with me".

## Footage it needs
- **Shot:** medium or close for `cap` and `chest`. Wide works with `head` (beside the speaker); on a wide shot a `cap` tag is wider than the cap (build.py warns).
- **Camera:** still, drifting or moving. Handheld is fine: the tag follows the speaker, not the wall.
- **Wall:** none needed for `cap` / `chest`. `head` needs empty space beside the speaker's head inside the safe zone.
- **Cutout:** always measured (head outline = position and size). Layered over the picture only for `head`, and only while that tag is on.
- **What breaks it:** a hand above or on the speaker's head, a hood or long hair that hides the neck (track.py stops: no head outline), a second person in the cutout, the speaker leaving the frame, a head turn past about 40 degrees (the roll match weakens, the tag keeps the last good angle), plain cloth with hands crossing it for `chest`.
- **Close-up (tight selfie):** `head` has almost no room beside the speaker, so it comes out small or build.py refuses it. Use `cap`: it sits on the cap and is sized from the speaker's head. If the cap is inside the top 220 px, build.py pushes the tag down as far as the brow line, then shrinks it, then stops with a message: use `chest`.
- The tag needs 1.5 s on screen. The slot starts and ends on the plain picture (tags come on at `IN_F` at the earliest and leave 9 frames before the end).

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (cutout: REQUIRED), `words.json`, `clip.json`. No `aroll_hi`. Fonts (Inter Tight 800 / 900, JetBrains Mono) and `pop.mp3`, `whoosh-short.mp3`, `click-soft.mp3` come from the template. Python: numpy, scipy, Pillow only.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `TAGS[i].text` | the words on the tag | caps, 1 to 3 words: what the speaker says or the name of the thing. No invented claims |
| `say` | the spoken word it lands on | as track.py prints it; the onset is snapped to the audio. `''` = lands at `IN_F` |
| `anchor` | `'cap'` (on the cap / forehead, above the brows), `'head'` (beside the speaker's head, tucked behind it), `'chest'` (under the chin) | close-up: `cap`. Wide: `head`. Chest visible above y 1470: `chest` |
| `at` | seconds, overrides `say` | only if the printed onset is wrong |
| `small`, `sub`, `sub_say` | optional small line above the word, optional dark second line under the tag and the word it drops on | default none. Only when the speaker says a second thing |
| `side` | `head` only: `'left'`, `'right'`, `'auto'` | `auto` = the side with more room |
| `offset`, `tilt`, `size` | fine move in px, degrees at the landing frame, size factor on the auto size | leave out first; adjust after the snapshot |
| `out` / `OUT` | seconds a tag / every tag leaves | `None` = 9 frames before the slot ends |
| `IN_F` | first frame a tag may appear | 4 |
| `BROW`, `HEAD_H` | brow line (fraction of head height) and head height / width | defaults; change only if the blue lines in sheet.jpg miss the speaker's brows / chin |
| `TAG_COL`, `INK`, `CREAM` | tag, text, sub text colours | brand colours, never orange |
| `GRADE` | CSS filter on the picture | `'none'` (the reel grades) |

## Switches
`SAFE=1` safe-zone guide (snapshots only). `CAPTIONS=0` drops the `small` and `sub` lines, keeps the tag. `SFX=0` no pop / whoosh.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" track.py      # measure the speaker's head, chest and the word starts (about 30 s); read what it prints
# edit: the CLIP block in build.py, then build with the guide on; fix every line that starts with !!
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 1.0,2.2,3.8      # snapshot at landing + 0.3 s, the middle, and 0.5 s before the end (times in seconds)
PY "SK/scripts/fx_run.py" "<slot>" build.py      # build without the guide, then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # numbers, sheet, lock crops, stills, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
A 4.5 s slot takes about 5 minutes end to end once the cutout exists (track 40 s, render 20 s).

## What to look at (work/check/)
- `lock.jpg`: six crops centred on what the tag is glued to. The tag sits at the same spot on the speaker in each; a tag that swims = weak track (track.py match quality under 0.35).
- `sheet.jpg`: the frame with the biggest head movement is in it. Tag above the blue brow line (`cap`) or under the blue chin line (`chest`); eyes, nose and mouth never covered. Nothing past the red lines.
- check.py prints which frames differ from the a-roll: frame 0 and the last frame must be plain.
- `head`: the cutout edge over the tag is clean, no light rim, no double edge (double edge = cutout frame drift).

## Traps
- Whisper word starts are 0.1 to 0.3 s off: use `say` (track.py snaps it to the audio, good to about 3 frames). If the tag lands early or late in the render, set `at=` in seconds.
- A swinging camera that takes the speaker's cap into the top 220 px for a moment rules out `cap` and `head` for the whole span (build.py says so). `chest` still works, or cut the slot shorter.
- Chest roll is damped on purpose (median, long smoothing, within 8 degrees of the head): cloth folds and a low camera fake a roll.
- Position comes from the silhouette, roll from a template match against one reference frame. Optical flow on a head drifts and broke on the demo; a face-pose point slid 40 px against the cap.
- Smoothing is light on purpose (position 0.8 frames, roll and size 1.6). More and the tag lags the head.
- The safe-zone fix is one constant shift, never a per-frame clamp (a per-frame clamp unsticks the tag).
- Snapshots seek loosely during the entrance: judge landing timing on frames from the real render.
- On screen: the speaker's words only, no made-up names or numbers, no em dashes, no orange.
