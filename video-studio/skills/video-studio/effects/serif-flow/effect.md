# serif-flow

**What it does:** the picture cuts to a flat deep-ink card. A small [BRACKET CAPS] title sits on top and a process builds down the card one node at a time: serif italic nodes whose letters surface out of order, bold sans nodes that cut on as they are said, thin lines drawing down between them. Then it cuts back to the speaker.
**Job:** explain. Cause and effect, a pipeline, "this leads to this leads to this".
**Trigger phrases:** "draw the process on a card", "show it as a flow", "one video becomes five, on a card".

## Footage it needs, and where it fails
- A line that describes 2 to 4 steps or stages, said within about 3 to 6 seconds.
- Any framing, any camera: the card replaces the picture, so the face is never covered.
- The card is a hard cut in and out. Start the slot on a word or a cut of the reel, end it on a cut or a new sentence.

## Adapting to the footage
- Any shot: the card is full frame. Long node text shrinks the whole stack to fit the safe width; 4 nodes shrink it to fit between the safe lines.

## Slot inputs
An OVERLAY effect (`"layer": "overlay"`): the final build is transparent graphics, `hf render` writes `renders/<slot>.webm`, and the reel lays it over its own footage (grade, cuts and punch-ins stay). `SAFE=1` builds show the footage under it for the snapshots.
`assets/aroll.mp4`, `words.json`, `clip.json`. No cutout, no layout needed, no extra packages.

## CLIP block (top of build.py)
| Field | What it is | How to get it |
|---|---|---|
| `TITLE` | the bracket caps line on top | the speaker's subject, short; `''` = none |
| `NODES` | 2 to 4 dicts, top to bottom: `{'kind': 'serif', 'text', 'at'}` or `{'kind': 'sans', 'parts': [(text, sec)]}` | the speaker's words, with the seconds build.py prints. Required |
| `T_IN`, `T_OUT` | card in and out | 0.0 and `None` (= slot end) |
| `SERIF`, `SANS` | node sizes | 118, 82 |
| `SOUND` | soft whoosh as the card cuts in | 0.22; 0 = silent |

STYLE block: `serif_font` / `serif_italic` for the serif nodes, `font` / `big_weight` for the sans nodes and title, `ink`, and `card` for the card colour.
**Switches:** `SAFE=1`, `SFX=0`, `CAPTIONS=0` accepted and ignored.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# edit: TITLE and NODES in the CLIP block
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # prints each node and its time, the snapshot times and the caption window
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, work/check/sheet.jpg, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
In a reel: `fx_add.py` hides the reel's captions only while this effect's words are up (build.py writes that window to `work/reel_captions.json`). Look at both edges of the slot in the final render.

## What to look at in the final frames
- Each node appears on its word, each line draws just before the node under it, all inside the safe lines.
- Frame 0 (unless T_IN is 0) and the frames after T_OUT are the plain picture.
