#!/usr/bin/env python3
"""Lay a finished effect slot into the reel: checks the slot's render, copies it into the project and writes its
entry in <project>/plan.json ("slots"). Run build_reel.py afterwards.

Usage:  PY fx_add.py <project_dir> <slot_dir> [--captions keep|hide] [--hide-captions 3.9-4.9,6.0-6.4] [--caption-y 1290]
                                              [--no-sfx] [--no-match] [--picks <file>] [--remove]

What it checks before it adds anything:
  - <slot>/renders/<slot folder>.mp4 exists, is 1080x1920 and has exactly the slot's frame count
  - the render is newer than index.html and the red safe-zone guide is not in it
  - the slot sits inside the parts of the reel the buyer allowed for this effect ("effectSections" in the picks)

What it writes into the plan entry:
  src            the render, copied to <project>/assets/fx/<slot folder>.mp4
  from / to      the slot's frames in reel seconds
  captions       "hide" or "keep": what the effect says about the reel's own captions while it plays
                 (effects/<key>/slot.json). --captions overrides it. --hide-captions a-b,c-d hides them only for
                 those windows (reel seconds), for an effect whose own words cover part of the slot. An effect
                 that knows its own window (Before and After: from the line coming in until the look eases off)
                 writes it to <slot>/work/reel_captions.json and it is used when neither flag is given.
  caption_y      --caption-y N: the reel's own captions stay on, in the buyer's style, and the TOP of their line
                 moves to screen y N while the slot plays (for an effect that needs the chest for itself: its
                 build.py prints the value). The same number is right for every caption style, and the move
                 happens on a caption change, never in mid caption. Use with --captions keep or a "keep" effect.
  (a check)      the head in the slot's own clean cutout is compared with layout.json: more than 60 px apart
                 prints a CHECK line, because captions and the self-check read layout.json.
  (the picture)  a slot render goes through the renderer twice, the footage around it once, and every pass shifts
                 tone and colour a little. The slot's first frame is still plain footage, so that shift is measured
                 there against the same reel frame and taken back out of the copy in assets/fx/. If the effect
                 already covers the first frame it falls back to a plain brightness lift ("gain") and says so.
                 --no-match skips the measuring.
  sfx            the effect's own sounds, read from the slot's index.html, replayed over the reel's voice track
                 (--no-sfx leaves them out)
--remove takes the slot's entry out of plan.json again (the files stay).
"""
import os
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402
import fxlib  # noqa: E402


def opt(name):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    return None


def rel(path):
    return path.replace('\\', '/')


def sound_cues(page, slot, proj, name, t0):
    """The effect's <audio> elements (everything but the a-roll's own track) as reel-time cues. The files are the
    stock sounds the project already has in assets/sfx, or get copied to assets/fx/."""
    cues = []
    for tag in re.findall(r'<audio\b[^>]*>', page):
        at = dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
        src = at.get('src', '')
        if not src or src.endswith('aroll.mp4'):
            continue
        file = os.path.join(slot, *src.split('/'))
        if not os.path.isfile(file):
            print(f'note: the slot plays {src} but that file is not there: left out')
            continue
        base = os.path.basename(src)
        if src.startswith('assets/sfx/') and os.path.isfile(os.path.join(proj, 'assets', 'sfx', base)):
            dst = f'assets/sfx/{base}'
        else:
            dst = f'assets/fx/{name}-{base}'
            shutil.copyfile(file, os.path.join(proj, *dst.split('/')))
        cues.append({'src': dst, 'at': round(t0 + float(at.get('data-start') or 0), 3),
                     'media': round(float(at.get('data-media-start') or 0), 3),
                     'dur': round(float(at.get('data-duration') or .5), 3),
                     'vol': round(float(at.get('data-volume') or .3), 3)})
    return cues


def main():
    skillenv.utf8_stdio()
    pos = [a for a in sys.argv[1:] if not a.startswith('--')]
    for flag in ('--captions', '--hide-captions', '--caption-y', '--picks'):
        if opt(flag) in pos:
            pos.remove(opt(flag))
    if len(pos) < 2:
        sys.exit(__doc__)
    proj, slot = os.path.abspath(skillenv.path_arg(pos[0])), os.path.abspath(skillenv.path_arg(pos[1]))
    name = os.path.basename(slot)
    plan_path = os.path.join(proj, 'plan.json')
    plan = fxlib.read(plan_path, {}) or {}
    slots = [s for s in (plan.get('slots') or []) if s.get('slot') != name]
    if '--remove' in sys.argv:
        plan['slots'] = slots
        fxlib.write(plan_path, plan)
        print(f'removed {name} from plan.json ({len(slots)} slot(s) left). Run build_reel.py again.')
        return
    clip = fxlib.read(os.path.join(slot, 'clip.json'))
    if not clip:
        sys.exit(f'{slot} is not an effect slot (no clip.json).')
    key = clip.get('key') or clip.get('effect')
    meta = fxlib.read(os.path.join(slot, 'slot.json'), {}) or fxlib.slot_meta(key) or {}
    entry = fxlib.index().get(key, {})
    label = entry.get('name', key)
    if os.path.abspath(clip.get('src', '')) != os.path.join(proj, 'assets', 'aroll.mp4'):
        sys.exit('this slot was not cut from this reel\'s a-roll, so its frames do not line up with the reel. '
                 'Make it with: fx_new.py <effect> --project <project> --from S --to S')
    render = os.path.join(slot, 'renders', name + '.mp4')
    index = os.path.join(slot, 'index.html')
    if not os.path.isfile(render):
        sys.exit(f'no render yet: {render}. Finish the slot\'s commands (see {os.path.join(slot, "RUN.txt")}).')
    frames, f0 = int(clip['frames']), int(clip['frame'])
    got, size = fxlib.probe_frames(render), fxlib.probe_size(render)
    if got != frames or size != (1080, 1920):
        sys.exit(f'the render is {got} frames at {size[0]}x{size[1]}; the slot is {frames} frames at 1080x1920. '
                 'A slot has to hand back exactly what it was given: fix the effect build, render again.')
    with open(index, encoding='utf-8') as fh:
        page = fh.read()
    if fxlib.SAFE_MARK in page:
        sys.exit('the red safe-zone guide is in index.html. Run build.py without SAFE=1, render again, then add.')
    if os.path.getmtime(index) > os.path.getmtime(render) + 1:
        sys.exit('index.html changed after the render (build.py ran again). Render the slot again, then add.')
    t0, t1 = f0 / 30, (f0 + frames) / 30
    picks = fxlib.read(skillenv.path_arg(opt('--picks')) if opt('--picks') else skillenv.picks_file(), {}) or {}
    where, dur = fxlib.reel_parts(proj)
    ok, why = fxlib.part_verdict(picks, key, where, t0, t1)
    if not ok:
        sys.exit(f'NOT ADDED  {label}: {why}.')
    clash = [s for s in slots if not s.get('off') and float(s['from']) < t1 - .01 and float(s['to']) > t0 + .01]
    if clash:
        sys.exit(f'NOT ADDED  {label}: its frames overlap the slot "{clash[0].get("slot") or clash[0].get("src")}" '
                 f'({clash[0]["from"]} to {clash[0]["to"]}s). Two effects cannot share frames: remove one (--remove).')

    os.makedirs(os.path.join(proj, 'assets', 'fx'), exist_ok=True)
    dst = f'assets/fx/{name}.mp4'
    dst_file = os.path.join(proj, *dst.split('/'))
    aroll = os.path.join(proj, 'assets', 'aroll.mp4')
    # a slot goes through the renderer twice, the footage around it once: take one pass back out of the slot
    gain, match = 1.0, 'not matched'
    fit = None if '--no-match' in sys.argv else fxlib.pass_fit(aroll, f0, render)
    if fit and fit['rms'] < 4 and fit['share'] > .5:
        wrote = fxlib.undo_pass(render, dst_file, fit, frames)
        if wrote == frames and fxlib.probe_frames(dst_file) == frames:
            match = f'tone and colour matched to the reel (measured on {fit["share"] * 100:.0f}% of the first frame, fit {fit["rms"]:.1f})'
        else:
            fit = None
    else:
        fit = None
    if fit is None:
        shutil.copyfile(render, dst_file)
        a, s = fxlib.luma(aroll, f0), fxlib.luma(render, 0)
        gain = round(a / s, 4) if a and s else 1.0
        if not .96 <= gain <= 1.06:        # the effect already fills the slot's first frame: no fair comparison
            gain = 1.0
        match = (f'NOT matched pixel for pixel (the effect covers the first frame, or --no-match): brightness lift {gain} only. '
                 'Look hard at both edges of the slot in the final render')
    captions = opt('--captions') or meta.get('reel_captions') or 'hide'
    if captions not in ('keep', 'hide'):
        sys.exit('--captions takes keep or hide')
    item = {'key': key, 'slot': name, 'src': dst, 'frame': f0, 'frames': frames, 'from': round(t0, 4), 'to': round(t1, 4),
            'captions': captions, 'gain': gain}
    if opt('--hide-captions'):
        try:
            item['hide_captions'] = [[float(x) for x in w.split('-', 1)] for w in opt('--hide-captions').split(',') if w]
        except ValueError:
            sys.exit('--hide-captions takes windows in reel seconds, like 3.9-4.9,6.0-6.4')
    if opt('--caption-y'):
        try:
            item['caption_y'] = int(float(opt('--caption-y')))
        except ValueError:
            sys.exit('--caption-y takes one number: the screen y the top of the reel\'s caption line moves to while the slot plays')
        if not 236 <= item['caption_y'] <= 1376:
            sys.exit(f'--caption-y {item["caption_y"]} would push the captions out of the safe zone (use 236 to 1376)')
    if opt('--hide-captions'):
        pass
    elif not opt('--captions'):
        # an effect whose own words cover only part of the slot says so itself (build.py writes work/reel_captions.json,
        # slot seconds): the reel's captions are hidden for just that window and carry every other word
        own = fxlib.read(os.path.join(slot, 'work', 'reel_captions.json'))
        if isinstance(own, dict) and isinstance(own.get('hide'), list):
            wins = [[round(max(t0, t0 + float(a)), 3), round(min(t1, t0 + float(b)), 3)] for a, b in own['hide']
                    if float(b) > float(a)]
            if wins:
                item['hide_captions'] = wins
            else:
                item['captions'] = captions = 'keep'
    item['sfx'] = [] if '--no-sfx' in sys.argv else sound_cues(page, slot, proj, name, t0)
    plan['slots'] = sorted(slots + [item], key=lambda s: float(s['from']))
    fxlib.write(plan_path, plan)

    hidden = item.get('hide_captions')
    cap_line = ('hidden for ' + ', '.join(f'{h[0]:.2f} to {h[1]:.2f}s' for h in hidden) if hidden
                else 'kept on while it plays' if captions == 'keep' else 'hidden while it plays')
    if item.get('caption_y') is not None:
        cap_line += f', top of the caption line moved to y {item["caption_y"]}'
    print(f'added {label}: reel {t0:.3f} to {t1:.3f}s (frames {f0} to {f0 + frames - 1}), parts: {why}')
    print(f'  picture  {dst}   {match}')
    print(f'  captions {cap_line}' + (f'   ({meta["captions_note"]})' if meta.get('captions_note') else ''))
    print(f'  sounds   {len(item["sfx"])} from the effect' + (': ' + ', '.join(f"{os.path.basename(c['src'])}@{c['at']:.2f}s" for c in item['sfx']) if item['sfx'] else ''))
    if key not in (picks.get('effects') or []):
        print(f'  note: {label} is not in the saved picks (fine for a one-off the buyer asked for)')
    warn = fxlib.head_check(proj, slot, t0)
    if warn:
        print('  ' + warn)
    print(f'next: build_reel.py "{skillenv.shell_path(proj)}", lint, render, then frames_check.py --at '
          f'{t0 + .1:.2f},{(t0 + t1) / 2:.2f},{t1 - .1:.2f},{min(t1 + .1, dur - .05):.2f} to see the slot and both of its edges')


if __name__ == '__main__':
    main()
