"""QA automático del alt-text aplicando las reglas del MASTER_PROMPT.md.

Devuelve un dict con `passed` y `issues` (lista de strings).
Las issues son etiquetas estables que `generate.py` puede inyectar como retry hint.
"""
from __future__ import annotations
import re
import unicodedata


BLACKLIST_PATTERNS = [
    r"\bcaptur(a|ó|an|aron|ar|ado|ada)\b",
    r"\bmuestr(a|an|en|e)\b",
    r"\bretrat(a|an|en|e|aron|ar|ado|ada|ando|ó)\b",
    r"\bplasm(a|ó|an)\b",
    r"\bcongel(a|ó|an)\b",
    r"\bevoc(a|ó|an)\b",
    r"\bmágic[oa]s?\b",
    r"\búnic[oa]s?\b",
    r"\bespecial(es)?\b",
    r"\bincreíbles?\b",
    r"\bimpactantes?\b",
    r"\bhermos[oa]s?\b",
    r"\bbell[oa]s?\b",
    r"\bespectacular(es)?\b",
    r"\bimpresionantes?\b",
    r"\besta imagen\b",
    r"\ben esta fotografía\b",
    r"\buna toma que\b",
    r"\bla fotografía (nos|invita|captura)",
    r"\beste momento\b",
    r"\bpara siempre\b",
    r"\bel alma de\b",
    r"\bla esencia de\b",
    r"\batrapar el instante\b",
]
BLACKLIST_RX = [re.compile(p, re.IGNORECASE) for p in BLACKLIST_PATTERNS]

EMOJI_RX = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F2FF"
    "]",
    flags=re.UNICODE,
)

BRAND_TERMS = ["umbral", "mono no aware", "物の哀れ", "impermanencia", "anicca", "polytropos"]


def count_brand_terms(text: str) -> int:
    low = text.lower()
    n = 0
    for t in BRAND_TERMS:
        n += len(re.findall(r"\b" + re.escape(t) + r"s?\b", low))
    return n


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def qa(text: str) -> dict:
    issues: list[str] = []
    chars = len(text)
    if chars < 50:
        issues.append(f"too_short:{chars}")
    if chars > 600:
        issues.append(f"too_long:{chars}")

    for rx in BLACKLIST_RX:
        m = rx.search(text)
        if m:
            issues.append(f"blacklist:{m.group(0).lower()}")

    if EMOJI_RX.search(text):
        issues.append("emoji")

    if "!" in text or "¡" in text:
        issues.append("exclamation")

    bn = count_brand_terms(text)
    if bn > 1:
        issues.append(f"brand_terms_overuse:{bn}")

    sentences = split_sentences(text)
    if len(sentences) < 2:
        issues.append(f"too_few_sentences:{len(sentences)}")

    if sentences:
        first = sentences[0]
        if len(first) < 40:
            issues.append(f"first_sentence_short:{len(first)}")

    return {"passed": not issues, "issues": issues, "chars": chars, "sentences": len(sentences)}


if __name__ == "__main__":
    import json, sys
    sample = sys.argv[1] if len(sys.argv) > 1 else "Texto de prueba muy corto."
    print(json.dumps(qa(sample), ensure_ascii=False, indent=2))
