"""Page builders for printable products. Each returns the inner HTML of one page.

A product "spec" (written by the AI, or by hand) is JSON like:
{
  "title": "Daily Planner", "subtitle": "...", "brand": "My Store",
  "language": "en" | "ur" | "ar", "size": "A4" | "A5" | "Letter",
  "colors": {"primary": "#8C2F45", "accent": "#B08A45", "paper": "#FFFDF9"},
  "pages": [ {"type": "cover"}, {"type": "daily", "repeat": 7}, ... ]
}
"""
import calendar
import html
import math
import random

E = html.escape

LABELS = {
    "en": {"date": "Date", "notes": "Notes", "todo": "To do", "priorities": "Top 3 priorities",
           "schedule": "Schedule", "water": "Water", "grateful": "I am grateful for",
           "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
           "dshort": ["M", "T", "W", "T", "F", "S", "S"], "habit": "Habit", "week": "Week of",
           "name": "Name", "score": "Score", "words": "Find these words", "affirm": "Today's affirmation",
           "caption": "About this photo", "answers": "Answer key", "month": "Month"},
    "ur": {"date": "تاریخ", "notes": "نوٹس", "todo": "کرنے کے کام", "priorities": "آج کی تین ترجیحات",
           "schedule": "شیڈول", "water": "پانی", "grateful": "میں ان باتوں کے لیے شکر گزار ہوں",
           "days": ["پیر", "منگل", "بدھ", "جمعرات", "جمعہ", "ہفتہ", "اتوار"],
           "dshort": ["پ", "م", "ب", "ج", "ج", "ہ", "ا"], "habit": "عادت", "week": "ہفتہ",
           "name": "نام", "score": "نمبر", "words": "یہ الفاظ تلاش کریں", "affirm": "آج کی مثبت بات",
           "caption": "اس تصویر کے بارے میں", "answers": "جوابات", "month": "مہینہ"},
}
LABELS["ar"] = LABELS["ur"]


def L(spec, key):
    return LABELS.get(spec.get("language", "en"), LABELS["en"])[key]


def lines(n, gap=None):
    style = f' style="height:{gap}mm"' if gap else ""
    return "".join(f'<div class="ln"{style}></div>' for _ in range(n))


def header(title, sub=""):
    s = f'<div class="ph"><h2>{E(title)}</h2>'
    if sub:
        s += f'<div class="sub">{E(sub)}</div>'
    return s + "</div>"


# ---------------- planner / journal pages ----------------
def cover(spec, p):
    return f'''<div class="cover"><div class="frame"></div>
    <div class="ctop">{E(p.get("kicker", spec.get("kicker", "")))}</div>
    <h1>{E(p.get("title", spec.get("title", "")))}</h1>
    <div class="csub">{E(p.get("subtitle", spec.get("subtitle", "")))}</div>
    <div class="orn">❦</div>
    <div class="cname">{E(L(spec, "name"))}: ____________________</div>
    <div class="cbrand">{E(spec.get("brand", ""))}</div></div>'''


def section(spec, p):
    q = f'<div class="quote">{E(p["quote"])}</div>' if p.get("quote") else ""
    return f'''<div class="section"><div class="snum">{E(p.get("kicker", ""))}</div>
    <h1>{E(p.get("title", ""))}</h1><div class="csub">{E(p.get("subtitle", ""))}</div>{q}</div>'''


def lined(spec, p):
    top = f'<div class="prompt">{E(p["prompt"])}</div>' if p.get("prompt") else ""
    return header(p.get("title", L(spec, "notes")), p.get("subtitle", "")) + top + lines(p.get("lines", 22 if top else 24))


def prompts(spec, p):
    qs = p.get("questions", [])
    per = max(1, int(p.get("lines_each", 5)))
    body = "".join(f'<div class="q"><div class="prompt">{E(q)}</div>{lines(per)}</div>' for q in qs)
    return header(p.get("title", ""), p.get("subtitle", "")) + body


def dotgrid(spec, p):
    return header(p.get("title", L(spec, "notes"))) + '<div class="dots"></div>'


def grid(spec, p):
    return header(p.get("title", L(spec, "notes"))) + '<div class="gridp"></div>'


def checklist(spec, p):
    items = p.get("items") or [""] * int(p.get("rows", 18))
    rows = "".join(f'<div class="ck"><span class="box"></span><span class="ckt">{E(i)}</span></div>' for i in items)
    return header(p.get("title", L(spec, "todo")), p.get("subtitle", "")) + rows


def habit_tracker(spec, p):
    days = int(p.get("days", 31))
    habits = p.get("habits") or [""] * int(p.get("rows", 10))
    head = f'<th class="hn">{E(L(spec, "habit"))}</th>' + "".join(f"<th>{d}</th>" for d in range(1, days + 1))
    body = "".join(f'<tr><td class="hn">{E(h)}</td>' + "<td></td>" * days + "</tr>" for h in habits)
    return header(p.get("title", "Habit Tracker"), p.get("subtitle", f'{L(spec, "month")}: ________')) + \
        f'<table class="ht">{head}{body}</table>'


def weekly(spec, p):
    boxes = "".join(f'<div class="wd"><div class="wdl">{E(d)}</div>{lines(5)}</div>' for d in L(spec, "days"))
    boxes += f'<div class="wd"><div class="wdl">{E(L(spec, "notes"))}</div>{lines(5)}</div>'
    return header(p.get("title", "Weekly Planner"), f'{L(spec, "week")}: ____________') + f'<div class="wk">{boxes}</div>'


def monthly(spec, p):
    year, month = p.get("year"), p.get("month")
    cells = []
    if year and month:
        cal = calendar.Calendar(firstweekday=0).monthdayscalendar(int(year), int(month))
        title = p.get("title") or f"{calendar.month_name[int(month)]} {year}"
        for week in cal:
            cells += [str(d) if d else "" for d in week]
    else:
        title = p.get("title", "Monthly Planner")
        cells = [""] * 35
    head = "".join(f'<div class="mh">{E(d)}</div>' for d in L(spec, "days"))
    body = "".join(f'<div class="mc"><span>{c}</span></div>' for c in cells)
    return header(title, "" if (year and month) else f'{L(spec, "month")}: ____________') + \
        f'<div class="mg">{head}{body}</div>' + f'<div class="prompt" style="margin-top:4mm">{E(L(spec, "notes"))}</div>' + lines(3)


def daily(spec, p):
    pr = "".join(f'<div class="ck"><span class="box"></span><span class="ckt"></span></div>' for _ in range(3))
    sched = "".join(f'<div class="hr"><span>{h:02d}:00</span></div>' for h in range(int(p.get("start", 6)), int(p.get("end", 21)) + 1))
    todo = "".join('<div class="ck"><span class="box"></span><span class="ckt"></span></div>' for _ in range(8))
    water = "".join('<span class="drop">○</span>' for _ in range(8))
    return header(p.get("title", "Daily Planner"), f'{L(spec, "date")}: ____________') + f'''
    <div class="two"><div><div class="lab">{E(L(spec, "priorities"))}</div>{pr}
      <div class="lab">{E(L(spec, "todo"))}</div>{todo}
      <div class="lab">{E(L(spec, "water"))}</div><div class="water">{water}</div>
      <div class="lab">{E(L(spec, "grateful"))}</div>{lines(3)}</div>
    <div><div class="lab">{E(L(spec, "schedule"))}</div>{sched}</div></div>'''


def gratitude(spec, p):
    three = "".join(f'<div class="g"><b>{i}.</b>{lines(2)}</div>' for i in range(1, 4))
    return header(p.get("title", "Gratitude"), f'{L(spec, "date")}: ____________') + \
        f'<div class="lab">{E(L(spec, "grateful"))}</div>{three}<div class="lab">{E(L(spec, "affirm"))}</div>{lines(3)}' + \
        f'<div class="lab">{E(L(spec, "notes"))}</div>{lines(8)}'


def photo(spec, p):
    n = int(p.get("boxes", 2))
    boxes = "".join(f'<div class="photo"><span>{E(p.get("label", "Photo"))}</span></div>{lines(2)}' for _ in range(n))
    return header(p.get("title", ""), p.get("subtitle", "")) + boxes


def quote(spec, p):
    src = f'<div class="qsrc">{E(p.get("source", ""))}</div>' if p.get("source") else ""
    return f'<div class="section"><div class="quote big">{E(p.get("text", ""))}</div>{src}</div>'


def notes(spec, p):
    return lined(spec, {**p, "title": p.get("title", L(spec, "notes"))})


# ---------------- worksheets ----------------
def tracing(spec, p):
    text = p.get("text", "A B C")
    rows = int(p.get("rows", 8))
    one = (f'<svg class="trace" viewBox="0 0 600 70" preserveAspectRatio="xMinYMid meet">'
           f'<line x1="0" y1="58" x2="600" y2="58" class="base"/><line x1="0" y1="14" x2="600" y2="14" class="base l"/>'
           f'<line x1="0" y1="36" x2="600" y2="36" class="base l"/>'
           f'<text x="4" y="56">{E(text)}</text></svg>')
    return header(p.get("title", "Tracing"), f'{L(spec, "name")}: ____________') + one * rows


def math_sheet(spec, p):
    op = p.get("op", "+")
    n = int(p.get("count", 20))
    lo, hi = int(p.get("min", 1)), int(p.get("max", 10))
    rnd = random.Random(p.get("seed", 7))
    probs, answers = [], []
    for _ in range(n):
        a, b = rnd.randint(lo, hi), rnd.randint(lo, hi)
        if op == "-" and b > a:
            a, b = b, a
        sym = {"+": "+", "-": "−", "x": "×", "*": "×"}.get(op, "+")
        res = a + b if op == "+" else a - b if op == "-" else a * b
        probs.append(f'<div class="mp"><span>{a}</span><span>{sym} {b}</span><span class="mpl"></span></div>')
        answers.append(f"{a} {sym} {b} = {res}")
    p["_answers"] = answers
    return header(p.get("title", "Maths Practice"), f'{L(spec, "name")}: ________   {L(spec, "score")}: ____ / {n}') + \
        f'<div class="mgrid">{"".join(probs)}</div>'


def wordsearch(spec, p):
    words = [w.upper().replace(" ", "") for w in p.get("words", ["APPLE", "MOON", "STAR"])][:15]
    size = int(p.get("size", 12))
    size = max(size, max(len(w) for w in words) + 1)
    rnd = random.Random(p.get("seed", 3))
    g = [["" for _ in range(size)] for _ in range(size)]
    dirs = [(0, 1), (1, 0), (1, 1), (-1, 1)]
    for w in words:
        for _ in range(300):
            dr, dc = rnd.choice(dirs)
            r, c = rnd.randrange(size), rnd.randrange(size)
            cells = [(r + dr * i, c + dc * i) for i in range(len(w))]
            if all(0 <= a < size and 0 <= b < size and g[a][b] in ("", w[i]) for i, (a, b) in enumerate(cells)):
                for i, (a, b) in enumerate(cells):
                    g[a][b] = w[i]
                break
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    rows = "".join("<tr>" + "".join(f"<td>{ch or rnd.choice(letters)}</td>" for ch in row) + "</tr>" for row in g)
    wl = "".join(f"<span>{E(w)}</span>" for w in words)
    return header(p.get("title", "Word Search"), f'{L(spec, "name")}: ____________') + \
        f'<table class="ws">{rows}</table><div class="lab">{E(L(spec, "words"))}</div><div class="wl">{wl}</div>'


def fill_blanks(spec, p):
    items = "".join(f'<div class="fb"><b>{i}.</b> {E(s)}</div>' for i, s in enumerate(p.get("sentences", []), 1))
    return header(p.get("title", "Fill in the blanks"), f'{L(spec, "name")}: ____________') + items


def flashcards(spec, p):
    cards = p.get("cards", [])[:8]
    cells = "".join(f'<div class="fc"><div class="fcf">{E(c.get("front", ""))}</div><div class="fcb">{E(c.get("back", ""))}</div></div>' for c in cards)
    return header(p.get("title", "Flashcards"), "✂ cut along the lines") + f'<div class="fcg">{cells}</div>'


def answer_key(spec, p):
    items = "".join(f"<div>{E(a)}</div>" for a in p.get("answers", []))
    return header(L(spec, "answers")) + f'<div class="ak">{items}</div>'


# ---------------- coloring pages (pure line art, generated by code) ----------------
def _petal(cx, cy, r1, r2, ang, width):
    a = math.radians(ang)
    w = math.radians(width)
    x1, y1 = cx + r1 * math.cos(a - w), cy + r1 * math.sin(a - w)
    x2, y2 = cx + r1 * math.cos(a + w), cy + r1 * math.sin(a + w)
    tx, ty = cx + r2 * math.cos(a), cy + r2 * math.sin(a)
    c1x, c1y = cx + (r2 * .85) * math.cos(a - w * 1.6), cy + (r2 * .85) * math.sin(a - w * 1.6)
    c2x, c2y = cx + (r2 * .85) * math.cos(a + w * 1.6), cy + (r2 * .85) * math.sin(a + w * 1.6)
    return f'<path d="M{x1:.1f},{y1:.1f} Q{c1x:.1f},{c1y:.1f} {tx:.1f},{ty:.1f} Q{c2x:.1f},{c2y:.1f} {x2:.1f},{y2:.1f}"/>'


def coloring_mandala(spec, p):
    rnd = random.Random(p.get("seed", 1))
    cx = cy = 300
    parts = [f'<circle cx="{cx}" cy="{cy}" r="18"/>']
    r = 18
    while r < 250:
        n = rnd.choice([8, 12, 16, 24])
        depth = min(rnd.randint(28, 46), 288 - r)
        style = rnd.choice(["petal", "petal", "circle", "arch"])
        for i in range(n):
            ang = 360 / n * i + (180 / n if rnd.random() < .5 else 0)
            if style == "petal":
                parts.append(_petal(cx, cy, r, r + depth, ang, 180 / n * .9))
                parts.append(_petal(cx, cy, r + 4, r + depth * .62, ang, 180 / n * .45))
            elif style == "circle":
                a = math.radians(ang)
                rr = min(depth / 2, math.pi * (r + depth / 2) / n * .85)
                parts.append(f'<circle cx="{cx + (r + depth / 2) * math.cos(a):.1f}" cy="{cy + (r + depth / 2) * math.sin(a):.1f}" r="{rr:.1f}"/>')
            else:
                a1, a2 = math.radians(360 / n * i), math.radians(360 / n * (i + 1))
                x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
                x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
                parts.append(f'<path d="M{x1:.1f},{y1:.1f} A{depth},{depth} 0 0 1 {x2:.1f},{y2:.1f}"/>')
        r += depth
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}"/>')
        r += 4
    svg = f'<svg class="color" viewBox="0 0 600 600"><g fill="none" stroke="#111" stroke-width="2.2">{"".join(parts)}</g></svg>'
    return header(p.get("title", "")) + svg if p.get("title") else svg


def coloring_pattern(spec, p):
    rnd = random.Random(p.get("seed", 2))
    kind = p.get("pattern") or rnd.choice(["scales", "flowers", "diamonds", "hearts"])
    parts = []
    s = 60
    for row in range(-1, 12):
        for col in range(-1, 11):
            x = col * s + (s / 2 if row % 2 and kind != "diamonds" else 0)
            y = row * s * (0.75 if kind == "scales" else 1)
            if kind == "scales":
                parts.append(f'<path d="M{x},{y + s / 2} A{s / 2},{s / 2} 0 0 0 {x + s},{y + s / 2}"/>')
                parts.append(f'<path d="M{x + 12},{y + s / 2} A{s / 2 - 12},{s / 2 - 12} 0 0 0 {x + s - 12},{y + s / 2}"/>')
            elif kind == "flowers":
                cx, cy = x + s / 2, y + s / 2
                for k in range(6):
                    parts.append(_petal(cx, cy, 5, 26, k * 60, 22))
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="5"/>')
            elif kind == "diamonds":
                parts.append(f'<path d="M{x + s / 2},{y} L{x + s},{y + s / 2} L{x + s / 2},{y + s} L{x},{y + s / 2} Z"/>')
                parts.append(f'<path d="M{x + s / 2},{y + 14} L{x + s - 14},{y + s / 2} L{x + s / 2},{y + s - 14} L{x + 14},{y + s / 2} Z"/>')
            else:
                cx, cy = x + s / 2, y + s / 2
                parts.append(f'<path d="M{cx},{cy + 16} C{cx - 30},{cy - 4} {cx - 12},{cy - 24} {cx},{cy - 8} C{cx + 12},{cy - 24} {cx + 30},{cy - 4} {cx},{cy + 16} Z"/>')
    svg = (f'<svg class="color" viewBox="0 0 600 800"><defs><clipPath id="cp{kind}"><rect x="10" y="10" width="580" height="780" rx="24"/></clipPath></defs>'
           f'<g clip-path="url(#cp{kind})" fill="none" stroke="#111" stroke-width="2.2">{"".join(parts)}</g>'
           f'<rect x="10" y="10" width="580" height="780" rx="24" fill="none" stroke="#111" stroke-width="3"/></svg>')
    return svg


def coloring_letters(spec, p):
    text = p.get("text", "A")
    return (f'<svg class="color" viewBox="0 0 600 800"><text x="300" y="470" text-anchor="middle" class="bubble">{E(text)}</text>'
            f'<text x="300" y="700" text-anchor="middle" class="bubble small">{E(p.get("word", ""))}</text></svg>')


BUILDERS = {
    "cover": cover, "section": section, "lined": lined, "notes": notes, "prompts": prompts,
    "dotgrid": dotgrid, "grid": grid, "checklist": checklist, "habit_tracker": habit_tracker,
    "weekly": weekly, "monthly": monthly, "daily": daily, "gratitude": gratitude, "photo": photo,
    "quote": quote, "tracing": tracing, "math": math_sheet, "wordsearch": wordsearch,
    "fill_blanks": fill_blanks, "flashcards": flashcards, "answer_key": answer_key,
    "coloring_mandala": coloring_mandala, "coloring_pattern": coloring_pattern,
    "coloring_letters": coloring_letters,
}

PAGE_TYPES_HELP = """Page types and their options:
cover {title, subtitle, kicker} | section {kicker, title, subtitle, quote} | quote {text, source}
lined {title, prompt, lines} | notes {title} | prompts {title, questions:[...], lines_each}
dotgrid {title} | grid {title} | checklist {title, items:[...] or rows}
habit_tracker {title, habits:[...], days} | daily {title, start, end} | weekly {title}
monthly {title, year, month (both optional)} | gratitude {title} | photo {title, boxes, label}
tracing {title, text, rows} | math {title, op:'+','-','x', count, min, max, answer_key:true}
wordsearch {title, words:[...], size} | fill_blanks {title, sentences:[...]} | flashcards {title, cards:[{front, back}]}
coloring_mandala {seed} | coloring_pattern {pattern:'scales'|'flowers'|'diamonds'|'hearts', seed} | coloring_letters {text, word}
Any page can have "repeat": N to repeat it (e.g. 30 daily pages; coloring pages get a new seed each time)."""
