# Spatial Glass: the lab demo (maker-side only)

`demo.mp4` and `stills/` show Marc and are for the maker only: never ship them to a buyer or show them as the
buyer's result. They are the LAB build (reel-edit/fx-lab/spatial-glass), whose clip grid used frames of Marc's own
clip and whose prompt bar typed "edit it". The packaged effect replaces both: the grid is six generic tiles, the bar
types the speaker's own words.

- Source: aesthetics-reel c3 (1080x1920, armchair, medium shot, still camera with two small nudges), 49.20 s to 53.45 s, 128 frames.
- Line: "All you need to do is drop your clips, trigger the skill, and Claude takes care of it all for you."
- CLIP values in the packaged build.py for this line:
  - `STEPS = [('drop', 'Clips'), ('trigger', 'edit it'), ('takes', 'Editing')]`
  - `DONE = 'auto'`, `DONE_LABEL = 'Done'`, `OUT = 'auto'` (the lab demo held to the last frame; the package leaves 3 frames early)
  - everything else 'auto' (light glass, Inter 500, Instrument Serif italic, butter yellow accent, lamp found on the sconce)
