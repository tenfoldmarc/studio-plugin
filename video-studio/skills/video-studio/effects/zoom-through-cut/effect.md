# zoom-through

**What it does:** turns a hard cut between two shots into one continuous camera move: the camera dives into a point on the speaker, the picture streaks with true radial motion blur, passes through the dark of the speaker's clothes, and the next shot opens out of the same point and brakes into place. 18 frames centred on the cut, audio stays a straight cut.

**Job:** transition, anywhere in a video (new set-up, new look, new location, a "like this" reveal). Works on the hook too.

**Trigger phrases:** "zoom through the speaker into the next shot", "make that cut a zoom-through", "dive into the speaker's shirt and come out in the next clip".

**Footage it needs:** two shots with a hard cut, the speaker in frame in both. Still or handheld camera both work. Best when the speaker wears something dark and plain on the torso (the dive point). Each shot needs at least `HALF + 2` frames (11 by default) and the line after the cut should run 1.5s or more so the landing can breathe.
**Where it fails:** the dive point lands on skin, a hand or a busy print (the pass-through goes pink or noisy: move the point); a shot shorter than 11 frames; a cut that sits mid-word (the whoosh and the blur fight the word: move the cut to the gap).

**Slot inputs:** `assets/aroll.mp4` holding BOTH shots, `clip.json` with `"cut_frames": [K]`, cutout `assets/subject.webm` (only for the automatic dive points and caption height; with hand-set values `--no-cutout` is fine). No `aroll_hi`. Python: the skill's Python only (numpy, Pillow, scipy), no extra packages.

## CLIP block (top of build.py)
| field | what it is | how to get it |
|---|---|---|
| `CUT` | first frame of shot B | `None` = clip.json `cut_frames` (two_shot.py writes it) |
| `HALF` | transition frames each side of the cut | 9 = 18 frames; auto-lowered if a shot is too short |
| `POINT_A` / `POINT_B` | px the camera dives into (last A frame) / opens from (first B frame) | `None` = prep.py picks the darkest flat patch on the speaker's torso (for A: torso or lap, dark all around, clear of the speaker's hands); check `work/measure.jpg`, else read x,y off that image (it is half size: double them) |
| `DEPTH`, `SHARP`, `ROLL` | zoom travelled, ease steepness, camera roll in degrees | defaults suit most cuts; `DEPTH 40` is gentler |
| `CREEP_A` / `CREEP_B` | slow push-in before / after | 1 = off (use 1 when the main reel already moves the shot) |
| `GRADE_A` / `GRADE_B` | optional baked look per shot | `None` unless the two shots should look different |
| `CAP_A` / `CAP_B` | caption block per shot: `style`, `top`, `lead`, `punch`, `tail` as `(seconds, 'word')` | times from words.json, confirmed on the audio; `None` = no block; `top: None` = just under the speaker's chin from prep.py |
| `WHOOSH_VOL` | template volume of the one whoosh | 0.30 (x0.75 applied); its peak is placed on the cut |

**Switches:** `SAFE=1` safe-zone guide, `CAPTIONS=0` no caption blocks (the main reel captions it), `SFX=0` no whoosh, `BAKE_WORKERS=n` bake processes (default 4).

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # measure, then LOOK at work/measure.jpg (yellow cross on dark flat fabric, green line under the speaker's chin)
# edit: the CLIP block in build.py (caption words and times from words.json, points only if the cross is wrong)
PY "SK/scripts/fx_run.py" "<slot>" bake.py sheet      # bake: half-size contact sheet first (about 30s), full bake when it looks right (2 to 4 min); look at work/bake/sheet.jpg
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # writes assets/plate.mp4
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0      # compose, check, render
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <6 to 8 times incl. the frames around the cut>
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0
PY "SK/scripts/fx_run.py" "<slot>" hf render
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
In the main reel: add `CAPTIONS=0` (and `SFX=0` if the reel has its own whoosh) to both `build.py` calls, and lay the render over the a-roll for exactly these frames. The slot's audio is the two shots with a straight cut, each at its own level: two different recordings can differ by several dB, so use the main reel's audio (or match the levels) rather than the slot's.

## What to look at in the final frames
- The dive goes into fabric, and the cut frame is dark with shot B as a small bright burst at the point. No pink or skin-coloured full frame.
- Around shot B while it is small: soft rays of its own border colours fading to dark. Never a mirrored copy of the room, never a hard rectangle.
- The first frame after the transition (`K + HALF`) is the clean shot, same framing as the a-roll plus the slow creep. No jump, no dark edge strip.
- Captions: the A block is gone by the cut, the B block lands with the picture, both clear of the speaker's face and inside the safe zone at rest.
- Frame count equals clip.json `frames`; the whoosh sits in the gap between the two lines and under the speaker's voice.

## Traps
- Aiming at the speaker's cap, face or hands puts skin across the frame for 4 frames. Aim at the tee, jacket, a dark jumper or dark trousers. The speaker gestures: check the cross against the LAST frame of shot A, which is the one in measure.jpg.
- Do not fog shot A earlier (`FOG_FROM` below the A scale on the cut frame): the cut frame turns into a flat colour card.
- prep.py reads the head from the cutout silhouette; a hood, a hand on the chin or a raised arm in front of the neck can fool it. The jpg shows it at once: set `POINT_*` or `top` by hand.
- If the block has no room under the speaker's chin (tight close-up) it is dropped with a message. Let the main reel caption that shot.
- A staggered `fromTo(..., immediateRender:false)` shows the late letters early: letters are parked with `gsap.set` and animated with `tl.to`.
- The plate has no audio; the speaker's voice comes from `assets/aroll.mp4`. Do not re-encode or re-time the a-roll after baking.
- `hyperframes snapshot` can show the next shot a frame early at the cut. Only the sheet from the final mp4 proves the transition.
