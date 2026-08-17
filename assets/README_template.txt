TRENDX — "العائد على الإنسان" | HTML version
=================================================

This package contains the full report (Page 1 + Page 2) as ONE single HTML
page (the two pages are stacked vertically into one scrolling page).


------------------------------------------------------------------
1. THE TWO HTML FILES — WHAT'S THE DIFFERENCE?
------------------------------------------------------------------
Both files are the SAME design, same pages, same live text. The ONLY
difference is HOW the images are stored:

  index.html
    - Images are kept OUTSIDE the file, in the "images/" folder.
    - The HTML file itself is tiny (a few KB) and easy to edit.
    - REQUIRES the "images/" folder to sit right next to it, in the same
      folder. If you move index.html on its own, the images will NOT show.
    - Best for: publishing on a website / server, or when you want to edit
      the code.

  index_self_contained.html
    - All images are EMBEDDED inside the file itself (base64).
    - It is one big standalone file (~6 MB) that opens ANYWHERE with no
      folder needed. Just double-click it, or send it over email/WhatsApp
      and it works on any device.
    - Slightly heavier and harder to hand-edit.
    - Best for: quick preview, sharing, or sending to someone.

  Quick rule:
    - Want to test quickly or send it to someone  ->  index_self_contained.html
    - Publishing it / editing it                  ->  index.html  +  images/ folder

  If images don't show:
    - Use index_self_contained.html (it can't have this problem), OR
    - Make sure the "images/" folder is in the SAME place as index.html.


------------------------------------------------------------------
2. ADDING YOUR FONTS
------------------------------------------------------------------
Put your font files inside the "fonts/" folder, then:

1) At the top <style> there are two @font-face blocks:
     PROJECT_DISPLAY = headings font   |   PROJECT_BODY = body text font
   In each block, change:
     - font-family: "PROJECT_DISPLAY"      ->  your font's name
     - src: url("fonts/DISPLAY.woff2")     ->  your file path/name
                                               (woff2 / woff / ttf / otf)
2) Lower down, in :root, also change:
     --font-display / --font-body          ->  the same font names
   (If you use one font for everything, use the same name/file in both.)

Note: before you add your font, the text shows in a system fallback font
(this is normal). Once your real font is in, it will look like the design,
and the line-wrapping will fit better too (your real font is wider/bolder
than the fallback).


------------------------------------------------------------------
3. MAX WIDTH ON LARGE SCREENS
------------------------------------------------------------------
In :root:   --max-width: 1500;   (max width in px the design scales up to)
Increase it = scales bigger, decrease it = stops at a smaller width.


------------------------------------------------------------------
4. RESPONSIVENESS
------------------------------------------------------------------
The design has a fixed width (1200) and zooms as ONE single piece to fit the
screen width (it scales down/up without reflowing anything), capped at
--max-width. It always stays centered.


------------------------------------------------------------------
5. LIVE TEXT vs IMAGES
------------------------------------------------------------------
- Live HTML text (uses your font): all titles, intros, the headline, the
  "حكاية" line, the full timeline (years + titles + descriptions),
  "ركائز الاستثمار", and the section pills.
- Baked as pixel-perfect images: the bubble chart, the bar chart, the stat
  boxes (100+ / 103 / 3.47+), and the portfolios (67 / 14 / 7 / 1) — these
  are compact number-infographics, so they are kept as images.
