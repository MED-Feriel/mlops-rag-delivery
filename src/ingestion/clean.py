"""Clean — déduplication, filtrage des nulls et valeurs aberrantes.

Opère sur le résultat de ``extract_all()`` (dict[str, list[dict]]) ou sur une
liste plate de documents. Les lignes rejetées sont écrites dans
``etl_rejects.jsonl`` pour audit, et un compteur est retourné.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable

import structlog

log = structlog.get_logger()

REQUIRED_BY_SOURCE: dict[str, set[str]] = {
    "incidents_actifs": {"id", "type", "severite", "created_at", "commande_id"},
    "commandes": {"id", "statut", "created_at"},
    "restaurants": {"id", "nom"},
    "zones": {"id", "nom"},
}

REJECTS_PATH = Path(os.getenv("ETL_REJECTS_PATH", "/tmp/etl_rejects.jsonl"))


def _is_valid(row: dict, required: set[str]) -> bool:
    return all(row.get(k) not in (None, "") for k in required)


def _fix_negative_delays(row: dict) -> dict:
    """Délais négatifs → None (les SQL produisent parfois GREATEST(...,0), mais pas toujours)."""
    for key in ("delai_reel_min", "retard_min", "retard_moyen"):
        v = row.get(key)
        if isinstance(v, (int, float)) and v < 0:
            row[key] = None
    return row


def _dedupe(rows: list[dict], key: str = "id") -> list[dict]:
    """Dédup en gardant la version la plus récente (par updated_at puis created_at)."""
    by_key: dict = {}
    for r in rows:
        k = r.get(key)
        if k is None:
            continue
        existing = by_key.get(k)
        if existing is None:
            by_key[k] = r
            continue
        ts_new = r.get("updated_at") or r.get("created_at") or datetime.min
        ts_old = (
            existing.get("updated_at") or existing.get("created_at") or datetime.min
        )
        if ts_new >= ts_old:
            by_key[k] = r
    return list(by_key.values())


def _write_rejects(rejects: Iterable[dict]) -> None:
    REJECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REJECTS_PATH.open("a", encoding="utf-8") as f:
        for r in rejects:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


def clean_rows(source: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Nettoie une liste de lignes pour une source donnée.

    Retourne (kept, rejected).
    """
    required = REQUIRED_BY_SOURCE.get(source, set())
    deduped = _dedupe(rows) if any("id" in r for r in rows) else rows
    kept: list[dict] = []
    rejected: list[dict] = []
    for r in deduped:
        if required and not _is_valid(r, required):
            rejected.append({"_source": source, "_reason": "missing_required", **r})
            continue
        kept.append(_fix_negative_delays(r))
    return kept, rejected


def clean(extract_result: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Nettoie l'ensemble du résultat d'extraction.

    Persiste les rejets dans ``etl_rejects.jsonl`` et logue les compteurs.
    """
    cleaned: dict[str, list[dict]] = {}
    all_rejects: list[dict] = []
    for source, rows in extract_result.items():
        kept, rejected = clean_rows(source, rows)
        cleaned[source] = kept
        all_rejects.extend(rejected)
        if rejected:
            log.warning(
                "clean: lignes rejetées",
                source=source,
                kept=len(kept),
                rejected=len(rejected),
            )
    if all_rejects:
        _write_rejects(all_rejects)
    return cleaned
