# Mariner GenAI DBX

Internal Flask chat application for the Mariner Databricks multi-agent employee-assistance system. The application sends employee questions to a Databricks Supervisor, renders Markdown tables and supported bar charts, resolves approved citations, and provides an in-app PDF document reader.

This repository is a test/prototype application. Conversation state is process-local, guardrails are regex-based, and the readiness endpoint does not perform a live Supervisor invocation.

## What the application does

- Serves the ASK MARINER chat interface.
- Sends ordinary questions to the Databricks Supervisor, with an optional POC performance workflow described below.
- Supports explicit user-directed routes:
  - `/policy` → Branch Operations (`mariner-policy-assistant`)
  - `/handbook` → Employee Handbook (`mariner-handbook-assistant`)
  - `/benefits` → Employee Benefits
  - `/performance` → Employee Performance
  - `/benfits` remains as a compatibility alias for `/benefits`.
- Keeps bounded conversation history in memory and sends it explicitly because the serving endpoint is treated as stateless.
- Runs explicit slash commands without prior conversation history so an earlier domain cannot bias the selected specialist. The completed turn is still saved in the current conversation.
- Adds a structured format instruction when the user explicitly requests a table, chart, graph, plot, or visualization.
- Renders Markdown, tables, and validated `mariner-chart` bar-chart blocks in the browser.
- Resolves agent citations against approved Databricks SQL chunk tables.
- Displays resolved citations separately from the answer and opens approved PDFs in the document reader at the resolved page when available.
- Provides allowlisted PDF browsing and filename search across configured Unity Catalog Volumes.
- Records best-effort chat analytics in a configured Databricks table.
- Emits structured JSON operational logs to stdout.

## Request flow

1. Flask validates the JSON request, message length, and conversation ID. Password-mode authentication is enforced before protected routes are dispatched.
2. Input guardrails inspect the message.
3. The route resolves the local or forwarded user identity and rejects unauthenticated requests.
4. Ordinary questions are forwarded unchanged to the Supervisor unless the optional POC performance workflow handles them. Explicit slash commands are converted to authoritative specialist-routing instructions.
5. The app sends bounded conversation history for ordinary follow-up questions.
6. The Supervisor may call its configured specialist agents. Only allowlisted approval requests are approved by the Flask transport, with a maximum of five approval rounds.
7. The app selects the final Supervisor message and records specialist names reported in the response.
8. Source labels are extracted from the final message. If the final message omits them, the app searches the grounded specialist messages in the complete Databricks response.
9. Source labels are resolved through parameterized Databricks SQL queries.
10. Output guardrails mask or replace unsafe output.
11. The filtered answer and safe sources are saved to in-memory history, queued for best-effort analytics, and returned to the browser.

### Flask latency diagnostics

The browser uses `POST /api/v1/chat/stream` for progressive delivery. After the
Supervisor completes, Flask applies output guardrails and sends the answer with
"Waiting on citations… Sources are not yet verified." Citation lookup runs next;
validated source links are attached to that same message. Verification failures
leave a visible warning, and failed/unverified turns are not saved to history.
The stream does not expose raw model tokens or intermediate tool messages.
Agent generation time remains unchanged; this removes the wait for citations
before displaying the completed, checked answer.

The existing `POST /api/v1/chat` API still waits for validated citations and
returns its original JSON response. Compare completed answers, including sources,
when measuring the full response-time target.

Streaming events are `status`, `answer`, `sources`, and `done`, or `error`.
Validation/authentication failures before streaming remain normal JSON HTTP
errors. Once streaming starts, errors use an `error` event over HTTP 200. EOF
without `done` is an incomplete response, never a successful completion.
The route sets `X-Accel-Buffering: no` and private/no-store cache headers. Disable
response buffering on any reverse proxy and allow sufficient idle time for
Databricks generation; proxy-specific settings must be checked in deployment.

- Citation document rows are cached in each resolver for 60 seconds, with a maximum
  of 128 labels. Page selection runs separately for every answer. Employee data,
  generated answers, and signed URLs are not cached. Document changes or permission
  revocations can take up to 60 seconds to appear in citation lookups; restarting
  workers clears the cache. Source downloads still enforce the existing checks.
- Databricks analytics uses a lazy background thread per worker and a queue of at
  most 256 pending events. SQL submission no longer blocks chat responses. Events
  are best effort: queue overflow, SQL failures, and process exit can lose events.
- INFO logs report `inference_ms` (including worker approval continuations) and
  `citations_ms`. HTTP completion logs report total Flask duration and request ID.
  JSON responses include `Server-Timing: app;dur=...`. Streams report
  `app_headers` for header preparation, then log full duration when closed.
- Flask duration starts when the worker receives a request; proxy or Gunicorn
  queueing and browser rendering require separate end-to-end measurement.

These changes remove avoidable application waits but do not establish a
30-second response guarantee. Validate the six performance questions against the
live application after deployment.

### Optional structured citations

The app also accepts a final assistant message containing a JSON object with
`answer` and `citations`. Registry-backed citations include `document_id`,
`document_version`, `chunk_id`, `document_title`, and an integer `page`.
The public chat response remains unchanged; the UI still receives plain answer
text and validated `Source` objects.

The transport explicitly allows the read-only tool
`endpoint-perf-policy-citations-dev` and can continue its MCP approval requests.
Restart Flask/Gunicorn after updating this allowlist. Other unrecognized tools
remain blocked; a different endpoint name requires its own reviewed entry.

Follow [the deployment instructions](agent_descriptions/structured_citations.md)
to create [the registry view](sql/create_citation_registry.sql), update retrieval
and Supervisor output, and enable `DATABRICKS_CITATION_REGISTRY_TABLE`.
The feature is disabled by default. `CITATION_REGISTRY_TTL_SECONDS` defaults to
60 (allowed 1–3600); `CITATION_REGISTRY_TIMEOUT_SECONDS` defaults to 10 (1–30).

Registry preload and refresh start lazily in a background thread alongside the
first inference request. Cached references avoid request-path SQL; all cache
misses in one answer use a single parameterized query. Every reference must
match an approved document version, chunk, title, page range, and Volume root.
Malformed structured responses are rejected before any draft is displayed.
Invalid references fail validation; the progressive UI marks the draft unverified
and does not save it. The JSON endpoint returns a citation error without an answer.
Legacy Markdown/Source-line responses continue through the existing resolver.

Metadata caches are local to each configured workspace principal and approved
Volume set, expire after the configured TTL, and are limited to shared policy
documents. They do not grant per-user access or verify claim-to-passage entailment.
Document/permission changes can take up to the TTL to be reflected. See the
deployment instructions for access boundaries, cache limits, and rollback.

## Application-layer guardrails

These application controls run in Flask before and after the Supervisor call, independently of controls configured in Databricks.

### Input controls

- Rejects non-JSON requests, empty messages, invalid conversation UUIDs, requests over 16 KiB, and messages over `MAX_MESSAGE_CHARACTERS`.
- Blocks recognized prompt-injection and hidden-prompt extraction attempts.
- Blocks requests to generate Social Security numbers, payment-card numbers, passwords, or account credentials.
- Blocks recognized hateful, threatening, or directly abusive requests.
- Blocks explicit off-topic patterns such as coding requests, creative-writing requests, weather, sports scores, stock prices, cryptocurrency, recipes, and basic general-knowledge lookups.
- Returns a crisis-support response for recognized self-harm or suicide-risk input without calling the Supervisor.
- Does **not** use the supported-domain vocabulary as an exhaustive allowlist. Ambiguous requests, including unfamiliar employee topics, are forwarded to the Supervisor for classification.
- Logs only the guardrail category and request ID when an input is intercepted; it does not place the blocked text in the operational log message.

These controls are pattern-based and are not a substitute for a dedicated moderation service, authorization policy, or human review.

### Output controls

- Masks recognized Social Security numbers, phone numbers, account/routing numbers, and payment-card numbers.
- Masks external email addresses and Mariner addresses whose local part contains a dot, such as `name.lastname@marinerfinance.com`.
- Allows a `marinerfinance.com` address whose local part contains no dot, such as `travel@marinerfinance.com`, so approved operational contacts can remain usable.
- Replaces responses that expose recognized internal endpoint, model, agent-architecture, tool, API-path, or service-principal details.
- Replaces responses that make recognized binding termination, promotion, demotion, suspension, compensation, salary, bonus, or disciplinary decisions.
- Replaces hateful output and unsafe self-harm instructions. Unsafe self-harm output is replaced with the crisis-support response.
- Removes sources when the entire answer is replaced by an output guardrail.
- Applies filtering before conversation persistence and Databricks analytics recording.

Guardrail patterns and user-facing fallback messages are maintained together near the top of `src/mariner_genai_dbx/web.py`.

## Supervisor and conversation behavior

The active dependency wiring imports the Databricks client from
`supervisor_service.py`. It calls the configured Databricks serving endpoint
through the streaming Responses API and treats that endpoint as stateless.
The OAuth application used by `DATABRICKS_CLIENT_ID` must allow the
`model-serving` scope. This is required because the Supervisor invokes its
specialists as nested serving-endpoint tools; `model-serving-inference` alone
can reach the Supervisor but cannot authorize those worker calls.

Conversation history is:

- Stored in memory only.
- Scoped by user ID and conversation UUID.
- Limited by `CHAT_HISTORY_LIMIT`.
- Expired after `CHAT_SESSION_TTL_SECONDS`.
- Lost when the process restarts.
- Not shared across multiple Gunicorn workers.

Because production Gunicorn defaults to two workers, this in-memory store is suitable only for the current prototype. A shared persistence layer is required for reliable multi-worker or multi-instance conversation continuity.

## Citations and approved sources

The citation resolver queries four approved chunk tables:

| Domain | Table |
| --- | --- |
| Branch Operations | `workspace.default.branch_operations_chunks` |
| Employee Handbook | `workspace.default.employee_handbook_chunks` |
| Employee Benefits | `workspace.default.benefits_chunks` |
| Employee Performance Policy | `workspace.performance_test.app_policy_chunks` |

The first three tables use the standard `document_title`, `volume_path`, `page_start`, and `chunk_text` columns. The performance table is configured to use `document_name`, `source_volume_path`, `page_start`, and `chunk_text`.

Citation behavior:

- SQL uses bound parameters rather than interpolating agent-provided labels.
- Matching normalizes case, `.pdf`, year/version text, underscores, common separators, parentheses, policy suffixes, and section text surrounding a document title.
- Configured aliases map known agent labels to canonical document names, including Branch Operations record-retention and Employee Performance policy variants.
- The app recovers citations from grounded specialist messages when the Supervisor final message omits a source line.
- Canonical Handbook and Performance document fallbacks are used when those identified specialists omit or vary their source label.
- When a document has chunks on multiple pages, the page is selected by meaningful-token overlap between the Supervisor answer and chunk text. The page may be omitted when support is ambiguous.
- Model-emitted `Source:` lines are removed from the displayed answer after resolution because the UI renders a separate Sources list.
- If source labels do not resolve to an approved document, the JSON route returns `CITATIONS_UNAVAILABLE`. The progressive route marks its already displayed draft unverified, emits an error, and does not save the turn.
- If the Supervisor and specialists return no source label at all, the response can be displayed without a source. The Flask layer does not perform full claim-to-chunk entailment validation.

## Document reader controls

`VOLUME_CATALOGS_JSON` defines the only Volume roots available to the application.

- Only configured catalog IDs and paths beneath their configured `/Volumes/...` roots are accepted.
- Path traversal, absolute relative paths, backslashes, NUL bytes, and non-PDF document paths are rejected.
- Directory listings include folders and PDF files only.
- Search examines filenames and paths, not PDF contents. It scans at most 5,000 objects and returns at most 50 results.
- Document links are signed, bound to the current user ID, and expire after `SOURCE_URL_TTL_SECONDS`.
- PDFs are streamed through Flask with `Cache-Control: private, no-store`.
- The browser opens a resolved page by adding `#page=<number>` to the document URL.

## Authentication modes

| Mode | Behavior |
| --- | --- |
| `local` | Uses the fixed local-development identity. No login is required. |
| `password` | Uses the Flask login page, one configured username, a Werkzeug password hash, and a signed session cookie. |
| `databricks` | Uses the `X-Forwarded-User` request header as the employee identity. The hosting layer must authenticate the user and set this header correctly. |

Production configuration requires:

- `APP_ENV=production`
- `AUTH_MODE=databricks`
- `SUPERVISOR_MODE=databricks`
- `SESSION_SECRET_KEY` with at least 32 characters
- OAuth client credentials
- No `DATABRICKS_TOKEN`

The application does not load `.env` when `APP_ENV=production`; production settings must come from the process environment or platform secret injection.

## Databricks authentication

When OAuth client credentials are configured, Supervisor inference requests a
token with the `model-serving` scope and caches it until shortly before
expiration. In non-production development, a configured `DATABRICKS_TOKEN` is
used directly instead.

Databricks SQL and Files operations use the Databricks SDK. OAuth M2M clients request the `sql` and `files` scopes. These operations support:

- Citation resolution
- Chat analytics inserts
- Volume browsing and search
- PDF downloads

`DATABRICKS_TOKEN` is supported only for non-production development. Production validation rejects it.

## Configuration

Only allowlisted keys are read from `.env`. Process environment variables override `.env` values.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `development`, `test`, or `production`. |
| `APP_VERSION` | `development` | Version recorded with analytics events. |
| `AUTH_MODE` | `local` | `local`, `password`, or `databricks`. |
| `SUPERVISOR_MODE` | `mock` | `mock` or `databricks`. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `LOGIN_USERNAME` | unset | Required for password authentication. |
| `LOGIN_PASSWORD_HASH` | unset | Werkzeug password hash; never store a plaintext password. |
| `SESSION_SECRET_KEY` | generated in development | Required with at least 32 characters for password mode and production. |
| `DATABRICKS_HOST` | unset | HTTPS Databricks workspace URL. |
| `DATABRICKS_CLIENT_ID` | unset | OAuth M2M client ID. |
| `DATABRICKS_CLIENT_SECRET` | unset | OAuth M2M client secret. |
| `DATABRICKS_TOKEN` | unset | Non-production development token alternative. Rejected in production. |
| `DATABRICKS_SUPERVISOR_ENDPOINT` | unset | Preferred Supervisor serving-endpoint setting. |
| `SUPERVISOR_ENDPOINT` | unset | Compatibility fallback when `DATABRICKS_SUPERVISOR_ENDPOINT` is absent. |
| `DATABRICKS_WAREHOUSE_ID` | unset | Enables citation SQL and Databricks analytics. |
| `DATABRICKS_LOG_TABLE` | `workspace.default.flask_app_logs` | Fully qualified analytics table. It must already exist with the expected schema. |
| `VOLUME_CATALOGS_JSON` | `[]` | Approved source catalogs as JSON objects containing `id`, `label`, and `volumePath`. |
| `REQUEST_TIMEOUT_SECONDS` | `60` | Supervisor request timeout and citation-query deadline. |
| `MAX_MESSAGE_CHARACTERS` | `4000` | Maximum trimmed chat-message length. |
| `CHAT_HISTORY_LIMIT` | `20` | Maximum turns retained per in-memory conversation. |
| `CHAT_SESSION_TTL_SECONDS` | `1800` | In-memory conversation inactivity lifetime. Minimum 60 seconds. |
| `SOURCE_URL_TTL_SECONDS` | `300` | Signed document-link lifetime. Valid range: 60–900 seconds. |

`DIRECT_SPECIALIST_ROUTES_JSON` maps `/policy`, `/handbook`, `/benefits` and
`/performance` to their specialist endpoints, for example
`{"/policy":{"endpoint":"ka-bad183de-endpoint","api":"responses","agent":"mariner-policy-assistant"}}`.
A mapped command calls the specialist once instead of going through the
Supervisor, with the same citation checks. Chart requests, unmapped commands and
failed direct calls still use the Supervisor. The app identity needs `CAN_QUERY`
on each mapped endpoint. An optional `"stream": true` streams a Responses agent's
answer live; it is off by default because Knowledge Assistants send their text
in one or two pieces at the end, so it adds no speed today.

The `/api/v1/chat/stream` route sends `progress` events (a domain label such as
"Checking the Employee Handbook…", never internal agent names) and `delta`
events with a checked preview of the Supervisor's final answer. The preview
releases whole lines only, at least 200 characters behind the model, after
personal-data masking and the block checks; a block sends `preview_reset`. The
`answer` event is still the fully checked final answer and replaces the preview.

Gunicorn also reads `PORT`, `WEB_CONCURRENCY`, `WEB_THREADS`, and `GUNICORN_TIMEOUT_SECONDS`. Current defaults are port `8000`, two workers, 16 threads per worker, and a 180-second worker timeout. The Supervisor client retries once on HTTP 429/502/503/504 or a connection error, and uses a 10-second connect timeout.

## Local setup

Python 3.14 is used by the container image. Create a virtual environment and install the bounded dependency ranges:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

For a fully isolated mock session, set:

```dotenv
APP_ENV=development
AUTH_MODE=local
SUPERVISOR_MODE=mock
VOLUME_CATALOGS_JSON=[]
```

Run Flask:

```bash
PYTHONPATH=src flask --app 'mariner_genai_dbx.web:create_app()' run --debug
```

Open <http://127.0.0.1:5000>.

For live Databricks testing, set `SUPERVISOR_MODE=databricks`, configure the workspace host, endpoint, warehouse, OAuth credentials, and approved Volume catalogs. Do not commit `.env` or credentials.

## Running with Gunicorn

```bash
PYTHONPATH=src gunicorn --config gunicorn.conf.py 'mariner_genai_dbx.web:create_app()'
```

The Docker image runs the same command as a non-root user and exposes port 8000.

## HTTP endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/login` | Password-mode login. Other modes redirect to `/`. |
| `POST` | `/logout` | Clears the Flask session. |
| `GET` | `/` | Chat and document-reader interface. |
| `GET` | `/health` | Process liveness; returns `{"status":"ok"}`. |
| `GET` | `/ready` | Cached construction-level readiness. It does not invoke the live Supervisor. |
| `POST` | `/api/v1/chat` | Chat API. Accepts `message` and optional `conversationId`. |
| `POST` | `/api/v1/chat/stream` | Same input; sends checked answer first, verified sources next using SSE. |
| `GET` | `/api/v1/sources` | Lists configured source catalogs. |
| `GET` | `/api/v1/sources/search?q=...` | Searches allowlisted PDF filenames and paths. |
| `GET` | `/api/v1/sources/<catalog_id>/children` | Lists an allowlisted folder. |
| `POST` | `/api/v1/sources/<catalog_id>/open` | Creates a user-bound document URL for a PDF path. |
| `GET` | `/documents/<token>` | Validates the signed token and streams the PDF. |

There is no `/api/chat` compatibility route; clients use `/api/v1/chat` or `/api/v1/chat/stream`.

## Logging and analytics

Two separate mechanisms exist and have different data content.

### Operational stdout logs

- One structured JSON completion event is emitted per HTTP request.
- Fields are allowlisted and include request ID, method, route template, status, and duration.
- Every HTTP response receives an `X-Request-ID` header.
- Unexpected exceptions include exception type and stack-frame file, line, and function metadata without exception text.
- Controlled messages sanitize common credentials and question/answer key-value patterns.
- Request bodies, headers, cookies, questions, and answers are not intentionally added as structured fields.
- Guardrail logs contain the category and request ID, not the intercepted message.
- Gunicorn access logging is disabled to avoid a duplicate unstructured access line.

### Databricks chat analytics

When `SUPERVISOR_MODE=databricks` and `DATABRICKS_WAREHOUSE_ID` is set, the app performs a best-effort insert into `DATABRICKS_LOG_TABLE`. Analytics failures are logged and do not fail a successful chat response.

The analytics record includes:

- User ID and hashed conversation/session ID
- Application version and latency
- Request and event timestamps
- The employee’s question
- The output-filtered answer
- Resolved source metadata
- Specialist names reported by the Supervisor
- Status and sanitized application error category
- Token usage when the endpoint reports it

Because the analytics table stores questions and answers, access, retention, and deletion controls must be applied at the Databricks table level. Do not describe this table as content-free operational telemetry.

## Tests

Run the Python suite:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Run the standalone JavaScript Markdown-renderer test:

```bash
node tests/test_markdown_renderer.cjs
```

The Python suite covers configuration, authentication, chat routing, guardrails, output filtering, conversation history, citation recovery, canonical source aliases, analytics writes, source-catalog controls, document links, and error sanitization.

## Known prototype limitations

- Conversation history is in-memory and process-local.
- The readiness endpoint validates construction/configuration only and is cached for 30 seconds.
- Guardrails use maintainable regex and string matching, not semantic moderation.
- Citation resolution validates approved document labels and selects a likely supporting page; it does not prove that every generated claim is entailed by the source text.
- Filename search does not search PDF contents.
- Analytics writes are best-effort and depend on the destination table already existing.
- The browser currently supports validated bar charts only.

### Optional POC performance retrieval

Set these values in the local `.env` and restart Flask to enable the bounded
performance workflow:

```dotenv
PERFORMANCE_FAST_PATH_ENABLED=true
PERFORMANCE_FAST_MODEL_ENDPOINT=databricks-gpt-5-4-mini
PERFORMANCE_SYNTHESIS_MODEL_ENDPOINT=databricks-gpt-5-4-mini
DATABRICKS_CITATION_REGISTRY_TABLE=workspace.default.app_citation_registry
PERFORMANCE_VIEW_PREFIX=app_fast_
```

`PERFORMANCE_VIEW_PREFIX` chooses which views the fast path reads. `app_vw_`
(the default) uses the live views; `app_fast_` uses the copies created by
`sql/create_performance_fast_views.sql`: six materialized views refreshed daily
plus a live `app_fast_review_compliance`, so "overdue" is always current. Run
that script before switching to `app_fast_`, and refresh the materialized views
(`REFRESH MATERIALIZED VIEW ...`) after loading new performance data if it
cannot wait for the daily refresh.

The app identity needs its existing warehouse access, `SELECT` on the approved
`workspace.performance_test.app_vw_*` views and citation registry, and query
permission on both model endpoints. This option uses the app identity's Unity
Catalog visibility for this POC; it does not add per-manager access lists. It is
disabled by default and rejected in production configuration.

A small planner selects employee, branch, region and quarter filters. One
parameterized SQL statement retrieves all selected employees and the needed
ratings, production, goals, competencies, review-compliance or branch datasets.
When policy is needed, that same statement retrieves performance policy passages
and their authoritative citation metadata from the registry. No question text is
executed as SQL. A single final model call combines the observed data and policy;
code copies selected citations from retrieved records and validates them through
the existing resolver. Existing output guardrails and progressive source delivery
still apply. Employee results and answers are not cached.

Future quarters remain explicitly missing. Planning requests also include bounded
historical context, clearly marked separately from the requested period. Monetary
amounts remain source values; attainment percentages are normalized from funded
and target amounts to avoid confusing ratios with percentages. Duplicate employee
names, oversized selections and truncated results require clarification.

The implementation has no embedded employee names, branch names, particular
quarter, or canned question responses. Explicit Branch Operations, Handbook and
Benefits commands bypass it. Other topics and unsupported analysis continue
through the existing Supervisor; those fallback requests can still take longer
than 30 seconds. Performance requests require a known employee, branch or region
for data reads. The POC policy context is bounded to ten passages and 100,000
characters; exceeding it fails explicitly instead of silently dropping policy.

Analytics identifies this local workflow as `performance-fast-path`, rather than
claiming that a hosted specialist was called. Timing logs report `planner_ms`,
`reads_ms`, and `total_ms`, without employee names
or answer bodies. Measure complete source delivery, including cold warehouse
starts, before treating 30 seconds as an operational guarantee. Disable
`PERFORMANCE_FAST_PATH_ENABLED` and restart Flask to restore the original route.
