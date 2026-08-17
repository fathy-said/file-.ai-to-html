#!/usr/bin/env python3
"""
compare_build.py  --  `/ai-to-html test` mode.

Compares the BUILT output of an app against its original `.ai` design, page by
page, and writes a VERSIONED report into  <build>/design_vs_build/version_N/
(auto-incrementing each time `test` is run).

Per version, per page:
    compare_p{i}.jpg   design (left) | build (right)
    diff_p{i}.jpg      difference heatmap (brighter = bigger difference)
and one report.md with per-page + overall match %, the biggest-difference
regions, and an "Analysis & fixes" section Claude fills in after viewing.

PRIMARY rendering of the build = a REAL headless Chromium (so Arabic shaping,
wrapping, and your fonts are exactly as a browser shows them). It auto-discovers
a Chromium/Chrome binary (puppeteer cache, playwright cache, PATH, or the usual
macOS app paths). If none is found it FALLS BACK to an approximate raqm render
and says so in the report.

Usage:
    python3 compare_build.py <build_folder | project.json> [SKILL_DIR]
"""
import sys, os, json, glob, shutil, subprocess, tempfile, datetime, urllib.request, math
import fitz
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

try:
    from skimage.metrics import structural_similarity as _ssim
    HAVE_SSIM = True
except Exception:
    HAVE_SSIM = False


# ---------- config / source ----------
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


# ---------- browser discovery ----------
def find_browser():
    home = os.path.expanduser("~")
    cands = []
    for e in ("PUPPETEER_EXECUTABLE_PATH", "CHROME_PATH", "CHROMIUM_PATH", "BROWSER_PATH"):
        if os.environ.get(e):
            cands.append(os.environ[e])
    # puppeteer cache (linux + mac)
    cands += glob.glob(home + "/.cache/puppeteer/chrome-headless-shell/*/*/chrome-headless-shell")
    cands += glob.glob(home + "/.cache/puppeteer/chrome/*/chrome-linux*/chrome")
    cands += glob.glob(home + "/.cache/puppeteer/chrome/*/*/*.app/Contents/MacOS/Google Chrome for Testing")
    # playwright cache (linux + mac)
    cands += glob.glob(home + "/.cache/ms-playwright/chromium*/chrome-linux/chrome")
    cands += glob.glob(home + "/.cache/ms-playwright/chromium*/chrome-mac*/*/Chromium.app/Contents/MacOS/Chromium")
    cands += glob.glob(home + "/Library/Caches/ms-playwright/chromium*/chrome-mac*/*/Chromium.app/Contents/MacOS/Chromium")
    # usual macOS apps
    cands += ["/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    # PATH
    for n in ("chrome-headless-shell", "chromium", "chromium-browser",
              "google-chrome", "google-chrome-stable", "chrome", "headless-shell"):
        w = shutil.which(n)
        if w:
            cands.append(w)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


# ---------- real-browser render ----------
def render_build_browser(cfg, out):
    """Screenshot build/index.html with headless Chromium, slice into per-page
    images at canvas width. Returns (list_of_PIL_pages, method_str) or (None, why)."""
    browser = find_browser()
    if not browser:
        return None, "no Chromium found"
    html = os.path.join(out, "index.html")
    if not os.path.exists(html):
        return None, "index.html missing"
    W = cfg["canvas_width"]
    # section css heights (px) in document order
    heights = []
    for pg in cfg["pages"]:
        s = pg.get("scale") or (W / pg["width_pt"])
        heights.append(pg["height_pt"] * s)
    total = sum(heights)
    cap = 14000.0
    rs = 1.0 if total <= cap else cap / total
    Wr = max(1, round(W * rs))
    Hr = max(1, round(total * rs)) + 10
    png = tempfile.mktemp(suffix=".png")
    url = "file://" + urllib.request.pathname2url(os.path.abspath(html))
    hl = "--headless" if "headless-shell" in browser else "--headless=new"
    cmd = [browser, hl, "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
           "--hide-scrollbars", "--force-device-scale-factor=1",
           f"--window-size={Wr},{Hr}", "--virtual-time-budget=4000",
           f"--screenshot={png}", url]
    try:
        subprocess.run(cmd, timeout=180,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return None, f"launch failed: {e}"
    if not os.path.exists(png) or os.path.getsize(png) < 1000:
        return None, "screenshot empty"
    shot = Image.open(png).convert("RGB")
    # sanity: not a blank page
    if np.asarray(shot.convert("L")).std() < 3:
        return None, "screenshot looks blank"
    pages = []
    cum = 0.0
    for h in heights:
        y0 = round(cum * rs)
        y1 = round((cum + h) * rs)
        crop = shot.crop((0, y0, shot.width, min(y1, shot.height)))
        if crop.width != W:
            crop = crop.resize((W, round(crop.height * W / max(1, crop.width))))
        pages.append(crop)
        cum += h
    return pages, f"headless Chromium ({os.path.basename(browser)})"


# ---------- approximate raqm render (fallback) ----------
def render_build_raqm(cfg, out, skill_dir):
    qa_font = cfg.get("qa_font") or os.path.join(skill_dir, "assets", "qa_font.ttf")
    f = cfg.get("fonts", {})
    disp = os.path.join(out, f.get("display_file", "fonts/DISPLAY.woff2"))
    body = os.path.join(out, f.get("body_file", "fonts/BODY.woff2"))
    rd = disp if os.path.exists(disp) else None
    rb = body if os.path.exists(body) else None

    def fp(kind):
        return (rd or rb or qa_font) if kind == "display" else (rb or qa_font)
    cache = {}

    def font(kind, px):
        k = (kind, int(round(px)))
        if k not in cache:
            try:
                cache[k] = ImageFont.truetype(fp(kind), max(1, int(round(px))),
                                              layout_engine=ImageFont.Layout.RAQM)
            except Exception:
                cache[k] = ImageFont.truetype(qa_font, max(1, int(round(px))),
                                              layout_engine=ImageFont.Layout.RAQM)
        return cache[k]
    W = cfg["canvas_width"]
    by_pg = {}
    for b in cfg.get("blocks", []):
        by_pg.setdefault(b["page"], []).append(b)
    pages = []
    for pg in cfg["pages"]:
        idx = pg["index"]; s = pg.get("scale") or (W / pg["width_pt"])
        bands = [Image.open(os.path.join(out, "images", f"p{idx}_band{i}.jpg")).convert("RGB")
                 for i in range(len(pg["bands"]))]
        rw = bands[0].width; tot = sum(b.height for b in bands)
        plate = Image.new("RGB", (rw, tot)); y = 0
        for b in bands:
            plate.paste(b, (0, y)); y += b.height
        img = plate.resize((W, round(tot * W / rw))); dr = ImageDraw.Draw(img)

        def meas(t, ft): bb = dr.textbbox((0, 0), t, font=ft); return bb[2] - bb[0]
        def wrap(t, ft, mw):
            ws = t.split(" "); ls = []; cur = ""
            for w_ in ws:
                c = (cur + " " + w_).strip()
                if meas(c, ft) <= mw or not cur: cur = c
                else: ls.append(cur); cur = w_
            if cur: ls.append(cur)
            return ls
        for b in by_pg.get(idx, []):
            ft = font(b.get("font", "body"), b["size"] * s); top = b["top"] * s
            lh = b.get("lh", 1.15) * b["size"] * s; t = b["type"]
            if t == "C": mw, al, cx = W, "c", W / 2
            elif t == "CF": mw, al, cx = b["colW"] * s, "c", W / 2
            elif t == "CB": mw, al, cx = b["w"] * s, "c", (b["x0"] + b["w"] / 2) * s
            elif t == "R": mw, al, rx = b["w"] * s, "r", b["xR"] * s
            elif t == "L": mw, al, lx = b["w"] * s, "l", b["xL"] * s
            else: continue
            lns = wrap(b["text"], ft, mw) if t in ("CF", "R", "L") else [b["text"]]
            yc = top
            for ln in lns:
                lw = meas(ln, ft)
                x = (cx - lw / 2) if al == "c" else (rx - lw) if al == "r" else lx
                dr.text((x, yc), ln, font=ft, fill=b["color"]); yc += lh
        pages.append(img)
    return pages


# ---------- metrics ----------
def score(a_img, b_img):
    w = 700
    a = a_img.convert("L").resize((w, int(a_img.height * w / a_img.width)))
    b = b_img.convert("L").resize((w, int(b_img.height * w / b_img.width)))
    h = min(a.height, b.height)
    a = a.crop((0, 0, w, h)); b = b.crop((0, 0, w, h))
    aa = np.asarray(a, float); bb = np.asarray(b, float)
    ab = np.asarray(a.filter(ImageFilter.GaussianBlur(5)), float)
    bl = np.asarray(b.filter(ImageFilter.GaussianBlur(5)), float)
    if HAVE_SSIM:
        ex = _ssim(aa, bb, data_range=255); ly = _ssim(ab, bl, data_range=255)
    else:
        ex = 1 - np.abs(aa - bb).mean() / 255; ly = 1 - np.abs(ab - bl).mean() / 255
    return round(ly * 100, 1), round(ex * 100, 1)


def hotspots(a_img, b_img, scale, blocks, top_n=4):
    w = 700
    a = np.asarray(a_img.convert("L").resize((w, int(a_img.height * w / a_img.width))), float)
    b = np.asarray(b_img.convert("L").resize((w, int(b_img.height * w / b_img.width))), float)
    h = min(a.shape[0], b.shape[0]); a = a[:h]; b = b[:h]
    step = max(1, h // 40); d = np.abs(a - b); bands = []
    for r in range(0, h, step):
        bands.append((d[r:r + step].mean(), r, min(r + step, h)))
    bands.sort(reverse=True); out = []
    for sc, r0, r1 in bands[:top_n]:
        if sc < 6: continue
        y0 = r0 / h * a_img.height / scale; y1 = r1 / h * a_img.height / scale
        near = ""
        if blocks:
            nb = min(blocks, key=lambda bk: abs(bk["top"] - (y0 + y1) / 2))
            txt = nb["text"].strip().replace("\n", " ")
            near = (txt[:42] + "…") if len(txt) > 42 else txt
        out.append((round(y0), round(y1), round(float(sc), 1), near))
    return out


# ---------- main ----------
# ---------- live-text integrity (strict) ----------
def _hex_rgb(c):
    c = str(c).strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        return None
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _lin(v):
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def _lum(rgb):
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _block_box(b, W):
    """Container box (pt) for a block, matching build_site.emit_block geometry.
    For flowing types the height spans the estimated wrapped line count, so the
    source spans of lines 2+ are counted as covered (not falsely 'missing')."""
    t = b["type"]; top = float(b["top"])
    size = float(b.get("size", 30)); lh = float(b.get("lh", 1.2))
    if t == "C":
        left, w = 0.0, float(W)
    elif t == "CF":
        w = float(b["colW"]); left = W / 2 - w / 2
    elif t == "CB":
        left, w = float(b["x0"]), float(b["w"])
    elif t == "R":
        w = float(b["w"]); left = float(b["xR"]) - w
    elif t == "L":
        left, w = float(b["xL"]), float(b["w"])
    else:
        left, w = 0.0, float(W)
    if t in ("CF", "R", "L") and w > 0:
        cpl = max(1.0, w / (size * 0.55))            # ~chars per line (Arabic)
        lines = max(1, math.ceil(len(str(b.get("text", ""))) / cpl))
        h = size * 1.6 * lines        # generous: cover this block's wrapped lines
    else:
        h = size * 1.3                # tight: a single line, so a missing line
        #                               just below (e.g. a number's caption) still shows
    return (left, top, left + w, top + h)


def _strip_arr(src, idx):
    """Render the page with ALL live text removed (the real background behind text)."""
    d = fitz.open(src); p = d[idx]
    for blk in p.get_text("dict")["blocks"]:
        if blk.get("type", 0) == 0:
            for ln in blk.get("lines", []):
                for sp in ln.get("spans", []):
                    p.add_redact_annot(fitz.Rect(sp["bbox"]) + (-1, -1, 1, 1))
    p.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                       graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                       text=fitz.PDF_REDACT_TEXT_REMOVE)
    pix = p.get_pixmap(matrix=fitz.Matrix(1, 1))
    arr = np.asarray(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
    d.close()
    return arr


def _median_color(arr, box):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    H, Wd = arr.shape[:2]
    x0 = max(0, min(x0, Wd - 1)); x1 = max(x0 + 1, min(x1, Wd))
    y0 = max(0, min(y0, H - 1)); y1 = max(y0 + 1, min(y1, H))
    crop = arr[y0:y1, x0:x1].reshape(-1, 3)
    if crop.size == 0:
        return (255, 255, 255)
    return tuple(int(v) for v in np.median(crop, axis=0))


def _letter_rows(page):
    """Baked headings = rows of >=5 small letter-images (see make_handoff)."""
    small = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type", 0) == 1:
            x0, y0, x1, y1 = b["bbox"]; w, h = x1 - x0, y1 - y0
            if 4 <= w <= 90 and 10 <= h <= 70:
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
    return [[min(r[0] for r in rw), min(r[1] for r in rw),
             max(r[2] for r in rw), max(r[3] for r in rw)] for rw in rows]


def _in_box(cx, cy, box):
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


def _source_color_at(page, box):
    """Most common ORIGINAL text colour (hex) of source spans whose centre is in
    box — i.e. the colour the design actually used there. None if no span."""
    from collections import Counter
    cols = []
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type", 0) != 0:
            continue
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                bb = sp["bbox"]; cx = (bb[0] + bb[2]) / 2; cy = (bb[1] + bb[3]) / 2
                if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
                    cols.append(int(sp.get("color", 0)) & 0xFFFFFF)
    if not cols:
        return None
    return "#%06x" % Counter(cols).most_common(1)[0][0]


def _source_size_at(page, box, fallback):
    sizes = []
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type", 0) != 0:
            continue
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                bb = sp["bbox"]; cx = (bb[0] + bb[2]) / 2; cy = (bb[1] + bb[3]) / 2
                if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
                    sizes.append(float(sp.get("size", 0)))
    sizes = [s for s in sizes if s > 0]
    return round(sorted(sizes)[len(sizes) // 2], 1) if sizes else fallback


def _fix_color(src_col, bg, min_c):
    """Prefer the design's own colour; only if it still wouldn't read against the
    actual background do we fall back to plain dark/light (guarantees progress)."""
    if src_col:
        rgb = _hex_rgb(src_col)
        if rgb and _contrast(rgb, bg) >= min_c:
            return src_col
    return "#111111" if _lum(bg) > 0.45 else "#ffffff"


def live_text_integrity(cfg, src, W, vdir, doc, renders):
    """Strict check: every live block must be legible, and no source text missing.
    A source-text region counts as 'missing' only when the BUILD render is blank
    there while the DESIGN has text (so baked text is not falsely flagged).
    Returns (issue_count, markdown_lines, fixes) where fixes = {"contrast":[...],
    "missing":[...]} are concrete, ready-to-apply auto-fixes."""
    min_c = float(cfg.get("min_contrast", 3.0))
    blocks_by_pg = {}
    for b in cfg.get("blocks", []):
        blocks_by_pg.setdefault(b["page"], []).append(b)
    handoff_by_pg = {}
    for m in cfg.get("handoff", []):
        if m.get("bbox"):
            handoff_by_pg.setdefault(m["page"], []).append(m["bbox"])

    contrast_issues, missing_issues = [], []
    fixes = {"contrast": [], "missing": []}
    for pg in cfg["pages"]:
        idx = pg["index"]; page = doc[idx]
        strip = _strip_arr(src, idx)
        blocks = blocks_by_pg.get(idx, [])
        boxes = [_block_box(b, W) for b in blocks]

        # 1) contrast: text colour vs the background actually behind it
        for b in blocks:
            fg = _hex_rgb(b.get("color", "#000"))
            if not fg:
                continue
            bx = _block_box(b, W)
            bg = _median_color(strip, bx)
            cr = _contrast(fg, bg)
            if cr < min_c:
                txt = " ".join(str(b.get("text", "")).split())[:60]
                src_col = _source_color_at(page, bx)
                new_col = _fix_color(src_col, bg, min_c)
                contrast_issues.append((idx, b["top"], txt, b.get("color"),
                                        "#%02x%02x%02x" % bg, round(cr, 2), new_col))
                fixes["contrast"].append({"page": idx, "top": b["top"],
                                          "snip": txt, "new_color": new_col})

        # 2) coverage: real source text not overlaid live and not intentionally baked
        keep = pg.get("keep", []); lrows = _letter_rows(page)
        hboxes = handoff_by_pg.get(idx, [])
        uncovered = []
        for blk in page.get_text("dict")["blocks"]:
            if blk.get("type", 0) != 0:
                continue
            for ln in blk.get("lines", []):
                for s in ln.get("spans", []):
                    if not s.get("text", "").strip():
                        continue
                    bb = s["bbox"]; cx = (bb[0] + bb[2]) / 2; cy = (bb[1] + bb[3]) / 2
                    if any(r[0] <= cy <= r[1] for r in keep):
                        continue
                    if any(_in_box(cx, cy, bx) for bx in boxes):
                        continue
                    if any(_in_box(cx, cy, bx) for bx in lrows):
                        continue
                    if any(_in_box(cx, cy, bx) for bx in hboxes):
                        continue
                    uncovered.append(bb)
        # cluster uncovered spans into regions
        uncovered.sort(key=lambda b: ((b[1] + b[3]) / 2, (b[0] + b[2]) / 2))
        clusters = []
        for bb in uncovered:
            cy = (bb[1] + bb[3]) / 2
            if clusters and abs(cy - clusters[-1]["cy"]) < 45:
                c = clusters[-1]
                c["x0"] = min(c["x0"], bb[0]); c["y0"] = min(c["y0"], bb[1])
                c["x1"] = max(c["x1"], bb[2]); c["y1"] = max(c["y1"], bb[3])
                c["cy"] = (c["y0"] + c["y1"]) / 2
            else:
                clusters.append({"x0": bb[0], "y0": bb[1], "x1": bb[2],
                                 "y1": bb[3], "cy": cy})
        # keep only clusters where the BUILD is blank but the DESIGN has text
        dimg, bimg, sp = renders.get(idx, (None, None, 1.0))
        for j, c in enumerate(clusters):
            if dimg is not None:
                px = (int(c["x0"] * sp), int(c["y0"] * sp),
                      int(c["x1"] * sp), int(c["y1"] * sp))
                dg = np.asarray(dimg.convert("L").crop(px), float)
                bg_ = np.asarray(bimg.convert("L").crop(px), float)
                d_std = dg.std() if dg.size else 0.0
                b_std = bg_.std() if bg_.size else 0.0
                # design has text (texture) but build is comparatively flat → missing
                if not (d_std > 12 and b_std < d_std * 0.45):
                    continue
            box = (c["x0"], c["y0"], c["x1"], c["y1"])
            size = _source_size_at(page, box, fallback=max(18, min(48, (c["y1"] - c["y0"]))))
            col = _source_color_at(page, box) or "#111111"
            fixes["missing"].append({
                "block": {"page": idx, "type": "CB", "text": "صحّح هذا النص",
                          "top": round(c["y0"], 1), "size": size, "color": col,
                          "font": "body", "x0": round(c["x0"], 1),
                          "w": round(c["x1"] - c["x0"], 1)},
                "handoff": {"page": idx,
                            "bbox": [round(c["x0"]), round(c["y0"]),
                                     round(c["x1"]), round(c["y1"])],
                            "text": "صحّح هذا النص",
                            "note": "auto-added placeholder — replace with the real "
                                    "text read from the design"}})
            if vdir:
                clip = fitz.Rect(c["x0"] - 6, c["y0"] - 6, c["x1"] + 6, c["y1"] + 6)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip)
                fn = f"missing_p{idx}_{j}.png"
                Image.frombytes("RGB", [pix.width, pix.height],
                                pix.samples).save(os.path.join(vdir, fn))
            else:
                fn = None
            missing_issues.append((idx, round(c["y0"]), round(c["y1"]), fn))

    n = len(contrast_issues) + len(missing_issues)
    L = ["## Live-text integrity (strict — must be 100%)", ""]
    if n == 0:
        L += ["**PASS** — every live-text block is legible against its background, "
              "and no source text is missing from the build.", ""]
    else:
        L += [f"**FAIL — {n} issue(s). This must reach 0 before delivering.**", ""]
    if contrast_issues:
        L += [f"### Invisible / low-contrast text (< {min_c}:1 vs its background)", ""]
        for idx, top, txt, fg, bg, cr, newc in contrast_issues:
            L.append(f'- page {idx}, y≈{round(top)} pt — "{txt}" — text `{fg}` on '
                     f"background `{bg}` (contrast {cr}:1). Recolour to `{newc}` "
                     f"(the design's own colour where available).")
        L.append("")
    if missing_issues:
        L += ["### Missing text (present in the design, but neither overlaid live "
              "nor baked)", ""]
        for idx, y0, y1, fn in missing_issues:
            L.append(f"- page {idx}, y≈{y0}–{y1} pt — add a live block here (or a "
                     f"`keep` range if it is meant to stay baked):")
            if fn:
                L.append(f"  ![missing p{idx}]({fn})")
        L.append("")
    return n, L, fixes


def apply_fixes(cfg, fixes):
    """Apply auto-fixes to cfg in place. Returns a human-readable log list."""
    log = []
    for fx in fixes.get("contrast", []):
        for b in cfg.get("blocks", []):
            if (b.get("page") == fx["page"]
                    and abs(float(b.get("top", -1)) - float(fx["top"])) < 1.0
                    and " ".join(str(b.get("text", "")).split())[:60] == fx["snip"]):
                old = b.get("color")
                b["color"] = fx["new_color"]
                log.append(f"recoloured invisible text on page {fx['page']} "
                           f"(y≈{round(fx['top'])}) \"{fx['snip']}\": "
                           f"{old} → {fx['new_color']}")
                break
    for fx in fixes.get("missing", []):
        cfg.setdefault("blocks", []).append(fx["block"])
        cfg.setdefault("handoff", []).append(fx["handoff"])
        bl = fx["block"]
        log.append(f"added placeholder live block on page {bl['page']} "
                   f"(y≈{round(bl['top'])}) — \"صحّح هذا النص\" in {bl['color']}")
    return log


def render_build_any(cfg, out, skill_dir):
    builds, method = render_build_browser(cfg, out)
    if builds is None:
        why = method
        builds = render_build_raqm(cfg, out, skill_dir)
        f = cfg.get("fonts", {})
        has_real = os.path.exists(os.path.join(out, f.get("body_file", "fonts/BODY.woff2"))) or \
                   os.path.exists(os.path.join(out, f.get("display_file", "fonts/DISPLAY.woff2")))
        method = (f"APPROXIMATE raqm render ({why}) — "
                  f"{'your fonts' if has_real else 'stand-in font'}; "
                  f"run in an environment with Chromium for an exact comparison")
    return builds, method


def page_renders(cfg, doc, W, builds):
    """{page_index: (design_img, build_img, scale)} cropped to canvas width."""
    out = {}
    for k, pg in enumerate(cfg["pages"]):
        idx = pg["index"]
        build = builds[k]
        z = W / pg["width_pt"]
        pix = doc[idx].get_pixmap(matrix=fitz.Matrix(z, z))
        design = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        H = min(design.height, build.height)
        out[idx] = (design.crop((0, 0, W, H)), build.crop((0, 0, W, H)), z)
    return out


def main():
    arg = sys.argv[1]
    rest = sys.argv[2:]
    autofix = any(a in ("--fix", "fix", "-f") for a in rest)
    skill_dir = next((a for a in rest if a not in ("--fix", "fix", "-f")),
                     os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cfg = load_cfg(arg)
    out = cfg["out_dir"]; W = cfg["canvas_width"]
    src = resolve_source(cfg, out)
    doc = fitz.open(src)

    # --- auto-fix loop (only with --fix): recolour invisible text to the design's
    #     own colour, add a placeholder live block for missing text, rebuild, and
    #     re-check, until live-text integrity passes (or 3 rounds) ---
    saved_cfg = os.path.join(out, ".aitohtml_project.json")
    build_site_py = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "build_site.py")
    fix_log = []
    if autofix:
        for _ in range(3):
            builds, method = render_build_any(cfg, out, skill_dir)
            rds = page_renders(cfg, doc, W, builds)
            n, _, fixes = live_text_integrity(cfg, src, W, None, doc, rds)
            if n == 0 or not (fixes["contrast"] or fixes["missing"]):
                break
            fix_log += apply_fixes(cfg, fixes)
            json.dump(cfg, open(saved_cfg, "w", encoding="utf-8"),
                      ensure_ascii=False)
            try:
                subprocess.run([sys.executable, build_site_py, saved_cfg, skill_dir],
                               check=True, capture_output=True)
            except Exception as e:
                fix_log.append(f"(could not rebuild to apply fixes: {e})")
                break
            cfg = load_cfg(out)

    builds, method = render_build_any(cfg, out, skill_dir)
    print("render method:", method)

    base = os.path.join(out, "design_vs_build"); os.makedirs(base, exist_ok=True)
    ex = [d for d in os.listdir(base) if d.startswith("version_") and d[8:].isdigit()]
    ver = max([int(d[8:]) for d in ex], default=0) + 1
    vdir = os.path.join(base, f"version_{ver}"); os.makedirs(vdir)

    by_pg = {}
    for b in cfg.get("blocks", []):
        by_pg.setdefault(b["page"], []).append(b)

    rows = []; hot_all = []; renders = {}
    for k, pg in enumerate(cfg["pages"]):
        idx = pg["index"]; s = pg.get("scale") or (W / pg["width_pt"])
        build = builds[k]
        pix = doc[idx].get_pixmap(matrix=fitz.Matrix(W / pg["width_pt"], W / pg["width_pt"]))
        design = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        H = min(design.height, build.height)
        design = design.crop((0, 0, W, H)); build = build.crop((0, 0, W, H))
        renders[idx] = (design, build, W / pg["width_pt"])
        sbs = Image.new("RGB", (W * 2 + 20, H), "white")
        sbs.paste(design, (0, 0)); sbs.paste(build, (W + 20, 0))
        sc = min(1.0, 1500 / sbs.width)
        if sc < 1.0: sbs = sbs.resize((int(sbs.width * sc), int(sbs.height * sc)))
        sbs.save(os.path.join(vdir, f"compare_p{idx}.jpg"), quality=82)
        da = np.asarray(design.convert("L"), float); db = np.asarray(build.convert("L"), float)
        diff = Image.fromarray(np.clip(np.abs(da - db) * 2.2, 0, 255).astype("uint8"))
        sc2 = min(1.0, 900 / diff.width)
        if sc2 < 1.0: diff = diff.resize((int(diff.width * sc2), int(diff.height * sc2)))
        diff.save(os.path.join(vdir, f"diff_p{idx}.jpg"), quality=80)
        ly, exv = score(design, build); rows.append((idx, ly, exv))
        for hs in hotspots(design, build, s, by_pg.get(idx, [])):
            hot_all.append((idx,) + hs)
        print(f"page{idx}: layout {ly}%  exact {exv}%")

    al = round(sum(r[1] for r in rows) / len(rows), 1)
    ae = round(sum(r[2] for r in rows) / len(rows), 1)
    integ_n, integ_L, _ = live_text_integrity(cfg, src, W, vdir, doc, renders)
    is_approx = method.startswith("APPROXIMATE")
    verdict = ("**Live-text integrity: PASS ✅**" if integ_n == 0
               else f"**Live-text integrity: FAIL ❌ — {integ_n} issue(s), see below.**")
    L = [f"# design_vs_build — version_{ver}", "", verdict, ""]
    if fix_log:
        L += [f"_Auto-fixed {len(fix_log)} live-text issue(s) before this report "
              f"(see “Auto-fixes applied” below)._", ""]
    if is_approx:
        try:
            _prompt = open(os.path.join(skill_dir, "assets", "browser_setup_prompt.txt"),
                           encoding="utf-8").read().rstrip()
        except Exception:
            _prompt = "(setup prompt asset missing)"
        L += [
            "> ## ⚠️ THIS IS AN APPROXIMATE (EXPERIMENTAL) COMPARISON",
            ">",
            "> No headless browser was found in this environment, so the build was",
            "> rendered with a stand-in method and a fallback font. **The match",
            "> numbers below are indicative, NOT final — don't make decisions on",
            "> them as-is.**",
            ">",
            "> ### A more accurate comparison is available",
            "> Rendering the real `index.html` in **headless Chromium** gives correct",
            "> Arabic shaping, real line-wrapping, and your actual fonts — so the",
            "> comparison reflects what users truly see.",
            ">",
            "> ### How to switch to it (works on macOS, Linux, or Windows)",
            "> 1. Open this project in your terminal with Claude (Claude Code).",
            "> 2. Copy the **setup prompt** below and paste it to Claude as-is.",
            "> 3. It auto-detects your OS, finds or installs a browser, and verifies it.",
            "> 4. When it says **READY**, re-run `/ai-to-html test` — you'll get an",
            ">    accurate report in the next `version_` folder.",
            "",
            "<details>",
            "<summary><b>📋 Setup prompt — click to expand, copy ALL of it, paste to Claude in your terminal</b></summary>",
            "",
            "```text",
            _prompt,
            "```",
            "</details>",
            "",
            "---",
            "",
        ]
    L += [
         f"- Source design: `{os.path.basename(src)}`",
         f"- Generated: {datetime.date.today().isoformat()}",
         f"- Build rendered with: {method}",
         f"- Metric: {'SSIM (structural similarity)' if HAVE_SSIM else 'normalised pixel difference'}",
         "", "## Match scores", "",
         "| page | layout & imagery match | exact pixel match |",
         "|------|------------------------|-------------------|"]
    for idx, ly, exv in rows:
        L.append(f"| {idx} | {ly}% | {exv}% |")
    L.append(f"| **ALL** | **{al}%** | **{ae}%** |")
    L += ["",
          "- **Layout & imagery match** — blur-tolerant; reflects whether imagery, "
          "colours, and element positions came out right.",
          "- **Exact pixel match** — stricter; also catches font/spacing differences.",
          ""]
    if fix_log:
        L += ["## Auto-fixes applied", "",
              "These live-text problems were detected and fixed automatically "
              "(then the build was re-checked):", ""]
        L += [f"- {line}" for line in fix_log]
        L += ["",
              "Placeholder blocks read **«صحّح هذا النص»** — they are live and "
              "in the design's own position/size/colour, so the text shows and is "
              "fully editable; replace the wording with the real text from the "
              "design (also listed in `design_handoff.md`).", ""]
    L += integ_L
    L += ["## Biggest-difference regions (auto-detected)", ""]
    if hot_all:
        for idx, y0, y1, scv, near in hot_all:
            tag = f' — near: "{near}"' if near else ""
            L.append(f"- page {idx}, y ≈ {y0}–{y1} pt (diff {scv}){tag}")
    else:
        L.append("- none significant.")

    L += ["## Analysis & fixes", "",
          "<!-- Claude: open each compare_p*.jpg and diff_p*.jpg, then for every REAL "
          "discrepancy write what differs, the likely cause, and the concrete fix "
          "(block top/width/line-height, keep-range, colour, missing font, etc.). "
          "Mark each as 'needs fixing' or 'expected (e.g. fallback font)'. -->", ""]
    open(os.path.join(vdir, "report.md"), "w", encoding="utf-8").write("\n".join(L))
    print(f"\nwrote {vdir}/   OVERALL layout {al}%  exact {ae}%   "
          f"-> version_{ver}   live-text: {'PASS' if integ_n == 0 else f'FAIL ({integ_n})'}"
          f"{f'   (auto-fixed {len(fix_log)})' if fix_log else ''}")


if __name__ == "__main__":
    main()
