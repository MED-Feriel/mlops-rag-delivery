"""Génère monitoring/kibana/dashboards.ndjson (Saved Objects Kibana 8.x).

Crée :
  - 1 data view (index-pattern) ``livraison-*`` sur ``@timestamp`` ;
  - 7 visualisations agrégées (count / terms / date_histogram) — format legacy
    ``visState``, importable tel quel dans Kibana 8.12 ;
  - 4 dashboards regroupant ces visualisations.

Champs des events (routés depuis Kafka par Logstash) : ``event_type``,
``source_service``, ``type``, ``statut``, ``severite`` (sous-champ ``.keyword``).

Régénérer :  python monitoring/kibana/build_dashboards.py
Importer  :  Kibana → Stack Management → Saved Objects → Import → dashboards.ndjson
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "dashboards.ndjson"
INDEX_PATTERN_ID = "livraison-star"
INDEX_REF = [
    {
        "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
        "type": "index-pattern",
        "id": INDEX_PATTERN_ID,
    }
]
SEARCH_SOURCE = json.dumps(
    {"query": {"query": "", "language": "kuery"}, "filter": []}
)


def viz(vid: str, title: str, vis_state: dict) -> dict:
    """Construit un saved object 'visualization' agrégé."""
    return {
        "type": "visualization",
        "id": vid,
        "attributes": {
            "title": title,
            "visState": json.dumps(vis_state),
            "uiStateJSON": "{}",
            "description": "",
            "version": 1,
            "kibanaSavedObjectMeta": {"searchSourceJSON": SEARCH_SOURCE},
        },
        "references": INDEX_REF,
        "coreMigrationVersion": "8.12.0",
    }


def count_agg() -> dict:
    return {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}}


def terms_agg(agg_id: str, field: str, schema: str, size: int = 10) -> dict:
    return {
        "id": agg_id,
        "enabled": True,
        "type": "terms",
        "schema": schema,
        "params": {
            "field": field,
            "size": size,
            "order": "desc",
            "orderBy": "1",
            "otherBucket": False,
            "missingBucket": False,
        },
    }


def date_hist_agg(agg_id: str) -> dict:
    return {
        "id": agg_id,
        "enabled": True,
        "type": "date_histogram",
        "schema": "segment",
        "params": {"field": "@timestamp", "interval": "auto", "min_doc_count": 1},
    }


# ── Visualisations ────────────────────────────────────────────────
VISUALS = [
    viz(
        "viz-volume-total",
        "Volume total d'événements",
        {
            "title": "Volume total d'événements",
            "type": "metric",
            "aggs": [count_agg()],
            "params": {"metric": {"colorSchema": "Green to Red"}},
        },
    ),
    viz(
        "viz-par-service",
        "Événements par service",
        {
            "title": "Événements par service",
            "type": "pie",
            "aggs": [count_agg(), terms_agg("2", "source_service.keyword", "segment")],
            "params": {"isDonut": True, "addLegend": True, "legendPosition": "right"},
        },
    ),
    viz(
        "viz-par-type",
        "Répartition par type d'événement",
        {
            "title": "Répartition par type d'événement",
            "type": "pie",
            "aggs": [count_agg(), terms_agg("2", "event_type.keyword", "segment")],
            "params": {"isDonut": True, "addLegend": True, "legendPosition": "right"},
        },
    ),
    viz(
        "viz-timeline",
        "Timeline des événements par type",
        {
            "title": "Timeline des événements par type",
            "type": "histogram",
            "aggs": [
                count_agg(),
                date_hist_agg("2"),
                terms_agg("3", "event_type.keyword", "group", size=6),
            ],
            "params": {"addLegend": True, "legendPosition": "right", "seriesParams": []},
        },
    ),
    viz(
        "viz-top-incidents",
        "Top types d'incidents",
        {
            "title": "Top types d'incidents",
            "type": "table",
            "aggs": [count_agg(), terms_agg("2", "type.keyword", "bucket")],
            "params": {"perPage": 10, "showtotal": True},
        },
    ),
    viz(
        "viz-paiements-statut",
        "Paiements par statut",
        {
            "title": "Paiements par statut",
            "type": "pie",
            "aggs": [count_agg(), terms_agg("2", "statut.keyword", "segment")],
            "params": {"isDonut": True, "addLegend": True, "legendPosition": "right"},
        },
    ),
    viz(
        "viz-severite",
        "Sévérité des incidents",
        {
            "title": "Sévérité des incidents",
            "type": "pie",
            "aggs": [count_agg(), terms_agg("2", "severite.keyword", "segment")],
            "params": {"isDonut": True, "addLegend": True, "legendPosition": "right"},
        },
    ),
]


# ── Dashboards ────────────────────────────────────────────────────
def dashboard(did: str, title: str, viz_ids: list[str]) -> dict:
    """Assemble un dashboard avec une grille 2 colonnes (12 unités chacune)."""
    panels = []
    references = []
    for i, vid in enumerate(viz_ids):
        x = (i % 2) * 24
        y = (i // 2) * 15
        ref_name = f"panel_{i}"
        panels.append(
            {
                "panelIndex": str(i),
                "gridData": {"x": x, "y": y, "w": 24, "h": 15, "i": str(i)},
                "version": "8.12.0",
                "type": "visualization",
                "panelRefName": ref_name,
            }
        )
        references.append(
            {"name": f"{ref_name}", "type": "visualization", "id": vid}
        )
    return {
        "type": "dashboard",
        "id": did,
        "attributes": {
            "title": title,
            "hits": 0,
            "description": "",
            "panelsJSON": json.dumps(panels),
            "optionsJSON": json.dumps({"useMargins": True, "hidePanelTitles": False}),
            "version": 1,
            "timeRestore": False,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({"query": {"query": "", "language": "kuery"}, "filter": []})
            },
        },
        "references": references,
        "coreMigrationVersion": "8.12.0",
    }


DASHBOARDS = [
    dashboard(
        "dash-vue-globale",
        "Livraison — Vue globale",
        ["viz-volume-total", "viz-par-service", "viz-par-type", "viz-timeline"],
    ),
    dashboard(
        "dash-incidents",
        "Livraison — Incidents et anomalies",
        ["viz-top-incidents", "viz-severite", "viz-timeline"],
    ),
    dashboard(
        "dash-commandes-paiements",
        "Livraison — Commandes et paiements",
        ["viz-paiements-statut", "viz-volume-total", "viz-timeline"],
    ),
    dashboard(
        "dash-livraisons-restaurants",
        "Livraison — Livraisons et restaurants",
        ["viz-par-service", "viz-par-type", "viz-timeline"],
    ),
]


def main() -> None:
    index_pattern = {
        "type": "index-pattern",
        "id": INDEX_PATTERN_ID,
        "attributes": {"title": "livraison-*", "timeFieldName": "@timestamp"},
        "references": [],
        "coreMigrationVersion": "8.12.0",
    }
    objects = [index_pattern, *VISUALS, *DASHBOARDS]
    with open(OUT, "w", encoding="utf-8") as f:
        for obj in objects:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"{len(objects)} saved objects écrits dans {OUT}")


if __name__ == "__main__":
    main()
