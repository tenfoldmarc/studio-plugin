# Bold Creator

The creator's own face fills the slide. A huge white all-caps headline sits above the head, the handle sits over it
in small mono type, and nothing else gets in the way. Simple, loud, face-first, like the covers of the big
talking-head creators in AI, tech, business, design, money and fitness.

- **Ground:** a full-bleed photo of the creator, with a dark fade at the top (for the headline) and at the foot
  (for the payoff). Slides without a photo stand on a dark charcoal studio wall with a soft light in the middle and
  a little grain.
- **Colour:** white type. One warm orange accent (`--accent`) for the hit word, the step numbers, the check marks and
  the panel behind a cut-out. A light "screenshot" paper (`--paper`) for the thing to keep and the keyword.
- **Type:** Archivo at its heaviest weight and wide width (900, 110 to 125%), all caps, tight lines, every line sized to fill the
  width (short punchy lines go big, long ones smaller, so stacks look like "STOP / COLLECTING / AI TOOLS").
  Inter for reading text. JetBrains Mono for the handle, labels, captions and small print. Instrument Serif
  (regular, sentence case) for the quiet `((...))` line, the kicker and quotes: the "editorial title" moment.
- **Hierarchy:** one loud headline, then very little. Body text is short. Labels are small mono pills.
- **Layouts:** everything centred. Cover: headline stack in the upper part, face below. Content on a photo: headline
  on top, face in the middle, one payoff at the foot (callout, payload, keyword). Lists, grids, numbers and
  quotes go on a text-only slide or a half-photo slide, never across a face.
- **Chrome:** the handle in mono at the top centre of every slide (it moves down to sit right over the headline when
  the photo takes the top half). A quiet `01 / 07` bottom left and `Swipe ->` bottom right. Nothing else.
- **Blocks:** list rows and bullets are dark glass panels (blurred over photos). The thing to keep (payload) is a
  light app window with three dots and a title bar. Pictures in the middle are rounded like dropped-in screenshots.
  The CTA keyword sits on a white slab.
- **Copy feel:** short, direct, spoken. Headlines of 2 to 4 short lines, 1 to 3 words a line works best ("Pick your
  lane", "Ignore the noise", "Stop trying everything"). Sub lines of one sentence. No emojis, no hashtags.

## Photo slide recipes

- **Cover / statement on a photo:** `"image": {"src": ..., "fit": "bleed", "face": "x,y,w,h"}`. Push the photo
  down so the headline sits above the head with a class: `drop` (14%), `drop-l` (24%) or `drop-xl` (32%, the
  classic cover: face in the lower half). The top of the photo melts into the dark wall.
- **Half photo:** `"fit": "half", "side": "bottom"` (text on top, the person below, like a split slide) or
  `"side": "top"` (photo on top, the handle and headline under it). Fits a headline plus a sub, 2 or 3 short points
  or a payload. Use `focus` ("50% 40%") to slide the face into the visible half.
- **Cut-out (`carousel.py cutout`, `"fit": "cutout", "place": "stage"`):** the person turns black and white and
  stands on an orange panel that starts under the headline. Class `natural` keeps the colour.
- **Split screen:** `"photos": {"layout": "pair", "place": "bleed", ...}` stacks two photos top and bottom; keep the
  text short (a headline, a note) and pick photos whose faces sit low in the top one.
- **Collage in the middle:** `"photos": {"layout": "pair"}` = two rounded screenshots side by side, with mono
  captions.
- **Black and white:** class `bw` on any photo slide.

## Choosing and cropping photos

- Real photos of the creator: mid-shot, talking to camera, in a real place (desk, studio, office, cafe, street).
  Eyes open, mouth mid-word or a clear expression. Phone portrait photos are ideal.
- The head should be in the middle or lower half with plain room above it (wall, ceiling, sky). Photos where the head
  touches the top need `drop-l` or `drop-xl`.
- Always mark the face (`"face": "x,y,w,h"`, forehead to chin, in % of the photo) so the render keeps the type off
  it. The headline may overlap the hair or a cap, never the face.
- Dark or moody backgrounds look best; bright outdoor photos work too because of the top and foot fades.

## Standing notes
