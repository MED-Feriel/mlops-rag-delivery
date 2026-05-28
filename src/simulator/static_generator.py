"""
Génération des données statiques — v3.0 (Hello Delivery, 6 mois, noms algériens).

Architecture :
- Insère zones, restaurants, livreurs, clients (noms 100% algériens).
- Pour chaque timestamp généré (bimodal × jour × saison), appelle
  l'Orchestrator qui simule la commande à travers les 4 services
  (Client, Restaurant, Livreur, Paiement) et retourne une liste d'events.
- Les events sont ensuite ventilés vers les bonnes tables :
    commandes, livraisons, paiements, incidents, avis_clients
- IDs assignés par l'application (schema sans SERIAL).
- Batch flush de 5 000 commandes (avec leurs events corrélés)
  via asyncpg unnest() — beaucoup plus rapide qu'executemany.

Usage :
    python -m simulator.static_generator
    SIM_JOURS=1 python -m simulator.static_generator   # smoke test 1 jour
"""

from __future__ import annotations

import asyncio
import math
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import structlog

from simulator import algerian_names
from simulator.config import load_config
from simulator.db import connect
from simulator.orchestrator import Orchestrator
from simulator.timestamp_generator import generate_timestamps

log = structlog.get_logger()

SCHEMA_FILE = Path(__file__).parent / "schema.sql"
BATCH_SIZE = 5000

TYPES_CUISINE = [
    "fast-food",
    "pizza",
    "traditionnel",
    "asiatique",
    "burger",
    "halal",
    "végétarien",
    "tacos",
    "grillade",
    "sandwich",
]


# ───────────────────────────────────────────────────────────────
# ENTITÉS STATIQUES
# ───────────────────────────────────────────────────────────────


async def insert_zones(conn, cfg: dict) -> list[dict]:
    rows = []
    for i, z in enumerate(cfg["zones"], start=1):
        await conn.execute(
            """INSERT INTO zones (id, nom, poids, delai_extra_min, lat, lng)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            i,
            z["nom"],
            z["poids"],
            z.get("delai_extra_min", 0),
            z.get("lat"),
            z.get("lng"),
        )
        rows.append(
            {
                "id": i,
                "nom": z["nom"],
                "poids": z["poids"],
                "delai_extra_min": z.get("delai_extra_min", 0),
                "lat": z.get("lat"),
                "lng": z.get("lng"),
            }
        )
    log.info("zones insérées", n=len(rows))
    return rows


async def insert_restaurants(conn, cfg: dict, zones: list[dict]) -> list[dict]:
    n = cfg["volume"]["nb_restaurants"]
    zone_weights = [z["poids"] for z in zones]
    ids, noms, zone_ids, cuisines, notes = [], [], [], [], []
    rows = []

    # Distribution Pareto-like : top restaurants concentrés sur premières zones populaires
    for i in range(n):
        z = random.choices(zones, zone_weights)[0]
        nom = algerian_names.random_nom_restaurant(zone=z["nom"], idx=i)
        cuisine = random.choice(TYPES_CUISINE)
        note = float(np.clip(np.random.normal(4.0, 0.5), 1.0, 5.0))
        rid = i + 1
        ids.append(rid)
        noms.append(nom)
        zone_ids.append(z["id"])
        cuisines.append(cuisine)
        notes.append(note)
        rows.append({"id": rid, "zone_id": z["id"], "nom": nom})

    await conn.execute(
        """INSERT INTO restaurants (id, nom, zone_id, type_cuisine, note_moyenne)
           SELECT * FROM unnest($1::int[], $2::text[], $3::int[], $4::text[], $5::float8[])""",
        ids,
        noms,
        zone_ids,
        cuisines,
        notes,
    )
    log.info("restaurants insérés", n=len(rows))
    return rows


async def insert_livreurs(conn, cfg: dict, zones: list[dict]) -> list[dict]:
    n = cfg["volume"]["nb_livreurs"]
    zone_weights = [z["poids"] for z in zones]
    note_dist = cfg["distributions"]["note_livreur"]
    notes_choix = list(note_dist.keys())
    notes_pds = list(note_dist.values())

    ids, prenoms, noms_fam, zone_ids, notes, tels = [], [], [], [], [], []
    rows = []

    for i in range(n):
        z = random.choices(zones, zone_weights)[0]
        genre = "femme" if random.random() < 0.05 else "homme"
        prenom, nom = algerian_names.random_nom_complet(genre)
        # Note discrète selon distribution config (5..1)
        note = float(random.choices(notes_choix, notes_pds)[0])
        # Jitter ±0.4 pour avoir une note continue plus réaliste
        note = float(np.clip(note + np.random.normal(0, 0.2), 1.0, 5.0))
        lid = i + 1
        ids.append(lid)
        prenoms.append(prenom)
        noms_fam.append(nom)
        zone_ids.append(z["id"])
        notes.append(note)
        tels.append(algerian_names.random_telephone())
        rows.append({"id": lid, "zone_id": z["id"]})

    await conn.execute(
        """INSERT INTO livreurs (id, prenom, nom, zone_principale_id, note_moyenne, telephone)
           SELECT * FROM unnest($1::int[], $2::text[], $3::text[], $4::int[], $5::float8[], $6::text[])""",
        ids,
        prenoms,
        noms_fam,
        zone_ids,
        notes,
        tels,
    )
    log.info("livreurs insérés", n=len(rows))
    return rows


async def insert_clients(conn, cfg: dict, zones: list[dict]) -> list[dict]:
    n = cfg["volume"]["nb_clients"]
    zone_weights = [z["poids"] for z in zones]
    ids, prenoms, noms_fam, zone_ids, tels, emails = [], [], [], [], [], []
    rows = []

    for i in range(n):
        z = random.choices(zones, zone_weights)[0]
        genre = "femme" if random.random() < 0.40 else "homme"
        prenom, nom = algerian_names.random_nom_complet(genre)
        cid = i + 1
        ids.append(cid)
        prenoms.append(prenom)
        noms_fam.append(nom)
        zone_ids.append(z["id"])
        tels.append(algerian_names.random_telephone())
        emails.append(algerian_names.random_email(prenom, nom))
        rows.append({"id": cid, "zone_id": z["id"]})

    await conn.execute(
        """INSERT INTO clients (id, prenom, nom, zone_id, telephone, email)
           SELECT * FROM unnest($1::int[], $2::text[], $3::text[], $4::int[], $5::text[], $6::text[])""",
        ids,
        prenoms,
        noms_fam,
        zone_ids,
        tels,
        emails,
    )
    log.info("clients insérés", n=len(rows))
    return rows


# ───────────────────────────────────────────────────────────────
# COMMANDES + ENFANTS (livraisons, paiements, incidents, avis)
# ───────────────────────────────────────────────────────────────


def _statut_final(events: list[dict]) -> str:
    types = {e["event_type"] for e in events}
    if "livraison_échouée" in types:
        return "echouee"
    if "commande_annulée" in types or "commande_refusée" in types:
        return "annulee"
    if "livraison_terminée" in types:
        return "livree"
    return "en_cours"


def _ts(s: str) -> datetime:
    """ISO string → datetime naïve (PostgreSQL TIMESTAMP without TZ)."""
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _build_row_buckets():
    """Retourne 5 dicts colonne→[] pour bulk insert."""
    return {
        "commandes": {
            k: []
            for k in (
                "id",
                "restaurant_id",
                "livreur_id",
                "client_id",
                "zone_id",
                "montant",
                "frais_livraison",
                "montant_total",
                "statut",
                "methode_paiement",
                "delai_estime_min",
                "delai_reel_min",
                "note_livreur",
                "commentaire",
                "created_at",
                "livre_at",
            )
        },
        "livraisons": {
            k: []
            for k in (
                "id",
                "commande_id",
                "livreur_id",
                "lat_depart",
                "lng_depart",
                "lat_arrivee",
                "lng_arrivee",
                "distance_km",
                "duree_trajet_estime_min",
                "duree_trajet_reel_min",
                "statut",
                "created_at",
                "terminee_at",
            )
        },
        "paiements": {
            k: []
            for k in (
                "id",
                "commande_id",
                "montant",
                "methode",
                "statut",
                "tentatives",
                "cause_echec",
                "created_at",
            )
        },
        "incidents": {
            k: []
            for k in (
                "id",
                "commande_id",
                "type",
                "severite",
                "description",
                "resolu",
                "source_service",
                "created_at",
                "resolu_at",
            )
        },
        "avis_clients": {
            k: []
            for k in (
                "id",
                "commande_id",
                "note",
                "commentaire",
                "sentiment",
                "created_at",
            )
        },
    }


# Sévérités/résolution par type d'incident
_SEV_BY_TYPE = {
    "retard_détecté": ("moyenne", 45),
    "livraison_échouée": ("haute", 30),
    "restaurant_fermé": ("moyenne", 60),
    "livreur_bloqué": ("haute", 25),
    "paiement_abandonné": ("haute", 15),
}


def _process_events(
    commande_id: int,
    client_id: int,
    restaurant_id: int,
    livreur_id: int,
    zone_id: int,
    events: list[dict],
    buckets: dict,
    id_counters: dict,
) -> None:
    """Ventile les events Kafka d'une commande vers les 5 buckets."""
    evt_create = events[0]
    statut = _statut_final(events)
    created_at = _ts(evt_create["timestamp"])

    # Chercher événements clés
    evt_mission = next(
        (e for e in events if e["event_type"] == "mission_acceptée"), None
    )
    evt_livraison = next(
        (e for e in events if e["event_type"] == "livraison_terminée"), None
    )
    evt_paiements = [e for e in events if e["topic"] == "paiements"]
    evt_avis = next((e for e in events if e["event_type"] == "avis_client"), None)
    evt_incidents = [e for e in events if e["topic"] == "incidents"]

    delai_estime = (
        (
            evt_mission.get("delai_estime_total_min")
            or evt_mission.get("duree_trajet_estime_min")
        )
        if evt_mission
        else None
    )
    delai_reel = evt_livraison.get("delai_reel_min") if evt_livraison else None
    livre_at = _ts(evt_livraison["timestamp"]) if evt_livraison else None

    note_livreur = float(evt_avis["note"]) if evt_avis else None
    commentaire = evt_avis["commentaire"] if evt_avis else None

    # ── commande ──
    c = buckets["commandes"]
    c["id"].append(commande_id)
    c["restaurant_id"].append(restaurant_id)
    c["livreur_id"].append(livreur_id)
    c["client_id"].append(client_id)
    c["zone_id"].append(zone_id)
    c["montant"].append(float(evt_create["montant"]))
    c["frais_livraison"].append(float(evt_create["frais_livraison"]))
    c["montant_total"].append(float(evt_create["montant_total"]))
    c["statut"].append(statut)
    c["methode_paiement"].append(evt_create["methode_paiement"])
    c["delai_estime_min"].append(delai_estime)
    c["delai_reel_min"].append(delai_reel)
    c["note_livreur"].append(note_livreur)
    c["commentaire"].append(commentaire)
    c["created_at"].append(created_at)
    c["livre_at"].append(livre_at)

    # ── livraison (si une mission a été acceptée) ──
    if evt_mission:
        liv_id = id_counters["livraisons"]
        id_counters["livraisons"] += 1
        liv = buckets["livraisons"]
        liv["id"].append(liv_id)
        liv["commande_id"].append(commande_id)
        liv["livreur_id"].append(livreur_id)
        liv["lat_depart"].append(float(evt_mission["lat_depart"]))
        liv["lng_depart"].append(float(evt_mission["lng_depart"]))
        liv["lat_arrivee"].append(float(evt_mission["lat_arrivee"]))
        liv["lng_arrivee"].append(float(evt_mission["lng_arrivee"]))
        liv["distance_km"].append(float(evt_mission["distance_km"]))
        liv["duree_trajet_estime_min"].append(
            int(evt_mission["duree_trajet_estime_min"])
        )
        liv["duree_trajet_reel_min"].append(int(delai_reel) if delai_reel else None)
        liv["statut"].append("terminée" if evt_livraison else statut)
        liv["created_at"].append(_ts(evt_mission["timestamp"]))
        liv["terminee_at"].append(livre_at)

    # ── paiements ──
    for ep in evt_paiements:
        pay_id = id_counters["paiements"]
        id_counters["paiements"] += 1
        p = buckets["paiements"]
        p["id"].append(pay_id)
        p["commande_id"].append(commande_id)
        p["montant"].append(float(ep["montant"]))
        p["methode"].append(ep["methode"])
        p["statut"].append(ep.get("statut", "confirmé"))
        p["tentatives"].append(int(ep.get("tentative", 1)))
        p["cause_echec"].append(ep.get("cause"))
        p["created_at"].append(_ts(ep["timestamp"]))

    # ── incidents ──
    for ei in evt_incidents:
        inc_id = id_counters["incidents"]
        id_counters["incidents"] += 1
        i = buckets["incidents"]
        et = ei["event_type"]
        sev, resolu_min = _SEV_BY_TYPE.get(et, ("basse", 120))
        # Type stocké côté table = catégorie courte
        type_court = {
            "retard_détecté": "retard",
            "livraison_échouée": "livraison_echouee",
            "restaurant_fermé": "restaurant_ferme",
            "livreur_bloqué": "livreur_bloque",
            "paiement_abandonné": "paiement_echoue",
        }.get(et, et)
        inc_ts = _ts(ei["timestamp"])
        resolu = random.random() < 0.75
        i["id"].append(inc_id)
        i["commande_id"].append(commande_id)
        i["type"].append(type_court)
        i["severite"].append(sev)
        i["description"].append(
            f"[{sev.upper()}] {et} (zone={ei.get('zone','?')}, raison={ei.get('raison','-')})"
        )
        i["resolu"].append(resolu)
        i["source_service"].append(ei["source_service"])
        i["created_at"].append(inc_ts)
        i["resolu_at"].append(
            inc_ts + timedelta(minutes=random.randint(resolu_min // 2, resolu_min))
            if resolu
            else None
        )

    # ── avis client ──
    if evt_avis:
        av_id = id_counters["avis_clients"]
        id_counters["avis_clients"] += 1
        a = buckets["avis_clients"]
        a["id"].append(av_id)
        a["commande_id"].append(commande_id)
        a["note"].append(int(evt_avis["note"]))
        a["commentaire"].append(evt_avis["commentaire"])
        a["sentiment"].append(evt_avis["sentiment"])
        a["created_at"].append(_ts(evt_avis["timestamp"]))


async def _flush_buckets(conn, buckets: dict) -> None:
    """Insère les 5 tables en parallèle via unnest()."""
    c = buckets["commandes"]
    if c["id"]:
        await conn.execute(
            """INSERT INTO commandes (
                  id, restaurant_id, livreur_id, client_id, zone_id,
                  montant, frais_livraison, montant_total, statut,
                  methode_paiement, delai_estime_min, delai_reel_min,
                  note_livreur, commentaire, created_at, livre_at
               )
               SELECT * FROM unnest(
                  $1::int[], $2::int[], $3::int[], $4::int[], $5::int[],
                  $6::float8[], $7::float8[], $8::float8[], $9::text[],
                  $10::text[], $11::int[], $12::int[],
                  $13::float8[], $14::text[], $15::timestamp[], $16::timestamp[]
               )""",
            c["id"],
            c["restaurant_id"],
            c["livreur_id"],
            c["client_id"],
            c["zone_id"],
            c["montant"],
            c["frais_livraison"],
            c["montant_total"],
            c["statut"],
            c["methode_paiement"],
            c["delai_estime_min"],
            c["delai_reel_min"],
            c["note_livreur"],
            c["commentaire"],
            c["created_at"],
            c["livre_at"],
        )

    liv = buckets["livraisons"]
    if liv["id"]:
        await conn.execute(
            """INSERT INTO livraisons (
                  id, commande_id, livreur_id,
                  lat_depart, lng_depart, lat_arrivee, lng_arrivee,
                  distance_km, duree_trajet_estime_min, duree_trajet_reel_min,
                  statut, created_at, terminee_at
               )
               SELECT * FROM unnest(
                  $1::int[], $2::int[], $3::int[],
                  $4::float8[], $5::float8[], $6::float8[], $7::float8[],
                  $8::float8[], $9::int[], $10::int[],
                  $11::text[], $12::timestamp[], $13::timestamp[]
               )""",
            liv["id"],
            liv["commande_id"],
            liv["livreur_id"],
            liv["lat_depart"],
            liv["lng_depart"],
            liv["lat_arrivee"],
            liv["lng_arrivee"],
            liv["distance_km"],
            liv["duree_trajet_estime_min"],
            liv["duree_trajet_reel_min"],
            liv["statut"],
            liv["created_at"],
            liv["terminee_at"],
        )

    p = buckets["paiements"]
    if p["id"]:
        await conn.execute(
            """INSERT INTO paiements (
                  id, commande_id, montant, methode, statut,
                  tentatives, cause_echec, created_at
               )
               SELECT * FROM unnest(
                  $1::int[], $2::int[], $3::float8[], $4::text[], $5::text[],
                  $6::int[], $7::text[], $8::timestamp[]
               )""",
            p["id"],
            p["commande_id"],
            p["montant"],
            p["methode"],
            p["statut"],
            p["tentatives"],
            p["cause_echec"],
            p["created_at"],
        )

    i = buckets["incidents"]
    if i["id"]:
        await conn.execute(
            """INSERT INTO incidents (
                  id, commande_id, type, severite, description,
                  resolu, source_service, created_at, resolu_at
               )
               SELECT * FROM unnest(
                  $1::int[], $2::int[], $3::text[], $4::text[], $5::text[],
                  $6::bool[], $7::text[], $8::timestamp[], $9::timestamp[]
               )""",
            i["id"],
            i["commande_id"],
            i["type"],
            i["severite"],
            i["description"],
            i["resolu"],
            i["source_service"],
            i["created_at"],
            i["resolu_at"],
        )

    a = buckets["avis_clients"]
    if a["id"]:
        await conn.execute(
            """INSERT INTO avis_clients (
                  id, commande_id, note, commentaire, sentiment, created_at
               )
               SELECT * FROM unnest(
                  $1::int[], $2::int[], $3::int[], $4::text[], $5::text[], $6::timestamp[]
               )""",
            a["id"],
            a["commande_id"],
            a["note"],
            a["commentaire"],
            a["sentiment"],
            a["created_at"],
        )


def _pareto_pick_index(n: int) -> int:
    """Pareto-like : restaurants à index bas reçoivent plus de commandes."""
    # tirage rapide en O(1) avec une loi puissance
    u = random.random()
    # exposant 0.3 → concentre ~65% sur les 42% premiers
    return int(n * (u**0.3))


async def insert_commandes_et_enfants(
    conn,
    cfg: dict,
    zones: list[dict],
    restaurants: list[dict],
    livreurs: list[dict],
    clients: list[dict],
    jours_override: int | None,
) -> dict:
    """Génère 324k commandes + leurs events ventilés vers 5 tables."""
    orch = Orchestrator(cfg)
    n_restos = len(restaurants)
    n_livreurs = len(livreurs)
    n_clients = len(clients)
    zone_weights = [z["poids"] for z in zones]

    id_counters = {"livraisons": 1, "paiements": 1, "incidents": 1, "avis_clients": 1}
    buckets = _build_row_buckets()

    commande_id = 1
    processed = 0
    t0 = datetime.now()

    for ts in generate_timestamps(cfg, jours_override=jours_override):
        zone = random.choices(zones, zone_weights)[0]
        resto = restaurants[_pareto_pick_index(n_restos)]
        livreur = livreurs[random.randrange(n_livreurs)]
        client = clients[random.randrange(n_clients)]

        events = orch.simuler_commande_complete(
            commande_id=commande_id,
            client_id=client["id"],
            restaurant_id=resto["id"],
            livreur_id=livreur["id"],
            zone=zone,
            base_timestamp=ts,
        )

        _process_events(
            commande_id,
            client["id"],
            resto["id"],
            livreur["id"],
            zone["id"],
            events,
            buckets,
            id_counters,
        )
        commande_id += 1
        processed += 1

        if processed % BATCH_SIZE == 0:
            await _flush_buckets(conn, buckets)
            buckets = _build_row_buckets()
            elapsed = (datetime.now() - t0).total_seconds()
            rate = processed / max(elapsed, 0.001)
            log.info(
                "batch flushé",
                processed=processed,
                rate_per_sec=round(rate, 1),
                elapsed_s=round(elapsed, 1),
            )

    # Flush final
    if buckets["commandes"]["id"]:
        await _flush_buckets(conn, buckets)

    # ANALYZE après bulk pour stats planner
    for tbl in ("commandes", "livraisons", "paiements", "incidents", "avis_clients"):
        await conn.execute(f"ANALYZE {tbl}")

    return {
        "commandes": processed,
        "livraisons": id_counters["livraisons"] - 1,
        "paiements": id_counters["paiements"] - 1,
        "incidents": id_counters["incidents"] - 1,
        "avis_clients": id_counters["avis_clients"] - 1,
    }


# ───────────────────────────────────────────────────────────────
# MAIN
# ───────────────────────────────────────────────────────────────


async def main() -> None:
    cfg = load_config()
    seed = cfg["simulation"]["seed"]
    random.seed(seed)
    np.random.seed(seed)

    jours_override = int(os.getenv("SIM_JOURS", "0")) or None
    if jours_override:
        log.warning("MODE SMOKE TEST", jours=jours_override)

    log.info("connexion Postgres", host=os.getenv("POSTGRES_HOST"))
    conn = await connect()
    try:
        log.info("création schéma")
        await conn.execute(SCHEMA_FILE.read_text())

        zones = await insert_zones(conn, cfg)
        restos = await insert_restaurants(conn, cfg, zones)
        livreurs = await insert_livreurs(conn, cfg, zones)
        clients = await insert_clients(conn, cfg, zones)

        log.info(
            "démarrage génération commandes", cible=cfg["volume"]["nb_commandes_total"]
        )
        counts = await insert_commandes_et_enfants(
            conn,
            cfg,
            zones,
            restos,
            livreurs,
            clients,
            jours_override,
        )

        log.info(
            "génération terminée",
            zones=len(zones),
            restaurants=len(restos),
            livreurs=len(livreurs),
            clients=len(clients),
            **counts,
        )
    finally:
        await conn.close()


# ─── Public helpers (kept for unit-test compatibility post-v3 refactor) ──────


def weighted_pick(items: list, weights: list[float]) -> int:
    """Retourne l'index d'un item tiré selon les poids fournis."""
    return int(np.random.choice(len(items), p=np.asarray(weights) / sum(weights)))


def temporal_factor(ts: datetime, cfg: dict) -> float:
    """Facteur multiplicatif horaire : pics 12h30 et 20h, weekend boost."""
    h = ts.hour + ts.minute / 60.0
    pic_dej = cfg["temporal"]["pic_dejeuner_heure"]
    pic_din = cfg["temporal"]["pic_diner_heure"]
    duree = cfg["temporal"]["pic_duree_heures"]
    sigma = duree / 2.0
    base = 0.15
    f_dej = math.exp(-((h - pic_dej) ** 2) / (2 * sigma**2))
    f_din = math.exp(-((h - pic_din) ** 2) / (2 * sigma**2))
    factor = base + f_dej + f_din
    if ts.weekday() >= 5:
        factor *= cfg["temporal"]["facteur_weekend"]
    return factor


def sample_commande_timestamp(cfg: dict, jours_historique: int) -> datetime:
    """Tire un timestamp dans les N derniers jours, biaisé par temporal_factor."""
    while True:
        days_ago = random.uniform(0, jours_historique)
        ts = datetime.now() - timedelta(days=days_ago)
        ts = ts.replace(microsecond=0)
        accept_proba = temporal_factor(ts, cfg) / 2.5
        if random.random() < accept_proba:
            return ts


def pick_statut(cfg: dict) -> str:
    p = cfg["statuts"]
    r = random.random()
    if r < p["prob_livree"]:
        return "livree"
    if r < p["prob_livree"] + p["prob_annulee"]:
        return "annulee"
    return "echouee"


def pick_methode_paiement(cfg: dict) -> str:
    methods = list(cfg["paiements"]["methodes"].keys())
    weights = list(cfg["paiements"]["methodes"].values())
    return methods[weighted_pick(methods, weights)]


def pick_severite(cfg: dict) -> str:
    sev = list(cfg["incidents"]["severites"].keys())
    w = list(cfg["incidents"]["severites"].values())
    return sev[weighted_pick(sev, w)]


def pick_type_incident(cfg: dict) -> str:
    types = list(cfg["incidents"]["types"].keys())
    w = list(cfg["incidents"]["types"].values())
    return types[weighted_pick(types, w)]


def description_incident(t: str, severite: str) -> str:
    d = {
        "retard": "Retard de livraison signalé par le client",
        "restaurant_ferme": "Restaurant fermé sans préavis à l'arrivée du livreur",
        "livreur_bloque": "Livreur bloqué (trafic, panne moto, conditions météo)",
        "paiement_echoue": "Échec de paiement par carte",
        "adresse_incorrecte": "Adresse de livraison incorrecte ou introuvable",
        "probleme_qualite": "Plainte client sur la qualité du repas",
    }
    return f"[{severite.upper()}] {d.get(t, t)}"


if __name__ == "__main__":
    asyncio.run(main())
