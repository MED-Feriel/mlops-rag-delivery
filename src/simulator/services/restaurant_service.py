"""
Module Restaurant — simule le comportement des restaurants partenaires.

Responsabilités :
- Accepter/refuser les commandes (topic : restaurants)
- Signaler la préparation terminée (topic : restaurants)
- Fermetures temporaires (topic : restaurants + incidents)
"""

import random
from datetime import datetime

import structlog

log = structlog.get_logger()


class RestaurantService:
    """Simule le comportement d'un restaurant partenaire."""

    SERVICE_NAME = "restaurant-service"

    def __init__(self, config: dict):
        self.config = config
        self.restaurants_fermes: set = set()

    def accepter_commande(
        self, commande_id: int, restaurant_id: int, timestamp: datetime
    ) -> dict:
        """Restaurant accepte → début de préparation."""
        prep_cfg = self.config["distributions"]["phases"]["preparation"]
        temps_prep = max(5, int(random.gauss(prep_cfg["mu"], prep_cfg["sigma"])))
        return {
            "event_type": "commande_acceptée",
            "source_service": self.SERVICE_NAME,
            "topic": "restaurants",
            "commande_id": commande_id,
            "restaurant_id": restaurant_id,
            "temps_preparation_estime_min": temps_prep,
            "timestamp": timestamp.isoformat(),
        }

    def preparation_terminee(
        self, commande_id: int, restaurant_id: int, timestamp: datetime
    ) -> dict:
        return {
            "event_type": "préparation_terminée",
            "source_service": self.SERVICE_NAME,
            "topic": "restaurants",
            "commande_id": commande_id,
            "restaurant_id": restaurant_id,
            "timestamp": timestamp.isoformat(),
        }

    def refuser_commande(
        self, commande_id: int, restaurant_id: int, raison: str, timestamp: datetime
    ) -> dict:
        return {
            "event_type": "commande_refusée",
            "source_service": self.SERVICE_NAME,
            "topic": "restaurants",
            "commande_id": commande_id,
            "restaurant_id": restaurant_id,
            "raison": raison,
            "timestamp": timestamp.isoformat(),
        }

    def fermeture_temporaire(
        self, restaurant_id: int, duree_min: int, timestamp: datetime
    ) -> dict:
        self.restaurants_fermes.add(restaurant_id)
        return {
            "event_type": "restaurant_fermé",
            "source_service": self.SERVICE_NAME,
            "topic": "incidents",
            "restaurant_id": restaurant_id,
            "duree_estimee_min": duree_min,
            "timestamp": timestamp.isoformat(),
        }

    def reouverture(self, restaurant_id: int, timestamp: datetime) -> dict:
        self.restaurants_fermes.discard(restaurant_id)
        return {
            "event_type": "restaurant_réouvert",
            "source_service": self.SERVICE_NAME,
            "topic": "restaurants",
            "restaurant_id": restaurant_id,
            "timestamp": timestamp.isoformat(),
        }

    def est_ferme(self, restaurant_id: int) -> bool:
        return restaurant_id in self.restaurants_fermes
