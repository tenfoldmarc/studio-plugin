# glass-type ("Glass Type")

**What it does:** one word appears as thick clear glass letters standing on the speaker's wall, level, bending the room behind them (lamp, window, panels, shelves), with a dark glass rim, a thin rim light, a soft backing shade and a shadow + caustic on the wall. He stays in front of it. It lands on the spoken word, stands about 1.3 s, thins away, and the slot ends on the plain picture.
**Job:** hook or emphasis: the one word the line turns on.
**Trigger phrases:** "make DESIGN out of glass behind me", "put this word on my wall as glass", "glass type on this line".

## Footage it needs
- Shot: wide, medium or close (selfie). Camera: still or handheld drift (tracked, the glass stays pinned to the wall). Not a moving camera, not a zoom or punch-in inside the slot (declines).
- Wall: some open wall above or beside the head (above / beside / both). Cutout: layered (required: he occludes the glass) and measured (head, where he goes).
- Best on: a room with something to bend (a window, a lamp, wall panels, a door frame, shelves). A plain wall still reads (rim light, shadow, caustic), just quieter.
- Breaks on: the speaker filling the frame where a word could go, a zoom in the slot, a camera that travels. `glass.py measure` stops with the reason.

## Adapting to the footage (measured by `glass.py measure`, printed; CLIP entries override)
- Wide / medium: the biggest box on open wall near the head, usually above it, up to 330 px tall and 950 px wide.
- Tight selfie close-up: the open strip above the head (or beside it); the word gets smaller (it says so under 90 px). No strip at all: declines.
- Still camera: locked. Handheld drift (a selfie arm breathing in and out 10% included): a background-only track pins it to the wall. A punch-in (3% in one frame), a steady zoom over 6% while the glass is up, or travel over 300 px: declines.
- Window or lamp behind the word: backing shade and dark rim go up so the letters read over bright glass; no shadow lands on daylight.
- Busy shelf or panels: refraction shows them bending; letters may sit behind him by at most `MAX_HIDDEN` (no single letter over 30%).
- Plain wall: rim light, shadow and caustic go up so it still reads as glass. Plain dark wall: rim light up, no shadow.
- Level: the word stays level unless the wall's lines at that height clearly slope (then it follows at most 4 degrees).
- Speaker off-centre or two-thirds of the frame: the box goes to the open side; `PLACE` forces 'above', 'left', 'right' or a box.

## Slot inputs
`assets/aroll.mp4`, cutout `assets/subject.webm` (required), `clip.json`, `words.json`, `assets/fonts/fonts.css` (the Studio's font set). No `aroll_hi`. Sounds are synthesised by build.py into `assets_fx/` (seeded); nothing ships. Python: numpy, Pillow, opencv-python-headless (`requirements.txt`).

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `TEXT` | the one word in glass | his own word; 8 letters or fewer read biggest |
| `T_IN`, `T_OUT`, `HOLD` | arrival word / leave / seconds it stands | `'auto'` finds TEXT in words.json, onset re-measured on the audio; or a word, `'word#2'`, seconds. `T_OUT='cut'` only when the reel cuts right after |
| `PLACE`, `MAX_HIDDEN` | where the word goes; share of letters he may cover | `'auto'` unless work/measure.jpg shows a better spot: `'above'`, `'left'`, `'right'`, or `(x, y, width)` |
| `LEVEL` | perspective | `'auto'`, `True` (always level) or degrees |
| `FONT`, `WEIGHT`, `CASE`, `STRETCH`, `TRACKING` | the letters | default Inter Tight 900, upper, 1.10, 0.035 (stand-in for the demo's heavy condensed grotesk). Heavy faces only (Archivo 900, Inter Tight 800+, Poppins 700, Bebas Neue) |
| `INK`, `ACCENT`, `TINT` | dark rim and backing; light on the glass; glass body | defaults `#0B1016`, `#FFF6EA`, `#F2F8F4`. Take the buyer's darkest colour for INK, a pale tint of their accent for ACCENT. Never orange |
| `BACKING`, `RIM_DARK`, `RIM_LIGHT`, `SHADOW` | readability and wall light | `'auto'` (from the light behind the word) or numbers |
| `LIGHT_FROM` | where the room's key light comes from | `(-0.7, -0.7)` = upper left; flip x if the window is on the right |
| `IOR`, `BEVEL`, `DEPTH`, `DISPERSION`, `KEY_GAIN`, `DRIFT` | glass physics and motion | leave |
| `VOL_AIR`, `VOL_LAND`, `VOL_RING`, `SEED` | sound levels (x0.75 applied), noise seed | 0 turns one off |

**Switches:** `SAFE=1` (build.py: guide in index.html for snapshots; glass.py still: guide on stills). `SFX=0` no sounds. `CAPTIONS=0` and `GRADE` change nothing: the glass word is the caption for that word (do not caption it again in the reel), and there is no grade, so the edges match the a-roll.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# edit: the CLIP block: TEXT always; the rest only if a printout says so
PY "SK/scripts/fx_run.py" "<slot>" glass.py measure      # 4. camera, zoom, plate, head, the word's box, level, light. LOOK at work/measure.jpg
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # optional: if the glass lands visibly early or late, give T_IN in seconds
PY "SK/scripts/fx_run.py" "<slot>" glass.py still SAFE=1      # 5. six key frames -> work/stills/sheet.jpg
PY "SK/scripts/fx_run.py" "<slot>" glass.py bake      # 6. assets/fx.mp4 (up to 4 workers; WORKERS=n)
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 7. sounds + index.html (same switches you want in the render, e.g. SFX=0)
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 8. frame count, phone copy, stills, work/qa/sheet_*.jpg from the final mp4
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Re-run measure + bake after any CLIP change except sounds (build.py only). Bake: 12 to 24 s per slot second (4 workers, M-series Mac under load; bigger words cost more).

## What to look at (work/qa/sheet_*.jpg)
- The glass starts on the word, never before; the word reads in one glance on every background behind it.
- He is in front of it (hair and hands clean), no letter more than a third hidden, everything inside the safe zone.
- Handheld: the glass stays pinned to the wall (no swimming against the panels or frames).
- First and last frame identical to the a-roll. Frame count equals `clip.json`.

## Traps
- Thin faces (Didot, Inter 300, script fonts) leave no glass body to bend the room: the word vanishes. Heavy faces only.
- A white wall with nothing on it makes quiet glass. Pick a line where the word can sit across a window, lamp or panels if there is one.
- The cutout must be clean around the head: a matte that grabs room makes the glass stop at a ghost edge.
- Long words on a close-up get small; pick the shortest word that carries the line.
