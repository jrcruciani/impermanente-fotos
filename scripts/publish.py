"""Publica alt-texts generados a Pixelfed via PUT /api/v1/media/:id.

Uso:
    python scripts/publish.py --dry-run                  # simula, no escribe
    python scripts/publish.py --sample 5                 # 5 aleatorias (con write real)
    python scripts/publish.py --limit 10                 # primeras 10 pendientes
    python scripts/publish.py                            # publica todas las pendientes
    python scripts/publish.py --media-ids 27633677,...   # publica IDs específicos

Características:
- Lee data/generated.jsonl (solo qa_status=passed).
- Skip si media_id ya está en data/published.jsonl con status=ok.
- Throttle: 4s entre escrituras (Pixelfed rate-limita agresivamente).
- Retry: backoff exponencial sobre 5xx, Retry-After sobre 429.
- Read-after-write: GET /api/v1/statuses/:id, busca media_id, decodifica
  HTML entities, compara con alt_text esperado.
- Escribe data/published.jsonl atómicamente tras cada publicación exitosa.
- Endpoint validado: PUT /api/v1/media/:id (form-encoded description=...).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import random
import sys
import time
import datetime as dt
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
GENERATED_PATH = ROOT / "data" / "generated.jsonl"
PUBLISHED_PATH = ROOT / "data" / "published.jsonl"
ENV_PATH = Path.home() / ".config" / "hispania-obscura" / ".env"

THROTTLE_SECONDS = 4.0
HTTP_TIMEOUT = 30
MAX_RETRIES = 6
RETRY_429_BASE = 30  # segundos base para 429 (Pixelfed pide "a few minutes")


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
BASE = f"https://{INSTANCE}"
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}


def load_generated() -> list[dict]:
    out = []
    with GENERATED_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("qa_status") == "passed":
                out.append(rec)
    return out


def load_published() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if PUBLISHED_PATH.exists():
        with PUBLISHED_PATH.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                out[rec["media_id"]] = rec
    return out


def append_published(rec: dict) -> None:
    """Append-only para preservar historial (idempotencia por re-escribir solo lectura)."""
    PUBLISHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PUBLISHED_PATH.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def put_description(media_id: str, description: str) -> tuple[int, str, dict]:
    url = f"{BASE}/api/v1/media/{media_id}"
    r = requests.put(
        url,
        headers=AUTH_HEADERS,
        data={"description": description},
        timeout=HTTP_TIMEOUT,
    )
    return r.status_code, r.text[:300], dict(r.headers)


def get_description(media_id: str, status_id: str | None) -> tuple[int, str | None, str]:
    """Lee la descripción actual desde el status que contiene el media.

    Pixelfed no permite GET /api/v1/media/:id tras cerrar la sesión de upload
    (devuelve 404 "No query results"). La forma robusta es leer el status y
    buscar el media_id dentro de media_attachments. Maneja 429 con backoff.
    """
    if not status_id:
        return 400, None, "status_id requerido para verificación"
    url = f"{BASE}/api/v1/statuses/{status_id}"
    for attempt in range(1, MAX_RETRIES + 1):
        r = requests.get(url, headers=AUTH_HEADERS, timeout=HTTP_TIMEOUT)
        if r.status_code == 200:
            body = r.json()
            for m in body.get("media_attachments") or []:
                if str(m.get("id")) == str(media_id):
                    return 200, m.get("description"), ""
            return 404, None, f"media_id {media_id} no encontrado en status {status_id}"
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", str(RETRY_429_BASE * attempt)))
            print(f"    GET 429, esperando {retry_after}s (verify retry {attempt}/{MAX_RETRIES})")
            time.sleep(retry_after)
            continue
        if r.status_code in (500, 502, 503, 504):
            wait = 2 ** attempt
            print(f"    GET {r.status_code}, retry {attempt}/{MAX_RETRIES} en {wait}s")
            time.sleep(wait)
            continue
        return r.status_code, None, r.text[:200]
    return 429, None, "verify retries exhausted (rate limited)"


def publish_one(rec: dict, dry_run: bool) -> dict:
    media_id = rec["media_id"]
    alt_text = rec["alt_text"]

    if dry_run:
        return {
            "media_id": media_id,
            "status": "dry_run",
            "alt_text": alt_text,
            "alt_text_chars": len(alt_text),
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    last_err = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            code, body, hdrs = put_description(media_id, alt_text)
            if code in (200, 204):
                break
            if code == 429:
                retry_after = int(hdrs.get("Retry-After", str(RETRY_429_BASE * attempt)))
                last_err = f"PUT HTTP 429: {body}"
                print(f"    PUT 429, esperando {retry_after}s (retry {attempt}/{MAX_RETRIES})")
                time.sleep(retry_after)
                continue
            if code in (500, 502, 503, 504):
                last_err = f"PUT HTTP {code}: {body}"
                wait = 2 ** attempt
                print(f"    retry {attempt}/{MAX_RETRIES} en {wait}s — {last_err[:80]}")
                time.sleep(wait)
                continue
            # 4xx no recuperable
            return {
                "media_id": media_id,
                "status": "failed_put",
                "http_code": code,
                "error": body,
                "alt_text": alt_text,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        except requests.RequestException as e:
            last_err = f"network: {e}"
            wait = 2 ** attempt
            print(f"    retry {attempt}/{MAX_RETRIES} en {wait}s — {last_err[:80]}")
            time.sleep(wait)
    else:
        return {
            "media_id": media_id,
            "status": "failed_put_exhausted",
            "error": last_err,
            "alt_text": alt_text,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    # Read-after-write verification (vía status, no vía media/:id que devuelve 404)
    time.sleep(0.5)
    code, got_desc, err = get_description(media_id, rec.get("status_id"))
    if code != 200:
        return {
            "media_id": media_id,
            "status": "failed_verify_get",
            "http_code": code,
            "error": err,
            "alt_text": alt_text,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    if (html.unescape(got_desc or "")).strip() != alt_text.strip():
        return {
            "media_id": media_id,
            "status": "verify_mismatch",
            "expected": alt_text,
            "got": got_desc,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    return {
        "media_id": media_id,
        "status": "ok",
        "alt_text": alt_text,
        "alt_text_chars": len(alt_text),
        "verified": True,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="No escribe, solo simula y muestra")
    ap.add_argument("--sample", type=int, help="Muestra aleatoria de N (semilla determinista)")
    ap.add_argument("--limit", type=int, help="Primeras N pendientes (orden cronológico)")
    ap.add_argument("--media-ids", type=str, help="Lista CSV de media_ids específicos")
    ap.add_argument("--seed", type=int, default=42, help="Semilla para --sample")
    ap.add_argument("--force", action="store_true", help="Reescribe aun si ya está publicado")
    args = ap.parse_args()

    generated = load_generated()
    published = load_published()
    ok_ids = {m for m, r in published.items() if r.get("status") == "ok"}

    if args.media_ids:
        wanted = set(args.media_ids.split(","))
        candidates = [r for r in generated if r["media_id"] in wanted]
    else:
        candidates = [r for r in generated if args.force or r["media_id"] not in ok_ids]

    candidates.sort(key=lambda r: r.get("created_at") or "")

    if args.sample:
        rnd = random.Random(args.seed)
        candidates = rnd.sample(candidates, min(args.sample, len(candidates)))

    if args.limit:
        candidates = candidates[: args.limit]

    print(f"Total generated:        {len(generated)}")
    print(f"Already published (ok): {len(ok_ids)}")
    print(f"To process this run:    {len(candidates)}")
    print(f"Mode:                   {'DRY-RUN' if args.dry_run else 'WRITE'}")
    print()

    n_ok = 0
    n_fail = 0
    last_call = 0.0

    for i, rec in enumerate(candidates, 1):
        # throttle entre escrituras reales
        if not args.dry_run:
            elapsed = time.monotonic() - last_call
            if elapsed < THROTTLE_SECONDS:
                time.sleep(THROTTLE_SECONDS - elapsed)
            last_call = time.monotonic()

        media_id = rec["media_id"]
        preview = rec["alt_text"][:70].replace("\n", " ")
        print(f"[{i:>3}/{len(candidates)}] {media_id}  | {preview}...")

        result = publish_one(rec, args.dry_run)
        result["batch"] = rec.get("batch")
        result["status_id"] = rec.get("status_id")

        if not args.dry_run:
            append_published(result)

        if result["status"] in ("ok", "dry_run"):
            n_ok += 1
            print(f"        ✓ {result['status']}  ({len(rec['alt_text'])} chars)")
        else:
            n_fail += 1
            print(f"        ✗ {result['status']}  → {str(result.get('error') or result.get('got') or '')[:100]}")

    print()
    print(f"Done: ok={n_ok}  failed={n_fail}  total={len(candidates)}")
    if not args.dry_run:
        print(f"Published log: {PUBLISHED_PATH}")


if __name__ == "__main__":
    main()
