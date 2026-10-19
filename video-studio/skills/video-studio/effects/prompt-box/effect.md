# prompt-box

**What it does:** a glass input field appears over the chest with a small label notched into its top border, and what the speaker says they type ("edit it in my style") types itself in, with a caret that blinks when it stops.
**Job:** explain. Any line where the speaker tells an AI or an app what to do.
**Trigger phrases:** "type my prompt on screen", "show the prompt in a box", "a text box with what I tell Claude".

## Footage it needs, and where it fails
- A spoken instruction of up to about 60 characters (one or two lines in the box).
- Any framing, any camera. Chest band; above the head on a tight selfie; declines when there is room for neither.

## Adapting to the footage
- wide / medium: chest band. tight selfie: above the head. Long text: smaller type, two lines. Bright wall: the box fill is the dark `card` colour at 42%, so the text keeps its contrast.

## Slot inputs
An OVERLAY effect (`"layer": "overlay"`): the final build is transparent graphics, `hf render` writes `renders/<slot>.webm`, and the reel lays it over its own footage (grade, cuts and punch-ins stay). `SAFE=1` builds show the footage under it for the snapshots.
`assets/aroll.mp4`, `words.json`, `clip.json`, the reel's `layout.json`. No cutout, no extra packages.

## CLIP block (top of build.py)
| Field | What it is | How to get it |
|---|---|---|
| `TEXT` | what types in, the speaker's own words | required |
| `LABEL` | small label in the top border | the step or "prompt"; `''` = plain border |
| `T_TYPE`, `T_DONE` | first and last letter | `None` = when the first word of TEXT is said / when its last word ends |
| `T_OUT` | when the box cuts out | `None` = 0.4 s after T_DONE |
| `Y`, `WIDTH`, `SIZE` | place and size | `None`, 740, 50 |
| `SOUND` | soft key clicks while typing | 0 (quiet look) |

STYLE block: the reel's caption look for the typed text, `small_font` for the label, `ink` and `card` for the box.
**Switches:** `SAFE=1`, `SFX=0`, `CAPTIONS=0` accepted and ignored.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# edit: TEXT and LABEL in the CLIP block
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # prints typing window, place, the snapshot times and the caption window
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, work/check/sheet.jpg, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
In a reel: `fx_add.py` hides the reel's captions only while this effect's words are up (build.py writes that window to `work/reel_captions.json`). Look at both edges of the slot in the final render.

## What to look at in the final frames
- The caret follows the last typed letter, never sits at the far end of the box.
- Typing finishes as the speaker finishes the line; the box is clear of the chin and the red area.
- No real product's logo or interface: it is a plain field.
