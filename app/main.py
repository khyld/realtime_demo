import logging
from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexerClient
from azure.storage.blob.aio import BlobServiceClient
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.knowledge import DocumentValidationError, KnowledgeService
from app.services.realtime import RealtimeService, RealtimeSessionError

logger = logging.getLogger(__name__)

app = FastAPI(title="Bilingual Realtime Lab", version="0.1.0")


class SessionRequest(BaseModel):
    language: Literal["auto", "da", "en"] = "auto"


class SessionResponse(BaseModel):
    token: str
    expires_at: int | None = None
    calls_url: str


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    language: Literal["auto", "da", "en"] = "auto"


class DeleteKnowledgeDocumentsRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)


async def get_realtime_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[RealtimeService]:
    credential = DefaultAzureCredential()
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            yield RealtimeService(settings, credential, client)
        finally:
            await credential.close()


async def get_knowledge_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[KnowledgeService]:
    if not settings.azure_search_endpoint or not settings.azure_storage_account_url:
        raise HTTPException(status_code=503, detail="Knowledge base is not configured")

    credential = DefaultAzureCredential()
    search_client = SearchClient(
        settings.azure_search_endpoint,
        settings.azure_search_index_name,
        credential,
    )
    indexer_client = SearchIndexerClient(settings.azure_search_endpoint, credential)
    blob_service_client = BlobServiceClient(settings.azure_storage_account_url, credential)
    container_client = blob_service_client.get_container_client(
        settings.azure_storage_container_name
    )
    try:
        yield KnowledgeService(
            container_client,
            search_client,
            indexer_client,
            settings.azure_search_indexer_name,
        )
    finally:
        await search_client.close()
        await indexer_client.close()
        await blob_service_client.close()
        await credential.close()


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", str(uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    return response


@app.exception_handler(RealtimeSessionError)
async def handle_realtime_error(request: Request, exc: RealtimeSessionError) -> JSONResponse:
    logger.warning(
        "Realtime session creation failed",
        extra={"correlation_id": request.state.correlation_id},
    )
    return JSONResponse(
        status_code=502,
        content={
            "detail": "Could not start the realtime session",
            "correlation_id": request.state.correlation_id,
        },
    )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/realtime/session", response_model=SessionResponse)
async def create_realtime_session(
    body: SessionRequest,
    service: Annotated[RealtimeService, Depends(get_realtime_service)],
) -> dict[str, str | int | None]:
    return await service.create_client_secret(body.language)


@app.get("/api/knowledge/documents")
async def list_knowledge_documents(
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> dict[str, object]:
    return await service.list_documents()


@app.post("/api/knowledge/documents", status_code=202)
async def upload_knowledge_documents(
    request: Request,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    files: Annotated[list[UploadFile], File(alias="file")],
) -> dict[str, object]:
    documents = [
        (file.filename, file.content_type, await file.read(20 * 1024 * 1024 + 1))
        for file in files
    ]
    try:
        return await service.upload_documents(documents)
    except DocumentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ClientAuthenticationError, HttpResponseError) as exc:
        logger.warning(
            "Knowledge-base upload failed while accessing Blob Storage",
            extra={"correlation_id": request.state.correlation_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "Upload kunne ikke godkendes mod Blob Storage. "
                "Kontrollér Azure-login og rollen Storage Blob Data Contributor."
            ),
        ) from exc


@app.get("/api/knowledge/indexing-status")
async def knowledge_indexing_status(
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> dict[str, object]:
    return await service.get_indexing_status()


@app.delete("/api/knowledge/documents")
async def delete_knowledge_documents(
    body: DeleteKnowledgeDocumentsRequest,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> dict[str, object]:
    return await service.delete_documents(body.document_ids)


@app.post("/api/knowledge/search")
async def search_knowledge(
    body: KnowledgeSearchRequest,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> dict[str, object]:
    return await service.search(body.query, body.language)


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")