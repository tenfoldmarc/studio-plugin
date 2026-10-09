#!/usr/bin/env python3
"""Cut the speaker out of the assembled cut -> <project>/assets/subject.webm (VP9 + alpha), then verify it is
frame-for-frame the same length as aroll.mp4 (a mismatch means the cutout will drift; re-run assemble.py).

Usage:  PY cutout.py <project_dir> [extra remove-background arguments, e.g. --device cpu]
Speed: ~7s per second of footage on Apple Silicon (CoreML). Everywhere else, Windows included, HyperFrames runs the
model on the CPU (no GPU): it works, and the time depends on the processor (forced onto the CPU of an M1 Pro it
took about twice as long as CoreML; nothing has been measured on a Windows PC yet). Run it in the background, one
cutout at a time (~1.5 GB of RAM). The first run downloads the segmentation model (~170 MB).
Prints a progress line every 30s. Standard library only.
"""
import collections
import os
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True   # no __pycache__ next to the scripts (a plugin's folder is not ours to write in)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')


def frames(f):
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                          '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', f], **skillenv.TEXT).stdout
    return out.strip().split(',')[0]


def split_progress(buf):
    """-> (finished lines, unfinished rest). HyperFrames redraws its spinner with cursor escape codes instead of
    newlines, so every escape code counts as a line break, and the spinner glyph in front is dropped."""
    *lines, rest = re.split(r'[\r\n]+', ANSI.sub('\n', buf))
    return [l for l in (re.sub(r'^[^\w\[(]+', '', l).strip() for l in lines) if l], rest


def run(argv, env, cwd, every=30):
    """Run quietly like `| tail -1`, but print the newest progress line every `every` seconds so a long CPU run in
    the background is visibly alive. Returns (exit code, last lines)."""
    last, shown, t_print = collections.deque(maxlen=25), '', time.time()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf = ''
    while True:
        chunk = proc.stdout.read1(4096)
        if not chunk:
            break
        lines, buf = split_progress(buf + chunk.decode('utf-8', 'replace'))
        for l in lines:
            if not last or l != last[-1]:
                last.append(l)
        if last and last[-1] != shown and time.time() - t_print >= every:
            shown, t_print = last[-1], time.time()
            print(shown, flush=True)
    for l in split_progress(buf + '\n')[0]:
        last.append(l)
    return proc.wait(), list(last)


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    aroll, subject = os.path.join(proj, 'assets', 'aroll.mp4'), os.path.join(proj, 'assets', 'subject.webm')
    if not os.path.isfile(aroll):
        sys.exit(f'{aroll} not found: run assemble.py first.')
    # relative paths + cwd: nothing with the user's folder name goes through npx's argument handling
    argv, env = skillenv.hyperframes_command(['remove-background', 'assets/aroll.mp4', '-o', 'assets/subject.webm',
                                              '--quality', 'best'] + sys.argv[2:])
    t0 = time.time()
    code, last = run(argv, env, proj)
    if code != 0:
        print('\n'.join(last))
        sys.exit(f'remove-background failed (exit {code}). Lines above are the end of its output.')
    if last:
        print(last[-1])
    a, s = frames(aroll), frames(subject)
    print(f'aroll frames {a} / cutout frames {s}   ({time.time() - t0:.0f}s)')
    if not a or a != s:
        sys.exit('FRAME MISMATCH: cutout will drift. Re-run assemble.py (clean CFR) then this script.')


if __name__ == '__main__':
    main()
