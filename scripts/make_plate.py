#!/usr/bin/env python3
"""make_plate.py -- text-stripped background plate + SAFE auto-slicing.

Redacts live text (except inside `keep` ranges, which bake in as pixel-perfect
images), renders the plate at `render_zoom`, then slices it into horizontal bands.

SLICING RULE (strict, safety-first): every cut is placed on a FLAT BACKGROUND row
-- a row whose pixels (in the rendered plate) are uniform across the width
(horizontal std below `flat_std`). Photos, logos, charts, and text all have
horizontal variation, so a cut never lands on them; it only lands where the
rendered row is a single flat colour, so the separately-JPEG'd bands re-stack
seamlessly in HTML. (Uniformity is measured on the actual rendered pixels, so a
flat region that happens to be part of a full-bleed background image still
qualifies -- which matters for designs that are mostly imagery.)
Full-height coverage [0 -> page height] is guaranteed. If no safe row exists
within `band_max_px` of the previous cut (e.g. a very tall full-bleed image),
SAFETY WINS: it keeps searching downward for the next safe row even if the band
ends up taller than the cap (a warning is printed). A band is never cut inside
imagery.

The chosen band ranges (pt) are written back into project.json so build_site
places them at the exact same offsets.

Usage:  python3 make_plate.py project.json
Writes: {out_dir}/images/p{index}_band{i}.jpg   (+ updates project.json bands)
"""
import sys, os, json
import fitz
import numpy as np
from PIL import Image


def safe_row_index(img, flat_std, pad=8):
    """Indices of rows safe to cut: a row qualifies only if EVERY row within
    +/-`pad` px is a single flat colour across the width (per-channel std below
    `flat_std`). The window guarantees the 8x8 JPEG blocks on BOTH sides of the
    cut are uniform, so the re-stacked bands have no visible seam."""
    arr = np.asarray(img)                       # H,W,3 uint8
    sub = arr[:, ::4, :]                        # subsample columns (flatness only)
    row_std = sub.std(axis=1, dtype=np.float32).max(axis=1)   # per-row max-channel std
    flat = (row_std < flat_std).astype(np.int32)
    H = arr.shape[0]
    cs = np.concatenate([[0], np.cumsum(flat)])
    a = np.clip(np.arange(H) - pad, 0, H)
    b = np.clip(np.arange(H) + pad, 0, H)
    winsum = cs[b] - cs[a]
    safe = winsum == (b - a)                    # all rows in the window are flat
    return np.where(safe)[0], H


def auto_cuts(safe_idx, H, target, mx, mn):
    """greedy: walk down, cut at the safe row nearest the ideal spot within the
    cap; if none within the cap, expand past it (safety first)."""
    cuts = [0]; prev = 0; warns = []
    while H - prev > mx:
        lo, hi, ideal = prev + mn, prev + mx, prev + target
        cand = safe_idx[(safe_idx > lo) & (safe_idx <= hi)]
        if cand.size:
            cut = int(cand[np.argmin(np.abs(cand - ideal))])
        else:
            beyond = safe_idx[safe_idx > hi]
            if beyond.size:
                cut = int(beyond[0]); warns.append((prev, cut))
            else:
                break    # no safe row until the bottom -> last band runs to H
        cuts.append(cut); prev = cut
    if cuts[-1] != H:
        cuts.append(H)
    return cuts, warns


def main():
    path = sys.argv[1]
    cfg = json.load(open(path, encoding="utf-8"))
    doc = fitz.open(cfg["source_pdf"])
    zoom = cfg.get("render_zoom", 2.0)
    q = cfg.get("jpeg_quality", 88)
    out = cfg["out_dir"]
    target = cfg.get("band_target_px", 9000)
    mx = cfg.get("band_max_px", 14000)
    mn = cfg.get("band_min_px", 2000)
    flat_std = cfg.get("flat_std", 3.5)
    os.makedirs(os.path.join(out, "images"), exist_ok=True)

    in_keep = lambda mid, keep: any(a <= mid <= b for a, b in keep)

    for pg in cfg["pages"]:
        idx = pg["index"]
        keep = pg.get("keep", [])
        p = doc[idx]


        # redact live text not inside a keep range
        for blk in p.get_text("dict").get("blocks", []):
            if blk.get("type", 0) != 0:
                continue
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    b = span["bbox"]
                    if not in_keep((b[1] + b[3]) / 2, keep):
                        p.add_redact_annot(fitz.Rect(b) + (-1, -1, 1, 1))
        p.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                           graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                           text=fitz.PDF_REDACT_TEXT_REMOVE)
        pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        if pg.get("manual_bands") and pg.get("bands"):
            ranges = [(int(round(y0 * zoom)), int(round(y1 * zoom))) for y0, y1 in pg["bands"]]
            warns = []
        else:
            sidx, H = safe_row_index(img, flat_std)
            cuts, warns = auto_cuts(sidx, H, target, mx, mn)
            ranges = [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]

        import glob as _glob
        for _old in _glob.glob(os.path.join(out, "images", f"p{idx}_band*.jpg")):
            os.remove(_old)
        bands_pt = []
        for i, (y0px, y1px) in enumerate(ranges):
            band = img.crop((0, y0px, img.width, y1px))
            if band.height > mx:
                print(f"  !! page{idx} band{i} = {band.height}px (>{mx}); kept tall so the cut stays in flat background, not inside imagery.")
            fn = os.path.join(out, "images", f"p{idx}_band{i}.jpg")
            band.save(fn, quality=q, optimize=True)
            bands_pt.append([round(y0px / zoom, 2), round(y1px / zoom, 2)])
            print(f"page{idx} band{i}: y {bands_pt[-1][0]}-{bands_pt[-1][1]}pt  {band.size}  {os.path.getsize(fn)//1024}KB")
        for a, b in warns:
            print(f"  ~ page{idx}: no flat row within cap after {round(a/zoom)}pt; next safe cut at {round(b/zoom)}pt (longer band, but cut stays in background).")
        pg["bands"] = bands_pt   # keep build_site in sync

    json.dump(cfg, open(path, "w"), ensure_ascii=False, indent=1)
    print("band ranges written back to", os.path.basename(path))


if __name__ == "__main__":
    main()
