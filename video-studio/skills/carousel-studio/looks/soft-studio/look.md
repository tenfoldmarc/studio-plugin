# Soft Studio

A photo-led look: the buyer's own photos edge to edge in soft light, with type that feels like a boutique studio's
Instagram. Calm, feminine, premium. Best for pilates, yoga, wellness, beauty, fitness coaches, studios, self-care.

- Ground: warm cream with a soft blush glow in the middle (text-only slides). Photo slides: the photo full bleed,
  as it is, never dimmed overall. Little four-point sparkles in the top right and bottom left corners.
- Colour: plum ink (#4B1834) on the ground, white on photos. Mauve (#B97FA5) for numbers, sparkles and dots.
  Butter (#FFF2C8) for pills (the SWIPE cue, chips, the CTA keyword). Blush and cream behind everything.
- Type: Instrument Serif, tall and tight, for every headline. One accent per headline: `[[word]]` is the italic
  serif; a whole `[[line]]` is the flowing script (Pinyon Script); with the slide class `script` an inline
  `[[word]]` is the script too ("Have a great [[Monday]]"). Body in light Inter. Labels in tiny tracked caps
  (REMINDER, NOTE 01). Handwritten notes and photo captions in Sacramento.
- Hierarchy: one big serif headline, a short light sans line under it, small tracked-caps label above. Calm, lots
  of air. Never more than one script word or line per slide.
- Layouts:
  - Cover: a full photo, text at the bottom, centred (the face up top). A search-bar or note sticker in the gap.
  - Content on a photo: `"fit": "bleed"` with the text at the bottom, or class `text-top` when the face is low.
    The plum fade starts just above the text, so the rest of the photo stays bright. Busy photo: class `glass`.
    A light flat lay or plain wall: class `ink` (plum text, soft cream fade).
  - Half photo: `"fit": "half"`, side top (share 0.4 to 0.5) or left/right (0.46 to 0.5), text on the blush.
    A `caption` on it is written by hand.
  - Collage: `photos` pair or trio with `"frame": "polaroid"` and handwritten captions, `"height": 600` leaves
    room for a ribbon under it (a `strip` sticker in butter, rotated a few degrees).
  - Giant words: `ghost` ("Eat\nSleep\nPilates\nRepeat") in huge mauve italic serif behind a person cut-out on
    `"place": "stage"`. Only on the ground or behind a cut-out, never over a face in a full photo.
  - Text only: `statement` with a label ("Reminder") and one centred line with one italic word.
  - Lists: rows/steps with italic mauve numbers and hairlines; cards for grid and versus; chips as butter pills.
  - CTA: headline, then the keyword in a big butter pill. Works on a photo or on the ground.
- Chrome: only the handle, tiny tracked caps, bottom centre. The butter SWIPE pill on the cover only. No counter.
- Stickers that fit: `search` (white pill, mauve caret, plum button), `bubble` side left (cream "pov:" bubble),
  `hand` notes and product labels, `sparkle`, `label` (butter pill like "15% off this week"), `strip` ribbons,
  `polaroid`. Give every sticker on a photo a spot clear of the face.
- Copy feel: warm, short, encouraging, sentence case, no emoji. A cover is a promise ("Things I wish I knew before
  my first pilates class"); middle slides are one gentle point each; a reminder slide is one kind line.

## Photos for this look

Bright, airy, soft natural daylight: cream or white studios, pale wood, linen, blush or neutral activewear,
candid calm poses, a matcha, a mat, a reformer. Never dark, moody or high contrast. Pick photos with plain wall or
floor where the text goes: covers need calm space in the lower or upper third away from the face. Crop so the
face sits in the top 40% for bottom text, or use `text-top` when the person is low in the frame. Always give
`face` for a photo with text on it. Flat lays: shoot from above with space between objects for handwritten labels.

## Standing notes
