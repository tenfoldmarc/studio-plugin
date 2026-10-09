# green-screen

**What it does:** the speaker is cut out and shrunk to the bottom of the frame (left, right or centre) and the whole frame behind them becomes the thing they are talking about: a video, a picture, or a screenshot shown as a rounded card on a plain wallpaper. The "reacting to it" look.
**Job:** explain / proof (the viewer sees the subject full screen while the speaker keeps talking over it).
**Trigger phrases:** "put me in front of this clip", "green screen me over this video", "show this behind me while I talk about it".

## First step: the background is the user's own material
Ask for the file(s) and copy them into `bg/` in the slot: video (mp4 / mov / webm) or picture (png / jpg), at least one. The effect ships no media. No material = no Green Screen: `prep.py` and `build.py` stop with a message, leave the effect out.
When the background is someone else's footage, set `credit` to their handle (`'@name'`): a pill shows it top left. Never invent a handle. Only material the user may show.

## Footage it needs
- **Shot:** medium is best (head, shoulders and chest in frame). Wide works: the speaker is enlarged to the same head size, and above 1.3x the cutout turns soft (`prep.py` warns). Close fails when less than about one head height of body shows below the chin: the build stops with "too tight".
- **Camera:** still, drifting or moving. The room is gone while the effect is up, so camera motion does not show; a speaker who travels across the frame travels across the background too.
- **Wall:** none needed.
- **Cutout:** layered and measured. `assets/subject.webm` is the speaker on screen, and head top, chin, head width and the row where the body is cut off (desk edge, table, frame bottom) are read from its alpha. `aroll_hi` is not used.
- **Breaks it:** a cutout that loses hair or fast hands (the new background shows every matte fault), a body that touches the left AND right edge of the source frame (straight edges show), two people in the shot, slots under 36 frames between in and out, a background with its own burned-in captions at head height.
- **Edges:** frame 0 and the last frame are the untouched clip (shrink in from `IN_FRAME`, grown back by `OUT_FRAME`), so the slot drops onto the a-roll anywhere. Exception: `HARD_IN` / `HARD_OUT` open or end the slot ON the green screen, for a slot that starts or ends on a cut of the reel.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `BG_DIR`, `BG` | the folder, and one dict per background item | `[]` = every file in name order, evenly spaced. Keys: `file`, `at`, `start`, `mode`, `side`, `size`, `reframe`, `focus`, `credit` |
| `BG[..]['at']` | frame or spoken word a later item hard-cuts in on | `prep.py words`; `'this#2'` = second time the word is said |
| `BG[..]['mode']` | `'fill'` (covers the frame) or `'card'` (rounded card on the wallpaper) | `'auto'`: tall material fills, wide material (screenshots) becomes a card |
| `BG[..]['reframe']`, `['focus']`, `['start']` | `(scale, x, y)` slide of a fill item; which part survives the 9:16 crop; first second of a video | look at `work/layout.jpg`: the subject must not be behind the speaker |
| `IN_FRAME`, `OUT_FRAME` | frame or word the effect starts on / the plain picture is back on | defaults 2 and `None` (2 frames before the end) |
| `HARD_IN`, `HARD_OUT` | no shrink in / no grow back | only where the reel itself cuts |
| `SIDE`, `SIZE` | `'left'`, `'center'`, `'right'`, `'far-left'`, `'far-right'` or an x; `'normal'`, `'small'`, `'big'` | the side the background's subject is NOT on; `'small'` gives it more room |
| `CREDIT`, `WALLPAPER` | handle pill (default `''` = off); CSS background behind a card | neutral dark by default |
| `CAPS`, `CAP_KEY`, `CAP_FIX`, `CAP_WORDS`, `CAP_PLATE` | the effect's own caption words. ONLY for a reel with no caption style of its own: in a reel the slot is built with `CAPTIONS=0` and the reel's captions carry the words | `'auto'` = the speaker's words from words.json; fix mishearings in `CAP_FIX`; yellow words in `CAP_KEY` |
| `BODY_BOTTOM`, `FACE` | manual body cut-off row / head box on the source frame | `None` = measured; set only when `work/layout.jpg` shows them wrong |
| `TRANS`, `PUSH`, `SHADOW`, `GRADE`, `VOICE`, `SOUNDS` | shrink length, push-in, speaker shadow, CSS filter on the cutout, the speaker's audio, sounds | defaults; keep `GRADE='none'` |

**Switches:** `SAFE=1` safe-zone guide (snapshots only), `CAPTIONS=0` no caption words of its own (ALWAYS in a reel that has a caption style: the buyer's style wins), `SFX=0` no sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# first: ask the buyer what goes behind them: their own clip or picture of the thing they are talking about (copy it into <slot>/bg/). When it is someone else's footage, ask for that person's handle and set credit to it; never invent a handle. No material from the buyer = no Green Screen: leave it out and say so
PY "SK/scripts/fx_run.py" "<slot>" prep.py words      # copy the user's file(s) into ./bg; 1. every word with its frame -> edit the CLIP block in build.py
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. measures the cutout, cuts the bg files, work/layout.json + work/layout.jpg (LOOK)
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0      # 3. page with the guide; prints boxes, the --caption-y value, snapshot times
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # 4. guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # 5. frame count, plain edges, cut frames, face / body rows, sheet, stills, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
After ANY change to the CLIP block run `prep.py` again before `build.py` (build.py refuses a stale layout). A 5 s slot takes about 6 minutes after the cutout.

## When the reel captions the slot (CAPTIONS=0, the normal case)
The buyer's style wins: in a reel that has a caption style the slot is built with `CAPTIONS=0` and the reel's own captions stay on, in the buyer's style. `build.py` then prints `fx_add.py --caption-y N`: add the slot with it and the reel's captions move to the line above the speaker's head while the slot plays (the move happens on a caption change, never in mid caption). Look at one reel snapshot inside the slot: a tall caption style may need `SIZE = 'small'` to get more room above the head. The effect's own words (`CAPS`, lowercase) are only for a reel with no captions of its own (caption style `none`): build without `CAPTIONS=0` and add the slot with `--captions hide`.

The reel's normal chest-height captions would land on the shrunk speaker's face. `build.py` prints, and `work/layout.json` holds per item, where words may sit: `cap_top` .. `cap_bottom` (one 76 px line, 42 px above the head), inside `cap_box` (x range), never lower. `face` and `box` are the speaker's face and body on the canvas.

## What to look at (work/check/sheet.jpg)
- First and last frame, the frame before `IN_FRAME` and the frame of `OUT_FRAME`: the plain clip (check.py prints the difference).
- Whole face above the red line (y 1470). No straight cut body edge above the bottom of the canvas once the shrink is done.
- The background's subject is not behind the speaker; every cut lands on its frame; a card ends above the caption line.
- Caption words never on the face; over a bright background they sit on a dark plate. Credit pill present when the footage is not the user's.

## Traps
- The first one or two frames of the shrink show the body's cut-off edge (the speaker is still near full size): normal, it is gone by frame 3.
- The measured chin is the neck line plus the speaker's head movement, so the face box runs a little low on purpose. A hood, long hair or a hand at the face hides the neck: `prep.py` says so, then set `FACE`.
- A desk that cuts the body diagonally: the highest point of the cut is used. If a wedge still shows, lower `BODY_BOTTOM` by 20 px.
- A video shorter than its time on screen holds its last frame (prep warns). HDR phone footage as a background can look washed out: export it as SDR first.
- Whisper mishears names and numbers: read the auto caption lines once, fix them in `CAP_FIX`, or write `CAPS` by hand.
- On-screen words: the speaker's own, no em dashes, no invented numbers, names or handles. Wallpaper stays neutral: no brand colours of a real product.
- Sounds: stock `whoosh-short` only, at 0.75x template volume (in, each cut, out).
