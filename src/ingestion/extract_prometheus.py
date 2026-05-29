"""Snapshot santé système Prometheus → Qdrant (toutes les minutes).

Famille 3 (état système) : permet au RAG de répondre aux questions sur l'état
courant de la plateforme (taux de succès, latences, erreurs, services up).

Principe : 1 SEUL document « rapport santé système » avec un ID FIXE
(``prometheus_health_snapshot_current``). Il est REMPLACÉ à chaque run via upsert
→ pas d'accumulation, la mémoire Qdrant reste stable.

Exécuté toutes les minutes par le DAG ``rag_prometheus_snapshot``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
import structlog

log = structlog.get_logger()

PROM_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

# Métriques surveillées — liste filtrée (RAG + infra) pour rester léger.
# kafka_consumer_lag peut être absent selon l'exporter → renverra N/A (toléré).
QUERIES = {
    "rag_queries_total": "sum(rag_query_total)",
    "rag_success_rate": (
        "sum(rag_query_total{status='success'}) / sum(rag_query_total) * 100"
    ),
    "rag_latence_p95_s": (
        "histogram_quantile(0.95, "
        "sum(rate(rag_query_duration_seconds_bucket[5m])) by (le))"
    ),
    "rag_llm_latence_p95_s": (
        "histogram_quantile(0.95, "
        "sum(rate(rag_llm_latency_seconds_bucket[5m])) by (le))"
    ),
    "rag_context_score": "rag_context_score_avg",
    "rag_active_requests": "rag_active_requests",
    "kafka_lag": "sum(kafka_consumer_lag) by (topic)",
    "api_error_rate": "sum(rate(rag_query_total{status='error'}[5m]))",
    "services_up": "sum(up)",
}


async def fetch_metric(
    client: httpx.AsyncClient, name: str, query: str
) -> tuple[str, float | None]:
    """Requête Prometheus → (valeur formatée pour le rapport, valeur float|None)."""
    try:
        r = await client.get(
            f"{PROM_URL}/api/v1/query", params={"query": query}, timeout=5
        )
        result = r.json().get("data", {}).get("result", [])
        if not result:
            return f"{name}: N/A", None
        val = float(result[0]["value"][1])
        # histogram_quantile renvoie NaN sans trafic récent → N/A plutôt que "nans"
        if val != val:  # NaN
            return f"{name}: N/A", None
        if "rate" in name or "pct" in name or "score" in name:
            return f"{name}: {val:.3f}", val
        if "latence" in name or name.endswith("_s"):
            return f"{name}: {val:.2f}s", val
        return f"{name}: {val:.0f}", val
    except Exception as e:
        return f"{name}: erreur ({e})", None


async def fetch_services_status(
    client: httpx.AsyncClient,
) -> tuple[str, list[str]]:
    """Récupère l'état up/down de chaque service depuis la métrique `up`.

    Retourne ``(ligne, services_en_panne)`` :
      - ``ligne`` : "services: rag-api=up, qdrant=up, ..." (pour le contexte RAG).
      - ``services_en_panne`` : liste des jobs dont up=0 (pour l'interprétation).
    Chaque service est identifié par le label `job` de la métrique Prometheus.
    """
    try:
        r = await client.get(
            f"{PROM_URL}/api/v1/query", params={"query": "up"}, timeout=5
        )
        result = r.json().get("data", {}).get("result", [])
    except Exception as e:
        return f"services: erreur ({e})", []

    statuses: dict[str, str] = {}
    for item in result:
        metric = item.get("metric", {})
        job = metric.get("job") or metric.get("instance") or "inconnu"
        try:
            up = float(item["value"][1]) >= 1
        except (KeyError, ValueError, IndexError):
            up = False
        statuses[job] = "up" if up else "down"

    if not statuses:
        return "services: N/A", []

    ligne = "services: " + ", ".join(f"{j}={s}" for j, s in sorted(statuses.items()))
    down = sorted(j for j, s in statuses.items() if s == "down")
    return ligne, down


def _phrase_naturelle(vals: dict[str, float | None]) -> str:
    """Décrit l'état système en langage naturel (aligne l'embedding sur les
    questions type « état de santé de la plateforme », « taux de succès RAG »)."""
    phrases: list[str] = []
    sr = vals.get("rag_success_rate")
    if sr is not None:
        etat = "satisfaisant" if sr >= 95 else ("correct" if sr >= 90 else "dégradé")
        phrases.append(f"Le taux de succès du RAG est de {sr:.1f}% ({etat}).")
    tot = vals.get("rag_queries_total")
    if tot is not None:
        phrases.append(f"Au total, {tot:.0f} requêtes RAG ont été traitées.")
    p95 = vals.get("rag_latence_p95_s")
    if p95 is not None:
        phrases.append(f"La latence p95 des requêtes RAG est de {p95:.2f} seconde(s).")
    err = vals.get("api_error_rate")
    if err is not None:
        phrases.append(f"Le taux d'erreur de l'API est de {err:.3f} requête/seconde.")
    up = vals.get("services_up")
    if up is not None:
        phrases.append(f"{up:.0f} service(s) sont actuellement actifs (up).")
    cs = vals.get("rag_context_score")
    if cs is not None:
        phrases.append(f"Le score de pertinence du contexte Qdrant est de {cs:.3f}.")
    return " ".join(phrases)


async def generate_health_snapshot() -> dict:
    """Génère 1 document « rapport santé système » depuis Prometheus."""
    ts = datetime.now(timezone.utc)

    import asyncio

    async with httpx.AsyncClient() as client:
        pairs = await asyncio.gather(
            *[fetch_metric(client, name, query) for name, query in QUERIES.items()]
        )
        services_ligne, services_down = await fetch_services_status(client)

    results = [p[0] for p in pairs]
    vals = {name: p[1] for name, p in zip(QUERIES.keys(), pairs)}
    # Ligne explicite up/down par service ajoutée au détail des métriques.
    lignes = "\n".join(results + [services_ligne])

    # Verdict global sur la santé de la plateforme.
    sr = vals.get("rag_success_rate")
    err = vals.get("api_error_rate")
    if (
        services_down
        or (sr is not None and sr < 90)
        or (err is not None and err > 0.05)
    ):
        verdict = "La plateforme présente des signes de dégradation."
    else:
        verdict = "La plateforme est en bonne santé et fonctionne normalement."

    # Phrase naturelle sur les services en panne (réponse à "quels services
    # sont en panne ?") — citée explicitement pour que le LLM puisse répondre.
    if services_down:
        phrase_services = f" Services en panne : {', '.join(services_down)}."
    else:
        phrase_services = " Aucun service en panne : tous les services sont actifs."

    # En-tête en langage naturel (aligné sur les questions) + détail technique.
    texte = (
        f"État de santé de la plateforme au {ts.strftime('%Y-%m-%d %H:%M')} UTC. "
        f"{verdict} {_phrase_naturelle(vals)}{phrase_services}\n\n"
        f"Détail des métriques système :\n{lignes}\n\n"
        f"Interprétation automatique :"
    )

    # Alertes détaillées à partir des valeurs disponibles.
    interpretations = []
    if services_down:
        interpretations.append(f"\n🔴 Service(s) en panne : {', '.join(services_down)}")
    if sr is not None and sr < 90:
        interpretations.append(f"\n⚠️ Taux de succès RAG bas : {sr:.1f}% (seuil: 95%)")
    if err is not None and err > 0.05:
        interpretations.append(f"\n🔴 Taux erreur élevé : {err:.3f} req/s")
    cs = vals.get("rag_context_score")
    if cs is not None and cs < 0.30:
        interpretations.append(f"\n⚠️ Score contexte Qdrant bas : {cs:.3f}")

    if interpretations:
        texte += "".join(interpretations)
    else:
        texte += "\n✅ Aucune anomalie détectée — plateforme nominale."

    return {
        # ID FIXE → remplace le snapshot précédent à chaque run (pas d'accumulation)
        "id": "prometheus_health_snapshot_current",
        "source": "prometheus",
        "source_service": "monitoring",
        "topic": "metriques_systeme",
        "type_event": "health_snapshot",
        "criticite": "normale",
        "zone": "all",
        "timestamp": ts.isoformat(),
        "texte": texte,
        "ttl_hours": 0.1,  # remplacé toutes les minutes
    }


async def index_health_to_qdrant(qdrant_store, embedder) -> int:
    """Embed le snapshot et l'upsert sous ID fixe. Retourne 1 si indexé."""
    doc = await generate_health_snapshot()

    import asyncio

    loop = asyncio.get_event_loop()
    vectors = await loop.run_in_executor(None, lambda: embedder.embed([doc["texte"]]))

    n = qdrant_store.upsert(
        [doc["id"]],
        vectors,
        [doc["texte"]],
        [{k: v for k, v in doc.items() if k not in ("texte", "id")}],
    )
    log.info("prometheus_snapshot_indexed", n=n)
    return n
