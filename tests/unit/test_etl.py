"""Tests unitaires ETL — clean, normalize, chunk, document_builder."""

from __future__ import annotations

from datetime import datetime, timezone


from src.ingestion.chunk import chunk_documents, chunk_long_text
from src.ingestion.clean import clean, clean_rows
from src.ingestion.document_builder import doc_commande, doc_incident
from src.ingestion.normalize import UNIFIED_FIELDS, normalize


# ── clean ─────────────────────────────────────────────────────────────────


def test_clean_removes_duplicates_keeps_most_recent():
    rows = [
        {
            "id": 1,
            "type": "x",
            "severite": "haute",
            "created_at": datetime(2026, 1, 1),
            "commande_id": 10,
        },
        {
            "id": 1,
            "type": "x",
            "severite": "haute",
            "created_at": datetime(2026, 5, 1),
            "commande_id": 10,
        },
    ]
    kept, _ = clean_rows("incidents_actifs", rows)
    assert len(kept) == 1
    assert kept[0]["created_at"] == datetime(2026, 5, 1)


def test_clean_rejects_missing_required_fields():
    rows = [
        {
            "id": 1,
            "type": "x",
            "severite": "haute",
            "created_at": datetime.now(),
            "commande_id": 10,
        },
        {
            "id": 2,
            "type": None,
            "severite": "haute",
            "created_at": datetime.now(),
            "commande_id": 10,
        },  # type manquant
    ]
    kept, rejected = clean_rows("incidents_actifs", rows)
    assert len(kept) == 1
    assert len(rejected) == 1
    assert rejected[0]["_reason"] == "missing_required"


def test_clean_fixes_negative_delays():
    rows = [
        {
            "id": 1,
            "statut": "livree",
            "created_at": datetime.now(),
            "delai_reel_min": -5,
            "retard_min": -3,
        }
    ]
    kept, _ = clean_rows("commandes", rows)
    assert kept[0]["delai_reel_min"] is None
    assert kept[0]["retard_min"] is None


def test_clean_preserves_extract_result_keys():
    extract_result = {
        "incidents_actifs": [],
        "commandes": [{"id": 1, "statut": "livree", "created_at": datetime.now()}],
    }
    cleaned = clean(extract_result)
    assert set(cleaned.keys()) == {"incidents_actifs", "commandes"}


# ── normalize ──────────────────────────────────────────────────────────────


def test_normalize_returns_unified_schema():
    out = normalize({"id": "x-1", "source": "commandes", "text": "blah"})
    assert UNIFIED_FIELDS.issubset(out.keys())


def test_normalize_calculates_criticite_haute_when_retard_over_60():
    out = normalize(
        {"id": "x", "source": "commandes", "delai_reel_min": 90, "delai_estime_min": 20}
    )
    assert out["criticite"] == "haute"


def test_normalize_criticite_info_when_no_delay_data():
    out = normalize({"id": "x", "source": "zones"})
    assert out["criticite"] == "info"


def test_normalize_timestamp_is_iso_string():
    out = normalize(
        {
            "id": "x",
            "source": "commandes",
            "created_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
        }
    )
    assert out["timestamp"].startswith("2026-05-10")


# ── chunk ──────────────────────────────────────────────────────────────────


def test_chunk_long_text_short_text_returns_single_chunk():
    assert chunk_long_text("short", chunk_size=512) == ["short"]


def test_chunk_long_text_respects_size():
    text = "abcdef. " * 200  # 1600 chars
    chunks = chunk_long_text(text, chunk_size=200, chunk_overlap=20)
    assert len(chunks) > 1
    # chaque chunk au plus chunk_size + overlap (à cause de _apply_overlap)
    for c in chunks:
        assert len(c) <= 200 + 20


def test_chunk_long_text_empty_returns_empty_list():
    assert chunk_long_text("") == []


def test_chunk_documents_duplicates_metadata_for_long_docs():
    long_text = "phrase. " * 200
    ids, texts, metas = chunk_documents(
        ["doc-1"],
        [long_text],
        [{"source": "x"}],
        chunk_size=200,
        chunk_overlap=20,
    )
    assert len(ids) > 1
    assert ids[0] == "doc-1-c0"
    assert all(m["source"] == "x" for m in metas)


# ── document_builder : pas de None visible dans la phrase naturelle ────────


def test_doc_incident_has_no_literal_none():
    row = {
        "id": 42,
        "type": "retard",
        "severite": "haute",
        "resolu": False,
        "created_at": datetime(2026, 5, 1),
        "commande_id": 100,
        "statut": "annulee",
        "zone_nom": "Bab Ezzouar",
        "restaurant_nom": "Pizza Z",
        "livreur_nom": "Karim",
        "description": "Retard livreur",
    }
    _, text, _ = doc_incident(row)
    assert "None" not in text


def test_doc_commande_handles_missing_optional_fields():
    row = {
        "id": 1,
        "statut": "livree",
        "montant": 1000,
        "delai_estime_min": 30,
        "delai_reel_min": None,
        "retard_min": None,
        "note_livreur": None,
        "commentaire": None,
        "methode_paiement": "cash",
        "created_at": datetime(2026, 5, 1),
        "zone_nom": "Z",
        "restaurant_nom": "R",
        "livreur_nom": "L",
    }
    _, text, _ = doc_commande(row)
    assert "None" not in text  # gérés via 'N/A' / '(aucun)'
