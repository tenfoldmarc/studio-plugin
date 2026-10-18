# Code Scan: the demo clip (maker side only)

`demo.mp4` and `stills/` show Marc and his room. They are for the maker and the importer, never for buyers' reels.

Source: `reel-edit/aesthetics-reel/src/c3.mp4` 49.20 to 53.45 s (128 frames, 1080x1920, still camera, sitting on
the floor in front of a window, warm wall lamp). Rebuilt with the packaged effect from the lab slot's a-roll and cutout
(`pack/tests/code-scan/demo/`).

Spoken line: "All you need to do is drop your clips, trigger the skill, and Claude takes care of it all for you."

CLIP block values (everything else default):
| field | value |
|---|---|
| `T_IN` | 'trigger' (audio onset 1.94 s, front starts 1.88 s, code landed 2.43 s) |
| `T_OUT` | 'you#2' (picture fully back by 4.03 s) |
| `IN_DUR`, `OUT_DUR` | 0.55, 0.50 |
| `LINE1`, `LINE2` | 'edit it', 'done' |
| `TOKENS` | default list |

What changed from the lab build (Marc: the transition looked "amateur-ish"; v2 had a dark blocky cloud for 2 to 3
frames): the transition is now two layers that never fight. A smooth, rank-equalised order field (no cells) moves a
soft print front out from his core; behind it the photo becomes glyphs printed in the photo's own colours with the
brightness matched to the photo around them (the lab's printed stage was about a stop darker, which read as a dark
cloud). The fall into the dark code palette is one nearly global grade on its own gentle curve, so no single cell
drops to near black on its own and no frame moves more than about an eighth of the way. Out is the same in reverse:
the lights come up first, then the glyphs unprint from the room inward, the speaker last.
