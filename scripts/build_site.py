"""Genera el sitio estático fotos.impermanente.es a partir de:
  - data/inventory.jsonl  (todas las fotos con metadata Pixelfed)
  - data/published.jsonl  (alt-texts publicados)

Salida en `output/`:
  - index.html              Landing (intro + collections + últimas 30 fotos + paginación)
  - archivo/p/{N}/index.html Páginas siguientes (30 por página)
  - foto/{status_id}/index.html Página por foto
  - sitemap.xml
  - robots.txt
  - llms.txt                Índice curado para LLMs (convención por host)
  - okf/                    Bundle Open Knowledge Format (markdown + frontmatter)
  - feed.json               (compatibilidad con consumidor JS de impermanente.es/fotos)
  - CNAME                   Para GitHub Pages custom domain

Filosofía:
  - HTML completo en cada página (sin JS para mostrar fotos).
  - Alt-text completo en `<img alt>` y JSON-LD ImageObject por foto.
  - Visualmente alineado con impermanente.es (mismo CSS embebido).
  - Hereda tipografías/estilos del sitio principal y carga Wireboard.
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
IMAGES_CACHE_DIR = DATA_DIR / "images_cache"
COLLECTIONS_PATH = DATA_DIR / "collections.jsonl"

SITE_DOMAIN = "fotos.impermanente.es"
SITE_URL = f"https://{SITE_DOMAIN}"
PARENT_URL = "https://impermanente.es"
PIXELFED_USER_URL = "https://pixelfed.social/HispaniaObscura"
FAVICON_URL = "https://micro.blog/JRCruciani/favicon.png"
AUTHOR_NAME = "J.R. Cruciani"
AUTHOR_ID = "https://impermanente.es/about/#person"
SERIES_ID = f"{SITE_URL}/#series"
PHOTOS_PER_PAGE = 30
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
COLLECTION_ORDER = [
    "umbrales",
    "ciudades",
    "oubal",
    "por-la-calle",
    "dorado",
    "psicopompo",
]

# Descripciones curadas por colección (las del campo `description` en
# collections.jsonl suelen venir vacías). Coherentes con el llms.txt del blog.
COLLECTION_BLURBS = {
    "umbrales": "marca personal del autor. Arcos, túneles, pasajes y orillas como espacios de tránsito y contacto entre dos mundos.",
    "ciudades": "retrato fotográfico de ciudades — arquitectura, ritmo y atmósfera.",
    "oubal": "serie íntima dedicada a Valeria. Retrato cotidiano y libre.",
    "por-la-calle": "fotografía de calle. Gestos, escenas y personas en lo cotidiano urbano.",
    "dorado": "puestas de sol y golden hour. La luz que cierra el día.",
    "psicopompo": "tanatoturismo y patrimonio funerario. Cementerios históricos de Europa y otras geografías, escultura sepulcral y simbología de la muerte.",
}


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


def sort_collections(collections: list[dict]) -> list[dict]:
    order = {slug: pos for pos, slug in enumerate(COLLECTION_ORDER)}
    unknown_pos = len(order)
    sorted_with_index = sorted(
        enumerate(collections),
        key=lambda item: (order.get(item[1].get("slug"), unknown_pos), item[0]),
    )
    return [collection for _, collection in sorted_with_index]


def fallback_alt(content_text: str | None, place: dict | None) -> str:
    if content_text:
        return content_text.strip()[:500]
    if place and place.get("name"):
        return f"Foto en {place['name']}"
    return "Foto de Hispania Obscura"


def fmt_place(place: dict | None) -> str:
    """Formato unificado para mostrar ubicación: 'Ciudad, País', 'Ciudad' o ''."""
    if not place or not place.get("name"):
        return ""
    name = place["name"].strip()
    country = (place.get("country") or "").strip()
    if country:
        return f"{name}, {country}"
    return name


def merge_records() -> list[dict]:
    """Une inventory + published por media_id; ordena por created_at desc.

    `alt_is_real` indica si el alt-text proviene de una fuente real
    (published.jsonl o current_description de Pixelfed) o si es un fallback
    genérico de fallback_alt(). Sirve para evitar mostrar captions feos
    tipo "Foto en Lima" en la galería cuando aún no hay alt-text.
    """
    inv = {r["media_id"]: r for r in load_jsonl(DATA_DIR / "inventory.jsonl")}
    pub_records = load_jsonl(DATA_DIR / "published.jsonl")
    pub_ok = {}
    for p in pub_records:
        if p.get("status") == "ok":
            pub_ok[p["media_id"]] = p

    merged = []
    for mid, r in inv.items():
        published_alt = pub_ok.get(mid, {}).get("alt_text")
        current_alt = r.get("current_description")
        if published_alt:
            alt = published_alt
            alt_is_real = True
        elif current_alt:
            alt = current_alt
            alt_is_real = True
        else:
            alt = fallback_alt(r.get("content_text"), r.get("place"))
            alt_is_real = False
        merged.append({
            "media_id": mid,
            "status_id": r["status_id"],
            "status_url": r.get("status_url") or f"{PIXELFED_USER_URL}/{r['status_id']}",
            "image_url": r["image_url"],
            "preview_url": r.get("preview_url") or r["image_url"],
            "blurhash": r.get("blurhash"),
            "alt_text": alt,
            "alt_is_real": alt_is_real,
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
/* === impermanente fotos: overrides al theme Magnum del blog ===
   Los stylesheets del blog (fonts.css, main.css, photos-masonry.css, custom.css)
   se cargan via <link> en head() y aportan: tipografía Lora+Inter,
   variables de color (--bg, --text, --heading, --serif, --sans, --accent,
   --separator, --caption, --muted, --footer-bg, --footer-text), header
   styling (.header, .site-nav, .site-title, .u-photo, .nav-menu, .nav-item),
   footer negro y tokens de spacing. Aquí solo definimos lo único de la
   galería. */

/* Galería más ancha que el ancho de texto del blog */
main {
  max-width: var(--header-width, 94rem);
  padding: 60px var(--gutter, 24px) 40px;
}

/* Texto introductorio centrado, en serif del blog */
.page-intro {
  text-align: center;
  max-width: var(--text-width, 620px);
  margin: 0 auto 30px;
}
.page-intro p {
  font-family: var(--serif);
  font-size: 1.9rem;
  font-weight: var(--weight-light, 300);
  line-height: 1.55;
  letter-spacing: 0.3px;
  color: var(--text);
  max-width: var(--text-width, 620px);
  margin: 0 auto;
}

.section-divider {
  border: none;
  border-top: 1px solid var(--separator);
  max-width: 60px;
  margin: 40px auto;
}

.section-title {
  font-family: var(--sans);
  font-size: 2rem;
  font-weight: var(--weight-light, 300);
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--heading);
  text-align: center;
  margin: 60px 0 30px;
}

/* === Colecciones (grid superior) === */
.collections-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2px;
  margin-bottom: 40px;
}
.collection-card {
  position: relative;
  display: block;
  overflow: hidden;
  border-radius: 0;
  aspect-ratio: 1;
  text-decoration: none;
}
.collection-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  border-radius: 0 !important;
  margin: 0 !important;
  transition: transform 0.4s ease;
}
.collection-card:hover img { transform: scale(1.04); }
.collection-name {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  padding: 24px 14px 12px;
  background: linear-gradient(transparent, rgba(0,0,0,.7));
  color: #fff;
  font-family: var(--sans);
  font-size: 1.4rem;
  font-weight: var(--weight-medium, 500);
  letter-spacing: 1.5px;
  text-transform: uppercase;
}
@media (max-width: 600px) {
  .collections-grid { grid-template-columns: repeat(2, 1fr); }
}

/* === Galería de fotos: masonry 3 columnas (estilo Magnum del blog) ===
   Reutilizamos la clase `.masonry-grid` del blog (photos-masonry.css)
   pero forzamos column-count aquí porque nuestro <main> no tiene clase
   `.photos`/`.photos-wide`. Skip del JS de loading: emitimos `class="loaded"`
   en cada <li> y `class="visible"` en cada <img> desde el SSR. */
.masonry-grid {
  column-count: 3;
  column-gap: 8px;
  list-style: none;
  margin: 30px 0;
  padding: 0;
}
.masonry-grid li {
  background: transparent;
  border-radius: 0;
  break-inside: avoid;
  margin: 0 0 8px;
  padding: 0;
  overflow: hidden;
  position: relative;
  list-style: none;
}
/* override del placeholder "Loading..." del blog: no lo necesitamos */
.masonry-grid li::before {
  display: none !important;
}
.masonry-grid li a {
  display: block;
  text-decoration: none;
  color: var(--text);
}
.masonry-grid img {
  display: block;
  opacity: 1 !important;
  width: 100%;
  height: auto;
  border-radius: 0 !important;
  margin: 0 !important;
  transition: opacity 0.2s ease;
}
.masonry-grid img.u-photo {
  width: 100% !important;
  height: auto !important;
}
.masonry-grid li a:hover img {
  opacity: 0.92;
  filter: none;
}
.masonry-grid .photo-info {
  padding: 8px 4px 16px;
  max-width: none;
  margin: 0;
}
.masonry-grid .photo-caption {
  font-family: var(--serif);
  font-size: 1.3rem;
  font-weight: var(--weight-light, 300);
  line-height: 1.45;
  color: var(--text);
  margin: 0 0 6px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.masonry-grid .photo-meta-line {
  font-family: var(--sans);
  font-size: 0.95rem;
  font-weight: var(--weight-normal, 400);
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: var(--muted);
  display: block;
}
.masonry-grid .photo-meta-line .photo-place {
  color: var(--caption);
}
@media (max-width: 768px) {
  .masonry-grid { column-count: 2; }
}
@media (max-width: 375px) {
  .masonry-grid { column-count: 1; }
}

/* === Paginación (estilo Magnum) === */
.pagination {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin: 60px 0 30px;
  font-family: var(--sans);
  font-size: 1.2rem;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  flex-wrap: wrap;
}
.pagination a, .pagination span {
  padding: 10px 16px;
  border: 1px solid var(--separator);
  color: var(--muted);
  text-decoration: none;
  border-radius: 0;
  transition: color 0.2s ease, border-color 0.2s ease;
}
.pagination a:hover {
  color: var(--heading);
  border-color: var(--heading);
}
.pagination .current {
  background: var(--heading);
  color: var(--bg);
  border-color: var(--heading);
}

/* === CTA Pixelfed (botón Magnum) ===
   El blog define .btn-pixelfed con !important; con este selector más
   específico evitamos pisarlo, pero si llegara a pisarse el resultado
   visual sería el mismo. */
.pixelfed-cta {
  text-align: center;
  margin: 60px 0;
}

/* === Página individual de foto === */
body.photo-page main {
  max-width: var(--header-width, 94rem);
}
.photo-page .photo-hero {
  margin: 0 0 30px;
  text-align: center;
}
.photo-page .photo-hero img {
  max-width: 100%;
  height: auto;
  border-radius: 0 !important;
  margin: 0 !important;
}
.photo-page .photo-hero img.u-photo {
  width: auto !important;
  height: auto !important;
}
.photo-page .photo-text {
  font-family: var(--serif);
  font-size: 1.9rem;
  font-weight: var(--weight-light, 300);
  line-height: 1.55;
  letter-spacing: 0.3px;
  color: var(--text);
  max-width: var(--text-width, 620px);
  margin: 30px auto;
}
.photo-page .photo-meta {
  font-family: var(--sans);
  font-size: 1.2rem;
  font-weight: var(--weight-normal, 400);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--muted);
  text-align: center;
  margin: 0 auto 40px;
  max-width: var(--text-width, 620px);
}
.photo-page .photo-meta a {
  color: var(--accent);
  text-decoration: none;
  border: none;
}
.photo-page .photo-meta a:hover {
  text-decoration: underline;
  text-underline-offset: 4px;
}
.photo-page .photo-prev-next {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  margin: 80px auto 0;
  padding-top: 30px;
  border-top: 1px solid var(--separator);
  font-family: var(--sans);
  font-size: 1.2rem;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  max-width: var(--text-width, 620px);
}
.photo-page .photo-prev-next a {
  color: var(--muted);
  text-decoration: none;
}
.photo-page .photo-prev-next a:hover {
  color: var(--heading);
}

/* === Mobile === */
@media (max-width: 768px) {
  main { padding: 40px 16px 30px; }
  .page-intro p { font-size: 1.8rem; }
  .masonry-grid .photo-caption { font-size: 1.2rem; }
  .photo-page .photo-text { font-size: 1.7rem; }
  .section-title { font-size: 1.7rem; }
}
"""


WIREBOARD_TAG = """<!-- wireboard tag -->
<script type="text/javascript">
;(function(w,i,r,e,b,oar,d){if(!w[b]){w.WireBoardNamespace=w.WireBoardNamespace||[];
w.WireBoardNamespace.push(b);w[b]=function(){(w[b].q=w[b].q||[]).push(arguments)};
w[b].q=w[b].q||[];oar=i.createElement(r);d=i.getElementsByTagName(r)[0];oar.async=1;
oar.src=e;d.parentNode.insertBefore(oar,d)}}(window,document,"script","https://static.wireboard.io/wireboard.js","wireboard"));
wireboard('newTracker', 'wb', 'pipeline-0.collector.wireboard.io', {
    appId: 'cmOvSUIF',
    forceSecureTracker: true,
    useCookies: false,
    contexts: {
      performanceTiming: true,
    }
});
window.wireboard('enableActivityTracking', 5, 10);
var customContext=[{schema:'wb:io.wireboard/publisher',data:{publisher:'4efd8f4e-cc94-4802-a6bd-92ebecce357f'}}]
window.wireboard('trackPageView', null, customContext);
</script>"""


def head(title: str, description: str, canonical: str, og_image: str | None = None,
        extra_jsonld: list[dict] | None = None, body_class: str = "") -> str:
    jsonld_blocks = ""
    if extra_jsonld:
        for ld in extra_jsonld:
            jsonld_blocks += f'\n<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    jsonld_blocks += f'\n<script type="application/ld+json">{json.dumps(jsonld_website(), ensure_ascii=False)}</script>'
    og_img_tag = f'<meta property="og:image" content="{esc(og_image)}">' if og_image else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
{WIREBOARD_TAG}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="author" content="{esc(AUTHOR_NAME)}">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#20232a" media="(prefers-color-scheme: dark)">
<link rel="canonical" href="{esc(canonical)}">
<link rel="icon" href="{FAVICON_URL}" type="image/png">
<link rel="shortcut icon" href="{FAVICON_URL}" type="image/png">
<link rel="apple-touch-icon" href="{FAVICON_URL}">
<link rel="preload stylesheet" as="style" href="{PARENT_URL}/css/fonts.css">
<link rel="preload stylesheet" as="style" href="{PARENT_URL}/css/main.css">
<link rel="preload stylesheet" as="style" href="{PARENT_URL}/css/photos-masonry.css">
<link rel="preload stylesheet" as="style" href="{PARENT_URL}/custom.css">
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
    <h1 class="site-title"><a href="{PARENT_URL}/" class="u-url">
      <img src="https://avatars.micro.blog/avatars/2025/36/1810674.jpg" alt="" class="u-photo" id="avatar" width="28" height="28">impermanente
    </a></h1>
    <ul class="nav-menu">
      <li class="nav-item"><a href="{PARENT_URL}/about/">Acerca de</a></li>
      <li class="nav-item"><a href="{PARENT_URL}/blog/">Blog</a></li>
      <li class="nav-item"><a href="{SITE_URL}/" class="current">Fotos</a></li>
      <li class="nav-item"><a href="{PARENT_URL}/viajes/">Viajes</a></li>
      <li class="nav-item"><a href="{PARENT_URL}/lecturas/">Lecturas</a></li>
      <li class="nav-item"><a href="{PARENT_URL}/mastodon/">Cortos</a></li>
      <li class="nav-item"><a href="{PARENT_URL}/hispania-obscura/">Libros</a></li>
    </ul>
    <div class="hamburger" aria-label="Abrir menú" role="button" tabindex="0">
      <span class="bar"></span>
      <span class="bar"></span>
      <span class="bar"></span>
    </div>
  </nav>
</header>
<main>
"""


def footer() -> str:
    return f"""</main>
<footer>
    <p>&copy;2023&nbsp;-&nbsp;2026 J.R. Cruciani</p>
<p><a href="https://www.buymeacoffee.com/jrcruciani" target="_blank" rel="noopener" class="btn-coffee">🍕 Invítame una pizza</a></p><p>Suscribirse por&nbsp;<a href="{PARENT_URL}/feed.xml">RSS</a></p>
</footer>
<script>
(function(){{
  const h = document.querySelector('.hamburger');
  const m = document.querySelector('.nav-menu');
  if (!h || !m) return;
  function toggle(){{ h.classList.toggle('active'); m.classList.toggle('active'); }}
  h.addEventListener('click', toggle);
  h.addEventListener('keydown', e => {{ if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); toggle(); }} }});
  document.querySelectorAll('.nav-menu a').forEach(a => a.addEventListener('click', () => {{
    h.classList.remove('active'); m.classList.remove('active');
  }}));
}})();
</script>
</body>
</html>
"""


# ---------- JSON-LD constructors ----------

def jsonld_website() -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": SITE_URL + "/#website",
        "url": SITE_URL + "/",
        "name": "impermanente — fotos",
        "description": "Galería estática de fotografías de J.R. Cruciani publicadas originalmente en Pixelfed.",
        "inLanguage": "es",
        "author": {"@id": AUTHOR_ID},
        "publisher": {"@id": AUTHOR_ID},
        "isPartOf": {"@id": "https://impermanente.es/#website"},
        "sameAs": PIXELFED_USER_URL,
    }


def jsonld_imageobject(p: dict) -> dict:
    """Un ImageObject completo por foto."""
    node = {
        "@type": ["ImageObject", "Photograph"],
        "@id": photo_url(p["status_id"]) + "#image",
        "contentUrl": p["image_url"],
        "thumbnailUrl": p["preview_url"],
        "url": photo_url(p["status_id"]),
        "description": p["alt_text"],
        "creditText": AUTHOR_NAME,
        "copyrightNotice": f"© {AUTHOR_NAME}",
        "license": LICENSE_URL,
        "creator": {"@id": AUTHOR_ID},
        "isPartOf": {"@id": SERIES_ID},
        "inLanguage": "es",
    }
    caption = (p.get("content_text") or "").strip().split("\n")[0]
    if caption:
        node["caption"] = caption
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
        "isPartOf": {"@id": SITE_URL + "/#website"},
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


def jsonld_collectionpage(coll: dict, items: list[dict], canonical: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "@id": canonical + "#page",
        "url": canonical,
        "name": coll["title"],
        "description": coll.get("description") or "",
        "isPartOf": {"@id": SERIES_ID},
        "inLanguage": "es",
        "mainEntity": {
            "@type": "ImageGallery",
            "@id": canonical + "#gallery",
            "name": coll["title"],
            "numberOfItems": len(items),
            "image": [jsonld_imageobject(p) for p in items],
        },
    }


# ---------- Renderers ----------

def render_collections(collections: list[dict]) -> str:
    if not collections:
        return ""
    cards = []
    for c in collections:
        local_thumb = IMAGES_CACHE_DIR / f"coll_{c['id']}.jpg"
        thumb_src = f"/img/coll_{c['id']}.jpg" if local_thumb.exists() else (c.get('thumb_url') or '')
        cards.append(f"""<a href="/coleccion/{esc(c['slug'])}/" class="collection-card">
  <img src="{esc(thumb_src)}" alt="{esc(c['title'])}" loading="lazy">
  <span class="collection-name">{esc(c['title'])}</span>
</a>""")
    return f"""<h2 class="section-title">Colecciones</h2>
<div class="collections-grid">
{''.join(cards)}
</div>
"""


def render_collection_page(coll: dict, items: list[dict]) -> str:
    title = f"{coll['title']} | impermanente"
    description = coll.get("description") or f"Colección «{coll['title']}» de J.R. Cruciani — {len(items)} fotografías."
    canonical = f"{SITE_URL}/coleccion/{coll['slug']}/"

    page_jsonld = [
        jsonld_collectionpage(coll, items, canonical),
        jsonld_breadcrumbs([
            ("Fotos", SITE_URL + "/"),
            ("Colecciones", SITE_URL + "/#colecciones"),
            (coll["title"], canonical),
        ]),
    ]

    og_img_url = None
    local_thumb = IMAGES_CACHE_DIR / f"coll_{coll['id']}.jpg"
    if local_thumb.exists():
        og_img_url = f"{SITE_URL}/img/coll_{coll['id']}.jpg"
    elif coll.get("thumb_url"):
        og_img_url = coll["thumb_url"]

    body = head(title, description[:200], canonical, og_img_url, extra_jsonld=page_jsonld)
    body += '<nav class="breadcrumb" aria-label="breadcrumb"><a href="/">Fotos</a> · <span>Colecciones</span> · <span>{}</span></nav>\n'.format(esc(coll["title"]))
    body += f'<h1 class="collection-title">{esc(coll["title"])}</h1>\n'
    if coll.get("description"):
        body += f'<p class="collection-description">{esc(coll["description"])}</p>\n'
    body += f'<p class="collection-meta">{len(items)} fotografías</p>\n'
    if not items:
        body += '<p>Esta colección aún no tiene fotos disponibles.</p>\n'
    else:
        body += render_gallery(items)
    body += footer()
    return body


def render_gallery(items: list[dict]) -> str:
    parts = []
    for p in items:
        date = fmt_date_es(p.get("created_at"))
        date_iso = p.get("created_at") or ""
        place_str = fmt_place(p.get("place"))
        entry_name = (p.get("content_text") or "").strip().split("\n")[0]
        if not entry_name:
            entry_name = p["alt_text"][:80].rstrip(",;:.")

        meta_parts = []
        if place_str:
            meta_parts.append(f'<span class="photo-place p-location">{esc(place_str)}</span>')
        if date:
            meta_parts.append(f'<time class="dt-published" datetime="{esc(date_iso)}">{esc(date)}</time>')
        meta_line = ('<span class="photo-meta-line">' + ' · '.join(meta_parts) + '</span>') if meta_parts else ''

        dim_attrs = (' width="' + str(p['meta'].get('width')) + '" height="' + str(p['meta'].get('height')) + '"') if p['meta'].get('width') else ''
        # Galería: usa thumb local (1024px max, aspect natural) si existe.
        # Fallback al preview_url remoto solo si la cache está vacía.
        local_thumb = IMAGES_CACHE_DIR / f"{p['media_id']}.jpg"
        thumb_src = f"/img/{p['media_id']}.jpg" if local_thumb.exists() else p['preview_url']
        # Emitimos `class="loaded"` en <li> y `class="visible"` en <img>
        # para que el CSS del blog (photos-masonry.css) muestre la foto
        # inmediatamente sin esperar al JS de loading que el blog usa.
        parts.append(f"""<li class="loaded h-entry">
  <a href="{esc(photo_url(p['status_id']))}" class="u-url">
    <img src="{esc(thumb_src)}" alt="{esc(p['alt_text'])}" loading="lazy" class="visible u-photo"{dim_attrs}>
    <span class="p-name visually-hidden" aria-hidden="true">{esc(entry_name)}</span>
    <div class="photo-info">
      {meta_line}
    </div>
  </a>
</li>""")
    return f'<ul class="masonry-grid h-feed">\n{"".join(parts)}\n</ul>'


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
                      include_collections: bool, collections: list[dict] | None = None) -> str:
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
  <p>Archivo curado de fotografías publicadas originalmente en Pixelfed: umbrales, calle, ciudades, retratos, cementerios y luz dorada; mi manera de mirar lo que está a punto de cambiar, desaparecer o quedarse un segundo más.</p>
</div>
<hr class="section-divider" aria-hidden="true">
"""
        if include_collections:
            body += render_collections(collections or [])
        body += '<h2 class="section-title">Últimas fotos</h2>\n'
    else:
        body += f'<h1 class="section-title">Archivo de fotos · página {page}</h1>\n'

    body += render_gallery(page_items)
    body += render_pagination(page, total_pages)
    body += f"""<div class="pixelfed-cta">
  <a href="{PIXELFED_USER_URL}" target="_blank" rel="noopener" class="btn-pixelfed">
    Seguir el feed original en Pixelfed
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

    place_str = fmt_place(p.get("place"))
    date_str = fmt_date_es(p.get("created_at"))
    date_iso = p.get("created_at") or ""
    meta_bits = []
    if place_str:
        meta_bits.append(f'<span class="p-location">{esc(place_str)}</span>')
    if date_str:
        meta_bits.append(f'Publicada el <time class="dt-published" datetime="{esc(date_iso)}">{esc(date_str)}</time>')
    meta_bits.append(f'<a href="{esc(p["status_url"])}" target="_blank" rel="noopener">Ver en Pixelfed</a>')

    body += f"""<article class="h-entry">
  <h1 class="p-name visually-hidden">{esc(title_short)}</h1>
  <a href="{esc(canonical)}" class="u-url visually-hidden" tabindex="-1" aria-hidden="true">Permalink</a>
  <div class="photo-hero">
    <a href="{esc(p['image_url'])}" rel="noopener">
      <img src="{esc(p['image_url'])}" alt="{esc(p['alt_text'])}" loading="eager" class="u-photo"{dim_attrs}>
    </a>
  </div>
  <div class="photo-text e-content">
    {esc(p['alt_text'])}
  </div>
  <div class="photo-meta">
    {' · '.join(meta_bits)}
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


def render_sitemap(items: list[dict], total_pages: int, collections: list[dict] | None = None) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    urls = [
        (SITE_URL + "/", today, "weekly", "1.0"),
        (SITE_URL + "/okf/", today, "weekly", "0.7"),
    ]
    for n in range(2, total_pages + 1):
        urls.append((f"{SITE_URL}/p/{n}/", today, "weekly", "0.7"))
    for c in (collections or []):
        if c.get("status_ids"):
            lastmod = (c.get("updated_at") or today)[:10]
            urls.append((f"{SITE_URL}/coleccion/{c['slug']}/", lastmod, "weekly", "0.7"))
    for p in items:
        urls.append((photo_url(p["status_id"]), (p.get("created_at") or today)[:10], "monthly", "0.6"))
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url, lastmod, freq, prio in urls:
        body += f'<url><loc>{esc(url)}</loc><lastmod>{lastmod}</lastmod><changefreq>{freq}</changefreq><priority>{prio}</priority></url>\n'
    body += '</urlset>\n'
    return body


def render_llms_txt(items: list[dict], collections: list[dict] | None = None) -> str:
    """llms.txt nativo del subdominio (la convención es por host).

    El llms.txt del blog (impermanente.es) NO cubre este origen, así que
    fotos.impermanente.es necesita el suyo para ser visible en esa ruta.
    """
    n = len(items)
    by_slug = {c.get("slug"): c for c in (collections or [])}
    lines = [
        "# fotos.impermanente.es",
        "",
        f"> Galería estática de la obra fotográfica de {AUTHOR_NAME} (@HispaniaObscura en "
        "Pixelfed): umbrales, calle, ciudades, retrato, cementerios y golden hour. Cada "
        "fotografía lleva un alt-text evocativo en la voz del autor, pensado para ser legible "
        "por personas y por modelos de lenguaje. Español, licencia Creative Commons Attribution 4.0.",
        "",
        f"Sitio hermano del cuaderno {PARENT_URL} (que tiene su propio llms.txt). Aquí vive "
        "exclusivamente el archivo fotográfico, renderizado como HTML estático (sin JavaScript "
        "para mostrar las fotos) con JSON-LD `ImageObject` por foto. El repositorio canónico de "
        f"origen es Pixelfed: {PIXELFED_USER_URL}.",
        "",
        f"- **Autor**: {AUTHOR_NAME} — fotógrafo y escritor radicado en España. Royal Photographic Society (RPS).",
        "- **Idioma**: español.",
        "- **Marca personal**: *umbrales* — arcos, túneles, pasajes y orillas como espacios de tránsito.",
        f"- **Fotografías publicadas**: {n}, todas con alt-text.",
        f"- **Licencia**: Creative Commons Attribution 4.0 ({LICENSE_URL}).",
        "",
        "## Colecciones",
        "",
    ]
    order = COLLECTION_ORDER + [s for s in by_slug if s not in COLLECTION_ORDER]
    for slug in order:
        c = by_slug.get(slug)
        if not c or not c.get("status_ids"):
            continue
        count = len(c["status_ids"])
        blurb = COLLECTION_BLURBS.get(slug) or (c.get("description") or "").strip()
        url = f"{SITE_URL}/coleccion/{slug}/"
        suffix = f": {blurb}" if blurb else ""
        lines.append(f"- [{c.get('title') or slug}]({url}) ({count} fotos){suffix}")
    lines += [
        "",
        "## Recursos para máquinas",
        "",
        f"- [Índice completo del sitio (sitemap)]({SITE_URL}/sitemap.xml) — todas las páginas de foto y colección.",
        f"- [Feed JSON]({SITE_URL}/feed.json) — últimas fotos con su alt-text en `media_attachments[].description`.",
        f"- [Bundle Open Knowledge Format (OKF)]({SITE_URL}/okf/) — el archivo fotográfico como conjunto de archivos markdown con frontmatter, legible y clonable por agentes.",
        f"- [Página principal de la galería]({SITE_URL}/) — todas las fotos paginadas.",
        f"- [Repositorio fotográfico de origen en Pixelfed]({PIXELFED_USER_URL}).",
        "",
        "## Sobre el alt-text",
        "",
        "El texto alternativo de cada foto no es una descripción neutra: es una lectura breve "
        "y evocativa en la voz del autor (mono no aware, la atención a lo que está a punto de "
        "desaparecer). Se sirve por triplicado —atributo `alt` de la imagen, prosa visible bajo "
        "la foto y campo `description` del JSON-LD `ImageObject`— para que cualquier agente lo "
        "encuentre sin ejecutar JavaScript.",
        "",
        f"## Más sobre {AUTHOR_NAME}",
        "",
        f"- [Cuaderno principal]({PARENT_URL}/) — escritura, viajes, lecturas e impermanencia (tiene su propio llms.txt).",
        "- [Mastodon](https://masto.impermanente.es/@jrcruciani)",
        "- [micro.blog](https://micro.blog/JRCruciani)",
        "- [GitHub](https://github.com/Jrcruciani)",
        "",
    ]
    return "\n".join(lines)


def render_robots() -> str:
    return f"""User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: anthropic-ai
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: CopilotBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: GoogleOther
Allow: /

User-agent: Google-Agent
Allow: /

User-agent: Google-NotebookLM
Allow: /

User-agent: MistralAI-User
Allow: /

User-agent: MistralAI-Index
Allow: /

User-agent: Meta-ExternalAgent
Allow: /

User-agent: Meta-ExternalFetcher
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


def okf_scalar(value: str | None) -> str:
    return json.dumps(" ".join((value or "").split()), ensure_ascii=False)


def okf_frontmatter(fields: dict[str, object]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {okf_scalar(str(item))}")
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: {okf_scalar(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def okf_description(text: str | None, limit: int = 140) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


def okf_photo_title(photo: dict) -> str:
    place = fmt_place(photo.get("place"))
    date = fmt_date_es(photo.get("created_at"))
    if place and date:
        return f"{place} · {date}"
    if place:
        return place
    if date:
        return f"Fotografía · {date}"
    return okf_description(photo.get("alt_text"), 80) or f"Fotografía {photo['status_id']}"


def okf_landing_html(n_photos: int, n_collections: int) -> str:
    # ponytail: puerta HTML para humanos; los agentes entran por index.md.
    return """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>impermanente fotos — bundle OKF</title>
<style>
:root{color-scheme:light dark}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;max-width:42rem;margin:3rem auto;padding:0 1.2rem;line-height:1.6;color:#3a3a3a;background:#faf8f5}
@media(prefers-color-scheme:dark){body{color:#e6e1da;background:#1a1816}}
a{color:#b07a5a;text-decoration:none}a:hover{text-decoration:underline}
code{background:rgba(128,128,128,.15);padding:.1em .35em;border-radius:.3em}
ul{padding-left:1.2rem}li{margin:.3rem 0}
.muted{opacity:.7;font-size:.9rem}
</style>
</head>
<body>
<h1>impermanente fotos — bundle OKF</h1>
<p>Esta carpeta es un <strong>bundle en Open Knowledge Format (OKF&nbsp;v0.1)</strong>:
una representación legible por agentes del archivo fotográfico, con un concepto en
markdown por cada fotografía y colección.</p>
<p>Entradas del bundle (markdown):</p>
<ul>
<li><a href="index.md">index.md</a> — entrada del bundle</li>
<li><a href="colecciones/index.md">colecciones/</a> — N_COLLECTIONS recorridos curados</li>
<li><a href="fotografias/index.md">fotografias/</a> — N_PHOTOS conceptos, uno por foto</li>
<li><a href="log.md">log.md</a> — historial</li>
</ul>
<p class="muted">¿Eres un agente? Empieza por <code>index.md</code>. Formato:
<a href="https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md">OKF&nbsp;SPEC</a>.</p>
<p><a href="SITE_URL_HERE">← Volver a la galería</a></p>
</body>
</html>
""".replace("N_COLLECTIONS", str(n_collections)).replace("N_PHOTOS", str(n_photos)).replace("SITE_URL_HERE", SITE_URL)


def build_okf(output_dir: Path, items: list[dict], collections: list[dict] | None = None) -> int:
    okf_dir = output_dir / "okf"
    collections = collections or []
    by_status = {p["status_id"]: p for p in items}
    collections_by_status: dict[str, list[tuple[str, str]]] = {}
    for c in collections:
        for sid in c.get("status_ids", []):
            collections_by_status.setdefault(sid, []).append((c["slug"], c.get("title") or c["slug"]))

    write(okf_dir / ".nojekyll", "")
    write(okf_dir / "index.md", okf_frontmatter({
        "okf_version": "0.1",
        "title": "impermanente fotos — OKF",
        "description": "Archivo fotográfico de HispaniaObscura en Open Knowledge Format.",
    }) + """# impermanente fotos — OKF

## Colecciones

* [Colecciones](/colecciones/) - recorridos curados por tema, luz y motivo.

## Fotografías

* [Fotografías](/fotografias/) - un concepto markdown por foto publicada.
""")
    write(okf_dir / "log.md", f"""# Log

## {datetime.now().astimezone().date().isoformat()}

* **Creación** del bundle OKF v0.1 con {len(items)} fotografías y {len(collections)} colecciones.
""")
    write(okf_dir / "index.html", okf_landing_html(len(items), len(collections)))

    photo_index = ["# Fotografías", ""]
    for p in items:
        title = okf_photo_title(p)
        photo_index.append(f"* [{title}]({p['status_id']}.md) - {okf_description(p.get('alt_text'))}")
        place = p.get("place") or {}
        tags = []
        for value in (place.get("name"), place.get("country")):
            if value and value not in tags:
                tags.append(value)
        for _, title_tag in collections_by_status.get(p["status_id"], []):
            if title_tag not in tags:
                tags.append(title_tag)
        collection_links = [f"[{title_tag}](/colecciones/{slug}.md)" for slug, title_tag in collections_by_status.get(p["status_id"], [])]
        body = okf_frontmatter({
            "type": "Fotografía",
            "title": title,
            "description": p.get("alt_text") or "",
            "resource": p.get("status_url") or "",
            "tags": tags,
            "timestamp": p.get("created_at") or "",
        })
        body += f"# {title}\n\n{p.get('alt_text') or ''}\n\n"
        place_str = fmt_place(p.get("place"))
        if place_str:
            body += f"**Lugar:** {place_str}\n\n"
        body += f"**Página:** [{photo_url(p['status_id'])}]({photo_url(p['status_id'])})\n\n"
        if collection_links:
            body += "**Colecciones:** " + ", ".join(collection_links) + "\n\n"
        body += f"![{p.get('alt_text') or title}]({p.get('image_url') or p.get('preview_url') or ''})\n"
        write(okf_dir / "fotografias" / f"{p['status_id']}.md", body)
    write(okf_dir / "fotografias" / "index.md", "\n".join(photo_index) + "\n")

    collection_index = ["# Colecciones", ""]
    concept_collections = 0
    for c in collections:
        coll_items = [by_status[sid] for sid in c.get("status_ids", []) if sid in by_status]
        description = COLLECTION_BLURBS.get(c["slug"]) or (c.get("description") or "").strip()
        title = c.get("title") or c["slug"]
        collection_index.append(f"* [{title}]({c['slug']}.md) - {okf_description(description)}")
        timestamp = c.get("updated_at") or c.get("published_at") or ""
        tags = [title]
        body = okf_frontmatter({
            "type": "Colección",
            "title": title,
            "description": description,
            "resource": f"{SITE_URL}/coleccion/{c['slug']}/",
            "tags": tags,
            "timestamp": timestamp,
        })
        body += f"# {title}\n\n{description}\n\n## Fotografías\n\n"
        for p in coll_items:
            body += f"* [{okf_photo_title(p)}](/fotografias/{p['status_id']}.md) - {okf_description(p.get('alt_text'))}\n"
        write(okf_dir / "colecciones" / f"{c['slug']}.md", body)
        concept_collections += 1
    write(okf_dir / "colecciones" / "index.md", "\n".join(collection_index) + "\n")
    return len(items) + concept_collections


# ---------- Main ----------

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build(output_dir: Path, items: list[dict], collections: list[dict] | None = None) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Copia los thumbs locales (1024px max, aspect natural) generados por
    # fetch_inventory.py. Sirven la galería sin recurrir al `_thumb.jpg`
    # cuadrado de Pixelfed que destroza el aspect ratio original.
    img_dest = output_dir / "img"
    if IMAGES_CACHE_DIR.exists():
        shutil.copytree(IMAGES_CACHE_DIR, img_dest)
        print(f"  [img] Copiados {sum(1 for _ in img_dest.iterdir())} thumbs a output/img/")
    else:
        img_dest.mkdir(parents=True, exist_ok=True)
        print("  [img] AVISO: data/images_cache no existe; la galería caerá a previews remotos")

    total_pages = max(1, (len(items) + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE)

    collections = collections or []

    # index + páginas paginadas
    for page in range(1, total_pages + 1):
        start = (page - 1) * PHOTOS_PER_PAGE
        end = start + PHOTOS_PER_PAGE
        page_items = items[start:end]
        html_str = render_index_page(page, total_pages, page_items,
                                     include_collections=(page == 1),
                                     collections=collections)
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

    # páginas por colección
    by_status = {p["status_id"]: p for p in items}
    coll_built = 0
    for c in collections:
        coll_items = [by_status[sid] for sid in c.get("status_ids", []) if sid in by_status]
        if not coll_items:
            print(f"  [coleccion] skip {c['slug']}: 0 fotos disponibles")
            continue
        html_str = render_collection_page(c, coll_items)
        write(output_dir / f"coleccion/{c['slug']}/index.html", html_str)
        coll_built += 1
    if collections:
        print(f"  [coleccion] {coll_built}/{len(collections)} páginas de colección")

    # sitemap, robots, feed
    okf_concepts = build_okf(output_dir, items, collections)
    print(f"  [okf] {okf_concepts} conceptos en output/okf/")
    write(output_dir / "sitemap.xml", render_sitemap(items, total_pages, collections))
    write(output_dir / "robots.txt", render_robots())
    write(output_dir / "llms.txt", render_llms_txt(items, collections))
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

    collections = sort_collections(load_jsonl(COLLECTIONS_PATH))

    build(args.out, items, collections)
    try:
        out_label = args.out.relative_to(ROOT)
    except ValueError:
        out_label = Path(args.out.name)
    print(f"Sitio generado en {out_label}/")
    print(f"  - {len(items)} fotos")
    print(f"  - {(len(items) + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE} páginas paginadas")
    print(f"  - {len(items)} páginas individuales")
    print(f"  - {len(collections)} colecciones")
    print(f"  - sitemap.xml, robots.txt, llms.txt, okf/, feed.json, 404.html, CNAME")


if __name__ == "__main__":
    main()
