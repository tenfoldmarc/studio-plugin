# chart-grow (Chart Grow)

**What it does:** a line chart draws itself on the wall BEHIND the speaker: grid, a flat line with small wobbles, then the line kicks up in the accent colour on one spoken word. The room dims a little while it is up.
**Job:** proof (growth, results, "it took off"). **Trigger phrases:** "draw a growth chart behind me that takes off when I say scale", "put a chart behind me on this line", "make the line shoot up when I say X".

## The chart is a claim: shape only by default
A rising line says "this grew". Out of the box it draws a SHAPE and nothing else: no axis numbers, no value labels, no currency, no percentage, no title. `FIGURES`, `X_LABELS` and `TAG` are off. Turn them on only with what the speaker hands you: their own real numbers, the real period names, a word they say. **Never invent, estimate or round up a number.** If they have no figures, the shape is the whole effect. With `FIGURES` the line is drawn to scale from zero, so numbers that do not kick will not look like a kick (build.py warns: then this is the wrong effect, do not bend the numbers).

## Footage it needs
- **Shot:** wide or medium. **Close:** only if a patch of wall about 330 x 280 px stays clear of the speaker for the whole slot; otherwise build.py stops with `NO OPEN WALL` and the effect is left out of that clip.
- **Camera:** still (chart is pinned) or drifting / handheld (chart is glued to the wall by measure.py's own track, numpy only). **Moving** (walking, pans, more than about 16 px per frame) breaks the track.
- **Wall:** beside, above, or both. Best: open wall up and to the right of the head, where the line ends. None = stop.
- **Cutout:** layered (the chart sits between the picture and the cutout) and measured (the chart is placed from it).
- **What breaks it:** tight selfies; hands that fly through the top right during the kick (chart shrinks to open wall or stops); a wall with no texture on a handheld shot (nothing to track: the chart floats); the kick word in the first second of the slot (no flat part to grow from); under 1.5 s of footage after the word.
- Placement: `'behind'` = full safe width, the flat part runs behind the head (that is the depth cue), the turn, the kick and the end point are kept clear of the speaker on every frame (62 / 40 / 70 px if the wall allows, 34 / 26 / 70 px at the tightest). If that does not fit: `'beside'` = a smaller chart on the biggest patch of wall. If that does not fit either: stop.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (cutout REQUIRED), `words.json`, `clip.json`. No `aroll_hi`. Fonts (Inter Tight, Montserrat) and four stock sounds (`whoosh-short`, `pop`, `impact-bass-1`, `sparkle`) come from the template. Python: numpy, scipy, Pillow only.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `KICK` | the word the line takes off on; `('word', 2)` = second time; or a frame number | measure.py prints every word with its measured start frame; `-v` shows the loudness strip |
| `KICK_LEAD` | frames the kick starts before the word | 2 (the line is moving when the word hits) |
| `SHAPE` | height of each point, 0 to 1 | keep the default; flat first, last point highest, kick at least 2.5x the wobble |
| `KICK_FROM` | index of the point it kicks from | 4 with the default 7 points |
| `FIGURES` / `FIGURE_FMT` / `FIGURE_AT` | the speaker's own numbers (one per point), how they read, which points show one | OFF. Only from the speaker, exactly as given |
| `X_LABELS` | period name per point | OFF. Only real ones |
| `TAG` | one spoken word in a pill over the turn | OFF. Never a result like "3X" |
| `SIT` | `'auto'`, `'behind'`, `'beside'` or `(x0, y_top, x1, y_floor)` | leave `'auto'`; by hand only after looking at the snapshot |
| `IN_FRAME` / `OUT_FRAME` | first frame anything shows / frame by which all is gone | 3 and `'auto'` (4 before the end). `None` = the slot ends on a cut and the chart holds to the last frame |
| `DRAW_START` | when the flat part starts | `'auto'`, a word, or a frame |
| `ACCENT` / `LINE` | kick colour / line, grid and label colour | brand colour; never orange, never grey (build.py warns) |
| `DIM` | how far the room falls back | `'auto'` from the measured wall brightness (0.38 to 0.68) |
| `LOCK` | glue to the wall | `'auto'` from the measured camera drift |
| `PUNCH`, `GRADE`, `SFX_LEVEL` | push-in on the kick, CSS grade, sound level | 1.0, `'none'`, 1.0 (the first two off: the main reel does them) |

## Switches
`SAFE=1` safe-zone guide (snapshots only). `CAPTIONS=0` drops `TAG`. `SFX=0` drops the sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" measure.py      # words with measured start frames, where the speaker is, camera still or moving (about 1 minute)
# edit: the CLIP block in build.py: KICK at least. FIGURES, X_LABELS and TAG stay off unless the speaker gave real ones
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0      # prints kick frame, where the chart sits, clearances, every warning starts with !!
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 1.2,3.0,3.6      # use your own times: mid draw, kick + 0.15 s, landing + 0.3 s
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # guide off (it must print "clean")
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, plain first and last frame, kick frame against the word, sound level, sheet, stills, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
A 5 s slot: the cutout takes about 8 minutes, then the whole run order about 4 (measure 1, render 1).

## What to look at (work/check/sheet.jpg, then one full-size still)
- The kick: nothing in the accent colour one frame before the kick frame, clearly rising on the word, landed about 0.45 s later. check.py prints the frame the colour first shows.
- The end point and the whole kick are on open wall, never behind the head or a hand. The flat part may pass behind the head; it must come out again before the turn.
- First and last frame are the untouched picture (check.py prints the difference; with `OUT_FRAME = None` only the first).
- Cutout edge against the dimmed wall: no light rim, hair and fingers intact. A rim on a bright wall: lower `DIM`.
- On screen there is nothing to read unless the speaker gave it. End dot, tag and figures inside the safe zone (top 220, bottom 1470, sides 35, right 100 from y 1155): build.py lists each.
- Handheld: the grid stays on the wall (watch a picture frame or a corner against a grid line through the slot).

## Traps
- Whisper word starts run up to 0.35 s early. Never type them in: measure.py snaps them to the rise of the voice. A word with "no clear rise" needs the `-v` strip.
- The flat line hides behind the head by design, so a cursor and a dashed tracker carry the sweep. Do not "fix" it by lifting the whole line above the head: a thin strip up there reads as flat on a phone.
- A bright wall needs the dim or the line disappears; `'auto'` handles it. Do not set `DIM` under 0.3 on a white wall.
- The line head is one linear keyframe per frame (`perFrame`), worked out in Python. Do not replace it with eased tweens: the dash offset and the dot drift apart.
- The sounds follow the measured voice: build.py turns them down until the loudest sits 8 dB under the speaker's loudest word (a quiet wide-shot voice gets quieter sounds). Nobody has heard the mix until you play it.
- `NO OPEN WALL` is an answer, not a bug: use another effect on that clip. `SIT` by hand is for a speaker who agrees to hide part of the line.
- Text on screen: the speaker's own words and numbers only, no em dashes, never the words "free" or "course".
