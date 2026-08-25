from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_openai_resource: str = "proj-ai103-resource"
    azure_openai_realtime_deployment: str = "gpt-realtime-1.5"
    azure_openai_voice: Literal[
        "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"
    ] = "coral"
    azure_search_endpoint: str | None = None
    azure_search_index_name: str = "knowledge-chunks"
    azure_search_indexer_name: str = "knowledge-indexer"
    azure_storage_account_url: str | None = None
    azure_storage_container_name: str = "knowledge"
    log_level: str = "INFO"

    @computed_field
    @property
    def azure_openai_endpoint(self) -> str:
        return f"https://{self.azure_openai_resource}.openai.azure.com"

    @computed_field
    @property
    def realtime_calls_url(self) -> str:
        return f"{self.azure_openai_endpoint}/openai/v1/realtime/calls"


@lru_cache
def get_settings() -> Settings:
    return Settings()