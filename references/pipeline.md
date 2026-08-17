# Pipeline walkthrough (detailed)

Read this when you need more than the SKILL.md summary. It expands each phase
with the practical tricks that make the result faithful.

## 1. Open

- `.ai` is a PDF under the hood **iff** it was saved with "Create PDF Compatible
  File" (Illustrator's default). PyMuPDF opens it directly. If `fitz.open` throws,
  the file is a pure-AI stream — ask the user to re-export PDF-compatible, or to
  send a PDF/SVG.
- Copy to a writable path (`/tmp/work.pdf`); the uploads dir is read-only.

## 2. Read the design (the part only Claude can do)

- Render each page at a readable zoom and actually view it. You cannot classify
  or transcribe what you haven't seen.
- Run `extract_geom.py`. You now have, per line: `x,y,w,h,size,color,raw`.
- **Transcription:** `raw` is reliable for Latin/digits but frequently garbled
  for Arabic (CID-keyed subset fonts reorder/[]-out glyphs). So:
  - Render dense text regions (timelines, fine print) at 2x via a clip pixmap and
    read them carefully.
  - Keep the *geometry* from `geom.json` (it is correct) but type the *words*
    yourself from the render.
  - Watch mixed content: years, ranges like `2018 - 2020`, `100+`, `3.47+`,
    percentages — type them as they appear; bidi will place them correctly.

## 3. Classify + plan

- Walk the page top to bottom. For each block: live text or baked image?
  (See the split in SKILL.md.) When a region is borderline (a heavily styled
  "stat" line vs a real chart), that's a legitimate moment to ask the user.
- **keep ranges** (baked regions): the vertical pt span of each chart/infographic
  you want in the plate. `make_plate.py` keeps any text whose vertical *center*
  falls inside a keep range and strips the rest. Make ranges tight enough not to
  swallow an adjacent live heading (e.g. keep the bubble cluster but not the
  section pill just above it).
- **band cuts:** choose horizontal boundaries so (a) no band exceeds ~16000 px at
  the render zoom, and (b) each chart sits inside a single band (cleaner). Bands
  reconstruct seamlessly because they are exact adjacent slices — any cut works
  visually; these are just two goals, not hard constraints.

## 4. Plate

- `make_plate.py` does redaction with
  `images=PDF_REDACT_IMAGE_NONE, graphics=PDF_REDACT_LINE_ART_NONE,
  text=PDF_REDACT_TEXT_REMOVE` — this removes glyphs while leaving photos,
  vector shapes, gradients, and lines untouched. Baked text (rasterized into an
  image, e.g. a hero title) is part of the image and survives automatically.
- Render zoom 2.0 gives crisp bands; bump to 3.0 only if a baked chart's small
  labels look soft.

## 5. Live-text blocks

- One block per visual line or per flowing paragraph. Pull `top/size/color` from
  `geom.json`; pull the words from your transcription.
- **Block types:**
  - `C`  — a centered line (title, headline, a one-line caption). Centers on the
    canvas; wraps only at full width (so keep these to lines that don't need to
    wrap, or use `CF`).
  - `CF` — a centered paragraph that should wrap; set `colW` to the design column
    width so the wrap points roughly match the design.
  - `CB` — text centered inside a pill/box/circle; set `x0,w` to the shape's box.
  - `R`/`L` — a right/left-aligned block anchored at an edge; set `xR`/`xL` and
    `w`. Use `R` for RTL body columns (anchor the right edge, let it flow left).
- **Line-height:** derive from the gap between the design's consecutive lines
  (gap_pt / size_pt). Typical: headings ~1.2–1.3, body ~1.33–1.5.
- **No forced breaks:** never insert `<br>`. Control wrap with `colW`/`w`. The
  user's real font is usually wider/bolder than the QA stand-in, so wrap points
  shift slightly — that's expected and fine.
- **Fonts:** `display` for headings/numbers-in-callouts/section titles; `body`
  for paragraphs. When in doubt, `body`.

## 6. Scale normalization (multi-page)

- Pages may have different native widths. Each page's `scale = canvas_width /
  page.width_pt`; `build_site.py` applies it to every coordinate and size and to
  the band placement, so all pages render at the same canvas width and stack
  cleanly. Bands tile because `band_height_pt * scale` equals the displayed band
  height at the canvas width.

## 7. QA loop

- The QA is `compare_build.py`: it renders the actual built `index.html` (in a
  real headless browser when available, else an approximate raqm fallback) beside
  the design at the same width, and reports match %, the biggest-difference
  regions, and a strict **live-text integrity** verdict (no missing or invisible
  text). There is no separate preview step.
- Look for: wrong/missing words, blocks too high/low, wrong alignment, RTL order,
  collisions (a paragraph that wrapped to more lines than the design and now
  overlaps the next block — widen `colW`/`w` or nudge `top`). The integrity check
  catches the two silent killers — text that's missing, or coloured the same as
  its background — and with `--fix` repairs them automatically.
- Iterate: edit `blocks` in `project.json`, rerun `build_site.py` +
  `compare_build.py`. Two or three passes is normal.

## 8. Deliver + explain

- `present_files` the self-contained HTML (easy to open) and the zip.
- Tell the user, briefly: live-vs-baked split; add fonts via README; the two-file
  difference; wrapping improves with their font.
