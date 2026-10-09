# clone

**What it does:** copies of the speaker spring up from behind the furniture, one per spoken beat, each running a few tenths of a second behind the speaker (a canon). Optional payoff: they all snap into sync with the speaker on one word. Optional exit: they drop back down.
**Job:** hook. Also a spoken list ("this, this, or that").
**Trigger phrases:** "clone me when I say like this, like this" / "put two more of me behind the couch on these words" / "multiply me on this line".

## Footage it needs, and where it fails
- **Still camera** (tripod, table, floor). Slow gimbal creep is tracked and removed (up to ~40 px). A handheld or walking shot fails: the clones slide on the wall.
- **Wide shot with a piece of furniture behind or beside the speaker** whose top edge has wall above it: sofa back, bed head, counter, desk. The clones stand BEHIND that edge, which hides their legs. Free wall beside the speaker's head, roughly one head-width per clone.
- **Does NOT work on:** handheld close-up selfies (the speaker fills the frame, no room, no edge); armchair or stool shots where the only furniture is the seat under the speaker (a clone beside the speaker would show legs with nothing to stand on); a shot where the speaker stands full-length on an open floor; a moving or zooming camera; a busy or dark wall right behind the clones (they still composite, but the motion-blur clean-up only knows a plain light wall).
- **It cannot seat a same-size copy next to the speaker.** A seated person is ~70% of a 9:16 frame wide with hands out: a full-size copy clips the frame edge and a scaled copy on the same seat floats. Do not promise "three of me on the couch".
- The speaker's gestures decide the layout: the widest pose over the whole slot sets how close to the frame edge a clone can stand.

## Slot inputs
Cutout: **yes** (`assets/subject.webm`, made by `fx_new.py`). `aroll_hi`: no. `words.json`: used by `prep.py` for word hits.
Python: the skill's Python only (numpy, scipy, PIL). No OpenCV.

## CLIP block (top of `build.py`)
| field | what it is | how to find it |
|---|---|---|
| `CLONES[].word_f` | frame the vowel of the trigger word lands on | `work/onsets.txt` "HIT" rows; check against the level bars |
| `CLONES[].x`, `.top` | clone's head centre x and head top y, px | `work/prep/grid_*.jpg`: wall with no red tint; top = the speaker's head top + 60 to 120 |
| `CLONES[].scale` | size vs the speaker, 0.5 to 0.7 | furniture edge should cross the clone between chest and hips |
| `CLONES[].lag` | frames behind the speaker (6 = 0.2 s) | different per clone |
| `SYNC_F` | payoff frame, or `None` | vowel of the payoff word |
| `EXIT_F` | frame the clones drop back, or `None` | reel slot: ~14 frames before the end; stand-alone clip: `None` |
| `OCCLUDER_LINE` | rough points along the furniture top edge, full frame width | read from `grid_000.jpg`, ~10 px accuracy; continue straight through the speaker |
| `LIGHT_FROM` | `'left'` / `'right'` | brighter side of the speaker's face |
| `CAP_X`, `CAPS`, `PUNCH` | caption words with frames, big accent word | chest band, under the speaker's chin, above y 1470 |
| `ACCENT`, `VIGNETTE` | accent colour; vignette (0 in a reel slot) | |

Switches: `SAFE=1` safe-zone guide (snapshots only), `CAPTIONS=0` no caption words, `SFX=0` no sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 20 s: head anchor, widest pose, word hits, grid frames in work/prep/
# edit: look at work/prep/grid_*.jpg and work/onsets.txt, fill the CLIP block in build.py
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 2 to 4 min, heavy: fg.webm + clone_*.webm. Read its report (below)
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 1.2,2.4,3.6
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, per-frame diff vs a-roll, contact sheets, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Snapshot times: 0.15 s after each pop, the payoff, the exit. Change `x`, `top`, `scale`, `lag`, `SYNC_F` or `OCCLUDER_LINE` -> bake again. Change only captions, `word_f` by a frame or two, `EXIT_F` -> `build.py` + render is enough (re-bake if `word_f` moves earlier by more than 1 or `EXIT_F` later by more than 10).

## Read the bake report
- `camera drift`: a few px is normal. Above 40 px it warns: wrong footage.
- `occluder edge snapped on N of 1080 columns`: open `work/bake_debug/occluder_overlay.jpg`, the red area must end exactly on the furniture edge. "large correction" = re-read the points.
- `clone X: seen x A to B`: must stay inside 6..1074 (it says CLIPPED otherwise): move `x` inward or lower `scale`. If the real speaker is cut by the same frame edge (elbow out of frame) a clone may run off that edge too: it says "acceptable, look at it".
- `the speaker's cutout is cut by the source frame edge and that straight cut is in view`: the clone shows a sliced-off elbow in mid-air. Move `x` until the cut end is off-frame or behind the speaker.
- `head hidden by the real speaker`: above ~60% for a stretch means the speaker's body covers that clone's face: move `x` away from the speaker.

## What to look at in the final frames (`work/check/`)
- `sheet_pop_*`: the head is clear of the furniture on the vowel frame, no frame shows a clone before its pop.
- `crop_*` at 1:1: no pale smear where the speaker's moving hand passes over a clone, no halo on the clone, the clone ends cleanly on the furniture edge, the speaker's face is never covered.
- `sheet_payoff`: one soft flash frame, all three in the same pose after it. `sheet_exit` and the last frame: clean a-roll.
- check.py's diff: ~0 before the first pop and after the exit; "unexplained jump" = look at that frame.

## Traps
- "Static" gimbal footage creeps. The track runs only on the band the clones live in, so a table edge or rug at the lens cannot bias it.
- RVM calls motion-blurred hands opaque: fine over the plate, a pale smear over a clone. bake.py caps alpha against a clean plate, only on pixels uncovered one frame before or after (a still, pale palm gets holes otherwise).
- The speaker's raised hands will cover a clone's face for a few frames. That is correct depth. Fix it with `x`, not with layer order.
- PIL treats RGBA specially when filtering and resizing: premultiplied frames are wrapped as `CMYK` (4 plain channels).
- Pop the wrapper, flash the inner div, never the `<video>`. Filter tweens need the same function list at both ends.
- Stage punch (1.04) x clone pop (1.1) on the payoff needs ~20 spare px at the frame edge: the 6..1074 rule covers it.
- In a reel slot keep `VIGNETTE = 0` and set `EXIT_F`, or the cut back to the a-roll pops.
