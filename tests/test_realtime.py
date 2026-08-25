import json
from unittest.mock import AsyncMock

import httpx
import pytest
from azure.core.credentials import AccessToken

from app.config import Settings
from app.services.realtime import RealtimeService, RealtimeSessionError


@pytest.mark.asyncio
async def test_create_client_secret_uses_ga_endpoint_and_entra_token() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"value": "ephemeral", "expires_at": 1234})

    credential = AsyncMock()
    credential.get_token.return_value = AccessToken("entra-token", 9999)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = RealtimeService(Settings(), credential, client)
        result = await service.create_client_secret("en")

    assert captured_request is not None
    assert captured_request.url.path == "/openai/v1/realtime/client_secrets"
    assert captured_request.headers["authorization"] == "Bearer entra-token"
    payload = json.loads(captured_request.content)
    session = payload["session"]
    assert "MUST call this tool" in session["instructions"]
    assert session["tools"][0]["name"] == "search_knowledge_base"
    assert session["tool_choice"] == "auto"
    assert result["token"] == "ephemeral"
    assert result["calls_url"].endswith("/openai/v1/realtime/calls")


@pytest.mark.asyncio
async def test_create_client_secret_rejects_missing_secret() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    credential = AsyncMock()
    credential.get_token.return_value = AccessToken("entra-token", 9999)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = RealtimeService(Settings(), credential, client)
        with pytest.raises(RealtimeSessionError):
            await service.create_client_secret("auto")