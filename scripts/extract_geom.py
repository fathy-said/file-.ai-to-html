#!/usr/bin/env python3
"""
extract_geom.py  --  Dump page dimensions, image rectangles, and per-line text
boxes from a PDF / PDF-compatible .ai file, so Claude can read exact positions.

Usage:
    python3 extract_geom.py INPUT.pdf [OUT.json]

Output JSON:
{
  "pages": [
    {
      "index": 0,
      "width_pt": 1200.0, "height_pt": 3452.8,
      "images": [ {"xref":266,"x":..,"y":..,"w":..,"h":..}, ... ],
      "text_lines": [ {"x":..,"y":..,"w":..,"h":..,"size":..,
                       "color":[r,g,b],"font":"..","raw":".."}, ... ]
    }, ...
  ]
}

Coordinates are top-left origin in PDF points == CSS px on a 1pt->1px canvas.
NOTE: 'raw' is often garbled for Arabic / ligatures / subset fonts. Treat the
geometry (x,y,w,h,size,color) as ground truth, and RE-READ the actual words
from a rendered image of the page.
"""
import sys, json
import fitz  # PyMuPDF

def rgb(i):
    return [(i >> 16) & 255, (i >> 8) & 255, i & 255]

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "geom.json"
    doc = fitz.open(src)
    pages = []
    for pno in range(doc.page_count):
        p = doc[pno]
        r = p.rect
        # images (placement rectangles on the page)
        images = []
        for img in p.get_images(full=True):
            xref = img[0]
            for rc in p.get_image_rects(xref):
                images.append({"xref": xref, "x": round(rc.x0, 1), "y": round(rc.y0, 1),
                               "w": round(rc.width, 1), "h": round(rc.height, 1)})
        # text lines
        lines = []
        for blk in p.get_text("dict").get("blocks", []):
            if blk.get("type", 0) != 0:
                continue
            for line in blk.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                x0 = min(s["bbox"][0] for s in spans)
                y0 = min(s["bbox"][1] for s in spans)
                x1 = max(s["bbox"][2] for s in spans)
                y1 = max(s["bbox"][3] for s in spans)
                big = max(spans, key=lambda s: s["size"])
                raw = "".join(s["text"] for s in spans)
                lines.append({"x": round(x0, 1), "y": round(y0, 1),
                              "w": round(x1 - x0, 1), "h": round(y1 - y0, 1),
                              "size": round(big["size"], 1),
                              "color": rgb(big.get("color", 0)),
                              "font": big.get("font", ""),
                              "raw": raw})
        lines.sort(key=lambda d: (d["y"], d["x"]))
        pages.append({"index": pno, "width_pt": round(r.width, 2),
                      "height_pt": round(r.height, 2),
                      "images": images, "text_lines": lines})
        print(f"page {pno}: {r.width:.0f}x{r.height:.0f}pt  "
              f"{len(images)} images  {len(lines)} text lines")
    json.dump({"pages": pages}, open(out, "w"), ensure_ascii=False, indent=1)
    print("wrote", out)

if __name__ == "__main__":
    main()
