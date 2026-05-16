"""Construit le contexte texte concaténé à partir des chunks récupérés."""


def build_context(chunks: list[dict], max_chars: int = 4000) -> str:
    parts: list[str] = []
    total = 0
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        header = f"[Doc {i} | source={meta.get('source', '?')} | score={chunk.get('score', 0):.2f}]"
        body = chunk.get("text", "")
        block = f"{header}\n{body}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)
