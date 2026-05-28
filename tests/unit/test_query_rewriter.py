"""Couverture de rag.query_rewriter — règles d'extraction d'intent."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from src.rag.query_rewriter import (
    filter_by_date_range,
    parse_doc_timestamp,
    rewrite_query,
)


def test_rewrite_extracts_criticite():
    out = rewrite_query("incidents critiques de la semaine")
    assert out["qdrant_filters"]["criticite"] == "critique"
    assert out["matched"]["criticite"] == "critique"


def test_rewrite_extracts_haute_severity():
    out = rewrite_query("alertes haute sévérité")
    assert out["qdrant_filters"]["criticite"] == "haute"


def test_rewrite_extracts_zone():
    out = rewrite_query("retards à Hydra")
    assert out["qdrant_filters"]["zone"] == "Hydra"
    assert out["qdrant_filters"]["type_event"] == "retard"


def test_rewrite_extracts_zone_case_insensible():
    out = rewrite_query("incidents à HYDRA")
    assert out["qdrant_filters"]["zone"] == "Hydra"


def test_rewrite_extracts_type_event_dns():
    out = rewrite_query("panne dns récente")
    assert out["qdrant_filters"]["type_event"] == "dns_failure"


def test_rewrite_infrastructure_maps_to_critique():
    out = rewrite_query("incident infrastructure majeur")
    assert out["qdrant_filters"]["criticite"] == "critique"


def test_rewrite_source_only_if_no_other_match():
    out = rewrite_query("liste des avis clients récents")
    assert out["qdrant_filters"]["source"] == "avis_clients"


def test_rewrite_source_ignored_when_criticite_present():
    out = rewrite_query("avis critiques")
    # criticite gagne, source non posée
    assert "source" not in (out["qdrant_filters"] or {})


def test_rewrite_extracts_sentiment_negatif():
    out = rewrite_query("commentaires négatifs récents")
    assert out["matched"].get("sentiment") == "négatif"


def test_rewrite_extracts_date_range_mois_annee():
    out = rewrite_query("incidents en mars 2026")
    assert out["date_range"] is not None
    start, end = out["date_range"]
    assert start.year == 2026
    assert start.month == 3
    assert end.month == 3


def test_rewrite_extracts_date_range_decembre_annee():
    out = rewrite_query("incidents en décembre 2025")
    start, end = out["date_range"]
    assert start.month == 12
    assert end.year == 2025


def test_rewrite_extracts_date_range_derniers_jours():
    out = rewrite_query("incidents des 7 derniers jours")
    assert out["date_range"] is not None


def test_rewrite_extracts_date_range_mois_sans_annee():
    out = rewrite_query("incidents en juillet")
    assert out["date_range"] is not None
    start, _end = out["date_range"]
    assert start.month == 7


def test_rewrite_empty_query_no_filters():
    out = rewrite_query("bonjour ?")
    assert out["qdrant_filters"] is None
    assert out["date_range"] is None


def test_parse_doc_timestamp_found():
    ts = parse_doc_timestamp("Le 2026-03-15 14:30, incident détecté")
    assert ts == datetime(2026, 3, 15, 14, 30)


def test_parse_doc_timestamp_not_found():
    assert parse_doc_timestamp("aucune date ici") is None


def test_parse_doc_timestamp_invalid_format():
    assert parse_doc_timestamp("date 9999-99-99 99:99") is None


def test_filter_by_date_range_no_range_returns_all():
    chunks = [{"text": "foo"}, {"text": "bar"}]
    assert filter_by_date_range(chunks, None) == chunks


def test_filter_by_date_range_keeps_in_range():
    chunks = [
        {"text": "2026-03-15 12:00 incident"},
        {"text": "2026-05-01 09:00 autre"},
        {"text": "sans date — snapshot global"},
    ]
    rng = (datetime(2026, 3, 1), datetime(2026, 3, 31, 23, 59))
    kept = filter_by_date_range(chunks, rng)
    # Le 1er chunk dans la plage + le 3e sans date sont conservés
    assert len(kept) == 2
    assert any("snapshot" in c["text"] for c in kept)
    assert any("2026-03-15" in c["text"] for c in kept)


def test_filter_by_date_range_excludes_out_of_range():
    chunks = [{"text": "2025-01-01 00:00 vieux"}]
    rng = (datetime(2026, 1, 1), datetime(2026, 12, 31))
    assert filter_by_date_range(chunks, rng) == []
