# chip-row

**What it does:** as the speaker lists things, an outlined pill pops in for each one, in a row under the captions. The reel's own captions keep running above the row.
**Job:** explain. Short lists: options, ingredients, tools, prices.
**Trigger phrases:** "pop a pill for each thing I list", "chips under the captions", "show the options as tags".

## Footage it needs, and where it fails
- A spoken list of 2 to 4 short things (1 to 3 words each on screen).
- Any framing, any camera. The row sits under the caption line on the chest band; on a tight selfie with no room under the chin it moves above the head; declines when there is room for neither.

## Adapting to the footage
- wide / medium: under the reel's caption line. tight selfie: above the head. Long items: the row shrinks to fit the safe width.

## Slot inputs
An OVERLAY effect (`"layer": "overlay"`): the final build is transparent graphics, `hf render` writes `renders/<slot>.webm`, and the reel lays it over its own footage (grade, cuts and punch-ins stay). `SAFE=1` builds show the footage under it for the snapshots.
`assets/aroll.mp4`, `words.json`, `clip.json`, the reel's `layout.json`. No cutout, no extra packages.

## CLIP block (top of build.py)
| Field | What it is | How to get it |
|---|---|---|
| `CHIPS` | `[(text, sec)]`, one pill per thing, in the speaker's words | the words build.py prints: the second each thing is said. Required |
| `T_OUT` | when the row cuts out | `None` = the slot end |
| `Y` | centre of the row | `None` = just under the reel's caption line |
| `SIZE` | chip text size | 30 |
| `SOUND` | soft click per chip | 0.12; 0 = silent |

STYLE block: `small_font`, `small_weight`, `ink` (text and outline) and `card` (pill fill) from the reel's look. Colours as 6-digit hex.
**Switches:** `SAFE=1`, `SFX=0`, `CAPTIONS=0` accepted and ignored.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# edit: CHIPS in the CLIP block from the words build.py prints
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # prints each chip, the row place and the snapshot times
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, work/check/sheet.jpg, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
In a reel the captions stay on (slot.json says keep). Look at one REEL snapshot with a caption up: the caption line must not touch the row. A caption style with very big punch words can reach it: then set `Y` lower or the slot later.

## What to look at in the final frames
- Each pill pops on its word; the row is centred, inside the safe width, clear of the chin and of the captions.
