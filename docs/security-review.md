# Security Review

Review date: 2026-08-25  
Scope: Application code, browser client, tests, container image, Azure configuration, and Bicep infrastructure.

## Summary

The project has a sound baseline for a learning application: Azure data-plane access uses managed identity and `DefaultAzureCredential`, the container runs as a non-root user, Blob public access is disabled, Azure AI Search local authentication is disabled, and no hardcoded secrets were found.

The application is not production-ready yet. The high-priority findings concern reliable deletion from Azure AI Search, fail-open authentication configuration, authorization for shared knowledge-base operations, and upload resource exhaustion.

## Findings

| ID | Priority | Finding | Status |
|---|---|---|---|
| SEC-001 | High | Deleted documents can remain searchable | Open |
| SEC-002 | High | Azure authentication configuration fails open | Open |
| SEC-003 | High | Knowledge-base operations lack user/role authorization | Open |
| SEC-004 | High | Upload batches can exhaust container memory | Open |
| SEC-005 | Medium | Azure Storage Shared Key authorization remains enabled | Open |
| SEC-006 | Medium | Browser supply-chain and response-header protections are missing | Open |
| SEC-007 | Medium | Retrieved documents are not treated explicitly as untrusted input | Open |
| SEC-008 | Low | Dependency and container builds are not reproducible | Open |

### SEC-001: Deleted documents can remain searchable

The delete operation removes blobs and starts the indexer, but it does not delete the projected chunks from the Search index. The index uses one-to-many index projections, for which Azure AI Search deletion-detection policies do not apply.

Evidence:

- [`KnowledgeService.delete_documents`](../app/services/knowledge.py) deletes blobs and reruns the indexer.
- [`configure_search.py`](../scripts/configure_search.py) configures `indexProjections` without an explicit index deletion path.

Impact: A document removed from the UI and Blob Storage can remain retrievable from the knowledge base.

Recommended remediation:

1. Find all Search documents whose `document_id` belongs to a deleted source document.
2. Submit explicit delete actions for their `chunk_id` keys.
3. Define retry and partial-failure behavior across Search and Blob Storage.
4. Add an integration test proving that deleted content is no longer searchable.

### SEC-002: Azure authentication configuration fails open

`entraClientId` and `entraClientSecret` default to empty values. The Container Apps Easy Auth resource is created only when both values are non-empty. A missing or partially configured deployment therefore exposes the application without authentication instead of failing provisioning.

Evidence:

- [`main.bicep`](../infra/main.bicep) defines empty defaults and conditionally creates `webAuth`.
- [`main.bicepparam`](../infra/main.bicepparam) also defaults both environment values to empty strings.

Recommended remediation:

1. Make Entra configuration mandatory for deployed environments.
2. Add a Bicep assertion that rejects missing or partially configured values.
3. Add a deployment validation that verifies the auth configuration exists and anonymous API access is rejected.

### SEC-003: Knowledge-base operations lack user/role authorization

Easy Auth authenticates users when configured, but the application does not use identity claims or roles. Every accepted user can list, search, upload, and delete documents in the same shared container and index.

Evidence:

- Knowledge endpoints in [`app/main.py`](../app/main.py) have no role or ownership checks.
- Blob names and Search documents contain no user or tenant partition.

Impact: In a multi-user deployment, one authenticated user can access or delete another user's documents.

Recommended remediation:

- If this remains a deliberately single-user/shared lab, document that boundary and restrict Entra assignment to approved users.
- Otherwise, partition documents by a stable user or tenant claim and require an administrator role for destructive operations.
- Add authorization tests for anonymous, regular-user, owner, and administrator cases.

### SEC-004: Upload batches can exhaust container memory

The API reads up to ten files of 20 MB each into a list before validation and upload. A single request can therefore retain approximately 200 MB of file data. The Container App has 1 GiB of memory and permits 20 concurrent HTTP requests.

Evidence:

- [`app/main.py`](../app/main.py) reads each upload into bytes before calling the service.
- [`knowledge.py`](../app/services/knowledge.py) permits ten documents of up to 20 MB each.
- [`main.bicep`](../infra/main.bicep) configures 1 GiB memory and 20 concurrent requests.

Recommended remediation:

1. Enforce a conservative total request-size limit at ingress and application level.
2. Stream or spool one validated document at a time instead of retaining the complete batch.
3. Add per-user rate limits for upload, indexing, search, and realtime-session creation.
4. Add tests for per-file, batch, and concurrent-request limits.

### SEC-005: Azure Storage Shared Key authorization remains enabled

The Storage account sets `defaultToOAuthAuthentication`, but this only selects the preferred authorization method. Shared Key remains allowed unless `allowSharedKeyAccess` is explicitly set to `false`.

Evidence: The Storage resource in [`main.bicep`](../infra/main.bicep) does not define `allowSharedKeyAccess`.

Recommended remediation: Add `allowSharedKeyAccess: false`, validate that Search's managed identity integration still works, and retain the existing RBAC-based access.

### SEC-006: Browser supply-chain and response-header protections are missing

The browser loads Lucide from unpkg without Subresource Integrity. FastAPI responses do not include a Content Security Policy, HSTS, clickjacking protection, MIME-sniffing protection, a referrer policy, or a permissions policy.

Evidence:

- [`index.html`](../app/static/index.html) loads the external script.
- The middleware in [`app/main.py`](../app/main.py) adds only a correlation ID.

Recommended remediation: Self-host the pinned Lucide asset and add tested security headers. Keep microphone access constrained to the application origin through `Permissions-Policy`.

### SEC-007: Retrieved documents are not treated explicitly as untrusted input

The model is instructed to ground answers in retrieved sources, but it is not told explicitly to treat instructions found inside uploaded documents as untrusted data. A malicious document could attempt indirect prompt injection.

Evidence: [`KNOWLEDGE_INSTRUCTIONS`](../app/services/realtime.py) defines grounding rules without an instruction/data boundary.

Recommended remediation: Strengthen the higher-priority instructions, limit tool output to necessary fields, and add adversarial evaluations containing document-based instruction overrides and data-exfiltration requests.

### SEC-008: Dependency and container builds are not reproducible

Python dependencies use minimum versions without a lock file, and the Docker base image uses a mutable tag. Separate builds can therefore resolve different artifacts.

Evidence:

- [`pyproject.toml`](../pyproject.toml) contains lower-bound dependency constraints.
- [`Dockerfile`](../Dockerfile) uses `python:3.12-slim` without a digest.

Recommended remediation: Generate and maintain a reviewed lock file with hashes, pin the runtime base image by digest, and automate dependency and container-image vulnerability scanning.

## Existing Strengths

- Azure SDK access uses `DefaultAzureCredential` and managed identities.
- Secrets are excluded from source control and the Entra secret is a secure Bicep parameter.
- The runtime container uses a non-root system user.
- Container Apps ingress rejects insecure external traffic.
- Blob public access and ACR admin access are disabled.
- Azure AI Search local key authentication is disabled.
- Dynamic transcript, filename, source, and event text is rendered with `textContent`.
- Upload filenames, extensions, count, and per-file size are validated.

## Verification Performed

- `pytest`: 13 tests passed; one Starlette test-client deprecation warning.
- `ruff`: all checks passed.
- `pip check`: no broken requirements.
- `pip-audit`: no known vulnerabilities in application dependencies; the local virtual environment's `pip` 25.0.1 reported advisories and should be upgraded.
- Bicep template and parameter files compiled successfully when required deployment context was supplied.
- Runtime header inspection confirmed that the listed security headers are absent.
- Static secret scan found no embedded credentials in tracked project files.

## Remediation Order

1. SEC-001: Ensure deletion removes Search chunks.
2. SEC-002: Make deployed authentication fail closed.
3. SEC-003: Decide and enforce the single-user or multi-user authorization model.
4. SEC-004: Bound request memory and request rates.
5. SEC-005 and SEC-006: Harden Azure Storage and browser responses.
6. SEC-007: Add prompt-injection mitigations and evaluations.
7. SEC-008: Make builds reproducible and continuously scanned.

Update each finding's status to `In progress`, `Mitigated`, `Accepted`, or `Closed`, and record the validating test or deployment check when its status changes.