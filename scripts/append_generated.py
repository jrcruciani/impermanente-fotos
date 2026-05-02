"""Append alt-texts generados a data/generated.jsonl aplicando QA.

Uso:
    python scripts/append_generated.py BATCH_ID < records.json
    python scripts/append_generated.py BATCH_ID --records '[{...},{...}]'

Cada record requiere: media_id, alt_text. Opcional: status_id, created_at, model.

El script:
- Aplica QA y deja qa_status pass/fail.
- Anota generated_at + batch.
- Es IDEMPOTENTE: si el media_id ya existe en generated.jsonl, lo SOBREESCRIBE
  (rewrite atómico vía .tmp).
- Imprime resumen: pasados / fallados / sobreescritos.
"""
from __future__ import annotations
import json
import os
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import qa  # noqa: E402

OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "generated.jsonl"


def load_existing() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if OUT_PATH.exists():
        with OUT_PATH.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                out[rec["media_id"]] = rec
    return out


def write_all(records: dict[str, dict]) -> None:
    tmp = OUT_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for rec in sorted(records.values(), key=lambda r: r.get("created_at", "")):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT_PATH)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("uso: python scripts/append_generated.py BATCH_ID [--records JSON]")
    batch_id = sys.argv[1]
    if "--records" in sys.argv:
        idx = sys.argv.index("--records")
        new_records = json.loads(sys.argv[idx + 1])
    else:
        new_records = json.loads(sys.stdin.read())

    if not isinstance(new_records, list):
        sys.exit("records debe ser una lista de objetos")

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    existing = load_existing()
    overwritten = 0
    passed = 0
    failed = 0

    for r in new_records:
        media_id = r["media_id"]
        alt_text = r["alt_text"]
        report = qa(alt_text)
        rec = {
            "media_id": media_id,
            "status_id": r.get("status_id"),
            "created_at": r.get("created_at"),
            "alt_text": alt_text,
            "qa": report,
            "qa_status": "passed" if report["passed"] else "failed",
            "model": r.get("model", "claude-opus-4.7-xhigh-direct"),
            "generated_at": now,
            "batch": batch_id,
        }
        if media_id in existing:
            overwritten += 1
        existing[media_id] = rec
        if report["passed"]:
            passed += 1
        else:
            failed += 1
            print(f"  ⚠ FAIL {media_id}: {report['issues']}  | {alt_text[:80]}...")

    write_all(existing)
    total = len(existing)
    print(f"batch={batch_id}  passed={passed}  failed={failed}  overwritten={overwritten}  total_in_file={total}")


if __name__ == "__main__":
    main()
