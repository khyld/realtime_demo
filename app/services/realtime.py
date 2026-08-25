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
    " A knowledge base of the user's uploaded documents is available through "
    "search_knowledge_base. You MUST call this tool before answering any question that refers "
    "to the knowledge base, uploaded documents, or facts that could be specific to the user's "
    "organization, project, or documents. Never answer such a question from general knowledge "
    "or assumptions. After the tool returns, answer only from its sources and mention each used "
    "source title. If no sources are found, say that the knowledge base does not contain enough "
    "information. Do not call the tool for casual conversation or general knowledge questions."
)

KNOWLEDGE_TOOL = {
    "type": "function",
    "name": "search_knowledge_base",
    "description": (
        "Search the user's uploaded documents. This tool is required before answering questions "
        "about the knowledge base, uploaded files, or user-specific organizational/project facts."
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
                "audio": {"output": {"voice": self._settings.azure_openai_voice}},
                "tools": [KNOWLEDGE_TOOL],
                "tool_choice": "auto",
            }
        }

        try:
            response = await self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token.token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RealtimeSessionError("Azure Realtime session creation failed") from exc

        data = response.json()
        ephemeral_token = data.get("value")
        if not ephemeral_token:
            raise RealtimeSessionError("Azure Realtime response did not contain a client secret")

        return {
            "token": ephemeral_token,
            "expires_at": data.get("expires_at"),
            "calls_url": self._settings.realtime_calls_url,
        }