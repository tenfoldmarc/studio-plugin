# before-after

**What it does:** the raw clip plays, a comparison line with a round handle peeks in on the lead-in word, eases back and waits beside the head, then sweeps across on the payoff word and leaves the edited version of the same frames (grade, soft shade, caption words, slow push-in, optional word behind the head). Two tags ride the line.
**Job:** proof. **Trigger phrases:** "do a before/after wipe on this line", "show the raw clip turning into the edit".

## Footage it needs
- **Shot:** wide, medium or close. **Camera:** still, drifting or moving (both sides are the same frames, nothing can slide). **Wall:** none needed.
- **Cutout:** only measured (head position decides where the line waits, the handle and caption height); layered only when `PUNCH` is set. A slot made with `--no-cutout` (cheaper) still runs: give `REST` an x by eye or it does one straight sweep, and `PUNCH` is left out.
- **What breaks it:** the payoff word in the first 0.3 s of the slot; less than 1.5 s of slot after the sweep (the after look has no time to be seen, build.py warns); a head so wide there is no place for the line to wait (it falls back to one sweep); a line that says nothing about a change (then it is decoration, not proof).

## Where the after side comes from
1. **Made here (default, `AFTER = None`).** The same a-roll with `AFTER_GRADE`, `AFTER_SHADE`, `CAPS`, `PUSH`, optional `ACCENT` / `PUNCH`. No hand work, one render.
2. **Your own finished version.** Copy the file into `after/` in the slot, set `AFTER = 'after/<file>'`, run `prep_after.py`. It must be the SAME frames: same take, 9:16, starting on the slot's first frame, covering the whole slot, no punch-in, reframe or speed change (captions and graphics on it are fine). Its sound is ignored, the voice is the a-roll's. `prep_after.py` prints the frame offset (not 0: it tells you the `AFTER_SHIFT` to set) and an outline match (under 0.33: it does not line up, use mode 1). `CAPS`, `PUNCH`, `AFTER_GRADE`, `PUSH` do nothing in this mode, and `OUT` cross-fades your file away (burned-in captions fade mid-word: prefer `OUT = None` and end on a cut).

## Slot inputs
`assets/aroll.mp4`, `words.json`, `clip.json`, `assets/subject.webm` (optional, see above). No `aroll_hi`. Fonts and `whoosh-short.mp3` / `pop.mp3` come from the template. numpy and Pillow only.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `COMMIT` | payoff word, the line sweeps across on it | a word or phrase from `measure.py`'s list, `('word', 2)` for the 2nd time the speaker says it, or seconds |
| `PEEK` | lead-in word, the line peeks in and waits | a word 0.7 s or more before `COMMIT`; `None` = one straight sweep |
| `REST` | x where the line waits | `'auto'` (measured: 70 px off the head, off the caption, tags readable); a number; `None` |
| `SWEEP` | seconds the sweep takes | 0.5; 0.4 if the next word comes fast |
| `LABELS` | the two tags | `('before', 'after')` or the speaker's own two words; `None`. Never a claim or number the speaker does not say |
| `LABEL_IN`, `LABEL_Y` | when the first tag pops in, top of the tags | `'auto'`, 232; change only on a build.py warning |
| `AFTER`, `AFTER_SHIFT` | own-file mode | see above |
| `AFTER_GRADE`, `AFTER_SHADE` | the look of the after side | a CSS filter / `True`. This grade IS the effect; it leaves with `OUT` |
| `PUSH` | push-in on the after side after the sweep | 1.045; 1 = off |
| `CAPS`, `CAP_Y` | caption lines on the after side | `'auto'` (from words.json, lower case), or a list of lines with one entry per spoken word in order (fix Whisper's spelling here); `None` |
| `ACCENT` | one caption word in yellow with underline and sparkles | a word the speaker says after the sweep; default `None` |
| `PUNCH` | a word the speaker says, big behind the speaker's head | the payoff word; needs the cutout; default `None` |
| `HANDLE_Y` | height of the handle | `'auto'` |
| `OUT` | when the after look eases off | `'auto'` (default: last 0.6 s, the slot ends on plain footage); seconds; `None` = the slot ENDS ON A CUT with the look on (only as the last thing before a cut or the end of the reel) |

## Switches
`SAFE=1` safe-zone guide (snapshots only). `CAPTIONS=0` no caption words, accent or punch word (the tags stay). `SFX=0` no whooshes / pop.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" measure.py      # words with measured starts and where the head is, then edit the CLIP block in build.py
PY "SK/scripts/fx_run.py" "<slot>" prep_after.py      # ONLY when AFTER names your own file (skip it otherwise): makes assets/after.mp4 and checks it lines up
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0      # prints the wait position, sweep times, caption lines and every warning (!!)
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 0.1,2.0,3.0      # use your own times: tag in, line waiting, mid sweep, after look
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, plain edges, both sides while the line waits, sheet, stills, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
A 5.5 s slot takes about 4 minutes once the slot exists (render under 1 minute); making the slot with a cutout adds the matte, `--no-cutout` adds nothing.

## What to look at in the final frames (work/check/sheet.jpg)
- Frame 0 is the plain picture. With `OUT` set the last frames are plain too (check.py prints the first and last touched frame).
- While the line waits it is beside the head, never on the face; no caption letters cut in half at the line; both tags fully readable.
- Mid sweep: one clean edge, the picture does not jump at the line (a jump = the two sides are not the same frames).
- After the sweep the difference must read at phone size. If it does not, use a stronger `AFTER_GRADE` or add `PUNCH`.
- Captions sit under the chin, nothing readable above y 220, below y 1470, within 35 px of the sides.

## Traps
- `mask-image` / `clip-path` do not render reliably: the after side is an `overflow:hidden` box moved to the line with its content moved back by the same amount.
- Every layer that follows the line is sampled per frame in Python and written as linear keyframes. Separate eased tweens drift a pixel or two and the edge tears.
- The box stops at x 0 while the line carries on off-screen, or the right 80 px shows BEFORE again.
- The push-in starts only when the sweep is done: the after picture must not move while the line is on screen.
- Two `<video>` tags on one file get merged by the renderer (lint: `duplicate_media_discovery_risk`): build.py copies the a-roll to `assets/aroll_b.mp4` for the after side. Every video needs an explicit `z-index`.
- Never tween opacity on `#aclip` (it carries the keyframed x): the whole after side vanishes from frame 0. The ease-off fades `#afade` inside it.
- `data-duration` is floored to the ms (5.167 renders one frame too many).
- Whisper word starts are 0.1 to 0.3 s off: name the word and let `measure.py` snap it; type seconds only if a snapshot shows it is wrong.
- Text on screen is the speaker's own words, spelled the speaker's way: no numbers, results or claims the speaker did not say.
