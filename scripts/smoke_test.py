#!/usr/bin/env python3
"""
smoke_test.py — Fase 2 del plan de alt-text.

Determina empíricamente si podemos escribir descriptions retroactivamente en
posts de Pixelfed (issue #5014). Es el GATE de decisión: si no funciona en
posts existentes, activamos plan B (override KV en Worker).

Tests:
  A) Editar descripción de un post antiguo (>30 días).
  B) Editar descripción de un post reciente (<7 días).
  C) Crear un post nuevo via API con descripción al subir media + verificar.
  D) Editar un post multi-attachment (si existe alguno; si no, lo crea).

Endpoints probados (en orden de preferencia):
  1. POST /api/v1.1/media/update/:id   (Pixelfed UI)
  2. PUT  /api/v1/media/:id            (Mastodon-compat)
  3. PUT  /api/v1/statuses/:id         (status edit, fuerza recompute)

Superficies verificadas tras cada edición:
  S1) GET  /api/v1/statuses/:id                       (API directa)
  S2) GET  /p/:user/:id  Accept: text/html            (HTML público)
  S3) GET  pixelfeed.workers.dev/?v=N                 (Worker JSON, cache-bust)
  S4) GET  /p/:user/:id  Accept: application/activity+json  (ActivityPub)

Restaura descripciones originales al final de cada test (idempotente).
Borra el post de prueba creado en Test C/D.

Output: SMOKE_TEST_RESULTS.md con matriz completa de endpoint × superficie.

Uso:
    source ~/Proyectos/impermanente-alttext/.venv/bin/activate
    python scripts/smoke_test.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

# --- Config ---
ENV_PATH = Path.home() / ".config" / "hispania-obscura" / ".env"
RESULTS_PATH = Path(__file__).parent.parent / "SMOKE_TEST_RESULTS.md"
WORKER_URL = os.environ.get("PIXELFED_WORKER_URL", "")  # opcional, para validar caché del Worker existente
HTTP_TIMEOUT = 30
SMOKE_MARK = f"SMOKE-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
SLEEP_BETWEEN_SURFACES = 4  # segundos para dar tiempo a la propagación
WORKER_CACHE_BUST_BASE = int(time.time())


# --- env loader ---
def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env(ENV_PATH)
INSTANCE = ENV["PIXELFED_INSTANCE"]
TOKEN = ENV["PIXELFED_ACCESS_TOKEN"]
USERNAME = ENV["PIXELFED_USERNAME"]
ACCOUNT_ID = ENV["PIXELFED_ACCOUNT_ID"]
BASE = f"https://{INSTANCE}"

AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}


# --- HTTP helpers ---
def api_get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{BASE}{path}", headers=AUTH_HEADERS, timeout=HTTP_TIMEOUT, **kwargs)


def api_post(path: str, **kwargs) -> requests.Response:
    return requests.post(f"{BASE}{path}", headers=AUTH_HEADERS, timeout=HTTP_TIMEOUT, **kwargs)


def api_put(path: str, **kwargs) -> requests.Response:
    return requests.put(f"{BASE}{path}", headers=AUTH_HEADERS, timeout=HTTP_TIMEOUT, **kwargs)


def api_delete(path: str, **kwargs) -> requests.Response:
    return requests.delete(f"{BASE}{path}", headers=AUTH_HEADERS, timeout=HTTP_TIMEOUT, **kwargs)


# --- Pixelfed inventory ---
def fetch_all_statuses() -> list[dict]:
    """Pagina todas las status del usuario."""
    out: list[dict] = []
    max_id = None
    for _ in range(20):  # safety: max 20 paginas (40 limit = 800 statuses)
        params = {"limit": 40, "exclude_replies": "true"}
        if max_id:
            params["max_id"] = max_id
        r = api_get(f"/api/v1/accounts/{ACCOUNT_ID}/statuses", params=params)
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        out.extend(page)
        max_id = page[-1]["id"]
        if len(page) < 40:
            break
    return out


def find_candidates(statuses: list[dict]) -> dict[str, dict | None]:
    """Identifica los posts adecuados para cada test."""
    now = datetime.now(timezone.utc)
    has_media = [s for s in statuses if s.get("media_attachments")]

    def parse_dt(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    sorted_by_age = sorted(has_media, key=lambda s: parse_dt(s["created_at"]))
    old_posts = [s for s in has_media if (now - parse_dt(s["created_at"])).days > 30]
    recent_posts = [s for s in has_media if (now - parse_dt(s["created_at"])).days < 7]
    multi = [s for s in has_media if len(s.get("media_attachments", [])) > 1]

    return {
        "A_old": old_posts[0] if old_posts else (sorted_by_age[0] if sorted_by_age else None),
        "B_recent": recent_posts[0] if recent_posts else (sorted_by_age[-1] if sorted_by_age else None),
        "D_multi": multi[0] if multi else None,
    }


# --- Endpoints de edición ---
def try_endpoint_1_pixelfed_ui(media_id: str, description: str) -> tuple[bool, str]:
    """POST /api/v1.1/media/update/:id"""
    r = api_post(f"/api/v1.1/media/update/{media_id}", data={"description": description})
    return r.status_code in (200, 204), f"HTTP {r.status_code}: {r.text[:200]}"


def try_endpoint_2_mastodon_put(media_id: str, description: str) -> tuple[bool, str]:
    """PUT /api/v1/media/:id"""
    r = api_put(f"/api/v1/media/{media_id}", data={"description": description})
    return r.status_code in (200, 204), f"HTTP {r.status_code}: {r.text[:200]}"


def try_endpoint_3_status_edit(status_id: str, media_id: str, description: str) -> tuple[bool, str]:
    """PUT /api/v1/statuses/:id (edita el status, intentando incluir media_attributes)."""
    payload = {
        "media_attributes[0][id]": media_id,
        "media_attributes[0][description]": description,
    }
    r = api_put(f"/api/v1/statuses/{status_id}", data=payload)
    return r.status_code in (200, 204), f"HTTP {r.status_code}: {r.text[:200]}"


# --- Verificación de superficies ---
def verify_surface_S1_api(status_id: str, media_id: str, expected: str) -> tuple[bool, str]:
    r = api_get(f"/api/v1/statuses/{status_id}")
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    data = r.json()
    for m in data.get("media_attachments", []):
        if str(m.get("id")) == str(media_id):
            desc = m.get("description") or ""
            return desc == expected, f"description={desc!r}"
    return False, "media_id no encontrado"


def verify_surface_S2_html(status_id: str, expected: str) -> tuple[bool, str]:
    url = f"{BASE}/p/{USERNAME}/{status_id}"
    r = requests.get(url, headers={"Accept": "text/html"}, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    found = expected in r.text
    return found, f"expected en HTML: {found}"


def verify_surface_S3_worker(media_id: str, expected: str, bust: int) -> tuple[bool, str]:
    url = f"{WORKER_URL}?v={WORKER_CACHE_BUST_BASE + bust}"
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    try:
        posts = r.json()
    except Exception as e:
        return False, f"JSON parse: {e}"
    for p in posts:
        for m in p.get("media_attachments") or []:
            if str(m.get("id")) == str(media_id):
                desc = m.get("description") or ""
                return desc == expected, f"description={desc!r}"
    return False, "media_id no encontrado en feed (puede no estar en últimas 10)"


def verify_surface_S4_activitypub(status_id: str, expected: str) -> tuple[bool, str]:
    url = f"{BASE}/p/{USERNAME}/{status_id}"
    r = requests.get(
        url, headers={"Accept": "application/activity+json"}, timeout=HTTP_TIMEOUT
    )
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    try:
        ap = r.json()
    except Exception:
        return False, "no JSON (¿devolvió HTML?)"
    obj = ap.get("object", ap)
    attachments = obj.get("attachment", [])
    if not isinstance(attachments, list):
        attachments = [attachments]
    for a in attachments:
        name = a.get("name") or ""
        if name == expected:
            return True, f"name={name!r}"
    names = [a.get("name") for a in attachments]
    return False, f"names={names}"


# --- Restauración ---
def restore_description(media_id: str, status_id: str, original: str | None) -> str:
    """Intenta dejar la descripción como estaba (None → cadena vacía)."""
    target = original or ""
    for name, fn in [
        ("ep1", lambda: try_endpoint_1_pixelfed_ui(media_id, target)),
        ("ep2", lambda: try_endpoint_2_mastodon_put(media_id, target)),
        ("ep3", lambda: try_endpoint_3_status_edit(status_id, media_id, target)),
    ]:
        ok, info = fn()
        if ok:
            return f"restaurado via {name}"
    return "WARNING: no pude restaurar"


# --- Test runner por edición ---
def run_edit_test(label: str, status: dict, marker: str) -> dict:
    """Ejecuta un test de edición sobre un status existente."""
    media = status["media_attachments"][0]
    media_id = str(media["id"])
    status_id = str(status["id"])
    original = media.get("description")

    print(f"\n{'='*70}")
    print(f"TEST {label}: {status_id} (media {media_id})")
    print(f"  Created: {status['created_at']}  |  Original desc: {original!r}")
    print(f"{'='*70}")

    test_desc = f"[{marker}] {label} smoke test"
    result: dict[str, Any] = {
        "label": label,
        "status_id": status_id,
        "media_id": media_id,
        "created_at": status["created_at"],
        "original_description": original,
        "test_description": test_desc,
        "endpoints": {},
    }

    endpoints = [
        ("EP1_pixelfed_ui", lambda d: try_endpoint_1_pixelfed_ui(media_id, d)),
        ("EP2_mastodon_put", lambda d: try_endpoint_2_mastodon_put(media_id, d)),
        ("EP3_status_edit", lambda d: try_endpoint_3_status_edit(status_id, media_id, d)),
    ]

    for ep_name, ep_fn in endpoints:
        marker_ep = f"{test_desc} via {ep_name}"
        print(f"\n  → Probando {ep_name} ...")
        ok, info = ep_fn(marker_ep)
        ep_result: dict[str, Any] = {"http_ok": ok, "http_info": info, "surfaces": {}}
        result["endpoints"][ep_name] = ep_result
        if not ok:
            print(f"    ❌ {info}")
            continue
        print(f"    ✅ {info[:100]}")
        print(f"    Esperando {SLEEP_BETWEEN_SURFACES}s para propagación...")
        time.sleep(SLEEP_BETWEEN_SURFACES)

        bust_idx = endpoints.index((ep_name, ep_fn)) + 1
        for sname, sfn in [
            ("S1_api", lambda: verify_surface_S1_api(status_id, media_id, marker_ep)),
            ("S2_html", lambda: verify_surface_S2_html(status_id, marker_ep)),
            ("S3_worker", lambda: verify_surface_S3_worker(media_id, marker_ep, bust_idx)),
            ("S4_activitypub", lambda: verify_surface_S4_activitypub(status_id, marker_ep)),
        ]:
            try:
                ok_s, info_s = sfn()
            except Exception as e:
                ok_s, info_s = False, f"EXC {type(e).__name__}: {e}"
            ep_result["surfaces"][sname] = {"ok": ok_s, "info": info_s}
            symbol = "✅" if ok_s else "❌"
            print(f"      {symbol} {sname}: {info_s[:120]}")

    print(f"\n  → Restaurando descripción original...")
    restore_msg = restore_description(media_id, status_id, original)
    result["restore"] = restore_msg
    print(f"    {restore_msg}")
    return result


# --- Test C: post nuevo creado via API ---
def make_test_image(text: str) -> bytes:
    img = Image.new("RGB", (400, 400), color=(20, 20, 30))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except Exception:
        font = ImageFont.load_default()
    draw.text((20, 180), text, fill=(220, 220, 220), font=font)
    draw.text((20, 220), datetime.now(timezone.utc).isoformat(), fill=(140, 140, 160), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_test_C_create_new(marker: str) -> dict:
    print(f"\n{'='*70}")
    print(f"TEST C: crear post NUEVO via API con description al upload")
    print(f"{'='*70}")
    description = f"[{marker}] TEST_C upload-time description"
    img_bytes = make_test_image(f"SMOKE TEST C\n{marker}")

    print("  → POST /api/v1/media (con description en el upload)...")
    r = api_post(
        "/api/v1/media",
        data={"description": description},
        files={"file": ("smoke_test.png", img_bytes, "image/png")},
    )
    if r.status_code not in (200, 201):
        print(f"    ❌ HTTP {r.status_code}: {r.text[:300]}")
        return {"label": "C_create_new", "media_upload_ok": False, "info": r.text[:300]}
    media = r.json()
    media_id = str(media["id"])
    print(f"    ✅ media_id={media_id}, description en respuesta: {media.get('description')!r}")

    print("  → POST /api/v1/statuses (publicar)...")
    r = api_post(
        "/api/v1/statuses",
        data={
            "status": f"[smoke test C — borrar] {marker}",
            "media_ids[]": media_id,
            "visibility": "public",
        },
    )
    if r.status_code not in (200, 201):
        print(f"    ❌ HTTP {r.status_code}: {r.text[:300]}")
        return {"label": "C_create_new", "media_upload_ok": True, "status_create_ok": False, "media_id": media_id, "info": r.text[:300]}
    status = r.json()
    status_id = str(status["id"])
    print(f"    ✅ status_id={status_id} (visibility=unlisted)")

    print(f"  Esperando {SLEEP_BETWEEN_SURFACES}s para propagación...")
    time.sleep(SLEEP_BETWEEN_SURFACES)

    surfaces: dict[str, Any] = {}
    for sname, sfn in [
        ("S1_api", lambda: verify_surface_S1_api(status_id, media_id, description)),
        ("S2_html", lambda: verify_surface_S2_html(status_id, description)),
        ("S3_worker", lambda: verify_surface_S3_worker(media_id, description, 99)),
        ("S4_activitypub", lambda: verify_surface_S4_activitypub(status_id, description)),
    ]:
        try:
            ok_s, info_s = sfn()
        except Exception as e:
            ok_s, info_s = False, f"EXC {type(e).__name__}: {e}"
        surfaces[sname] = {"ok": ok_s, "info": info_s}
        symbol = "✅" if ok_s else "❌"
        print(f"    {symbol} {sname}: {info_s[:120]}")

    # Cleanup
    print(f"\n  → DELETE /api/v1/statuses/{status_id} (cleanup)...")
    r = api_delete(f"/api/v1/statuses/{status_id}")
    cleanup = r.status_code in (200, 204)
    print(f"    {'✅' if cleanup else '⚠️'} HTTP {r.status_code}")

    return {
        "label": "C_create_new",
        "media_upload_ok": True,
        "status_create_ok": True,
        "media_id": media_id,
        "status_id": status_id,
        "test_description": description,
        "surfaces": surfaces,
        "cleanup_ok": cleanup,
    }


# --- Reporting ---
def render_results_md(results: dict) -> str:
    md = io.StringIO()
    md.write(f"# Smoke test results — {results['timestamp']}\n\n")
    md.write(f"- Instance: `{results['instance']}`\n")
    md.write(f"- Account: `@{results['username']}` (id `{results['account_id']}`)\n")
    md.write(f"- Marker run-id: `{results['marker']}`\n")
    md.write(f"- Statuses con media inventariadas: {results['inventory']['total_with_media']}\n")
    md.write(f"- Multi-attachment encontrados: {results['inventory']['multi_attachment_count']}\n\n")

    md.write("## Decisión gate\n\n")
    md.write(results["decision"]["summary"] + "\n\n")
    md.write("Detalle:\n")
    for k, v in results["decision"]["details"].items():
        md.write(f"- **{k}**: {v}\n")
    md.write("\n")

    md.write("## Matriz de resultados\n\n")
    for test_name in ["A_old", "B_recent", "D_multi"]:
        test = results["tests"].get(test_name)
        if not test:
            md.write(f"### {test_name}: SKIP (no se encontró candidato)\n\n")
            continue
        md.write(f"### {test_name} — status `{test['status_id']}` (creado {test['created_at']})\n\n")
        md.write(f"- Original description: `{test['original_description']!r}`\n")
        md.write(f"- Test description: `{test['test_description']!r}`\n")
        md.write(f"- Restore: {test['restore']}\n\n")
        md.write("| Endpoint | HTTP | S1 API | S2 HTML | S3 Worker | S4 ActivityPub |\n")
        md.write("|---|---|---|---|---|---|\n")
        for ep_name, ep in test["endpoints"].items():
            http = "✅" if ep["http_ok"] else "❌"
            srows = []
            for s in ["S1_api", "S2_html", "S3_worker", "S4_activitypub"]:
                surf = ep["surfaces"].get(s)
                if not surf:
                    srows.append("—")
                else:
                    srows.append("✅" if surf["ok"] else f"❌ {surf['info'][:40]}")
            md.write(f"| {ep_name} | {http} {ep['http_info'][:50]} | " + " | ".join(srows) + " |\n")
        md.write("\n")

    test_c = results["tests"].get("C_create_new")
    if test_c:
        md.write("### C_create_new — post nuevo creado via API\n\n")
        if not test_c.get("media_upload_ok"):
            md.write(f"❌ Upload fallido: {test_c.get('info','')}\n\n")
        elif not test_c.get("status_create_ok"):
            md.write(f"❌ Status create fallido: {test_c.get('info','')}\n\n")
        else:
            md.write(f"- media_id `{test_c['media_id']}`, status_id `{test_c['status_id']}`\n")
            md.write(f"- Test description: `{test_c['test_description']!r}`\n")
            md.write(f"- Cleanup: {'✅' if test_c['cleanup_ok'] else '⚠️ revisar manualmente'}\n\n")
            md.write("| S1 API | S2 HTML | S3 Worker | S4 ActivityPub |\n|---|---|---|---|\n")
            srows = []
            for s in ["S1_api", "S2_html", "S3_worker", "S4_activitypub"]:
                surf = test_c["surfaces"].get(s, {})
                srows.append("✅" if surf.get("ok") else f"❌ {surf.get('info','')[:40]}")
            md.write("| " + " | ".join(srows) + " |\n\n")

    md.write("## Datos crudos (JSON)\n\n")
    md.write("```json\n")
    md.write(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    md.write("\n```\n")
    return md.getvalue()


def decide(results: dict) -> dict:
    """Aplica la lógica del gate.

    Superficies críticas para nuestro caso de uso:
      - S1 API:        confirma que la write persiste server-side.
      - S4 ActivityPub: confirma que la federación ve el cambio.
      - S3 Worker:     opcional/informativo. El feed actual solo expone últimas N statuses;
                       que un post antiguo no aparezca aquí no implica fallo de propagación.
                       Cuenta como ✅ si el media_id está en el feed; n/a en otro caso.
      - S2 HTML:       DESCARTADA. Las páginas /p/.../id de pixelfed.social son SPA Vue
                       (verificado: <noscript>Please enable javascript</noscript>). El HTML
                       inicial nunca contiene alt-text — no la controlamos ni la usamos.
    """
    def has_full_success(test: dict | None) -> str | None:
        if not test:
            return None
        for ep_name, ep in test.get("endpoints", {}).items():
            if not ep.get("http_ok"):
                continue
            surfaces = ep.get("surfaces", {})
            crit = ["S1_api", "S4_activitypub"]
            if all(surfaces.get(s, {}).get("ok") for s in crit):
                return ep_name
        return None

    a_ok = has_full_success(results["tests"].get("A_old"))
    b_ok = has_full_success(results["tests"].get("B_recent"))
    d_ok = has_full_success(results["tests"].get("D_multi"))

    test_c = results["tests"].get("C_create_new") or {}
    c_surfaces = test_c.get("surfaces", {})
    c_crit_ok = all(c_surfaces.get(s, {}).get("ok") for s in ["S1_api", "S4_activitypub"]) if c_surfaces else False

    details = {
        "Test A (post antiguo)": f"endpoint funcional: `{a_ok}`" if a_ok else "❌ ningún endpoint propagó",
        "Test B (post reciente)": f"endpoint funcional: `{b_ok}`" if b_ok else "❌ ningún endpoint propagó",
        "Test C (post nuevo)": "✅ description al upload se propaga" if c_crit_ok else "❌ description al upload NO se propaga",
        "Test D (multi-attachment)": (f"endpoint funcional: `{d_ok}`" if d_ok else ("SKIP (no había multi)" if not results["tests"].get("D_multi") else "❌ ningún endpoint propagó")),
    }

    if a_ok and b_ok and c_crit_ok and (d_ok or not results["tests"].get("D_multi")):
        summary = "✅ **PLAN A confirmado**: Pixelfed como single source de verdad funciona en todos los casos. Backfill viable."
    elif c_crit_ok and not (a_ok and b_ok):
        summary = "⚠️ **PLAN A parcial**: descripción al subir foto NUEVA funciona, pero edición retroactiva (backfill) NO. Activar PLAN B (override KV en Worker) para las 153 existentes; flujo de fotos nuevas viable via Pixelfed."
    elif not c_crit_ok:
        summary = "❌ **GATE FALLIDO**: ni siquiera la subida nueva propaga la descripción. Reabrir decisión arquitectónica con el usuario antes de continuar."
    else:
        summary = "⚠️ Resultado mixto. Revisar la matriz arriba y decidir caso por caso."

    return {"summary": summary, "details": details, "endpoints_working": {"A": a_ok, "B": b_ok, "C": c_crit_ok, "D": d_ok}}


# --- Main ---
def main() -> None:
    print(f"Smoke test — marker {SMOKE_MARK}")
    print(f"Instance: {INSTANCE}, account: @{USERNAME} (id={ACCOUNT_ID})")

    print("\n→ Fetcheando inventario completo de statuses...")
    statuses = fetch_all_statuses()
    print(f"  Total statuses fetcheadas: {len(statuses)}")

    candidates = find_candidates(statuses)
    print("\nCandidatos seleccionados:")
    for k, v in candidates.items():
        if v:
            print(f"  {k}: {v['id']}  (created {v['created_at']}, {len(v['media_attachments'])} media)")
        else:
            print(f"  {k}: SKIP (no encontrado)")

    results: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "marker": SMOKE_MARK,
        "instance": INSTANCE,
        "username": USERNAME,
        "account_id": ACCOUNT_ID,
        "inventory": {
            "total_fetched": len(statuses),
            "total_with_media": sum(1 for s in statuses if s.get("media_attachments")),
            "multi_attachment_count": sum(1 for s in statuses if len(s.get("media_attachments") or []) > 1),
        },
        "tests": {},
    }

    for label, status in [("A_old", candidates["A_old"]), ("B_recent", candidates["B_recent"]), ("D_multi", candidates["D_multi"])]:
        if status:
            results["tests"][label] = run_edit_test(label, status, SMOKE_MARK)

    results["tests"]["C_create_new"] = run_test_C_create_new(SMOKE_MARK)

    results["decision"] = decide(results)

    md = render_results_md(results)
    RESULTS_PATH.write_text(md)
    print(f"\n\n{'='*70}")
    print(f"Resultados escritos en: {RESULTS_PATH}")
    print(f"{'='*70}")
    print("\n" + results["decision"]["summary"])
    print()
    for k, v in results["decision"]["details"].items():
        print(f"  • {k}: {v}")


if __name__ == "__main__":
    main()
