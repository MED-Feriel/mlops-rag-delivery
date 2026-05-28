"""
Module Livreur — simule le comportement de la flotte de livreurs.

Responsabilités :
- Accepter/refuser une mission (topic : livraisons)
- Mettre à jour la position GPS (topic : livraisons)
- Signaler une livraison terminée (topic : livraisons)
- Signaler un blocage (topic : incidents)
"""

import math
import random
from datetime import datetime

import structlog

log = structlog.get_logger()


class LivreurService:
    """Simule le comportement d'un livreur."""

    SERVICE_NAME = "livreur-service"

    def __init__(self, config: dict):
        self.config = config
        self.livreurs_bloques: set = set()

    def accepter_mission(
        self,
        commande_id: int,
        livreur_id: int,
        lat_depart: float,
        lng_depart: float,
        lat_arrivee: float,
        lng_arrivee: float,
        timestamp: datetime,
    ) -> dict:
        distance = self._haversine(lat_depart, lng_depart, lat_arrivee, lng_arrivee)
        trajet_cfg = self.config["distributions"]["phases"]["trajet"]
        duree_trajet = max(5, int(random.gauss(trajet_cfg["mu"], trajet_cfg["sigma"])))
        return {
            "event_type": "mission_acceptée",
            "source_service": self.SERVICE_NAME,
            "topic": "livraisons",
            "commande_id": commande_id,
            "livreur_id": livreur_id,
            "distance_km": round(distance, 2),
            "duree_trajet_estime_min": duree_trajet,
            "lat_depart": lat_depart,
            "lng_depart": lng_depart,
            "lat_arrivee": lat_arrivee,
            "lng_arrivee": lng_arrivee,
            "timestamp": timestamp.isoformat(),
        }

    def position_gps(
        self,
        livreur_id: int,
        lat: float,
        lng: float,
        vitesse_kmh: float,
        timestamp: datetime,
    ) -> dict:
        return {
            "event_type": "position_gps",
            "source_service": self.SERVICE_NAME,
            "topic": "livraisons",
            "livreur_id": livreur_id,
            "latitude": lat,
            "longitude": lng,
            "vitesse_kmh": vitesse_kmh,
            "timestamp": timestamp.isoformat(),
        }

    def livraison_terminee(
        self,
        commande_id: int,
        livreur_id: int,
        delai_reel_min: int,
        timestamp: datetime,
    ) -> dict:
        return {
            "event_type": "livraison_terminée",
            "source_service": self.SERVICE_NAME,
            "topic": "livraisons",
            "commande_id": commande_id,
            "livreur_id": livreur_id,
            "delai_reel_min": delai_reel_min,
            "timestamp": timestamp.isoformat(),
        }

    def signaler_blocage(
        self,
        livreur_id: int,
        commande_id: int,
        lat: float,
        lng: float,
        timestamp: datetime,
    ) -> dict:
        self.livreurs_bloques.add(livreur_id)
        return {
            "event_type": "livreur_bloqué",
            "source_service": self.SERVICE_NAME,
            "topic": "incidents",
            "livreur_id": livreur_id,
            "commande_id": commande_id,
            "latitude": lat,
            "longitude": lng,
            "timestamp": timestamp.isoformat(),
        }

    def refuser_mission(
        self, livreur_id: int, commande_id: int, timestamp: datetime
    ) -> dict:
        return {
            "event_type": "mission_refusée",
            "source_service": self.SERVICE_NAME,
            "topic": "livraisons",
            "livreur_id": livreur_id,
            "commande_id": commande_id,
            "timestamp": timestamp.isoformat(),
        }

    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
