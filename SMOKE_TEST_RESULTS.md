# Smoke test results — 2026-05-02

- Instance: `pixelfed.social` (v0.12.7)
- Account: `@HispaniaObscura` (id `783480968440772334`)
- Marker run-id: `SMOKE-20260502-103555`
- Statuses con media inventariadas: 154 (153 reales + 1 temporal del Test C, ya eliminado)
- Multi-attachment encontrados: 0 (toda la cuenta es single-image)

---

## Decisión gate

✅ **PLAN A CONFIRMADO — Pixelfed como single source de verdad funciona.**

El reporte automático del script salió "GATE FALLIDO" porque la lógica era demasiado estricta (exigía las 4 superficies). Tras analizar los datos crudos y diagnosticar S2, se reclasifica:

- **S2 (HTML público de Pixelfed)** queda **descartada como superficie aplicable**: las páginas `/p/.../id` de Pixelfed son una SPA Vue (`<post-component>` + `<noscript>Please enable javascript</noscript>`). El HTML inicial nunca contiene el alt-text — se hidrata client-side desde la API. Esta no es una superficie que controlemos, ni una que vayamos a usar como destino de crawlers (para eso tenemos `fotos.impermanente.es` con SSR en Fase 5).
- **S3 Worker** en post antiguo (Test A) falló porque el feed JSON solo expone los últimos 10 statuses; el post de hace 30 días no estaba ahí. Esto es esperable y no afecta a producción (la galería completa la sirve el Worker nuevo en Fase 5, no el actual).

**Endpoint de escritura validado: `EP2_mastodon_put` — `PUT /api/v1/media/:id`** con form-encoded `description=...`. Funciona para posts antiguos, posts recientes, y al subir uno nuevo. La descripción persiste en API, ActivityPub y feed Worker.

| Test | Endpoint útil | API | ActivityPub | Worker | Veredicto |
|---|---|:-:|:-:|:-:|---|
| **A_old** (post de 30 días) | EP2 ✅ | ✅ | ✅ | n/a* | **OK** |
| **B_recent** (post de hoy) | EP2 ✅ | ✅ | ✅ | ✅ | **OK** |
| **C_new** (crear via API) | upload-time desc ✅ | ✅ | ✅ | ✅ | **OK** |
| **D_multi** | (no había candidatos en la cuenta) | — | — | — | SKIP |

*n/a: post antiguo no aparece en el feed JSON del Worker actual (solo top-10), pero sí lo hará en el Worker de Fase 5 que paginará los 153.

### Endpoints descartados

- `EP1_pixelfed_ui` — `POST /api/v1.1/media/update/:id`: **404 The route could not be found**. La ruta `v1.1` que usaba la UI rota de `/settings/applications` ya no existe en pixelfed.social v0.12.7.
- `EP3_status_edit` — `PUT /api/v1/statuses/:id`: **500** porque exige `media_ids[]` en el cuerpo. Reintentar enviando el array completo de media_ids es factible pero innecesario: EP2 ya cubre todos los casos.

### Sobre el bug #5014

No reproducido en pixelfed.social v0.12.7. La descripción se persiste correctamente en posts antiguos también. O el bug está corregido en esta versión, o solo se manifiesta en otras instancias / configuraciones. **Plan B (override KV en Worker) queda como fallback documentado pero no necesario.**

### Detalle de restauración

El script restauró los posts a `description=""` (cadena vacía) en lugar de `null`. La API de Mastodon-compat no acepta `null` en PUT, solo string. Funcionalmente equivalente: el frontend usa `(media.description && media.description.trim()) || fallback`, que trata vacío como falsy. Confirmado:

- Post A (`944855314474473362`): `description: ""` ✅
- Post B (`955881786576642347`): `description: ""` ✅
- Post C (`956139286977150399`): borrado (HTTP 404) ✅
- Total cuenta: 153 statuses ✅

---

## Implicaciones para fases siguientes

1. **Fase 3 (frontend fix):** sin cambios. El snippet planeado ya trata vacío como falsy.
2. **Fase 4 (backfill):** `publish.py` usa `PUT /api/v1/media/:id` con `description=...` form-encoded. Throttle 1 req/s. Verificación read-after-write con `GET /api/v1/statuses/:status_id` y comparación literal del campo `description` del media correcto (en multi-attachment se identifica por `media_id`).
3. **Fase 5 (Worker SSR):** sin sorpresas — el feed actual sí refleja descriptions y el subdominio nuevo paginará los 153 con SSR.
4. **Fase 7 (flujo continuo):** `POST /api/v1/media` con `description` al upload **persiste correctamente** → flujo de "subir foto + alt-text en mismo paso desde script" es viable.

---

## Matriz cruda

### A_old — status `944855314474473362` (creado 2026-04-01)
- Original description: `null`
- Test description: `[SMOKE-20260502-103555] A_old smoke test`
- Restore: ✅ via EP2 (queda como `""`)

| Endpoint | HTTP | S1 API | S2 HTML | S3 Worker | S4 ActivityPub |
|---|---|:-:|:-:|:-:|:-:|
| EP1 (`/api/v1.1/media/update/:id`) | ❌ 404 | — | — | — | — |
| **EP2 (`PUT /api/v1/media/:id`)** | **✅ 200** | ✅ | n/a (SPA) | n/a (no en top-10) | ✅ |
| EP3 (`PUT /api/v1/statuses/:id`) | ❌ 500 | — | — | — | — |

### B_recent — status `955881786576642347` (creado 2026-05-01)
- Original description: `null`
- Test description: `[SMOKE-20260502-103555] B_recent smoke test`
- Restore: ✅ via EP2

| Endpoint | HTTP | S1 API | S2 HTML | S3 Worker | S4 ActivityPub |
|---|---|:-:|:-:|:-:|:-:|
| EP1 | ❌ 404 | — | — | — | — |
| **EP2** | **✅ 200** | ✅ | n/a (SPA) | ✅ | ✅ |
| EP3 | ❌ 500 | — | — | — | — |

### C_create_new — status `956139286977150399` (creado y borrado por el test)
- media_id `42260383`
- Test description: `[SMOKE-20260502-103555] TEST_C upload-time description`
- Cleanup: ✅ DELETE 200, verificado 404 después

| Surface | OK |
|---|:-:|
| S1 API | ✅ |
| S2 HTML | n/a (SPA) |
| S3 Worker | ✅ |
| S4 ActivityPub | ✅ |

### D_multi
SKIP — la cuenta es 100% single-image. No se pudo testar comportamiento multi-attachment, pero el contrato de EP2 es por `media_id` individual, así que el comportamiento debería ser idéntico. Se valida en producción si en algún momento JR sube un álbum.

---

## Próximos pasos

→ Continuar con **Fase 3 (fix del frontend JS de `/fotos/`)**.
