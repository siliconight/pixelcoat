"""Smooth type: anti-aliased lettering from minted outline faces (0.62.0).

The walker, 2026-10-09, of a lit sign over a club's door: "need better looking fonts on these
signs" -- and then: "use Blue Highway for the shop signs". Zoo 1.90.0 set the names it paints
over a door in Blue Highway Condensed; this sets the names Pixelcoat letters on a business's
street band the same way, from the same face (`tools/mint_smooth_type.py` mints it, and its
table is byte-identical to Zoo's).

A face here is a CC0 outline font rasterised ONCE, large, into a coverage table
(`smooth_faces/`). A line is composed from those masters and AREA-RESAMPLED to the size a sign
asks for, in numpy: exact anti-aliasing, and the same bytes on every machine, which a font drawn
by the host's FreeType at build time would not give.

A line's size is its CAP HEIGHT in pixels, because that is what a sign painter means by "this
tall" and it does not move with a face's ascender.

    cov = coverage("JAWN'S HOAGIES", 40)     # float 0..1, rows x cols, trimmed to the ink

No kerning (see the mint tool). An unknown face or a character the face does not have raises,
naming what there is.
"""
from __future__ import annotations

import importlib

import numpy as np

FACES = ("highway_cond",)
#: The face a business's sign speaks in: the shop's own hand, Zoo's `smooth_type.OWNERS`
#: "shop_small" -- one face for the door box and the band over it.
SHOP_FACE = "highway_cond"

_TABLES = {}
_MASTERS = {}


def _table(face):
    t = _TABLES.get(face)
    if t is None:
        if face not in FACES:
            raise ValueError(f"no smooth face {face!r}; the faces are {', '.join(FACES)}")
        t = importlib.import_module(f".smooth_faces.{face}", __package__)
        _TABLES[face] = t
    return t


def _glyph(face, ch):
    key = (face, ch)
    g = _MASTERS.get(key)
    if g is None:
        t = _table(face)
        if ch not in t.GLYPHS:
            raise ValueError(f"smooth face {face!r} has no {ch!r}")
        adv, xo, yo, w, h, hx = t.GLYPHS[ch]
        a = (np.frombuffer(bytes.fromhex(hx), dtype=np.uint8).reshape(h, w) if w and h
             else np.zeros((0, 0), dtype=np.uint8))
        g = (float(adv), int(xo), int(yo), a)
        _MASTERS[key] = g
    return g


def _master(text, face):
    """The line at master size: float coverage 0..1, the line box tall."""
    t = _table(face)
    pen, places = 0.0, []
    for ch in text:
        adv, xo, yo, a = _glyph(face, ch)
        places.append((int(round(pen)) + xo, yo, a))
        pen += adv
    left = min([x for x, _y, a in places if a.size] + [0])
    right = max([x + a.shape[1] for x, _y, a in places if a.size] + [int(np.ceil(pen))])
    top = min([y for _x, y, a in places if a.size] + [0])
    foot = max([y + a.shape[0] for _x, y, a in places if a.size] + [t.ASCENT + t.DESCENT])
    out = np.zeros((foot - top, right - left), dtype=np.float32)
    for x, y, a in places:
        if not a.size:
            continue
        h, w = a.shape
        view = out[y - top:y - top + h, x - left:x - left + w]
        np.maximum(view, a.astype(np.float32) / 255.0, out=view)
    return out


def _weights(n_in, n_out):
    """An (n_out, n_in) matrix that area-averages ``n_in`` samples into ``n_out``: each output
    pixel is the mean of the span of input it covers, partial pixels by their share."""
    m = np.zeros((n_out, n_in), dtype=np.float32)
    step = n_in / float(n_out)
    for i in range(n_out):
        a, b = i * step, (i + 1) * step
        j0, j1 = int(np.floor(a)), min(n_in, int(np.ceil(b)))
        for j in range(j0, j1):
            m[i, j] = min(b, j + 1) - max(a, j)
        m[i] /= max(step, 1e-9)
    return m


def _resample(a, new_w, new_h):
    h, w = a.shape
    if h == 0 or w == 0 or new_w <= 0 or new_h <= 0:
        return np.zeros((max(0, new_h), max(0, new_w)), dtype=np.float32)
    return _weights(h, new_h) @ a @ _weights(w, new_w).T


def coverage(text, cap_px, face=SHOP_FACE):
    """``text`` set with capitals ``cap_px`` tall: float coverage 0..1, rows x cols, cropped to
    the ink (an empty line is one empty pixel). Quantised to 8 bits, as a texture will hold it,
    so two calls agree to the byte."""
    t = _table(face)
    m = _master(str(text), face)
    ys = np.where(m.max(axis=1) > 0)[0]
    xs = np.where(m.max(axis=0) > 0)[0]
    if not len(ys):
        return np.zeros((1, 1), dtype=np.float32)
    m = m[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1]
    k = float(cap_px) / float(t.CAP)
    new_w = max(1, int(round(m.shape[1] * k)))
    new_h = max(1, int(round(m.shape[0] * k)))
    out = np.clip(np.rint(_resample(m, new_w, new_h) * 255.0), 0, 255)
    return (out / 255.0).astype(np.float32)


def fit_cap(text, max_w, max_h, face=SHOP_FACE):
    """The largest whole cap height at which ``text``'s ink fits ``max_w`` x ``max_h`` px, or
    None when not even a 4 px cap does: a name that does not set is a defect to report, not to
    crop. Measured on the master, so it is arithmetic, not trial renders."""
    t = _table(face)
    full = _master(str(text), face)
    ys = np.where(full.max(axis=1) > 0)[0]
    xs = np.where(full.max(axis=0) > 0)[0]
    if not len(xs):
        return None
    ink_w, ink_h = xs[-1] - xs[0] + 1, ys[-1] - ys[0] + 1
    for cap in range(int(max_h), 3, -1):
        k = cap / float(t.CAP)
        if ink_w * k <= max_w and ink_h * k <= max_h:
            return cap
    return None
