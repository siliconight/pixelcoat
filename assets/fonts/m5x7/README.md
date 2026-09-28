# m5x7

A small proportional pixel face: labels, price cards, small print.

- **Name:** m5x7
- **Designer:** Daniel Linssen
- **Licence:** CC0 1.0 Universal -- public domain. The itch.io page's licence
  field reads "Creative Commons Zero v1.0 Universal". No attribution is
  required and none is claimed; `LICENSE.txt` beside this file is the CC0 1.0
  dedication text (the font ships as a bare TTF with no licence file of its
  own).
- **Source:** managore.itch.io/m5x7
- **Fetched:** 2026-09-28, `m5x7.ttf`, 34,300 bytes,
  sha256 `47c3f0b01f0fd417b3a44c2888a71d3072f750e76f3e6e946a6a9b188d988cbf`.
  Downloaded through the page's free "just take me to the downloads" path;
  nothing was purchased.

MEASURED BEFORE IT WAS VENDORED, through Zoo's `tools/mint_pixel_type.py`
rules: all 96 characters the factory letters (printable ASCII and ¢) are in
its character map; at 16 px, and at 32 as the doubled grid, every glyph is
pure on/off with a whole-pixel advance, and a string PIL sets equals its
glyphs laid at their advances -- no kerning. So it is minted at 16 px like
Pixel Operator, and a table of its bitmaps loses nothing.

WHY THIS ONE: docs/proposals/CC0_FONTS.md, the small-print face. Its
siblings m3x6 and m6x11 ask for attribution and are NOT here.
