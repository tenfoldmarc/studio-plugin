# stat-stack

**What it does:** a number the speaker says lands huge over the chest, and a tiny caps line under it swaps on the words that follow ("14,000" / FOLLOWERS / IN 7 DAYS). Hard cuts, no bounce.
**Job:** proof. Results, prices, counts: any number that IS the point of the line.
**Trigger phrases:** "make the number huge", "put 14,000 big on screen", "stat on this line".

## Footage it needs, and where it fails
- A spoken number the speaker really said. Never a number they did not say, never a made-up result.
- Any framing, any camera. Chest band under the chin on wide and medium shots; above the head on a tight selfie when the chin is low; declines when there is room for neither.

## Adapting to the footage
- wide / medium: chest band. tight selfie: above the head. Long numbers ("$1,250,000") shrink to fit the width.
- still or handheld: no difference.

## Slot inputs
An OVERLAY effect (`"layer": "overlay"`): the final build is transparent graphics, `hf render` writes `renders/<slot>.webm`, and the reel lays it over its own footage (grade, cuts and punch-ins stay). `SAFE=1` builds show the footage under it for the snapshots.
`assets/aroll.mp4`, `words.json`, `clip.json`, the reel's `layout.json`. No cutout, no extra packages.

## CLIP block (top of build.py)
| Field | What it is | How to get it |
|---|---|---|
| `NUMBER` | the big text, as said | `None` = the first spoken word with a digit |
| `T_IN` | when it lands | `None` = when that word starts |
| `SUBS` | `[(TEXT, sec)]` small caps lines under it, each replacing the last | `None` = the word said right after the number; `[]` = none |
| `T_OUT` | when it cuts out | `None` = the slot end |
| `Y`, `SIZE` | place and size | `None`, 176 |

STYLE block: the reel's caption look. `big_weight`, `big_tracking` and `accent` set the number.
**Switches:** `SAFE=1`, `SFX=0` (no sounds), `CAPTIONS=0` accepted and ignored.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # prints the number, the sub lines, the snapshot times and the caption window
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, work/check/sheet.jpg, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
In a reel: `fx_add.py` hides the reel's captions only while this effect's words are up (build.py writes that window to `work/reel_captions.json`). Look at both edges of the slot in the final render.

## What to look at in the final frames
- The number lands on the frame the word starts; each sub line swaps on its word.
- Clear of the chin, clear of the red area.

## Traps
- Whisper splits "14,000" into "14" ",000" in a raw transcript; the reel's cleaned words.json has them merged. Type `NUMBER` yourself when it looks wrong.
