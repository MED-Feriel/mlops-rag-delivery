"""Construit le contexte texte concaténé à partir des chunks récupérés."""


def build_context(chunks: list[dict], max_chars: int = 4000) -> str:
    # Promouvoir les documents de synthèse (listes Top-N, agrégations) en tête de
    # contexte : ils contiennent l'ordre du classement qui répond directement aux
    # questions superlatives. Stable au sein de chaque groupe : on garde le score.
    sorted_chunks = sorted(
        chunks,
        key=lambda c: (
            0 if c.get("metadata", {}).get("source") == "synthese" else 1,
            -float(c.get("score", 0)),
        ),
    )
    parts: list[str] = []
    total = 0
    for i, chunk in enumerate(sorted_chunks, 1):
        meta = chunk.get("metadata", {})
        header = f"[Doc {i} | source={meta.get('source', '?')} | score={chunk.get('score', 0):.2f}]"
        body = chunk.get("text", "")
        block = f"{header}\n{body}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)
