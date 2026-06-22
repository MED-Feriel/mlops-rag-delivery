"""Prompt builder — SYSTEM_PROMPT + assemblage pour Gemma3:1b.

⚠️ Source UNIQUE du prompt système : ``src/llm/llm_service.py`` importe
``SYSTEM_PROMPT`` et ``build_prompt`` d'ici. Modifier le prompt ICI change donc
le comportement réel de l'assistant (chemins /query, /chat et /v1/chat/completions).
"""

from __future__ import annotations

import structlog

log = structlog.get_logger()

# Version du prompt (tracée dans MLflow via llm_service.PROMPT_VERSION).
PROMPT_VERSION = "v2.1"

SYSTEM_PROMPT = """Tu es un assistant de supervision pour une plateforme de livraison \
de repas en Algérie. Réponds toujours en français, de façon concise, factuelle et \
directe (3 phrases maximum).

Consignes :
- Appuie-toi UNIQUEMENT sur les informations du CONTEXTE ci-dessous pour répondre. \
N'invente jamais un chiffre, un restaurant, une zone, un livreur ni un service.
- Réponds toujours avec les données présentes dans le contexte. N'écris \
« Information non disponible dans les données actuelles. » que si le contexte ne \
contient réellement aucun élément lié à la question.
- Ne te présente pas, ne salue pas, ne conclus pas et ne pose jamais de question. \
Donne directement la réponse.
- Pour une énumération, utilise des puces « • » (5 éléments maximum). Pour un \
diagnostic, donne la cause principale puis l'action recommandée. Pour une valeur \
chiffrée, cite le chiffre exact issu du contexte.
"""


def build_prompt(context: str, question: str) -> str:
    """Construit le prompt complet (system + contexte + question) pour le LLM."""
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"<contexte>\n{context}\n</contexte>\n\n"
        f"<question>\n{question}\n</question>\n\n"
        f"<Réponse (concise, factuelle, sans présentation)>"
    )


def build_rag_prompt(
    question: str, context: str, system_prompt: str = SYSTEM_PROMPT
) -> dict:
    """Variante few-shot (utilisée par les tests). Retourne un dict prêt LLM."""
    full = (
        f"{system_prompt}\n\n"
        f"=== EXEMPLE ===\n"
        f"CONTEXTE :\n"
        f"- Livraison en retard — commande #111 zone Centre, livreur Ali.\n"
        f"- Livraison en retard — commande #222 zone Centre, livreur Sam.\n"
        f"- Livraison en retard — commande #333 zone Hydra, livreur Lina.\n"
        f"QUESTION : Quels livreurs sont en retard ?\n"
        f"RÉPONSE :\n"
        f"• Ali (commande #111, zone Centre)\n"
        f"• Sam (commande #222, zone Centre)\n"
        f"• Lina (commande #333, zone Hydra)\n"
        f"=== FIN EXEMPLE ===\n\n"
        f"=== CONTEXTE RÉEL ===\n{context}\n=== FIN CONTEXTE ===\n\n"
        f"QUESTION : {question}\n\n"
        f"RÉPONSE :\n"
    )
    return {
        "system": system_prompt,
        "context": context,
        "question": question,
        "prompt": full,
    }
