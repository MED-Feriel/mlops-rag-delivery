"""Tests des fonctions pures de static_generator (pas de connexion DB)."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import random

import pytest

from src.simulator.static_generator import (
    description_incident,
    pick_methode_paiement,
    pick_severite,
    pick_statut,
    pick_type_incident,
    sample_commande_timestamp,
    temporal_factor,
    weighted_pick,
)


@pytest.fixture
def cfg():
    """Configuration minimale réutilisable."""
    return {
        "temporal": {
            "pic_dejeuner_heure": 12.5,
            "pic_diner_heure": 20.0,
            "pic_duree_heures": 2.0,
            "facteur_weekend": 1.3,
        },
        "statuts": {"prob_livree": 0.8, "prob_annulee": 0.1},
        "paiements": {"methodes": {"carte": 0.6, "espece": 0.4}},
        "incidents": {
            "severites": {"basse": 0.5, "moyenne": 0.3, "haute": 0.2},
            "types": {
                "retard": 0.4,
                "restaurant_ferme": 0.2,
                "livreur_bloque": 0.2,
                "paiement_echoue": 0.1,
                "adresse_incorrecte": 0.05,
                "probleme_qualite": 0.05,
            },
        },
    }


# ─── weighted_pick ───────────────────────────────────────────────────────────


def test_weighted_pick_returns_valid_index():
    idx = weighted_pick(["a", "b", "c"], [0.5, 0.3, 0.2])
    assert 0 <= idx < 3


def test_weighted_pick_deterministic_with_extreme_weight():
    # Si seul un poids est non-nul, on doit toujours obtenir cet index
    for _ in range(20):
        idx = weighted_pick(["a", "b", "c"], [0.0, 1.0, 0.0])
        assert idx == 1


# ─── temporal_factor ─────────────────────────────────────────────────────────


def test_temporal_factor_peaks_at_lunch(cfg):
    lunch = datetime(2026, 5, 14, 12, 30)  # jeudi 12h30
    off_peak = datetime(2026, 5, 14, 4, 0)  # jeudi 4h
    assert temporal_factor(lunch, cfg) > temporal_factor(off_peak, cfg)


def test_temporal_factor_peaks_at_dinner(cfg):
    dinner = datetime(2026, 5, 14, 20, 0)  # jeudi 20h
    morning = datetime(2026, 5, 14, 7, 0)  # jeudi 7h
    assert temporal_factor(dinner, cfg) > temporal_factor(morning, cfg)


def test_temporal_factor_weekend_boost(cfg):
    sat_noon = datetime(2026, 5, 16, 12, 30)  # samedi
    thu_noon = datetime(2026, 5, 14, 12, 30)  # jeudi
    assert temporal_factor(sat_noon, cfg) > temporal_factor(thu_noon, cfg)


# ─── sample_commande_timestamp ───────────────────────────────────────────────


def test_sample_commande_timestamp_in_range(cfg):
    random.seed(42)
    now = datetime.now()
    ts = sample_commande_timestamp(cfg, jours_historique=30)
    delta_days = (now - ts).total_seconds() / 86400
    assert 0 <= delta_days <= 30


# ─── pick_statut ─────────────────────────────────────────────────────────────


def test_pick_statut_returns_valid_value(cfg):
    valid = {"livree", "annulee", "echouee"}
    for _ in range(20):
        assert pick_statut(cfg) in valid


def test_pick_statut_distribution_favors_livree(cfg):
    random.seed(0)
    out = [pick_statut(cfg) for _ in range(1000)]
    # prob_livree=0.8 → on s'attend à au moins 60% de livrées
    assert out.count("livree") > 600


# ─── pick_methode_paiement / pick_severite / pick_type_incident ─────────────


def test_pick_methode_paiement_returns_valid_method(cfg):
    valid = {"carte", "espece"}
    for _ in range(20):
        assert pick_methode_paiement(cfg) in valid


def test_pick_severite_returns_valid_severity(cfg):
    valid = {"basse", "moyenne", "haute"}
    for _ in range(20):
        assert pick_severite(cfg) in valid


def test_pick_type_incident_returns_valid_type(cfg):
    valid = set(cfg["incidents"]["types"].keys())
    for _ in range(20):
        assert pick_type_incident(cfg) in valid


# ─── description_incident ───────────────────────────────────────────────────


def test_description_incident_known_type():
    d = description_incident("retard", "haute")
    assert "[HAUTE]" in d
    assert "Retard" in d


def test_description_incident_unknown_type_falls_back_to_type():
    d = description_incident("type_inconnu_xyz", "basse")
    assert "[BASSE]" in d
    assert "type_inconnu_xyz" in d


def test_description_incident_all_known_types():
    for t in [
        "retard",
        "restaurant_ferme",
        "livreur_bloque",
        "paiement_echoue",
        "adresse_incorrecte",
        "probleme_qualite",
    ]:
        d = description_incident(t, "moyenne")
        assert "[MOYENNE]" in d
        assert len(d) > 20  # non vide, description significative
