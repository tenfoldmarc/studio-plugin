# comment-bubble

**What it does:** a comment field slides up under the speaker's chin, the keyword types itself on the spoken word, send is tapped, the comment posts as a bubble with a creator heart, then a reply bubble lands with a link chip.
**Job:** CTA. **Trigger phrases:** "show the comment being typed when I say comment VIDEO", "comment bubble on the CTA", "type the keyword and reply with the link".

## Footage it needs, and where it fails
- A line shaped like "(just) comment KEYWORD and I'll send you THING", plus at least 1.5s of the same shot after THING.
- Face-on talking head with the TOP OF HIS HEAD in frame. Works close-up and wide; the camera can be handheld.
- Close-up selfie (chin below y ~1050): no room for 1.3x. The thread shrinks to about 1.0 and the plate lifts up to 12% from the bottom edge (like a keyboard opening). The lift is still on at the last frame: end the slot on a cut, or set `T_OUT`.
- Wide shot: full 1.3x in the lower third, reply stacked (text above the chip), plate untouched. It covers the speaker's lap and whatever the speaker's hands do below y ~1050.
- Fails or needs `CHIN_Y` by hand: head cropped by the top of the frame, profile shots, hood / long hair (no head taper), two people, a hand on the speaker's face for most of the slot. The thread is fixed in frame: if the speaker stands up or walks, pick another take.
- Fast talkers: under 0.3s between the keyword and "send" makes the post, heart, dots and reply pile up. It still reads, but give it a look.

## Slot inputs
`assets/aroll.mp4`, `words.json`, `clip.json`. `assets/subject.webm` is used ONLY by measure.py (chin, head centre, avatar crop), never layered: with `fx_new.py --no-cutout` set `CHIN_Y`, `X_CENTER`, `AVATAR_BOX` by hand. `aroll_hi`: not used. No extra Python packages.

## CLIP block (top of build.py)
| Field | What it is | How to get it |
|---|---|---|
| `KEYWORD` | word to comment, caps | from the line; measure.py prints it |
| `REPLY_TEXT`, `CHIP_TEXT` | creator reply and yellow chip label | under ~20 / ~14 characters; only things the speaker says or implies |
| `USER_NAME` | generic commenter | keep `you` |
| `T_IN` .. `T_LINK`, `KEY_GAP` | beat times in seconds from the slot start | paste the "suggested CLIP times" from measure.py, then check each against its onset table |
| `T_OUT` | thread leaves and the plate settles back | `None` if the slot ends on a cut; else >= `T_LINK` + 0.6 and <= end - 0.25 |
| `SCALE` | thread size (1.0 = original demo) | leave 1.3; build.py shrinks it if the band under the chin is too small and says so |
| `CHIN_Y`, `CHIN_GAP` | chin line override, clear px under it | `None` = measured; override if work/measure_check.jpg is wrong |
| `DROP` | `'auto'` = as low as the safe zone allows; number = px under the chin | `'auto'` unless the buyer wants it hugging the chin on a wide shot |
| `X_CENTER` | thread centre x | `None` = under the speaker's head |
| `PUSH`, `PUSH_MAX` | plate lift (`'auto'` up to `PUSH_MAX`, or `1` = never) | `1` when the slot must match its neighbours frame for frame |
| `AVATAR_FRAME`, `AVATAR_BOX` | frame / square crop for the creator avatar | pick the frame from work/avatar_check.jpg (eyes open); box only if the auto crop misses |
| `GRADE`, `SEAT` | css filter on the plate; strength of the dark gradient behind the thread | `GRADE` = the reel's grade; `SEAT` 0 to 1.5 |
| `WORD_FONT`, `TEXT_FONT` | typeface of the keyword and chip / of the reply and name: (css family, weight, file in assets/fonts) | from the reel's caption style (the type facts table in effects/INDEX.md). Karaoke: both `('Archivo', 900, 'Archivo-900-normal.woff2')` |
| `UPPER` | reply, chip and name in capitals | `True` when the buyer's captions are in capitals |
| `ACCENT_COL`, `LIGHT_COL`, `DARK_COL` | accent (ring, caret, chip), light (bubble, words), dark (words on light) | the buyer's caption colours |

The buyer's style wins: in a reel the thread's words follow the reel's caption style. Set the four rows above before
the first build. A wider typeface makes the thread wider; it is scaled to the safe zone, so lower `SCALE` only if
the words get small.

## Switches
`SAFE=1` safe zone in red + the chin line in cyan (snapshots only). `SFX=0` no sounds (3 key ticks, tap click, pop, soft whoosh, all 0.75x template). `CAPTIONS=0` accepted, does nothing: the effect has no captions. Drop the reel's own captions for these frames, the thread sits where they would go.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" measure.py      # onsets + suggested times; LOOK at work/measure_check.jpg and work/avatar_check.jpg
# edit: the CLIP block in build.py (texts, the suggested times, AVATAR_FRAME)
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <T_IN+.3,T_TYPE+.1,T_SEND,T_SEND+.2,T_DOTS+.1,T_REPLY+.15,T_LINK+.2,end-.05>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # must print 0
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count + work/check/full.jpg and band.jpg from the FINAL mp4
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
build.py prints the layout it chose (scale, inline or stacked reply, thread box, chin, lift) and warns when it shrank the thread, lifted the plate, or a time is out of order. About 10 minutes per new clip, most of it the cutout in fx_new.py.

## What to look at in the final frames
- First letter appears on the frame the keyword starts (or one before); the tap is in the breath after it; reply on "send"; chip on the thing the speaker sends.
- Cyan chin line on or under the speaker's real chin on every frame, thread top below it. Face never covered.
- Nothing readable past the red safe lines (reply bubble right edge <= 980 below y 1155).
- "posting" frame: keyword shows once, not twice. Typing dots gone the moment the reply appears.
- Close-ups: the lift is smooth, no black edge at the bottom, avatar crop is the speaker's face (not a hand or the wall).

## Traps
- Whisper word starts were 0.1 to 0.6s early on the test clips, and it puts words inside silences. Use measure.py's audio onsets (`--env` prints the envelope); start each visual one frame before the onset.
- Stock sounds have silent lead-ins (click 48ms, pop / whoosh ~118ms): `SFX_LEAD` already compensates, keep it if you swap files.
- Chin = head top + 1.5 x head width from the cutout. Good to about 35px on a speaker wearing a cap; other people, hats or hair change the ratio (`CHIN_K` in measure.py). The check sheet is the truth.
- Reply text and chip are measured with PIL from the slot's fonts. Run build.py with the venv python, or widths are estimates and the bubble can cross the safe line.
- Changing `REPLY_TEXT` / `CHIP_TEXT` length can flip inline to stacked and move the whole thread: rebuild with `SAFE=1` and look again.
- Lint rules that bit: an `inset:0` element with a later opacity tween, two tweens of one property touching at the same timestamp, a `tl.set(autoAlpha:0)` under a still-running `tl.to(autoAlpha:1)`.
