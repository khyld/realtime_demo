from unittest.mock import AsyncMock, Mock

import pytest

from app.services.knowledge import (
    DocumentValidationError,
    KnowledgeService,
    compact_excerpt,
    validate_document,
)


class AsyncResults:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class AsyncBlobs:
    def __init__(self, items: list[Mock]) -> None:
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def test_validate_document_sanitizes_filename() -> None:
    assert validate_document("../Møde referat?.PDF", b"content") == "M_de referat.pdf"


def test_validate_document_rejects_unsupported_type() -> None:
    with pytest.raises(DocumentValidationError, match="Only PDF"):
        validate_document("payload.exe", b"content")


@pytest.mark.asyncio
async def test_upload_documents_starts_indexer_once_for_batch() -> None:
    blob_client = Mock(upload_blob=AsyncMock())
    container_client = Mock()
    container_client.get_blob_client.return_value = blob_client
    indexer_client = AsyncMock()
    service = KnowledgeService(container_client, AsyncMock(), indexer_client, "indexer")

    result = await service.upload_documents(
        [
            ("guide.pdf", "application/pdf", b"guide"),
            ("notes.txt", "text/plain", b"notes"),
        ]
    )

    assert result["count"] == 2
    assert [document["filename"] for document in result["documents"]] == [
        "guide.pdf",
        "notes.txt",
    ]
    assert blob_client.upload_blob.await_count == 2
    indexer_client.run_indexer.assert_awaited_once_with("indexer")


@pytest.mark.asyncio
async def test_list_documents_returns_names_and_ids() -> None:
    alpha = Mock()
    alpha.name = "alpha/guide.pdf"
    beta = Mock()
    beta.name = "beta/notes.txt"
    container_client = Mock()
    container_client.list_blobs.return_value = AsyncBlobs([alpha, beta])
    service = KnowledgeService(container_client, AsyncMock(), AsyncMock(), "indexer")

    result = await service.list_documents()

    assert result["count"] == 2
    assert result["documents"] == [
        {"document_id": "alpha", "filename": "guide.pdf"},
        {"document_id": "beta", "filename": "notes.txt"},
    ]


@pytest.mark.asyncio
async def test_delete_documents_removes_selected_blobs_and_reindexes() -> None:
    blob_client_one = Mock(delete_blob=AsyncMock())
    blob_client_two = Mock(delete_blob=AsyncMock())
    blob_one = Mock()
    blob_one.name = "alpha/guide.pdf"
    blob_two = Mock()
    blob_two.name = "beta/notes.txt"
    container_client = Mock()
    container_client.get_blob_client.side_effect = [blob_client_one, blob_client_two]
    container_client.list_blobs.return_value = AsyncBlobs([blob_one, blob_two])
    indexer_client = AsyncMock()
    service = KnowledgeService(container_client, AsyncMock(), indexer_client, "indexer")

    result = await service.delete_documents(["alpha", "beta"])

    assert result["deleted_count"] == 2
    assert blob_client_one.delete_blob.await_count == 1
    assert blob_client_two.delete_blob.await_count == 1
    indexer_client.run_indexer.assert_awaited_once_with("indexer")


@pytest.mark.asyncio
async def test_search_deduplicates_documents_and_limits_excerpt() -> None:
    search_client = AsyncMock()
    search_client.search.return_value = AsyncResults(
        [
            {"document_id": "one", "title": "Guide", "content": "A " * 500},
            {"document_id": "one", "title": "Guide", "content": "duplicate"},
            {"document_id": "two", "title": "FAQ", "content": "Short answer"},
        ]
    )
    service = KnowledgeService(Mock(), search_client, AsyncMock(), "indexer")

    result = await service.search("Hvad er politikken?", "da")

    assert result["found"] is True
    assert [source["id"] for source in result["sources"]] == ["one", "two"]
    assert len(result["sources"][0]["excerpt"]) <= 700
    assert "filter" not in search_client.search.call_args.kwargs


@pytest.mark.asyncio
async def test_search_returns_explicit_no_result() -> None:
    search_client = AsyncMock()
    search_client.search.return_value = AsyncResults([])
    service = KnowledgeService(Mock(), search_client, AsyncMock(), "indexer")

    result = await service.search("missing", "auto")

    assert result == {
        "found": False,
        "query": "missing",
        "message": "No relevant knowledge-base sources were found.",
        "sources": [],
    }


def test_compact_excerpt_normalizes_whitespace() -> None:
    assert compact_excerpt("one\n\n two\tthree") == "one two three"