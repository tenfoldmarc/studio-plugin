# Turning a video into a carousel

The source can be a reel the Studio edited (its project folder, the best source: the words were already fixed by
hand during the edit and there is a clean cut without captions), any video file on the computer, or a link to a
post (Instagram, TikTok, YouTube). "Turn my last reel into a carousel" = the newest folder in `projectsDir`
(`config.json` in the Studio state folder).

```
1. PY "CS/scripts/carousel.py" new "<title>" --source "<project, file or link>"      -> the carousel folder
2. PY "CS/scripts/carousel.py" transcript "<same source>" --out "<carousel folder>"
       read every line. Fix what Whisper misheard (names, tools: "cloud" is often "Claude") before writing a word.
3. write the outline (craft.md "From a video to a carousel"): the hook, the points in the reel's order, what each
   middle slide keeps, the CTA (the reel's own keyword when it has one)
4. pictures, only where they help (a hook with their face, a proof slide, a screen they showed):
   PY "CS/scripts/carousel.py" frames "<source>" --sheet 24 --out "<carousel folder>"
       look at assets/pick-sheet.jpg, choose by number (open eyes, clear expression, no blur, nothing covering the face)
   PY "CS/scripts/carousel.py" frames "<source>" --at 12.4,31.0 --out "<carousel folder>"
       the exact moments you picked from the sheet -> assets/frame-<t>s.jpg. A face: use the exact time you saw.
       --sharp takes the least blurry still within 0.3s instead: for screens and fast motion, not for faces
       (it can land on a blink).
   PY "CS/scripts/carousel.py" faces "<carousel folder>/assets/frame-12.40s.jpg" ...
       where the face is in each still: give it as "face" wherever text sits on that still
   optional, the person cut out for a cover (the strongest hook with a face):
   PY "CS/scripts/carousel.py" cutout "<carousel folder>/assets/frame-12.40s.jpg" --top 0.6
       trimmed to the person; --top 0.6 keeps head to waist. On the hook:
       "image": {"src": "assets/frame-12.40s-cutout.png", "fit": "cutout", "place": "stage", "height": "60%"}
       It stands on the bottom edge behind the text. The render shrinks it until no text covers the face
       ("picture made smaller to keep the face clear"); a TEXT OVER THE FACE line means shorten the headline.
       Look at the result: a chair or a bit of floor can stay in the cut-out; pick another still if it shows.
5. show the copy (SKILL.md "The copy, for approval"), with which still goes on which slide. Wait for the OK.
6. write carousel.json, render, check, open (SKILL.md)
```

## What changes from the reel

- The reel's first line is usually the hook. Tighten it for reading: the number and the outcome loud, the rest
  quiet. It may need the payoff spelled out (a reel can tease with tone, a slide cannot).
- Their best phrases stay word for word. The filler, the repeats and the "so what you want to do is" go.
- A point the reel makes in 20 seconds becomes one slide: the point as the headline, the why as one line, the
  thing to keep in its own block.
- Anything they SHOWED (a screen, a website, a result) can be a still from the video, labelled.
- The CTA keyword stays the same as the reel's so both posts lead to the same resource. No CTA in the reel: ask
  what they want people to do, or end on "Save this" with a short reason.
- Stills from a Studio edit come from the clean cut (`assets/aroll.mp4`, no captions burned in). From a finished
  reel file the captions show in the still: prefer the raw clip, or use a moment without a caption.
- A video with no speech (music only, a screen recording): ask what the carousel should say, use stills.
