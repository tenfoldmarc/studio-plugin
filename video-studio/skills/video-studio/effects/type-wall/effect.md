# type-wall

**What it does:** the room behind the speaker turns into a dark wall of giant words. Rows of one repeated word march sideways in alternating directions, solid and outlined rows taking turns, and every row hard-swaps to the next word on the frame the speaker says it. The row right above the speaker's head says every word as the speaker says it; on the word that matters the whole wall snaps to it, punches in, and that row turns yellow. The speaker stays in front of the wall the whole time.

**Job:** emphasis, anywhere in a video: a hook line, the one sentence a section hangs on, a punchline, a call to action. Best on a short line (2 to 4 seconds) with one word that matters.

**Trigger phrases:** "put giant words behind me that change as I talk", "type wall on this line", "turn the wall behind me into words".

**Footage it needs:** a still camera (tripod, or a phone leaning on something), the speaker from the chest or wider, with clear room above the speaker's head: the speaker's head top at y 250 or lower in the 1080x1920 frame. A clean person cutout (the slot maker cuts the speaker out with the good matting model). 1 to 2 seconds of footage after the last word so the wall can be read.
**Where it fails (say so and offer another effect):**
- Tight selfie with no wall: head near the top of the frame, shoulders edge to edge. The words have nowhere to show. `prep.py` warns ("no room above the speaker's head", "open wall under 40%").
- Moving or handheld camera: the wall is locked, so the speaker wobbles on it like a sticker, and a `KEEP` shape comes unstuck from the furniture. `prep.py` warns over 8 px of drift. (One slow settle with `KEEP = []` is fine: the demo clip has one.)
- A face in a painting, poster or screen behind the speaker can end up in the cutout and float on the wall. `prep.py` reports a second shape; look at those frames.
- Long words: at the default size a word over about 7 letters is wider than the frame. Split it or skip it.

**Slot inputs:** `assets/aroll.mp4`, cutout `assets/subject.webm` (required), `clip.json`, `words.json`. No `aroll_hi`. Python: the skill's Python for `prep.py` (numpy, scipy, Pillow); `build.py` and `onsets.py` run on plain python3. Ships its own font and one sound in `assets_fx/`.

## CLIP block (top of build.py)
| field | what it is | how to get it |
|---|---|---|
| `PHRASES` | what the wall says: 1 to 3 UPPER CASE words per phrase, each `(frame, 'WORD')`; `'hit': True` on the phrase that matters | words from `words.json`, frames from `python3 onsets.py` (column "swap"). The first word rides in with the wall |
| `IN_FRAME`, `OUT_FRAME` | frame the wall arrives (hard cut from the room, rows whip in) and frame the room is back | `IN_FRAME` = frame of the first wall word (0 = up from the start); `OUT_FRAME = None` = stays to the end of the slot |
| `KEEP` | shapes of the real picture kept in front of the wall (the sofa, desk or counter the speaker sits at) | `[]` = wall fills the frame. Otherwise read corner points off `work/measure.jpg` (labels are full-size px), a few px inside the furniture edge |
| `FS` | letter size in px | 205; go to 150 to 180 when there is little room above the speaker or a word is too wide |
| `ACCENT_Y`, `HEAD_GAP` | where the yellow row's letters end | `None` = measured, 14 px above the highest point of the speaker's head |
| `XC` | `{row: x}` to move where a row's word is centred on a swap | `{}` = measured (the widest gap the speaker leaves in that row); row numbers are printed by `build.py` |
| `GROUND`, `INK`, `ACCENT` | wall colours, letter colour, yellow row colour (6-digit hex) | defaults are the approved look; keep the wall dark |
| `VOL_IN`, `VOL_HIT`, `VOL_SWAP` | entry whoosh, low hit on the hit word, soft whoosh on a new phrase | 0 turns one off |

A 1 word phrase fills every row. A 2 or 3 word phrase builds down the wall: all rows say word 1, then every 2nd (or 3rd) row turns to word 2, then word 3, so the finished wall reads the phrase top to bottom.
**Switches:** `SAFE=1` draws the safe zone, the head-top line (blue) and the `KEEP` outline (green). `SFX=0` drops the sounds. `CAPTIONS=0` changes nothing: the wall is the caption, so the main video should not caption these frames.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # measure the speaker, then LOOK at work/measure.jpg (yellow line on top of the speaker's head, blue tint = everywhere the speaker goes)
PY "SK/scripts/fx_run.py" "<slot>" onsets.py -v      # 3. word frames from the audio; read the per-frame loudness strip for every wall word
# edit: the CLIP block in build.py: PHRASES always, KEEP when the speaker sits on or behind something.
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # build with the guide on, lint, look at snapshots (one per swap, one at the end); read its row table and any "!!" lines
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times in seconds, comma separated>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # render
PY "SK/scripts/fx_run.py" "<slot>" hf render
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
In the main video: build with `SFX=0` if it has its own sound design, lay the render over the a-roll for exactly these frames, and do not caption them.

## What to look at in the final frames
- Each swap is on screen on its word's frame (the yellow row first, the rest within a few frames), never before the speaker says it.
- The speaker's whole outline is clean on every frame: no halo of the old room, no missing fingers, nothing extra floating (picture frames, lamps).
- The yellow row sits clear above the speaker's head and its word reads whole at the swap. The speaker's face is never covered (the words are behind the speaker by construction).
- With `KEEP`: no sliver of the old wall above the furniture, and the edge does not swim.
- The end state holds long enough to read, and the frame count equals `clip.json` `frames`.

## Traps
- Everything behind the speaker is replaced. If the speaker sits on a sofa or at a desk and `KEEP` is empty, the speaker floats on the wall. Draw the furniture top edge as a `KEEP` shape, 3 to 5 px inside the furniture, closed along the bottom of the frame. `KEEP` and the row above the speaker's head assume the speaker and the camera stay put: if the speaker stands up or leans far, cut the slot shorter.
- Whisper word starts drift by a few frames, and `onsets.py` is only a first guess (on the test clip it put "out" on the vowel of the word before). Settle every wall word on the `-v` strip. A frame late is fine, a frame early looks like a mistake.
- Fast speech: a row that has not finished spreading when the next word is due skips the earlier word. That is by design; the yellow row never skips.
- The top two rows sit in the top 220 px where app buttons live. That is fine for the marching rows; `build.py` warns if the yellow row itself starts above 220.
- Bright daylight footage on the dark wall looks cut out on purpose. That is the look. Do not add grain or go black and white to hide it. With the wall up, the kept room is graded like the speaker (about 10% darker) so the seams match.
