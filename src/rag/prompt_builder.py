"""Prompt builder — assemble system prompt + contexte + question pour Gemma3:1b."""

from __future__ import annotations

SYSTEM_PROMPT = (
    "Tu es un assistant expert en supervision d'une plateforme de livraison "
    "de repas en Algérie. Tu réponds STRICTEMENT en français.\n\n"
    "RÈGLES IMPÉRATIVES :\n"
    "1. Utilise UNIQUEMENT les informations présentes dans le CONTEXTE. "
    "N'invente jamais de noms, chiffres, zones ou commandes.\n"
    '2. Quand la question demande "qui", "quels", "combien", "liste" '
    "ou toute énumération, tu DOIS lister EXHAUSTIVEMENT toutes les "
    "occurrences trouvées dans le contexte sous forme de puces (- ), une "
    "par ligne, sans rien omettre.\n"
    "3. Traite ces termes comme équivalents : « bloqué », « en retard », "
    "« retardé », « perturbé » désignent tous une livraison en retard "
    "(type_event = livraison_retardee).\n"
    "4. Si le contexte ne contient pas l'information demandée, réponds "
    "exactement : « Information non disponible dans le contexte fourni. »\n"
    "5. Sois factuel, concis, sans phrase d'introduction inutile. "
    "Donne directement la réponse."
)


def build_rag_prompt(
    question: str, context: str, system_prompt: str = SYSTEM_PROMPT
) -> dict:
    """Retourne un dict {system, context, question, prompt} prêt pour le LLM."""
    full = (
        f"{system_prompt}\n\n"
        f"=== EXEMPLE ===\n"
        f"CONTEXTE :\n"
        f"- Livraison en retard — commande #111 zone Centre, livreur Ali.\n"
        f"- Livraison en retard — commande #222 zone Centre, livreur Sam.\n"
        f"- Livraison en retard — commande #333 zone Hydra, livreur Lina.\n"
        f"QUESTION : Quels livreurs sont en retard ?\n"
        f"RÉPONSE :\n"
        f"- Ali (commande #111, zone Centre)\n"
        f"- Sam (commande #222, zone Centre)\n"
        f"- Lina (commande #333, zone Hydra)\n"
        f"=== FIN EXEMPLE ===\n\n"
        f"=== CONTEXTE RÉEL ===\n{context}\n=== FIN CONTEXTE ===\n\n"
        f"QUESTION : {question}\n\n"
        f"Liste TOUS les éléments du CONTEXTE RÉEL qui correspondent à la "
        f"question, un par ligne, format identique à l'exemple. "
        f"N'omets AUCUNE entrée du contexte qui correspond.\n\n"
        f"RÉPONSE :\n"
    )
    return {
        "system": system_prompt,
        "context": context,
        "question": question,
        "prompt": full,
    }
