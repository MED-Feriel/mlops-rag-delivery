"""Couverture de monitoring.prometheus_metrics — extract_zone_filter + métriques."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from src.monitoring import prometheus_metrics as pm


def test_extract_zone_filter_none():
    assert pm.extract_zone_filter(None) == "none"
    assert pm.extract_zone_filter({}) == "none"


def test_extract_zone_filter_direct_key():
    assert pm.extract_zone_filter({"zone": "Hydra"}) == "Hydra"


def test_extract_zone_filter_must_clause():
    flt = {"must": [{"match": {"zone": "Bab Ezzouar"}}]}
    assert pm.extract_zone_filter(flt) == "Bab Ezzouar"


def test_extract_zone_filter_should_term_clause():
    flt = {"should": [{"term": {"zone": "Kouba"}}]}
    assert pm.extract_zone_filter(flt) == "Kouba"


def test_extract_zone_filter_must_not_equals():
    flt = {"must_not": [{"equals": {"zone": "Alger Centre"}}]}
    assert pm.extract_zone_filter(flt) == "Alger Centre"


def test_extract_zone_filter_must_no_zone():
    flt = {"must": [{"match": {"severite": "haute"}}]}
    assert pm.extract_zone_filter(flt) == "other"


def test_extract_zone_filter_skips_non_dict_items():
    flt = {"must": ["not-a-dict", {"match": {"zone": "Hydra"}}]}
    assert pm.extract_zone_filter(flt) == "Hydra"


def test_metrics_objects_exist():
    assert pm.RAG_QUERY_TOTAL is not None
    assert pm.RAG_QUERY_DURATION is not None
    assert pm.RAG_LLM_LATENCY is not None
    assert pm.RAG_EMBEDDING_DURATION is not None
    assert pm.RAG_RETRIEVED_DOCS is not None
    assert pm.RAG_CONTEXT_SCORE_AVG is not None
    assert pm.RAG_ACTIVE_REQUESTS is not None
