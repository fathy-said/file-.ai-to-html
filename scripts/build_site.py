#!/usr/bin/env python3
"""
build_site.py  --  Assemble the final single-file HTML from the harness template
plus project.json (pages + live-text blocks), then produce the self-contained
(base64) version, the README, the fonts/ placeholder, and a zip.

Usage:
    python3 build_site.py project.json [SKILL_DIR]

SKILL_DIR (default: this script's parent's parent) locates assets/harness.html
and assets/README_template.txt.

Live-text block schema (in project.json -> "blocks"):
  page  : page index the block belongs to
  type  : "C"  centered single/short line (wraps at canvas width)
          "CF" centered FLOWING paragraph     -> needs "colW" (pt)
          "CB" centered inside a box/pill      -> needs "x0","w" (pt)
          "R"  right-aligned block             -> needs "xR","w" (pt)
          "L"  left-aligned block              -> needs "xL","w" (pt)
  text  : the actual text (already transcribed correctly)
  top   : top in native pt of that page
  size  : font size in native pt
  color : "#rrggbb"
  font  : "display" | "body"
  lh    : optional line-height (number)

All page-native pt values are multiplied by that page's scale
(= canvas_width / page.width_pt) so every page renders at the canvas width.
"""
import sys, os, json, base64, zipfile

def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;")

def main():
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    skill_dir = sys.argv[2] if len(sys.argv) > 2 else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = cfg["out_dir"]
    W = cfg["canvas_width"]
    os.makedirs(os.path.join(out, "images"), exist_ok=True)
    os.makedirs(os.path.join(out, "fonts"), exist_ok=True)

    # per-page scale
    for pg in cfg["pages"]:
        pg["scale"] = pg.get("scale") or (W / pg["width_pt"])

    blocks_by_page = {}
    for b in cfg.get("blocks", []):
        blocks_by_page.setdefault(b["page"], []).append(b)

    def emit_block(b, s):
        fs = f'font-size:{round(b["size"]*s,1)}px;'
        lh = f'line-height:{b["lh"]};' if "lh" in b else ""
        ff = "font-family:var(--font-display);" if b.get("font") == "display" else ""
        cc = f'color:{b["color"]};'
        t = b["type"]; top = round(b["top"]*s, 1)
        if t == "C":
            st = f'top:{top}px;left:0;width:{W}px;text-align:center;'
        elif t == "CF":
            colW = b["colW"]*s; left = W/2 - colW/2
            st = f'top:{top}px;left:{round(left,1)}px;width:{round(colW,1)}px;text-align:center;'
        elif t == "CB":
            x0 = b["x0"]*s; w = b["w"]*s
            st = f'top:{top}px;left:{round(x0,1)}px;width:{round(w,1)}px;text-align:center;'
        elif t == "R":
            xR = b["xR"]*s; w = b["w"]*s; left = xR - w
            st = f'top:{top}px;left:{round(left,1)}px;width:{round(w,1)}px;text-align:right;'
        elif t == "L":
            xL = b["xL"]*s; w = b["w"]*s
            st = f'top:{top}px;left:{round(xL,1)}px;width:{round(w,1)}px;text-align:left;'
        else:
            raise ValueError("bad block type " + t)
        return f'  <div class="tx" style="{st}{fs}{lh}{cc}{ff}">{esc(b["text"])}</div>'

    # follow whatever format make_plate.py actually wrote (band_format: webp|jpg)
    def _band_ext(idx, i):
        for ext in ("webp", "jpg", "jpeg"):
            if os.path.exists(os.path.join(out, "images", f"p{idx}_band{i}.{ext}")):
                return ext
        return "webp"

    # build sections
    secs = []
    _img_n = 0
    for pg in cfg["pages"]:
        idx = pg["index"]; s = pg["scale"]
        secs.append(f'<section class="page" id="p{idx}" '
                    f'style="height:{round(pg["height_pt"]*s,1)}px;">')
        for i, (y0, y1) in enumerate(pg["bands"]):
            # first image eager (above the fold); the rest lazy for tall pages
            ld = "eager" if _img_n == 0 else "lazy"
            secs.append(f'  <img class="bg" src="images/p{idx}_band{i}.{_band_ext(idx, i)}" '
                        f'loading="{ld}" decoding="async" '
                        f'style="top:{round(y0*s,1)}px;" alt="">')
            _img_n += 1
        for b in blocks_by_page.get(idx, []):
            secs.append(emit_block(b, s))
        secs.append('</section>')
    sections = "\n".join(secs)

    # fill harness
    harness = open(os.path.join(skill_dir, "assets", "harness.html"), encoding="utf-8").read()
    f = cfg.get("fonts", {})
    fallback = cfg.get("fallback",
        '"Segoe UI", Tahoma, "Geeza Pro", "Noto Sans Arabic", Arial, sans-serif')
    repl = {
        "__LANG__": cfg.get("lang", "ar"),
        "__DIR__": cfg.get("dir", "rtl"),
        "__TITLE__": cfg.get("title", ""),
        "__SEO_H1__": cfg.get("seo_h1", cfg.get("title", "")),
        "__CANVAS_W__": str(W),
        "__MAX_W__": str(cfg.get("max_width", 1500)),
        "__BG__": cfg.get("bg", "#0a0a0a"),
        "__FALLBACK__": fallback,
        "__DISPLAY_FILE__": f.get("display_file", "fonts/DISPLAY.woff2"),
        "__DISPLAY_FMT__": f.get("display_fmt", "woff2"),
        "__BODY_FILE__": f.get("body_file", "fonts/BODY.woff2"),
        "__BODY_FMT__": f.get("body_fmt", "woff2"),
        "__SECTIONS__": sections,
    }
    for k, v in repl.items():
        harness = harness.replace(k, v)
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(harness)
    print("wrote index.html")

    # persist the resolved config inside build/ so `/ai-to-html test` can reuse it later
    try:
        import copy
        saved = copy.deepcopy(cfg)
        json.dump(saved, open(os.path.join(out, ".aitohtml_project.json"), "w"),
                  ensure_ascii=False, indent=1)
    except Exception as e:
        print("warn: could not save .aitohtml_project.json:", e)

    # self-contained (embed every referenced image as base64)
    html = harness
    imgdir = os.path.join(out, "images")
    _embedded_webp = False
    for fn in sorted(os.listdir(imgdir)):
        ref = f'src="images/{fn}"'
        if ref in html:
            data = base64.b64encode(open(os.path.join(imgdir, fn), "rb").read()).decode()
            mime = "webp" if fn.lower().endswith(".webp") else ("jpeg" if fn.lower().endswith((".jpg", ".jpeg")) else "png")
            if mime == "webp":
                _embedded_webp = True
            html = html.replace(ref, f'src="data:image/{mime};base64,{data}"')
    open(os.path.join(out, "index_self_contained.html"), "w", encoding="utf-8").write(html)
    if _embedded_webp:
        print("note: index_self_contained.html embeds WebP data URIs. There is no "
              "server MIME type and no fallback here -- if the recipient opens it in a "
              "viewer without WebP support the page renders with no imagery at all. "
              'Set "band_format": "jpg" in project.json and re-run make_plate.py + '
              "build_site.py if the delivery target is unknown.")
    print("wrote index_self_contained.html",
          os.path.getsize(os.path.join(out, "index_self_contained.html"))//1024, "KB")

    # README + fonts placeholder
    rt = os.path.join(skill_dir, "assets", "README_template.txt")
    if os.path.exists(rt):
        open(os.path.join(out, "README.txt"), "w", encoding="utf-8").write(
            open(rt, encoding="utf-8").read())
    fph = os.path.join(out, "fonts", "PUT-YOUR-FONT-FILES-HERE.txt")
    if not os.path.exists(fph):
        open(fph, "w").write("Drop your font files here and edit the @font-face "
                             "blocks + :root vars in the HTML.\n")

    # zip
    zp = os.path.join(out, cfg.get("zip_name", "site.zip"))
    if os.path.exists(zp):
        os.remove(zp)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ["index.html", "index_self_contained.html", "README.txt"]:
            pth = os.path.join(out, name)
            if os.path.exists(pth):
                z.write(pth, name)
        for sub in ["images", "fonts"]:
            d = os.path.join(out, sub)
            for fn in sorted(os.listdir(d)):
                z.write(os.path.join(d, fn), os.path.join(sub, fn))
    print("wrote", zp, os.path.getsize(zp)//1024, "KB")

if __name__ == "__main__":
    main()
