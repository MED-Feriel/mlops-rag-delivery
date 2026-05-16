"""Producteur Kafka temps-réel — events synthétiques (incidents, commandes, livraisons)."""

from __future__ import annotations

import asyncio
import json
import os
import random
from datetime import datetime, timezone

from confluent_kafka import Producer
from faker import Faker

fake = Faker(locale="fr_FR")

ZONES = [
    "Bab Ezzouar",
    "Hydra",
    "Kouba",
    "Centre",
    "Bir Mourad Rais",
    "El Harrach",
    "Dar El Beida",
]
EVENT_TYPES = [
    "incident_ouvert",
    "commande_creee",
    "livraison_retardee",
    "commande_livree",
]


def _bootstrap() -> str:
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


def _make_event() -> tuple[str, dict]:
    et = random.choice(EVENT_TYPES)
    base = {
        "event_type": et,
        "commande_id": random.randint(10000, 99999),
        "zone": random.choice(ZONES),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if et == "incident_ouvert":
        base.update(
            {
                "type": random.choice(
                    [
                        "livreur_bloque",
                        "retard",
                        "adresse_incorrecte",
                        "restaurant_ferme",
                    ]
                ),
                "severite": random.choice(["haute", "moyenne", "basse"]),
                "description": fake.sentence(nb_words=8),
            }
        )
        return "incidents", base
    if et == "commande_creee":
        base.update(
            {
                "restaurant_nom": fake.company(),
                "montant": random.randint(500, 5000),
                "methode_paiement": random.choice(["cb", "cash", "mobile"]),
            }
        )
        return "commandes", base
    if et == "livraison_retardee":
        base.update(
            {
                "retard_min": random.randint(15, 90),
                "livreur_nom": fake.first_name(),
            }
        )
        return "livraisons", base
    # commande_livree
    base.update(
        {
            "delai_reel_min": random.randint(20, 50),
            "delai_estime_min": random.randint(20, 40),
            "note_livreur": round(random.uniform(2.5, 5.0), 1),
        }
    )
    return "livraisons", base


async def produce_events_loop(state: dict, interval_s: float = 5.0) -> None:
    """Boucle async produisant un event Kafka toutes les ``interval_s`` secondes.

    S'arrête proprement quand ``state['running']`` devient ``False``. Met à jour
    ``state['events_produced']`` et ``state['last_event']``.
    """
    producer = Producer(
        {"bootstrap.servers": _bootstrap(), "client.id": "rag-simulator"}
    )
    try:
        while state.get("running"):
            topic, evt = _make_event()
            producer.produce(topic, json.dumps(evt, ensure_ascii=False).encode("utf-8"))
            producer.poll(0)
            state["events_produced"] = state.get("events_produced", 0) + 1
            state["last_event"] = {"topic": topic, **evt}
            await asyncio.sleep(interval_s)
    finally:
        producer.flush(timeout=5)
