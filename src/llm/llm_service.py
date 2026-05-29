"""LLM Service — Gemma3:1b via Ollama — streaming + génération + chat history."""

import httpx
import json
from typing import AsyncGenerator
import structlog

log = structlog.get_logger()

SYSTEM_PROMPT = """Tu es « RAG-Livraison », assistant de supervision opérationnelle
d'une plateforme de livraison de repas en Algérie. Tu réponds en français, de
façon concise et factuelle.

RÈGLE FONDAMENTALE : tu ne te bases QUE sur le CONTEXTE fourni ci-dessous.
Le contexte est une liste de passages au format :
    [Doc N | source=<source> | score=<score>]
    <texte du document>

Le champ `source` indique la provenance et donc le TYPE d'information :
- prometheus      → MÉTRIQUES SYSTÈME temps réel (taux succès, latences,
                    services up, score contexte) — un instantané daté.
- elasticsearch   → LOGS applicatifs récents (erreurs/warnings de services :
                    tracking-service, payment-service…), avec service et heure.
- incidents       → incidents métier (retard, restaurant fermé, livreur bloqué…).
- commandes / restaurants / livreurs / zones / avis_clients → DONNÉES MÉTIER.
- synthese        → agrégats et classements Top-N déjà calculés.

RÈGLES STRICTES (anti-hallucination) :
1. N'invente JAMAIS un chiffre, un nom, un service, une métrique ou un log
   absent du contexte. Si l'info n'y est pas, dis-le explicitement.
2. Si le CONTEXTE est vide ou ne contient pas l'information demandée, réponds
   exactement : « Information non disponible dans le contexte fourni. » puis,
   si utile, suggère de consulter Kibana (logs) ou Grafana (métriques).
3. Cite la provenance : « D'après les métriques Prometheus… », « Les logs
   montrent… », « Selon les données métier… ».
4. MÉTRIQUES : recopie la valeur EXACTE du contexte et précise l'heure du
   snapshot. Une valeur « N/A » signifie non disponible → ne la remplace pas
   par un chiffre inventé.
   ÉTAT DES SERVICES : si le contexte contient une ligne « services: nom=up,
   nom=down… » ou la phrase « Aucun service en panne », UTILISE-la directement
   pour répondre (liste les services en panne, ou indique qu'aucun ne l'est).
   N'invente un statut que si cette information est absente du contexte.
5. LOGS : précise toujours le service et l'heure de chaque erreur citée.
   Ne réponds jamais « oui » sans citer le log ou la métrique correspondante.
6. CLASSEMENTS : cite l'élément n°1 en premier ; recopie nom ET chiffres de la
   MÊME ligne, sans les mélanger.
7. Ne mélange pas les sources : n'attribue pas à un « log » une valeur qui vient
   d'une métrique Prometheus, et inversement.
8. Unités : délais en minutes, montants en DZD, latences en secondes.

Le paiement (payment-service, paiements) fait partie du périmètre : tu peux en
parler UNIQUEMENT s'il figure dans le contexte, jamais de mémoire.
"""


def _format_history(messages: list[dict]) -> str:
    """Formate les messages [{role, content}, ...] sauf le dernier user."""
    lines = []
    for m in messages[:-1]:
        role = m.get("role", "user")
        label = {
            "user": "UTILISATEUR",
            "assistant": "ASSISTANT",
            "system": "SYSTÈME",
        }.get(role, role.upper())
        lines.append(f"{label}: {m.get('content', '')}")
    return "\n".join(lines)


class LLMService:
    def __init__(
        self, host: str, port: int, model: str = "gemma3:1b", timeout: int = 120
    ):
        self.base_url = f"http://{host}:{port}"
        self.model = model
        self.timeout = timeout

    def _build_prompt(self, context: str, question: str) -> str:
        return f"{SYSTEM_PROMPT}\n\nCONTEXTE :\n{context}\n\nQUESTION : {question}\n\nRÉPONSE :"

    def _build_chat_prompt(self, messages: list[dict], context: str) -> str:
        last = messages[-1]["content"] if messages else ""
        history = _format_history(messages)
        history_block = (
            f"\n\nHISTORIQUE DE CONVERSATION :\n{history}" if history else ""
        )
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"CONTEXTE :\n{context}"
            f"{history_block}\n\n"
            f"QUESTION ACTUELLE : {last}\n\nRÉPONSE :"
        )

    async def generate(self, context: str, question: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": self._build_prompt(context, question),
                    "stream": False,
                    "options": {"temperature": 0.0, "top_p": 0.9, "num_predict": 512},
                },
            )
            r.raise_for_status()
            return r.json()["response"]

    async def stream(self, context: str, question: str) -> AsyncGenerator[str, None]:
        async for tok in self._post_stream(self._build_prompt(context, question)):
            yield tok

    async def chat(self, messages: list[dict], context: str) -> str:
        """Génération non-streaming avec historique de conversation."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": self._build_chat_prompt(messages, context),
                    "stream": False,
                    "options": {"temperature": 0.0, "top_p": 0.9, "num_predict": 512},
                },
            )
            r.raise_for_status()
            return r.json()["response"]

    async def chat_stream(
        self, messages: list[dict], context: str
    ) -> AsyncGenerator[str, None]:
        """Streaming avec historique de conversation."""
        async for tok in self._post_stream(self._build_chat_prompt(messages, context)):
            yield tok

    async def _post_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {"temperature": 0.0},
                },
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        chunk = json.loads(line)
                        if not chunk.get("done", False):
                            yield chunk.get("response", "")

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return self.model in [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return False
