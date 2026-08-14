"""Regresiones del contrato SEO/accesible de los alt-text."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qa import qa  # noqa: E402


class AltTextQaTests(unittest.TestCase):
    def test_accepts_concise_specific_description(self) -> None:
        result = qa(
            "Molinos de viento blancos se alinean sobre una colina de Consuegra al atardecer."
        )
        self.assertTrue(result["passed"], result["issues"])
        self.assertLessEqual(result["words"], 25)
        self.assertEqual(result["sentences"], 1)

    def test_rejects_old_literary_style(self) -> None:
        result = qa(
            "Molinos blancos sobre una colina. La impermanencia convierte sus aspas en memoria."
        )
        self.assertFalse(result["passed"])
        self.assertIn("sentence_count:2", result["issues"])
        self.assertIn("blacklist:impermanencia", result["issues"])

    def test_rejects_redundant_intro_and_excess_words(self) -> None:
        text = (
            "Foto de una calle muy larga con edificios antiguos, varias personas, "
            "muchos coches, árboles, farolas, balcones, tiendas, montañas lejanas, "
            "señales de tráfico, terrazas y bicicletas aparcadas."
        )
        result = qa(text)
        self.assertFalse(result["passed"])
        self.assertTrue(any(issue.startswith("blacklist:") for issue in result["issues"]))
        self.assertTrue(any(issue.startswith("too_many_words:") for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
