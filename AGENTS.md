# Agent Instructions

This project was built with the microsoft-foundry skill. Before working on or answering questions about Foundry agents, read the microsoft-foundry skill first.

- Keep secrets out of source control and use `DefaultAzureCredential` for Azure data-plane access.
- Keep `gpt-realtime-1.5` and `text-embedding-3-large` deployment names configurable.
- Use the GA Realtime endpoints under `/openai/v1`; do not reintroduce preview endpoints.