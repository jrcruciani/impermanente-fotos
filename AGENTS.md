# AGENTS.md — Runbook operativo para sesiones IA

> Este documento es la **fuente de verdad** para cualquier asistente IA (Copilot CLI, Claude, etc.) que retome operación sobre este repo. Si una sesión se pierde, leer esto primero permite continuar sin contexto.

---

## 0. Contexto del proyecto en una pantalla

**Objetivo:** que las fotos de [`@HispaniaObscura` en Pixelfed](https://pixelfed.social/HispaniaObscura) tengan **alt-text evocativo** (no solo descriptivo) en la voz de J.R. Cruciani, indexable por crawlers/LLMs.

**Pipeline:**
```
Pixelfed (fuente)
   │
   ▼  fetch_inventory.py   (pull metadata via API + descarga imágenes)
inventory.jsonl
   │
   ▼  generación con LLM-vision (manual con sesión IA)  →  qa.py  →  append_generated.py
generated.jsonl
   │
   ▼  publish.py  (PUT /api/v1/media/:id  con read-after-write)
Pixelfed actualizado
   │
   ▼  build_site.py  (genera output/ estático)
fotos.impermanente.es  (GitHub Pages, cron 6h)
```

**Cobertura actual:** 154/154 fotos con alt-text publicado, verificado en 7 surfaces (API, SSR, ActivityPub, feed.json, etc.).

---

## 1. Cuándo activarme (triggers desde JR)

| JR dice | Hago |
|---|---|
| "tengo fotos nuevas en Pixelfed", "procesa las fotos nuevas" | Workflow §3 completo |
| "actualiza el inventario" | Solo `fetch_inventory.py` y reporto pendientes |
| "republica esta foto" `<id>` | `publish.py --media-ids X --force` |
| "regenera el sitio" | `build_site.py` + `git push` (Action despliega) |
| "qué falta por hacer" | `next_batch.py` + reporte |
| "valida cobertura" | Probes a los 7 surfaces (ver §6) |
| "cambia el style guide" | Edit `style-guide/STYLE_GUIDE.md` + `prompt/MASTER_PROMPT.md`, NO regenero retroactivamente salvo que JR lo pida explícito |

---

## 2. Setup y credenciales

**Path repo:** `~/Proyectos/impermanente-alttext`
**venv:** `~/Proyectos/impermanente-alttext/.venv` con `requests`, `Pillow`
**Credenciales Pixelfed:** `~/.config/hispania-obscura/.env`

Variables esperadas:
```bash
PIXELFED_INSTANCE="pixelfed.social"
PIXELFED_USERNAME="HispaniaObscura"
PIXELFED_ACCOUNT_ID="783480968440772334"
PIXELFED_ACCESS_TOKEN="<JWT, válido hasta 2027>"
PIXELFED_CLIENT_ID="..."   # opcional, solo para refresh
PIXELFED_CLIENT_SECRET="..."  # opcional
```

**Activar venv siempre:**
```bash
cd ~/Proyectos/impermanente-alttext && source .venv/bin/activate
set -a && source ~/.config/hispania-obscura/.env && set +a
```

**Cuenta GitHub activa (gh CLI):** `jrcruciani`
**Repo:** `Jrcruciani/impermanente-fotos` (público).

---

## 3. Workflow completo: "procesa las fotos nuevas"

### 3.1. Sync local con remoto
```bash
cd ~/Proyectos/impermanente-alttext && source .venv/bin/activate
git pull --rebase origin main
```

### 3.2. Refrescar inventario desde Pixelfed
```bash
python3 scripts/fetch_inventory.py
```
- Usa `?_pe=1` (Pixelfed Extended) — devuelve `place: {id, slug, name, country}` que la API estándar oculta.
- Descarga imágenes nuevas a `data/images_cache/` (max 1024px, JPEG q85).
- Reporta pendientes (`description=null`).

### 3.3. Listar lo que falta
```bash
python3 scripts/next_batch.py 20
```
Output: lista de `media_id` con `image_url`, `place`, `content_text`, `status_id`.

### 3.4. Generar alt-text (paso manual, requiere LLM-vision)

Para cada pendiente:
1. **Ver la imagen** con la herramienta `view` (path en `data/images_cache/`).
2. **Aplicar style guide** (`style-guide/STYLE_GUIDE.md`) y MASTER_PROMPT (`prompt/MASTER_PROMPT.md`).
3. **Estructura del alt-text:**
   - 200–500 chars (target ~300)
   - Anclaje visual concreto → gesto/tensión → eco breve no solemne
   - **CERO nombres geográficos** (sí permitido nombrar objetos/edificios genéricamente: "centro comercial", "palacio fortificado", "puente colgante")
   - Voz JR: aforismo + matiz, observacional, sin pose
4. **Validación local con `qa.py`** antes de añadir:
   ```python
   from scripts.qa import qa_check
   result = qa_check(alt_text)
   # result = {"passed": bool, "issues": [...]}
   ```

### 3.5. Añadir a generated.jsonl

`append_generated.py` espera registros con campos: `media_id`, `status_id`, `image_url`, `alt_text`, `place`, `content_text`, `created_at`.

```bash
# Vía stdin (preferido):
cat <<'EOF' | python3 scripts/append_generated.py BATCH_NAME
[
  {
    "media_id": "12345",
    "status_id": "9876543210",
    "image_url": "https://...",
    "alt_text": "Texto generado...",
    "place": {"name": "Madrid", "country": "Spain"},
    "content_text": "",
    "created_at": "2026-05-01T12:00:00.000Z"
  }
]
EOF
```

⚠ **No existe `--records-file`**, solo `--records JSON` o stdin.
⚠ Si `created_at` es `None`, `append_generated.py` falla con TypeError al ordenar — siempre pasa `created_at` aunque sea de `inventory.jsonl`.

### 3.6. Publicar a Pixelfed
```bash
python3 scripts/publish.py --dry-run --media-ids 12345,67890   # simula
python3 scripts/publish.py --media-ids 12345,67890              # real
```

**Comportamiento:**
- Endpoint: `PUT /api/v1/media/:id` form-encoded `description=...`
- Throttle: 4s entre requests (rate limit Pixelfed agresivo)
- Retry: hasta 6 con `Retry-After` header en 429s, base 30s
- Verify: `GET /api/v1/statuses/:status_id` → busca media en `media_attachments` → compara `description` con `html.unescape()` (Pixelfed convierte `&` → `&amp;` al persistir)

**Otros flags útiles:**
- `--sample N` — muestra aleatoria con seed
- `--limit N` — primeras N pendientes
- `--force` — reescribe aunque ya esté publicado

### 3.7. Commit y push
```bash
git add data/inventory.jsonl data/generated.jsonl data/published.jsonl
git commit -m "alt-text: BATCH_NAME (N fotos)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

El push dispara el workflow → ~1 min build + ~5–10 min CDN cache → live en `fotos.impermanente.es`.

### 3.8. Validación post-push (opcional pero recomendado)
```bash
# Esperar 2 min, luego:
curl -s "https://fotos.impermanente.es/feed.json?cb=$(date +%s)" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} posts | {sum(1 for p in d if (p.get(\"media_attachments\") or [{}])[0].get(\"description\"))} con alt')"
```

---

## 4. Style guide — reglas duras del alt-text

Resumen ejecutable. Detalle en `style-guide/STYLE_GUIDE.md`.

### Estructura
1. **Anclaje visual concreto** (1–2 frases) — qué hay, cómo está dispuesto, paleta/luz si añade.
2. **Gesto / tensión / dirección** — la cosa que el ojo persigue, no decorativa.
3. **Eco breve no solemne** — máximo 1 término-marca o ninguno; preferible un giro coloquial de cierre.

### Blacklist (rechaza `qa.py`)
`captura/captur*`, `muestra*`, `retrato*` (como verbo), `plasma*`, `congela*`, `evoca*`, `mágico*`, `único*`, `especial*`, `increíble*`, `impactante*`, `hermoso/bello*`, `espectacular*`, `impresionante*`, `esta imagen`, `en esta fotografía`, `una toma que`, `la fotografía nos/invita/captura`, `este momento`, `para siempre`, `el alma de`, `la esencia de`, `atrapar el instante`, **emojis**, **exclamaciones**.

Sustitutos para "única": *mejor, principal, más honesta/fiel/limpia*.

### Términos-marca (máx 1 por alt-text, mejor ninguno)
*umbral, mono no aware (物の哀れ), impermanencia, anicca, polytropos*.

### Verbos suyos (preferidos)
*enfocar, triangular, encajar, atravesar, ceder, contemplar, revisar, expulsar, apoyarse, aparecer*.

### Reglas extra
- **CERO nombres geográficos** (la ubicación va en el campo `place` aparte).
- **Identificación de objetos sí permitida** ("Coliseo", "Big Ben", "Aljafería como palacio fortificado") — pero ojo, mejor descriptivo si el objeto es local.
- Longitud target: 200–500 chars. Avg histórico: 309. Min 192, Max 418.

---

## 5. Pixelfed — quirks aprendidos

| Quirk | Workaround |
|---|---|
| `/api/v1/statuses/:id` oculta `place` (Mastodon-compat) | Añadir **`?_pe=1`** (Pixelfed Extended) |
| `/api/v1/media/:id` da 404 después de cerrar sesión upload (`No query results for model [App\Media] X`) | Usar `/api/v1/statuses/:status_id` y buscar en `media_attachments` |
| Pixelfed convierte `&` → `&amp;` al persistir descriptions | `html.unescape()` antes de comparar |
| Rate limit agresivo: 1 req/s = 429 "Try again in a few minutes" | Throttle ≥4s + retry con `Retry-After` |
| `media_attachments[].description` puede llegar `null` aunque exista en BD si no usas `_pe=1` | Mismo fix: `?_pe=1` en GETs |
| Endpoint validado para escritura | `PUT /api/v1/media/:id` form-encoded `description=...` |

---

## 6. Validación rápida — los 7 surfaces

Cuando JR pida "valida cobertura", probar:

```bash
# A) Pixelfed API (fuente)
curl -s "https://pixelfed.social/api/v1/accounts/$PIXELFED_ACCOUNT_ID/statuses?limit=10&_pe=1" \
  -H "Authorization: Bearer $PIXELFED_ACCESS_TOKEN" | jq '.[].media_attachments[].description' | head

# B) fotos.impermanente.es gallery
curl -s https://fotos.impermanente.es/ | grep -oE 'alt="[^"]{80,}"' | head -3

# C) Página individual SSR
curl -s https://fotos.impermanente.es/foto/<status_id>/ | grep -oE 'alt="[^"]+"' | head

# D) feed.json
curl -s https://fotos.impermanente.es/feed.json | jq '.[0].media_attachments[0].description'

# E) impermanente.es/fotos/ — meta-refresh a fotos.impermanente.es
#    El menú "Fotos" del blog redirige aquí; ya no hay galería embebida.
curl -s https://impermanente.es/fotos/ | grep -oE 'fotos\.impermanente\.es' | head -1
# F) Pixelfed HTML público (Pixelfed es SPA, no renderiza alt en SSR — esperado vacío)
# G) ActivityPub (federación a Mastodon)
curl -s https://pixelfed.social/p/$PIXELFED_USERNAME/<status_id> \
  -H "Accept: application/activity+json" | jq '.attachment[].name'
```

---

## 6.bis. Diseño visual: heredado del blog

`fotos.impermanente.es` carga directamente los 4 stylesheets del blog principal vía `<link rel="stylesheet">`:

- `https://impermanente.es/css/fonts.css` (declara la fuente "GTW", actualmente sin uso visible — el theme la sobreescribe)
- `https://impermanente.es/css/main.css` (base + tokens del diseño Hugo)
- `https://impermanente.es/css/photos-masonry.css` (grid de fotos)
- `https://impermanente.es/custom.css` (theme **"Magnum"**: Lora serif + Inter sans, paleta blanco/negro/teal, footer negro)

**Mi `<style>` embebido** queda DESPUÉS en el `<head>` y solo añade reglas para componentes únicos de la galería (`.photo-grid`, `.photo-info`, `.photo-caption`, `.photo-meta-line`, paginación, página individual de foto). Reutiliza las variables del blog (`--serif`, `--sans`, `--bg`, `--text`, `--heading`, `--accent`, `--separator`, `--caption`, `--muted`, `--footer-bg`).

**Beneficio:** si JR cambia el theme del blog, `fotos.impermanente.es` se actualiza automáticamente sin tocar nada en este repo. Solo el cache CDN del blog (~10 min) y del navegador hacen de barrera temporal.

**HTML del header** (definido en `head()` de `build_site.py`) usa las clases idénticas al blog: `.header`, `.site-nav`, `.site-title`, `.u-photo`, `#avatar`, `.nav-menu`, `.nav-item`. Eso permite que el theme aplique sus estilos sin tener que duplicarlos.

**Si quieres romper el vínculo** (por ejemplo para hacer un re-skin local independiente): copia los 4 archivos a `output/css/` durante el build y cambia las URLs a relativas. Hoy NO está hecho.

---

## 7. CI/CD — qué hace el cron

**Workflow:** `.github/workflows/build.yml`
**Cron:** `17 */6 * * *` UTC (00:17, 06:17, 12:17, 18:17 — en CEST: 02:17, 08:17, 14:17, 20:17)

**Jobs:**
1. `fetch-and-publish`: `fetch_inventory.py` → si hay diff en `data/`, commit con `github-actions[bot]` y push.
   - **Ojo:** este job **NO genera alt-text** (no tiene LLM-vision). Solo refresca metadata + descarga imágenes nuevas. Si JR sube una foto sin alt, aparecerá en `fotos.impermanente.es` con caption pero **sin alt evocativo**.
2. `build-and-deploy`: `build_site.py` → push a branch `gh-pages` → GitHub Pages sirve.

**Trigger manual:**
```bash
gh workflow run build.yml --repo Jrcruciani/impermanente-fotos
```

**Latencia foto nueva → live:**
- Best case: ~10 min (cron + build + CDN cache 600s)
- Worst case: ~6h 10 min (justo después de un cron)
- Avg: ~3h
- Para alt-text evocativo: requiere sesión manual (§3).

---

## 8. Troubleshooting común

### "El feed.json no actualiza"
1. ¿El último cron pasó? `gh run list --repo Jrcruciani/impermanente-fotos --limit 5`
2. ¿CDN cacheado? Probar con `?cb=$(date +%s)`. Si tras 10 min no actualiza, forzar build.
3. ¿Pages errored? `gh api repos/Jrcruciani/impermanente-fotos/pages | jq .status`

### "Cert HTTPS no se emite"
- Estado normal tras DNS: `authorization_pending`. Tarda 1–60 min.
- Truco para nudgear: clear y re-set CNAME via API:
  ```bash
  gh api -X PUT repos/Jrcruciani/impermanente-fotos/pages -f "cname="
  sleep 3
  gh api -X PUT repos/Jrcruciani/impermanente-fotos/pages -f "cname=fotos.impermanente.es"
  ```

### "publish.py falla con 429 repetidos"
- Cooldown 5–10 min y reintentar. Si persiste, subir `RETRY_429_BASE` o `THROTTLE`.

### "El JS de /fotos/ en micro.blog se rompe con SyntaxError"
- micro.blog **decodifica entidades HTML dentro de `<script>`**. Histórico (cuando había una página `/fotos/` con JS embebido en micro.blog). Hoy `/fotos/` es solo un meta-refresh a `fotos.impermanente.es`. La regla queda anotada por si en el futuro vuelves a meter JS en alguna page de micro.blog.
- Patrón seguro para `esc()`: usar `document.createElement('div').textContent = ...` y construir entidades con `String.fromCharCode(38)` para el `&`.

### "fotos.impermanente.es no se ve igual que el blog"
- El sitio carga 4 stylesheets desde `https://impermanente.es/css/` y `/custom.css`. Si dejas de servirlos o cambia la URL, el sitio pierde el theme.
- Verificar que el blog responde 200 y con `access-control-allow-origin: *` (los CSS están en el mismo origin que el sitio que los pide vía cross-origin):
  ```bash
  curl -sI https://impermanente.es/custom.css | grep -i 'http\|access-control'
  ```
- Cache del navegador puede mantener una versión vieja del CSS — hard refresh (`Cmd+Shift+R`) tras un cambio en el blog.

### "Quiero regenerar todos los alt-text retroactivamente"
- NO se hace solo si JR lo pide explícito. Coste alto en tiempo y reescribe historia. Si confirmado: borrar `data/generated.jsonl`, re-ejecutar generación con `--force` en publish.

---

## 9. Anatomía de los datos

### `data/inventory.jsonl` (154 records)
Snapshot canónico de Pixelfed. Una línea = un media_attachment.
```json
{
  "media_id": "42237889",
  "status_id": "955881786576642347",
  "status_url": "https://pixelfed.social/p/HispaniaObscura/955881786576642347",
  "created_at": "2026-05-01T17:32:57.000Z",
  "image_url": "https://pxscdn.com/.../foo.jpg",
  "preview_url": "https://...",
  "description": null,           // alt-text actual en Pixelfed
  "place": {"id":31427,"slug":"madrid","name":"Madrid","country":"Spain"},
  "content_text": "",
  "meta": {...}
}
```

### `data/generated.jsonl` (154 records)
Alt-texts generados con QA. Source de verdad para `publish.py`.
```json
{
  "media_id": "...",
  "status_id": "...",
  "alt_text": "Texto evocativo...",
  "qa_status": "passed",
  "qa_issues": [],
  "batch": "BATCH_NAME",
  "generated_at": "2026-05-02T..."
}
```

### `data/published.jsonl` (append-only log)
Una línea por intento de publicación. `load_published()` toma la última por `media_id` (dict overwrite).
```json
{
  "media_id": "...",
  "status": "ok",        // ok | failed | dry_run
  "verified": true,
  "alt_text_sent": "...",
  "alt_text_verified": "...",
  "ts": "2026-05-02T..."
}
```

---

## 10. Identidades públicas

Toda mención del autor en este repo y en cualquier output (HTML generado, JSON-LD, commits) usa **solo** los aliases públicos:

| Surface | Alias |
|---|---|
| GitHub | `Jrcruciani` |
| Pixelfed | `HispaniaObscura` |
| micro.blog | `JRCruciani` |

⚠ Nunca incluir en commits, código, comentarios o documentación: el username del Mac local del operador, hostnames internos derivados de él, ni rutas absolutas tipo `/Users/<usuario>/...`. Usar siempre `~/...` (o `$HOME/...`), que resuelve dinámicamente.

---

## 11. Referencias

- **Style guide completo:** `style-guide/STYLE_GUIDE.md`
- **Master prompt LLM:** `prompt/MASTER_PROMPT.md`
- **Smoke test del endpoint de escritura:** `SMOKE_TEST_RESULTS.md`
- **README operativo:** `README.md`
- **Workflow CI:** `.github/workflows/build.yml`
- **Sitio live:** https://fotos.impermanente.es/
- **Repo:** https://github.com/Jrcruciani/impermanente-fotos
