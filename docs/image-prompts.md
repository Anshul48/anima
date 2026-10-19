# WS5 image prompts — style bible + slot prompts (docs only, no generation)

Source of truth for palette/type: `/tmp/r2/ws0/design-tokens.css` (single set;
light default, dark via `prefers-color-scheme`). This file contains PROMPTS ONLY.
No images are generated or committed by WS5. Every rendered image MUST be labeled
"illustrative" in its caption/alt — code (canvases, tables, receipts) carries proof,
images never do.

## 1. Style bible (applies to every entry)

**Palette (hex, from tokens — use these exactly, no substitutes):**

- Light: paper `#f4f6f8`, panel `#ffffff`, ink `#17212b`, muted `#3d4c5c`,
  line `#c3ced8`, accent blue `#0b5cad`, accent2 teal-green `#0a6e4e`,
  warn ink `#7a4a00` on wash `#fdf3e3`, err `#8b0000`, chip `#e8eff6`,
  focus `#b35c00`.
- Dark: paper `#0e1116`, panel `#161b22`, ink `#e6edf3`, muted `#8b949e`,
  line `#2a3139`, accent `#4493f8`, accent2 `#3fb950`, warn ink `#f0c674`
  on `#3a2b00`, err `#f85149`, chip `#1c2b45`, focus `#f0c674`.
- Per-image: pick ONE mode (match the page's `prefers-color-scheme` default the
  slot will render under) and stay inside that mode's column. No gradients, no
  glow, no glass — flat fills + 1px `#line` strokes only.

**Line weight:** 1–2px strokes at export size; 8px corner radius on cards/panels
(`--r-m`), pill radii only for status chips; 4px-base spacing rhythm visually
(generous whitespace, max ~1120px content feel).

**Lighting / finish:** flat vector-diagram lighting, no shadows except a single
soft 2px panel offset at most; matte fills, no metallic/glossy rendering.

**Diagrammatic, NOT photoreal:** clean technical illustration / explainer-diagram
style. Abstract geometric nodes, edges, bars, ledger rows — never photographs of
people, hardware, or places; never photorealistic textures.

**No-text rule:** images contain NO legible words, numbers, or logos. Label-like
marks must be unreadable placeholder ticks/bars (e.g. "short gray bars where
text would be"). All real labels, values, and claims live in HTML next to the
image, never baked into pixels (also keeps i18n/dark-mode honest).

**Negative prompt master (append to every generation):**
`photorealistic, photograph, 3d render, glossy, glowing neon, gradient mesh,
glassmorphism, drop shadows, legible text, words, letters, numbers, logos,
watermarks, people, faces, hands, cluttered, low contrast, blurry`

**Honesty rule:** each slot's caption + alt text MUST include the word
"illustrative". Images decorate; canvases/tables/receipts prove.

## 2. Slot entries (7 — ONLY slots code can't carry)

Code already covers: hero canvases (trace landing/explorer/recording, anima
module replays), proof strips, benchmark tables, receipts, counters. Images are
allowed ONLY in the slots below.

### IP-1 — trace landing hero backdrop (decorative, behind canvas)
- Placement: `docs/index.html` hero section, CSS backdrop behind the membership
  hero canvas (canvas stays the proof layer on top).
- Aspect: wide 21:9, e.g. 1680x720.
- Prompt: `flat technical-diagram backdrop, faint slate grid (#c3ced8 hairlines)
  on paper #f4f6f8, scattered abstract document-node dots in muted slate #3d4c5c
  linked by thin blue #0b5cad hairlines converging toward one teal #0a6e4e hub
  off-center right, generous empty space center-left for overlaid content, matte,
  diagrammatic, no text` + negative master.
- Negative: master only.
- Alt text: `Illustrative diagram backdrop of abstract document nodes converging
  toward a hub; the live canvas above it carries the real data.`

### IP-2 — trace landing OG image
- Placement: `og:image` for trace landing (`docs/index.html`).
- Aspect: 1200x630 (see §3 trace spec).
- Prompt: `flat vector-style social card, paper #f4f6f8 background, left side
  empty breathing room, right side abstract cluster of slate document chips #e8eff6
  with 1px #c3ced8 borders connected by thin blue #0b5cad lines to one teal
  #0a6e4e node, unreadable gray placeholder bars only, no text` + negative master.
- Negative: master + `, text-heavy layout, logo`.
- Alt text: `Illustrative social preview graphic for the trace demo; abstract
  node diagram, no data.`

### IP-3 — trace recording OG image
- Placement: `og:image` for trace recording (`docs/recording/`).
- Aspect: 1200x630 (see §3 trace spec).
- Prompt: `flat vector-style social card, panel white #ffffff on paper #f4f6f8, a
  horizontal 5-frame filmstrip of abstract slate rectangles #eef2f6 with 1px
  #c3ced8 borders and tiny teal #0a6e4e progress ticks, unreadable placeholder
  bars only, no text` + negative master.
- Negative: master + `, video still, faces`.
- Alt text: `Illustrative social preview graphic for the 5-scene demo; abstract
  filmstrip, no measured numbers.`

### IP-4 — anima index OG image
- Placement: `og:image` for anima index (`docs/index.html`).
- Aspect: 1200x630 (see §3 anima spec).
- Prompt: `flat vector-style social card, dark panel #161b22 on dark paper
  #0e1116, five abstract module tiles in a row with 1px #2a3139 borders, small
  blue #4493f8 and green #3fb950 geometric glyphs (circle, tree, nodes, grid,
  shield), unreadable placeholder bars only, no text` + negative master.
- Negative: master + `, light background, logo`.
- Alt text: `Illustrative social preview graphic for the anima docs site; five
  abstract module glyphs, no data.`

### IP-5 — anima sst OG image
- Placement: `og:image` for anima sst (`docs/sst.html`).
- Aspect: 1200x630 (see §3 anima spec).
- Prompt: `flat vector-style social card, dark paper #0e1116, abstract search
  tree branching from left in thin blue #4493f8 lines, most branches ending in
  small muted #8b949e dots, one branch reaching a green #3fb950 node, one branch
  visibly pruned with a red #f85149 tick, unreadable placeholder bars only, no
  text` + negative master.
- Negative: master + `, approved stamp, checkmark badge`.
- Alt text: `Illustrative social preview of an abstract search tree with one kept
  and one pruned branch; the pin receipt on the page carries the real result.`

### IP-6 — section divider, trace pages (reused)
- Placement: divider band between "Try it" and "Limits & honesty" on trace
  landing / explorer / recording.
- Aspect: ultra-wide 21:4 strip, e.g. 1680x320, Croppable left/right.
- Prompt: `flat minimal divider strip, paper #f4f6f8, one 1px horizontal slate
  rule #c3ced8 across the middle with a single small teal #0a6e4e diamond marker
  at center, faint blue #0b5cad hairline accents fading toward edges, matte,
  no text` + negative master.
- Negative: master only.
- Alt text: `Illustrative divider band; decorative only.`

### IP-7 — section divider, anima pages (reused)
- Placement: divider band above "Limits & honesty" on substrate / sst / stc /
  entorhinal / reflex.
- Aspect: ultra-wide 21:4 strip, e.g. 1680x320, croppable left/right.
- Prompt: `flat minimal divider strip, dark paper #0e1116, one 1px horizontal
  rule #2a3139 across the middle with a single small green #3fb950 diamond marker
  at center, faint blue #4493f8 hairline accents fading toward edges, matte,
  no text` + negative master.
- Negative: master only.
- Alt text: `Illustrative divider band; decorative only.`

Slots deliberately WITHOUT images: explorer hero (live query canvas), recording
5-scene demo + terminal player, all proof strips / bench tables / receipts /
counters, anima substrate ledger replay, stc/entorhinal/reflex heroes — code
carries these; no prompt is provided for them.

## 3. OG 1200x630 spec per site

**Trace site** (`docs/index.html`, `docs/recording/`; light-first):
canvas 1200x630px (2x: author at 2400x1260, export at 1200x630). Background
`#f4f6f8`, safe zone central 1000x540 (keep motif clear of ~60px edges for
client crops). No text in pixels — page `<meta property="og:*">` tags carry
title/description. Format: PNG or JPEG q80, ≤300KB, `img {max-width:100%;
height:auto}` + explicit `width`/`height` attributes (CLS fix per tokens file).

**Anima site** (`docs/index.html`, `docs/sst.html`; dark-first):
canvas 1200x630px (2x: author at 2400x1260, export at 1200x630). Background
`#0e1116`, safe zone central 1000x540. No text in pixels — `og:title` /
`og:description` live in meta tags. Format: PNG or JPEG q80, ≤300KB, explicit
`width`/`height` attributes + `height:auto`.
