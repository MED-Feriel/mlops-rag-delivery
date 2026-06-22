"""Fallback extractif — réponse sans LLM quand Ollama est indisponible.

Si l'appel au modèle échoue (timeout, Ollama down), plutôt que de renvoyer une
500, le pipeline construit une réponse *extractive* directement à partir des
passages récupérés : aucune génération, donc aucune hallucination, mais
l'utilisateur obtient quand même les faits bruts pertinents. Dégradation
gracieuse (C.8).
"""

from __future__ import annotations

MAX_CHUNKS = 5
MAX_SNIPPET = 280

PREFIX = (
    "⚠️ Réponse automatique dégradée (le modèle de génération est momentanément "
    "indisponible). Voici les éléments pertinents extraits des documents :"
)
SUFFIX = (
    "\n\n(Pour une réponse rédigée, réessayez quand le service LLM est rétabli — "
    "voir /health pour l'état d'Ollama.)"
)


def _snippet(text: str, limit: int = MAX_SNIPPET) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def build_extractive_answer(question: str, chunks: list[dict]) -> str:
    """Construit une réponse lisible à partir des passages, sans appel LLM."""
    usable = [c for c in (chunks or []) if (c.get("text") or "").strip()]
    if not usable:
        return (
            "Information non disponible dans le contexte fourni, et le service "
            "de génération est momentanément indisponible. Réessayez plus tard "
            "ou consultez Kibana (logs) / Grafana (métriques)."
        )
    lines = [PREFIX]
    for c in usable[:MAX_CHUNKS]:
        meta = c.get("metadata", {}) or {}
        source = meta.get("source", "?")
        zone = meta.get("zone")
        label = f"{source}" + (f", zone {zone}" if zone else "")
        lines.append(f"- ({label}) {_snippet(c.get('text', ''))}")
    return "\n".join(lines) + SUFFIX
