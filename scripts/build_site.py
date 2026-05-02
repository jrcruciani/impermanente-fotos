"""Genera el sitio estático fotos.impermanente.es a partir de:
  - data/inventory.jsonl  (todas las fotos con metadata Pixelfed)
  - data/published.jsonl  (alt-texts publicados)

Salida en `output/`:
  - index.html              Landing (intro + collections + últimas 30 fotos + paginación)
  - archivo/p/{N}/index.html Páginas siguientes (30 por página)
  - foto/{status_id}/index.html Página por foto
  - sitemap.xml
  - robots.txt
  - feed.json               (compatibilidad con consumidor JS de impermanente.es/fotos)
  - CNAME                   Para GitHub Pages custom domain

Filosofía:
  - HTML completo en cada página (sin JS para mostrar fotos).
  - Alt-text completo en `<img alt>` y JSON-LD ImageObject por foto.
  - Visualmente alineado con impermanente.es (mismo CSS embebido).
  - Sin tracking, sin tipografías externas más allá de las del sitio principal.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

SITE_DOMAIN = "fotos.impermanente.es"
SITE_URL = f"https://{SITE_DOMAIN}"
PARENT_URL = "https://impermanente.es"
PIXELFED_USER_URL = "https://pixelfed.social/HispaniaObscura"
AUTHOR_NAME = "J.R. Cruciani"
AUTHOR_ID = "https://impermanente.es/about/#person"
SERIES_ID = f"{SITE_URL}/#series"
PHOTOS_PER_PAGE = 30
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

COLLECTIONS = [
    {
        "slug": "umbrales",
        "name": "Umbrales",
        "description": "Marca personal y eje del trabajo fotográfico del autor: arcos, túneles, pasajes y orillas como espacios de tránsito y contacto entre dos mundos.",
        "url": "https://pixelfed.social/c/945553508223330178",
        "thumb": "https://pxscdn.com/public/m/_v2/783480968440772334/0c2c69eb8-6377a8/CPzeJtgtFI5f/xUEmfN7t97xz3laCHiinCnKYA87bDpdwii2SRTdm.jpg",
    },
    {
        "slug": "por-la-calle",
        "name": "Por la calle",
        "description": "Gestos, escenas y personas en lo cotidiano urbano: street photography sin pose ni guion.",
        "url": "https://pixelfed.social/c/945557139208117482",
        "thumb": "https://pxscdn.com/public/m/_v2/783480968440772334/31410d826-759a86/a04qBIyRiDWO/BXHpDtoJQEECKYTZZX5VbjAx18VJb6iSNlQCU4RE.jpg",
    },
    {
        "slug": "ciudades",
        "name": "Ciudades",
        "description": "Arquitectura, ritmo y atmósfera de ciudades visitadas.",
        "url": "https://pixelfed.social/c/945559829313601798",
        "thumb": "https://pxscdn.com/public/m/_v2/783480968440772334/a1431798c-70628a/5sZGV1HRmf19/Fo5E5nWxUAMtGSI6RTDR6C9VT1BjZNzzC8lcHFxJ.jpg",
    },
    {
        "slug": "oubal",
        "name": "Oubal",
        "description": "Retrato cotidiano y libre: fotos de Valeria siendo Valeria.",
        "url": "https://pixelfed.social/c/945724326079277422",
        "thumb": "https://pxscdn.com/public/m/_v2/783480968440772334/ffe7c43a6-a8b5f2/KgaGEkAkOZ43/WpYhTbCcMLgeBIOgJyFWrT3FOlYCB5zlrogcJPh5.jpg",
    },
    {
        "slug": "psicopompo",
        "name": "Psicopompo",
        "description": "Patrimonio funerario y tanatoturismo: cementerios históricos, escultura sepulcral y simbología de la muerte fotografiados en Europa y otras geografías.",
        "url": "https://pixelfed.social/c/945719873655811786",
        "thumb": "https://pxscdn.com/public/m/_v2/783480968440772334/0c2c69eb8-6377a8/jfpBNgHl6733/LVeuunKoh03KDvSpPxkfvPYBLgjNZoRwwZCem5aY.jpg",
    },
    {
        "slug": "dorado",
        "name": "Dorado",
        "description": "La luz que cierra el día: puestas de sol y golden hour en distintos paisajes.",
        "url": "https://pixelfed.social/c/945723351877605084",
        "thumb": "https://pxscdn.com/public/m/_v2/783480968440772334/634f2a4e4-291f24/XBjGkWXgqShy/qfbD2c9Ed3c4QaUkSpCHKZx2k9AjLqoXiTdtE7SX.jpg",
    },
]


# ---------- Utility ----------

def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def load_jsonl(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def fallback_alt(content_text: str | None, place: dict | None) -> str:
    if content_text:
        return content_text.strip()[:500]
    if place and place.get("name"):
        return f"Foto en {place['name']}"
    return "Foto de Hispania Obscura"


def merge_records() -> list[dict]:
    """Une inventory + published por media_id; ordena por created_at desc."""
    inv = {r["media_id"]: r for r in load_jsonl(DATA_DIR / "inventory.jsonl")}
    pub_records = load_jsonl(DATA_DIR / "published.jsonl")
    pub_ok = {}
    for p in pub_records:
        if p.get("status") == "ok":
            pub_ok[p["media_id"]] = p

    merged = []
    for mid, r in inv.items():
        alt = pub_ok.get(mid, {}).get("alt_text") or r.get("current_description") or fallback_alt(
            r.get("content_text"), r.get("place")
        )
        merged.append({
            "media_id": mid,
            "status_id": r["status_id"],
            "status_url": r.get("status_url") or f"{PIXELFED_USER_URL}/{r['status_id']}",
            "image_url": r["image_url"],
            "preview_url": r.get("preview_url") or r["image_url"],
            "blurhash": r.get("blurhash"),
            "alt_text": alt,
            "place": r.get("place"),
            "created_at": r.get("created_at"),
            "content_text": r.get("content_text") or "",
            "meta": r.get("meta") or {},
            "position_in_status": r.get("position_in_status", 0),
            "total_in_status": r.get("total_in_status", 1),
        })
    # ordena más reciente primero
    merged.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return merged


def fmt_date_es(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{d.day} {months[d.month - 1]} {d.year}"


def photo_url(status_id: str) -> str:
    return f"{SITE_URL}/foto/{status_id}/"


# ---------- Templates ----------

CSS = """
:root {
  --bg: #fafafa;
  --bg-elev: #fff;
  --fg: #222;
  --fg-soft: #555;
  --fg-soft2: #888;
  --rule: rgba(0,0,0,.12);
  --link: #2a4d8f;
  --photo-border: #fff;
  --photo-outline: #000;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171c;
    --bg-elev: #1a1f27;
    --fg: #ececec;
    --fg-soft: #bbb;
    --fg-soft2: #888;
    --rule: rgba(255,255,255,.12);
    --link: #93b8ff;
    --photo-border: #000;
    --photo-outline: #fff;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--fg);
  margin: 0;
  line-height: 1.55;
}
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
.header {
  border-bottom: 1px solid var(--rule);
  background: var(--bg-elev);
}
.site-nav {
  max-width: 980px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 14px 1rem;
  flex-wrap: wrap;
}
.site-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
}
.site-title a {
  color: var(--fg);
  display: flex;
  align-items: center;
  gap: 8px;
}
.site-title img {
  width: 28px;
  height: 28px;
  border-radius: 50%;
}
.nav-menu {
  list-style: none;
  display: flex;
  gap: 1rem;
  margin: 0;
  padding: 0;
  font-size: .95rem;
  flex-wrap: wrap;
}
.nav-menu a { color: var(--fg-soft); }
.nav-menu a.current { color: var(--fg); font-weight: 600; }
main {
  max-width: 720px;
  margin: 0 auto;
  padding: 2rem 1rem 4rem;
}
.page-intro {
  max-width: 680px;
  margin: 0 auto 2rem auto;
  text-align: center;
  color: var(--fg-soft);
  font-size: 1.05rem;
  line-height: 1.7;
}
.section-divider {
  width: 72px;
  margin: 2rem auto 2.4rem auto;
  border: 0;
  border-top: 1px solid var(--rule);
}
h1, h2, h3 {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  letter-spacing: .3px;
}
h1 { font-size: 1.7rem; margin: 0 0 1rem; }
h2.section-title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 2rem 0 1rem;
  color: var(--fg);
}
.collections-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.collection-card {
  position: relative;
  display: block;
  overflow: hidden;
  border-radius: 8px;
  text-decoration: none;
  aspect-ratio: 1;
}
.collection-card img {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
  transition: transform .3s ease;
}
.collection-card:hover img { transform: scale(1.05); }
.collection-name {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  padding: 24px 10px 10px;
  background: linear-gradient(transparent, rgba(0,0,0,.65));
  color: #fff;
  font-size: 1.1rem;
  font-weight: 600;
}
@media (max-width: 600px) {
  .collections-grid { grid-template-columns: repeat(2, 1fr); }
}
.gallery {
  margin: 1rem auto 2rem;
}
.gallery-item {
  margin-bottom: 30px;
}
.gallery-item a {
  text-decoration: none;
  color: var(--fg);
  display: block;
}
.gallery-item img {
  width: calc(100% - 10px);
  margin: 5px;
  display: block;
  border: 5px solid var(--photo-border);
  outline: 5px solid var(--photo-outline);
  outline-offset: 0;
  box-shadow: none;
  height: auto;
}
.gallery-item:hover { opacity: .85; }
.photo-info {
  margin-top: 10px;
}
.photo-caption {
  font-size: .98rem;
  color: var(--fg-soft);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.photo-date {
  display: block;
  font-size: .8rem;
  color: var(--fg-soft2);
  margin-top: 5px;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.pagination {
  display: flex;
  justify-content: center;
  gap: .5rem;
  margin: 2rem 0 1rem;
  flex-wrap: wrap;
  font-size: .95rem;
}
.pagination a, .pagination span {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--rule);
  color: var(--fg-soft);
  text-decoration: none;
}
.pagination a:hover { background: var(--bg-elev); color: var(--fg); }
.pagination .current {
  background: var(--fg);
  color: var(--bg);
  border-color: var(--fg);
}
.pixelfed-cta {
  text-align: center;
  margin: 2rem 0;
}
.btn-pixelfed {
  display: inline-block;
  padding: 12px 24px;
  background: #6366f1;
  color: #fff !important;
  border-radius: 8px;
  font-weight: 600;
  text-decoration: none;
}
.btn-pixelfed:hover { background: #4f46e5; }
footer {
  border-top: 1px solid var(--rule);
  padding: 2rem 1rem;
  font-size: .85rem;
  color: var(--fg-soft2);
  text-align: center;
}
footer a { color: var(--fg-soft); }
.photo-page main { max-width: 920px; }
.photo-page .photo-hero {
  margin: 0 0 1.5rem;
  text-align: center;
}
.photo-page .photo-hero img {
  max-width: 100%;
  height: auto;
  border: 5px solid var(--photo-border);
  outline: 5px solid var(--photo-outline);
}
.photo-page .photo-text {
  font-size: 1.05rem;
  line-height: 1.7;
  color: var(--fg);
  margin: 1.5rem 0;
}
.photo-page .photo-meta {
  font-size: .9rem;
  color: var(--fg-soft);
  margin-bottom: 2rem;
}
.photo-page .photo-meta a { color: var(--fg-soft); border-bottom: 1px dotted; }
.photo-page .photo-prev-next {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--rule);
  font-size: .92rem;
}
.photo-page .photo-prev-next a { color: var(--fg-soft); }
"""


def head(title: str, description: str, canonical: str, og_image: str | None = None,
        extra_jsonld: list[dict] | None = None, body_class: str = "") -> str:
    jsonld_blocks = ""
    if extra_jsonld:
        for ld in extra_jsonld:
            jsonld_blocks += f'\n<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    og_img_tag = f'<meta property="og:image" content="{esc(og_image)}">' if og_image else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="author" content="{esc(AUTHOR_NAME)}">
<meta name="color-scheme" content="light dark">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:locale" content="es_ES">
<meta property="og:site_name" content="impermanente — fotos">
{og_img_tag}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<link rel="alternate" type="application/rss+xml" href="{PARENT_URL}/feed.xml" title="impermanente">
<link rel="me" href="{PIXELFED_USER_URL}">
<style>{CSS}</style>{jsonld_blocks}
</head>
<body class="{esc(body_class)}">
<header class="header">
  <nav class="site-nav">
    <h1 class="site-title"><a href="{PARENT_URL}/">
      <img src="https://avatars.micro.blog/avatars/2025/36/1810674.jpg" alt="" width="28" height="28">impermanente
    </a></h1>
    <ul class="nav-menu">
      <li><a href="{PARENT_URL}/about/">Acerca de</a></li>
      <li><a href="{SITE_URL}/" class="current">Fotos</a></li>
      <li><a href="{PARENT_URL}/viajes/">Viajes</a></li>
      <li><a href="{PARENT_URL}/lecturas/">Lecturas</a></li>
      <li><a href="{PARENT_URL}/mastodon/">Cortos</a></li>
      <li><a href="{PARENT_URL}/hispania-obscura/">Libros</a></li>
      <li><a href="{PARENT_URL}/loops/">Loops</a></li>
    </ul>
  </nav>
</header>
<main>
"""


def footer() -> str:
    return f"""</main>
<footer>
  Hecho con luz por <a href="{PARENT_URL}/about/">{esc(AUTHOR_NAME)}</a> ·
  Las fotos son CC BY 4.0 ·
  <a href="{PIXELFED_USER_URL}">@HispaniaObscura</a>
</footer>
</body>
</html>
"""


# ---------- JSON-LD constructors ----------

def jsonld_imageobject(p: dict) -> dict:
    """Un ImageObject completo por foto."""
    node = {
        "@type": "ImageObject",
        "@id": photo_url(p["status_id"]) + "#image",
        "contentUrl": p["image_url"],
        "thumbnailUrl": p["preview_url"],
        "url": photo_url(p["status_id"]),
        "description": p["alt_text"],
        "license": LICENSE_URL,
        "creator": {"@id": AUTHOR_ID},
        "isPartOf": {"@id": SERIES_ID},
        "inLanguage": "es",
    }
    if p.get("created_at"):
        node["datePublished"] = p["created_at"]
    if p.get("place"):
        place = p["place"]
        loc = {"@type": "Place", "name": place.get("name") or ""}
        if place.get("country"):
            loc["address"] = {"@type": "PostalAddress", "addressCountry": place["country"]}
        node["contentLocation"] = loc
    if p.get("meta", {}).get("width"):
        node["width"] = p["meta"]["width"]
        node["height"] = p["meta"].get("height")
    if p.get("status_url"):
        node["sameAs"] = p["status_url"]
    return node


def jsonld_series_root() -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "CreativeWorkSeries",
        "@id": SERIES_ID,
        "name": "impermanente — fotografía",
        "alternativeHeadline": "Fotografía de umbrales",
        "description": "Trabajo fotográfico continuo y principal de J.R. Cruciani. Documenta umbrales —pasajes, arcos, túneles, orillas— como tema central, ampliado en seis colecciones temáticas: fotografía de calle, ciudades, retrato íntimo, tanatoturismo en cementerios europeos y golden hour. Repositorio principal en Pixelfed.",
        "url": SITE_URL + "/",
        "inLanguage": "es",
        "creator": {"@id": AUTHOR_ID},
        "author": {"@id": AUTHOR_ID},
        "copyrightHolder": {"@id": AUTHOR_ID},
        "license": LICENSE_URL,
        "genre": [
            "Fotografía documental", "Fotografía de umbrales",
            "Fotografía de calle", "Tanatoturismo", "Retrato",
        ],
        "keywords": "umbrales, threshold, pasajes, fotografía documental, fotografía de calle, tanatoturismo, cementerios europeos, golden hour, retrato, J.R. Cruciani",
        "isPartOf": {"@id": "https://impermanente.es/#website"},
        "sameAs": PIXELFED_USER_URL,
    }


def jsonld_person() -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "@id": AUTHOR_ID,
        "name": AUTHOR_NAME,
        "alternateName": "JRCruciani",
        "url": "https://impermanente.es/about/",
        "image": "https://avatars.micro.blog/avatars/2025/36/1810674.jpg",
        "jobTitle": "Fotógrafo y escritor",
        "knowsLanguage": ["es", "en"],
        "sameAs": [
            PIXELFED_USER_URL,
            "https://masto.impermanente.es/@jrcruciani",
            "https://micro.blog/JRCruciani",
            "https://github.com/Jrcruciani",
        ],
    }


def jsonld_imagegallery(items: list[dict], page_url: str, page_name: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "ImageGallery",
        "@id": page_url + "#gallery",
        "url": page_url,
        "name": page_name,
        "isPartOf": {"@id": SERIES_ID},
        "inLanguage": "es",
        "image": [jsonld_imageobject(p) for p in items],
    }


def jsonld_breadcrumbs(crumbs: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
            for i, (name, url) in enumerate(crumbs)
        ],
    }


# ---------- Renderers ----------

def render_collections() -> str:
    cards = []
    for c in COLLECTIONS:
        cards.append(f"""<a href="{esc(c['url'])}" target="_blank" rel="noopener" class="collection-card">
  <img src="{esc(c['thumb'])}" alt="{esc(c['name'])}" loading="lazy">
  <span class="collection-name">{esc(c['name'])}</span>
</a>""")
    return f"""<h2 class="section-title">Colecciones</h2>
<div class="collections-grid">
{''.join(cards)}
</div>
"""


def render_gallery(items: list[dict]) -> str:
    parts = []
    for p in items:
        date = fmt_date_es(p.get("created_at"))
        caption = (p.get("content_text") or "").strip().split("\n")[0]
        if not caption:
            caption = p["alt_text"][:120]
        parts.append(f"""<div class="gallery-item">
  <a href="{esc(photo_url(p['status_id']))}">
    <img src="{esc(p['preview_url'])}" alt="{esc(p['alt_text'])}" loading="lazy"{(' width="' + str(p['meta'].get('width')) + '" height="' + str(p['meta'].get('height')) + '"') if p['meta'].get('width') else ''}>
    <div class="photo-info">
      <p class="photo-caption">{esc(caption)}</p>
      {('<span class="photo-date">' + esc(date) + '</span>') if date else ''}
    </div>
  </a>
</div>""")
    return f'<div class="gallery">\n{"".join(parts)}\n</div>'


def render_pagination(current_page: int, total_pages: int) -> str:
    if total_pages <= 1:
        return ""
    parts = []

    def link(page: int, label: str | None = None, current: bool = False) -> str:
        text = label or str(page)
        if current:
            return f'<span class="current">{esc(text)}</span>'
        url = f"{SITE_URL}/" if page == 1 else f"{SITE_URL}/p/{page}/"
        return f'<a href="{esc(url)}">{esc(text)}</a>'

    if current_page > 1:
        parts.append(link(current_page - 1, "‹ Anteriores"))
    for n in range(1, total_pages + 1):
        parts.append(link(n, current=(n == current_page)))
    if current_page < total_pages:
        parts.append(link(current_page + 1, "Siguientes ›"))
    return f'<nav class="pagination" aria-label="paginación">{"".join(parts)}</nav>'


def render_index_page(page: int, total_pages: int, page_items: list[dict],
                      include_collections: bool) -> str:
    if page == 1:
        title = "Fotos | impermanente"
        description = "Fotografías de umbrales, calle, ciudades, retratos, cementerios y luz dorada: mi manera de mirar lo que está a punto de cambiar, desaparecer o quedarse un segundo más."
        canonical = SITE_URL + "/"
    else:
        title = f"Fotos · página {page} | impermanente"
        description = f"Archivo de fotografías de J.R. Cruciani — página {page} de {total_pages}."
        canonical = f"{SITE_URL}/p/{page}/"

    og_img = page_items[0]["image_url"] if page_items else None
    page_jsonld = [
        jsonld_series_root(),
        jsonld_person(),
        jsonld_imagegallery(page_items, canonical, title),
    ]

    body = head(title, description, canonical, og_img, extra_jsonld=page_jsonld)
    if page == 1:
        body += f"""<div class="page-intro">
  <p>Fotografías de umbrales, calle, ciudades, retratos, cementerios y luz dorada: mi manera de mirar lo que está a punto de cambiar, desaparecer o quedarse un segundo más.</p>
</div>
<hr class="section-divider" aria-hidden="true">
"""
        if include_collections:
            body += render_collections()
        body += '<h2 class="section-title">Últimas fotos</h2>\n'
    else:
        body += f'<h1>Archivo de fotos · página {page}</h1>\n'

    body += render_gallery(page_items)
    body += render_pagination(page, total_pages)
    body += f"""<div class="pixelfed-cta">
  <a href="{PIXELFED_USER_URL}" target="_blank" rel="noopener" class="btn-pixelfed">
    Mira la galería completa en Pixelfed
  </a>
</div>
"""
    body += footer()
    return body


def render_photo_page(p: dict, prev_p: dict | None, next_p: dict | None) -> str:
    title_short = (p.get("content_text") or "").strip().split("\n")[0]
    if not title_short:
        title_short = p["alt_text"][:80].rstrip(",;:.")
    title = f"{title_short} | impermanente"
    canonical = photo_url(p["status_id"])

    page_jsonld = [
        jsonld_imageobject(p),
        jsonld_breadcrumbs([
            ("Fotos", SITE_URL + "/"),
            (title_short[:60], canonical),
        ]),
    ]

    body = head(title, p["alt_text"][:200], canonical, p["image_url"],
                extra_jsonld=page_jsonld, body_class="photo-page")

    width = p["meta"].get("width", "")
    height = p["meta"].get("height", "")
    dim_attrs = f' width="{width}" height="{height}"' if width else ""

    body += f"""<article>
  <div class="photo-hero">
    <a href="{esc(p['image_url'])}" rel="noopener">
      <img src="{esc(p['image_url'])}" alt="{esc(p['alt_text'])}" loading="eager"{dim_attrs}>
    </a>
  </div>
  <div class="photo-text">
    {esc(p['alt_text'])}
  </div>
  <div class="photo-meta">
    {('Publicada el ' + esc(fmt_date_es(p['created_at'])) + ' · ') if p.get('created_at') else ''}
    <a href="{esc(p['status_url'])}" target="_blank" rel="noopener">Ver en Pixelfed</a>
  </div>
"""

    nav_parts = []
    if prev_p:
        nav_parts.append(f'<a href="{esc(photo_url(prev_p["status_id"]))}">‹ Más reciente</a>')
    else:
        nav_parts.append('<span></span>')
    if next_p:
        nav_parts.append(f'<a href="{esc(photo_url(next_p["status_id"]))}">Más antigua ›</a>')
    body += f'<div class="photo-prev-next">{"".join(nav_parts)}</div>\n'
    body += '</article>\n'
    body += footer()
    return body


def render_sitemap(items: list[dict], total_pages: int) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    urls = [
        (SITE_URL + "/", today, "weekly", "1.0"),
    ]
    for n in range(2, total_pages + 1):
        urls.append((f"{SITE_URL}/p/{n}/", today, "weekly", "0.7"))
    for p in items:
        urls.append((photo_url(p["status_id"]), (p.get("created_at") or today)[:10], "monthly", "0.6"))
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url, lastmod, freq, prio in urls:
        body += f'<url><loc>{esc(url)}</loc><lastmod>{lastmod}</lastmod><changefreq>{freq}</changefreq><priority>{prio}</priority></url>\n'
    body += '</urlset>\n'
    return body


def render_robots() -> str:
    return f"""User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: anthropic-ai
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: CCBot
Allow: /

Sitemap: {SITE_URL}/sitemap.xml
"""


def render_feed_json(items: list[dict], limit: int = 30) -> str:
    """Compatibilidad con el consumidor JS de impermanente.es/fotos/.

    Mismo shape que el Worker existente (Mastodon-compatible status), para que
    el snippet actual de /fotos/ pueda apuntar aquí sin tocar el frontend.
    """
    posts = []
    for p in items[:limit]:
        posts.append({
            "id": p["status_id"],
            "url": p["status_url"],
            "created_at": p.get("created_at"),
            "content_text": p.get("content_text") or "",
            "place": p.get("place"),
            "media_attachments": [{
                "id": p["media_id"],
                "type": "image",
                "url": p["image_url"],
                "preview_url": p["preview_url"],
                "description": p["alt_text"],
                "blurhash": p.get("blurhash"),
                "meta": p.get("meta") or {},
            }],
        })
    return json.dumps(posts, ensure_ascii=False, indent=2)


# ---------- Main ----------

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build(output_dir: Path, items: list[dict]) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    total_pages = max(1, (len(items) + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE)

    # index + páginas paginadas
    for page in range(1, total_pages + 1):
        start = (page - 1) * PHOTOS_PER_PAGE
        end = start + PHOTOS_PER_PAGE
        page_items = items[start:end]
        html_str = render_index_page(page, total_pages, page_items, include_collections=(page == 1))
        if page == 1:
            write(output_dir / "index.html", html_str)
        else:
            write(output_dir / f"p/{page}/index.html", html_str)

    # páginas por foto
    for i, p in enumerate(items):
        prev_p = items[i - 1] if i > 0 else None
        next_p = items[i + 1] if i + 1 < len(items) else None
        html_str = render_photo_page(p, prev_p, next_p)
        write(output_dir / f"foto/{p['status_id']}/index.html", html_str)

    # sitemap, robots, feed
    write(output_dir / "sitemap.xml", render_sitemap(items, total_pages))
    write(output_dir / "robots.txt", render_robots())
    write(output_dir / "feed.json", render_feed_json(items))

    # CNAME para GitHub Pages custom domain
    write(output_dir / "CNAME", SITE_DOMAIN + "\n")

    # 404 page
    page_404 = head("Página no encontrada | impermanente — fotos",
                    "Esta página no existe.", SITE_URL + "/404.html")
    page_404 += f"""<h1>404</h1>
<p>Esta página no existe. Vuelve al <a href="{SITE_URL}/">inicio de fotos</a> o al <a href="{PARENT_URL}/">blog</a>.</p>
"""
    page_404 += footer()
    write(output_dir / "404.html", page_404)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUTPUT_DIR, help="Directorio de salida")
    args = ap.parse_args()

    items = merge_records()
    if not items:
        raise SystemExit("No hay records en data/inventory.jsonl. Ejecuta fetch_inventory.py primero.")

    build(args.out, items)
    print(f"Sitio generado en {args.out}/")
    print(f"  - {len(items)} fotos")
    print(f"  - {(len(items) + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE} páginas paginadas")
    print(f"  - {len(items)} páginas individuales")
    print(f"  - sitemap.xml, robots.txt, feed.json, 404.html, CNAME")


if __name__ == "__main__":
    main()
