# Rack Focus: the approved lab demo (maker side only)

`demo.mp4` and `stills/` show Marc and are for the maker only: they never ship to buyers.
They are the lab build (`fx-lab/rack-focus/`, approved: "great for her looks", liked the two fonts).

- Source: handheld selfie close-up, 1440x2560, from 19.82 s, 120 frames (4.0 s). Warm room, a lantern behind him.
- Spoken line: "So I created a skill with all of the knowledge that I have personally as a media buyer"
- Lab values: pull starts 0.58 s (middle of the pull on the vowel of "skill", 0.86 s), back at 1.78 s ("knowledge"),
  title "I CREATED A" / "Skill", centre (338, 1336), room blur 30 px, speaker 0.62, discs 74 px at rest.

The same clip re-built with this package (`pack/tests/rack-focus/demo/`), only the CLIP block set:
```
T_LAND = 'skill'          # onset measured 0.86 s, the lab's hand value
T_BACK = 1.88             # seconds (build.py starts leaving 0.10 s before): 1.78 s, as the lab
SMALL = 'I CREATED A'
BIG = 'Skill'
```
Everything else auto: close shot measured (head 456 px), title centre chosen (392, 1333) (lab hand value 338, 1336),
room blur 30 px, speaker 0.62, discs 73 px, lantern lifted to bloom (0.9 percent of the room clipped).
Render: `pack/tests/rack-focus/demo/renders/demo.mp4`.

What changed from the lab look: the resting discs now carry a real lens's imprint (slightly nine-sided, lit rim,
faint onion rings, dust, cat's eye toward the frame edge, uneven brightness, some clumped) instead of flat
butter circles; the disc colour comes from the room's lights; the title fades in as discs (frame 0 is plain).
