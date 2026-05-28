"""Couverture des 4 services simulateur + Orchestrator (sync logic)."""

import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from src.simulator.orchestrator import Orchestrator
from src.simulator.services.client_service import ClientService
from src.simulator.services.livreur_service import LivreurService
from src.simulator.services.paiement_service import PaiementService
from src.simulator.services.restaurant_service import RestaurantService


SIM_CONFIG = {
    "temporal": {
        "pic_dejeuner_heure": 12.5,
        "pic_diner_heure": 20.0,
        "pic_duree_heures": 2.0,
        "facteur_weekend": 1.3,
    },
    "statuts": {
        "prob_livree": 0.8,
        "prob_annulee": 0.1,
        "livree": 0.8,
        "annulee": 0.1,
        "echouee": 0.1,
        "annulation_initiateur": {
            "client": 0.5,
            "restaurant": 0.3,
            "plateforme": 0.2,
        },
    },
    "paiements": {
        "methodes": {"carte": 0.6, "especes": 0.4},
        "echec_carte": 0.04,
        "causes_echec": {"timeout": 0.6, "refus": 0.3, "autre": 0.1},
        "tentatives_max": 3,
        "retry_delai_sec": 30,
    },
    "distributions": {
        "phases": {
            "preparation": {"mu": 20, "sigma": 5},
            "trajet": {"mu": 25, "sigma": 7},
            "attente_livreur": {"mu": 3, "sigma": 1},
        },
        "delai": {
            "reel_mu": 35,
            "reel_sigma": 5,
            "estime_mu": 30,
            "estime_sigma": 3,
            "retard_seuil": 2,
        },
        "montant": {"mu_log": 7.65, "sigma_log": 0.6, "min": 500, "max": 20000},
        "frais_livraison": {"base": 250, "gratuit_seuil": 5000},
    },
    "incidents": {
        "severites": {"basse": 0.5, "moyenne": 0.3, "haute": 0.2},
        "types": {"retard": 0.5, "restaurant_ferme": 0.3, "livreur_bloque": 0.2},
    },
    "zones": [
        {"nom": "Hydra", "poids": 1.0, "lat": 36.75, "lng": 3.05, "delai_extra_min": 0}
    ],
    "volume": {"jours_historique": 3, "nb_commandes_par_jour": 100},
}

TS = datetime(2026, 1, 15, 12, 30, 0)
ZONE = {"nom": "Hydra", "lat": 36.75, "lng": 3.05, "delai_extra_min": 2}


# ── PaiementService ─────────────────────────────────────────────


def test_paiement_especes_succes():
    svc = PaiementService(SIM_CONFIG)
    out = svc.traiter_paiement(1, 2000, "especes", TS)
    assert out["statut"] == "confirmé"
    assert out["topic"] == "paiements"
    assert out["tentative"] == 1


def test_paiement_carte_succes(monkeypatch):
    svc = PaiementService(SIM_CONFIG)
    monkeypatch.setattr(random, "random", lambda: 0.99)
    out = svc.traiter_paiement(2, 3000, "carte", TS)
    assert out["statut"] == "confirmé"


def test_paiement_carte_echec(monkeypatch):
    svc = PaiementService(SIM_CONFIG)
    monkeypatch.setattr(random, "random", lambda: 0.001)
    monkeypatch.setattr(random, "choices", lambda *a, **k: ["timeout"])
    out = svc.traiter_paiement(3, 3000, "carte", TS)
    assert out["statut"] == "échoué"
    assert out["cause"] == "timeout"
    assert out["next_retry_sec"] == 30


def test_retry_paiement_succes(monkeypatch):
    svc = PaiementService(SIM_CONFIG)
    monkeypatch.setattr(random, "random", lambda: 0.1)
    out = svc.retry_paiement(4, 3000, "carte", 2, TS)
    assert out["statut"] == "confirmé"


def test_retry_paiement_nouvel_echec(monkeypatch):
    svc = PaiementService(SIM_CONFIG)
    monkeypatch.setattr(random, "random", lambda: 0.95)
    monkeypatch.setattr(random, "choices", lambda *a, **k: ["refus"])
    out = svc.retry_paiement(5, 3000, "carte", 2, TS)
    assert out["statut"] == "échoué"
    assert out["tentative"] == 2


def test_retry_paiement_abandon():
    svc = PaiementService(SIM_CONFIG)
    out = svc.retry_paiement(6, 3000, "carte", 3, TS)
    assert out["statut"] == "abandonné"
    assert out["topic"] == "incidents"
    assert out["tentatives_totales"] == 3


def test_remboursement():
    svc = PaiementService(SIM_CONFIG)
    out = svc.rembourser(7, 5000, "client mécontent", TS)
    assert out["event_type"] == "remboursement"
    assert out["montant_rembourse"] == 5000
    assert out["raison"] == "client mécontent"


# ── LivreurService ──────────────────────────────────────────────


def test_accepter_mission_calcule_distance():
    svc = LivreurService(SIM_CONFIG)
    out = svc.accepter_mission(10, 1, 36.75, 3.05, 36.76, 3.06, TS)
    assert out["event_type"] == "mission_acceptée"
    assert out["distance_km"] > 0
    assert out["duree_trajet_estime_min"] >= 5


def test_position_gps():
    svc = LivreurService(SIM_CONFIG)
    out = svc.position_gps(1, 36.75, 3.05, 25.0, TS)
    assert out["event_type"] == "position_gps"
    assert out["vitesse_kmh"] == 25.0


def test_livraison_terminee():
    svc = LivreurService(SIM_CONFIG)
    out = svc.livraison_terminee(11, 1, 35, TS)
    assert out["event_type"] == "livraison_terminée"
    assert out["delai_reel_min"] == 35


def test_signaler_blocage_track_set():
    svc = LivreurService(SIM_CONFIG)
    out = svc.signaler_blocage(2, 12, 36.75, 3.05, TS)
    assert out["topic"] == "incidents"
    assert 2 in svc.livreurs_bloques


def test_refuser_mission():
    svc = LivreurService(SIM_CONFIG)
    out = svc.refuser_mission(3, 13, TS)
    assert out["event_type"] == "mission_refusée"


def test_haversine_distance_zero():
    svc = LivreurService(SIM_CONFIG)
    out = svc.accepter_mission(14, 1, 36.75, 3.05, 36.75, 3.05, TS)
    assert out["distance_km"] == 0.0


# ── RestaurantService ───────────────────────────────────────────


def test_accepter_commande():
    svc = RestaurantService(SIM_CONFIG)
    out = svc.accepter_commande(20, 5, TS)
    assert out["event_type"] == "commande_acceptée"
    assert out["temps_preparation_estime_min"] >= 5


def test_preparation_terminee():
    svc = RestaurantService(SIM_CONFIG)
    out = svc.preparation_terminee(20, 5, TS)
    assert out["event_type"] == "préparation_terminée"


def test_refuser_commande():
    svc = RestaurantService(SIM_CONFIG)
    out = svc.refuser_commande(21, 5, "surcharge", TS)
    assert out["raison"] == "surcharge"


def test_fermeture_reouverture_etat():
    svc = RestaurantService(SIM_CONFIG)
    assert not svc.est_ferme(99)
    svc.fermeture_temporaire(99, 30, TS)
    assert svc.est_ferme(99)
    svc.reouverture(99, TS)
    assert not svc.est_ferme(99)


# ── ClientService ───────────────────────────────────────────────


def test_creer_commande_payload():
    svc = ClientService(SIM_CONFIG)
    out = svc.creer_commande(1, 5, ZONE, TS)
    assert out["event_type"] == "commande_créée"
    assert out["zone"] == "Hydra"
    assert out["montant"] >= 500
    assert out["frais_livraison"] in (0, 250)
    assert out["montant_total"] == out["montant"] + out["frais_livraison"]


def test_annuler_commande():
    svc = ClientService(SIM_CONFIG)
    out = svc.annuler_commande(1, "changement d'avis", TS)
    assert out["initiateur"] == "client"


def test_laisser_avis_negatif(monkeypatch):
    svc = ClientService(SIM_CONFIG)
    monkeypatch.setattr(random, "random", lambda: 0.1)
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    out = svc.laisser_avis(
        1, delai_reel=55, delai_estime=30, note_livreur=4.0, timestamp=TS
    )
    assert out is not None
    assert out["sentiment"] == "négatif"
    assert out["note"] in (1, 2)


def test_laisser_avis_positif(monkeypatch):
    svc = ClientService(SIM_CONFIG)
    monkeypatch.setattr(random, "random", lambda: 0.1)
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    out = svc.laisser_avis(
        2, delai_reel=33, delai_estime=30, note_livreur=4.8, timestamp=TS
    )
    assert out is not None
    assert out["sentiment"] == "positif"
    assert out["note"] == 5


def test_laisser_avis_neutre(monkeypatch):
    svc = ClientService(SIM_CONFIG)
    monkeypatch.setattr(random, "random", lambda: 0.1)
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    out = svc.laisser_avis(
        3, delai_reel=45, delai_estime=30, note_livreur=3.5, timestamp=TS
    )
    assert out is not None
    assert out["sentiment"] == "neutre"
    assert out["note"] == 3


def test_laisser_avis_none(monkeypatch):
    svc = ClientService(SIM_CONFIG)
    # Retard <= 5, livreur < 4.5 → tombe à la fin → None
    out = svc.laisser_avis(
        4, delai_reel=33, delai_estime=30, note_livreur=4.0, timestamp=TS
    )
    assert out is None


# ── Orchestrator ────────────────────────────────────────────────


@pytest.fixture(autouse=False)
def seeded():
    random.seed(42)


def _orch():
    return Orchestrator(SIM_CONFIG)


def test_orchestrator_init():
    o = _orch()
    assert isinstance(o.client, ClientService)
    assert isinstance(o.paiement, PaiementService)


def test_orchestrator_commande_livree(monkeypatch):
    """Force destin = livree, force échec paiement pour couvrir branche retry."""
    o = _orch()
    monkeypatch.setattr(
        random, "choices", lambda values, weights=None, **k: [values[0]]
    )
    monkeypatch.setattr(random, "randint", lambda a, b: a)
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: mu)
    monkeypatch.setattr(random, "uniform", lambda a, b: a)
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(random, "random", lambda: 0.001)  # forcera échec paiement
    events = o.simuler_commande_complete(1, 10, 100, 200, ZONE, TS)
    types = [e["event_type"] for e in events]
    assert "commande_créée" in types
    assert "commande_acceptée" in types
    assert "préparation_terminée" in types
    assert "mission_acceptée" in types
    assert "livraison_terminée" in types


def _smart_choices(force: dict):
    """Patch random.choices : si une cible est dans values, on la force."""

    def fake(values, weights=None, **k):
        for key, val in force.items():
            if val in values:
                return [val]
        return [values[0]]

    return fake


def test_orchestrator_commande_annulee(monkeypatch):
    """Force destin = annulee, initiateur = restaurant."""
    o = _orch()
    monkeypatch.setattr(
        random, "choices", _smart_choices({"destin": "annulee", "init": "restaurant"})
    )
    monkeypatch.setattr(random, "randint", lambda a, b: a)
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: mu)
    monkeypatch.setattr(random, "uniform", lambda a, b: a)
    events = o.simuler_commande_complete(2, 11, 101, 201, ZONE, TS)
    types = [e["event_type"] for e in events]
    assert "commande_créée" in types
    assert "commande_refusée" in types


def test_orchestrator_commande_annulee_par_plateforme(monkeypatch):
    """Force destin = annulee, initiateur = plateforme → branche else."""
    o = _orch()
    monkeypatch.setattr(
        random, "choices", _smart_choices({"destin": "annulee", "init": "plateforme"})
    )
    monkeypatch.setattr(random, "randint", lambda a, b: a)
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: mu)
    monkeypatch.setattr(random, "uniform", lambda a, b: a)
    events = o.simuler_commande_complete(20, 11, 101, 201, ZONE, TS)
    raisons = [e.get("raison", "") for e in events]
    assert any("plateforme" in r for r in raisons)


def test_orchestrator_commande_echouee(monkeypatch):
    """Force destin = echouee → branche livraison_échouée."""
    o = _orch()
    monkeypatch.setattr(random, "choices", _smart_choices({"destin": "echouee"}))
    monkeypatch.setattr(random, "randint", lambda a, b: a)
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: mu)
    monkeypatch.setattr(random, "uniform", lambda a, b: a)
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(random, "random", lambda: 0.99)
    events = o.simuler_commande_complete(3, 12, 102, 202, ZONE, TS)
    types = [e["event_type"] for e in events]
    assert "livraison_échouée" in types
