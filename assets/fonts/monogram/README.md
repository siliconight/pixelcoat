# monogram

A monospace pixel face with an italic: register tape, price columns, shelf
tags.

- **Name:** monogram (the extended character set, and its italic)
- **Designer:** datagoblin
- **Licence:** CC0 1.0 Universal -- public domain. The itch.io page's licence
  field reads "Creative Commons Zero v1.0 Universal". No attribution is
  required and none is claimed; `LICENSE.txt` beside this file is the CC0 1.0
  dedication text.
- **Source:** datagoblin.itch.io/monogram
- **Fetched:** 2026-09-28, through the page's free "just take me to the
  downloads" path; nothing was purchased (the page's paid "thank-you gift"
  is not here):
  - `monogram-extended.ttf`, 59,008 bytes,
    sha256 `68648b5c939c4935d8ec7b3a0614c8e7dc3ba23caa11070456a154600e4d2171`
  - `monogram-extended-italic.ttf`, 60,904 bytes,
    sha256 `eb506dd378fc5dbc813cb9fb6bdb2da576fc7b6f53176fd9e5c0b7be73779b1a`

MEASURED BEFORE IT WAS VENDORED, through Zoo's `tools/mint_pixel_type.py`
rules: the page states no pixel grid, so it was measured -- at 16 px, and at
32 as the doubled grid, every glyph is pure on/off with a whole-pixel
advance and nothing kerns, at every other size from 6 to 32 it is not. All
96 characters the factory letters (printable ASCII and ¢) are in both
files' character maps (577 code points each).

WHY THIS ONE: docs/proposals/CC0_FONTS.md, the monospace face with an
italic. The page's plain `monogram.ttf` (10 kB) was not fetched: the extended
face and its italic are the two the walker approved.
