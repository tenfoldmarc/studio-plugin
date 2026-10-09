# ui-world: the demo clip

> The demo render and stills this note mentions (`demo.mp4`, `stills/`) are not part of the skill. What carries over to a new clip is the CLIP block and the numbers.

**Spoken line:** "All you need to do is drop your clips, trigger the skill, and Claude takes care of it all for you."
**Footage:** 1080x1920, medium-wide, sitting on the floor in front of an armchair, 126 frames (4.2 s), one continuous take, still camera.

## CLIP block values (the defaults shipped in build.py follow the same line)
| field | value | why |
|---|---|---|
| `SCREEN` | `'chat'` | the packaged chat-style screen |
| `APP_NAME` | `'Claude'` | the name in the header |
| `GREETING` / `PLACEHOLDER` | "What are we making today?" / "How can I help you today?" | empty screen before the first word |
| `ATTACH` | frame 25, five clips | "drop" at 0.84 s |
| `LABELS` | frame 39 `RAW CLIPS` at `'attach'`, frame 67 `ONE COMMAND` at `'text'` | "clips" at 1.30 s; just before the send |
| `TYPE` | frame 54, a slash command | "trigger" at 1.80 s |
| `SEND` | 74 | "skill" ends at 2.46 s |
| `REPLY` | frame 79, "On it. Editing your reel." | "Claude" at 2.62 s |
| `STEPS` | 4 rows on frames 87, 93, 99, 105 | they tick through "takes care of it all" |
| `RESULT` | frame 112, `reel-final.mp4`, badge `Ready` | "for you" at 3.74 s |
| `EDGE` | 1188 in the demo (set by hand) | the speaker's chest line; the package measures it |
| `HEAD_Y` / `ZOOM` | not used in the demo (the speaker's head already sat at y 864) | the package reframes other shots to match |

## Read this before comparing a new render with demo.mp4
- The demo was built by hand before the effect was packaged, and it was not rendered again through the packaged build. The test in `test.md` is the proof of the packaged scripts.
- Look: the demo uses a serif face for the header and the reply, a small star logo, and a clay accent on the button and the progress bar. The package uses the fonts that ship with the template, no logo unless you supply one (`APP_MARK`), and a neutral ink `ACCENT` you replace with your own brand colour.
- Attachments and the result card: the demo shows thumbnails of the speaker's own clips. The package ships no footage, so the defaults are plain labelled tiles. Give picture paths in `ATTACH` and `RESULT` to get thumbnails.
- Cutout: the demo used a heavier portrait matting model on an upper-body crop plus hand clean-up on a few frames. The package uses the slot's standard cutout and cleans its edge in `prep.py`. On hard footage (clothes the colour of the furniture) the demo's shoulder line is better than what the package gives out of the box.
