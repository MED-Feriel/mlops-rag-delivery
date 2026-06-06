"""Audit logging des accès API (MLOPS-117).

Chaque accès est journalisé en JSON structuré via structlog. Les logs partent
sur stdout → collectés par la stack ELK (logstash → Elasticsearch → Kibana),
donc pas d'écriture dans /var/log (chemin non writable en conteneur non-root).
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

log = structlog.get_logger("audit")


def log_api_access(
    *,
    request,
    user_id: str,
    action: str,
    resource: str,
    status_code: int,
    details: dict | None = None,
) -> None:
    """Journalise un accès API pour la conformité / la traçabilité."""
    try:
        client_ip = getattr(getattr(request, "client", None), "host", None)
        log.info(
            "api_access",
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            client_ip=client_ip,
            method=getattr(request, "method", None),
            path=str(getattr(getattr(request, "url", None), "path", "")),
            action=action,
            resource=resource,
            status_code=status_code,
            user_agent=request.headers.get("user-agent", "") if hasattr(request, "headers") else "",
            details=details or {},
        )
    except Exception:  # l'audit ne doit jamais casser une requête
        pass
