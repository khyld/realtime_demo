import os
import time
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential

API_VERSION = "2026-04-01"
SEARCH_SCOPE = "https://search.azure.com/.default"


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.rstrip("/")


def put_search_object(
    client: httpx.Client,
    endpoint: str,
    object_type: str,
    name: str,
    payload: dict[str, Any],
) -> None:
    url = f"{endpoint}/{object_type}/{name}?api-version={API_VERSION}"
    for attempt in range(1, 7):
        response = client.put(url, json=payload)
        if response.is_success:
            print(f"Configured {object_type}/{name}")
            return
        if response.status_code not in {403, 409, 429, 500, 503} or attempt == 6:
            raise RuntimeError(
                f"Failed to configure {object_type}/{name}: "
                f"{response.status_code} {response.text}"
            )
        time.sleep(attempt * 5)


def main() -> None:
    search_endpoint = required("AZURE_SEARCH_ENDPOINT")
    storage_resource_id = required("AZURE_STORAGE_ACCOUNT_ID")
    container_name = required("AZURE_STORAGE_CONTAINER_NAME")
    openai_endpoint = required("AZURE_OPENAI_ENDPOINT")
    ai_services_endpoint = required("AZURE_AI_SERVICES_ENDPOINT")
    embedding_deployment = required("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    index_name = required("AZURE_SEARCH_INDEX_NAME")
    indexer_name = required("AZURE_SEARCH_INDEXER_NAME")

    credential = DefaultAzureCredential()
    token = credential.get_token(SEARCH_SCOPE).token
    client = httpx.Client(
        timeout=60,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )

    index = {
        "name": index_name,
        "fields": [
            {
                "name": "chunk_id",
                "type": "Edm.String",
                "key": True,
                "searchable": True,
                "filterable": True,
                "analyzer": "keyword",
            },
            {"name": "parent_id", "type": "Edm.String", "filterable": True},
            {"name": "document_id", "type": "Edm.String", "filterable": True},
            {"name": "title", "type": "Edm.String", "searchable": True, "filterable": True},
            {"name": "content", "type": "Edm.String", "searchable": True},
            {"name": "source_uri", "type": "Edm.String", "filterable": True},
            {"name": "language", "type": "Edm.String", "filterable": True},
            {
                "name": "content_vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "dimensions": 3072,
                "vectorSearchProfile": "knowledge-vector-profile",
            },
        ],
        "vectorSearch": {
            "algorithms": [
                {"name": "knowledge-hnsw", "kind": "hnsw", "hnswParameters": {"metric": "cosine"}}
            ],
            "profiles": [
                {
                    "name": "knowledge-vector-profile",
                    "algorithm": "knowledge-hnsw",
                    "vectorizer": "knowledge-vectorizer",
                }
            ],
            "vectorizers": [
                {
                    "name": "knowledge-vectorizer",
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": openai_endpoint,
                        "deploymentId": embedding_deployment,
                        "modelName": "text-embedding-3-large",
                    },
                }
            ],
        },
        "semantic": {
            "configurations": [
                {
                    "name": "knowledge-semantic-config",
                    "prioritizedFields": {
                        "titleField": {"fieldName": "title"},
                        "prioritizedContentFields": [{"fieldName": "content"}],
                    },
                }
            ]
        },
    }

    data_source = {
        "name": "knowledge-blob-source",
        "type": "azureblob",
        "credentials": {"connectionString": f"ResourceId={storage_resource_id};"},
        "container": {"name": container_name},
    }

    skillset = {
        "name": "knowledge-skillset",
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
                "name": "split-content",
                "context": "/document",
                "textSplitMode": "pages",
                "maximumPageLength": 2000,
                "pageOverlapLength": 300,
                "inputs": [{"name": "text", "source": "/document/content"}],
                "outputs": [{"name": "textItems", "targetName": "pages"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.LanguageDetectionSkill",
                "name": "detect-language",
                "context": "/document/pages/*",
                "inputs": [{"name": "text", "source": "/document/pages/*"}],
                "outputs": [{"name": "languageCode", "targetName": "language"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embed-content",
                "context": "/document/pages/*",
                "resourceUri": openai_endpoint,
                "deploymentId": embedding_deployment,
                "modelName": "text-embedding-3-large",
                "dimensions": 3072,
                "inputs": [{"name": "text", "source": "/document/pages/*"}],
                "outputs": [{"name": "embedding", "targetName": "embedding"}],
            },
        ],
        "cognitiveServices": {
            "@odata.type": "#Microsoft.Azure.Search.AIServicesByIdentity",
            "subdomainUrl": ai_services_endpoint,
        },
        "indexProjections": {
            "selectors": [
                {
                    "targetIndexName": index_name,
                    "parentKeyFieldName": "parent_id",
                    "sourceContext": "/document/pages/*",
                    "mappings": [
                        {"name": "document_id", "source": "/document/metadata_storage_path"},
                        {"name": "title", "source": "/document/metadata_storage_name"},
                        {"name": "content", "source": "/document/pages/*"},
                        {"name": "content_vector", "source": "/document/pages/*/embedding"},
                        {"name": "source_uri", "source": "/document/metadata_storage_path"},
                        {"name": "language", "source": "/document/pages/*/language"},
                    ],
                }
            ],
            "parameters": {"projectionMode": "skipIndexingParentDocuments"},
        },
    }

    indexer = {
        "name": indexer_name,
        "dataSourceName": data_source["name"],
        "targetIndexName": index_name,
        "skillsetName": skillset["name"],
        "schedule": {"interval": "PT5M"},
        "parameters": {
            "batchSize": 10,
            "configuration": {
                "dataToExtract": "contentAndMetadata",
                "parsingMode": "default",
                "failOnUnsupportedContentType": True,
                "failOnUnprocessableDocument": False,
            },
        },
    }

    try:
        put_search_object(client, search_endpoint, "indexes", index_name, index)
        put_search_object(client, search_endpoint, "datasources", data_source["name"], data_source)
        put_search_object(client, search_endpoint, "skillsets", skillset["name"], skillset)
        put_search_object(client, search_endpoint, "indexers", indexer_name, indexer)
    finally:
        client.close()


if __name__ == "__main__":
    main()