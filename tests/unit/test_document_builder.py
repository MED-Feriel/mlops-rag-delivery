"""Tests unitaires pour src/ingestion/document_builder.py — pures fonctions."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from src.ingestion.document_builder import (
    _fmt_dt,
    doc_commande,
    doc_incident,
    doc_incidents_par_zone,
    doc_restaurant,
    doc_synthese_incidents,
    doc_synthese_paiements,
    doc_tendance_volume,
    doc_top_restaurants,
    doc_zone,
)


# ─── _fmt_dt ─────────────────────────────────────────────────────────────────


def test_fmt_dt_with_datetime():
    dt = datetime(2026, 5, 16, 14, 30)
    assert _fmt_dt(dt) == "2026-05-16 14:30"


def test_fmt_dt_with_none_returns_empty():
    assert _fmt_dt(None) == ""


def test_fmt_dt_with_string_passthrough():
    assert _fmt_dt("hier") == "hier"


# ─── doc_incident ────────────────────────────────────────────────────────────


def _incident_row(**overrides):
    base = {
        "id": 42,
        "type": "livraison_retardee",
        "severite": "haute",
        "resolu": False,
        "created_at": datetime(2026, 5, 16, 12, 0),
        "commande_id": 4521,
        "statut": "en_cours",
        "zone_nom": "Bab Ezzouar",
        "restaurant_nom": "Pizza Roma",
        "livreur_nom": "Ali",
        "description": "Bouchons sur la rocade",
    }
    base.update(overrides)
    return base


def test_doc_incident_returns_id_text_meta():
    doc_id, text, meta = doc_incident(_incident_row())
    assert doc_id == "incident-42"
    assert "Incident #42" in text
    assert "Bab Ezzouar" in text
    assert "NON RÉSOLU" in text
    assert meta["source"] == "incidents"
    assert meta["criticite"] == "haute"
    assert meta["zone"] == "Bab Ezzouar"
    assert meta["resolu"] is False


def test_doc_incident_resolved_label():
    _, text, meta = doc_incident(_incident_row(resolu=True))
    assert "résolu" in text
    assert "NON RÉSOLU" not in text
    assert meta["resolu"] is True


# ─── doc_commande ────────────────────────────────────────────────────────────


def _commande_row(**overrides):
    base = {
        "id": 100,
        "statut": "livree",
        "created_at": datetime(2026, 5, 16, 12, 0),
        "zone_nom": "Hydra",
        "restaurant_nom": "Sushi Bar",
        "livreur_nom": "Sam",
        "montant": 1500.0,
        "methode_paiement": "carte",
        "delai_estime_min": 30,
        "delai_reel_min": 35,
        "retard_min": 5,
        "note_livreur": 4.5,
        "commentaire": "OK",
    }
    base.update(overrides)
    return base


def test_doc_commande_basse_criticite():
    _, text, meta = doc_commande(_commande_row(retard_min=5))
    assert "retard de 5 min" in text
    assert meta["criticite"] == "basse"


def test_doc_commande_moyenne_criticite():
    _, _, meta = doc_commande(_commande_row(retard_min=20))
    assert meta["criticite"] == "moyenne"


def test_doc_commande_haute_criticite():
    _, _, meta = doc_commande(_commande_row(retard_min=60))
    assert meta["criticite"] == "haute"


def test_doc_commande_a_l_heure_when_no_retard():
    _, text, _ = doc_commande(_commande_row(retard_min=0))
    assert "à l'heure" in text


def test_doc_commande_handles_no_note():
    _, text, _ = doc_commande(_commande_row(note_livreur=None))
    assert "non notée" in text


def test_doc_commande_handles_no_comment():
    _, text, _ = doc_commande(_commande_row(commentaire=None))
    assert "(aucun)" in text


def test_doc_commande_handles_no_delai_reel():
    _, text, _ = doc_commande(_commande_row(delai_reel_min=None))
    assert "N/A" in text


# ─── doc_restaurant ──────────────────────────────────────────────────────────


def _restaurant_row(**overrides):
    base = {
        "id": 7,
        "nom": "Pizza Roma",
        "type_cuisine": "italienne",
        "zone_nom": "Centre",
        "nb_commandes_30j": 100,
        "nb_annulees": 5,
        "nb_echouees": 2,
        "note_moyenne_30j": 4.2,
        "retard_moyen": 12.0,
        "note_moyenne": 4.0,
    }
    base.update(overrides)
    return base


def test_doc_restaurant_low_criticite():
    _, _, meta = doc_restaurant(_restaurant_row(nb_annulees=2, nb_commandes_30j=100))
    assert meta["criticite"] == "basse"


def test_doc_restaurant_moyenne_criticite():
    _, _, meta = doc_restaurant(_restaurant_row(nb_annulees=15, nb_commandes_30j=100))
    assert meta["criticite"] == "moyenne"


def test_doc_restaurant_haute_criticite():
    _, _, meta = doc_restaurant(_restaurant_row(nb_annulees=30, nb_commandes_30j=100))
    assert meta["criticite"] == "haute"


def test_doc_restaurant_handles_zero_commandes():
    _, text, _ = doc_restaurant(_restaurant_row(nb_commandes_30j=0, nb_annulees=0))
    assert "0 commandes" in text


# ─── doc_zone ────────────────────────────────────────────────────────────────


def _zone_row(**overrides):
    base = {
        "id": 3,
        "nom": "Bab Ezzouar",
        "nb_commandes_30j": 500,
        "nb_annulees": 50,
        "delai_moyen": 28.0,
        "retard_moyen": 10.0,
        "note_moyenne": 4.0,
    }
    base.update(overrides)
    return base


def test_doc_zone_haute_criticite_when_retard_high():
    _, _, meta = doc_zone(_zone_row(retard_moyen=20.0))
    assert meta["criticite"] == "haute"


def test_doc_zone_moyenne_criticite_when_retard_low():
    _, text, meta = doc_zone(_zone_row(retard_moyen=5.0))
    assert meta["criticite"] == "moyenne"
    assert "Bab Ezzouar" in text


# ─── doc_synthese_incidents ──────────────────────────────────────────────────


def test_doc_synthese_incidents_empty_returns_none():
    assert doc_synthese_incidents([]) is None


def test_doc_synthese_incidents_aggregates():
    rows = [
        {"type": "retard", "severite": "haute", "n": 10, "n_actifs": 3},
        {"type": "annulation", "severite": "moyenne", "n": 5, "n_actifs": 1},
    ]
    doc_id, text, meta = doc_synthese_incidents(rows)
    assert doc_id == "synthese-incidents"
    assert "Total: 15 incidents" in text
    assert "4 encore actifs" in text
    assert "retard" in text
    assert "annulation" in text
    assert meta["topic"] == "synthese_incidents"


# ─── doc_top_restaurants ─────────────────────────────────────────────────────


def test_doc_top_restaurants_empty_returns_none():
    assert doc_top_restaurants([]) is None


def test_doc_top_restaurants_lists_entries():
    rows = [
        {
            "nom": "Resto A",
            "zone_nom": "Centre",
            "nb_commandes": 50,
            "nb_annulees": 10,
            "nb_echouees": 5,
            "pct_problemes": 30,
            "retard_moyen": 12.5,
        }
    ]
    doc_id, text, meta = doc_top_restaurants(rows)
    assert doc_id == "synthese-top-restaurants"
    assert "Resto A" in text
    assert "30%" in text
    assert meta["criticite"] == "haute"


# ─── doc_synthese_paiements ──────────────────────────────────────────────────


def test_doc_synthese_paiements_empty_returns_none():
    assert doc_synthese_paiements([]) is None


def test_doc_synthese_paiements_aggregates_by_method():
    rows = [
        {"methode_paiement": "carte", "statut": "livree", "n": 80, "pct_methode": 80},
        {"methode_paiement": "carte", "statut": "echouee", "n": 20, "pct_methode": 20},
        {"methode_paiement": "espece", "statut": "livree", "n": 50, "pct_methode": 100},
    ]
    _, text, meta = doc_synthese_paiements(rows)
    assert "carte" in text
    assert "espece" in text
    assert meta["topic"] == "synthese_paiements"


# ─── doc_incidents_par_zone ──────────────────────────────────────────────────


def test_doc_incidents_par_zone_empty_returns_none():
    assert doc_incidents_par_zone([]) is None


def test_doc_incidents_par_zone_groups_by_zone():
    rows = [
        {"zone_nom": "Centre", "type": "retard", "n": 10},
        {"zone_nom": "Centre", "type": "annulation", "n": 5},
        {"zone_nom": "Hydra", "type": "retard", "n": 3},
    ]
    _, text, meta = doc_incidents_par_zone(rows)
    assert "Centre" in text
    assert "Hydra" in text
    assert "15 incidents" in text  # Centre total
    assert meta["topic"] == "incidents_par_zone"


# ─── doc_tendance_volume ─────────────────────────────────────────────────────


def test_doc_tendance_volume_empty_returns_none():
    assert doc_tendance_volume([]) is None


def test_doc_tendance_volume_caps_to_14_entries():
    rows = [
        {
            "jour": f"2026-05-{i:02d}",
            "nb_commandes": 100 + i,
            "nb_annulees": 5,
            "note_moyenne": 4.0,
            "retard_moyen": 10.0,
        }
        for i in range(1, 21)
    ]
    _, text, meta = doc_tendance_volume(rows)
    assert text.count("2026-05-") == 14
    assert meta["topic"] == "tendance_volume"


def test_doc_tendance_volume_handles_none_metrics():
    rows = [
        {
            "jour": "2026-05-16",
            "nb_commandes": 100,
            "nb_annulees": 5,
            "note_moyenne": None,
            "retard_moyen": None,
        }
    ]
    _, text, _ = doc_tendance_volume(rows)
    assert "0.00/5" in text
    assert "0.0 min" in text
