# odometer demo clip

**Footage:** handheld close-up selfie (the speaker fills most of the frame, the wall drifts about 120 px), 186 frames.
**Line:** "with 10 years of experience running ads for hundreds of different offers, funnels, and all types of budgets."

## CLIP block that rebuilds it (this is what build.py ships with, plus the optional `label2` on the second counter)
```python
COUNTERS = [
    dict(text='10', say='10', lock=None,
         label=[('YEARS', 'years'), ('RUNNING', 'running'), ('ADS', 'ads')],   # wraps: YEARS / RUNNING ADS
         label2=None, sit='auto', size='auto', then='dock'),
    dict(text='100s', say='hundreds', lock=None,
         label=[('OF', 'of'), ('OFFERS', 'offers')],
         label2=[[('FUNNELS', 'funnels')], [('FUNNELS', 'budgets'), ('+', None), ('BUDGETS', None)]],   # demo only; default is None
         sit='auto', size='auto', then='dock'),
]
ROLL = 0.44
OUT = None
DOCK_CORNER = 'auto'
GRADE = 'contrast(1.05) saturate(.92) brightness(.99)'
```

## What the machinery measured on this clip (the demo had these typed in by hand)
| | hand-set in the demo | measured by the pack |
|---|---|---|
| "10" lock | 0.56 s | 0.56 s (Whisper said the word ran 0.24 to 0.58) |
| "100s" lock | 2.48 s | 2.51 s |
| YEARS / RUNNING / ADS | 0.60 / 1.62 / 1.82 | 0.60 / 1.61 / 1.84 (Whisper: 0.58 / 1.26 / 1.74) |
| OF / OFFERS | 2.55 / 3.05 | 2.56 / 3.17 |
| "10" panel | (610, 236) scale 1.25 | (595, 236) scale 1.25 |
| chip | (45, 236) | (47, 236) |
| "100s" panel | (455, 236) scale 1.0, the speaker's head clipped a drum corner on 5 frames | (463, 236) scale 0.91, nothing readable behind the speaker |

Beats: 0.02 panel pops in top right, drums spin, "10" locks at 0.56 as "ten" ends; YEARS, RUNNING ADS on the speaker's words; 1.93 the panel shrinks into a chip top left while the "100s" panel slides in from the right and locks on "hundreds" at 2.51; OF OFFERS.
