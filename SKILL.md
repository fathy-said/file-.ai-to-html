---
name: ai-to-html
metadata:
  version: 2.1.0
description: >-
  Converts a designed Adobe Illustrator (.ai) file or a design PDF into ONE
  faithful, responsive, single-file HTML reproduction (all pages stacked;
  imagery baked as a pixel-perfect background plate; prose re-created as live,
  font-swappable HTML text; full RTL / Arabic support), and verifies the result
  against the source pixel-for-pixel. Use this skill when the user uploads or
  references a .ai file or a design PDF and wants it turned into HTML, a
  webpage, or a live report; when an existing HTML build must be matched to an
  Illustrator/PDF source ("X-ray", pixel-match, "why doesn't this match the
  design", alignment/spacing drift against a design file); or when the user
  asks for it by name. Do NOT use it for general web development, for building
  a page from a written brief or a screenshot alone, or for redesigning
  something when no .ai/PDF source of truth exists.
---

# ai-to-html

> Illustrator is the source of truth. Never redesign during a fidelity task.
> Measure → render → compare → diagnose → minimally fix → verify again.

Turn a designed `.ai` / PDF into one responsive HTML file that looks like the
design but whose text is real, selectable, font-swappable HTML.

## Modes

- **Build (default).** The full pipeline below: read the design, build the
  background plate + live text, deliver `build/`, and then **automatically run the
  comparison once with `--fix`** to produce `design_vs_build/version_1`. On build,
  live-text integrity problems (missing or invisible text) are **repaired
  automatically** (see step 7); all other differences are proposed, not auto-fixed.
- **`test` (compare an existing build to the design — measure only).** If the user
  invokes the skill as `/ai-to-html test` — the word `test`, with NO other
  instruction — do NOT rebuild and do NOT auto-fix. For each app that already has a
  `build/`, compare the built output against its original `.ai` and write a
  versioned report (this is a pure measurement; surface any issues as a proposed
  fix plan):
  ```bash
  python3 SKILL/scripts/compare_build.py <app>/build SKILL
  ```
- **`test fix` (compare and auto-repair live text).** If the user invokes
  `/ai-to-html test fix`, run the same comparison but **with `--fix`**, so the
  live-text integrity repairs (recolour invisible text to the design's colour; add
  a placeholder block for missing text), rebuild, and re-check happen
  automatically — exactly like a build does:
  ```bash
  python3 SKILL/scripts/compare_build.py <app>/build SKILL --fix
  ```
  In both `test` forms, `build_site.py` saved the layout config at
  `build/.aitohtml_project.json`, so
  the script reads that and compares **the real browser render of the built
  `index.html`** (primary: it auto-finds a headless Chromium — puppeteer cache,
  playwright cache, PATH, or macOS app paths — so Arabic shaping, wrapping, and
  the installed fonts are exactly as a browser shows them) against the original
  `.ai`, per page. If no Chromium is found it falls back to an approximate raqm
  render, and the report opens with a clear **banner** (the comparison is
  approximate, a better browser-based method exists, and a ready-to-paste,
  cross-platform **setup prompt** any team member can give to Claude in their
  terminal to enable it). Output goes into **`build/design_vs_build/version_N/`**
  (auto-incrementing `version_1`, `version_2`, … each time `test` is run):
  - `compare_p{i}.jpg` — design (left) | build (right)
  - `diff_p{i}.jpg` — difference heatmap
  - `report.md` — opens with a **Live-text integrity** verdict (see below), then
    per-page + overall **match %** (two numbers: layout/imagery vs exact pixel),
    the biggest-difference regions, and an **Analysis & fixes** section.

  **Live-text integrity (STRICT — must be 100%).** Every run also checks that the
  live text actually came out, because two failure modes are easy to ship and
  invisible in the match %:
  1. **Missing text** — a block was never added (or got stripped without a
     replacement), so text in the design is simply gone from the build. Detected
     by checking every real source-text position against the live blocks, `keep`
     ranges, baked letter-image headings, and `handoff` items; anything left over
     is confirmed by comparing the design vs the build render (flagged only where
     the build is genuinely blank, so **baked** text is never falsely flagged).
  2. **Invisible / same-as-background colour** — e.g. white text on a light pill.
     Detected by sampling the real background behind each block (the page with all
     text removed) and computing the WCAG contrast against the block's colour;
     anything below `min_contrast` (default **3.0:1**, tunable per project) is
     flagged with both colours and the measured ratio.

  The report's integrity section lists each problem (text, page, position, and a
  crop for missing text). **This must reach 0 issues** — a build is not done, and
  `test` does not pass, until the verdict is `PASS`. Fix flagged blocks (add the
  missing block / a `keep` range, or change the colour to contrast) and re-run.
  After the script runs, OPEN each `compare_p*.jpg` and `diff_p*.jpg` and FILL IN
  the "Analysis & fixes" section of `report.md`: for every real discrepancy
  (ignore ones that are just the stand-in font), write what differs, the cause,
  and the concrete fix. Then `present_files` the new `version_N` folder, and
  follow **"After a comparison: propose a fix plan, then fix on approval"** below.
  - If an app has no `build/` yet, tell the user to build it first.
  - With a real browser the match % is meaningful. Areas that still differ are
    usually missing fonts (install them in `build/fonts/` and run `test` again) or
    a genuine layout slip to fix. The report states which render method was used.



A designed page is split into two layers:

1. **Background plate (images).** Render the PDF with the *live* text removed but
   ALL imagery, gradients, shapes, empty pills/bubbles, timeline lines, emblems,
   and any *baked* regions kept. Slice into horizontal bands. This guarantees the
   visuals are pixel-perfect.
2. **Live HTML text (overlay).** Re-create the prose/headings as absolutely
   positioned HTML at the exact PDF coordinates, in the brand's font (left as
   clear placeholders the user swaps in). This is what becomes selectable and
   re-styleable.

Everything sits on a fixed-width canvas that scales as ONE uniform piece (a
zoom) to fit the screen, capped at a max width, always centered. No reflow.

## Defaults (run autonomously; ask ONLY when genuinely ambiguous)

Proceed with these unless the design clearly contradicts them; only stop to ask
the user when a real judgement call is unclear (e.g. a region that could be
either a chart or a styled text block, or missing/illegible text):

- **Canvas width** = the widest page's point-width (commonly 1080-1200). All
  other pages are scaled to it.
- **--max-width** = 1500 px.
- **Fonts** = placeholders `PROJECT_DISPLAY` (headings) + `PROJECT_BODY` (body),
  pointing to `fonts/DISPLAY.*` / `fonts/BODY.*`. Never guess the real font.
- **Output** = both `index.html` (external `images/`) and
  `index_self_contained.html` (base64), plus a zip + English README.
- **Image format** = **WebP** for all production rasters (`webp_quality` 90).
  QA artifacts (`compare_p*`, `diff_p*`) and handoff crops stay JPEG/PNG.
- **Live vs baked** = follow the split below.

## The core split: live text vs baked image

Decide per element/region:

- **Image that has text baked into it** (a hero with the title rendered into the
  artwork, a photo with an overlaid caption) -> keep the WHOLE thing as an image.
- **Clean prose & headings** (titles, intros, body copy, section headers,
  timeline titles + descriptions, captions on a clean background) -> **live HTML
  text** in the brand font.
- **Charts** (bubble / bar / pie / line), **dense number-infographics**, and
  **compact icon + number + short-label callouts** (stat boxes like "100+",
  circular portfolio figures) -> **bake as images**. Their internal layout is
  fiddly and the font barely matters for digits; baking keeps them perfect.

When unsure, prefer live text for anything that is mostly words, and baked image
for anything that is mostly a diagram/number with icons.

**Some headings come through as baked text, not live text.** `make_plate` removes
only real text. Text that was *outlined* (vectorised), flattened into a photo, or
— common in these Arabic exports — rendered as a **row of per-letter raster
images** (often alongside a garbled live-text span) survives stripping and stays
baked. Such text can't be edited or font-swapped. Leave it baked, and capture it
for the design team with `make_handoff.py` (step 7), which auto-detects the
per-letter-image headings and writes `design_handoff.md`. For baked text the
detector can't see (text inside a photo or chart), add it manually via the
`handoff` array (schema below). Quick manual check: render a region before and
after a full strip — anything that survives is baked.

## Workflow

Each `.ai` is an INDEPENDENT project. Keep scratch per-project under
`/tmp/<slug>/` and write that app's deliverables to its OWN `build/` folder.
Never share a `project.json`, a `work.pdf`, or an `out_dir` across apps. The
scripts live in this skill's `scripts/`. Drive them with one `project.json` per
project that you assemble after reading that design.

**1. Find the input(s) & set per-project output (CRITICAL for multi-app trees).**
   The `.ai` may be a file/folder the user points to, the current working
   directory, an upload, or — commonly — several sibling "app" folders that each
   contain their own `.ai` (e.g. `app_1/part.ai`, `app_2/Part 05.ai`,
   `app_3/Part 08.ai`). Look where the user indicated; if unspecified, search the
   working tree (and `/mnt/user-data/uploads`) for `*.ai` (then `*.pdf`),
   regardless of filename.
   - **If you find more than one `.ai`, treat each as a SEPARATE project. Do NOT
     merge them and do NOT put them all in one place.** List what you found, then
     process them ONE AT A TIME, fully isolated.
   - For each `.ai`, put its output in a `build/` folder **right next to that
     `.ai`** (`<that_ai's_folder>/build/`). To avoid collisions, copy that file to
     `/tmp/<slug>/work.pdf` and write `/tmp/<slug>/project.json`, but set
     `out_dir` to `<that_ai's_folder>/build`. Start each app from a clean state —
     never carry images/blocks/config over from a previous app.
   - Open with PyMuPDF. A `.ai` opens only if saved "PDF Compatible" (almost all
     are); if it won't open, tell the user to re-export it PDF-compatible.

**2. Read the design.** Render each page to a high-res image and LOOK at it to
   understand layout and content. Then (per project):
   ```bash
   python3 SKILL/scripts/extract_geom.py /tmp/<slug>/work.pdf /tmp/<slug>/geom.json
   ```
   `geom.json` has every page's dims, image rects, and per-line text boxes
   (x,y,w,h,size,color). **The `raw` text is often garbled for Arabic / subset
   fonts -- treat geometry as truth and RE-READ the actual words from the
   rendered images** (render dense areas at 2x and transcribe carefully).

**3. Plan (and confirm only if ambiguous).** Classify every element with the
   split above. Pick canvas width / max-width / fonts (defaults). For pages with
   charts/infographics, record their **keep** ranges (vertical pt ranges to bake
   in). You do **not** pick band boundaries — `make_plate.py` slices the page
   automatically, cutting only through rows that are a single flat colour across
   the full width (so seams are invisible) and never letting a band exceed the GPU
   limit. It writes the chosen ranges back into `project.json`. Leave `"bands": []`
   (or omit it). Only set `"manual_bands": true` on a page if you must override the
   auto-slicer with your own `bands`.

**4. Build the plate.** Write `/tmp/<slug>/project.json` (schema below; its
   `out_dir` points at that app's `build/` folder) and run:
   ```bash
   python3 SKILL/scripts/make_plate.py /tmp/<slug>/project.json
   ```
   This strips live text, keeps imagery + keep-regions, renders at 2x,
   auto-slices the page into safe seamless bands, and writes them to
   `<out_dir>/images/p{page}_band{i}.webp` (the chosen ranges are saved back into
   `project.json`, so the next step places them at matching offsets).

**5. Define live-text blocks.** Add a `blocks` array to that app's
   `/tmp/<slug>/project.json`: one entry per heading/paragraph/line with its exact
   native-pt position, size, color, font (`display`/`body`), and alignment type.
   Use FLOWING blocks (`CF`/`R`) for multi-line prose so it wraps naturally in the
   user's font; use per-line placement (`C`/`CB`) for titles, years, pills, and
   number/label callouts. Do NOT force `<br>` line breaks -- control wrapping via
   column width.
   Also add an optional `handoff` array for any baked text the auto-detector
   can't see (text flattened into a photo, labels inside a chart) so it reaches
   the design hand-off in step 7 — see the schema below.

**6. Assemble.** Build the site (per project):
   ```bash
   python3 SKILL/scripts/build_site.py /tmp/<slug>/project.json SKILL
   ```
   `build_site.py` only assembles `index.html` (+ self-contained, README, zip)
   from the config and the already-sliced plate bands — it does not re-slice the
   plate, so it is cheap to re-run after any block tweak. There is no separate
   preview step: the real QA is `compare_build.py` in step 7, which renders the
   actual built `index.html` (in a real browser when available) against the design
   — far more faithful than a stand-in-font preview ever was. The tuning loop is
   **build → `compare_build.py` → read the report → adjust blocks → rebuild**, and
   the `design_vs_build/version_N` reports are your record of that progress.

**7. Deliver + auto-compare + hand-off (per app).** After `build_site.py` wrote
   that app's `build/` (index.html, self-contained, README, zip), immediately run
   the comparison ONCE, automatically — with `--fix`, so any live-text problems are
   repaired before you ever see the report — producing `version_1`, and generate
   the design hand-off:
   ```bash
   python3 SKILL/scripts/compare_build.py <app>/build SKILL --fix
   python3 SKILL/scripts/make_handoff.py <app>/build
   ```
   **What `--fix` does automatically (live-text integrity only):** if the strict
   check finds text that is **invisible** (its colour ≈ its background) it recolours
   that block to **the design's own colour** at that spot (read from the source
   PDF; only if that still wouldn't read does it fall back to plain dark/light). If
   it finds **missing** text (in the design, blank in the build) it adds a **live
   placeholder block** «صحّح هذا النص» at the source's exact position, size, and
   colour, and logs it in `design_handoff.md`. Then it rebuilds and re-checks, up
   to 3 rounds, until the verdict is `PASS`. The report's **Auto-fixes applied**
   section lists everything it changed.

   `make_handoff.py` writes `build/design_handoff.md` (+ crops in
   `build/handoff_images/`): the baked text that should be live, plus any
   auto-added placeholders to replace with the real wording. It auto-detects
   per-letter-image headings; fill in each item's **Text** by reading its crop, and
   add any baked-in-photo / chart text via the `handoff` array, then re-run it.
   Then OPEN that app's `build/design_vs_build/version_1/compare_p*.jpg` and
   `diff_p*.jpg` and FILL IN the report's "Analysis & fixes" section (real
   discrepancies, causes, fixes; mark font-only differences as expected).

   **Gate — the Live-text integrity verdict MUST read `PASS`.** With `--fix` it
   normally already does; if it still says `FAIL` (e.g. 3 rounds weren't enough),
   finish the remaining items by hand and re-run. This is separate from, and not
   excused by, a high match %.

   For **all OTHER discrepancies** (font, spacing, layout, imagery — anything that
   is not the live-text integrity check) do NOT auto-fix: follow **"After a
   comparison: propose a fix plan, then fix on approval"** below — surface a plan
   first. Only the live-text integrity repairs above are automatic. If there are
   more apps, go back to step 1 with a fresh `/tmp/<slug>/`.

**8. Hand-over note + present.** When all apps are done, `present_files` each
   app's self-contained HTML + zip + its `design_vs_build/version_1` report + its
   `design_handoff.md` (clearly labelled per app, so nothing is mixed up). Briefly
   tell the user: that each app got its own `build/` beside its `.ai`; that an
   automatic design-vs-build comparison report is in
   `build/design_vs_build/version_1/`; that `design_handoff.md` lists the baked
   text that should be made live in the source; which parts are live text (their
   font) vs baked images; that they add their font via the README; the two-file
   difference; and that wrapping fits better once their real (usually
   wider/bolder) font is in. Note they can re-run `/ai-to-html test` anytime for a
   fresh `version_`.

## After a comparison: propose a fix plan, then fix on approval

This runs after EVERY comparison — the automatic one at the end of a build (step
7) and every explicit `/ai-to-html test`. Once the report and diff images exist:

**Exception — live-text integrity is auto-fixed, not proposed.** On a build and on
`/ai-to-html test fix`, `compare_build.py` runs with `--fix` and has already
repaired any missing/invisible live text (recolour to the design's colour; add a
«صحّح هذا النص» placeholder). Those repairs are reported under **Auto-fixes
applied** — just tell the user what was auto-fixed (and that placeholders need
their real wording from `design_handoff.md`); do NOT re-propose them. The plan
below is for **everything else** (and, under plain `/ai-to-html test`, which does
not auto-fix, also for any remaining live-text-integrity items).

1. **Triage what the comparison found.** Open `compare_p*.jpg` + `diff_p*.jpg` and
   sort each difference into:
   - **Real issue (fixable):** a block too high/low/narrow, missing or mistyped or
     mis-wrapped text, wrong colour, a chart that should be live text (or vice
     versa), a band/keep-range that cut something, a wrong position.
   - **Expected / not a defect:** differences that are only the stand-in or
     fallback font (glyph shapes/widths) when the user's real font isn't installed
     yet, or sub-pixel noise. **Do NOT propose "fixes" for these** — name them once
     as expected and move on.

2. **If there are NO real issues:** tell the user the build matches the design
   (note any expected font-only differences and that installing their font closes
   them). No plan needed. Stop here.

3. **If there ARE real issues: present a PLAN and WAIT — do not change anything
   yet.** The plan is a short numbered list; each item =
   `the problem (page + where) → the concrete fix (which block/coord/keep-range/
   colour) → rough effort`. Keep it skimmable. Ask the user to approve all, pick a
   subset, or skip.

4. **On approval, fix only what they approved:** edit that app's `project.json`
   (blocks / keep-ranges / colours / sizes), rebuild what changed
   (`make_plate.py` only if keep-ranges changed, then `build_site.py`), then
   **re-run `compare_build.py`** to produce a fresh `version_N` and confirm the
   issues are gone and the match improved. Tell the user the before→after match %
   and which items are resolved. If something still differs, offer another pass.

5. **Never auto-apply fixes without that approval**, and never touch issues the
   user chose to skip.

## After delivery: ask for problems, then fix or capture them

Treat every run as a chance to improve. AFTER you have presented the
deliverables, ask the user two short, easy-to-answer questions (one message):

1. "Did anything come out wrong in the result — a position off, wrong/missing
   text, something that should've been live text instead of an image (or vice
   versa), fonts, colours, spacing?"
2. "Anything about *how* I worked that I should do differently next time?"

Sort the answer into one of two buckets:

- **One-off fix (specific to THIS design).** e.g. "the 2019 title sits too low",
  "you missed a line of the intro". -> Just fix it: adjust this project's
  `project.json` / blocks / keep-ranges, rebuild, re-deliver. Do NOT change the
  skill for a one-off.

- **Reusable lesson (would help on OTHER designs too).** e.g. "right-aligned
  blocks land ~8px too high", "always treat circular % badges as images", "ask
  before splitting a two-line title". -> Capture it into the skill so it sticks:
  1. Draft the exact change — usually a new symptom->fix entry in
     `references/troubleshooting.md`, or a tightened rule/default in `SKILL.md`.
  2. Show the user the proposed wording and confirm it's a general rule worth
     keeping. **Never rewrite the skill silently.**
  3. On confirmation, persist it. The INSTALLED copy of a skill is usually
     READ-ONLY, so you generally cannot edit it in place. Instead: copy the skill
     folder to a writable path (e.g. `/tmp/ai-to-html/`), apply the edit there,
     re-package it (use skill-creator's `package_skill.py` if available, else just
     zip the folder as `ai-to-html.skill` — a `.skill` is a zip), and hand the
     user the updated `.skill` to re-install. If the skill folder is writable in
     this environment, edit it in place instead.
  4. Tell the user in one line what changed.

Keep captured lessons small and in the right place: symptom->fix goes in
troubleshooting; only change `SKILL.md` when a real default/rule should change.
Never persist a lesson without the user's OK.

## project.json contract

```json
{
  "source_pdf": "/tmp/app_3/work.pdf",
  "out_dir": "app_3/build",
  "canvas_width": 1200,
  "max_width": 1500,
  "bg": "#0a2e2b",
  "lang": "ar", "dir": "rtl",
  "title": "...", "seo_h1": "...",
  "fonts": {"display_file":"fonts/DISPLAY.woff2","display_fmt":"woff2",
            "body_file":"fonts/BODY.woff2","body_fmt":"woff2"},
  "fallback": "\"Segoe UI\", Tahoma, \"Geeza Pro\", \"Noto Sans Arabic\", Arial, sans-serif",
  "render_zoom": 2.0, "webp_quality": 90,
  "band_format": "webp",          // "jpg" only for viewers without WebP support
  "cut_pad": 16,                  // >= WebP macroblock; do not lower
  "min_contrast": 3.0,
  "zip_name": "site.zip",
  "pages": [
    {"index":0, "width_pt":1200, "height_pt":3452.83,
     "bands":[], "keep":[]},
    {"index":1, "width_pt":1100, "height_pt":8772.95,
     "bands":[],
     "keep":[[4900,5300],[5985,6855],[7560,8160],[8330,8773]]}
  ],
  "blocks":[
    {"page":0,"type":"C","text":"...","top":1682,"size":48,"color":"#fdf6e9","font":"body"},
    {"page":1,"type":"CF","text":"...","top":515,"size":38,"color":"#fff","font":"body","colW":905,"lh":1.45},
    {"page":1,"type":"R","text":"...","top":3196,"size":30,"color":"#fff","font":"body","xR":797,"w":672,"lh":1.33},
    {"page":1,"type":"CB","text":"1971","top":3135,"size":54,"color":"#03cc99","font":"display","x0":800.8,"w":200.6}
  ],
  "handoff":[
    {"page":1,"bbox":[200,400,900,520],"text":"...","note":"flattened into hero image"}
  ]
}
```

Block `type`: `C` centered line · `CF` centered flowing (needs `colW`) · `CB`
centered-in-box (needs `x0,w`) · `R` right block (needs `xR,w`) · `L` left block
(needs `xL,w`). All pt values are per the page's native size and are scaled to
the canvas automatically. See `scripts/build_site.py` header for the full schema.

`handoff` (optional) lists baked text the auto-detector can't find on its own
(text flattened into a photo, labels inside a chart) so `make_handoff.py` still
includes it in `design_handoff.md`. Each entry: `{page, bbox:[x0,y0,x1,y1], text,
note}` (bbox in native pt; `text`/`note` optional). Per-letter-image headings are
detected automatically and do **not** need an entry here.

`min_contrast` (optional, default `3.0`) is the WCAG contrast threshold for the
strict live-text integrity check; a live block whose colour falls below it against
its background is flagged as invisible. Lower it only if a design intentionally
uses subtler-but-legible text.

## X-ray matching discipline

When an existing HTML build must match Illustrator, **fix the existing code; do not rebuild or redesign it**. Illustrator wins every disagreement.

- Convert Illustrator coordinates to page-relative coordinates before comparing.
- Prefer `GetGeometry` transformation matrices over screenshot eyeballing.
- Measure a small set of layout landmarks (title Y, major section starts, chart/image centers, closing element) with browser `getBoundingClientRect()` at the same design scale.
- Record source coordinate, HTML coordinate, delta, responsible element, and likely upstream cause.
- Use overlay/diff images when numeric measurements do not explain a mismatch.
- Iterate render → measure → fix → render until landmarks converge.
- Do not treat a temporarily worse aggregate score as a regression if an upstream error was previously cancelling a downstream error.
- Never revert user edits encountered during the loop; treat them as authoritative.

## Section scrolling / presentation behavior

When the design is explicitly composed of full-screen sections (`100vh`) and the user wants one smooth section per scroll, use CSS scroll snapping rather than redesigning the sections:

```css
.report {
  height: 100vh;
  overflow-y: auto;
  scroll-snap-type: y mandatory;
  scroll-behavior: smooth;
}
.report-section {
  min-height: 100vh;
  scroll-snap-align: start;
  scroll-snap-stop: always;
}
```

Do not force this behavior when the source design is a continuous scrolling report or when a section can legitimately exceed the viewport.

## Critical rules (do not relearn the hard way)

- **Arabic/RTL wrap QA uses PIL+raqm, never wkhtmltoimage** — the old WebKit does
  not break Arabic at spaces, so its wrapping is meaningless for Arabic.
- **Live-text integrity must read `PASS`** — `compare_build.py` strictly checks
  that no live text is missing and none is invisible (colour ≈ its background); a
  high match % does NOT cover this. On a build (and on `test fix`) it runs with
  `--fix` and **repairs these automatically** (recolour to the design's own colour;
  add a «صحّح هذا النص» placeholder block for missing text), then rebuilds and
  re-checks until the verdict is `PASS`. Plain `test` only measures. This is the
  one class of issue that is auto-fixed; everything else is proposed first.
- **WebP production assets are the default.** QA artifacts and handoff crops stay
  JPEG/PNG. The preview server must serve `.webp` as `image/webp`. Note that
  `index_self_contained.html` embeds base64 WebP with no server and no fallback:
  if the delivery target is an unknown viewer rather than a real browser, set
  `"band_format": "jpg"` and rebuild.
- **RTL setup:** `dir="rtl"` on html+body, `.tx{direction:rtl;unicode-bidi:plaintext}`,
  and Arabic fallback fonts — so it reads correctly before the real font loads.
- **Bands are sliced automatically** by `make_plate.py` — cuts land only on
  flat single-colour rows (invisible seams) and never exceed ~16000 px (GPUs may
  refuse taller images). You set `keep`, not band coordinates.
- **PyMuPDF coords are top-left = CSS coords; 1pt -> 1px** on the canvas.
- **Center with flex** (`#scaler{display:flex;justify-content:center}`) +
  `transform-origin:top center` — `margin:auto` alone mis-centers when the
  viewport is narrower than the canvas.
- **Always ship both** the external-images and the self-contained HTML.

See `references/pipeline.md` for a fuller walkthrough and `references/troubleshooting.md`
for the full gotcha list and fixes.
