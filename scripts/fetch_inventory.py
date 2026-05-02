#!/usr/bin/env python3
"""
fetch_inventory.py — Fase 4 step 1

Lee TODOS los statuses del usuario @HispaniaObscura desde Pixelfed y produce:
  - data/inventory.jsonl: una línea por media_attachment (no por status), para soportar multi-attachment
  - data/images_cache/{media_id}.jpg: imagen redimensionada a 1024px (lado largo), quality 85

Resumibilidad: si data/inventory.jsonl ya existe lo recrea; las imágenes en cache se reusan.

Salida: resumen por consola + data/inventory.jsonl + data/images_cache/.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ENV_PATH = Path.home() / ".config" / "hispania-obscura" / ".env"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "images_cache"
INVENTORY_PATH = DATA_DIR / "inventory.jsonl"
SUMMARY_PATH = DATA_DIR / "inventory_summary.md"

MAX_DIM = 1024
JPEG_Q = 85
PER_PAGE = 20
SLEEP = 0.5
TIMEOUT = 60
MAX_RETRIES = 4


def load_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        sys.exit(f"❌ no encuentro {ENV_PATH}; lanza oauth_setup.py primero")
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def fetch_all_statuses(instance: str, account_id: str, token: str) -> list[dict]:
    out: list[dict] = []
    max_id: str | None = None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"https://{instance}/api/v1/accounts/{account_id}/statuses"
    while True:
        params = {"limit": PER_PAGE, "exclude_replies": "true", "exclude_reblogs": "true", "_pe": "1"}
        if max_id:
            params["max_id"] = max_id
        page: list[dict] | None = None
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
                r.raise_for_status()
                page = r.json()
                break
            except (requests.Timeout, requests.ConnectionError) as e:
                wait = 2 ** attempt
                print(f"  ⚠ timeout/conn (intento {attempt+1}/{MAX_RETRIES}): {e.__class__.__name__}; retry en {wait}s")
                time.sleep(wait)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code in (429, 502, 503, 504):
                    wait = 2 ** attempt
                    print(f"  ⚠ HTTP {e.response.status_code} (intento {attempt+1}/{MAX_RETRIES}); retry en {wait}s")
                    time.sleep(wait)
                else:
                    raise
        if page is None:
            sys.exit(f"❌ no pude fetchear page tras {MAX_RETRIES} intentos (max_id={max_id})")
        if not page:
            break
        out.extend(page)
        max_id = page[-1]["id"]
        print(f"  fetched page: {len(page)} statuses (total acumulado: {len(out)})")
        if len(page) < PER_PAGE:
            break
        time.sleep(SLEEP)
    return out


def normalize_to_media_records(statuses: list[dict]) -> list[dict]:
    records = []
    for st in statuses:
        media_list = st.get("media_attachments") or []
        for pos, m in enumerate(media_list):
            if m.get("type") != "image":
                continue
            records.append({
                "status_id": st["id"],
                "status_url": st.get("url"),
                "media_id": m["id"],
                "image_url": m.get("url") or m.get("preview_url"),
                "preview_url": m.get("preview_url"),
                "blurhash": m.get("blurhash"),
                "current_description": m.get("description"),
                "position_in_status": pos,
                "total_in_status": len(media_list),
                "place": st.get("place"),
                "created_at": st.get("created_at"),
                "content_text": st.get("content"),
                "visibility": st.get("visibility"),
                "meta": (m.get("meta") or {}).get("original"),
            })
    return records


def download_and_resize(url: str, dest: Path) -> tuple[bool, str]:
    if dest.exists() and dest.stat().st_size > 0:
        return True, "cached"
    last_err = ""
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, timeout=TIMEOUT, stream=True)
            r.raise_for_status()
            tmp = dest.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(64 * 1024):
                    f.write(chunk)
            with Image.open(tmp) as img:
                img = img.convert("RGB")
                w, h = img.size
                if max(w, h) > MAX_DIM:
                    if w >= h:
                        nw, nh = MAX_DIM, int(h * MAX_DIM / w)
                    else:
                        nh, nw = MAX_DIM, int(w * MAX_DIM / h)
                    img = img.resize((nw, nh), Image.LANCZOS)
                img.save(dest, "JPEG", quality=JPEG_Q, optimize=True)
            tmp.unlink(missing_ok=True)
            return True, f"saved {dest.stat().st_size // 1024}KB"
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = f"{e.__class__.__name__}"
            time.sleep(2 ** attempt)
        except Exception as e:
            return False, f"error: {e}"
    return False, f"timeout tras {MAX_RETRIES} intentos: {last_err}"


def needs_alt(rec: dict) -> bool:
    desc = rec.get("current_description")
    if desc is None:
        return True
    if isinstance(desc, str) and desc.strip() == "":
        return True
    return False


def main() -> None:
    env = load_env()
    instance = env["PIXELFED_INSTANCE"]
    token = env["PIXELFED_ACCESS_TOKEN"]
    account_id = env["PIXELFED_ACCOUNT_ID"]
    username = env.get("PIXELFED_USERNAME", "?")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"→ Fetcheando todos los statuses de @{username} (id={account_id}) en {instance}...")
    statuses = fetch_all_statuses(instance, account_id, token)
    print(f"\n✅ {len(statuses)} statuses totales")

    print("\n→ Normalizando a registros por media_attachment...")
    records = normalize_to_media_records(statuses)
    print(f"  {len(records)} registros media_attachment (incluye los ya descritos)")

    pending = [r for r in records if needs_alt(r)]
    multi = [r for r in records if r["total_in_status"] > 1]
    print(f"  {len(pending)} pendientes de alt-text")
    print(f"  {len(multi)} en posts multi-attachment")

    print("\n→ Escribiendo inventory.jsonl...")
    with open(INVENTORY_PATH, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  {INVENTORY_PATH} ({INVENTORY_PATH.stat().st_size // 1024}KB)")

    print("\n→ Descargando + redimensionando imágenes pendientes (max 1024px, JPEG q85)...")
    ok = 0
    failed: list[tuple[str, str]] = []
    for i, r in enumerate(pending, 1):
        dest = CACHE_DIR / f"{r['media_id']}.jpg"
        success, info = download_and_resize(r["image_url"], dest)
        marker = "✓" if success else "✗"
        if success:
            ok += 1
        else:
            failed.append((r["media_id"], info))
        if i % 10 == 0 or i == len(pending):
            print(f"  [{i}/{len(pending)}] {marker} {r['media_id']}: {info}")
        if info != "cached":
            time.sleep(SLEEP)

    print(f"\n✅ Imágenes descargadas: {ok}/{len(pending)}")
    if failed:
        print(f"❌ Fallaron {len(failed)}:")
        for mid, info in failed[:10]:
            print(f"   - {mid}: {info}")

    # Resumen útil
    summary = [
        "# Inventory summary",
        "",
        f"- Total statuses: {len(statuses)}",
        f"- Total media_attachments (image): {len(records)}",
        f"- Pendientes de alt-text: {len(pending)}",
        f"- En posts multi-attachment: {len(multi)}",
        f"- Imágenes descargadas correctamente: {ok}",
        f"- Imágenes que fallaron: {len(failed)}",
        "",
        "## Distribución temporal (pendientes)",
        "",
    ]
    by_year_month: dict[str, int] = {}
    for r in pending:
        ca = r.get("created_at") or ""
        ym = ca[:7] if len(ca) >= 7 else "??"
        by_year_month[ym] = by_year_month.get(ym, 0) + 1
    for ym in sorted(by_year_month):
        summary.append(f"- {ym}: {by_year_month[ym]}")
    summary.extend([
        "",
        "## Cobertura de `place`",
        "",
        f"- Con `place.name`: {sum(1 for r in pending if r.get('place'))}",
        f"- Sin `place`: {sum(1 for r in pending if not r.get('place'))}",
    ])
    SUMMARY_PATH.write_text("\n".join(summary), encoding="utf-8")
    print(f"\n→ Resumen escrito en {SUMMARY_PATH}")
    print("\n--- listo para Fase 4 step 2 (generación de alt-text) ---")


if __name__ == "__main__":
    main()
