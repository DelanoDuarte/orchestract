# Orchestract — logo assets

## Colour

| Role | Light theme | Dark theme |
|---|---|---|
| Mark | `#1D9E75` | `#35BC90` |
| Wordmark | `#191917` | `#F2F1EC` |

The mark lifts to a brighter teal on dark backgrounds so it holds the same
optical weight. Don't use the light teal on dark — it goes muddy.

## What to use where

| Need | File |
|---|---|
| Anything on the web, docs, README | `svg/orchestract-lockup-adaptive.svg` — switches theme automatically via `prefers-color-scheme` |
| App icon / avatar / GitHub org | `svg/orchestract-mark-adaptive.svg` |
| Inherit the surrounding text colour | `*-mono.svg` — uses `currentColor`, set `color:` on the parent |
| Browser tab | `favicon.ico` (16/32/48 bundled) |
| iOS home screen | `png/tile/apple-touch-icon-180.png` |
| PWA manifest | `png/tile/orchestract-tile-192.png`, `orchestract-tile-512.png` |
| Slides, print, merch | `png/lockup/*-2048w.png`, or the SVG at any size |
| Single-colour print / embroidery | `png/mark/orchestract-mark-black-512.png`, `-white-512.png` |

## Small sizes

`svg/orchestract-mark-small-*.svg` is a separate optical cut for **16–48px**:
thicker stroke, larger dot, tighter radius. The standard mark thins out below
about 48px, so the 16/32/48 PNGs and the favicon are all built from this cut.
Above 48px, always use the standard mark.

## Rules of thumb

- **Clear space:** keep at least the diameter of the dot free on every side.
- **Minimum sizes:** mark 16px, lockup 96px wide. Below that, use the mark alone.
- **Don't** recolour the mark outside the two teals, add a stroke to the wordmark,
  stretch the lockup, or close the ring — the gap is the whole idea.
- The wordmark is set in **Inter Display Medium**, tracking −2%, converted to
  outlines. No font needed to render these files, but Inter (SIL Open Font
  License) is the match if you need to set type alongside it.

## Source

`svg/` is the source of truth. Every PNG is rendered from it — regenerate at any
size rather than upscaling a raster.
