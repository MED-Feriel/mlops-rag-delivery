"""Chunking — découpe les textes longs avant embedding.

Stratégie : si le texte tient en un seul chunk (≤ ``chunk_size`` caractères),
on le retourne tel quel. Sinon, on découpe en respectant les séparateurs
hiérarchiques ``["\\n\\n", "\\n", ". ", " "]`` (RecursiveCharacterTextSplitter
de LangChain en fallback si la lib est dispo, sinon implémentation locale
équivalente).
"""

from __future__ import annotations

DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " "]


def _split_recursive(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    if not separators:
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    sep, rest = separators[0], separators[1:]
    parts = text.split(sep) if sep else list(text)

    chunks: list[str] = []
    buf = ""
    for p in parts:
        candidate = buf + (sep if buf else "") + p
        if len(candidate) <= chunk_size:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        if len(p) > chunk_size:
            chunks.extend(_split_recursive(p, chunk_size, rest))
            buf = ""
        else:
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    out = [chunks[0]]
    for i in range(1, len(chunks)):
        prev_tail = out[-1][-overlap:]
        out.append(prev_tail + chunks[i])
    return out


def chunk_long_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[str]:
    """Découpe ``text`` en chunks de ``chunk_size`` caractères max avec overlap.

    Si ``text`` est court, retourne ``[text]``. Sinon, applique un découpage
    récursif sur les séparateurs hiérarchiques puis ajoute l'overlap.
    """
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    raw = _split_recursive(text, chunk_size, DEFAULT_SEPARATORS)
    return _apply_overlap(raw, chunk_overlap)


def chunk_documents(
    ids: list[str],
    texts: list[str],
    metas: list[dict],
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> tuple[list[str], list[str], list[dict]]:
    """Applique ``chunk_long_text`` à une liste de documents.

    Les documents courts passent inchangés. Les longs sont scindés et leurs
    métadonnées dupliquées avec un suffixe ``-c{N}`` sur l'id.
    """
    out_ids: list[str] = []
    out_texts: list[str] = []
    out_metas: list[dict] = []
    for doc_id, text, meta in zip(ids, texts, metas):
        pieces = chunk_long_text(
            text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        if len(pieces) == 1:
            out_ids.append(doc_id)
            out_texts.append(pieces[0])
            out_metas.append(meta)
            continue
        for i, piece in enumerate(pieces):
            out_ids.append(f"{doc_id}-c{i}")
            out_texts.append(piece)
            out_metas.append({**meta, "chunk_index": i, "chunk_total": len(pieces)})
    return out_ids, out_texts, out_metas
