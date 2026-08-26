import json
from unittest.mock import AsyncMock

import httpx
import pytest
from azure.core.credentials import AccessToken

from app.config import Settings
from app.services.realtime import RealtimeService, RealtimeSessionError

TEST_SETTINGS = Settings(azure_openai_resource="test-foundry-resource")


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
        service = RealtimeService(TEST_SETTINGS, credential, client)
        result = await service.create_client_secret("en")

    assert captured_request is not None
    assert captured_request.url.path == "/openai/v1/realtime/client_secrets"
    assert captured_request.headers["authorization"] == "Bearer entra-token"
    payload = json.loads(captured_request.content)
    session = payload["session"]
    assert "For EVERY user question, you MUST call" in session["instructions"]
    assert session["audio"]["input"]["transcription"]["model"] == "gpt-4o-mini-transcribe"
    assert session["audio"]["input"]["turn_detection"] == {
        "type": "server_vad",
        "create_response": True,
        "interrupt_response": True,
    }
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
        service = RealtimeService(TEST_SETTINGS, credential, client)
        with pytest.raises(RealtimeSessionError):
            await service.create_client_secret("auto")


@pytest.mark.asyncio
async def test_create_client_secret_retries_transient_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("Temporary connection failure", request=request)
        return httpx.Response(200, json={"value": "ephemeral", "expires_at": 1234})

    sleep = AsyncMock()
    monkeypatch.setattr("app.services.realtime.asyncio.sleep", sleep)
    credential = AsyncMock()
    credential.get_token.return_value = AccessToken("entra-token", 9999)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = RealtimeService(TEST_SETTINGS, credential, client)
        result = await service.create_client_secret("da")

    assert attempts == 2
    sleep.assert_awaited_once_with(0.5)
    assert result["token"] == "ephemeral"