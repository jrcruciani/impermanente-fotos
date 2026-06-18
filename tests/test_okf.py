from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".scratch" / "test-okf-output"


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path} no empieza con frontmatter")
    raw = text.split("---\n", 2)[1]
    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line or line.startswith("  - "):
            continue
        key, value = line.split(":", 1)
        parsed[key] = value.strip().strip('"')
    return parsed


class OkfConformance(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(OUT, ignore_errors=True)

    def tearDown(self) -> None:
        shutil.rmtree(OUT, ignore_errors=True)

    def test_build_okf_conformance(self) -> None:
        items = [
            {
                "media_id": "m1",
                "status_id": "s1",
                "status_url": "https://pixelfed.social/p/HispaniaObscura/s1",
                "image_url": "https://cdn.example/foto.jpg",
                "preview_url": "https://cdn.example/foto-thumb.jpg",
                "alt_text": "Una puerta queda entreabierta y deja pasar una franja de luz tranquila.",
                "alt_is_real": True,
                "place": {"name": "Madrid", "country": "Spain"},
                "created_at": "2026-05-01T12:00:00.000Z",
                "content_text": "",
                "meta": {},
                "position_in_status": 0,
                "total_in_status": 1,
            }
        ]
        collections = [
            {
                "slug": "umbrales",
                "title": "Umbrales",
                "description": "Pasajes y orillas.",
                "updated_at": "2026-05-02T00:00:00.000Z",
                "status_ids": ["s1"],
            }
        ]

        concepts = build_site.build_okf(OUT, items, collections)
        self.assertEqual(concepts, 2)
        self.assertEqual(frontmatter(OUT / "okf" / "index.md").get("okf_version"), "0.1")

        for path in (OUT / "okf").rglob("*.md"):
            if path.name in {"index.md", "log.md"}:
                continue
            fields = frontmatter(path)
            self.assertTrue(fields.get("type"), path)

        output = "\n".join(p.read_text(encoding="utf-8") for p in (OUT / "okf").rglob("*.md"))
        self.assertNotIn("/Users/", output)
        self.assertIn("[Umbrales](/colecciones/umbrales.md)", output)
        self.assertIn("[Madrid, Spain · 1 may 2026](/fotografias/s1.md)", output)


if __name__ == "__main__":
    unittest.main()
