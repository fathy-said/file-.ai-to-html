# Changelog — ai-to-html

## v2.1.0 — consistency + WebP migration fixes
Corrective release. v2.0.0 shipped the WebP switch and the X-ray rules but left
contradictions and a half-finished migration behind. No pipeline redesign.

- **Fixed a direct self-contradiction in `SKILL.md`:** the defaults section still
  read "Image format = JPEG (universal). Never WebP" while the gotchas section
  declared WebP mandatory. Defaults now state WebP for production, JPEG/PNG for
  QA artifacts and handoff crops.
- **Made the trigger match the v2.0.0 intent.** v2.0.0's changelog claimed the
  skill no longer required an explicit by-name request, but only the leading
  "MANUAL / OPT-IN" sentence was removed — the `IMPORTANT TRIGGERING RULE`
  paragraph ("ignore this skill entirely" without a by-name request) was still
  in the description and still governing. The description is now rewritten
  around real trigger conditions, with explicit non-triggers.
- **Corrected the band-cut safety margin for WebP.** `safe_row_index`'s `pad`
  defaulted to 8, sized for JPEG's 8x8 DCT blocks — the docstring said so. WebP
  (VP8) codes in 16x16 macroblocks with intra prediction and an in-loop
  deblocking filter that has no neighbour at an image edge, so 8 no longer
  guaranteed a seamless re-stack. Default is now 16, overridable via `cut_pad`.
- **Restored backward compatibility with v1 builds:**
  - `compare_build.py` opened `p{i}_band{n}.webp` with no fallback and crashed on
    any v1 build directory; it now falls back to `.jpg`/`.jpeg` and raises a
    readable error naming the missing file.
  - `make_plate.py` swept only stale `.webp` bands, so v1 `.jpg` bands survived
    into the output zip; it now sweeps `.webp`, `.jpg`, and `.jpeg`.
  - A legacy `jpeg_quality` key was silently ignored in favour of the default 90;
    it is now honoured with a printed note telling the user to rename it.
- **Added a real `band_format` escape hatch.** `make_plate.py` accepts
  `"band_format": "webp"` (default) or `"jpg"`, and `build_site.py` now detects
  the extension that was actually written instead of hard-coding `.webp`.
  Previously WebP was unconditional, so the "ship JPEG instead" advice had no
  supported way to be acted on. `cut_pad` is configurable for the same reason.
- **Documented the risk the WebP switch introduced.** v1 mandated JPEG because
  some viewers don't render WebP; v2.0.0 replaced that note with server MIME-type
  advice, which doesn't apply to `index_self_contained.html` (base64, no server,
  no fallback — imagery silently vanishes). `build_site.py` now prints a warning
  when it embeds WebP, and `troubleshooting.md` separates the served-build case
  from the self-contained case.
- **Corrected the v2.0.0 claim that `make_handoff.py` was updated for WebP.** It
  still writes PNG, which is correct — handoff crops need lossless text — so the
  changelog entry was wrong, not the code.
- Removed `scripts/__pycache__/` (104 KB of committed bytecode) from the package
  and re-zipped with deflate compression instead of stored.

## v2.0.0 — Illustrator X-ray + WebP production pipeline
- Repackaged as the full `.skill` extension format with the existing scripts, references, assets, and QA pipeline.
- Triggered by Illustrator/PDF → HTML and X-ray/pixel-match requests instead of requiring an explicit skill name.
- Illustrator is explicitly the source of truth; existing HTML is fixed rather than redesigned.
- Added landmark-based X-ray verification, coordinate guidance, browser `getBoundingClientRect()` measurement, and overlay/diff diagnosis rules.
- **All production raster assets are now WebP-only**, including background bands and self-contained HTML embeds. Default `webp_quality` is 90.
- QA screenshots/diffs remain JPEG/PNG.
- Updated `make_plate.py`, `build_site.py`, `compare_build.py`, references, and README for WebP.
  (`make_handoff.py` was listed here in error — it continues to write PNG crops by design.)
- Added optional 100vh section scroll-snap guidance for presentation-style reports.


All notable changes to this skill. One packaged change = one version. Newest first.

Versions before v1.0.0 were not archived as files at the time they were made; they
are listed here for history and can be reconstructed on request from the session
transcripts. From v1.0.0 onward, every packaged version is saved as its own
`.skill` file in the version archive, so any version can be restored exactly.

## v1.0.0 — current
- Auto-repair for live-text integrity (runs with `--fix`, i.e. on a build and on
  `/ai-to-html test fix`):
  - **invisible text** (colour ≈ its background) is recoloured to the design's own
    colour, read from the source PDF (falls back to plain dark/light only if that
    still wouldn't read);
  - **missing text** gets a live placeholder block «صحّح هذا النص» at the source's
    exact position, size, and colour, logged in `design_handoff.md`;
  - rebuilds and re-checks up to 3 rounds until the verdict is `PASS`; the report
    gains an **Auto-fixes applied** section.
- Modes: `test` = measure only; `test fix` = auto-repair; build auto-runs the
  comparison with `--fix`. Live-text integrity is the only class of issue that is
  auto-fixed; everything else is still proposed first.
- Removed `qa_preview.py`; `compare_build.py` is now the single QA (real browser
  render when available, approximate raqm fallback otherwise).

## v0.11.0
- Strict **live-text integrity** check in `compare_build.py`: flags any live block
  whose colour is too close to its background (invisible) and any source text that
  is missing from the build (neither overlaid live nor baked). Verdict must be
  `PASS`; runs in the build auto-compare and in `test`.

## v0.10.0
- Fixed the **double-scroll** in the harness: `#scaler` uses `overflow:hidden`
  (both axes) instead of `overflow-x:hidden`, so the page has a single scrollbar.

## v0.9.0
- Removed redundant "Live text" / "Baked text" appendix sections from the `test`
  report.

## v0.8.0
- `make_handoff.py` + `design_handoff.md`: auto-detects per-letter-image baked
  headings (and accepts manual `handoff` entries) and lists, for the design team,
  the baked text that should be made live.

## v0.7.0
- Rewrote the plate slicer (`make_plate.py`) to cut bands only on flat single-colour
  rows, giving invisible seams.

## v0.6.0
- After every comparison: triage, propose a numbered fix plan, and fix only on
  approval (no silent edits).

## v0.5.0
- `test` mode: browser-primary comparison (auto-discovers a headless Chromium) with
  an approximate raqm fallback and a ready-to-paste setup banner; a build now runs
  the comparison once automatically.

## v0.4.0
- QA preview images written to a temp scratch folder only, so the delivered build
  stays clean.

## v0.3.0
- Self-improvement loop (human + Claude persist lessons and repackage) and a
  post-delivery feedback phase.

## v0.2.0
- Multi-app isolation: each `.ai` is its own project with its own `build/` beside
  it; nothing is mixed across apps.

## v0.1.0
- Initial: `.ai`/PDF → one faithful, responsive, single-file HTML; background plate
  (selective text-strip) + live RTL Arabic text overlay; multi-page stacking;
  placeholder fonts; self-contained HTML + zip.
