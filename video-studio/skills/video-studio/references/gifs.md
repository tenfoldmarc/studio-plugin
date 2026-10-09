# GIFs

Only when the buyer asks for them: "add a GIF when I say X", "put some GIFs in this one", or "always use GIFs"
(then write it into `ST/my-style.md` and do it on every reel). Never on your own.

## Which lines get one

A GIF is a reaction, so it goes on a line that has one in it: a joke, a surprise, a big number, a mistake, a win.
One to three in a reel, each on for 1.5 to 3 seconds, never two at once and never during an effect slot. The
buyer named the line or the GIF: do exactly that. "Add GIFs where they fit": you pick the lines from `words.json`.

## Find it, look at it, place it

```
PY "SK/scripts/gif_find.py" "<project>" "mind blown"      1 to 4 words: the reaction, not the sentence
       GIFs from Giphy and Tenor on one numbered sheet. LOOK at it. Pick the one that reads at a glance and
       fits the buyer's tone.
PY "SK/scripts/gif_add.py" "<project>" "<link of the one you picked>" --from 3.2 --to 5.4
       then build_reel.py --safe and look at one snapshot inside that time
```
- Nothing good on the sheet: run it again with other words. Use real GIFs, the kind people know from their
  group chats. `--stickers` (cut-out shapes) only when the buyer asks for a sticker.
- The buyer gave a GIF file or a link (Giphy, Tenor, or one that ends in .gif): skip the search and pass it
  straight to `gif_add.py`.
- Where it sits: `gif_add.py` picks a spot that keeps the face clear (above the head, else the open wall beside
  the speaker). Move it with `--place above|left|right|top|chest` or `--at X,Y`, resize with `--width`. Run it
  again with the same `--id` to replace it, `--remove <id>` to take it out.
- In the snapshot: the GIF is not on the face, not on a caption, and not under the pinned title. It follows the
  buyer's style like everything else: a calm style gets a small one, not three loud ones.
- `STATUS gifs NONE` (the search gave nothing or is offline): say "I couldn't find a GIF for that line. Send me
  one, or a link to one, and I'll drop it in."

## What kind

Reaction GIFs from shows, films and memes are what the buyer means, so use them: asking for GIFs is the one
exception to hard rule 4 ("never a real person who is not the buyer"). The first time you add GIFs for a buyer,
say once: "These GIFs come from Giphy and Tenor, the same ones you see in chats."

Say it plainly at delivery: "GIFs: a mind-blown one on the line about the price."
