# depth-scatter

**What it does:** the opening words land one by one over the chest at different sizes and heights; each earlier word goes soft and dim as the next one lands, like focus racking past them. Then they all cut out together.
**Job:** hook. The first 1 to 2 seconds of a reel, a 3 to 6 word opener.
**Trigger phrases:** "scatter my opening words", "make the hook words land at different sizes", "depth words on the hook".

## Footage it needs, and where it fails
- A spoken opening phrase of 2 to 6 words with no long pause in it. Any framing, any camera: nothing is tracked.
- Wide and medium shots: the cluster sits on the chest band under the chin. Close-up selfie with the chin low in the frame: it moves above the head by itself (build.py prints it). No room above or below the face: it declines with a one-line reason.
- Busy, bright room: the words carry a soft shadow; on a white wall set `ink` darker in STYLE.

## Adapting to the footage
- wide / medium: chest band from layout.json, two loose rows.
- tight selfie close-up: above the head when the chin leaves no room; declines when neither fits.
- still or handheld camera: no difference (screen-fixed words).
- off-centre speaker: the cluster stays centred on the frame; set `Y` if it lands on a hand.

## Slot inputs
An OVERLAY effect (`"layer": "overlay"`): the final build is transparent graphics, `hf render` writes `renders/<slot>.webm`, and the reel lays it over its own footage (grade, cuts and punch-ins stay). `SAFE=1` builds show the footage under it for the snapshots.
`assets/aroll.mp4`, `words.json`, `clip.json`, and the reel's `layout.json` (read through clip.json's project). No cutout, no extra packages.

## CLIP block (top of build.py)
| Field | What it is | How to get it |
|---|---|---|
| `WORDS` | `None` = the slot's first phrase; or `[(text, sec)]` | the words build.py prints, with their slot seconds |
| `T_OUT` | when all words cut out | `None` = 0.25 s after the last word |
| `Y` | centre of the cluster | `None` = automatic |
| `SIZES` | sizes in turn, px | put the biggest on the word that matters |
| `SOFT` | blur of the earlier words | 3; 0 = flat |

STYLE block: the reel's caption look (font, weight, tracking, case, ink). Match it before the first build.
**Switches:** `SAFE=1` red guide (snapshots only), `SFX=0` (it has no sounds), `CAPTIONS=0` accepted and ignored.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # prints each word, size and place, the snapshot times and the caption window
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, work/check/sheet.jpg, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
In a reel: `fx_add.py` hides the reel's captions only while this effect's words are up (build.py writes that window to `work/reel_captions.json`). Look at both edges of the slot in the final render.

## What to look at in the final frames
- No word overlaps another; the newest word is sharp, the older ones soft.
- Nothing on the face, nothing in the red area of the SAFE snapshot.
- The words cut out together, and the reel's captions pick up right after.

## Traps
- Long words at the biggest size can run wide: lower that entry in `SIZES`.
- A first word that starts before the slot's first frame is skipped: start the slot 0.1 s before the hook.
