from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site  # noqa: E402


def sample_photo() -> dict:
    return {
        "media_id": "m1",
        "status_id": "s1",
        "status_url": "https://pixelfed.social/p/HispaniaObscura/s1",
        "image_url": "https://cdn.example/foto.jpg?size=large&format=jpeg",
        "preview_url": "https://cdn.example/foto-thumb.jpg",
        "alt_text": "Una puerta queda entreabierta y deja pasar una franja de luz tranquila.",
        "alt_is_real": True,
        "place": {"name": "Madrid", "country": "Spain"},
        "created_at": "2026-05-01T12:00:00.000Z",
        "content_text": "",
        "meta": {"width": 1200, "height": 800},
        "position_in_status": 0,
        "total_in_status": 1,
    }


class SiteSemantics(unittest.TestCase):
    def test_home_has_one_content_heading_and_federated_identity(self) -> None:
        html = build_site.render_index_page(1, 1, [sample_photo()], False)

        self.assertEqual(len(re.findall(r"<h1\b", html)), 1)
        self.assertIn("Fotografías de umbrales y vida cotidiana", html)
        self.assertIn(
            '<link rel="me" href="https://masto.impermanente.es/@jrcruciani">',
            html,
        )
        self.assertIn(
            '<meta name="fediverse:creator" content="@jrcruciani@masto.impermanente.es">',
            html,
        )
        self.assertIn('<meta property="og:image:alt"', html)
        self.assertIn('<meta name="twitter:image"', html)

    def test_photo_page_uses_article_metadata_and_figure(self) -> None:
        photo = sample_photo()
        html = build_site.render_photo_page(photo, None, None)

        self.assertEqual(len(re.findall(r"<h1\b", html)), 1)
        self.assertIn('<meta property="og:type" content="article">', html)
        self.assertIn(
            '<meta property="article:published_time" content="2026-05-01T12:00:00.000Z">',
            html,
        )
        self.assertIn("<figure", html)
        self.assertIn("<figcaption", html)

    def test_sitemap_contains_valid_image_extension(self) -> None:
        photo = sample_photo()
        root = ET.fromstring(build_site.render_sitemap([photo], 1))
        namespaces = {
            "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
            "image": "http://www.google.com/schemas/sitemap-image/1.1",
        }

        image_loc = root.find(
            ".//sm:url[sm:loc='https://fotos.impermanente.es/foto/s1/']"
            "/image:image/image:loc",
            namespaces,
        )
        self.assertIsNotNone(image_loc)
        self.assertEqual(
            image_loc.text,
            "https://cdn.example/foto.jpg?size=large&format=jpeg",
        )


if __name__ == "__main__":
    unittest.main()
