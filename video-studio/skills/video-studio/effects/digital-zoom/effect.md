# digital-zoom

**What it does:** word-timed digital zooms on one continuous shot that aim at the speaker's face, not the frame centre: a slow creep in, a hard snap punch with real zoom blur, a whip pull-back. Any number of moves, in any order.
**Job:** hook / retention. Gives a single take two or three "camera angles" without a cut.
**Trigger phrases:** "punch in on my face when I say X", "slow zoom into me on this line", "add digital zooms on the key words", "zoom in, then snap back out when I say Y".

## Footage it needs, and where it fails
- One continuous shot (no internal cuts) with the speaker's face visible the whole time. Wide, mid and close-up selfie all work; tripod or handheld both work (the face track holds the speaker, the room moves instead).
- Best with `assets/aroll_hi.mp4` (make the slot with `--hi`): 1728 wide is lossless to 1.6x, 1440 wide to 1.33x. With a 1080 source every zoom is an upscale: build.py caps the scale at `MAX_UPSCALE` (1.5x) and prints that it did. Keep 1080 clips to a creep of about 1.15 and a snap of about 1.35.
- Fails or looks wrong when: the speaker's face leaves the frame or turns fully away (the track falls back to the matte and wobbles); a hand covers the speaker's eyes for more than a few frames; the head already fills the frame (nothing left to punch into); the shot has a cut in it.
- A close-up leaves little room under the chin once zoomed: use `CAPTIONS=0` or one short line (see clearance below).

## Slot inputs
cutout `assets/subject.webm`: yes (head position). `assets/aroll_hi.mp4`: optional, strongly preferred. `words.json`: only as a guide for `onsets.py`. Python: the skill's Python only (numpy, PIL), no extra packages.

## CLIP block (top of build.py, between the CLIP markers)
| Field | What it is | How to find it for a new clip |
|---|---|---|
| `ZOOMS` | list of `zoom(t_start, t_land, scale, kind)`, kind `creep` / `snap` / `pull`, times as `F(frame)` | frames from `onsets.py`. creep lands 2 frames after the vowel; snap lands ON the stressed vowel and starts 3 frames before; pull starts on the word's onset, lands ~9 frames later. Optional per zoom: `drift=` (0 = hold still), `over=`, `sfx=False` |
| `EYE` | where the speaker's eyes sit on screen when tight | (540, 640) wide and mid shots; about (540, 620) on a close-up. build.py prints "aim: ... fully framed from N x": start snaps above N |
| `FOLLOW` | how tightly the camera follows the speaker's head (sigma, frames) | 5 default; 3 for handheld; 8 to 10 if a tripod background swims |
| `AIM` | manual eye point `(frame, x, y)`, default `None` | only if `work/track_check.jpg` shows the cross off the speaker's eyes |
| `MAX_UPSCALE` | how far past lossless a scale may go | leave at 1.5 |
| `CAPS` | caption groups `(last frame, [(top px, size, [(frame, word, 'y' or '')])])`, size `'sm'` / `'lg'` / `'big'` or a number of px | word frames from `onsets.py`; tops and sizes from the printed clearance (it warns: too close to the chin, below 1470, too wide) |
| `WHOOSH` | whoosh volume on each snap (0 = none) | 0.26 sits under the speaker's voice at normal speech level |
| `GRADE` | CSS grade on the picture | leave, or match the reel |

## Switches (environment variables on build.py)
`SAFE=1` safe-zone guide + eye target + chin line (snapshots only). `CAPTIONS=0` no caption words: ALWAYS in a reel, so the reel's own captions stay on over the zoom in the caption style the buyer picked (the `CAPS` list is only for a stand-alone clip). build.py then prints one "reel captions" line: whether the chin stays clear of the reel's caption band at the tightest zoom. `SFX=0` no whoosh. `GRADE=0` no grade, vignette or flash: use it when the slot is laid into a graded reel, otherwise the look steps at the slot edges. `HI=0` ignore aroll_hi and work from the 1080 a-roll.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 1. onset frame of every word; then edit the CLIP block
PY "SK/scripts/fx_run.py" "<slot>" track.py      # 2. eye track. LOOK at work/track_check.jpg (cross between the speaker's eyes in every tile)
PY "SK/scripts/fx_run.py" "<slot>" build.py GRADE=0 CAPTIONS=0      # 3. camera + index.html. Read the printout: caps, scale per frame, the reel captions line
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 4. assets/zoom.mp4, 1 to 3 min (PY bake.py --frames 80-90 previews a few frames first)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 5. must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 GRADE=0 CAPTIONS=0
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 1.2,2.9,3.6      # use your own times: one just after each landing
PY "SK/scripts/fx_run.py" "<slot>" build.py GRADE=0 CAPTIONS=0      # 6. guide off again, same switches as the render
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 7. frame count, renders/<slot>-phone.mp4, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Re-bake after any change to ZOOMS, EYE, FOLLOW, AIM or HI; captions, grade and sound only need build.py and the render.

## What to look at in the final frames (work/qa/sheet_*.jpg)
- Each snap: two blurred travelling frames, then a sharp frame ON the stressed vowel. Each creep: motion stops within a frame or two of its word. Each pull: wide and sharp again before the next phrase.
- The speaker's eyes on the `EYE` line in every tight frame, face centred. Zoom blur streaks away from the speaker's face, the speaker's face stays the sharpest thing.
- No caption over eyes to chin, nothing readable above y 220 or below y 1470, right column clear from y 1155.
- First frame identical to the a-roll. Last frame at exactly 1.0x if the list ends with a pull (otherwise the reel cuts back to the wide, which is a choice: build.py prints a note).

## Traps
- Whisper word starts are 1 to 4 frames early or late. Never time a zoom from words.json: use `onsets.py`.
- The top of the head from the matte is not the eye line (it drifts 20 to 30px when the speaker tips the speaker's head). The plate template match fixes that; the matte is only the guard rail. Trust `track_check.jpg`, not the numbers.
- An ease-out "arrives" 4 to 5 frames before its last keyframe. That is why a creep's `t_land` goes 2 frames after the vowel.
- Blur is gated by speed: creeps stay crisp, snaps streak. A creep that covers more than about 0.6x in under 15 frames starts to blur; make it a snap or give it more frames.
- Caption pops with more than 18px of blur show as a grey smudge for a frame. A tween that starts on a word's frame shows nothing on that frame (`T()` starts it 1.4 frames early).
- At 1.0x the crop cannot move, so the aim blends in as the scale leaves 1.0. A snap that starts below the "fully framed" scale also slides the picture and smears the speaker's face for its two travelling frames (build.py prints a note). Fix: let a creep reach that scale first, or move `EYE` nearer to where the speaker's eyes already are. The same slide happens at the end of a pull back to 1.0 when the speaker sits off-centre; it is hidden in the whip.
- The slot render keeps the audio untouched plus the whoosh. If the reel adds its own sound design, render with `SFX=0`.
- Not built: zooming the cutout as well (for words behind the speaker's head during a zoom). It needs a second bake pass over subject.webm with the same camera.json.
