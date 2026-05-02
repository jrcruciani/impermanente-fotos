"""Lista los próximos N media_ids pendientes (no en generated.jsonl) ordenados.

Uso:
    python scripts/next_batch.py [N=8] [--order=newest|oldest]

Output JSON con: index, media_id, status_id, created_at, image_path, content_text, meta.aspect.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "data" / "inventory.jsonl"
GEN = ROOT / "data" / "generated.jsonl"
IMG = ROOT / "data" / "images_cache"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open() if l.strip()]


def main() -> None:
    n = 8
    order = "newest"
    for arg in sys.argv[1:]:
        if arg.isdigit():
            n = int(arg)
        elif arg.startswith("--order="):
            order = arg.split("=", 1)[1]

    inv = load_jsonl(INV)
    gen = load_jsonl(GEN)
    done = {r["media_id"] for r in gen}

    pending = [r for r in inv if r["media_id"] not in done]
    pending.sort(key=lambda r: r["created_at"], reverse=(order == "newest"))

    batch = pending[:n]
    out = []
    for i, r in enumerate(batch):
        out.append({
            "index": i,
            "media_id": r["media_id"],
            "status_id": r["status_id"],
            "status_url": r["status_url"],
            "created_at": r["created_at"],
            "image_path": str(IMG / f"{r['media_id']}.jpg"),
            "aspect": r.get("meta", {}).get("aspect"),
            "content_text": r.get("content_text", ""),
        })
    print(json.dumps({
        "n_requested": n,
        "n_pending_total": len(pending),
        "n_done_total": len(done),
        "batch": out,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
