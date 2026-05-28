"""
Injecteur d'anomalies planifiées (config.anomalies.planifiees).

Le static_generator produit des incidents normaux (retards, échecs, etc.) selon
les distributions stochastiques. Cet injecteur ajoute en plus les 6 anomalies
planifiées par le scénario Hello Delivery :

    jour  15  → panne_restaurant (40 min)
    jour  45  → pic_charge_ete   (×1.5, 30 min)
    jour  60  → erreurs_paiement (taux=0.30, 15 min)
    jour  90  → convoi_hydra     (25 min)
    jour 120  → panne_dns        (20 min)
    jour 150  → pic_charge_ete   (×2.0, 20 min)

Chaque anomalie génère 5-15 incidents corrélés dans la fenêtre temporelle,
rattachés à des commandes réelles de la même période. Les descriptions sont
détaillées pour donner du grain au retrieval RAG.

Usage :
    python -m simulator.anomaly_injector
"""

from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timedelta, timezone

import structlog

from simulator.config import load_config
from simulator.db import connect

log = structlog.get_logger()


# Mapping anomalie planifiée → (type_incident, severite, zone_cible, n_incidents, description)
ANOMALIE_SPECS = {
    "panne_restaurant": {
        "type": "restaurant_ferme",
        "severite": "haute",
        "n_min": 8,
        "n_max": 12,
        "desc_template": (
            "[HAUTE] Panne restaurant majeure — système de commande indisponible "
            "pendant {duree_min} min. Restaurant : '{restaurant}' en zone {zone}. "
            "Cause probable : panne du système POS du restaurant. "
            "{n} commandes affectées sur la fenêtre. Mots-clés : indisponibilité, "
            "panne POS, restaurant fermé, système commande, blocage."
        ),
    },
    "pic_charge_ete": {
        "type": "pic_charge",
        "severite": "moyenne",
        "n_min": 12,
        "n_max": 18,
        "desc_template": (
            "[MOYENNE] Pic de charge été — volume de commandes ×{facteur} pendant "
            "{duree_min} min. Saturation des livreurs disponibles, hausse des délais. "
            "Zone principale : {zone}. {n} retards générés par cette surcharge. "
            "Mots-clés : pic, surcharge, saturation, été, canicule, été 2026, "
            "weekend, soirée, demande exceptionnelle."
        ),
    },
    "erreurs_paiement": {
        "type": "paiement_echoue",
        "severite": "haute",
        "n_min": 10,
        "n_max": 15,
        "desc_template": (
            "[HAUTE] Vague d'erreurs paiement carte — taux d'échec monté à {taux:.0%} "
            "pendant {duree_min} min. Cause probable : incident côté processeur "
            "(timeouts gateway bancaire). {n} commandes en échec paiement. "
            "Mots-clés : panne paiement, gateway, timeout, refus carte, processeur, "
            "interruption, défaillance bancaire."
        ),
    },
    "convoi_hydra": {
        "type": "livreur_bloque",
        "severite": "haute",
        "n_min": 6,
        "n_max": 10,
        "desc_template": (
            "[HAUTE] Convoi officiel à Hydra — circulation bloquée pendant {duree_min} min. "
            "Plusieurs livreurs immobilisés, retards en cascade sur les commandes en cours. "
            "Zone affectée : Hydra et axes adjacents. {n} livreurs touchés. "
            "Mots-clés : embouteillage, convoi, Hydra, circulation bloquée, "
            "manifestation, axe principal, retards en cascade."
        ),
    },
    "panne_dns": {
        "type": "dns_failure",
        "severite": "critique",
        "n_min": 15,
        "n_max": 25,
        "desc_template": (
            "[CRITIQUE] Panne DNS infrastructure — résolution noms échoue pendant "
            "{duree_min} min. Impact transverse : API, base de données, services "
            "externes inaccessibles. {n} commandes en échec ou perdues. "
            "Mots-clés : panne DNS, infrastructure, indisponibilité, "
            "résolution échec, incident plateforme, outage, dégradation totale."
        ),
    },
}


def _select_anomalie_spec(planif: dict) -> dict | None:
    """Sélectionne le spec correspondant à une anomalie planifiée."""
    return ANOMALIE_SPECS.get(planif["type"])


async def _next_incident_id(conn) -> int:
    val = await conn.fetchval("SELECT COALESCE(MAX(id), 0) FROM incidents")
    return (val or 0) + 1


async def _pick_zone(conn, anomalie_type: str) -> dict:
    if anomalie_type == "convoi_hydra":
        row = await conn.fetchrow(
            "SELECT id, nom FROM zones WHERE nom = 'Hydra' LIMIT 1"
        )
        if row:
            return dict(row)
    # Pour les autres anomalies, prendre une zone à fort volume
    row = await conn.fetchrow(
        "SELECT z.id, z.nom FROM zones z ORDER BY z.poids DESC LIMIT 1"
    )
    return dict(row)


async def _pick_commandes_window(
    conn, anomalie_ts: datetime, duree_min: int, n: int, zone_id: int | None = None
) -> list[dict]:
    """Sélectionne n commandes dans la fenêtre temporelle, idéalement de la même zone."""
    end_ts = anomalie_ts + timedelta(minutes=duree_min)
    if zone_id:
        rows = await conn.fetch(
            """SELECT id, restaurant_id, livreur_id, zone_id, created_at
               FROM commandes
               WHERE created_at BETWEEN $1 AND $2 AND zone_id = $3
               ORDER BY random() LIMIT $4""",
            anomalie_ts,
            end_ts,
            zone_id,
            n,
        )
        if len(rows) >= max(1, n // 2):
            return [dict(r) for r in rows]
    # Fallback : ignorer zone, élargir fenêtre ±30 min
    rows = await conn.fetch(
        """SELECT id, restaurant_id, livreur_id, zone_id, created_at
           FROM commandes
           WHERE created_at BETWEEN $1 AND $2
           ORDER BY random() LIMIT $3""",
        anomalie_ts - timedelta(minutes=30),
        end_ts + timedelta(minutes=30),
        n,
    )
    return [dict(r) for r in rows]


async def _restaurant_nom(conn, restaurant_id: int) -> str:
    row = await conn.fetchval(
        "SELECT nom FROM restaurants WHERE id = $1", restaurant_id
    )
    return row or "?"


async def inject_anomalies(conn, cfg: dict) -> int:
    """Insère les anomalies planifiées dans la table incidents. Retourne le nombre injecté."""
    planifiees = cfg.get("anomalies", {}).get("planifiees", [])
    if not planifiees:
        log.warning("aucune anomalie planifiée dans la config")
        return 0

    nb_jours = cfg["volume"]["jours_historique"]
    start_date = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    ) - timedelta(days=nb_jours)

    next_id = await _next_incident_id(conn)
    total_inserted = 0

    # Bucket pour bulk insert
    ids, commande_ids, types, severites, descriptions = [], [], [], [], []
    resolus, source_services, created_ats, resolu_ats = [], [], [], []

    for planif in planifiees:
        spec = _select_anomalie_spec(planif)
        if not spec:
            log.warning("anomalie inconnue", type=planif["type"])
            continue

        # Date+heure de l'anomalie : jour J + une heure de pointe au hasard (déjeuner/dîner)
        jour_offset = planif["jour"]
        anomalie_date = start_date + timedelta(days=jour_offset)
        pic_hour = random.choice([12, 13, 19, 20])
        anomalie_ts = anomalie_date.replace(hour=pic_hour, minute=random.randint(0, 30))

        zone = await _pick_zone(conn, planif["type"])
        n_target = random.randint(spec["n_min"], spec["n_max"])
        commandes = await _pick_commandes_window(
            conn, anomalie_ts, planif["duree_min"], n_target, zone["id"]
        )
        if not commandes:
            log.warning(
                "pas de commandes pour anomalie",
                jour=jour_offset,
                type=planif["type"],
                ts=anomalie_ts.isoformat(),
            )
            continue

        # Choisir un restaurant représentatif pour la description (1er commande)
        resto_nom = await _restaurant_nom(conn, commandes[0]["restaurant_id"])
        desc = spec["desc_template"].format(
            duree_min=planif["duree_min"],
            facteur=planif.get("facteur", 1.0),
            taux=planif.get("taux", 0.0),
            restaurant=resto_nom,
            zone=zone["nom"],
            n=len(commandes),
        )

        for i, c in enumerate(commandes):
            ts_incident = anomalie_ts + timedelta(
                minutes=random.uniform(0, planif["duree_min"])
            )
            resolu = random.random() < 0.85
            resolu_at = (
                ts_incident
                + timedelta(
                    minutes=random.randint(planif["duree_min"], planif["duree_min"] * 3)
                )
                if resolu
                else None
            )
            ids.append(next_id)
            next_id += 1
            commande_ids.append(c["id"])
            types.append(spec["type"])
            severites.append(spec["severite"])
            # 1ère ligne porte la description complète, les suivantes une variante courte
            if i == 0:
                descriptions.append(desc)
            else:
                descriptions.append(
                    f"[{spec['severite'].upper()}] {planif['type']} — incident corrélé "
                    f"à l'anomalie planifiée du jour {jour_offset} en zone {zone['nom']}. "
                    f"Commande #{c['id']} affectée."
                )
            resolus.append(resolu)
            source_services.append("anomaly-injector")
            created_ats.append(ts_incident)
            resolu_ats.append(resolu_at)

        log.info(
            "anomalie injectée",
            jour=jour_offset,
            type=planif["type"],
            zone=zone["nom"],
            n=len(commandes),
            ts=anomalie_ts.isoformat(),
        )

    if not ids:
        return 0

    await conn.execute(
        """INSERT INTO incidents (id, commande_id, type, severite, description,
                                   resolu, source_service, created_at, resolu_at)
           SELECT * FROM unnest(
               $1::int[], $2::int[], $3::text[], $4::text[], $5::text[],
               $6::bool[], $7::text[], $8::timestamp[], $9::timestamp[]
           )""",
        ids,
        commande_ids,
        types,
        severites,
        descriptions,
        resolus,
        source_services,
        created_ats,
        resolu_ats,
    )
    total_inserted = len(ids)
    await conn.execute("ANALYZE incidents")
    return total_inserted


async def main() -> None:
    cfg = load_config()
    seed = cfg["simulation"]["seed"]
    random.seed(seed + 9999)  # seed offset pour ne pas dupliquer du static_generator

    log.info("connexion Postgres", host=os.getenv("POSTGRES_HOST"))
    conn = await connect()
    try:
        n = await inject_anomalies(conn, cfg)
        log.info("injection terminée", incidents_ajoutes=n)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
