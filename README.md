# Mariner GenAI DBX

Flask frontend for the Mariner multi-agent backend in Databricks. The project
preserves the AWS prototype's user experience and stable HTTP API while replacing
all AWS integrations with Databricks-specific service boundaries.

## Current baseline

- ASK MARINER chat and two-pane source interface
- `POST /api/v1/chat`
- `GET /health` and `GET /ready`
- Conversation and request UUIDs
- Direct Supervisor routing commands
- Bounded, thread-safe in-memory test history
- Injectable Supervisor, identity, and source services
- Safe mock Supervisor for local development
- Databricks Responses API transport with strict final-message parsing
- Parameterized citation-label lookup across the three approved chunk tables
- Allowlisted Unity Catalog Volume browsing, search, and signed PDF links
- Privacy-preserving structured JSON operational logs written to stdout

The Supervisor transport targets `mas-53dbd2d7-endpoint`. Citation labels are
resolved through warehouse `55cdb78d4d2a62d0` against the Branch Operations,
Employee Handbook, and Employee Benefits chunk tables. The corresponding approved
Volume roots are configured through `VOLUME_CATALOGS_JSON`; document links are
user-bound and expire after `SOURCE_URL_TTL_SECONDS`. Direct claim-to-chunk support
validation is not connected yet. Chat activity is recorded independently in the
approved analytics table when that integration is configured.

The Supervisor uses OAuth M2M with `DATABRICKS_CLIENT_ID` and
`DATABRICKS_CLIENT_SECRET`. The backend requests the `model-serving-inference`
scope, caches the short-lived access token until shortly before expiration, and
never returns credentials to the browser.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
PYTHONPATH=src flask --app 'mariner_genai_dbx.web:create_app()' run --debug
```

The default configuration uses `SUPERVISOR_MODE=mock` and makes no external
requests. Open <http://127.0.0.1:5000>.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Production guardrails

Production requires `AUTH_MODE=databricks` and `SUPERVISOR_MODE=databricks`.
It rejects `DATABRICKS_TOKEN`; deployed authentication must use the approved
Databricks workload identity. Do not place credentials or employee data in `.env`.

Set `LOG_LEVEL` to `INFO` (the default), `WARNING`, or another standard Python
level. Every HTTP response includes `X-Request-ID`, and the application writes a
JSON completion event containing only the request ID, method, route template,
status, and duration. Unexpected failures additionally include the exception type
and a stack trace containing file, line, and function metadata. Request bodies,
query values, headers, cookies, credentials, questions, answers, and exception
messages are not serialized. Gunicorn access logging is disabled because this
structured completion event replaces its duplicate unstructured access line;
the hosting platform should collect the process stdout stream.
