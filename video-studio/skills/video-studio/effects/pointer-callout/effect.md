# pointer-callout

**What it does:** callout cards that stay put, each tied to a point on the speaker (head, shoulder, hand, chest) by a thin line that stretches and swings with them on every frame.
**Job:** explain (name the 2 to 4 things the speaker lists, one card per thing, each landing on its word).
**Trigger phrases:** "put callout cards on these three things and tie them to me with a line that follows me", "label the things I list and connect them to me", "pointer callouts on this line".

## Footage it needs
- **Shot:** wide or medium is best (clear background beside or above the speaker). Close works with 1 or 2 short cards tied to `head_left` / `head_right`.
- **Camera:** still, drifting or moving. The cards stay put on screen, the line end follows the speaker. A camera that swings hard makes the head sweep the frame and leaves less room.
- **Wall:** beside or above helps (cards go on clear background first). With none, cards sit over the body, never over the head.
- **Cutout:** only measured (head outline, where the body is, the hands). Nothing is layered over the picture.
- **Best when** the speaker moves or points: a hand that travels makes the line visibly follow. A still speaker gives a static diagram.
- **What breaks it:** a tight selfie with a swinging camera (the head fills the safe zone: build.py stops and says how many cards fit, often 1 or 2), a hood or long hair hiding the neck or a hand on the head (track.py stops: no head outline), a second person in the cutout, the speaker leaving the frame. Hands: gloves, bare arms the same colour up to the shoulder, or skin-coloured clothes confuse the hand finder (use head / shoulder / chest).
- Each card needs 1 s on screen. The slot starts and ends on the plain picture: cards come on at `IN_F` at the earliest and everything is gone 6 frames before the end.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (cutout: REQUIRED), `words.json`, `clip.json`. No `aroll_hi`. Fonts (Inter Tight 800) and `pop.mp3`, `click-soft.mp3` come from the template. Python: numpy, scipy, Pillow only. The effect ships no pictures and needs none from the buyer: only their own words for the cards.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `CARDS[i].text` | the words on the card | the speaker's own name for the thing, 1 to 3 words (one long text shrinks every card: none is wider than half the frame). Never a number, result or claim they do not say |
| `say` | the spoken word the card lands on | as track.py prints it; `'this#2'` = the second "this". `''` = one after the other from `IN_F` |
| `anchor` | what the line is tied to: `head`, `head_left`, `head_right`, `chest`, `shoulder_left`, `shoulder_right`, `hand_left`, `hand_right` (as seen on screen) | track.py lists the ones that exist, their travel in px and whether they stay in the safe zone. Pick the ones that move |
| `side` | where the card sits: `'left'`, `'right'`, `'auto'` | `auto` = the clearest spot near its anchor |
| `icon`, `sub` | icon tile (`check`, `image`, `script`, `launch`, `spark`, `none`) and the small detail under the text (`lines`, `thumbs`, `progress`, `none`) | what suits the thing; `none` for a plain card |
| `at`, `pos` | optional: seconds (overrides `say`), `(left, top)` px to place one card by hand | only after looking at the snapshot |
| `IN_F`, `OUT_F` | first frame a card may appear, frame everything is gone by | 4, `None` (6 frames before the end) |
| `DONE_SAY` | optional word on which every dot pulses and `progress` bars complete | `''` = off |
| `SIZE`, `FLOOR` | card size (`'auto'` = as large as the open space allows) and the smallest readable size | leave; a number for `SIZE` only to match another slot |
| `ACCENT`, `CREAM`, `INK` | line / dots / icon tile, text, card | brand colours, never orange |
| `GRADE` | CSS filter on the picture | `'none'` (the reel grades) |

## Switches
`SAFE=1` safe-zone guide (snapshots only). `SFX=0` no pop sounds. `CAPTIONS=0` is accepted and changes nothing (the effect has no caption words). `DEBUG=1` prints why a card found no spot.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" track.py      # measure the head, the tie points, the open space and the word starts (about 30 s); read what it prints
# edit: the CLIP block in build.py, then build with the guide on; a line starting with !! is a stop or a warning to act on
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 3.6,4.5      # snapshot 0.6 s after the last card lands and 0.5 s before the end (seconds; build.py prints the landing frames)
PY "SK/scripts/fx_run.py" "<slot>" build.py      # build without the guide, then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # numbers, sheet, lock crops, stills, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
A 5 s slot takes about 4 minutes end to end once the cutout exists (track 25 s, build 2 s, render 25 s).

## What to look at (work/check/)
- check.py numbers: frame count matches, frame 0 and the last frame plain, 0 changed pixels outside the safe zone and inside the face, each card first seen within 3 frames of its word.
- `sheet.jpg`: no card or line over the blue head box from the brows down, nothing past the red lines, cards do not touch, lines do not cross.
- `lock.jpg`: one row per card. The dot sits on the same spot of the speaker in each crop. A dot that wanders = weak track: switch that card to `head` or a shoulder.
- Text reads at phone size (`renders/<slot>-phone.mp4`). build.py prints the text height in px: under 40 is small.

## Traps
- No room is a result, not a bug. "no room for 3 cards: 2 fit" means drop a card, shorten the text or tie lines to `head_left` / `head_right`. Do not lower `FLOOR` to squeeze them in.
- `!! over the body` in the layout line: there is no clear background, the cards cover clothes or hands. Look at the snapshot before rendering.
- Hands are found by skin colour sampled from the speaker's own face. When a hand is hidden or under y 1470 the line rests on that shoulder and travels back when the hand returns. Under 50% found (track.py says so): prefer a shoulder.
- A hand that sweeps across the body leaves its card far away: the line gets long and crosses the torso (never the face). If that reads messy, tie that card to a shoulder.
- Whisper word starts are 0.1 to 0.3 s off: `say` uses the start snapped to the audio (good to about 3 frames). Card early or late in the render: set `at=` in seconds.
- A point that leaves the safe zone gets one constant nudge (never a per-frame clamp, that unsticks the dot). Too far out = build.py stops and lists the points that are inside.
- The line travel is computed per frame in Python: a `stroke-dashoffset` draw-on snapped from hidden to full in the renderer. The dot sits exactly on the track, the spring is only in the curve: a lagging dot reads as bad tracking.
- Snapshots seek loosely during an entrance: judge landing timing on frames from the real render.
- On screen: the speaker's words only, no made-up names or numbers, no em dashes, no orange.
