# Changelog — ai-to-html

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
