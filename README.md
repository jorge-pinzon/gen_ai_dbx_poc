# Mariner GenAI DBX

Internal Flask chat application for the Mariner Databricks multi-agent employee-assistance system. The application sends employee questions to a Databricks Supervisor, renders Markdown tables and supported bar charts, resolves approved citations, and provides an in-app PDF document reader.

This repository is a test/prototype application. Conversation state is process-local, guardrails are regex-based, and the readiness endpoint does not perform a live Supervisor invocation.

## What the application does

- Serves the ASK MARINER chat interface.
- Sends ordinary questions to the Databricks Supervisor without application-level domain routing.
- Supports explicit user-directed routes:
  - `/policy` → Branch Operations (`mariner-policy-assistant`)
  - `/handbook` → Employee Handbook (`mariner-handbook-assistant`)
  - `/benefits` → Employee Benefits
  - `/coaching` → Employee Performance
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
4. Ordinary questions are forwarded unchanged to the Supervisor. Explicit slash commands are converted to authoritative specialist-routing instructions.
5. The app sends bounded conversation history for ordinary follow-up questions.
6. The Supervisor may call its configured specialist agents. Only allowlisted approval requests are approved by the Flask transport, with a maximum of five approval rounds.
7. The app selects the final Supervisor message and records specialist names reported in the response.
8. Source labels are extracted from the final message. If the final message omits them, the app searches the grounded specialist messages in the complete Databricks response.
9. Source labels are resolved through parameterized Databricks SQL queries.
10. Output guardrails mask or replace unsafe output.
11. The filtered answer and safe sources are saved to in-memory history, written to best-effort analytics, and returned to the browser.

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

The active dependency wiring imports the Databricks client from `supervisor_service1.py`. It calls the configured Databricks serving endpoint through the Responses API and treats that endpoint as stateless.

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
- If one or more source labels are returned but none resolves to an approved document, the chat route returns `CITATIONS_UNAVAILABLE` instead of displaying the answer as verified policy.
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

When OAuth client credentials are configured, Supervisor inference requests a token with the `model-serving-inference` scope and caches it until shortly before expiration. In non-production development, a configured `DATABRICKS_TOKEN` is used directly instead.

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

Gunicorn also reads `PORT`, `WEB_CONCURRENCY`, `WEB_THREADS`, and `GUNICORN_TIMEOUT_SECONDS`. Current defaults are port `8000`, two workers, four threads per worker, and a 660-second worker timeout.

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
| `GET` | `/api/v1/sources` | Lists configured source catalogs. |
| `GET` | `/api/v1/sources/search?q=...` | Searches allowlisted PDF filenames and paths. |
| `GET` | `/api/v1/sources/<catalog_id>/children` | Lists an allowlisted folder. |
| `POST` | `/api/v1/sources/<catalog_id>/open` | Creates a user-bound document URL for a PDF path. |
| `GET` | `/documents/<token>` | Validates the signed token and streams the PDF. |

There is no `/api/chat` compatibility route in the current application; clients must use `/api/v1/chat`.

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
