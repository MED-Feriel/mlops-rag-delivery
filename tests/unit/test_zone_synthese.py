"""Tests unitaires de build_zone_synthese (synthèse-diagnostic par zone, F4)."""

from src.ingestion.document_builder import build_zone_synthese

ZONES = [
    {
        "id": 1,
        "nom": "Hydra",
        "nb_commandes_30j": 800,
        "nb_annulees": 60,
        "retard_moyen": 18.0,
        "note_moyenne": 3.9,
    },
    {
        "id": 2,
        "nom": "Dely Ibrahim",
        "nb_commandes_30j": 1200,
        "nb_annulees": 40,
        "retard_moyen": 6.0,
        "note_moyenne": 4.4,
    },
    {
        "id": 3,
        "nom": "Petite",
        "nb_commandes_30j": 20,  # ≤ 50 → exclue
        "nb_annulees": 1,
        "retard_moyen": 3.0,
        "note_moyenne": 4.5,
    },
]
TOP_RESTOS = [
    {
        "nom": "Pizza Hydra",
        "zone_nom": "Hydra",
        "pct_problemes": 22.5,
        "retard_moyen": 25.0,
    },
]
INCIDENTS = [
    {"zone_nom": "Hydra", "type": "retard_livraison", "n": 45},
]


def test_zones_peu_actives_exclues():
    docs = build_zone_synthese(ZONES, TOP_RESTOS, INCIDENTS)
    noms = [meta["zone"] for _, _, meta in docs]
    assert "Petite" not in noms
    assert len(docs) == 2


def test_source_et_topic_synthese():
    docs = build_zone_synthese(ZONES, TOP_RESTOS, INCIDENTS)
    for _, _, meta in docs:
        assert meta["source"] == "synthese"  # → jamais chunké
        assert meta["topic"] == "zone_synthese"


def test_zone_au_dessus_moyenne_est_haute_criticite():
    docs = build_zone_synthese(ZONES, TOP_RESTOS, INCIDENTS)
    hydra = next(meta for _, _, meta in docs if meta["zone"] == "Hydra")
    # Hydra (18 min) très au-dessus de la moyenne plateforme (~10.7 min).
    assert hydra["criticite"] == "haute"


def test_texte_contient_restaurants_et_incidents():
    docs = build_zone_synthese(ZONES, TOP_RESTOS, INCIDENTS)
    hydra_text = next(t for _, t, m in docs if m["zone"] == "Hydra")
    assert "Pizza Hydra" in hydra_text
    assert "retard_livraison" in hydra_text
    assert "moyenne plateforme" in hydra_text


def test_zone_sans_resto_problematique_message_par_defaut():
    docs = build_zone_synthese(ZONES, TOP_RESTOS, INCIDENTS)
    dely_text = next(t for _, t, m in docs if m["zone"] == "Dely Ibrahim")
    assert "aucun restaurant problématique" in dely_text


def test_liste_vide_si_pas_de_zones():
    assert build_zone_synthese([], [], []) == []


def test_id_deterministe_par_zone():
    docs = build_zone_synthese(ZONES, TOP_RESTOS, INCIDENTS)
    ids = [doc_id for doc_id, _, _ in docs]
    assert "synthese-zone-1" in ids  # id basé sur z["id"]
