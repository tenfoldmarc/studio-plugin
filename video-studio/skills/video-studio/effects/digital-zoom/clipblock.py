#!/usr/bin/env python3
"""Reads the CLIP block of build.py so track.py sees the same values without a second place to edit."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
START, END = '# ==== CLIP (edit this) ====', '# ==== END CLIP ===='
FPS = 30


def F(n):
    return n / FPS


def zoom(t_start, t_land, scale, kind, **kw):
    return dict(t0=t_start, t1=t_land, scale=scale, kind=kind, **kw)


def load():
    src = open(os.path.join(HERE, 'build.py')).read()
    a, b = src.index(START), src.index(END)
    ns = {'F': F, 'zoom': zoom}
    exec(compile(src[a:b], 'build.py CLIP block', 'exec'), ns)
    return ns
