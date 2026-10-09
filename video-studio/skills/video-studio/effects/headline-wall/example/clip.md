# headline-wall: the demo clip

> The demo render and stills this note mentions (`demo.mp4`, `stills/`) are not part of the skill. What carries over to a new clip is the CLIP block and the numbers.

**Spoken line:** "Everybody's talking about how Claude can edit your videos."
**Footage:** 1080x1920, medium shot, sitting on the floor against a dark wall, 92 frames (3.07 s), one continuous take.

## CLIP block values (they are the defaults shipped in build.py)
| field | value | why |
|---|---|---|
| `HEADLINES` | 20 versions of "Claude edits video now", `[Claude]` marked in each | one message, many voices |
| `HEROES` | 4 cards on frames 42, 56, 65, 71 | onsets of "Claude", "edit", "your", "videos" |
| `SEARCH` | `can [claude] edit videos` | the pill opposite the first hero |
| `F_START` / `F_PEAK` | 2 / 28 | first syllable; end of "everybody's talking" |
| `F_ACCENT` | 42 | "Claude": highlighter, bump, low hit |
| `DENSITY` / `LEAD` | 1.8 / 4 | defaults |
| `WALL` | `None` | bare wall down to the speaker's elbows |
| `HERO_FIRST_SIDE` | `'L'` | more clear wall on the left |
| `PUSH` / `BUMP` / `DIM` | 1.06 / 1.032 / 1.0 | dark wall, no extra dim needed |
| `F_OUT`, `KEEP_OUT`, `FOREGROUND` | `None`, `[]`, `[]` | the wall stays to the last frame |

## Read this before comparing a new render with demo.mp4
- The demo was built by hand before the effect was packaged. Its small far cards run into the top 220 px of the frame. The packaged effect no longer does that: far cards stay below the top 220 px on every frame, so a new render has an empty band at the top.
- The demo file was not rendered again through the packaged build. The test in `test.md` is the proof of the packaged scripts.
