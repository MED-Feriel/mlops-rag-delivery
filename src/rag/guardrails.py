"""Guardrails RAG — anti-hallucination avant l'appel LLM.

Quand le retrieval ne ramène rien (ou trop peu), un petit modèle comme
Gemma3:1b a tendance à inventer une réponse. Ce garde-fou détecte ce cas en
amont et renvoie une réponse de secours déterministe SANS appeler le LLM.

Appelé dans le pipeline après ``build_context`` : si ``check_context`` renvoie
``ok=False``, on retourne directement ``message`` comme réponse.
"""

from __future__ import annotations

# Réponse de secours alignée sur la règle n°2 du SYSTEM_PROMPT.
REFUS_CONTEXTE_VIDE = (
    "Information non disponible dans le contexte fourni. "
    "Aucun document pertinent n'a été récupéré pour cette question. "
    "Reformulez-la, ou consultez directement Kibana (logs) "
    "ou Grafana (métriques) pour le détail."
)


def check_context(context: str) -> tuple[bool, str]:
    """Vérifie que le retrieval a ramené quelque chose d'exploitable.

    Le vrai déclencheur d'hallucination est un contexte VIDE (0 document
    récupéré → ``build_context`` renvoie ""). Dans ce cas un petit modèle
    invente une réponse ; on court-circuite avec une réponse de secours.

    Retourne ``(ok, message)`` :
      - ``ok=True``  → contexte non vide, message vide, on appelle le LLM.
      - ``ok=False`` → contexte vide, ``message`` = réponse de secours à
        renvoyer telle quelle (pas d'appel LLM → pas d'hallucination).
    """
    if not context or not context.strip():
        return False, REFUS_CONTEXTE_VIDE
    return True, ""
