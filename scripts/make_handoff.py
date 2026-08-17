#!/usr/bin/env python3
"""
make_handoff.py  --  generate design_handoff.md

Lists text that is baked into the background images and therefore CANNOT be made
live / editable / font-swappable, so the design team can recreate it as real
live text in the source file.

Two sources are merged:
  1. AUTO  -- headings exported as a row of per-letter raster images (a common
     artefact of these .ai exports). Detected as >=5 small letter-sized image
     blocks sitting in one horizontal row. Reliable: photos are single large
     images, not rows of tiny ones.
  2. MANUAL -- anything the auto-detector can't see (text flattened into a photo,
     labels inside a chart). Add these to a `handoff` list in project.json:
       {"page":0, "bbox":[x0,y0,x1,y1], "text":"...", "note":"..."}
     (bbox in native pt; text/note optional.)

For every item it crops the region from the source, embeds it in the markdown,
and notes page + coordinates, so the hand-off is unambiguous.

Usage:
    python3 make_handoff.py <out_dir | project.json>
"""
import sys, os, json, glob
import fitz
from PIL import Image

Z = 2.0          # crop render scale
PAD = 8          # pt padding around each crop


def load_cfg(arg):
    if os.path.isdir(arg):
        p = os.path.join(arg, ".aitohtml_project.json")
        if not os.path.exists(p):
            sys.exit(f"No .aitohtml_project.json in {arg}. Build the app first.")
        return json.load(open(p, encoding="utf-8"))
    return json.load(open(arg, encoding="utf-8"))


def resolve_source(cfg, out):
    src = cfg.get("source_pdf")
    if src and os.path.exists(src):
        return src
    parent = os.path.dirname(os.path.abspath(out))
    for ext in ("*.ai", "*.pdf"):
        c = sorted(glob.glob(os.path.join(parent, ext)))
        if c:
            return c[0]
    sys.exit("Could not find the original .ai/.pdf next to the build folder.")


def detect_letter_rows(page):
    """Return [ [x0,y0,x1,y1] pt, ... ] for rows of >=5 small letter-images."""
    small = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type", 0) == 1:
            x0, y0, x1, y1 = b["bbox"]
            w, h = x1 - x0, y1 - y0
            if 4 <= w <= 90 and 10 <= h <= 70:        # letter-sized raster
                small.append((x0, y0, x1, y1))
    small.sort(key=lambda r: (round((r[1] + r[3]) / 2 / 10), r[0]))
    yc = lambda r: (r[1] + r[3]) / 2
    rows, cur = [], []
    for r in small:
        if cur and abs(yc(r) - yc(cur[-1])) < 25:
            cur.append(r)
        else:
            if len(cur) >= 5:
                rows.append(cur)
            cur = [r]
    if len(cur) >= 5:
        rows.append(cur)
    out = []
    for rw in rows:
        out.append([min(r[0] for r in rw), min(r[1] for r in rw),
                    max(r[2] for r in rw), max(r[3] for r in rw)])
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cfg = load_cfg(sys.argv[1])
    out = cfg["out_dir"]
    src = resolve_source(cfg, out)
    doc = fitz.open(src)

    imgdir = os.path.join(out, "handoff_images")
    os.makedirs(imgdir, exist_ok=True)
    # clear stale crops
    for f in glob.glob(os.path.join(imgdir, "*.png")) + glob.glob(os.path.join(imgdir, "*.webp")):
        os.remove(f)

    items = []   # (page, bbox_pt|None, text|None, note, kind)
    for pg in cfg["pages"]:
        idx = pg["index"]
        page = doc[idx]
        for bb in detect_letter_rows(page):
            items.append((idx, bb, None,
                          "Exported as a row of per-letter images — recreate as "
                          "real, selectable live text.", "auto"))
    for m in cfg.get("handoff", []):
        items.append((m["page"], m.get("bbox"), m.get("text"),
                      m.get("note", "Recreate as real, selectable live text."),
                      "manual"))

    items.sort(key=lambda t: (t[0], (t[1][1] if t[1] else 0)))

    L = ["# Design hand-off — text that should be live", "",
         "The items below are **baked into the background images** in the exported "
         "design, so the build cannot turn them into real text: they can't be "
         "edited, selected, translated, or shown in the brand font, and they stay "
         "as flat pixels.", "",
         "**What to change in the source file:** recreate each as ordinary live "
         "text (a real text layer in the brand font) instead of outlining it, "
         "rasterising it, or flattening it into a photo. Where the text is Arabic, "
         "also make sure the font is embedded with proper Unicode (a `ToUnicode` "
         "map) so it isn't exported as garbled glyph codes.", "",
         "Each entry shows a crop of the exact element, its page, and its position.",
         ""]

    by_pg = {}
    for it in items:
        by_pg.setdefault(it[0], []).append(it)

    n = 0
    for idx in sorted(by_pg):
        page = doc[idx]
        L.append(f"## Page {idx}")
        L.append("")
        for j, (p_, bb, text, note, kind) in enumerate(by_pg[idx]):
            n += 1
            if bb:
                clip = fitz.Rect(bb[0] - PAD, bb[1] - PAD, bb[2] + PAD, bb[3] + PAD)
                pix = page.get_pixmap(matrix=fitz.Matrix(Z, Z), clip=clip)
                fn = f"handoff_images/p{idx}_{j}.png"
                Image.frombytes("RGB", [pix.width, pix.height],
                                pix.samples).save(os.path.join(out, fn))
                L.append(f"### {n}. Page {idx} · y ≈ {bb[1]:.0f}–{bb[3]:.0f} pt · "
                         f"x ≈ {bb[0]:.0f}–{bb[2]:.0f} pt")
                L.append("")
                L.append(f"![baked text p{idx}_{j}]({fn})")
            else:
                L.append(f"### {n}. Page {idx}")
            L.append("")
            if text:
                L.append(f"- **Text:** {text}")
            L.append(f"- **Why it's flagged:** {note}")
            L.append(f"- **Found by:** {kind} detection")
            L.append("")

    if n == 0:
        L += ["_No baked text was detected automatically, and none was listed "
              "manually in a `handoff` array. Nothing to hand off._", ""]

    path = os.path.join(out, "design_handoff.md")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    print(f"wrote {path}  ({n} item(s); crops in {imgdir})")


if __name__ == "__main__":
    main()
