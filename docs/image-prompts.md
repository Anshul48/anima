# ANIMA image prompts (docs only, no generation)

Status: PROMPTS ONLY. No images were generated or committed by this task.

Palette source: grounded in the shared token set
(`docs/assets/design.css`, identical in trace and anima) — not in older
figure hexes. Light: paper `#f4f6f8`, panel `#ffffff`, ink `#17212b`,
muted `#3d4c5c`, line `#c3ced8`, accent blue `#0b5cad`, accent green
`#0a6e4e`, warn ink `#7a4a00` on warn bg `#fdf3e3`, focus `#b35c00`.
Dark (`prefers-color-scheme`): paper `#0e1116`, panel `#161b22`, ink
`#e6edf3`, muted `#8b949e`, accent `#4493f8`, accent green `#3fb950`,
focus `#f0c674`, error `#f85149`. Radius 6/8/12/999px; type 1.25 ratio
system stack; motion 150/250/400/600ms. Prompts below cite the light
values; dark-mode rendering follows the same tokens via CSS.

Adapted from the WS5 prompt set (7 entries + OG spec): compositions,
aspects, and honesty rules kept; every hex re-grounded to the tokens
above.

## Style bible

Palette (tokens only): `--accent #0b5cad` primary blue, `--accent2
#0a6e4e` green, `--warn-ink #7a4a00` amber text on `--warn-bg #fdf3e3`,
`--muted #3d4c5c` secondary, hairlines `--line #c3ced8`, ink
`--ink #17212b`, backgrounds `--paper #f4f6f8` / `--panel #ffffff`.

Line weight: flat vector strokes, 1–2 px equivalent at 1200 px width,
rounded caps and joins; hairline dividers `--line #c3ced8`.
Corner radius follows tokens: 6/8/12px, pills 999px.

Lighting: even, flat, diagrammatic. Soft ambient only; no directional
photorealistic shading, no lens effects, no depth-of-field. Optional
subtle long shadow at 45° on hero shapes only.

Rendering mode: DIAGRAMMATIC, NOT PHOTOREAL. Flat vector illustration /
technical-diagram aesthetic. No photographs, no 3D renders, no textures,
no gradients except flat tints.

No-text rule: generated imagery MUST NOT contain words, letters, numbers,
captions, watermarks, or logos. All labels are added later as HTML/CSS
overlays by code. Prompts must explicitly forbid text.

Negative prompt master (append to every entry):
`photorealistic, photograph, 3d render, raytraced, text, words, letters,
numbers, caption, watermark, logo, trademark, blurry, noisy, cluttered,
dark moody lighting, lens flare, depth of field`

Honesty rule: every placed image carries `data-honesty="illustrative"` (or
equivalent marker) plus caption/alt text stating it is illustrative, never
a measured result. Never depict chart-like data, axes, or numbers.

Placement policy: image prompts exist ONLY for hero / OG / divider slots
where code and CSS cannot carry the visual weight. All inline explanatory
diagrams remain hand-authored SVG in code.

## Entries

### 1. TRACE hero — `trace`, homepage hero, 16:9

- Placement: trace site homepage hero background/panel.
- Aspect: 16:9 (generate 1600x900, display responsive).
- Prompt: `Flat vector hero illustration, diagrammatic technical style,
paper background #f4f6f8 with white panel #ffffff; abstract retrieval
pipeline motif: three rounded rectangular stages (12px radius) connected
by accent-blue #0b5cad arrows flowing left to right, small geometric
document and node glyphs in accent blue #0b5cad, accent green #0a6e4e
and warn amber #7a4a00 accents, thin 1-2px rounded strokes, even flat
lighting, generous whitespace, no text.`
- Negative: master + `screenshot, user interface, browser window`.
- Alt text: `Illustrative abstract diagram of a three-stage retrieval pipeline.`
- Depiction: illustrative.

### 2. TRACE OG — `trace`, social share, 1200x630

- Placement: `og:image` / Twitter card for trace site pages.
- Aspect: 1200x630 exactly (see OG spec below).
- Prompt: `Flat vector open-graph illustration 1200x630, diagrammatic
style, accent blue #0b5cad left motif of stacked document glyphs and
connecting nodes, flowing into warn-amber #7a4a00 highlight shape at
right third; paper background #f4f6f8, large empty central safe zone
free of detail for title overlay, 1-2px rounded strokes, flat even
lighting, no text.`
- Negative: master.
- Alt text: `Illustrative TRACE share image: abstract document and node motif.`
- Depiction: illustrative.

### 3. ANIMA hero — `anima`, landing hero, 16:9

- Placement: anima umbrella landing hero panel.
- Aspect: 16:9 (generate 1600x900, display responsive).
- Prompt: `Flat vector hero illustration, diagrammatic style, white
panel background #ffffff; concentric holonic motif: nested rounded
rings in accent blue #0b5cad enclosing small world-glyphs (hexagon,
circle, leaf shapes) tinted warn bg #fdf3e3, paper #f4f6f8 with accent
green #0a6e4e and warn amber #7a4a00 accents, hairline #c3ced8 orbit
strokes, calm symmetric composition, generous whitespace, flat even
lighting, no text.`
- Negative: master + `galaxy photo, nebula, space photo`.
- Alt text: `Illustrative abstract image of nested worlds within worlds.`
- Depiction: illustrative.

### 4. ANIMA OG — `anima`, social share, 1200x630

- Placement: `og:image` / Twitter card for anima site pages.
- Aspect: 1200x630 exactly (see OG spec below).
- Prompt: `Flat vector open-graph illustration 1200x630, diagrammatic
style, nested-ring holonic motif in accent blue #0b5cad at left, small
tinted world-glyphs in warn bg #fdf3e3 and paper #f4f6f8; background
#ffffff; large empty central safe zone free of detail for title overlay,
1-2px rounded strokes, flat even lighting, no text.`
- Negative: master.
- Alt text: `Illustrative ANIMA share image: abstract nested-rings motif.`
- Depiction: illustrative.

### 5. Divider — architecture sections, 21:5 panorama

- Placement: full-bleed section divider above architecture content (both sites).
- Aspect: 21:5 (generate 2100x500, crop-safe).
- Prompt: `Ultra-wide flat vector divider strip, diagrammatic style,
hairline #c3ced8 baseline running full width with five small geometric
module glyphs (square, hexagon, circle, diamond, triangle) in accent
blue #0b5cad, accent green #0a6e4e, warn amber #7a4a00 spaced evenly,
paper background #f4f6f8 fading to white #ffffff at edges, 1px strokes,
flat, no text.`
- Negative: master.
- Alt text: `Illustrative divider: small geometric module glyphs on a line.`
- Depiction: illustrative.

### 6. Divider — evaluation/benchmark sections, 21:5 panorama

- Placement: full-bleed section divider above evaluation content (both sites).
- Aspect: 21:5 (generate 2100x500, crop-safe).
- Prompt: `Ultra-wide flat vector divider strip, diagrammatic style, row of
abstract vertical bar glyphs of varying heights WITHOUT axes or numbers
in warn amber #7a4a00, accent blue #0b5cad, accent green #0a6e4e on white
#ffffff, hairline #c3ced8 baseline, 1-2px rounded strokes, flat even
lighting, purely decorative, no text, no numbers.`
- Negative: master + `axes, axis labels, tick marks, gridlines, numbers,
chart, graph paper`.
- Alt text: `Illustrative divider: decorative abstract bars, not real data.`
- Depiction: illustrative (explicitly not measured results).

### 7. Divider — reproducibility/provenance sections, 21:5 panorama

- Placement: full-bleed section divider above reproducibility content.
- Aspect: 21:5 (generate 2100x500, crop-safe).
- Prompt: `Ultra-wide flat vector divider strip, diagrammatic style, chain
of linked rounded-rectangle capsule glyphs (999px pill radius) connected
by accent-blue #0b5cad links on paper background #f4f6f8, one capsule
highlighted warn bg #fdf3e3, hairline #c3ced8 separators, 1-2px rounded
strokes, flat, no text.`
- Negative: master.
- Alt text: `Illustrative divider: abstract linked-capsule provenance chain.`
- Depiction: illustrative.

## OG 1200x630 spec (per site)

Common: exactly 1200x630 px; key motif inside central 1000x500 safe zone;
title overlay applied by site template (never baked in); export PNG or JPG
quality 85, target < 300 KB (hard cap 1 MB); file names
`og-trace-1200x630.png`, `og-anima-1200x630.png`.

- trace: dominant accent blue `#0b5cad` on `#f4f6f8`; warn amber `#7a4a00`
  reserved for single right-third highlight; overlay title in ink `#17212b`.
- anima: dominant accent blue `#0b5cad` rings + tints `#fdf3e3` / `#f4f6f8`
  on `#ffffff`; overlay title in ink `#17212b`.

Validation: `identify -format "%wx%h"` must print `1200x630`; grep exports
for embedded text layers (none allowed); confirm alt text + illustrative
caption present on every page using the image.
