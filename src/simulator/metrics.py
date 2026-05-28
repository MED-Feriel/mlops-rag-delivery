"""Métriques Prometheus du simulateur — par topic et par source_service."""

from prometheus_client import Counter, Gauge

SIM_EVENTS_TOTAL = Counter(
    "sim_events_total",
    "Nombre total d'événements Kafka publiés par le simulateur",
    ["topic", "source_service", "event_type"],
)

SIM_COMMANDES_TOTAL = Counter(
    "sim_commandes_total",
    "Nombre de commandes complètes simulées (lifecycle)",
    ["destin"],  # livree | annulee | echouee
)

SIM_RUNNING = Gauge(
    "sim_running",
    "1 si la boucle de production est active, 0 sinon",
)
