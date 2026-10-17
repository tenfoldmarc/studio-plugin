# Motion: animation you write yourself

The engine's named entrances (pop, fade, slide-up, type-on, word-by-word) are shortcuts, not the limit. When an
example moves something in a way they do not cover (letters dropping in one by one, a blur-in, a bounce with
overshoot, a word that shakes, a punch-in on every key word, a flash on every cut), write it as **motion entries**.
They are GSAP tweens on the reel's one timeline, so the renderer draws every frame of them exactly.

Never use css `@keyframes`, `animation` or `transition`: the renderer seeks frame by frame and they do not play.
The build prints a NOTE when it finds them.

## One entry

```json
{"target": ".w", "tween": "from", "vars": {"yPercent": 60, "opacity": 0, "duration": 0.28, "ease": "power3.out", "stagger": 0.05}, "at": 0}
```

| Field | What it is |
|---|---|
| `target` | a css selector INSIDE the element the entry belongs to, or `self` for the element itself |
| `tween` | `from` (animate from these values to how it looks), `to` (from how it looks to these), `fromTo` (with `from`), `set` (jump) |
| `vars` | any GSAP vars: `x`, `y`, `xPercent`, `yPercent`, `scale`, `scaleX`, `rotation`, `skewX`, `opacity`, `filter` ("blur(12px)"), `clipPath`, `color`, `backgroundColor`, `letterSpacing`, `transformOrigin`, `duration`, `ease`, `stagger` (a number or `{"each": 0.04, "from": "center"}`), `repeat`, `yoyo`, `delay` |
| `from` | the start values, for `fromTo` only |
| `at` | seconds after the element comes in (default 0) |
| `at_end` | instead of `at`: seconds before the element goes (an exit) |

Never random values (`random(...)`, `"from": "random"`) and never code: the renderer may load the page more than
once, and two renders of the same frame must match. Write the numbers out (a shake = a short list of fixed x values
with `repeat`, or several `to` entries).

## Where entries go

| Where | Field | Belongs to | Times are |
|---|---|---|---|
| Custom captions | `caption.motion` | each caption line (`.cu`); targets `.ln` (a line), `.w` (a word), `.w.m` (a marked word), `.ch` (a letter, with `entrance: "type-on"`) | after the line comes in / `at_end` before it goes |
| Custom captions | `caption.word_motion` | each word, at the moment it is said | after the word starts |
| Custom captions | `caption.mark_motion` | each marked word (num, key, emph, cta), as it is said | after the word starts |
| A layer | `layers[].motion` | that layer (its html); write letters as `<span class='ch'>` to animate them one by one | after the layer's `from` / `at_end` before its `to` |
| The whole reel | `motion` (top level of plan.json or the style) | the page; `target` is a selector, or `footage` (the picture and the cutout together), `speaker` (the cutout), `captions`, `layers` | `at` = reel seconds, or a pattern with `on` |

A reel-wide entry with **`on`** repeats on every moment of a kind, so it works on any reel:
- `"on": "marks"` every marked word (`"kinds": ["key", "num"]` for only some), `"on": "words"`, `"on": "cuts"`, `"on": "start"`
- `"every": 2` every other one, `"offset": -0.05` a little before

A saved style keeps only the `on` kind of reel motion (times at fixed seconds belong to one reel).

## Recipes (start here, then match the example)

Blur-in caption line:
```json
"motion": [{"target": "self", "tween": "from", "vars": {"filter": "blur(14px)", "opacity": 0, "duration": 0.12, "ease": "power1.out"}}]
```
Words rising one after another, line falls away at the end:
```json
"motion": [{"target": ".w", "tween": "from", "vars": {"yPercent": 70, "opacity": 0, "duration": 0.25, "ease": "power3.out", "stagger": 0.05}},
           {"target": "self", "tween": "to", "at_end": 0.12, "vars": {"y": -24, "opacity": 0, "duration": 0.12}}]
```
Key word slams in:
```json
"mark_motion": {"tween": "fromTo", "from": {"scale": 1.6, "rotation": -6}, "vars": {"scale": 1, "rotation": 0, "duration": 0.22, "ease": "back.out(3)"}}
```
Spoken word lights up and bumps:
```json
"word_motion": {"tween": "fromTo", "from": {"scale": 1.12}, "vars": {"scale": 1, "duration": 0.18}}
```
Punch-in on every key word, and a white flash on every cut:
```json
"motion": [{"on": "marks", "target": "footage", "tween": "to", "vars": {"scale": 1.07, "duration": 0.1, "yoyo": true, "repeat": 1, "transformOrigin": "50% 35%"}},
           {"on": "cuts", "target": "#root", "tween": "fromTo", "from": {"filter": "brightness(1.7)"}, "vars": {"filter": "brightness(1)", "duration": 0.18}}]
```
A sticker that springs in and wiggles once:
```json
"motion": [{"target": "self", "tween": "from", "vars": {"scale": 0, "rotation": 14, "duration": 0.45, "ease": "elastic.out(1, 0.5)"}},
           {"target": "self", "tween": "to", "at": 0.6, "vars": {"rotation": -4, "duration": 0.08, "yoyo": true, "repeat": 3}}]
```

## Reading motion from an example

`study.py` writes `motion_01.jpg ...`: frame-by-frame strips around every moment something appears or moves, two
frames apart at 30 fps. Read them left to right and note: what moves (the line, each word, each letter, the
picture), from where (below, the side, bigger, blurred, invisible), how long (count the frames: 3 frames = 0.1 s),
whether it overshoots and settles (`back.out`, `elastic.out`), what else moves with it. Then write the entries,
build, take snapshots at the same moments, and compare (`side_by_side.py`). One polish pass.

## Checks

Motion goes through the same checks as everything else: `hf lint` 0 errors, snapshots in the middle of a movement
(not only after it settles), and the final render's frames. Something that moves must not cross the face or leave
the safe zone at any frame of the movement, only at rest is not enough.

Motion on the picture itself (`footage`, `speaker`, `#root`): the captions and the face box are placed for the
unmoved picture. Bring a punch-in back (`"yoyo": true, "repeat": 1`, or a later `to` with `scale: 1`) unless the
example really holds the zoom, keep it small (1.03 to 1.08), and grow it from the face (`transformOrigin` at the
head). The automatic self-check cannot compare a moved picture with the footage, so `build_reel.py` says so and
`frames_check.py` stops flagging those frames: look at its sheet yourself.
