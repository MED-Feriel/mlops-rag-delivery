"""
Module Paiement — simule les transactions financières.

Responsabilités :
- Traiter un paiement (topic : paiements)
- Gérer les échecs et retries (topic : paiements + incidents)
- Confirmer un remboursement (topic : paiements)
"""

import random
from datetime import datetime

import structlog

log = structlog.get_logger()


class PaiementService:
    """Simule le traitement des paiements."""

    SERVICE_NAME = "payment-service"

    def __init__(self, config: dict):
        self.config = config
        self.paiements_cfg = config["paiements"]

    def traiter_paiement(
        self,
        commande_id: int,
        montant: int,
        methode: str,
        timestamp: datetime,
    ) -> dict:
        """
        4% d'échec sur carte (timeout 60%, refus 30%, autre 10%).
        Espèces = toujours succès.
        """
        if methode == "especes":
            return self._succes(commande_id, montant, methode, timestamp)

        if methode == "carte" and random.random() < self.paiements_cfg["echec_carte"]:
            cause = random.choices(
                list(self.paiements_cfg["causes_echec"].keys()),
                list(self.paiements_cfg["causes_echec"].values()),
            )[0]
            return self._echec(commande_id, montant, methode, cause, 1, timestamp)

        return self._succes(commande_id, montant, methode, timestamp)

    def retry_paiement(
        self,
        commande_id: int,
        montant: int,
        methode: str,
        tentative: int,
        timestamp: datetime,
    ) -> dict:
        """Retry — 70% succès, sinon nouvel échec. Au-delà de max → abandonné."""
        max_t = self.paiements_cfg["tentatives_max"]
        if tentative >= max_t:
            return self._echec_definitif(
                commande_id, montant, methode, tentative, timestamp
            )

        if random.random() < 0.70:
            return self._succes(commande_id, montant, methode, timestamp)

        cause = random.choices(
            list(self.paiements_cfg["causes_echec"].keys()),
            list(self.paiements_cfg["causes_echec"].values()),
        )[0]
        return self._echec(commande_id, montant, methode, cause, tentative, timestamp)

    def rembourser(
        self,
        commande_id: int,
        montant: int,
        raison: str,
        timestamp: datetime,
    ) -> dict:
        return {
            "event_type": "remboursement",
            "source_service": self.SERVICE_NAME,
            "topic": "paiements",
            "commande_id": commande_id,
            "montant_rembourse": montant,
            "raison": raison,
            "timestamp": timestamp.isoformat(),
        }

    def _succes(self, cid, montant, methode, ts):
        return {
            "event_type": "paiement_confirmé",
            "source_service": self.SERVICE_NAME,
            "topic": "paiements",
            "commande_id": cid,
            "montant": montant,
            "methode": methode,
            "statut": "confirmé",
            "tentative": 1,
            "timestamp": ts.isoformat(),
        }

    def _echec(self, cid, montant, methode, cause, tentative, ts):
        return {
            "event_type": "paiement_échoué",
            "source_service": self.SERVICE_NAME,
            "topic": "paiements",
            "commande_id": cid,
            "montant": montant,
            "methode": methode,
            "cause": cause,
            "tentative": tentative,
            "next_retry_sec": self.paiements_cfg["retry_delai_sec"],
            "statut": "échoué",
            "timestamp": ts.isoformat(),
        }

    def _echec_definitif(self, cid, montant, methode, tentative, ts):
        return {
            "event_type": "paiement_abandonné",
            "source_service": self.SERVICE_NAME,
            "topic": "incidents",
            "commande_id": cid,
            "montant": montant,
            "methode": methode,
            "tentatives_totales": tentative,
            "statut": "abandonné",
            "timestamp": ts.isoformat(),
        }
