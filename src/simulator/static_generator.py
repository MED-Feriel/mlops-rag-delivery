"""
Génération des données statiques.

Recrée le schéma puis remplit zones, restaurants, livreurs, clients, et un
historique de N commandes (par défaut 5000) sur les 30 derniers jours, avec
une distribution temporelle réaliste (pics dejeuner/diner, week-end), des
distributions log-normales pour montant et délais, et ~8% des commandes
porteuses d'un incident.

Usage : `python -m simulator.static_generator`
"""

from __future__ import annotations

import asyncio
import random
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import structlog
from faker import Faker

from simulator.config import load_config
from simulator.db import connect

log = structlog.get_logger()
fake = Faker("fr_FR")

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
SCHEMA_FILE = Path(__file__).parent / "schema.sql"


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


async def insert_zones(conn, cfg: dict) -> list[dict]:
    rows = []
    for z in cfg["static"]["zones"]:
        zid = await conn.fetchval(
            "INSERT INTO zones (nom, poids) VALUES ($1, $2) RETURNING id",
            z["nom"],
            z["poids"],
        )
        rows.append({"id": zid, "nom": z["nom"], "poids": z["poids"]})
    log.info("zones insérées", n=len(rows))
    return rows


async def insert_restaurants(conn, cfg: dict, zones: list[dict]) -> list[dict]:
    weights = [z["poids"] for z in zones]
    rows = []
    for _ in range(cfg["static"]["nb_restaurants"]):
        z = zones[weighted_pick(zones, weights)]
        nom = f"{fake.company()} - {random.choice(TYPES_CUISINE).title()}"
        cuisine = random.choice(TYPES_CUISINE)
        note = float(np.clip(np.random.normal(4.0, 0.5), 1.0, 5.0))
        rid = await conn.fetchval(
            """INSERT INTO restaurants (nom, zone_id, type_cuisine, note_moyenne)
               VALUES ($1, $2, $3, $4) RETURNING id""",
            nom,
            z["id"],
            cuisine,
            note,
        )
        rows.append({"id": rid, "zone_id": z["id"]})
    log.info("restaurants insérés", n=len(rows))
    return rows


async def insert_livreurs(conn, cfg: dict, zones: list[dict]) -> list[dict]:
    weights = [z["poids"] for z in zones]
    mu = cfg["distributions"]["note_livreur_mu"]
    sigma = cfg["distributions"]["note_livreur_sigma"]
    rows = []
    for _ in range(cfg["static"]["nb_livreurs"]):
        z = zones[weighted_pick(zones, weights)]
        nom = fake.name()
        note = float(np.clip(np.random.normal(mu, sigma), 1.0, 5.0))
        lid = await conn.fetchval(
            """INSERT INTO livreurs (nom, zone_principale_id, note_moyenne)
               VALUES ($1, $2, $3) RETURNING id""",
            nom,
            z["id"],
            note,
        )
        rows.append({"id": lid, "zone_id": z["id"]})
    log.info("livreurs insérés", n=len(rows))
    return rows


async def insert_clients(conn, zones: list[dict], n: int = 200) -> list[dict]:
    weights = [z["poids"] for z in zones]
    rows = []
    for _ in range(n):
        z = zones[weighted_pick(zones, weights)]
        cid = await conn.fetchval(
            """INSERT INTO clients (nom, zone_id, telephone)
               VALUES ($1, $2, $3) RETURNING id""",
            fake.name(),
            z["id"],
            fake.phone_number(),
        )
        rows.append({"id": cid, "zone_id": z["id"]})
    log.info("clients insérés", n=len(rows))
    return rows


def commentaire_client(statut: str, retard_min: int) -> str:
    """Génère un commentaire client réaliste suivant le statut."""
    if statut == "annulee":
        return random.choice(
            [
                "Annulé : trop long",
                "Restaurant a annulé",
                "Erreur de saisie",
                "Plus faim, désolé",
            ]
        )
    if statut == "echouee":
        return random.choice(
            [
                "Adresse introuvable",
                "Paiement refusé",
                "Restaurant fermé",
            ]
        )
    # livrée
    if retard_min > 20:
        return random.choice(
            [
                "Très en retard, déçu.",
                "Plus jamais ! 1h d'attente.",
                "Repas froid, livraison trop longue.",
            ]
        )
    if retard_min > 5:
        return random.choice(
            [
                "Un peu long mais ok",
                "Retard mais bon repas",
            ]
        )
    return random.choice(
        [
            "Parfait, merci !",
            "Livraison rapide, repas chaud",
            "Excellent service",
            "Top, comme d'habitude",
            "Très satisfait",
        ]
    )


async def insert_commandes_et_incidents(
    conn,
    cfg: dict,
    zones: list[dict],
    restaurants: list[dict],
    livreurs: list[dict],
    clients: list[dict],
) -> tuple[int, int]:
    """Génère N commandes + leurs incidents (8%) sur la période historique."""
    n_commandes = cfg["static"]["nb_commandes_historique"]
    jours = cfg["static"]["jours_historique"]
    d = cfg["distributions"]

    restos_par_zone: dict[int, list[dict]] = {}
    for r in restaurants:
        restos_par_zone.setdefault(r["zone_id"], []).append(r)
    livreurs_par_zone: dict[int, list[dict]] = {}
    for liv in livreurs:
        livreurs_par_zone.setdefault(liv["zone_id"], []).append(liv)

    zone_weights = [z["poids"] for z in zones]
    n_inc = 0
    BATCH = 500
    cmd_batch: list = []
    cmd_meta: list = []
    inc_batch: list = []

    for i in range(n_commandes):
        ts = sample_commande_timestamp(cfg, jours)
        z = zones[weighted_pick(zones, zone_weights)]
        resto = random.choice(restos_par_zone.get(z["id"], restaurants))
        liv = random.choice(livreurs_par_zone.get(z["id"], livreurs))
        client = random.choice(clients)

        montant = float(
            np.clip(
                np.random.lognormal(d["montant_mu"], d["montant_sigma"]) * 100,
                d["montant_min"],
                d["montant_max"],
            )
        )
        statut = pick_statut(cfg)
        methode = pick_methode_paiement(cfg)
        delai_estime = int(
            np.clip(
                np.random.normal(d["delai_estime_mu"], d["delai_estime_sigma"]),
                10,
                90,
            )
        )
        delai_reel: int | None = None
        livre_at = None
        note = None
        if statut == "livree":
            facteur = float(
                np.clip(
                    np.random.normal(
                        d["delai_reel_facteur_mu"], d["delai_reel_facteur_sigma"]
                    ),
                    0.6,
                    3.0,
                )
            )
            delai_reel = max(10, int(delai_estime * facteur))
            livre_at = ts + timedelta(minutes=delai_reel)
            mu, sigma = d["note_livreur_mu"], d["note_livreur_sigma"]
            if delai_reel - delai_estime > 30:
                mu -= 0.7
            note = float(np.clip(np.random.normal(mu, sigma), 1.0, 5.0))

        retard_min = (delai_reel - delai_estime) if delai_reel else 0
        commentaire = commentaire_client(statut, retard_min)

        cmd_batch.append(
            (
                resto["id"],
                liv["id"],
                client["id"],
                z["id"],
                montant,
                statut,
                methode,
                delai_estime,
                delai_reel,
                note,
                commentaire,
                ts,
                livre_at,
            )
        )
        cmd_meta.append((statut, retard_min, ts))

        if len(cmd_batch) >= BATCH:
            n_inc += await _flush_commandes(conn, cmd_batch, cmd_meta, cfg, inc_batch)
            cmd_batch.clear()
            cmd_meta.clear()
            inc_batch.clear()

    if cmd_batch:
        n_inc += await _flush_commandes(conn, cmd_batch, cmd_meta, cfg, inc_batch)

    log.info("commandes insérées", commandes=n_commandes, incidents=n_inc)
    return n_commandes, n_inc


async def _flush_commandes(conn, cmd_batch, cmd_meta, cfg, inc_batch) -> int:
    """Insert commandes via copy_records_to_table puis incidents associés."""
    rows = await conn.fetch(
        """INSERT INTO commandes (
              restaurant_id, livreur_id, client_id, zone_id,
              montant, statut, methode_paiement,
              delai_estime_min, delai_reel_min,
              note_livreur, commentaire, created_at, livre_at
           )
           SELECT * FROM unnest(
              $1::int[], $2::int[], $3::int[], $4::int[],
              $5::float8[], $6::text[], $7::text[],
              $8::int[], $9::int[],
              $10::float8[], $11::text[], $12::timestamp[], $13::timestamp[]
           )
           RETURNING id""",
        [r[0] for r in cmd_batch],
        [r[1] for r in cmd_batch],
        [r[2] for r in cmd_batch],
        [r[3] for r in cmd_batch],
        [r[4] for r in cmd_batch],
        [r[5] for r in cmd_batch],
        [r[6] for r in cmd_batch],
        [r[7] for r in cmd_batch],
        [r[8] for r in cmd_batch],
        [r[9] for r in cmd_batch],
        [r[10] for r in cmd_batch],
        [r[11] for r in cmd_batch],
        [r[12] for r in cmd_batch],
    )
    cmd_ids = [r["id"] for r in rows]
    n_inc = 0
    taux_inc = cfg["incidents"]["taux_par_commande"]
    for cid, (statut, retard, ts) in zip(cmd_ids, cmd_meta):
        if (
            random.random() < taux_inc
            or statut in ("annulee", "echouee")
            or retard > 30
        ):
            t = pick_type_incident(cfg)
            sev = pick_severite(cfg)
            resolu = random.random() < 0.7
            resolu_at = (
                ts + timedelta(minutes=random.randint(10, 240)) if resolu else None
            )
            await conn.execute(
                """INSERT INTO incidents
                   (commande_id, type, severite, description, resolu, created_at, resolu_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                cid,
                t,
                sev,
                description_incident(t, sev),
                resolu,
                ts,
                resolu_at,
            )
            n_inc += 1
    return n_inc


async def main() -> None:
    cfg = load_config()
    seed = cfg["simulation"]["seed"]
    random.seed(seed)
    np.random.seed(seed)
    Faker.seed(seed)

    log.info("connexion Postgres", host=os.getenv("POSTGRES_HOST"))
    conn = await connect()
    try:
        log.info("création schéma")
        await conn.execute(SCHEMA_FILE.read_text())
        zones = await insert_zones(conn, cfg)
        restos = await insert_restaurants(conn, cfg, zones)
        livreurs = await insert_livreurs(conn, cfg, zones)
        clients = await insert_clients(conn, zones, n=200)
        n_cmd, n_inc = await insert_commandes_et_incidents(
            conn,
            cfg,
            zones,
            restos,
            livreurs,
            clients,
        )
        log.info(
            "génération terminée",
            zones=len(zones),
            restaurants=len(restos),
            livreurs=len(livreurs),
            clients=len(clients),
            commandes=n_cmd,
            incidents=n_inc,
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
