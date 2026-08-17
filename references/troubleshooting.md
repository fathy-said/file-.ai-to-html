# Troubleshooting & gotchas

Symptoms -> causes -> fixes. These are the real failure modes hit while building
this pipeline; check here before re-deriving anything.

## Images don't show when the user opens the file
- **Cause A:** they opened `index.html` without the `images/` folder beside it.
  -> Use / send `index_self_contained.html` (images embedded), or keep `images/`
  in the same folder as `index.html`.
- **Cause B:** images were WebP and their viewer/client doesn't support WebP.
  -> Always export **JPEG**. (`jpeg_quality` ~88–92.)

## Arabic text renders left-to-right / disconnected / wrong order
- Ensure `dir="rtl"` on BOTH `<html>` and `<body>`, `direction:rtl` in CSS, and
  `.tx{direction:rtl;unicode-bidi:plaintext;}`.
- Add Arabic-capable fallback fonts in the stack (Segoe UI, Tahoma, Geeza Pro,
  Noto Sans Arabic) so it's correct even before the real font loads.
- Don't judge RTL from a half-loaded page (missing images can make absolute
  blocks pile up and *look* broken). Re-test with the self-contained file.

## Arabic won't wrap in my rendered check (but looks fine in a browser)
- You used **wkhtmltoimage**. Its bundled WebKit does not line-break Arabic at
  spaces — it only breaks Latin. Its wrapping is meaningless for Arabic.
- Use `compare_build.py` for QA: it renders the built `index.html` in a real
  headless browser when one is available (correct Arabic shaping and wrapping), and
  falls back to PIL + raqm otherwise. Never use wkhtmltoimage for Arabic wrap QA.

## A band image is blank / refuses to render
- The band is taller than the GPU's max texture (~16384 px). `make_plate.py`
  warns when a band exceeds 16000 px. -> Split that band into smaller ranges in
  `project.json -> pages[].bands`.

## The whole design isn't centered on a narrow window
- `margin:0 auto` does not center an element wider than its container, so when
  the viewport < canvas width the scaled content drifts.
- Fix in the harness (already applied): `#scaler{display:flex;justify-content:center}`
  plus `#canvas{transform-origin:top center}`.

## Seams / thin gaps between bands
- Bands must be **exact adjacent pixel slices** of one render, each placed at
  `top = band_y0_pt * scale`, width = canvas width, height auto. If you change a
  band's y-range, change the next band's start to match. Don't round inconsistently.

## Live text overlaps the next block after editing
- The paragraph wrapped to more lines than the design (font width differs, or
  `colW`/`w` too small). Widen the column or nudge the next block's `top`. This is
  normal during the QA loop.

## Baked chart labels look soft
- Bump `render_zoom` (2.0 -> 3.0) so small baked text is sharper. Costs file size.

## Numbers/symbols inside Arabic look wrong (e.g. "+100", "(2020 - 2018)")
- With `unicode-bidi:plaintext` the bidi algorithm orders mixed runs correctly.
  Type the text in logical order as you read it in the design ("100+",
  "2018 - 2020"); don't pre-reverse it.

## The .ai file won't open with PyMuPDF
- It wasn't saved "PDF Compatible". Ask the user to re-export from Illustrator
  with that option on, or to provide a PDF/SVG.

## extract_geom's `raw` text is gibberish
- Expected for Arabic / subset fonts. The geometry is still correct. Read the
  actual words from a rendered image and type them into the blocks yourself.

## `/ai-to-html test` says "APPROXIMATE raqm render (no Chromium found)"
- The comparison couldn't find a headless Chromium, so it fell back to an
  approximate render (text uses a stand-in/fallback font, so the exact % is lower
  than reality).
- Fix: run `test` in an environment that has Chrome/Chromium. The script looks in
  the puppeteer cache (`~/.cache/puppeteer/...`), the playwright cache, `PATH`,
  and the usual macOS app locations; you can also point it explicitly by setting
  `PUPPETEER_EXECUTABLE_PATH=/path/to/chrome` before running. With a real browser
  the match % is meaningful.

## Several apps / .ai files, but only one got built (or they got mixed together)
- **Cause:** treating the run as a single fixed input/output (one `/tmp/build`,
  one `project.json`) instead of one project PER `.ai`.
- **Fix:** each `.ai` is its own project. Discover them all; process ONE AT A
  TIME with a fresh `/tmp/<slug>/` scratch and a separate `project.json`; set each
  project's `out_dir` to a `build/` folder **right next to that `.ai`**
  (`<ai_folder>/build`). Never reuse `out_dir`, `work.pdf`, or `project.json`
  across apps, and start each app from a clean state so images/blocks from a
  previous app can't leak in. Present each app's deliverables separately.

## Fonts: it looks plain / falls back
- The deliverable ships with **placeholder** font names/paths on purpose (we
  never guess the brand font). Until the user drops their files in `fonts/` and
  edits the `@font-face` + `:root` vars, the system fallback shows — that's
  expected. Say so in the hand-over note.

## A heading stays baked in the image and won't become live text
- **Cause:** in the source it isn't real text. These .ai exports often render an
  Arabic heading as a **row of per-letter raster images** (sometimes with a
  garbled live-text span over it), or the text was outlined / flattened into a
  photo. `make_plate` removes only real text, so the baked pixels survive.
- **Fix:** you can't strip it — leave it baked. Capture it for the design team:
  `make_handoff.py` auto-detects the per-letter-image headings and writes
  `design_handoff.md` (with a crop + page + coordinates of each). For baked text
  it can't see (inside a photo or chart), add `{page,bbox,text,note}` entries to a
  `handoff` array in project.json and re-run. The real source fix is to keep that
  text as a live text layer (and embed the Arabic font with a ToUnicode map).

## `test` reports Live-text integrity: FAIL
- **Meaning:** the build is shipping text that the design has but the user won't
  see — either **missing** (a block was never added, or got stripped with no
  replacement) or **invisible** (its colour matches its background, e.g. white on
  a light pill). The match % can still look high while this is broken, which is
  why it's a separate strict gate.
- **Auto-repair:** run with `--fix` (this is what a build and `/ai-to-html test
  fix` do). It recolours invisible text to the design's own colour (read from the
  source PDF), adds a live placeholder block «صحّح هذا النص» at the source's exact
  position/size/colour for missing text, then rebuilds and re-checks up to 3 rounds
  until `PASS`. The **Auto-fixes applied** report section lists what changed, and
  placeholders are logged in `design_handoff.md` to replace with the real wording.
- **Plain `test`** only measures; fix by hand if you prefer: add the missing block
  (or a `keep` range if it's meant to stay baked), or change the block colour, then
  re-run. The verdict must read `PASS` (0 issues) before the build is done.
- **Note on modes:** the check is most precise with a real browser render (text
  wraps like the design). In the no-browser approximate fallback, a wrapped line
  can occasionally be flagged because the stand-in font wraps differently — open
  the crop to confirm before acting; genuine "whole block missing" and all
  contrast problems are caught in either mode.
