#!/usr/bin/env python3
"""
Draws the share cards (1200x630 PNG snapshots of each meter) and the small
share pages whose Open Graph tags make X, Bluesky, Facebook, LinkedIn, Reddit,
WhatsApp etc. show the snapshot as the link preview.

Called by update_doom.py after each reading. Needs Pillow.

Writes:
  data/cards/main-<ts>.png, data/cards/ai-<ts>.png   (unique per reading, beats preview caches)
  data/cards/main-latest.png, data/cards/ai-latest.png (stable, used by the homepage preview)
  share/main.html, share/ai.html                       (preview pages that bounce visitors to the site)
and adds "card" / "share" paths to the meter dicts in doom.json.
"""
import datetime as dt
import glob
import html
import math
import os
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "assets", "fonts")
CARDS = os.path.join(ROOT, "data", "cards")
SHARE = os.path.join(ROOT, "share")
TZ = os.environ.get("DOOM_TZ", "America/Phoenix")

S = 2                       # supersampling factor for smooth edges
W, H = 1200, 630

INK, PAPER, MUTED, HAZARD = "#16130f", "#f2e9d6", "#6b6152", "#ec7a1c"
BANDS = ["#5e9e6b", "#e2b829", "#ec7a1c", "#d6402a", "#7a1f5c"]

METERS = {
    "main": {
        "title": [("THE SKY IS ", None), ("FALLING", HAZARD), (" INDEX", None)],
        "plain_title": "Sky Is Falling Index",
        "dark": False,
        "anchor": "",
        "levels": ["Mild Concern", "Clutching Pearls", "Stockpiling Beans",
                   "Building a Bunker", "Full Chicken Little"],
    },
    "ai": {
        "title": [("ROBOT ", None), ("UPRISING", HAZARD), (" RISK", None)],
        "plain_title": "Robot Uprising Risk",
        "dark": True,
        "anchor": "#robot-uprising",
        "levels": ["Mild Robot Concern", "Side-Eyeing the Toaster",
                   "Saying Please to the Chatbot", "Unplugging Everything",
                   "Full Robot Uprising"],
    },
}


def site_url():
    url = os.environ.get("SITE_URL")
    if not url and os.environ.get("GITHUB_REPOSITORY"):
        owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
        url = f"https://{owner.lower()}.github.io/{repo}/"
    url = url or ""
    return url if not url or url.endswith("/") else url + "/"


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size * S)


def level_index(score):
    return min(4, max(0, int(score) // 20))


def wrap(draw, text, fnt, max_w):
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= max_w * S:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def arc_points(cx, cy, r, d0, d1, steps=40):
    pts = []
    for i in range(steps + 1):
        deg = d0 + (d1 - d0) * i / steps
        a = math.radians(180 - deg)
        pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
    return pts


def draw_gauge(d, cx, cy, r, score, dark):
    cx, cy, r = cx * S, cy * S, r * S
    band = 78 * S
    outline = INK
    for i, col in enumerate(BANDS):
        outer = arc_points(cx, cy, r, i * 36, (i + 1) * 36)
        inner = arc_points(cx, cy, r - band, (i + 1) * 36, i * 36)
        poly = outer + inner
        d.polygon(poly, fill=col)
        d.line(poly + [poly[0]], fill=outline, width=5 * S, joint="curve")
    tick = PAPER if dark else INK
    for v in range(0, 101, 10):
        a = math.radians(180 - v * 1.8)
        r1, r2 = r + 8 * S, r + (18 if v % 50 else 30) * S
        d.line([(cx + r1 * math.cos(a), cy - r1 * math.sin(a)),
                (cx + r2 * math.cos(a), cy - r2 * math.sin(a))],
               fill=tick, width=(7 if v % 50 == 0 else 4) * S)
    needle = PAPER if dark else INK
    a = math.radians(180 - max(0, min(100, score)) * 1.8)
    tip = (cx + (r - 22 * S) * math.cos(a), cy - (r - 22 * S) * math.sin(a))
    perp = a + math.pi / 2
    half = 11 * S
    base1 = (cx + half * math.cos(perp), cy - half * math.sin(perp))
    base2 = (cx - half * math.cos(perp), cy + half * math.sin(perp))
    d.polygon([base1, tip, base2], fill=needle)
    hub = 30 * S
    d.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], fill=needle)
    dot = 11 * S
    d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=HAZARD)


def render(kind, meter, when_label, url_label):
    cfg = METERS[kind]
    dark = cfg["dark"]
    bg, fg, muted = (INK, PAPER, "#b9ad97") if dark else (PAPER, INK, MUTED)
    img = Image.new("RGB", (W * S, H * S), bg)
    d = ImageDraw.Draw(img)

    # top broadcast strip
    strip_bg, strip_fg = (PAPER, INK) if dark else (INK, PAPER)
    d.rectangle([0, 0, W * S, 50 * S], fill=strip_bg)
    d.rectangle([0, 50 * S, W * S, 57 * S], fill=HAZARD)
    mono = font("JetBrainsMono-Bold.ttf", 19)
    d.text((60 * S, 25 * S), "EMERGENCY BROADCAST SYSTEM OF THE INTERNET", font=mono, fill=strip_fg, anchor="lm")
    d.text(((W - 60) * S, 25 * S), "THIS IS NOT A DRILL (IT IS A DRILL)", font=mono, fill=HAZARD if not dark else "#b04a12", anchor="rm")

    # title
    tf = font("ArchivoBlack.ttf", 66)
    x = 60 * S
    for text, col in cfg["title"]:
        d.text((x, 92 * S), text, font=tf, fill=col or fg, anchor="la")
        x += d.textlength(text, font=tf)

    # gauge
    score = int(meter.get("score", 0))
    draw_gauge(d, 330, 588, 262, score, dark)

    # right column
    rx = 650
    big = font("ArchivoBlack.ttf", 172)
    d.text((rx * S, 196 * S), str(score), font=big, fill=fg, anchor="la")
    sw = d.textlength(str(score), font=big)
    d.text((rx * S + sw + 10 * S, 330 * S), "/100", font=font("Archivo-SemiBold.ttf", 46), fill=muted, anchor="ls")

    li = level_index(score)
    level = cfg["levels"][li].upper()
    lf = font("Archivo-ExtraBold.ttf", 34)
    pad_x, pill_y, pill_h = 18 * S, 372 * S, 58 * S
    tw = d.textlength(level, font=lf)
    max_w = (W - rx - 50) * S
    while tw + 2 * pad_x > max_w and lf.size > 20 * S:
        lf = ImageFont.truetype(lf.path, lf.size - 2 * S)
        tw = d.textlength(level, font=lf)
    d.rectangle([rx * S, pill_y, rx * S + tw + 2 * pad_x, pill_y + pill_h], fill=BANDS[li])
    d.text((rx * S + pad_x, pill_y + pill_h / 2), level, font=lf,
           fill=INK if li == 1 else "#ffffff", anchor="lm")

    ff = font("Archivo-SemiBold.ttf", 27)
    lines = wrap(d, meter.get("forecast", ""), ff, W - rx - 60)
    if len(lines) > 3:
        last = lines[2]
        while last and d.textlength(last + "…", font=ff) > (W - rx - 60) * S:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines = lines[:2] + [last.rstrip(",;:") + "…"]
    y = 452 * S
    for ln in lines:
        d.text((rx * S, y), ln, font=ff, fill=fg, anchor="la")
        y += 34 * S

    small = font("JetBrainsMono-Bold.ttf", 17)
    d.text((rx * S, 580 * S), f"Reading of {when_label}", font=small, fill=muted, anchor="ls")
    d.text((rx * S, 606 * S), url_label, font=small, fill=HAZARD, anchor="ls")

    return img.resize((W, H), Image.LANCZOS)


def share_page(kind, meter, image_url, page_url, site):
    cfg = METERS[kind]
    li = level_index(meter.get("score", 0))
    title = f"{cfg['plain_title']}: {meter.get('score', 0)}/100, {cfg['levels'][li]}"
    desc = meter.get("forecast", "") + " The internet's official-ish panic gauge, updated hourly."
    target = "../" + cfg["anchor"]
    e = lambda s: html.escape(s, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{e(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="The Sky Is Falling Index">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{e(image_url)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{e(title)}">
<meta property="og:url" content="{e(page_url)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(image_url)}">
<meta http-equiv="refresh" content="0; url={e(target)}">
<link rel="canonical" href="{e(site + cfg['anchor'])}">
</head>
<body style="font-family:system-ui,sans-serif;background:#f2e9d6;color:#16130f;padding:40px">
<p>Taking you to <a href="{e(target)}">the {e(cfg['plain_title'])}</a>…</p>
<script>location.replace({target!r});</script>
</body>
</html>
"""


def build(data):
    """Render cards + share pages for every meter present in `data` (mutates it)."""
    site = site_url()
    os.makedirs(CARDS, exist_ok=True)
    os.makedirs(SHARE, exist_ok=True)
    url_label = (site.replace("https://", "").rstrip("/") or "the sky is falling index")
    for kind in ("main", "ai"):
        meter = data if kind == "main" else data.get("ai")
        if not meter or "score" not in meter:
            continue
        when = dt.datetime.fromisoformat(meter["updated"]).astimezone(ZoneInfo(TZ))
        when_label = when.strftime("%b %-d, %Y  %-I:%M %p ") + when.tzname()
        stamp = when.strftime("%Y%m%d%H%M")
        img = render(kind, meter, when_label, url_label)

        for old in glob.glob(os.path.join(CARDS, f"{kind}-2*.png")):
            os.remove(old)
        name = f"{kind}-{stamp}.png"
        img.save(os.path.join(CARDS, name), optimize=True)
        img.save(os.path.join(CARDS, f"{kind}-latest.png"), optimize=True)

        meter["card"] = f"data/cards/{name}"
        meter["share"] = f"share/{kind}.html?r={stamp}"
        with open(os.path.join(SHARE, f"{kind}.html"), "w", encoding="utf-8") as f:
            f.write(share_page(kind, meter, site + meter["card"], site + f"share/{kind}.html", site))
    return data


if __name__ == "__main__":
    import json
    path = os.path.join(ROOT, "data", "doom.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    build(d)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print("cards written")
