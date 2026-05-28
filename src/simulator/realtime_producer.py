"""Producteur Kafka temps-réel — v3.0.

Au lieu de générer des événements bruts avec faker FR, ce producteur appelle
l'Orchestrator (4 services service-like) pour simuler une commande complète
toutes les `interval_s` secondes. Chaque commande produit 5-10 événements
ventilés sur les 6 topics Kafka :

    commandes        ← ClientService (création, annulation)
    restaurants      ← RestaurantService (acceptation, préparation, fermeture)
    livraisons       ← LivreurService (mission, GPS, livraison)
    paiements        ← PaiementService (confirmation, échec, remboursement)
    incidents        ← tous services (retards, blocages, abandons)
    avis_clients     ← ClientService (commentaires, notes)

Le header `source_service` (présent dans chaque event) est copié dans les
headers Kafka pour routage côté consommateurs.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from datetime import datetime, timezone

import asyncpg
from confluent_kafka import Producer

from simulator.config import load_config
from simulator.metrics import SIM_COMMANDES_TOTAL, SIM_EVENTS_TOTAL, SIM_RUNNING
from simulator.orchestrator import Orchestrator


# Les 6 topics produits par le simulateur v3
TOPICS = {
    "commandes",
    "restaurants",
    "livraisons",
    "paiements",
    "incidents",
    "avis_clients",
}


def _bootstrap() -> str:
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


def _pg_dsn() -> str:
    return (
        f"postgres://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'secret')}@"
        f"{os.getenv('POSTGRES_HOST', 'postgres')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'livraison')}"
    )


async def _fetch_referentiel() -> dict:
    """Charge zones / restos / livreurs / clients depuis Postgres pour piocher des IDs réels."""
    conn = await asyncpg.connect(_pg_dsn())
    try:
        zones = [
            dict(r)
            for r in await conn.fetch(
                "SELECT id, nom, poids, delai_extra_min, lat, lng FROM zones"
            )
        ]
        restos = [
            dict(r) for r in await conn.fetch("SELECT id, zone_id FROM restaurants")
        ]
        livreurs = [dict(r) for r in await conn.fetch("SELECT id FROM livreurs")]
        clients = [dict(r) for r in await conn.fetch("SELECT id FROM clients")]
        max_commande_id = await conn.fetchval(
            "SELECT COALESCE(MAX(id), 0) FROM commandes"
        )
        return {
            "zones": zones,
            "restaurants": restos,
            "livreurs": livreurs,
            "clients": clients,
            "next_commande_id": (max_commande_id or 0) + 1,
        }
    finally:
        await conn.close()


def _produce_event(producer: Producer, evt: dict) -> None:
    """Publie un event sur le bon topic avec un header source_service."""
    topic = evt.get("topic")
    if topic not in TOPICS:
        # Topic inconnu — ignorer pour éviter de polluer Kafka
        return
    headers = [
        ("source_service", (evt.get("source_service") or "unknown").encode("utf-8"))
    ]
    producer.produce(
        topic,
        json.dumps(evt, ensure_ascii=False, default=str).encode("utf-8"),
        headers=headers,
    )
    producer.poll(0)


async def produce_events_loop(state: dict, interval_s: float = 5.0) -> None:
    """Boucle de production temps-réel.

    Toutes les ``interval_s`` secondes, simule une commande complète via
    l'Orchestrator et publie ses 5-10 events sur les 6 topics Kafka.

    S'arrête proprement quand ``state['running']`` devient False.
    Met à jour :
      - ``state['events_produced']`` : compteur total events Kafka
      - ``state['commandes_simulees']`` : compteur de commandes complètes
      - ``state['last_event']`` : dernier event publié (topic + payload)
      - ``state['events_par_topic']`` : dict topic → compteur
    """
    cfg = load_config()
    refs = await _fetch_referentiel()
    if (
        not refs["zones"]
        or not refs["restaurants"]
        or not refs["livreurs"]
        or not refs["clients"]
    ):
        state["error"] = "référentiel vide — exécuter static_generator d'abord"
        return
    SIM_RUNNING.set(1)

    orch = Orchestrator(cfg)
    producer = Producer(
        {"bootstrap.servers": _bootstrap(), "client.id": "rag-simulator-v3"}
    )
    zone_weights = [z["poids"] for z in refs["zones"]]
    commande_id = refs["next_commande_id"]
    state.setdefault("events_produced", 0)
    state.setdefault("commandes_simulees", 0)
    # Forcer la structure des compteurs par topic (main.py initialise à {})
    if not state.get("events_par_topic"):
        state["events_par_topic"] = {t: 0 for t in TOPICS}

    try:
        while state.get("running"):
            zone = random.choices(refs["zones"], zone_weights)[0]
            resto = random.choice(refs["restaurants"])
            livreur = random.choice(refs["livreurs"])
            client = random.choice(refs["clients"])

            events = orch.simuler_commande_complete(
                commande_id=commande_id,
                client_id=client["id"],
                restaurant_id=resto["id"],
                livreur_id=livreur["id"],
                zone=zone,
                base_timestamp=datetime.now(timezone.utc),
            )

            for evt in events:
                _produce_event(producer, evt)
                state["events_produced"] += 1
                topic = evt.get("topic") or "?"
                if topic in state["events_par_topic"]:
                    state["events_par_topic"][topic] += 1
                state["last_event"] = {"topic": topic, **evt}
                SIM_EVENTS_TOTAL.labels(
                    topic=topic,
                    source_service=evt.get("source_service", "unknown"),
                    event_type=evt.get("event_type", "unknown"),
                ).inc()

            # Détecter le destin de la commande pour la métrique outcome
            event_types = {e.get("event_type") for e in events}
            if "livraison_terminée" in event_types:
                SIM_COMMANDES_TOTAL.labels(destin="livree").inc()
            elif "livraison_échouée" in event_types:
                SIM_COMMANDES_TOTAL.labels(destin="echouee").inc()
            elif "commande_annulée" in event_types or "commande_refusée" in event_types:
                SIM_COMMANDES_TOTAL.labels(destin="annulee").inc()

            state["commandes_simulees"] += 1
            commande_id += 1
            await asyncio.sleep(interval_s)
    finally:
        SIM_RUNNING.set(0)
        producer.flush(timeout=5)
