#!/usr/bin/env python3
"""Build the static site for setimoandar.com into dist/.

Inputs: data/posts.json (from sync.py), data/episodes-extra.json (curated film
info + YouTube ids), src/ (css, js, svg). Needs Pillow for artwork and OG images.
"""
import datetime as dt
import html
import json
import os
import re
import shutil
import urllib.request
from html.parser import HTMLParser

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
CACHE = os.path.join(ROOT, ".cache")
FONTS = os.path.join(ROOT, "scripts", "fonts")
SITE = "https://setimoandar.com"
SUBSTACK = "https://7andar.substack.com"
EMAIL = "7andar.cast@gmail.com"

# (label, url, simple-icons slug, brand colour)
PLATFORMS = [
    ("Spotify", "https://open.spotify.com/show/1lexfzrdhYuEGJJW1KjGUw", "spotify", "#1ED760"),
    ("Apple Podcasts", "https://podcasts.apple.com/br/podcast/7-andar/id1630207506", "applepodcasts", "#A35BE6"),
    ("YouTube", "https://www.youtube.com/@7andar", "youtube", "#FF3B30"),
    ("YouTube Music", "https://music.youtube.com/playlist?list=PLxSC-1bD99WKefTZhHvCAvDL5cAvWXd5a", "youtubemusic", "#FF3B30"),
    ("Pocket Casts", "https://pca.st/v8s1xfvb", "pocketcasts", "#F43E37"),
    ("Substack", SUBSTACK, "substack", "#FF6719"),
]

MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]

PAPER = (255, 247, 242)
ESPRESSO = (32, 7, 4)
INK = (73, 28, 19)
RUST = (175, 77, 58)
AMBER = (244, 184, 96)

e = html.escape


# ---------------------------------------------------------------- helpers

def date_pt(d):
    return f"{d.day} de {MONTHS[d.month - 1]} de {d.year}"


def dur_label(sec):
    m = round(sec / 60)
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def fetch(url, dest):
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (setimoandar.com build)"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())
    return dest


def svg(name):
    return open(os.path.join(ROOT, "src", "img", f"{name}.svg")).read()


def inline_svg(name, cls, label=None):
    s = svg(name)
    attrs = f' class="{cls}"' + (f' role="img" aria-label="{e(label)}"' if label else ' aria-hidden="true"')
    return s.replace("<svg ", f"<svg{attrs} ", 1)


class Sanitizer(HTMLParser):
    """Keep reading text from Substack bodies; drop embeds, images and widgets."""
    KEEP = {"p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "b", "em", "i", "a", "blockquote", "br"}
    SKIP = {"figure", "picture", "script", "style", "form", "button", "svg", "iframe", "figcaption", "img", "video", "audio"}
    SKIP_CLASS = ("subscription-widget", "button-wrapper", "native-audio-embed", "captioned-image",
                  "youtube-wrap", "digest-post-embed", "embedded-post", "image-gallery", "footnote")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.stack = [], 0, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        skipping = tag in self.SKIP or (tag == "div" and any(c in (a.get("class") or "") for c in self.SKIP_CLASS))
        if self.skip or skipping:
            if tag not in ("br", "img"):
                self.skip += 1
            return
        if tag in self.KEEP:
            tag = {"b": "strong", "i": "em", "h2": "h3", "h4": "h3"}.get(tag, tag)
            if tag == "a":
                href = a.get("href") or ""
                if not href.startswith(("http://", "https://", "mailto:")) or "substack.com/subscribe" in href \
                        or "/subscribe?" in href or "action=share" in href:
                    self.stack.append(None)
                    return
                self.out.append(f'<a href="{e(href)}" rel="noopener" target="_blank">')
            elif tag == "br":
                self.out.append("<br>")
                return
            else:
                self.out.append(f"<{tag}>")
            self.stack.append(tag)
        else:
            self.stack.append(None)

    def handle_endtag(self, tag):
        if self.skip:
            if tag not in ("br", "img"):
                self.skip -= 1
            return
        if tag == "br" or not self.stack:
            return
        t = self.stack.pop()
        if t:
            self.out.append(f"</{t}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(e(data))


def clean_body(body_html):
    s = Sanitizer()
    s.feed(body_html or "")
    out = "".join(s.out)
    out = re.sub(r"<(p|h3|li|blockquote)>\s*(<br>\s*)*</\1>", "", out)
    out = re.sub(r"<p>[^<]*(Get full access|Obrigado por ler|Thanks for reading)[^<]*</p>", "", out, flags=re.I)
    return out.strip()


def is_logo_art(path):
    """Some episodes use the show logo as artwork; those get a designed card instead."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    corners = [im.getpixel((5, 5)), im.getpixel((w - 6, 5)), im.getpixel((5, h - 6)), im.getpixel((w - 6, h - 6))]
    return all(sum(abs(a - b) for a, b in zip(c, PAPER)) < 30 for c in corners)


# ---------------------------------------------------------------- data

def load_episodes():
    posts = json.load(open(os.path.join(ROOT, "data", "posts.json")))
    extra = json.load(open(os.path.join(ROOT, "data", "episodes-extra.json")))
    eps, reads = [], []
    for p in posts:
        d = dt.datetime.fromisoformat(p["post_date"].replace("Z", "+00:00"))
        if p["type"] != "podcast" or not p.get("podcast_url"):
            reads.append({"title": p["title"], "subtitle": p.get("subtitle") or "", "url": p["canonical_url"] or f"{SUBSTACK}/p/{p['slug']}",
                          "date": d, "img": p.get("cover_image"), "slug": p["slug"]})
            continue
        m = re.match(r"\W*(\d+)\s*\|\s*(.+)", p["title"])
        num, title = (int(m.group(1)), m.group(2).strip()) if m else (None, p["title"])
        x = extra.get(str(num), {})
        eps.append({
            "num": num, "slug": p["slug"], "title": title, "full_title": p["title"],
            "subtitle": (p.get("subtitle") or "").strip(), "date": d,
            "duration": p.get("podcast_duration") or 0, "audio": p["podcast_url"],
            "src_img": p.get("podcast_episode_image_url") or p.get("cover_image"),
            "notes": clean_body(p.get("body_html")), "substack": p["canonical_url"] or f"{SUBSTACK}/p/{p['slug']}",
            "film": x.get("film"), "original": x.get("original"), "year": x.get("year"),
            "director": x.get("director"), "youtube": x.get("youtube"),
        })
    eps.sort(key=lambda x: (x["num"] or 0, x["date"]), reverse=True)
    return eps, reads


# ---------------------------------------------------------------- images

def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def wrap(draw, text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def cat_png(size, color):
    """Rasterise the traced cat (with wordmark) for OG/touch icons."""
    import cairosvg  # build-time only
    s = svg("logo-cat").replace("currentColor", "#%02x%02x%02x" % color)
    out = os.path.join(CACHE, f"cat-{size}-{color}.png")
    cairosvg.svg2png(bytestring=s.encode(), write_to=out, output_height=size)
    return Image.open(out).convert("RGBA")


def to_srgb(im):
    """Convert embedded colour profiles (e.g. Display P3 from phones) to plain sRGB."""
    icc = im.info.get("icc_profile")
    if icc:
        import io
        from PIL import ImageCms
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            im = ImageCms.profileToProfile(im.convert("RGB"), src, ImageCms.createProfile("sRGB"), outputMode="RGB")
        except Exception:
            pass
    out = im.convert("RGB")
    out.info = {}
    return out


def build_read_images(reads):
    os.makedirs(os.path.join(DIST, "assets", "read"), exist_ok=True)
    for r in reads:
        src_url, r["img"] = r.get("img"), None
        if not src_url:
            continue
        ext = src_url.rsplit(".", 1)[-1].split("?")[0][:4]
        src = fetch(src_url, os.path.join(CACHE, "read", f"{r['slug']}.{ext}"))
        im = Image.open(src)
        im.seek(0)  # first frame of animated covers
        im = ImageOps.fit(to_srgb(im), (800, 450), Image.LANCZOS)
        im.save(os.path.join(DIST, "assets", "read", f"{r['slug']}.webp"), quality=80, method=6)
        r["img"] = f"/assets/read/{r['slug']}.webp"


def build_images(eps):
    os.makedirs(os.path.join(DIST, "assets", "ep"), exist_ok=True)
    os.makedirs(os.path.join(DIST, "assets", "og"), exist_ok=True)
    for ep in eps:
        ep["img"] = None
        if not ep["src_img"]:
            continue
        ext = ep["src_img"].rsplit(".", 1)[-1].split("?")[0][:4]
        src = fetch(ep["src_img"], os.path.join(CACHE, "art", f"{ep['slug']}.{ext}"))
        if is_logo_art(src):
            continue
        im = to_srgb(Image.open(src))
        # 3:2 crop, centred slightly above middle where faces usually sit
        im = ImageOps.fit(im, (1200, 800), Image.LANCZOS, centering=(0.5, 0.42))
        for w in (480, 960):
            im.resize((w, w * 2 // 3), Image.LANCZOS).save(
                os.path.join(DIST, "assets", "ep", f"{ep['slug']}-{w}.webp"), quality=80, method=6)
        ep["img"] = f"/assets/ep/{ep['slug']}"
        ep["_im"] = im

    big, mid, small = font("fraunces-800.ttf", 64), font("fraunces-600.ttf", 34), font("lora-italic.ttf", 30)
    num_font = font("fraunces-800.ttf", 120)
    cat = cat_png(330, PAPER)
    for ep in eps:
        og = Image.new("RGB", (1200, 630), ESPRESSO)
        d = ImageDraw.Draw(og)
        if ep.get("_im"):
            art = ImageOps.fit(ep["_im"], (560, 630), Image.LANCZOS, centering=(0.5, 0.4))
            og.paste(art, (640, 0))
            # soft fade from espresso into the still
            fade = Image.new("L", (160, 630))
            for x in range(160):
                ImageDraw.Draw(fade).line([(x, 0), (x, 630)], fill=int(255 * (1 - x / 159)))
            og.paste(Image.new("RGB", (160, 630), ESPRESSO), (640, 0), fade)
        else:
            og.paste(cat, (1200 - cat.width - 90, (630 - cat.height) // 2), cat)
        # elevator button with the floor number
        cx, cy, r = 130, 150, 70
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=AMBER, width=6)
        n = str(ep["num"])
        d.text((cx, cy + 4), n, font=num_font if len(n) == 1 else font("fraunces-800.ttf", 92), fill=AMBER, anchor="mm")
        y = 270
        for line in wrap(d, ep["title"], big, 560)[:3]:
            d.text((60, y), line, font=big, fill=PAPER)
            y += 74
        meta = ep["film"] and f"{ep['film']} ({ep['year']})"
        if meta:
            d.text((60, y + 16), meta, font=small, fill=(214, 196, 188))
        d.text((60, 560), "7° andar", font=mid, fill=RUST)
        og.save(os.path.join(DIST, "assets", "og", f"{ep['slug']}.jpg"), quality=86)
        ep["og"] = f"/assets/og/{ep['slug']}.jpg"

    # default OG + icons
    og = Image.new("RGB", (1200, 630), ESPRESSO)
    c = cat_png(470, PAPER)
    og.paste(c, ((1200 - c.width) // 2, (630 - c.height) // 2), c)
    og.save(os.path.join(DIST, "assets", "og", "default.jpg"), quality=88)
    icon = Image.new("RGB", (180, 180), ESPRESSO)
    c = cat_png(140, PAPER)
    icon.paste(c, ((180 - c.width) // 2, 20), c)
    icon.save(os.path.join(DIST, "apple-touch-icon.png"))
    for s in (192, 512):
        i = Image.new("RGB", (s, s), ESPRESSO)
        c = cat_png(int(s * 0.74), PAPER)
        i.paste(c, ((s - c.width) // 2, (s - c.height) // 2), c)
        i.save(os.path.join(DIST, "assets", f"icon-{s}.png"))


# ---------------------------------------------------------------- templates

ICONS = {
    "home": '<path d="M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z"/>',
    "list": '<path d="M5 6h14M5 12h14M5 18h9"/>',
    "listen": '<path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="3.5" y="14" width="4" height="6.5" rx="1.5"/><rect x="16.5" y="14" width="4" height="6.5" rx="1.5"/>',
    "about": '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5"/>',
    "play": '<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"/>',
    "pause": '<path d="M7.5 5h3v14h-3zM13.5 5h3v14h-3z" fill="currentColor" stroke="none"/>',
    "up": '<path d="M12 5l7 8H5z" fill="currentColor" stroke="none"/>',
    "out": '<path d="M14 5h5v5M19 5l-8 8M17 14v5H5V7h5"/>',
    "mail": '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="m4 7 8 6 8-6"/>',
}


def icon(name, cls="i"):
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def page(*, path, title, desc, body, active, og=None, floor="7", jsonld=None, extra_head=""):
    url = SITE + path
    og = SITE + (og or "/assets/og/default.jpg")
    nav = [("/", "Início", "home"), ("/episodios/", "Episódios", "list"), ("/#ouvir", "Ouvir", "listen"), ("/sobre/", "Sobre", "about")]
    top = "".join(f'<a href="{h}"{" aria-current=page" if k == active else ""}>{l}</a>' for h, l, k in nav)
    dock = "".join(
        f'<a href="{h}" class="dock-btn"{" aria-current=page" if k == active else ""}>'
        f'<span class="dock-ring">{icon(k)}</span><span class="dock-label">{l}</span></a>' for h, l, k in nav)
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="#200704">
<meta property="og:type" content="website">
<meta property="og:site_name" content="7° andar">
<meta property="og:locale" content="pt_BR">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{og}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="alternate" type="application/rss+xml" title="7° andar" href="{SUBSTACK}/feed">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Doto:wght@800&family=Fraunces:ital,opsz,wght,SOFT@0,9..144,400..900,100;1,9..144,400..700,100&family=Lora:ital,wght@0,400..600;1,400..600&display=swap">
<link rel="stylesheet" href="/assets/styles.css?v={BUILD_ID}">
{extra_head}{ld}
</head>
<body data-page="{active}">
<a class="skip" href="#conteudo">Pular para o conteúdo</a>
<header class="top">
  <a class="brand" href="/" aria-label="7° andar, página inicial">{inline_svg("wordmark", "wordmark")}</a>
  <nav class="top-nav" aria-label="Principal">{top}</nav>
  <div class="floor" aria-hidden="true"><span class="floor-arrow">{icon("up", "floor-i")}</span><span class="floor-num" data-floor>{floor}</span></div>
</header>
<main id="conteudo">
{body}
</main>
<footer class="foot">
  <div class="foot-in">
    {inline_svg("cat", "foot-cat")}
    <p class="foot-line">Cada filme que vemos é uma camada na lente que usamos para ver o mundo.</p>
    <ul class="foot-links">
      <li><a href="mailto:{EMAIL}">{EMAIL}</a></li>
      <li><a href="{SUBSTACK}">7andar.substack.com</a></li>
      <li><a href="{SUBSTACK}/feed">RSS</a></li>
    </ul>
    <p class="foot-small">© {dt.date.today().year} 7° andar, por Rai Rezende.</p>
  </div>
</footer>
<div class="np" data-np hidden>
  <button class="np-btn" data-np-toggle aria-label="Pausar">{icon("pause")}{icon("play")}</button>
  <a class="np-meta" data-np-link href="/"><span class="np-num" data-np-num></span><span class="np-title" data-np-title></span></a>
  <span class="np-time" data-np-time>0:00</span>
  <div class="np-bar"><span data-np-bar></span></div>
</div>
<nav class="dock" aria-label="Atalhos">{dock}</nav>
<audio data-audio preload="none"></audio>
<script src="/assets/app.js?v={BUILD_ID}" defer></script>
</body>
</html>
"""


def art(ep, cls, sizes="(min-width: 900px) 480px, 100vw", eager=False):
    if ep["img"]:
        load = 'fetchpriority="high"' if eager else 'loading="lazy"'
        return (f'<img class="{cls}" src="{ep["img"]}-960.webp" srcset="{ep["img"]}-480.webp 480w, {ep["img"]}-960.webp 960w" '
                f'sizes="{sizes}" width="960" height="640" alt="" {load} decoding="async">')
    return f'<div class="{cls} art-fallback" aria-hidden="true">{inline_svg("cat", "fb-cat")}<span>{ep["num"]}</span></div>'


def play_btn(ep, label=None, cls="play"):
    label = label or f"Ouvir episódio {ep['num']}"
    return (f'<button class="{cls}" data-play data-src="{e(ep["audio"])}" data-num="{ep["num"]}" '
            f'data-title="{e(ep["title"])}" data-href="/episodios/{ep["slug"]}/" aria-label="{e(label)}">'
            f'<span class="play-ring">{icon("play")}{icon("pause")}</span>'
            f'<span class="play-label">{e(label)}</span></button>')


def film_line(ep):
    if not ep["film"]:
        return ""
    return f'<span class="film">{e(ep["film"])}</span> <span class="year">({ep["year"]})</span>'


def floor_row(ep, latest=False):
    return f"""<li class="row{' row-latest' if latest else ''}" data-floor-of="{ep['num']}">
  <a class="row-link" href="/episodios/{ep['slug']}/">
    <span class="call{' call-lit' if latest else ''}" aria-hidden="true">{ep['num']}</span>
    <span class="row-text">
      <span class="row-title">{e(ep['title'])}</span>
      <span class="row-meta">{film_line(ep)}<span class="dur">{dur_label(ep['duration'])}</span></span>
    </span>
    {art(ep, 'row-art', sizes='120px')}
  </a>
</li>"""


def platform_logo(slug):
    raw = open(os.path.join(ROOT, "src", "img", "platforms", f"{slug}.svg")).read()
    raw = re.sub(r"<title>.*?</title>", "", raw)
    return raw.replace('<svg role="img" ', '<svg class="pl-logo" aria-hidden="true" fill="currentColor" ', 1)


def platforms_block(heading="Onde ouvir", hid="ouvir"):
    items = "".join(
        f'<li><a class="pl" href="{u}" rel="noopener" target="_blank" style="--brand:{c}">'
        f'<span class="pl-btn">{platform_logo(slug)}</span><span class="pl-name">{n}</span></a></li>'
        for n, u, slug, c in PLATFORMS)
    return f"""<section class="listen" id="{hid}" aria-labelledby="{hid}-h">
  <h2 id="{hid}-h" class="h2">{heading}</h2>
  <p class="lede">Episódio novo sai no Substack e chega aos aplicativos no mesmo dia.</p>
  <div class="panel"><ul class="pls">{items}</ul></div>
</section>"""


def read_block(read):
    if not read:
        return ""
    img = f'<img class="read-img" src="{read["img"]}" alt="" width="800" height="450" loading="lazy">' if read.get("img") else ""
    return f"""<section class="read" aria-labelledby="read-h">
  <h2 id="read-h" class="h2">Para ler</h2>
  <p class="lede">Listas e textos da newsletter.</p>
  <a class="read-card" href="{read['url']}" rel="noopener" target="_blank">
    {img}
    <span class="read-body">
      <span class="read-title">{e(read['title'])}</span>
      {f'<span class="read-sub">{e(read["subtitle"])}</span>' if read['subtitle'] else ''}
      <span class="read-go">Ler no Substack {icon('out')}</span>
    </span>
  </a>
</section>"""


def subscribe_block():
    # Same endpoint Substack's own embed posts to (7andar.substack.com/embed); creates a real free subscription.
    return f"""<section class="sub" aria-labelledby="sub-h">
  <div class="sub-in">
    <div class="sub-text">
      <h2 id="sub-h" class="h2">Receba cada episódio por <span class="nowrap">e-mail</span></h2>
      <p>É de graça. Um e-mail por episódio, com o áudio e as notas do filme.</p>
    </div>
    <form class="sub-form" action="{SUBSTACK}/api/v1/free?nojs=true" method="post" target="_blank">
      <input type="hidden" name="source" value="embed">
      <input type="hidden" name="first_url" value="{SITE}/">
      <label class="sr" for="sub-email">Seu e-mail</label>
      <input id="sub-email" name="email" type="email" required autocomplete="email" inputmode="email" placeholder="seu@email.com">
      <button type="submit">Assinar</button>
    </form>
  </div>
</section>"""


def hub_block(read):
    """Listen + read side by side on desktop, subscribe underneath."""
    return f"""<div class="hub">
  {platforms_block()}
  {read_block(read)}
  {subscribe_block()}
</div>"""


def series_ld(eps):
    return {
        "@context": "https://schema.org", "@type": "PodcastSeries", "name": "7° andar",
        "url": SITE, "inLanguage": "pt-BR", "webFeed": f"{SUBSTACK}/feed",
        "description": "Podcast de cinema apresentado por Rai Rezende. Um filme por episódio.",
        "author": {"@type": "Person", "name": "Rai Rezende"},
        "image": SITE + "/assets/icon-512.png",
    }


def home(eps, reads):
    latest = eps[0]
    meta = f'<p class="feat-film">{film_line(latest)}{" dirigido por " + e(latest["director"]) if latest["director"] else ""}</p>' if latest["film"] else ""
    rows = "".join(floor_row(ep, i == 0) for i, ep in enumerate(eps))
    read = reads[0] if reads else None
    body = f"""
<section class="hero">
  <div class="hero-in">
    {inline_svg("logo-cat", "hero-cat", "7° andar")}
    <h1 class="hero-h">Cada filme que vemos é uma camada na lente que usamos para ver o mundo.</h1>
    <p class="hero-p">Um podcast de cinema apresentado por Rai Rezende. Um filme por episódio.</p>
    <div class="hero-cta">
      {play_btn(latest, f"Ouvir o episódio {latest['num']}", "play play-big")}
      <a class="ghost" href="/episodios/">Ver todos os episódios</a>
    </div>
  </div>
</section>

{hub_block(read)}

<section class="feat" aria-labelledby="feat-h">
  <a class="feat-art-link" href="/episodios/{latest['slug']}/" tabindex="-1" aria-hidden="true">{art(latest, 'feat-art', eager=True)}</a>
  <div class="feat-body">
    <p class="feat-kicker"><span class="call call-lit call-sm" aria-hidden="true">{latest['num']}</span> Episódio mais recente, {date_pt(latest['date'])}</p>
    <h2 id="feat-h" class="feat-title"><a href="/episodios/{latest['slug']}/">{e(latest['title'])}</a></h2>
    {f'<p class="feat-sub">{e(latest["subtitle"])}</p>' if latest['subtitle'] else ''}
    {meta}
    <div class="feat-actions">{play_btn(latest, f"Ouvir agora, {dur_label(latest['duration'])}")}</div>
  </div>
</section>

<section class="building" aria-labelledby="andares-h">
  <div class="building-head">
    <h2 id="andares-h" class="h2">Todos os andares</h2>
    <p class="lede">{len(eps)} episódios. Escolha um andar.</p>
  </div>
  <ol class="rows" reversed>{rows}</ol>
</section>

<section class="paper" aria-labelledby="sobre-h">
  <div class="paper-in">
    <h2 id="sobre-h" class="paper-h">Suba comigo até o 7° andar.</h2>
    <p>Rai Rezende é jornalista pela UFOP. No 7° andar, cada episódio parte de um filme, clássico ou recém-lançado, para conversar sobre o que ele diz da gente: afeto, liberdade, corpo, medo, memória.</p>
    <a class="ink-link" href="/sobre/">Conheça o podcast</a>
  </div>
</section>

"""
    return page(path="/", title="7° andar, um podcast de cinema por Rai Rezende",
                desc="Cada filme que vemos é uma camada na lente que usamos para ver o mundo. Podcast de cinema apresentado por Rai Rezende.",
                body=body, active="home", jsonld=series_ld(eps))


def episodes_page(eps):
    rows = "".join(floor_row(ep, i == 0) for i, ep in enumerate(eps))
    body = f"""
<section class="page-head">
  <h1 class="h1">Episódios</h1>
  <p class="lede">Do primeiro andar até o mais recente. Toque em um andar para ouvir e ler as notas.</p>
</section>
<section class="building building-full">
  <ol class="rows" reversed>{rows}</ol>
</section>
{platforms_block("Ouça também nos aplicativos")}
"""
    return page(path="/episodios/", title="Episódios, 7° andar", active="list",
                desc=f"Todos os {len(eps)} episódios do 7° andar, podcast de cinema de Rai Rezende.", body=body,
                jsonld=series_ld(eps))


def episode_page(ep, prev_ep, next_ep):
    yt = ""
    if ep["youtube"]:
        yt = f"""<section class="ep-yt" aria-label="Assistir no YouTube">
  <button class="yt" data-yt="{ep['youtube']}" aria-label="Carregar o vídeo do episódio no YouTube">
    <img src="https://i.ytimg.com/vi/{ep['youtube']}/hqdefault.jpg" alt="" loading="lazy" width="480" height="360">
    <span class="yt-play">{icon('play')}</span>
    <span class="yt-label">Assistir no YouTube</span>
  </button>
</section>"""
    nav = []
    if next_ep:
        nav.append(f'<a class="ep-nav-btn" href="/episodios/{next_ep["slug"]}/"><span class="call call-sm">{next_ep["num"]}</span><span><small>Subir um andar</small>{e(next_ep["title"])}</span></a>')
    if prev_ep:
        nav.append(f'<a class="ep-nav-btn" href="/episodios/{prev_ep["slug"]}/"><span class="call call-sm">{prev_ep["num"]}</span><span><small>Descer um andar</small>{e(prev_ep["title"])}</span></a>')
    facts = ""
    if ep["film"]:
        orig = f'<div><dt>Título original</dt><dd>{e(ep["original"])}</dd></div>' if ep["original"] and ep["original"] != ep["film"] else ""
        facts = f"""<dl class="facts">
  <div><dt>Filme</dt><dd>{e(ep['film'])}</dd></div>{orig}
  <div><dt>Ano</dt><dd>{ep['year']}</dd></div>
  <div><dt>Direção</dt><dd>{e(ep['director'])}</dd></div>
</dl>"""
    ld = {
        "@context": "https://schema.org", "@type": "PodcastEpisode", "name": ep["full_title"],
        "episodeNumber": ep["num"], "datePublished": ep["date"].date().isoformat(),
        "url": f"{SITE}/episodios/{ep['slug']}/", "description": ep["subtitle"] or ep["title"],
        "timeRequired": f"PT{round(ep['duration'] / 60)}M",
        "associatedMedia": {"@type": "MediaObject", "contentUrl": ep["audio"]},
        "partOfSeries": {"@type": "PodcastSeries", "name": "7° andar", "url": SITE},
    }
    body = f"""
<article class="ep">
  <header class="ep-head">
    <div class="ep-art-wrap">{art(ep, 'ep-art', sizes='(min-width: 900px) 560px, 100vw', eager=True)}</div>
    <div class="ep-head-text">
      <p class="ep-kicker"><span class="call call-lit" aria-hidden="true">{ep['num']}</span><span>Episódio {ep['num']}<br><time datetime="{ep['date'].date().isoformat()}">{date_pt(ep['date'])}</time></span></p>
      <h1 class="ep-title">{e(ep['title'])}</h1>
      {f'<p class="ep-sub">{e(ep["subtitle"])}</p>' if ep['subtitle'] else ''}
      <div class="ep-player" data-player data-src="{e(ep['audio'])}">
        {play_btn(ep, f"Ouvir, {dur_label(ep['duration'])}", "play play-big")}
        <div class="scrub" data-scrub hidden>
          <input type="range" min="0" max="{round(ep['duration'])}" value="0" step="1" aria-label="Posição no episódio" data-seek>
          <div class="scrub-times"><span data-cur>0:00</span><span>{dur_label(ep['duration'])}</span></div>
        </div>
      </div>
    </div>
  </header>
  <div class="ep-body">
    {facts}
    <div class="notes">{ep['notes'] or ''}</div>
    <p class="ep-links">
      <a href="{ep['substack']}" rel="noopener" target="_blank">Comentar no Substack {icon('out')}</a>
    </p>
  </div>
  {yt}
  <nav class="ep-nav" aria-label="Outros episódios">{''.join(nav)}</nav>
</article>
{subscribe_block()}
"""
    desc = (ep["subtitle"] + " " if ep["subtitle"] else "") + (f"Episódio {ep['num']} do 7° andar sobre {ep['film']} ({ep['year']})." if ep["film"] else f"Episódio {ep['num']} do 7° andar.")
    return page(path=f"/episodios/{ep['slug']}/", title=f"{ep['num']}. {ep['title']}, 7° andar",
                desc=desc, body=body, active="list", og=ep["og"], jsonld=ld)


def about_page(eps):
    total_h = sum(x["duration"] for x in eps) / 3600
    body = f"""
<section class="page-head">
  <h1 class="h1">Sobre o 7° andar</h1>
</section>
<section class="prose">
  <p class="big">O 7° andar é um podcast de cinema apresentado por Rai Rezende. Cada episódio parte de um único filme e o usa como lente para olhar o mundo.</p>
  <p>Já passaram por aqui animações do Studio Ghibli, o primeiro Oscar do Brasil, terror recém-lançado e clássicos de sessão da tarde. São {len(eps)} episódios até agora, mais de {int(total_h)} horas de conversa.</p>
  <h2 class="h3">Quem apresenta</h2>
  <p>Rai Rezende é jornalista pela Universidade Federal de Ouro Preto (UFOP) e apresenta todos os episódios do 7° andar.</p>
  <h2 class="h3">Fale com o 7° andar</h2>
  <p>Sugestões de filme, convites e parcerias: <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>
</section>
{platforms_block()}
{subscribe_block()}
"""
    return page(path="/sobre/", title="Sobre, 7° andar", active="about",
                desc="Sobre o 7° andar, podcast de cinema apresentado por Rai Rezende, jornalista pela UFOP.", body=body)


def not_found():
    body = """
<section class="lost">
  <p class="lost-floor" aria-hidden="true">404</p>
  <h1 class="h1">Esse andar não existe.</h1>
  <p class="lede">O link pode estar errado ou o episódio mudou de endereço.</p>
  <p><a class="ghost" href="/episodios/">Ver todos os episódios</a></p>
</section>"""
    return page(path="/404.html", title="Andar não encontrado, 7° andar", desc="Página não encontrada.", body=body, active="", floor="?")


# ---------------------------------------------------------------- main

BUILD_ID = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")


def write(rel, content):
    path = os.path.join(DIST, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if rel.endswith(".html"):
        # keep "7° andar" together on one line
        content = content.replace("7° andar", "7°\u00a0andar")
    with open(path, "w") as f:
        f.write(content)


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(CACHE, exist_ok=True)
    eps, reads = load_episodes()
    build_images(eps)
    build_read_images(reads)
    write("index.html", home(eps, reads))
    write("episodios/index.html", episodes_page(eps))
    for i, ep in enumerate(eps):
        nxt = eps[i - 1] if i > 0 else None
        prv = eps[i + 1] if i + 1 < len(eps) else None
        write(f"episodios/{ep['slug']}/index.html", episode_page(ep, prv, nxt))
    write("sobre/index.html", about_page(eps))
    write("404.html", not_found())

    os.makedirs(os.path.join(DIST, "assets", "img"), exist_ok=True)
    for f in ("styles.css", "app.js"):
        shutil.copy(os.path.join(ROOT, "src", f), os.path.join(DIST, "assets", f))
    shutil.copytree(os.path.join(ROOT, "src", "img"), os.path.join(DIST, "assets", "img"), dirs_exist_ok=True)
    cat = svg("cat").replace("currentColor", "#FFF7F2")
    write("favicon.svg", cat.replace('viewBox="0 0 654 600"', 'viewBox="-60 -90 774 774"').replace(
        "<path", '<rect x="-60" y="-90" width="774" height="774" rx="150" fill="#200704"/><path', 1))
    write("site.webmanifest", json.dumps({
        "name": "7° andar", "short_name": "7° andar", "start_url": "/", "display": "standalone",
        "background_color": "#200704", "theme_color": "#200704", "lang": "pt-BR",
        "icons": [{"src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png"}]}, ensure_ascii=False))
    write("CNAME", "setimoandar.com\n")
    write(".nojekyll", "")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    urls = ["/", "/episodios/", "/sobre/"] + [f"/episodios/{x['slug']}/" for x in eps]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{SITE}{u}</loc></url>" for u in urls) + "</urlset>\n")
    print(f"built {len(eps)} episodes into {DIST}")


if __name__ == "__main__":
    main()
