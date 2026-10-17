# doodle-boil (Doodle Boil)
**What it does:** a hand-drawn chalk line traces the speaker and redraws every 2 frames (the boil), while chalk doodles from a 30-piece library draw on in stroke order on the words they belong to, then rub out. Optional payoff: the line goes double, rays burst round them, little stars sprinkle in.
**Job:** explain / personality (one doodle per spoken idea), with a finale for the payoff line. **Trigger phrases:** "draw a chalk heart when I say girlfriend", "outline me in chalk and doodle my words", "chalk doodles on this line", "use the blush colours".

## Footage it needs
- Shot: wide, medium or close-up selfie all work. Camera: still or handheld drift (everything follows the cutout each frame). Wall: none needed; open space beside or above the head is where doodles go. Cutout: layered (the room dim) and measured (outline, head, open space).
- Breaks it: no open space anywhere off the face inside the safe zone (build.py stops and says so); a second person in frame (the outline takes the biggest one); hands above the head for long (the head anchor jumps, doodles ride up).

## Adapting to the footage (build.py chooses, prints which and why; CLIP entries override)
- Wide: full-body outline, doodles about 1.35x head width (130 to 280 px), rays round the whole body. Medium: same, rays from the torso.
- Tight selfie (head near the top, shoulders edge to edge): the outline only traces the head and shoulders (the run along the frame edge is hidden and the draw-on skips it), a thicker line, doodles shrink to fit the gap beside the head; with no gap one goes on the torso under the chin.
- Still camera or handheld: doodles ride a smoothed head anchor, the outline re-reads the matte every frame.
- Room: open wall or plain dark gets a lighter dim; busy shelf, window or lamp gets a deeper one (`DIM='auto'`, printed with the room's brightness and texture). No person in the cutout (voice-over): doodles only, round the upper middle, outline and rays off.
- Speaker off-centre or filling two-thirds: each doodle takes the most open spot near the head (sides alternate, crown goes above); when two cannot fit together the older one rubs out as the new one lands.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (cutout, needed for outline and dim; without it doodles only), `words.json`. No aroll_hi. Python packages: numpy, opencv-python-headless, Pillow (`requirements.txt`; in the Studio: `setup.py --fx doodle-boil`). Draws no words, so caption fonts do not apply; its colours take the buyer's look (INK, ACCENT, ACCENT2).

## CLIP block (top of build.py)
| Field | What it is | How to set it for a new clip |
|---|---|---|
| `DOODLES` | `cue(word, doodle, cross=, hold=, where=, size=, colour=, fill=, accent=, rot=, finale=)` per idea | pick 2 to 4 strong words from words.json, a doodle each from the table below; `cross='word'` crosses it out on a negation ("NOT techy"); `finale=True` on the payoff word (one only) |
| `OUTLINE` | `'auto'` / `'single'` / `'double'` / `'off'` | auto: single line from the first doodle, double for the finale |
| `PALETTE`, `INK`, `ACCENT`, `ACCENT2` | colourway (`classic` cream/butter/pink, `blush` cream/lilac/pink) and hex overrides per slot | the buyer's caption colours go in INK / ACCENT. Never orange |
| `DIM` | room dim behind them while chalk is up | `'auto'`; 0 for none, up to 1 |
| `HOLD_MAX` | seconds a doodle stays when nothing needs its space | 2.8 |
| `SPARKLE` | finale stars | `'auto'` (as many as fit, up to 5) |
| `IN_FRAME`, `OUT_FRAME` | first frame anything shows, frame everything is rubbed out by | 3 and -4. `OUT_FRAME=None` holds to the end: only when the slot ends the reel or on a hard cut |
| `SFX_PEAK_DB` | chalk scratch level | -27 sits under the voice |

## Doodle library (name: what it reads as)
| doodle | for | doodle | for | doodle | for |
|---|---|---|---|---|---|
| heart | love, people you care about | star | best, standout | sparkle | new, magic |
| crown | winning, results (finale) | arrow | this, next | arrow_curved | look here |
| underline | stress a word | circle | this one | check | yes, done, works |
| cross | no, wrong | exclaim | warning, important | question | why, how |
| flower | grow, pretty | sun | day, bright | cloud | think, online |
| bolt | fast, power | bubble | talk, comment | smiley | happy, easy |
| coffee | morning, work | tag | price, sale | butterfly | change |
| bow | gift, wrapped up | clapper | video, editing | chip | tech, AI |
| clock | time, hours | dollar | money, paid | bulb | idea, learn |
Also pentagram, spiral, dot (finale sprinkles). Under ~110 px tag, coffee, butterfly, clapper turn to mush: on a close-up prefer check, cross, heart, bulb, dollar, star.

## Switches (environment variables on build.py)
`SAFE=1` safe-zone guide in index.html (snapshots only). `SFX=0` no chalk sound. `DIM=0` no room dim. `CAPTIONS` and `GRADE` do nothing here (no words, no grade; the dim is 0 on the first and last frame). `WORKERS=n` on bake.py: cores to use.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. plan + index.html + chalk sound. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames 40,80,120,160 --guide      # 2. quick look: work/test/sheet.jpg (yellow = doodle boxes, red = safe zone)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4, 3 to 7 s per second of slot on 4 cores
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 1.0,2.5,4.0
PY "SK/scripts/fx_run.py" "<slot>" build.py
PY "SK/scripts/fx_run.py" "<slot>" hf render      # 5. guide off first (the && above rebuilds without it)
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 6. frame count, edges plain, phone copy, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Re-bake after any CLIP change except SFX_PEAK_DB.

## What to look at (work/qa/sheet_*.jpg)
- Each doodle starts drawing on its word (frame printed per cue), crosses land on their word, nothing touches the face, every doodle inside the safe zone. The outline hugs the body with no line along the frame edge.
- First and last frame plain (post.py prints "plain"). The chalk reads against the room (if not, raise DIM).

## Traps
- Whisper is 1 to 4 frames off: build.py snaps each cue to the audio onset and prints both. Trust the printed frame.
- A hand raised beside the face pulls the outline along the cheek for a few frames; arms out to the frame edge make the line hide there.
- The line may run under the bottom UI zone on a wide shot: it is decoration, never text. Doodles always stay inside.
- Layer order is cream, yellow, pink: a pink fill paints over cream lines.
- Five or more cues in 3 seconds crowd the frame: the planner rubs older ones out early; fewer, stronger words look better.
