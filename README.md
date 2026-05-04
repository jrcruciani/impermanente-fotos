# impermanente-fotos

Pipeline para generar y publicar **alt-text evocativo** en las fotos de [@HispaniaObscura en Pixelfed](https://pixelfed.social/HispaniaObscura), y servir un sitio estático rico crawlable en [`fotos.impermanente.es`](https://fotos.impermanente.es/).

> 🤖 **Para asistentes IA / sesiones futuras:** leer **[AGENTS.md](./AGENTS.md)** primero. Ahí está el runbook operativo completo (qué hacer cuando JR sube fotos nuevas, quirks de Pixelfed, troubleshooting, anatomía de los datos).

## ¿Qué hace?

1. **Lee Pixelfed** y construye un inventario de cada foto (`scripts/fetch_inventory.py`).
2. **Genera alt-text** descriptivo + evocativo para cada foto sin descripción, aplicando un style guide y QA automático.
3. **Publica** los alt-texts en Pixelfed via `PUT /api/v1/media/:id` con read-after-write (`scripts/publish.py`).
4. **Construye un sitio estático** con todas las fotos paginadas, JSON-LD por foto, sitemap y robots (`scripts/build_site.py`). Hereda directamente el theme visual del blog (`https://impermanente.es/custom.css`) para verse igual que `impermanente.es`.
5. **Despliega** a GitHub Pages → `fotos.impermanente.es`. El menú "Fotos" del blog en micro.blog hace meta-refresh hacia este sitio.

## Estructura

```
impermanente-fotos/
├── data/
│   ├── inventory.jsonl        # Catálogo Pixelfed (media_id → metadata)
│   ├── generated.jsonl        # Alt-texts generados con QA
│   ├── published.jsonl        # Log de publicaciones
│   └── images_cache/          # Fotos descargadas (gitignored)
├── prompt/                    # Prompt maestro para el LLM
├── style-guide/               # Style guide consolidado (voz JR)
├── scripts/
│   ├── fetch_inventory.py     # Pixelfed → inventory.jsonl
│   ├── next_batch.py          # Lista próximas pendientes
│   ├── append_generated.py    # Añade alt-texts con QA
│   ├── qa.py                  # Reglas de QA (longitud, blacklist, etc.)
│   ├── publish.py             # Publica en Pixelfed con read-after-write
│   ├── build_site.py          # Genera sitio estático en output/
│   ├── oauth_setup.py         # Setup inicial OAuth Pixelfed
│   └── smoke_test.py          # Test exhaustivo del endpoint de escritura
├── output/                    # Sitio estático (gitignored, deployed por Action)
└── .github/workflows/build.yml
```

## Operación

### Local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install requests

# Fetch inventario actualizado
python3 scripts/fetch_inventory.py

# Ver pendientes
python3 scripts/next_batch.py 10

# Generar alt-texts (necesita LLM con vision; ver prompt/)
# Workflow actual: cargar imágenes con vision tool y llamar append_generated.py

# Publicar a Pixelfed
python3 scripts/publish.py --dry-run --sample 5

# Construir sitio
python3 scripts/build_site.py

# Servir local
cd output && python3 -m http.server 8080
```

### CI/CD (GitHub Actions)

`.github/workflows/build.yml` se ejecuta en cron y push a `main`:
- Fetch inventario delta.
- Genera + publica alt-texts pendientes (si la generación CI está habilitada).
- Construye `output/`.
- Deploy a `gh-pages` → GitHub Pages → `fotos.impermanente.es`.

### Secrets requeridos

En **Settings → Secrets and variables → Actions**:
- `PIXELFED_INSTANCE` — `pixelfed.social`
- `PIXELFED_USERNAME` — `HispaniaObscura`
- `PIXELFED_ACCOUNT_ID` — id numérico de la cuenta
- `PIXELFED_ACCESS_TOKEN` — bearer token (scopes `read write`)
- `PIXELFED_CLIENT_ID` / `PIXELFED_CLIENT_SECRET` — opcional, si refrescas tokens

## Endpoint Pixelfed validado

Smoke test exhaustivo en `SMOKE_TEST_RESULTS.md`. Endpoint útil:

```
PUT https://pixelfed.social/api/v1/media/:id
Authorization: Bearer …
Content-Type: application/x-www-form-urlencoded

description=texto…
```

Verificación: `GET /api/v1/statuses/:status_id` → buscar el media en `media_attachments` y comparar `description` (con `html.unescape()` por `&amp;`).

## Licencia

Código: MIT.
Fotografías: CC BY 4.0 (J.R. Cruciani).
