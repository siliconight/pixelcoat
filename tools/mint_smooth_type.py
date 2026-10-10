"""Mint Pixelcoat's SMOOTH faces: anti-aliased glyph tables from the CC0 outline fonts it vendors.

    python tools/mint_smooth_type.py [--face NAME | --all] [--check]

WHY A TABLE AND NOT THE FONT FILE (0.62.0). Pixelcoat's signage is byte-deterministic
(`core/signage.py`), and a font rasterised at build time is only as deterministic as the
FreeType that draws it: an edge pixel's coverage is the rasteriser's, and two machines' differ.
Pixel Operator survives that because `_render_ttf` thresholds every pixel to ink or none. A
printed letter cannot: its edge IS the partial pixel. So the outline is rasterised HERE, once,
large -- `EM` px to the em, 8-bit coverage -- and committed; `core/smooth_type.py` composes those
masters and area-resamples them to the size a sign sets its type at. Downsampling coverage by area
is exact anti-aliasing, and numpy does it the same on every machine.

THE SAME METHOD AS ZOO'S. Zoo mints its smooth faces from these same vendored files
(`zoo/tools/mint_smooth_type.py`, Zoo 1.46.0), so a name Pixelcoat letters on a street band and
the one Zoo paints over a door are one face at one em, and `--check` says whether this repo's
table still is what the font gives.

NO KERNING: glyphs are composed at their advances, as Zoo's are.

THE FACES are CC0, vendored here with their licence notes: Ray Larabie's Blue Highway (1998),
`assets/fonts/blue_highway/`, from typodermicfonts.com/public-domain/, "released under CC0 1.0
Universal".
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "assets", "fonts")
OUT = os.path.join(HERE, "..", "pixelcoat", "core", "smooth_faces")
EM = 64
CHARS = "".join(chr(c) for c in range(32, 127))
#: name -> file under assets/fonts. The module it mints to is the name.
FACES = {
    "highway_cond": "blue_highway/Blue Highway Cd.otf",
}

HEADER = '''"""{name}: a smooth face, minted by tools/mint_smooth_type.py. DO NOT EDIT.

{file}, CC0. EM = {em} px; coverage 0-255, one hex byte a pixel, row-major.
GLYPHS: char -> (advance, x_offset, y_offset, width, height, hex). The offsets
are from the pen and from the top of the line box (ASCENT above the baseline).
"""
EM = {em}
ASCENT = {ascent}
DESCENT = {descent}
CAP = {cap}
GLYPHS = {{
'''


def mint(path, name):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(path, EM)
    ascent, descent = font.getmetrics()
    cap = font.getbbox("H")
    cap_h = cap[3] - cap[1]
    rows = []
    for ch in CHARS:
        adv = font.getlength(ch)
        box = font.getbbox(ch)                       # relative to the pen, top of line = 0
        w, h = max(0, box[2] - box[0]), max(0, box[3] - box[1])
        if w == 0 or h == 0:
            rows.append((ch, round(adv, 3), 0, 0, 0, 0, ""))
            continue
        im = Image.new("L", (w + 4, h + 4), 0)
        ImageDraw.Draw(im).text((2 - box[0], 2 - box[1]), ch, font=font, fill=255)
        ink = im.getbbox()
        if ink is None:
            rows.append((ch, round(adv, 3), 0, 0, 0, 0, ""))
            continue
        crop = im.crop(ink)
        x_off = box[0] + ink[0] - 2
        y_off = box[1] + ink[1] - 2
        rows.append((ch, round(adv, 3), x_off, y_off, crop.width, crop.height, crop.tobytes().hex()))
    out = HEADER.format(name=name, file=os.path.basename(path), em=EM, ascent=ascent,
                        descent=descent, cap=cap_h)
    for ch, adv, xo, yo, w, h, hx in rows:
        out += f"    {ch!r}: ({adv}, {xo}, {yo}, {w}, {h}, {hx!r}),\n"
    return out + "}\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--face")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true", help="exit 1 if a minted module differs from the font")
    a = ap.parse_args(argv)
    names = list(FACES) if a.all or not a.face else [a.face]
    os.makedirs(a.out, exist_ok=True)
    init = os.path.join(a.out, "__init__.py")
    if not os.path.exists(init) and not a.check:
        open(init, "w", encoding="utf-8", newline="\n").write(
            '"""Smooth faces, minted. See tools/mint_smooth_type.py."""\n')
    bad = 0
    for name in names:
        text = mint(os.path.join(FONTS, FACES[name]), name)
        path = os.path.join(a.out, name + ".py")
        if a.check:
            same = os.path.exists(path) and open(path, encoding="utf-8").read() == text
            print(("ok   " if same else "STALE"), name)
            bad += 0 if same else 1
        else:
            open(path, "w", encoding="utf-8", newline="\n").write(text)
            print("minted", name, len(text) // 1024, "KiB")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
