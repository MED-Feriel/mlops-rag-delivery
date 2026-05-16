"""Normalize — schéma unifié pour tous les documents avant indexation.

Schéma cible :
    {
        "id":         str,
        "source":     str,           # commandes, incidents, restaurants, zones, kafka, synthese
        "topic":      str,
        "timestamp":  str (ISO UTC),
        "zone":       str,
        "statut":     str,
        "criticite":  str ("haute"|"moyenne"|"basse"|"info"),
        "type_event": str,
        "texte":      str,
    }
"""

from __future__ import annotations

from datetime import datetime, timezone

UNIFIED_FIELDS = {
    "id",
    "source",
    "topic",
    "timestamp",
    "zone",
    "statut",
    "criticite",
    "type_event",
    "texte",
}


def _to_iso_utc(value) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _criticite_from_retard(retard_min: float | None) -> str:
    """haute si retard > 60, moyenne si > 30, basse si > 10, sinon info."""
    if retard_min is None:
        return "info"
    if retard_min > 60:
        return "haute"
    if retard_min > 30:
        return "moyenne"
    if retard_min > 10:
        return "basse"
    return "info"


def normalize(doc: dict) -> dict:
    """Garantit la présence de tous les champs du schéma unifié.

    Accepte un doc partiel (ex: produit par ``document_builder``) et complète les
    champs manquants. Calcule ``criticite`` à partir de ``delai_reel_min`` ou
    ``retard_min`` si présent et non déjà spécifié.
    """
    out: dict = {
        "id": str(doc.get("id") or doc.get("_id") or ""),
        "source": doc.get("source", "unknown"),
        "topic": doc.get("topic", doc.get("source", "unknown")),
        "timestamp": _to_iso_utc(doc.get("timestamp") or doc.get("created_at")),
        "zone": doc.get("zone") or doc.get("zone_nom") or "all",
        "statut": doc.get("statut") or doc.get("type_event") or "n/a",
        "type_event": doc.get("type_event")
        or doc.get("type")
        or doc.get("statut")
        or "n/a",
        "texte": doc.get("texte") or doc.get("text") or "",
    }

    if "criticite" in doc and doc["criticite"]:
        out["criticite"] = doc["criticite"]
    else:
        retard = doc.get("retard_min")
        if retard is None and doc.get("delai_reel_min") and doc.get("delai_estime_min"):
            retard = doc["delai_reel_min"] - doc["delai_estime_min"]
        out["criticite"] = _criticite_from_retard(retard)

    return out


def normalize_all(docs: list[dict]) -> list[dict]:
    return [normalize(d) for d in docs]
