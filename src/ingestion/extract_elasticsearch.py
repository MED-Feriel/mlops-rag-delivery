"""Extraction des événements problématiques depuis Elasticsearch → Qdrant.

Famille 2 (logs applicatifs) : permet au RAG de répondre aux questions sur les
erreurs / incidents récents observés sur la plateforme.

NOTE IMPORTANTE (audit 2026-05-29) : les indices ``livraison-*`` ne contiennent
PAS de logs applicatifs avec un champ ``level`` (ERROR/WARN). Ce sont des
événements métier routés depuis Kafka par Logstash. La notion d'« erreur / log »
est donc dérivée de ``event_type`` (décision validée) :

    ERROR  (criticité haute)   : livraison_échouée, paiement_échoué, paiement_abandonné
    WARN   (criticité moyenne) : retard_détecté, commande_annulée, commande_refusée

Fenêtre : 5 dernières minutes (overlap pour ne rien rater).
Exécuté toutes les 2 minutes par le DAG ``rag_logs_indexer``.
Déduplication : ID déterministe → un même event n'est jamais indexé deux fois.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

import httpx
import structlog

log = structlog.get_logger()

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
INDICES = "livraison-*"

# event_type → (niveau pseudo-log, criticité). Joue le rôle du filtre ERROR/WARN.
_EVENT_LEVELS: dict[str, tuple[str, str]] = {
    "livraison_échouée": ("ERROR", "haute"),
    "paiement_échoué": ("ERROR", "haute"),
    "paiement_abandonné": ("ERROR", "haute"),
    "retard_détecté": ("WARN", "moyenne"),
    "commande_annulée": ("WARN", "moyenne"),
    "commande_refusée": ("WARN", "moyenne"),
}
PROBLEM_EVENTS = list(_EVENT_LEVELS.keys())


async def extract_logs_from_es(
    window_minutes: int = 5,
    event_types: list | None = None,
) -> list[dict]:
    """Requête Elasticsearch pour les événements problématiques récents.

    Retourne une liste de documents normalisés prêts pour Qdrant.
    """
    event_types = event_types or PROBLEM_EVENTS
    since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()

    query = {
        "size": 200,
        "query": {
            "bool": {
                "must": [
                    {"terms": {"event_type.keyword": event_types}},
                    {"range": {"@timestamp": {"gte": since}}},
                ]
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "_source": [
            "event_type",
            "source_service",
            "topic",
            "commande_id",
            "livreur_id",
            "zone",
            "statut",
            "raison",
            "depassement_min",
            "delai_estime_min",
            "delai_reel_min",
            "montant",
            "methode",
            "@timestamp",
            "timestamp",
        ],
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{ES_URL}/{INDICES}/_search",
            json=query,
            headers={"Content-Type": "application/json"},
        )
        if r.status_code != 200:
            log.warning("es_query_failed", status=r.status_code, body=r.text[:200])
            return []

        hits = r.json().get("hits", {}).get("hits", [])
        return [_normalize_log(h["_source"]) for h in hits]


def _phrase(src: dict, level: str) -> str:
    """Construit une phrase naturelle pour l'embedding à partir d'un event métier."""
    et = src.get("event_type", "événement")
    service = src.get("source_service", "service inconnu")
    cid = src.get("commande_id")
    zone = src.get("zone")

    texte = f"Log {level} — {et} — service {service}"
    if cid:
        texte += f" — commande {cid}"
    if zone:
        texte += f" — zone {zone}"

    # Détails contextuels selon le type d'event
    if src.get("depassement_min"):
        texte += (
            f" : retard de {src['depassement_min']} min "
            f"(estimé {src.get('delai_estime_min', '?')} min, "
            f"réel {src.get('delai_reel_min', '?')} min)"
        )
    elif src.get("raison"):
        texte += f" : {src['raison']}"
    elif src.get("statut"):
        montant = src.get("montant")
        methode = src.get("methode")
        texte += f" : paiement {src['statut']}"
        if methode:
            texte += f" ({methode})"
        if montant:
            texte += f", montant {montant}"
    else:
        texte += " détecté sur la plateforme"
    return texte


def _normalize_log(src: dict) -> dict:
    """Transforme un événement ES en document Qdrant."""
    et = src.get("event_type", "unknown")
    level, criticite = _EVENT_LEVELS.get(et, ("WARN", "moyenne"))
    service = src.get("source_service", "unknown")
    ts = (
        src.get("@timestamp")
        or src.get("timestamp")
        or datetime.now(timezone.utc).isoformat()
    )
    cid = src.get("commande_id")

    texte = _phrase(src, level)

    # ID déterministe pour déduplication (même event → même point Qdrant)
    doc_id = (
        "log_" + hashlib.md5(f"{ts}_{service}_{et}_{cid}".encode()).hexdigest()[:16]
    )

    return {
        "id": doc_id,
        "source": "elasticsearch",
        "source_service": service,
        "topic": "logs",
        "type_event": f"log_{level.lower()}",
        "criticite": criticite,
        "zone": src.get("zone", "") or "all",
        "timestamp": ts,
        "commande_id": cid,
        "texte": texte,
        # TTL informatif : les logs sont volatils (2h)
        "ttl_hours": 2,
    }


async def index_logs_to_qdrant(qdrant_store, embedder) -> int:
    """Pipeline complet : ES → embed → upsert Qdrant. Retourne le nb indexé."""
    docs = await extract_logs_from_es()
    if not docs:
        log.info("es_logs_no_documents")
        return 0

    texts = [d["texte"] for d in docs]
    ids = [d["id"] for d in docs]
    metadatas = [{k: v for k, v in d.items() if k not in ("texte", "id")} for d in docs]

    # Embedder.embed() est synchrone (sentence-transformers) → executor pour ne
    # pas bloquer la boucle asyncio.
    import asyncio

    loop = asyncio.get_event_loop()
    vectors = await loop.run_in_executor(None, lambda: embedder.embed(texts))

    n = qdrant_store.upsert(ids, vectors, texts, metadatas)
    log.info("es_logs_indexed", n=n, extracted=len(docs))
    return n
