"""Turn a product spec into a print-ready PDF (and a cover JPG) using a headless browser."""
import json
import re
import time
from pathlib import Path

from .. import config
from . import pages

SIZES = {"A4": ("210mm", "297mm"), "A5": ("148mm", "210mm"), "LETTER": ("8.5in", "11in")}

CSS = """
@page { size: %(w)s %(h)s; margin: 0 }
* { box-sizing: border-box; margin: 0; padding: 0 }
body { font-family: %(font)s; color: #2b2b2b; }
.page { width: %(w)s; height: %(h)s; padding: %(pad)s; position: relative; overflow: hidden;
        page-break-after: always; background: %(paper)s; }
.page:last-child { page-break-after: auto }
.page::before { content: ""; position: absolute; inset: 6mm; border: 0.4mm solid %(accent)s55; border-radius: 3mm; pointer-events: none }
.pn { position: absolute; bottom: 7mm; left: 0; right: 0; text-align: center; font-size: 8pt; color: #999 }
.ph { margin-bottom: 4mm; border-bottom: 0.5mm solid %(primary)s; padding-bottom: 2mm }
.ph h2 { font-family: %(hfont)s; color: %(primary)s; font-size: %(h2)s; line-height: %(lh)s }
.ph .sub { color: #777; font-size: 9pt; margin-top: 1mm }
.ln { height: %(lg)s; border-bottom: 0.25mm solid #cfc6bd }
.prompt, .lab { color: %(primary)s; font-weight: 600; font-size: 10pt; margin: 3mm 0 1mm; line-height: %(lh)s }
.q { margin-bottom: 3mm }
.cover, .section { height: 100%%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center }
.cover .frame { position: absolute; inset: 12mm; border: 0.8mm double %(accent)s; border-radius: 4mm }
.cover h1, .section h1 { font-family: %(hfont)s; color: %(primary)s; font-size: %(h1)s; line-height: %(lh)s; padding: 0 12mm }
.ctop, .snum { color: %(accent)s; letter-spacing: 2pt; font-size: 10pt; margin-bottom: 4mm; text-transform: uppercase }
.csub { color: #666; font-size: 11pt; margin-top: 4mm; padding: 0 16mm; line-height: %(lh)s }
.orn { color: %(accent)s; font-size: 24pt; margin: 8mm 0 }
.cname { font-size: 10pt; color: #555 } .cbrand { position: absolute; bottom: 18mm; font-size: 8pt; letter-spacing: 3pt; color: %(accent)s; text-transform: uppercase }
.quote { font-family: %(hfont)s; color: %(primary)s; font-size: 14pt; margin-top: 8mm; padding: 0 14mm; line-height: %(lh)s }
.quote.big { font-size: 20pt } .qsrc { color: #888; margin-top: 4mm; font-size: 9pt }
.dots { position: absolute; inset: 30mm 12mm 14mm; background-image: radial-gradient(#bbb 0.35mm, transparent 0.4mm); background-size: 5mm 5mm }
.gridp { position: absolute; inset: 30mm 12mm 14mm; background-image: linear-gradient(#e2dad1 0.2mm, transparent 0.2mm), linear-gradient(90deg, #e2dad1 0.2mm, transparent 0.2mm); background-size: 5mm 5mm }
.ck { display: flex; align-items: center; gap: 3mm; height: %(lg)s; border-bottom: 0.25mm solid #e0d8cf }
.box { width: 4mm; height: 4mm; border: 0.35mm solid %(primary)s; border-radius: 0.8mm; flex: none } .ckt { font-size: 10pt }
table.ht { width: 100%%; border-collapse: collapse; font-size: 6.5pt; table-layout: fixed }
.ht th, .ht td { border: 0.2mm solid #d5ccc2; height: 7mm; text-align: center }
.ht .hn { width: 26%%; text-align: start; padding: 0 1.5mm; font-size: 8pt } .ht th { color: %(primary)s }
.wk { display: grid; grid-template-columns: 1fr 1fr; gap: 3mm } .wd { border: 0.3mm solid #e0d8cf; border-radius: 2mm; padding: 2mm 3mm }
.wd .ln { height: 6mm } .wdl { color: %(primary)s; font-weight: 700; font-size: 10pt }
.mg { display: grid; grid-template-columns: repeat(7, 1fr); border-top: 0.3mm solid #d5ccc2; border-inline-start: 0.3mm solid #d5ccc2 }
.mh { font-size: 7.5pt; text-align: center; color: %(primary)s; padding: 1mm 0; border-inline-end: 0.3mm solid #d5ccc2; border-bottom: 0.3mm solid #d5ccc2 }
.mc { height: %(mch)s; border-inline-end: 0.3mm solid #d5ccc2; border-bottom: 0.3mm solid #d5ccc2; padding: 1mm; font-size: 8pt; color: #888 }
.two { display: grid; grid-template-columns: 1.15fr 1fr; gap: 5mm } .hr { height: 7.2mm; border-bottom: 0.25mm solid #e0d8cf; font-size: 8pt; color: #999; padding-top: 1mm }
.water { font-size: 16pt; color: %(accent)s; letter-spacing: 2mm } .g { display: flex; gap: 2mm } .g > div { flex: 1 }
.photo { height: %(photoh)s; border: 0.4mm dashed %(accent)s; border-radius: 3mm; margin: 3mm 0 1mm; display: flex; align-items: center; justify-content: center; color: %(accent)s; font-size: 10pt }
svg.trace { width: 100%%; height: 17mm; display: block } .trace text { font: 52px 'Andika', 'Comic Sans MS', sans-serif; fill: none; stroke: #9a9a9a; stroke-width: 1.4; stroke-dasharray: 5 4; letter-spacing: 6px }
.trace .base { stroke: #cfc6bd; stroke-width: 1.2 } .trace .l { stroke-dasharray: 6 6 }
.mgrid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6mm 4mm; margin-top: 6mm; direction: ltr }
.mp { display: flex; flex-direction: column; align-items: flex-end; font: 600 16pt 'Andika', sans-serif; padding-inline-end: 6mm }
.mpl { width: 22mm; border-top: 0.5mm solid #333; height: 9mm; margin-top: 1mm }
table.ws { margin: 4mm auto; border-collapse: collapse; direction: ltr } .ws td { width: 9mm; height: 9mm; text-align: center; font: 600 13pt 'Andika', sans-serif; border: 0.2mm solid #eee }
.wl { display: flex; flex-wrap: wrap; gap: 2mm 6mm; font: 600 10pt sans-serif; direction: ltr } .fb { font-size: 11pt; line-height: 2.4; border-bottom: 0.25mm solid #eee }
.fcg { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border: 0.3mm dashed #aaa } .fc { height: %(fch)s; border: 0.3mm dashed #aaa; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 3mm }
.fcf { font: 700 18pt %(hfont)s; color: %(primary)s } .fcb { font-size: 10pt; color: #666; margin-top: 2mm }
.ak { columns: 3; font-size: 9pt; line-height: 1.8; direction: ltr }
svg.color { width: 100%%; height: 100%%; display: block } .color .bubble { font: 900 380px 'Fredoka', 'Arial Black', sans-serif; fill: none; stroke: #111; stroke-width: 4 } .color .bubble.small { font-size: 110px; stroke-width: 3 }
.cpage { padding: 10mm !important } .cpage::before { display: none }
"""

FONTS = ("https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;600;700"
         "&family=Noto+Nastaliq+Urdu:wght@400;700&family=Amiri:wght@400;700&family=Andika&family=Fredoka:wght@700&display=swap")


def build_html(spec):
    lang = spec.get("language", "en")
    rtl = lang in ("ur", "ar")
    size = SIZES.get(str(spec.get("size", "A4")).upper(), SIZES["A4"])
    small = str(spec.get("size", "A4")).upper() == "A5"
    colors = {"primary": "#8C2F45", "accent": "#B08A45", "paper": "#FFFDF9"}
    colors.update(spec.get("colors") or {})
    vals = {
        "w": size[0], "h": size[1], "pad": "14mm 13mm 16mm" if small else "18mm 17mm 20mm",
        "font": "'Noto Nastaliq Urdu', 'Amiri', serif" if lang == "ur" else "'Amiri', serif" if lang == "ar" else "'Inter', sans-serif",
        "hfont": "'Noto Nastaliq Urdu', serif" if lang == "ur" else "'Amiri', serif" if lang == "ar" else "'Playfair Display', serif",
        "h1": "24pt" if small else "32pt", "h2": "15pt" if small else "18pt",
        "lh": "2.1" if lang == "ur" else "1.4", "lg": "8mm" if small else "9mm",
        "mch": "18mm" if small else "28mm", "photoh": "60mm" if small else "85mm", "fch": "40mm" if small else "58mm",
        **colors,
    }
    body = []
    n = 0
    for p in spec.get("pages", []):
        reps = max(1, min(int(p.get("repeat", 1) or 1), 120))
        for i in range(reps):
            page = dict(p)
            if "seed" in page or page.get("type", "").startswith("coloring"):
                page["seed"] = int(page.get("seed", 1)) + i * 17
            builder = pages.BUILDERS.get(page.get("type", "lined"), pages.lined)
            inner = builder(spec, page)
            n += 1
            cls = "page cpage" if page.get("type", "").startswith("coloring") else "page"
            pn = "" if page.get("type") in ("cover",) else f'<div class="pn">{n}</div>'
            body.append(f'<div class="{cls}">{inner}{pn}</div>')
            if page.get("type") == "math" and page.get("answer_key") and i == reps - 1:
                n += 1
                body.append(f'<div class="page">{pages.answer_key(spec, {"answers": page.get("_answers", [])})}</div>')
    return (f'<!doctype html><html lang="{lang}" dir="{"rtl" if rtl else "ltr"}"><head><meta charset="utf-8">'
            f'<link rel="stylesheet" href="{FONTS}"><style>{CSS % vals}</style></head><body>{"".join(body)}</body></html>'), n


def slug(text):
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return s[:60] or f"product_{int(time.time())}"


def build_pdf(spec, out_name=None):
    """Write <name>.pdf, <name>_cover.jpg and <name>.json into data/products. Returns their paths."""
    from playwright.sync_api import sync_playwright

    html, count = build_html(spec)
    name = out_name or slug(spec.get("title_en") or spec.get("title", "product"))
    out_dir = config.PRODUCTS_DIR
    pdf_path, jpg_path, json_path = out_dir / f"{name}.pdf", out_dir / f"{name}_cover.jpg", out_dir / f"{name}.json"
    html_path = out_dir / f"{name}.html"
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    size = SIZES.get(str(spec.get("size", "A4")).upper(), SIZES["A4"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 1270})
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.pdf(path=str(pdf_path), width=size[0], height=size[1], print_background=True)
        page.locator(".page").first.screenshot(path=str(jpg_path), type="jpeg", quality=90)
        browser.close()
    html_path.unlink(missing_ok=True)
    return {"pdf": str(pdf_path), "cover_image": str(jpg_path), "spec": str(json_path), "pages": count}
