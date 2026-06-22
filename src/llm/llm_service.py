"""LLM Service — Gemma3:1b via Ollama — streaming + génération + chat history."""

import hashlib
import httpx
import json
from typing import AsyncGenerator
import structlog

from src.rag.prompt_builder import SYSTEM_PROMPT, build_prompt

log = structlog.get_logger()

# SYSTEM_PROMPT est désormais importé de src.rag.prompt_builder (source unique).
# Versioning du prompt (C.5) — bumpé à v2.0 : prompt factuel/concis/sans
# présentation. Le SHA est dérivé du texte ; loggé dans MLflow et exposé via
# /prompt/version.
PROMPT_VERSION = "v2.0"
PROMPT_SHA = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]

# Paramètres d'inférence Ollama — source unique pour generate/chat/stream.
# Température basse (factuel, anti-invention), repeat_penalty (anti-répétition),
# num_predict (concision), stop tokens (coupe la sur-génération).
INFERENCE_OPTIONS = {
    "temperature": 0.1,
    "top_p": 0.85,
    "repeat_penalty": 1.15,
    "num_predict": 256,
    "stop": ["<|eot_id|>", "\n\n\n"],
}


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
        log.info(
            "[LLM] init",
            model=model,
            prompt_version=PROMPT_VERSION,
            temperature=INFERENCE_OPTIONS["temperature"],
            num_predict=INFERENCE_OPTIONS["num_predict"],
        )

    def _build_prompt(self, context: str, question: str) -> str:
        # Délègue au builder unique (prompt_builder.build_prompt) — prompt
        # factuel/concis avec balises <contexte>/<question>.
        return build_prompt(context, question)

    def _build_chat_prompt(self, messages: list[dict], context: str) -> str:
        last = messages[-1]["content"] if messages else ""
        history = _format_history(messages)
        hist_block = f"\n<historique>\n{history}\n</historique>\n" if history else ""
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"<contexte>\n{context}\n</contexte>\n"
            f"{hist_block}\n"
            f"<question>\n{last}\n</question>\n\n"
            f"<Réponse (concise, factuelle, sans présentation)>"
        )

    async def generate(self, context: str, question: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": self._build_prompt(context, question),
                    "stream": False,
                    "options": INFERENCE_OPTIONS,
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
                    "options": INFERENCE_OPTIONS,
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
                    # Mêmes options que generate()/chat() (cohérence streaming).
                    "options": INFERENCE_OPTIONS,
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
