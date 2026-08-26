import asyncio
from typing import Literal, Protocol

import httpx
from azure.core.credentials import AccessToken

from app.config import Settings

Language = Literal["auto", "da", "en"]


class AsyncTokenCredential(Protocol):
    async def get_token(self, *scopes: str) -> AccessToken: ...


class RealtimeSessionError(RuntimeError):
    pass


LANGUAGE_INSTRUCTIONS: dict[Language, str] = {
    "auto": (
        "Speak naturally in the user's current language. Support Danish and English, and switch "
        "only when the user switches."
    ),
    "da": (
        "Tal naturligt dansk. Svar på dansk, medmindre brugeren udtrykkeligt beder om engelsk."
    ),
    "en": (
        "Speak natural English. Reply in English unless the user explicitly asks for Danish."
    ),
}

KNOWLEDGE_INSTRUCTIONS = (
    " You are a knowledge-base-only assistant working for Margie's travel. You love that "
    "company and are very helpful. For EVERY user question, you MUST call "
    "`search_knowledge_base` before answering. Use only facts supported by the returned sources; "
    "do not use general knowledge, assumptions, or information from the conversation as evidence. "
    "Mention each source title used in the answer. If no sources are found, say that the knowledge "
    "base does not contain enough information and do not attempt an answer."
)

KNOWLEDGE_TOOL = {
    "type": "function",
    "name": "search_knowledge_base",
    "description": (
        "Search the user's uploaded documents. This tool is required before answering every user "
        "question because answers must be based only on the knowledge base."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "A concise semantic search query."},
            "language": {
                "type": "string",
                "enum": ["auto", "da", "en"],
                "description": "The language used by the speaker.",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


class RealtimeService:
    def __init__(
        self,
        settings: Settings,
        credential: AsyncTokenCredential,
        client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._credential = credential
        self._client = client

    async def create_client_secret(self, language: Language) -> dict[str, str | int | None]:
        token = await self._credential.get_token("https://ai.azure.com/.default")
        url = (
            f"{self._settings.azure_openai_endpoint}"
            "/openai/v1/realtime/client_secrets"
        )
        payload = {
            "session": {
                "type": "realtime",
                "model": self._settings.azure_openai_realtime_deployment,
                "instructions": LANGUAGE_INSTRUCTIONS[language] + KNOWLEDGE_INSTRUCTIONS,
                "audio": {
                    "input": {
                        "transcription": {
                            "model": self._settings.azure_openai_transcription_deployment
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            "silence_duration_ms": 300,
                            "create_response": True,
                            "interrupt_response": True,
                        },
                    },
                    "output": {"voice": self._settings.azure_openai_voice},
                },
                "tools": [KNOWLEDGE_TOOL],
                "tool_choice": "auto",
            }
        }

        response: httpx.Response | None = None
        for attempt in range(3):
            try:
                response = await self._client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token.token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code not in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                    break
                if attempt == 2:
                    response.raise_for_status()
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise RealtimeSessionError(
                        "Azure Realtime session creation failed"
                    ) from exc
            except httpx.HTTPStatusError as exc:
                raise RealtimeSessionError("Azure Realtime session creation failed") from exc

            await asyncio.sleep(0.5 * (attempt + 1))

        if response is None:
            raise RealtimeSessionError("Azure Realtime session creation failed")

        data = response.json()
        ephemeral_token = data.get("value")
        if not ephemeral_token:
            raise RealtimeSessionError("Azure Realtime response did not contain a client secret")

        return {
            "token": ephemeral_token,
            "expires_at": data.get("expires_at"),
            "calls_url": self._settings.realtime_calls_url,
        }