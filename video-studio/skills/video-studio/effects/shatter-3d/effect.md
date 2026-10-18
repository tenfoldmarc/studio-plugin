# shatter-3d (Shatter 3D)

**What it does:** on a word the picture fractures into tiles at different depths and a camera drifts through them; two punched-in close-ups (eyes, hands) fly out with an accent edge; a hard jolt lands on the punch word; then the held picture cracks and breaks like glass (glass sound) to reveal the clean live shot. `ENDING 'heal'` (v1) snaps the tiles back instead.
**Job:** hook, or emphasis on one punch line ("video editors are ABSOLUTELY... COOKED").
**Trigger phrases:** "shatter the frame on X and slam it on Y", "break it like glass", "shatter 3D on this line".

## Footage it needs
- Shot: wide, medium or close (selfie). Camera: still or handheld drift. A zoom or punch-in while the frame is fractured makes it decline.
- Wall: not needed (the whole frame fractures, the room does not matter).
- Cutout: only measured (`assets/subject.webm` finds the head, the eyes and the hands); without one it runs as a plain fracture. `aroll_hi` used when the slot has it (sharper close-ups on 4K: make the slot with `--hi`).
- Timing: about 0.6 to 1.5 s between the break word and the punch word, and about 1.2 s of slot after the punch word.
- Breaks: a zoom inside the slot (declines); two people (only the larger one is measured); hands right at the face (the hands close-up is skipped).

## Adapting to the footage (build.py chooses and prints why)
- Wide shot: the face tile is at least 300x420 px (head and shoulders), close-ups punched in up to x1.7 so they read.
- Medium shot: the demo look. Face tile 1.6 head widths, nearest the camera; eyes close-up beside the face on the open side, hands close-up low on the other side.
- Tight selfie close-up (head near the top, shoulders edge to edge): the face tile becomes most of the frame and sits less deep (so it does not blow up); close-ups only where they fit without covering the face, usually none. The tile stays whole.
- Still camera or handheld drift: the face tile covers every place the face goes during the effect.
- Room behind (open wall, busy shelf, window or lamp, plain dark): no change. A bright window shows through the gaps as tiles, which reads fine.
- Speaker off-centre or two-thirds of the frame: the tile grid is built around the face; close-ups fly to the side with more room.
- No speaker (voice-over b-roll) or no cutout: plain fracture, the centre tile nearest the camera, no close-ups.
- Declines with a plain reason: a zoom while fractured, no room for the glass after the punch word, the punch word too early.

## Slot inputs
`assets/aroll.mp4`, `words.json`, `clip.json`; `assets/subject.webm` (measured, optional); `assets/aroll_hi.mp4` (optional). Sounds (whoosh, deep hit, glass shatter; heal: whoosh and click) are synthesised into `assets_fx/` by build.py (seeded). No text, no fonts.

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `T_BREAK` | the word the frame fractures on | a word ('absolutely', 'so#2'), seconds, or 'auto'. Re-measured on the audio |
| `T_HIT` | the punch word: the jolt | a word, seconds, or 'auto' (last long word with room after it). Set both for a real edit |
| `ENDING` | 'glass' (v2, default) or 'heal' (v1) | glass unless asked for the snap back |
| `HOLD` | frames held after the hit before the glass cracks | 11; shortened automatically on a short slot |
| `SHOT` | 'auto', 'wide', 'medium', 'tight', 'none' | leave 'auto' unless the printout is wrong |
| `FACE_BOX` | override (x0, y0, x1, y1) of the face | only if the printed face is wrong (`bake.py -g` draws it green) |
| `CLOSEUPS` | 'auto', 0, 1, 2 | fewer when it looks busy |
| `IMPACT` | where the glass is hit (x, y) | 'auto': the hands, else under the chin, never the face |
| `ACCENT` | edge colour of the close-ups (r, g, b) | the buyer's accent colour; default butter yellow |
| `GROUND` | colour seen in the gaps | keep near black |
| `SEED`, `GLASS_SEED` | tile split and depths; crack pattern | change for another arrangement |
Words on screen: none, so FONT / WEIGHT / CASE / INK do not apply; `ACCENT` takes the buyer's look.

## Switches
`SAFE=1` red safe-zone guide in index.html (snapshots only). `SFX=0` no sounds. `CAPTIONS=0` and `GRADE`: accepted, do nothing (no words, no grade of its own).

## Python
Needs OpenCV: in the Studio run `setup.py --fx shatter-3d` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. measure, choose, plan, sounds, index.html. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames <the 4 it prints> -g      # 2. preview -> work/t/ (red = safe zone, green = face, blue = eyes)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4, 16 to 27 s per second of slot (4 workers)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. Re-run build.py and bake.py after any CLIP change; the render after every bake.

## What to look at (work/qa/sheet_*.jpg)
- First and last frame plain footage. The fracture starts on the break word, the jolt on the punch word.
- The face tile whole with both eyes readable in every fractured frame (build.py prints the worst eye visibility).
- Close-ups inside the safe zone, not over the face. Glass all gone before the clean frames.

## Traps
- Whisper can start a word up to 0.45 s early (it pads the silence before it). build.py lands on the end of the pause; if it still looks off, run `PY onsets.py first last` and give the word in seconds.
- On quiet audio Whisper can invent words ("Thank you for watching"): check words.json before picking words.
- A long gap (over 2 s) between break and hit makes the drift slow: pick a closer break word.
