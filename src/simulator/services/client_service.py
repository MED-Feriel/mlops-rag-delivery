"""
Module Client — simule le comportement des clients de la plateforme.

Responsabilités :
- Créer des commandes (topic Kafka : commandes)
- Annuler des commandes (topic : commandes)
- Générer des commentaires/avis après livraison (topic : avis_clients)

Chaque action est publiée sur Kafka comme si c'était un microservice
indépendant, avec le header "source": "client-service".
"""

import random
from datetime import datetime
from typing import Optional

import numpy as np
import structlog

log = structlog.get_logger()


class ClientService:
    """Simule le comportement d'un client de la plateforme."""

    SERVICE_NAME = "client-service"

    def __init__(self, config: dict):
        self.config = config
        self.dist = config["distributions"]
        self.statuts = config["statuts"]

    def creer_commande(
        self,
        client_id: int,
        restaurant_id: int,
        zone: dict,
        timestamp: datetime,
    ) -> dict:
        """
        Crée un événement 'commande_créée'.
        Montant : loi log-normale (médiane 2100 DZD, μ_log=7.65).
        Frais : 250 DZD, gratuits si ≥ 5000 DZD.
        """
        montant_cfg = self.dist["montant"]
        montant = float(
            np.random.lognormal(montant_cfg["mu_log"], montant_cfg["sigma_log"])
        )
        montant = int(np.clip(montant, montant_cfg["min"], montant_cfg["max"]))

        frais_cfg = self.dist["frais_livraison"]
        frais = 0 if montant >= frais_cfg["gratuit_seuil"] else frais_cfg["base"]

        methode = random.choices(
            list(self.config["paiements"]["methodes"].keys()),
            list(self.config["paiements"]["methodes"].values()),
        )[0]

        return {
            "event_type": "commande_créée",
            "source_service": self.SERVICE_NAME,
            "topic": "commandes",
            "client_id": client_id,
            "restaurant_id": restaurant_id,
            "zone": zone["nom"],
            "zone_lat": zone.get("lat", 36.75),
            "zone_lng": zone.get("lng", 3.05),
            "montant": montant,
            "frais_livraison": frais,
            "montant_total": montant + frais,
            "methode_paiement": methode,
            "timestamp": timestamp.isoformat(),
        }

    def annuler_commande(
        self, commande_id: int, raison: str, timestamp: datetime
    ) -> dict:
        """Événement annulation initiée par le client."""
        return {
            "event_type": "commande_annulée",
            "source_service": self.SERVICE_NAME,
            "topic": "commandes",
            "commande_id": commande_id,
            "initiateur": "client",
            "raison": raison,
            "timestamp": timestamp.isoformat(),
        }

    def laisser_avis(
        self,
        commande_id: int,
        delai_reel: int,
        delai_estime: int,
        note_livreur: float,
        timestamp: datetime,
    ) -> Optional[dict]:
        """
        Avis client CORRÉLÉ à l'expérience :
        - Retard > 20 min   → 70% chance commentaire négatif (1-2 étoiles)
        - Retard ≤ 5 min + livreur ≥ 4.5 → 30% chance avis positif (5 étoiles)
        - Retard > 10 min  → 40% chance avis neutre (3 étoiles)
        """
        retard = delai_reel - delai_estime

        if retard > 20:
            if random.random() < 0.70:
                return self._avis(
                    commande_id,
                    timestamp,
                    note=random.choice([1, 2]),
                    texte=random.choice(
                        [
                            f"Livraison en retard de {retard} min, nourriture froide.",
                            f"Commande arrivée {retard} min en retard. Très déçu.",
                            f"Retard inacceptable ({retard} min). La nourriture n'est plus bonne.",
                            f"J'ai attendu {retard} minutes de plus. Service médiocre.",
                            f"Encore un retard de {retard} min... Je vais changer de plateforme.",
                        ]
                    ),
                    sentiment="négatif",
                )
        elif retard <= 5 and note_livreur >= 4.5:
            if random.random() < 0.30:
                return self._avis(
                    commande_id,
                    timestamp,
                    note=5,
                    texte=random.choice(
                        [
                            "Livraison rapide et livreur très poli. Merci !",
                            "Commande chaude, livrée en avance. Parfait.",
                            "Excellent service, rien à dire. 5 étoiles.",
                            "Toujours aussi rapide. Mon livreur préféré.",
                            "Commande impeccable, emballage soigné. Bravo.",
                        ]
                    ),
                    sentiment="positif",
                )
        elif retard > 10:
            if random.random() < 0.40:
                return self._avis(
                    commande_id,
                    timestamp,
                    note=3,
                    texte=random.choice(
                        [
                            f"Un peu de retard ({retard} min) mais la nourriture était correcte.",
                            f"Retard de {retard} min, pas catastrophique mais peut mieux faire.",
                            "Service moyen. Le délai annoncé n'est pas respecté.",
                        ]
                    ),
                    sentiment="neutre",
                )
        return None

    def _avis(self, cid, ts, note, texte, sentiment):
        return {
            "event_type": "avis_client",
            "source_service": self.SERVICE_NAME,
            "topic": "avis_clients",
            "commande_id": cid,
            "note": note,
            "commentaire": texte,
            "sentiment": sentiment,
            "timestamp": ts.isoformat(),
        }
