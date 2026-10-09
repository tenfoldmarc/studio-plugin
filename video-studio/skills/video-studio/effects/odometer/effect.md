# odometer

**What it does:** the number the speaker says rolls up digit by digit like a mechanical mileage counter (each digit a drum, vertical motion blur while it spins, a hair of overshoot and a soft tick as it locks on the end of the spoken number), in a dark instrument panel that sits BEHIND the speaker next to the speaker's head. A label writes itself on the speaker's words.
**Job:** proof (years, client counts, revenue, percentages). Only numbers the speaker actually says in the clip.
**Trigger phrases:** "roll the number up like an odometer", "count it up when I say 10 years", "mileage counter on the 100%", "make the stat roll in".

## Footage it needs, and where it fails
- Any framing with free background beside or above the speaker's head: close-up selfie (demo) and wide tripod shot (test) both work. The panel is screen-fixed, so on a handheld clip the wall drifts behind it (reads as a HUD, fine); it is never pinned to the wall.
- Fails when the speaker fills the frame edge to edge for the whole span (build.py stops with "no free spot"), and when the number is said in the first 0.3 s of the slot (no time to roll: start the slot earlier).
- The number must be said cleanly once. Mumbled or doubled numbers: set `lock` by hand.
- One or two counters per slot. A third works but the corner chips pile up.
- Needs 1.5 s after the lock to be read; label words need their own spoken moments or `None`.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (cutout: REQUIRED, the panels go between plate and cutout), `words.json`, `clip.json`. No `aroll_hi`. Fonts (Inter Tight 900, Montserrat 600) and `click-soft.mp3` / `whoosh-short.mp3` come from the template. No extra Python packages (numpy + PIL from the skill's Python).

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `COUNTERS[i].text` | what locks on screen: digits + optional prefix/suffix (`10`, `$200K`, `87%`, `100s`, `1,250`) | the number the speaker says, written the way a viewer expects |
| `say` | the spoken words of the number as words.json has them (`'hundred percent'`, `'10'`) | `measure.py` prints the words; the lock = measured end of the last one |
| `lock` | seconds, overrides `say` | only if `say` is not found or the "measured end" column looks wrong |
| `label` | `[(WORD, when), ...]`, yellow line under the drums; wraps to a second line when wider than the drums | `when` = a spoken word, seconds, or `None` (right after the lock). The speaker's words, caps, no invented claims |
| `label2` | optional extra line(s), default `None`; each inner list rolls over the one before | only when the speaker lists more things after the number |
| `sit` | `'auto'`, `'right'`, `'left'`, `'above'`, or `(x, y)` | leave `'auto'`; force a side if the snapshot looks crowded |
| `size` | `'auto'` or a scale (1.0 = 150 px drums) | leave `'auto'` (biggest that keeps digits and label clear of the speaker, max 1.5) |
| `then` | what this counter does when the next arrives: `'dock'` (corner chip), `'stay'`, `'out'` | `'dock'` for two proofs in a row |
| `ROLL` | seconds of spin before the lock | 0.44; 0.35 for a number said very fast |
| `OUT` | seconds when every panel leaves, or `None` | `None` if the slot ends on a cut, else about 0.25 s before the slot ends |
| `DOCK_CORNER` | where the chip goes | `'auto'` |
| `GRADE` | CSS filter on plate + cutout | `'none'` when the main reel grades |

## Switches
`SAFE=1` safe-zone guide (snapshots only). `CAPTIONS=0` panels with numbers only, no label words. `SFX=0` no ticks / whoosh.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" measure.py      # words with measured start / end, where the speaker's head is
# edit: the CLIP block in build.py
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # prints lock frame, panel position, label times, warnings (!!)
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 0.2,1.0,2.0      # use: roll, lock+0.1, lock+0.6, last 0.1 s
PY "SK/scripts/fx_run.py" "<slot>" build.py      # guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, text-behind-the speaker test, tick timing, sheet, stills, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
A 4 s slot takes about 6 minutes end to end (render about 1 minute).

## What to look at in the final frames (work/check/sheet.jpg and lock_*.jpg)
- The lock frame printed by build.py: last drum sharp or one frame from it, yellow flash on the digits, suffix popping in. Two frames earlier it must still be a blur.
- Frame 0 is a clean plate (the panel enters at 0.02 s at the earliest), so the slot cuts in clean.
- The speaker's head overlaps only an EMPTY corner of the panel. No digit, suffix or label word behind the speaker in any frame (check.py prints the worst frame).
- Cutout edge over the dark panel: no light rim, no double edge (a double edge = cutout frame count drift).
- Nothing readable above y 220, below y 1470, within 35 px of the sides.

## Traps
- Whisper word times: starts are off by up to 0.35 s and it splits fast words in the wrong place. Never type them in; `measure.py` snaps them to the audio (nearest dip, not deepest: the deepest dip around "ten" is the stop inside the word).
- `click-soft.mp3` has 48 ms of silence before the transient and is a double click: build.py starts it early and trims it. Any other tick file needs its own `SFX_LEAD` / `SFX_TRIM`.
- Tick volume follows the speaker's measured voice level (`VOICE_REF`); check.py prints how far under the speaker's voice it landed (aim for 12 dB or more).
- Directional blur is an SVG `feGaussianBlur stdDeviation="0 N"` set per frame from the strip's speed. CSS `blur()` is isotropic and looks like defocus.
- The roll is one `tl.set` per frame (`frame/30 - 0.002`), not a GSAP ease: exact spring, lock on the frame.
- Each strip carries one extra number below the target, or the overshoot shows an empty drum.
- "Panel grows a line" is scaleY on the background only. Never tween height or letter-spacing (lint).
- Decode the cutout with `-c:v libvpx-vp9` BEFORE `-i` or the alpha is lost (measure.py does).
- Text on screen: the speaker's words only, no em dashes, never "free" or "course", no numbers the speaker did not say.
