"""Regresión para append_generated.write_all con created_at nulo/ausente.

Reproduce el bug del issue #1: antes del fix, ordenar registros con
`created_at: null` lanzaba TypeError ('<' not supported between str y NoneType).

Stdlib only (unittest). Ejecutar:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import append_generated  # noqa: E402


class WriteAllNullCreatedAt(unittest.TestCase):
    def test_sorts_with_null_and_missing_created_at(self) -> None:
        records = {
            "1": {"media_id": "1", "created_at": None, "alt_text": "a"},
            "2": {"media_id": "2", "created_at": "2026-01-01T00:00:00Z", "alt_text": "b"},
            "3": {"media_id": "3", "alt_text": "c"},  # created_at ausente
        }
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "generated.jsonl"
            original = append_generated.OUT_PATH
            append_generated.OUT_PATH = out
            try:
                append_generated.write_all(records)  # no debe lanzar TypeError
            finally:
                append_generated.OUT_PATH = original
            lines = out.read_text().splitlines()

        self.assertEqual(len(lines), 3)
        parsed = [json.loads(line) for line in lines]
        # None y ausente se normalizan a "" y ordenan antes que la fecha real.
        self.assertEqual(parsed[-1]["media_id"], "2")
        self.assertEqual({p["media_id"] for p in parsed}, {"1", "2", "3"})


if __name__ == "__main__":
    unittest.main()
