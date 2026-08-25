from fastapi.testclient import TestClient

from app.main import app, get_knowledge_service, get_realtime_service


class FakeRealtimeService:
    async def create_client_secret(self, language: str) -> dict[str, str | int]:
        assert language == "da"
        return {
            "token": "ephemeral-test-token",
            "expires_at": 1_800_000_000,
            "calls_url": "https://example.openai.azure.com/openai/v1/realtime/calls",
        }


def override_realtime_service() -> FakeRealtimeService:
    return FakeRealtimeService()


class FakeKnowledgeService:
    async def upload_documents(self, documents):
        assert [document[0] for document in documents] == ["one.txt", "two.txt"]
        return {
            "documents": [
                {"document_id": "one", "filename": "one.txt"},
                {"document_id": "two", "filename": "two.txt"},
            ],
            "count": 2,
            "status": "indexing",
        }


def override_knowledge_service() -> FakeKnowledgeService:
    return FakeKnowledgeService()


def test_health_returns_correlation_id() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"x-correlation-id": "test-id"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-correlation-id"] == "test-id"


def test_create_realtime_session() -> None:
    app.dependency_overrides[get_realtime_service] = override_realtime_service
    try:
        with TestClient(app) as client:
            response = client.post("/api/realtime/session", json={"language": "da"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["token"] == "ephemeral-test-token"
    assert response.json()["expires_at"] == 1_800_000_000


def test_upload_multiple_documents() -> None:
    app.dependency_overrides[get_knowledge_service] = override_knowledge_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/knowledge/documents",
                files=[
                    ("file", ("one.txt", b"one", "text/plain")),
                    ("file", ("two.txt", b"two", "text/plain")),
                ],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["count"] == 2