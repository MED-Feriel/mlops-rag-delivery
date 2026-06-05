"""Drift monitoring léger (C.4) — Population Stability Index sur Qdrant.

Plutôt qu'un drift d'embeddings coûteux, on surveille la **distribution** d'un
champ catégoriel du payload (ex: ``source``, ``criticite``, ``type_event``)
échantillonné dans Qdrant, comparée à une baseline. L'indice PSI quantifie
l'écart :
    PSI < 0.1  → stable
    0.1–0.2    → drift modéré (à surveiller)
    > 0.2      → drift significatif (ré-indexation / ré-éval conseillée)

Fonctions pures (testables) + helpers baseline Redis. Aucune dépendance lourde.
"""

from __future__ import annotations

import json
import math

import structlog

log = structlog.get_logger()

MISSING = "∅"


def distribution_from_points(points: list[dict], field: str) -> dict[str, int]:
    """Compte les occurrences de ``field`` dans les payloads échantillonnés."""
    counts: dict[str, int] = {}
    for p in points:
        val = str((p.get("payload") or {}).get(field, MISSING))
        counts[val] = counts.get(val, 0) + 1
    return counts


def _proportions(counts: dict) -> dict:
    total = sum(counts.values()) or 1
    return {k: v / total for k, v in counts.items()}


def population_stability_index(
    expected: dict, actual: dict, eps: float = 1e-6
) -> float:
    """PSI entre deux distributions de comptes. 0 = identiques."""
    e = _proportions(expected)
    a = _proportions(actual)
    psi = 0.0
    for cat in set(e) | set(a):
        ep = max(e.get(cat, 0.0), eps)
        ap = max(a.get(cat, 0.0), eps)
        psi += (ap - ep) * math.log(ap / ep)
    return round(psi, 4)


def drift_level(psi: float) -> str:
    if psi < 0.1:
        return "none"
    if psi < 0.2:
        return "moderate"
    return "significant"


# ── Baseline persistée en Redis ───────────────────────────────────────────
def baseline_key(field: str) -> str:
    return f"drift:baseline:{field}"


def get_baseline(redis_client, field: str) -> dict | None:
    if redis_client is None:
        return None
    try:
        raw = redis_client.get(baseline_key(field))
        return json.loads(raw) if raw else None
    except Exception as e:  # pragma: no cover - best effort
        log.warning("drift_baseline_get_error", error=str(e))
        return None


def set_baseline(redis_client, field: str, counts: dict) -> bool:
    if redis_client is None:
        return False
    try:
        redis_client.set(baseline_key(field), json.dumps(counts))
        return True
    except Exception as e:  # pragma: no cover - best effort
        log.warning("drift_baseline_set_error", error=str(e))
        return False


def build_redis(settings):
    """Client Redis dédié au drift (fallback None si indisponible)."""
    try:
        import redis

        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=False,
        )
        client.ping()
        return client
    except Exception:
        return None
