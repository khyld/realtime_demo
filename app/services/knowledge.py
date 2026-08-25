import re
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from azure.search.documents.models import VectorizableTextQuery

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_BATCH = 10
ALLOWED_EXTENSIONS = {".docx", ".pdf", ".txt"}


class BlobClientProtocol(Protocol):
    async def upload_blob(self, data: bytes, *, overwrite: bool, content_settings: Any) -> Any: ...


class ContainerClientProtocol(Protocol):
    def get_blob_client(self, blob: str) -> BlobClientProtocol: ...


class SearchClientProtocol(Protocol):
    async def search(self, *args: Any, **kwargs: Any) -> Any: ...


class IndexerClientProtocol(Protocol):
    async def run_indexer(self, name: str) -> None: ...


class DocumentValidationError(ValueError):
    pass


class KnowledgeService:
    def __init__(
        self,
        container_client: ContainerClientProtocol,
        search_client: SearchClientProtocol,
        indexer_client: IndexerClientProtocol,
        indexer_name: str,
    ) -> None:
        self._container_client = container_client
        self._search_client = search_client
        self._indexer_client = indexer_client
        self._indexer_name = indexer_name

    async def upload_document(
        self,
        filename: str | None,
        content_type: str | None,
        content: bytes,
    ) -> dict[str, str]:
        result = await self.upload_documents([(filename, content_type, content)])
        return {**result["documents"][0], "status": result["status"]}

    async def upload_documents(
        self,
        documents: list[tuple[str | None, str | None, bytes]],
    ) -> dict[str, Any]:
        if not documents or len(documents) > MAX_DOCUMENT_BATCH:
            raise DocumentValidationError(
                f"Upload between 1 and {MAX_DOCUMENT_BATCH} documents at a time"
            )

        validated_documents = [
            (str(uuid4()), validate_document(filename, content), content_type, content)
            for filename, content_type, content in documents
        ]

        from azure.storage.blob import ContentSettings

        uploaded_documents = []
        for document_id, safe_filename, content_type, content in validated_documents:
            blob_client = self._container_client.get_blob_client(
                f"{document_id}/{safe_filename}"
            )
            await blob_client.upload_blob(
                content,
                overwrite=False,
                content_settings=ContentSettings(
                    content_type=content_type or "application/octet-stream",
                    content_disposition=f'inline; filename="{safe_filename}"',
                ),
            )
            uploaded_documents.append(
                {"document_id": document_id, "filename": safe_filename}
            )

        await self._indexer_client.run_indexer(self._indexer_name)
        return {
            "documents": uploaded_documents,
            "count": len(uploaded_documents),
            "status": "indexing",
        }

    async def search(self, query: str, language: str, top: int = 5) -> dict[str, Any]:
        vector_query = VectorizableTextQuery(
            text=query,
            k_nearest_neighbors=20,
            fields="content_vector",
        )
        results = await self._search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            query_type="semantic",
            semantic_configuration_name="knowledge-semantic-config",
            select=["document_id", "title", "content", "source_uri", "language"],
            top=max(top * 2, 10),
        )

        sources: list[dict[str, Any]] = []
        seen_documents: set[str] = set()
        async for result in results:
            document_id = str(result.get("document_id", ""))
            if not document_id or document_id in seen_documents:
                continue
            seen_documents.add(document_id)
            sources.append(
                {
                    "id": document_id,
                    "title": result.get("title") or "Untitled document",
                    "excerpt": compact_excerpt(str(result.get("content", ""))),
                    "source_uri": result.get("source_uri"),
                    "language": result.get("language"),
                    "score": result.get("@search.reranker_score", result.get("@search.score")),
                }
            )
            if len(sources) == top:
                break

        return {
            "found": bool(sources),
            "query": query,
            "message": None if sources else "No relevant knowledge-base sources were found.",
            "sources": sources,
        }


def validate_document(filename: str | None, content: bytes) -> str:
    if not filename:
        raise DocumentValidationError("The uploaded document must have a filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise DocumentValidationError("Only PDF, DOCX, and TXT documents are supported")
    if not content:
        raise DocumentValidationError("The uploaded document is empty")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentValidationError("The uploaded document exceeds the 20 MB limit")

    base_name = Path(filename).name
    stem = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(base_name).stem).strip(" ._")
    return f"{stem or 'document'}{suffix}"


def compact_excerpt(content: str, limit: int = 700) -> str:
    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"