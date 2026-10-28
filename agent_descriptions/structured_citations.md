# Structured citation migration

Apply after creating `sql/create_citation_registry.sql`. This document is a
deployment instruction, not a claim that hosted agents have been changed.

## Retrieval contract

Update the policy retrieval tool/index to return the matching registry row's
`chunk_text`, `document_id`, `document_version`, `chunk_id`, `document_title`,
`page_start`, and `page_end`. Join any search index to the registry using the
same source path, page and exact chunk text; do not match on title alone.
Rebuild the index on document changes so versions match. If a managed agent
cannot expose these fields, keep its existing legacy Source-line contract
until a retrieval wrapper can provide them.

Keep registry and retrieval access scoped to the same approved shared policy
documents as the Flask workspace principal and Volume catalogs. This cache
does not implement per-employee document entitlements. Use separate registries
and app instances/identities when policy access differs.

## Add to the policy agent AND final Supervisor instructions

The following final-output contract replaces instructions requiring Source lines
for responses that use registry-enabled retrieval. Preserve all existing policy,
grounding, privacy, and employment-decision restrictions.

```text
For requests using registry-enabled retrieval, return exactly one JSON object:
{
  "answer": "The complete manager-facing answer in Markdown.",
  "citations": [
    {
      "document_id": "<exact retrieved document_id>",
      "document_version": "<exact retrieved document_version>",
      "chunk_id": "<exact retrieved chunk_id>",
      "document_title": "<exact retrieved document_title>",
      "page": 1
    }
  ]
}
Copy all identifiers, titles, and page numbers from approved retrieved passages.
Replace the example page with the actual retrieved page_start; never guess it.
Include only passages used to support the answer, up to ten citations.
Return citations: [] for answers containing no policy claims or document sources.
Policy claims require supporting citations. If evidence is missing, state the
limitation rather than providing unsupported policy guidance.
Do not put Source lines, internal paths, URLs, or routing information in answer.
The Supervisor must preserve citation objects unchanged and emit this same JSON
envelope in its final assistant message. Do not wrap it in prose or code fences.
For requests using legacy retrieval without registry IDs, preserve the existing
Markdown and Source-line output; never invent IDs to satisfy this contract.
```

Prefer constructing/preserving citation objects in retrieval/orchestration code
rather than relying on the model to reproduce metadata. This JSON is the final
assistant message's text inside the existing Responses API envelope. It is not
a replacement for the HTTP Responses API envelope itself.

## Enable Flask

Set these environment variables, then restart Flask/Gunicorn workers:

```dotenv
DATABRICKS_CITATION_REGISTRY_TABLE=workspace.default.app_citation_registry
CITATION_REGISTRY_TTL_SECONDS=60
CITATION_REGISTRY_TIMEOUT_SECONDS=10
```

The existing warehouse and approved Volume catalogs must be configured. The first
request starts background preload in parallel with inference; until preload has
finished, citations use a single batch query. Refresh runs every half TTL. Valid
cache hits need no request-path SQL. Failed refreshes never extend expired entries.
Registry warmup is limited to 10,000 metadata rows and rejects truncated SQL
results; oversized registries use batch misses instead of partial preload.

The view computes content-based versions across all document chunks. At scale,
materialize this result as part of policy ingestion and point Flask/retrieval at
that maintained table to avoid repeatedly hashing document contents.

To roll back, restore agent Markdown/Source-line output first, then clear
DATABRICKS_CITATION_REGISTRY_TABLE and restart workers. Structured citations with
no configured registry fail closed. The app's public JSON response and UI stay
unchanged. Metadata validation verifies source identity and location, not semantic
entailment of every claim. Live latency must be measured separately.
