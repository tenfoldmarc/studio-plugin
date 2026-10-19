# dot-counter

**What it does:** a row of dots pops in over the chest, one per item, when the speaker says how many things are coming ("3 things", "5 steps"). Filled dots are done, rings are still to come, so a later slot can show progress (two of three filled on step two).
**Job:** explain. The "here are N things" beat, and the step markers after it.
**Trigger phrases:** "pop a dot for each thing", "show 3 dots when I say 3 things", "progress dots on each step".

## Footage it needs, and where it fails
- A spoken count from 2 to 8 ("three", "5"), or COUNT typed in for a progress slot.
- Any framing, any camera. Chest band; above the head on a tight selfie; declines when there is room for neither.

## Adapting to the footage
- wide / medium: chest band. tight selfie: above the head. Bright wall: the dots keep a soft shadow; set `ink` darker if they still wash out.

## Slot inputs
An OVERLAY effect (`"layer": "overlay"`): the final build is transparent graphics, `hf render` writes `renders/<slot>.webm`, and the reel lays it over its own footage (grade, cuts and punch-ins stay). `SAFE=1` builds show the footage under it for the snapshots.
`assets/aroll.mp4`, `words.json`, `clip.json`, the reel's `layout.json`. No cutout, no extra packages.

## CLIP block (top of build.py)
| Field | What it is | How to get it |
|---|---|---|
| `COUNT` | how many dots | `None` = the number said in the slot |
| `FILLED` | how many are filled | `None` = all; fewer for progress |
| `T_IN`, `STEP` | first pop, seconds between pops | `None` = when the number is said; 0.08 |
| `T_OUT` | when the row cuts out | `None` = 0.6 s after the counted word |
| `Y`, `DOT` | place, size | `None`, 46 |
| `SOUND` | soft click per dot | 0.15; 0 = silent |

STYLE block: `ink` is the dot colour (the reel's caption colour).
**Switches:** `SAFE=1`, `SFX=0`, `CAPTIONS=0` accepted and ignored.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # prints count, timing, the snapshot times and the caption window
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, work/check/sheet.jpg, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
In a reel: `fx_add.py` hides the reel's captions only while this effect's words are up (build.py writes that window to `work/reel_captions.json`). Look at both edges of the slot in the final render.

## What to look at in the final frames
- The first dot pops on the number; the row is centred and clear of the chin and the red area.

## Traps
- "one of the things" is not a count: leave the effect out when the number is a passing one.
