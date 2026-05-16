"""LLM Service — Gemma3:1b via Ollama — streaming + génération + chat history."""

import httpx
import json
from typing import AsyncGenerator
import structlog

log = structlog.get_logger()

SYSTEM_PROMPT = """Tu es un assistant expert en supervision de plateforme de livraison de repas.
Tu réponds en français, de façon concise et exploitable opérationnellement.
Tu bases UNIQUEMENT tes réponses sur le contexte fourni.
Tiens compte de l'historique de la conversation pour résoudre les références implicites
(ex : "ces retards" renvoie aux retards mentionnés plus haut).
Si le contexte est insuffisant, dis-le clairement."""


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
                    "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": 512},
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
                    "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": 512},
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
                    "options": {"temperature": 0.1},
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
