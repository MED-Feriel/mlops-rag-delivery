"""Métriques Prometheus du simulateur — par topic et par source_service."""

from prometheus_client import REGISTRY, Counter, Gauge


def _get_or_create(metric_cls, name, documentation, labelnames=()):
    """Crée la métrique, ou réutilise celle déjà enregistrée.

    Ce module peut être importé sous deux chemins distincts (``simulator.metrics``
    et ``src.simulator.metrics``), ce qui crée deux objets module et tente de
    réenregistrer les mêmes métriques → ``ValueError: Duplicated timeseries``.
    On rend l'enregistrement idempotent en réutilisant le collector existant.
    """
    try:
        return metric_cls(name, documentation, labelnames)
    except ValueError:
        # Déjà présent dans le registre global → on récupère le collector.
        existing = REGISTRY._names_to_collectors.get(name)
        if existing is not None:
            return existing
        raise


SIM_EVENTS_TOTAL = _get_or_create(
    Counter,
    "sim_events_total",
    "Nombre total d'événements Kafka publiés par le simulateur",
    ["topic", "source_service", "event_type"],
)

SIM_COMMANDES_TOTAL = _get_or_create(
    Counter,
    "sim_commandes_total",
    "Nombre de commandes complètes simulées (lifecycle)",
    ["destin"],  # livree | annulee | echouee
)

SIM_RUNNING = _get_or_create(
    Gauge,
    "sim_running",
    "1 si la boucle de production est active, 0 sinon",
)

# ── Métier : Paiement (Phase 1) ────────────────────────────────
PAYMENT_TOTAL = _get_or_create(
    Counter,
    "payment_total",
    "Nombre total de paiements traités",
    ["methode", "statut"],  # especes/carte/wallet/autre × confirmé/échoué/abandonné
)

PAYMENT_RETRY_TOTAL = _get_or_create(
    Counter,
    "payment_retry_total",
    "Nombre de tentatives de retry de paiement",
    ["methode", "cause"],  # cause: timeout, refus, autre
)
