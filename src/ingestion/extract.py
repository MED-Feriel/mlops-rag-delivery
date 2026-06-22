"""Extract — lit les données opérationnelles depuis Postgres et Kafka."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import asyncpg
import structlog

log = structlog.get_logger()


def _dsn() -> str:
    return (
        f"postgres://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'secret')}@"
        f"{os.getenv('POSTGRES_HOST', 'postgres')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'livraison')}"
    )


SQL_INCIDENTS_ACTIFS = """
SELECT i.id, i.type, i.severite, i.description, i.resolu, i.created_at,
       c.id AS commande_id, c.statut, c.zone_id, c.restaurant_id, c.livreur_id,
       z.nom AS zone_nom, r.nom AS restaurant_nom, l.nom AS livreur_nom
FROM incidents i
JOIN commandes c ON c.id = i.commande_id
JOIN zones z ON z.id = c.zone_id
JOIN restaurants r ON r.id = c.restaurant_id
JOIN livreurs l ON l.id = c.livreur_id
ORDER BY i.created_at DESC
"""

SQL_AVIS_CLIENTS = """
SELECT a.id, a.commande_id, a.note, a.commentaire, a.sentiment, a.created_at,
       c.statut, c.delai_reel_min, c.delai_estime_min, c.montant,
       z.nom AS zone_nom, r.nom AS restaurant_nom, l.nom AS livreur_nom
FROM avis_clients a
JOIN commandes c ON c.id = a.commande_id
JOIN zones z ON z.id = c.zone_id
JOIN restaurants r ON r.id = c.restaurant_id
JOIN livreurs l ON l.id = c.livreur_id
ORDER BY a.created_at DESC
"""

SQL_COMMANDES_RECENTES_OU_EN_RETARD = """
SELECT c.id, c.statut, c.montant, c.montant_total, c.delai_estime_min, c.delai_reel_min,
       c.note_livreur, c.commentaire, c.methode_paiement, c.created_at, c.livre_at,
       c.canal_commande, c.delai_preparation_reel_min,
       z.nom AS zone_nom, r.nom AS restaurant_nom, l.nom AS livreur_nom,
       (COALESCE(c.delai_reel_min, 0) - c.delai_estime_min) AS retard_min
FROM commandes c
JOIN zones z ON z.id = c.zone_id
JOIN restaurants r ON r.id = c.restaurant_id
JOIN livreurs l ON l.id = c.livreur_id
WHERE c.created_at > NOW() - INTERVAL '24 hours'
   OR (c.delai_reel_min IS NOT NULL AND c.delai_reel_min - c.delai_estime_min > 30)
ORDER BY c.created_at DESC
LIMIT 500
"""

SQL_RESTAURANT_SNAPSHOTS = """
SELECT r.id, r.nom, r.type_cuisine, r.note_moyenne, z.nom AS zone_nom,
       r.categorie, r.heure_ouverture, r.heure_fermeture, r.delai_prep_moyen,
       COUNT(c.id) AS nb_commandes_30j,
       COUNT(*) FILTER (WHERE c.statut = 'annulee') AS nb_annulees,
       COUNT(*) FILTER (WHERE c.statut = 'echouee') AS nb_echouees,
       AVG(c.note_livreur) AS note_moyenne_30j,
       AVG(GREATEST(c.delai_reel_min - c.delai_estime_min, 0)) AS retard_moyen
FROM restaurants r
JOIN zones z ON z.id = r.zone_id
LEFT JOIN commandes c
       ON c.restaurant_id = r.id
      AND c.created_at > NOW() - INTERVAL '30 days'
GROUP BY r.id, r.nom, r.type_cuisine, r.note_moyenne, z.nom,
         r.categorie, r.heure_ouverture, r.heure_fermeture, r.delai_prep_moyen
"""

SQL_LIVREUR_SNAPSHOTS = """
SELECT l.id, l.prenom, l.nom, l.vehicule_type, l.annee_experience,
       l.note_moyenne, l.note_ponctualite, l.statut, z.nom AS zone_nom,
       COUNT(c.id) AS nb_commandes_30j,
       COUNT(*) FILTER (WHERE c.statut = 'livree') AS nb_livraisons_reussies,
       COUNT(*) FILTER (WHERE c.statut IN ('annulee','echouee')) AS nb_echecs,
       AVG(GREATEST(c.delai_reel_min - c.delai_estime_min, 0)) AS retard_moyen
FROM livreurs l
JOIN zones z ON z.id = l.zone_principale_id
LEFT JOIN commandes c
       ON c.livreur_id = l.id
      AND c.created_at > NOW() - INTERVAL '30 days'
GROUP BY l.id, l.prenom, l.nom, l.vehicule_type, l.annee_experience,
         l.note_moyenne, l.note_ponctualite, l.statut, z.nom
"""

SQL_ZONE_SNAPSHOTS = """
SELECT z.id, z.nom,
       COUNT(c.id) AS nb_commandes_30j,
       COUNT(*) FILTER (WHERE c.statut = 'annulee') AS nb_annulees,
       AVG(c.delai_reel_min) AS delai_moyen,
       AVG(GREATEST(c.delai_reel_min - c.delai_estime_min, 0)) AS retard_moyen,
       AVG(c.note_livreur) AS note_moyenne
FROM zones z
LEFT JOIN commandes c
       ON c.zone_id = z.id
      AND c.created_at > NOW() - INTERVAL '30 days'
GROUP BY z.id, z.nom
"""


SQL_AGG_INCIDENT_TYPES = """
SELECT type, severite, COUNT(*) AS n,
       COUNT(*) FILTER (WHERE NOT resolu) AS n_actifs,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM incidents
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY type, severite
ORDER BY n DESC
"""

SQL_AGG_TOP_RESTAURANTS_PROBLEMATIQUES = """
SELECT r.id, r.nom, z.nom AS zone_nom,
       COUNT(c.id) AS nb_commandes,
       COUNT(*) FILTER (WHERE c.statut = 'annulee') AS nb_annulees,
       COUNT(*) FILTER (WHERE c.statut = 'echouee') AS nb_echouees,
       ROUND(100.0 * COUNT(*) FILTER (WHERE c.statut IN ('annulee','echouee'))
             / NULLIF(COUNT(c.id), 0), 1) AS pct_problemes,
       AVG(GREATEST(c.delai_reel_min - c.delai_estime_min, 0)) AS retard_moyen
FROM restaurants r
JOIN zones z ON z.id = r.zone_id
LEFT JOIN commandes c ON c.restaurant_id = r.id
                       AND c.created_at > NOW() - INTERVAL '30 days'
GROUP BY r.id, r.nom, z.nom
HAVING COUNT(c.id) > 5
ORDER BY pct_problemes DESC NULLS LAST
LIMIT 10
"""

SQL_AGG_PAIEMENTS = """
SELECT methode_paiement, statut, COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY methode_paiement), 1) AS pct_methode
FROM commandes
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY methode_paiement, statut
ORDER BY methode_paiement, n DESC
"""

SQL_AGG_INCIDENTS_PAR_ZONE = """
SELECT z.nom AS zone_nom, i.type, COUNT(*) AS n
FROM incidents i
JOIN commandes c ON c.id = i.commande_id
JOIN zones z ON z.id = c.zone_id
WHERE i.created_at > NOW() - INTERVAL '30 days'
GROUP BY z.nom, i.type
ORDER BY z.nom, n DESC
"""

SQL_AGG_TENDANCE_VOLUME = """
SELECT DATE(created_at) AS jour,
       COUNT(*) AS nb_commandes,
       COUNT(*) FILTER (WHERE statut = 'annulee') AS nb_annulees,
       AVG(note_livreur) AS note_moyenne,
       AVG(GREATEST(delai_reel_min - delai_estime_min, 0)) AS retard_moyen
FROM commandes
WHERE created_at > NOW() - INTERVAL '14 days'
GROUP BY DATE(created_at)
ORDER BY jour DESC
"""


_KAFKA_NOISE_EVENTS = {"gps", "gps_ping", "heartbeat", "tick"}


def extract_kafka(
    bootstrap_servers: str,
    group_id: str,
    topics: list[str],
    max_messages: int = 300,
    poll_timeout: float = 1.0,
    from_beginning: bool = False,
) -> list[dict]:
    """Consomme un batch Kafka et retourne une liste de messages normalisés.

    - Filtre les événements purement GPS/heartbeat (pas de valeur RAG).
    - Commit manuel à la fin pour ne pas perdre de messages en cas d'échec
      d'indexation Qdrant en aval.

    Le commit est laissé à l'appelant via le retour ``.commit_fn`` n'est PAS
    exposé ici pour rester simple : on commit en fin de poll si tout va bien.
    """
    try:
        from confluent_kafka import Consumer, KafkaError  # type: ignore
    except ImportError:
        log.warning("confluent_kafka indisponible — extract_kafka skip")
        return []

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest" if from_beginning else "latest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(topics)
    out: list[dict] = []
    empty_polls = 0
    try:
        for _ in range(max_messages):
            msg = consumer.poll(timeout=poll_timeout)
            if msg is None:
                empty_polls += 1
                if empty_polls >= 3:
                    break
                continue
            empty_polls = 0
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                log.warning("kafka error", error=str(msg.error()))
                continue
            try:
                payload = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                log.warning("kafka decode failed", error=str(e))
                continue
            event_type = (payload.get("event_type") or "").lower()
            if event_type in _KAFKA_NOISE_EVENTS:
                continue
            out.append(
                {
                    **payload,
                    "_topic": msg.topic(),
                    "_offset": msg.offset(),
                    "_partition": msg.partition(),
                    "_kafka_ts": datetime.now(timezone.utc).isoformat(),
                }
            )
        # Commit même si 0 messages : avance l'offset au HEAD de chaque partition
        # pour que le run suivant ne rate pas les events produits entre-temps.
        try:
            consumer.commit(asynchronous=False)
        except Exception as e:
            log.warning("kafka commit failed", error=str(e))
    finally:
        consumer.close()
    log.info("kafka extract done", n=len(out), topics=topics)
    return out


async def extract_all() -> dict[str, list[dict]]:
    conn = await asyncpg.connect(_dsn())
    try:
        return {
            "incidents_actifs": [
                dict(r) for r in await conn.fetch(SQL_INCIDENTS_ACTIFS)
            ],
            "avis_clients": [dict(r) for r in await conn.fetch(SQL_AVIS_CLIENTS)],
            "commandes": [
                dict(r) for r in await conn.fetch(SQL_COMMANDES_RECENTES_OU_EN_RETARD)
            ],
            "restaurants": [
                dict(r) for r in await conn.fetch(SQL_RESTAURANT_SNAPSHOTS)
            ],
            "livreurs": [dict(r) for r in await conn.fetch(SQL_LIVREUR_SNAPSHOTS)],
            "zones": [dict(r) for r in await conn.fetch(SQL_ZONE_SNAPSHOTS)],
            "agg_incident_types": [
                dict(r) for r in await conn.fetch(SQL_AGG_INCIDENT_TYPES)
            ],
            "agg_top_restaurants": [
                dict(r)
                for r in await conn.fetch(SQL_AGG_TOP_RESTAURANTS_PROBLEMATIQUES)
            ],
            "agg_paiements": [dict(r) for r in await conn.fetch(SQL_AGG_PAIEMENTS)],
            "agg_incidents_par_zone": [
                dict(r) for r in await conn.fetch(SQL_AGG_INCIDENTS_PAR_ZONE)
            ],
            "agg_tendance_volume": [
                dict(r) for r in await conn.fetch(SQL_AGG_TENDANCE_VOLUME)
            ],
        }
    finally:
        await conn.close()
