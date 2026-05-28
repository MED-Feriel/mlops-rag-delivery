"""
Orchestrateur central — coordonne les 4 modules service-like.

Cycle de vie d'une commande :
  Client (crée) → Restaurant (accepte, prépare) → Livreur (livre) → Paiement (encaisse)

Chaque transition produit 1+ événements Kafka sur des topics distincts.
Note : les commande_id sont attribués par l'application (schema sans SERIAL),
ce qui permet d'émettre tous les events liés AVANT l'INSERT en base.
"""

import random
from datetime import datetime, timedelta

import numpy as np
import structlog

from .services.client_service import ClientService
from .services.livreur_service import LivreurService
from .services.paiement_service import PaiementService
from .services.restaurant_service import RestaurantService

log = structlog.get_logger()


class Orchestrator:
    """Coordonne les 4 services pour simuler une commande complète."""

    def __init__(self, config: dict):
        self.config = config
        self.client = ClientService(config)
        self.restaurant = RestaurantService(config)
        self.livreur = LivreurService(config)
        self.paiement = PaiementService(config)
        self.zones = config["zones"]

    def simuler_commande_complete(
        self,
        commande_id: int,
        client_id: int,
        restaurant_id: int,
        livreur_id: int,
        zone: dict,
        base_timestamp: datetime,
    ) -> list[dict]:
        """
        Simule une commande de bout en bout.
        Retourne la liste de TOUS les événements Kafka générés.
        Chaque événement a 'topic' et 'source_service'.
        """
        events = []
        t = base_timestamp
        delai_extra = zone.get("delai_extra_min", 0)

        # ── 1. Client crée la commande ──
        evt_create = self.client.creer_commande(client_id, restaurant_id, zone, t)
        evt_create["commande_id"] = commande_id
        events.append(evt_create)

        destin = random.choices(
            ["livree", "annulee", "echouee"],
            [
                self.config["statuts"]["livree"],
                self.config["statuts"]["annulee"],
                self.config["statuts"]["echouee"],
            ],
        )[0]

        # ── 2. Annulation précoce (14%) ──
        if destin == "annulee":
            t += timedelta(minutes=random.randint(1, 10))
            initiateur = random.choices(
                list(self.config["statuts"]["annulation_initiateur"].keys()),
                list(self.config["statuts"]["annulation_initiateur"].values()),
            )[0]
            if initiateur == "client":
                events.append(
                    self.client.annuler_commande(commande_id, "changement d'avis", t)
                )
            elif initiateur == "restaurant":
                events.append(
                    self.restaurant.refuser_commande(
                        commande_id, restaurant_id, "surcharge", t
                    )
                )
            else:
                events.append(
                    self.client.annuler_commande(
                        commande_id, "annulation plateforme", t
                    )
                )
            return events

        # ── 3. Restaurant accepte et prépare ──
        t += timedelta(minutes=random.randint(1, 5))
        evt_accept = self.restaurant.accepter_commande(commande_id, restaurant_id, t)
        events.append(evt_accept)

        temps_prep = evt_accept["temps_preparation_estime_min"]
        t += timedelta(minutes=temps_prep)
        events.append(
            self.restaurant.preparation_terminee(commande_id, restaurant_id, t)
        )

        # ── 4. Livreur récupère et livre ──
        attente_cfg = self.config["distributions"]["phases"]["attente_livreur"]
        attente = max(1, int(random.gauss(attente_cfg["mu"], attente_cfg["sigma"])))
        t += timedelta(minutes=attente)

        zone_lat = zone.get("lat", 36.75)
        zone_lng = zone.get("lng", 3.05)
        client_lat = zone_lat + random.uniform(-0.02, 0.02)
        client_lng = zone_lng + random.uniform(-0.02, 0.02)

        evt_mission = self.livreur.accepter_mission(
            commande_id,
            livreur_id,
            zone_lat,
            zone_lng,
            client_lat,
            client_lng,
            t,
        )

        delai_cfg = self.config["distributions"]["delai"]
        delai_reel = max(
            10,
            int(
                np.random.normal(
                    delai_cfg["reel_mu"] + delai_extra, delai_cfg["reel_sigma"]
                )
            ),
        )
        delai_estime = max(
            10,
            int(np.random.normal(delai_cfg["estime_mu"], delai_cfg["estime_sigma"])),
        )
        # Le delai_estime du commande = estimation bout-en-bout annoncée au client
        # (préparation + attente + trajet), pas seulement le trajet.
        evt_mission["delai_estime_total_min"] = delai_estime
        events.append(evt_mission)

        retard = delai_reel - delai_estime
        if retard > delai_cfg["retard_seuil"]:
            t_retard = t + timedelta(minutes=delai_estime + 5)
            events.append(
                {
                    "event_type": "retard_détecté",
                    "source_service": "tracking-service",
                    "topic": "incidents",
                    "commande_id": commande_id,
                    "livreur_id": livreur_id,
                    "delai_estime_min": delai_estime,
                    "delai_reel_min": delai_reel,
                    "depassement_min": retard,
                    "zone": zone["nom"],
                    "timestamp": t_retard.isoformat(),
                }
            )

        # ── Livraison échouée (1.8%) ──
        if destin == "echouee":
            t += timedelta(minutes=delai_reel)
            events.append(
                {
                    "event_type": "livraison_échouée",
                    "source_service": "livreur-service",
                    "topic": "incidents",
                    "commande_id": commande_id,
                    "livreur_id": livreur_id,
                    "raison": random.choice(
                        [
                            "client absent",
                            "adresse incorrecte",
                            "accès impossible",
                            "client injoignable",
                        ]
                    ),
                    "timestamp": t.isoformat(),
                }
            )
            return events

        # ── 5. Livraison réussie ──
        t += timedelta(minutes=delai_reel)
        events.append(
            self.livreur.livraison_terminee(commande_id, livreur_id, delai_reel, t)
        )

        # ── 6. Paiement ──
        t += timedelta(seconds=random.randint(5, 30))
        evt_paiement = self.paiement.traiter_paiement(
            commande_id,
            evt_create["montant_total"],
            evt_create["methode_paiement"],
            t,
        )
        events.append(evt_paiement)

        if evt_paiement.get("statut") == "échoué":
            for tentative in range(2, self.config["paiements"]["tentatives_max"] + 1):
                t += timedelta(seconds=self.config["paiements"]["retry_delai_sec"])
                evt_retry = self.paiement.retry_paiement(
                    commande_id,
                    evt_create["montant_total"],
                    evt_create["methode_paiement"],
                    tentative,
                    t,
                )
                events.append(evt_retry)
                if evt_retry.get("statut") in ("confirmé", "abandonné"):
                    break

        # ── 7. Avis client (optionnel) ──
        t += timedelta(minutes=random.randint(5, 60))
        avis = self.client.laisser_avis(
            commande_id,
            delai_reel,
            delai_estime,
            random.uniform(3.5, 5.0),
            t,
        )
        if avis:
            events.append(avis)

        return events
