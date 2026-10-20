---
name: carousel-studio
description: "Creator Studio carousels. Makes finished Instagram (and LinkedIn) carousels in the creator's own look: from a topic or idea, from scratch, or from a video (a reel the Studio edited, any video file, or a link). Writes the copy for every slide first and waits for approval, then renders the slides as PNGs and opens a swipe-through preview. Pictures from their own photos, a connected drive, their video, or an image generator. First carousel only: a short setup (handle, look built from carousels they love or picked from the Studio's looks shown with their own photos). Use when the user says 'make a carousel', 'carousel about X', 'turn this video / my last reel into a carousel', 'repurpose this into a carousel', 'carousel from this transcript', 'redo slide 3', 'make a new carousel look', 'copy this carousel style', 'change my carousel look', 'set up carousels', or runs /carousel-studio."
---

# Creator Studio: carousels (carousel-studio)

A topic, an idea or a video in. A finished carousel out, in the buyer's own look: the copy for every slide first,
then the slides, then a preview they can swipe through like the real post.

`CS` is this skill's folder (`${CLAUDE_SKILL_DIR}`, or the base directory Claude Code gave you when it loaded the
skill). `SK` is the video Studio's skill folder next to it: `CS/../video-studio`. Both are read-only.

Read before the first carousel in a chat: `references/craft.md` (what makes a carousel work: copy, hook, arc,
hierarchy, photos) and `references/slides.md` (every slide field). Read `references/looks.md` when building or
changing a look, `references/from-video.md` when the source is a video, `references/stickers.md` when the look or
the slide uses phone-screen, paper or hand-drawn pieces, `references/images.md` before generating any picture.

## The buyer's look and voice win

Order of precedence, highest first:
1. What the buyer asks for on this carousel.
2. The look this carousel is in: their default, or the one they name ("make it in Clean Sheet"). Read its
   `look.md` first (`carousel.py look show "<name>"` prints where): its copy feel and "Standing notes" are rules.
3. The principles in craft.md (one idea per slide, the hook promises, worth keeping, readable, real).
4. The defaults in craft.md. Always last: a default never overrides their look or their notes.

## Step 0: the quiet check (every chat)

1. The Studio's own setup check first, exactly as `SK/SKILL.md` "Step 0" says (Mac/Linux `sh "SK/scripts/start.sh"`,
   Windows the `setup.py` / `start.ps1` order there). It gives `PY` (in `ST/.platform.json`) and handles updates:
   `STATUS update AVAILABLE` is asked about first, on its own, as that file says.
   - A buyer who never set up the video side: this check still works; it sets up Python, ffmpeg and Node.
     The video setup questions are NOT asked for carousels.
2. `PY "CS/scripts/carousel.py" check`. Read, do not announce:
   - `profile MISSING`: the carousel setup below, then their carousel.
   - `browser MISSING`: the check already tried to download the browser that draws the slides and could not
     (usually no internet). Say so in one line and stop until they are online. The first check on a computer that
     never edited a reel downloads it (about 0.5 GB, one time): say that once while it runs.

Talk to the buyer in plain words. Never show them STATUS lines, file names of this skill, JSON or HTML.

## The carousel setup (first carousel only)

Only when `profile MISSING`. Short: they came to make a carousel, so get them there.

1. Say: "Quick setup for carousels, one time: your handle and your look. Then we make it."
2. Ask in ONE message: their handle as it should show on the slides, and (optional) a profile picture file for the
   corner of every slide. Where finished carousels go: `~/Carousels` unless they say otherwise.
   `PY "CS/scripts/carousel.py" profile --handle "<handle>" [--name "<name>"] [--avatar "<file>"] [--dir "<folder>"]`
   (`--verified yes` only if they ask for the tick.)
3. The look, in ONE message:
   > "Now your look. Two ways: send me 1 to 3 screenshots of carousels whose design you love (yours or anyone's)
   > and I'll rebuild that style for you. Or I'll show you the looks the Studio comes with, made with YOUR photos:
   > drop 2 or 3 photos of you (or of what you post about) and tell me what your account is about."
   - Screenshots, files, links or a description: build it (`references/looks.md`), show the 3 sample slides,
     adjust once or twice, ask what to call it, then `look default "<name>"`.
   - The Studio's looks: `PY "CS/scripts/carousel.py" looks` lists them (who each suits, its niches, photo-led or
     type-led). Pick the 3 or 4 that fit THEM (their niche, who they are, their photos). Find the faces first:
     `PY "CS/scripts/carousel.py" faces "<photo 1>" "<photo 2>" "<photo 3>"` (about 10 seconds a photo; its last
     line is the `--faces` to pass on). Then
     `PY "CS/scripts/carousel.py" preview-looks --looks "<a>,<b>,<c>" --photos "<photo 1>" "<photo 2>" "<photo 3>"
     --faces "<from faces>"`. It opens a gallery page with each look on 3 sample slides made with their photos
     and their handle. Text that lands on a face is moved off it by itself; a `NOTE ... TEXT OVER THE FACE` line
     means it could not be: run it again with the photos in another order (the one with the most empty space above
     or below the face goes where that look's slide has the most text), or other photos, before they see it. Say one line on each and "or I can show you all of them" (run it again with every look).
     No photos yet: show the type-led looks (Horizon, Paper, Poster need none) and mention that the photo looks
     come alive with their photos or with generated pictures.
   - They pick, or pick and tweak ("Soft Studio but in my green": `look new "<name>" --from soft-studio` with the
     change). `look default "<name>"`.
4. Then straight into the carousel they asked for.

A buyer who asks for the setup again ("set up carousels again", "change my carousel look", "new carousel look"):
show what they have in two plain lines (handle, looks, default) and change only what they ask. Never delete a look.

## Making a carousel

```
1. Source.
   A topic or idea: decide the angle (craft.md: the contrast it runs on, the promise of slide 1). Anything factual
     (a tool's name, a price, a command, a stat, a link) gets checked with a web search before it goes on a slide.
   A video: references/from-video.md, steps 1 to 4.
   Their own text (notes, a thread, a newsletter, a transcript): the ideas and their best lines, rewritten for slides.
   Not sure what they want? One question, then go.
2. PY "CS/scripts/carousel.py" new "<title>" [--look "<name>"] [--source "<video>"]     (skip if from-video did it)
   Pictures, when the look is photo-led or the copy calls for them: "Pictures" below.
3. Write the copy for EVERY slide and show it (below), with which picture goes on which slide. Wait for their OK.
   Change what they say, show the changed slides again, wait again. Nothing is rendered before the OK.
4. Write <carousel folder>/carousel.json from the approved copy (references/slides.md). The words are the approved
   words; the fields are your choice (craft.md, "Picking the right layout for the content").
5. PY "CS/scripts/carousel.py" render "<carousel folder>"
       one CHECK line per slide. LOOK at <carousel folder>/work/sheet.jpg (all slides) and at full size at any
       slide with a note. Fix (cut words, split a slide, pick another layout) and render again. When every slide
       is clean the swipe preview opens in their browser by itself.
6. Tell them, in two or three lines: it's open in their browser, where the PNGs are (the folder's slides/), and
   that they can ask for any change. Mac: offer "I can open the folder so you can AirDrop them to your phone."
```

### Pictures

A photo-led look (`carousel.py looks` says "needs photos") is built around pictures; any look can use them. Ask once,
in one message, where the pictures come from, offering only what applies:
- **Their photos.** Files or a folder they drop or name. `PY "CS/scripts/carousel.py" photos "<files or folders>" ...
  --out "<carousel folder>"` copies them in (iPhone HEIC too) as `assets/photos/p01.jpg ...` in the order given and
  makes `assets/photo-sheet.jpg`. They set the order ("this one first, then...") or let you choose: look at the sheet
  and at each photo you use, and pick by job (the cover: their best face photo, eye contact, room for the headline;
  a proof slide: the screen or the result; the rest: variety in framing, one consistent light). Then
  `PY "CS/scripts/carousel.py" faces --out "<carousel folder>"` finds every face (saved in `assets/photos.json`):
  give it as "face" on every slide where text sits on that photo. The render then keeps text off it.
- **A connector.** Look at your own tools: Google Drive, Google Photos, Dropbox, OneDrive, iCloud, Notion or any
  other files connector the buyer has connected. Search it for what the carousel needs ("photos from the shoot",
  "pictures of the studio"), show them what you found by name, download only what they confirm into a folder, then
  `photos` as above. No connector: say which ones would work and that they can connect one, or just drop files.
- **From their video.** Stills (and a cut-out of them for the cover): `references/from-video.md`.
- **Generated.** `references/images.md`: first see whether they already have an image generator (a connector in
  your tools, or a key `imagegen.py check` finds), ask which one to use when there are several, show the list of
  pictures and the cost before making more than 2, and never fake a result or a real person.
Mixing is fine (their face on the cover, generated scenes for the tips).

### The copy, for approval

Plain text, one block per slide, in the order it will post. What the slide SAYS and roughly how it looks, never
field names or JSON. The loud part in CAPS only if the look uses caps.

```
Slide 1 (cover)
  Big: 8 free sites that make Claude a design genius
  Small line: Stop shipping websites that look AI-made.
  Picture: you, mid-sentence, from 0:12 of the reel

Slide 2
  Label: Site 01
  Big: Animated sites as copy-paste prompts.
  Under it: Animated 3D websites, and every one comes with the prompt.
  To copy: [Paste the motionsites prompt here] Build this for my business...

...

Slide 9 (last)
  Big: Want all 8 websites + the prompts?
  Comment the word: DESIGN
  Then: and I'll send you the full guide.
```

End with one line: "Want any changes, or should I make it?" Also offer a post caption once (2 to 4 short lines in
their voice plus the CTA; hashtags only if they use them). The caption is shown on the preview page.

### Notes after they see it

- "Change slide 3": edit carousel.json, `render ... --only 3`. Show the slide.
- Copy changes on several slides: show the new copy first if it is more than a word or two, then render.
- "Bigger", "more space", "different colour": a one-off goes in the slide's `css` or the carousel's `css`; a change
  they want "always" goes into their look (look.css / look.json) and a line in look.md "Standing notes", then render.
- "Make it in Paper instead": `render ... --look paper` (or change `look` in carousel.json).
- "For LinkedIn too": `render ... --pdf` (a PDF document post, one page per slide). Size 4:5 or 1:1 on request.
- "Open the folder": open `<carousel folder>/slides` (Mac `open`, Windows `explorer`).

## Hard rules

1. Copy first, approval, then render. Never render a carousel they have not approved the words of.
2. Everything on a slide is real or a clear placeholder. No invented numbers, results, quotes, testimonials or
   screenshots. Checked facts only. A real person's words only when they said them, credited.
3. Never another creator's words, handle, logo, photos or mascot on their slides. A look copied from an example
   copies the design only.
4. No em dashes on slides. Readable on a phone: the check's SMALL TEXT, TOO MUCH, PAST THE MARGIN and OFF THE SLIDE
   are fixed before they see it.
5. Never delete or change the buyer's files. Their videos and pictures are only read; frames and photos are copies.
   Text never covers a face (the "face" field; the check says TEXT OVER THE FACE).
6. Every carousel gets its own folder and its own file names (`<slug>-01.png`), so nothing overwrites another.

## What the buyer hears

- Start: "On it. I'll write the copy for each slide first so you can check it before I design anything."
- Copy ready: the slide blocks, then "Want any changes, or should I make it?"
- Rendering: "Making it now."
- Done: "It's open in your browser: swipe through it like the real post. The slides are in Carousels/<name>/slides.
  Tell me anything you'd change."
- From a video: "I pulled the main points from your reel and kept your best lines. Here's the copy."
- First look built from their examples: "Here's your look on three sample slides: what matches, and what I could
  not match. Tell me what to change, then I'll save it as <name>."
