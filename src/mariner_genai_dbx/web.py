"""Flask application and stable HTTP API for the Databricks frontend."""

from __future__ import annotations

import logging
import json
import hmac
import inspect
import queue
import re
import secrets
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from threading import Lock, Thread
from uuid import UUID, uuid4

from flask import (
    Flask,
    Response,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.security import check_password_hash

from .analytics import ChatLogEvent
from .bootstrap import (
    create_analytics_service,
    create_coaching360_service,
    create_conversation_persistence,
    create_document_search_service,
    create_source_catalog_service,
    create_supervisor_service,
    shared_workspace_client,
)
from .config import Settings, load_settings
from .errors import (
    CitationResolutionError,
    ConversationPersistenceError,
    DatabricksAuthenticationError,
    InvalidQuestionError,
    InvalidSourcePathError,
    ReadinessCheckError,
    SourceCatalogError,
    SourceDocumentNotFoundError,
    SupervisorInvocationError,
)
from .document_views import (
    CONTENT_SECURITY_POLICY,
    SpreadsheetError,
    read_workbook,
    render_message,
    render_workbook,
)
from .models import AgentAnswer, ConversationHistory, ConversationTurn
from .live_preview import LivePreview, tidy_table
from .logging_config import configure_logging
from .source_catalog import document_kind, document_media_type


MAX_REQUEST_BYTES = 16 * 1024
READINESS_CACHE_SECONDS = 30
# Static URLs carry a content hash, so browsers may keep them for a year and
# still fetch a new file as soon as a deploy changes it.
STATIC_MAX_AGE_SECONDS = 365 * 24 * 60 * 60
MAX_SPREADSHEET_PREVIEW_BYTES = 20 * 1024 * 1024
LOCAL_USER_ID = "local-development-user"
logger = logging.getLogger(__name__)
BRANCH_OPERATIONS_SPECIALIST = (
    "Branch Operations specialist named mariner-policy-assistant"
)
EMPLOYEE_HANDBOOK_SPECIALIST = (
    "Employee Handbook specialist named mariner-handbook-assistant"
)
SUPERVISOR_ROUTE_COMMANDS = {
    "/policy": BRANCH_OPERATIONS_SPECIALIST,
    "/benfits": "Benefits Agent",
    "/benefits": "Benefits Agent",
    "/handbook": EMPLOYEE_HANDBOOK_SPECIALIST,
    "/performance": "Employee Performance Agent",
}

# Application-layer guardrail configuration. Keep patterns and user-facing
# responses together so changes can be reviewed without searching route code.
INPUT_GUARDRAIL_REFUSAL = (
    "I can help with Mariner employee policies, benefits, branch operations, "
    "the employee handbook, and performance topics. Please ask a question "
    "within one of those areas."
)
OUTPUT_GUARDRAIL_FALLBACK = (
    "I’m unable to provide that response. Please rephrase your question or "
    "contact Human Resources for assistance."
)
SELF_HARM_SUPPORT_MESSAGE = (
    "I’m sorry you’re going through this. If you may act on these thoughts or "
    "are in immediate danger, call 911 now. In the United States, call or text "
    "988 to reach the Suicide & Crisis Lifeline. If you can, move away from "
    "anything you could use to hurt yourself and contact someone you trust who "
    "can stay with you. This chat is not a crisis service."
)
SELF_HARM_INPUT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\bi\s+(?:want|plan|intend|am\s+going|might|may|could)\s+to\s+(?:kill|hurt|harm)\s+myself\b",
        r"\bi(?:'m|\s+am)\s+suicidal\b",
        r"\bi\s+(?:want|wish)\s+to\s+die\b",
        r"\bi\s+do\s+not\s+want\s+to\s+live\b",
        r"\b(?:end|take)\s+my\s+(?:own\s+)?life\b",
        r"\b(?:thinking|thoughts?)\s+(?:about|of)\s+(?:suicide|killing\s+myself|self[- ]?harm)\b",
        r"\b(?:friend|coworker|employee|manager|someone)\b.{0,60}\b(?:suicidal|suicide|kill(?:ing)?\s+(?:himself|herself|themselves))\b",
    )
)
HATE_OR_ABUSE_INPUT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"^\s*(?:fuck|screw)\s+(?:you|him|her|them)\b",
        r"^\s*(?:you|he|she|they)\s+(?:are|is)\s+(?:an?\s+)?(?:fucking\s+)?(?:idiot|moron|asshole|bitch)\b",
        r"\b(?:write|generate|create|give\s+me)\b.{0,60}\b(?:racist|homophobic|transphobic|antisemitic|sexist)\s+(?:joke|message|insult|slur|rant)\b",
        r"\b(?:write|generate|create|give\s+me)\b.{0,60}\b(?:hate\s+speech|racial\s+slurs?|ethnic\s+slurs?)\b",
        r"\b(?:i\s+hate|kill|attack|hurt|get\s+rid\s+of)\s+(?:all\s+)?(?:black\s+people|white\s+people|asians?|latinos?|hispanics?|muslims?|jews?|christians?|gay\s+people|lesbians?|trans\s+people|immigrants?|women|men)\b",
        r"\bi(?:'m|\s+am)\s+going\s+to\s+(?:kill|shoot|stab|attack|hurt)\s+(?:you|him|her|them|my\s+(?:manager|coworker))\b",
    )
)
PROMPT_INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b",
        r"\b(?:disregard|override|bypass)\b.{0,60}\b(?:instructions?|rules?|guardrails?|policy)\b",
        r"\byou\s+are\s+now\b",
        r"\b(?:reveal|show|print|repeat|extract|provide)\b.{0,80}\b(?:system|developer|hidden|internal)\s+(?:prompt|instructions?|message)\b",
        r"\b(?:system|developer)\s+prompt\b",
        r"\b(?:act|behave|respond)\s+as\b.{0,60}\b(?:without|no)\s+(?:rules?|restrictions?|guardrails?)\b",
        r"\b(?:change|switch|reassign)\s+(?:your\s+)?role\b",
        r"\bprompt\s+injection\b",
    )
)
PII_GENERATION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:generate|create|invent|make\s+up|provide|give\s+me|list|show\s+me)\b.{0,100}\b(?:ssn|ssns|social\s+security\s+numbers?)\b",
        r"\b(?:generate|create|invent|make\s+up|provide|give\s+me|list|show\s+me)\b.{0,100}\b(?:credit|debit)\s+card\s+numbers?\b",
        r"\b(?:generate|create|invent|make\s+up|provide|give\s+me|list|show\s+me)\b.{0,100}\b(?:passwords?|account\s+credentials?|login\s+credentials?)\b",
    )
)
EXPLICIT_OFF_TOPIC_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:write|debug|fix|refactor|compile|build)\b.{0,80}\b(?:code|program|script|python|javascript|java|sql|html|css)\b",
        r"\b(?:write|compose|create)\b.{0,60}\b(?:poem|story|song|novel|screenplay|joke)\b",
        r"\b(?:weather|sports\s+score|stock\s+price|cryptocurrency|recipe)\b",
        r"\b(?:capital|president|population)\s+of\b",
    )
)
SUPPORTED_DOMAIN_PATTERN = re.compile(
    r"\b(?:employee|employment|manager|supervisor|human\s+resources|hr|"
    r"branch|loan|lending|customer\s+complaint|record\s+retention|audit|"
    r"handbook|attendance|timekeeping|workplace|conduct|dress\s+code|attire|"
    r"social\s+media|technology\s+use|acceptable\s+use|confidentiality|safety|"
    r"disciplin(?:e|ary)|password|"
    r"benefit|benefits|eligibility|enrollment|medical|dental|vision|retirement|"
    r"insurance|wellness|life\s+event|pto|leave|vacation|ppo|hmo|401k|"
    r"provider|deductible|copay|fmla|jury\s+duty|business\s+casual|"
    r"reimburs|expense|travel|mileage|per\s+diem|education\s+assistance|"
    r"navan|travel\s+account|expense\s+(?:account|management)|corporate\s+card|"
    r"performance|rating|review|evaluation|competenc|goal|career|coaching|"
    r"promotion|bonus|compensation|meeting|quarter|target|funded|region)\w*\b",
    re.IGNORECASE,
)
SAFE_CONVERSATIONAL_PATTERN = re.compile(
    r"^\s*(?:(?:hi|hello|hey|thanks|thank\s+you|good\s+(?:morning|afternoon|evening))"
    r"[!.\s]*)$|\b(?:above|previous|earlier|that\s+answer|tell\s+me\s+more|"
    r"explain|clarify|summarize|table|chart|graph|compare)\b",
    re.IGNORECASE,
)
OUTPUT_PII_PATTERNS = (
    (
        "ssn",
        re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
        "[REDACTED SSN]",
    ),
    (
        "email",
        # Approved role-based Mariner mailboxes (for example, travel@...) are
        # operational contacts rather than personal email addresses. Continue
        # masking personal Mariner addresses containing a dot in the local part,
        # as well as every address outside the marinerfinance.com domain.
        re.compile(
            r"\b(?![A-Z0-9_%+-]+@marinerfinance\.com\b)"
            r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            re.IGNORECASE,
        ),
        "[REDACTED EMAIL]",
    ),
    (
        "phone",
        re.compile(
            r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\w)"
        ),
        "[REDACTED PHONE]",
    ),
    (
        "account_number",
        re.compile(
            r"\b(?:account|acct|routing)\s*(?:number|no\.?|#)?\s*[:=-]?\s*\d{6,17}\b",
            re.IGNORECASE,
        ),
        "[REDACTED ACCOUNT NUMBER]",
    ),
    (
        "payment_card",
        re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
        "[REDACTED PAYMENT CARD]",
    ),
)
INTERNAL_DETAIL_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\bmas-[a-z0-9-]+-endpoint\b",
        r"\b(?:model|serving)\s+endpoint\b",
        r"\b(?:gpt-?\d[\w.-]*|claude[\w.-]*|llama[\w.-]*|qwen[\w.-]*|dbrx[\w.-]*)\b",
        r"\b(?:supervisor\s+agent|sub-?agent|agent\s+architecture|knowledge\s+assistant)\b",
        r"\b(?:tool\s+(?:name|call)|mcp[_ -]|app-agent-[a-z0-9-]+)\b",
        r"/(?:api(?:/v\d+)?|serving-endpoints|Workspace|Volumes)/[^\s)\]]+",
        r"\b(?:service\s+principal|client[_ -]?id)\b.{0,80}\b[0-9a-f]{8}-[0-9a-f-]{27,36}\b",
    )
)
BINDING_DECISION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:you|the\s+employee)\s+(?:are|is|will\s+be|have\s+been|has\s+been)\s+(?:terminated|fired|promoted|demoted|suspended)\b",
        r"\b(?:we|mariner|management|human\s+resources|hr|the\s+company)\s+(?:has\s+|have\s+)?(?:decided|determined|approved|will)\b.{0,100}\b(?:terminate|fire|promote|demote|suspend|disciplinary\s+action|bonus|salary|compensation)\b",
        r"\b(?:your|the\s+employee(?:'s)?)\s+(?:salary|bonus|compensation)\s+(?:is|will\s+be|has\s+been)\s+(?:set\s+(?:at|to)\s*)?\$\s*[\d,]+(?:\.\d{2})?\b",
    )
)
SELF_HARM_OUTPUT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:you\s+should|go\s+ahead\s+and|the\s+best\s+way\s+to)\s+(?:kill|hurt|harm)\s+yourself\b",
        r"\b(?:instructions?|steps?|methods?|ways?)\b.{0,80}\b(?:commit\s+suicide|kill\s+yourself|self[- ]?harm)\b",
        r"\b(?:suicide|self[- ]?harm)\b.{0,80}\b(?:instructions?|steps?|methods?)\b",
    )
)
HATE_OR_ABUSE_OUTPUT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"^\s*(?:fuck|screw)\s+(?:you|him|her|them)\b",
        r"\b(?:kill|attack|hurt|get\s+rid\s+of)\s+(?:all\s+)?(?:black\s+people|white\s+people|asians?|latinos?|hispanics?|muslims?|jews?|christians?|gay\s+people|lesbians?|trans\s+people|immigrants?|women|men)\b",
        r"\b(?:write|use|repeat)\b.{0,60}\b(?:hate\s+speech|racial\s+slurs?|ethnic\s+slurs?)\b",
    )
)


class ReadinessCache:
    def __init__(self, ttl_seconds=READINESS_CACHE_SECONDS, *, clock=time.monotonic):
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = Lock()
        self._checked_at = None
        self._ready = False

    def check(self, checker) -> bool:
        now = self._clock()
        with self._lock:
            if self._checked_at is not None and now - self._checked_at < self._ttl_seconds:
                return self._ready
            try:
                self._ready = bool(checker().ready)
            except (
                DatabricksAuthenticationError,
                ReadinessCheckError,
                SupervisorInvocationError,
            ):
                self._ready = False
            self._checked_at = now
            return self._ready


def create_app(
    settings: Settings | None = None,
    *,
    supervisor_service=None,
    conversation_persistence=None,
    source_catalog_service=None,
    document_search_service=None,
    analytics_service=None,
    identity_provider=None,
    readiness_cache: ReadinessCache | None = None,
    coaching360_service=None,
) -> Flask:
    application_settings = settings or load_settings()
    configure_logging(application_settings.log_level)
    client_factory = shared_workspace_client(application_settings)
    service = supervisor_service or create_supervisor_service(
        application_settings, workspace_client_factory=client_factory
    )
    analytics = analytics_service or create_analytics_service(
        application_settings, workspace_client_factory=client_factory
    )
    persistence = conversation_persistence or create_conversation_persistence(
        application_settings
    )
    coaching360 = coaching360_service or create_coaching360_service(
        application_settings, workspace_client_factory=client_factory
    )
    catalog_service = source_catalog_service
    if catalog_service is None:
        catalog_service = create_source_catalog_service(
            application_settings, workspace_client_factory=client_factory
        )
    document_search = document_search_service
    if document_search is None and catalog_service is not None:
        document_search = create_document_search_service(
            application_settings, workspace_client_factory=client_factory
        )
    if identity_provider is None:
        if application_settings.auth_mode == "local":
            identity_provider = lambda: LOCAL_USER_ID
        elif application_settings.auth_mode == "password":
            identity_provider = lambda: session.get("user_id")
        else:
            identity_provider = lambda: request.headers.get("X-Forwarded-User")

    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,
        JSON_SORT_KEYS=False,
        SECRET_KEY=application_settings.session_secret_key or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=application_settings.app_env != "development",
    )
    app.extensions.update(
        mariner_settings=application_settings,
        supervisor_service=service,
        conversation_persistence=persistence,
        source_catalog_service=catalog_service,
        analytics_service=analytics,
        identity_provider=identity_provider,
        readiness_cache=readiness_cache or ReadinessCache(),
        coaching360_service=coaching360,
    )
    if application_settings.app_env != "development":
        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = STATIC_MAX_AGE_SECONDS
        static_versions = {}

        @app.url_defaults
        def version_static_urls(endpoint, values):
            filename = values.get("filename")
            if endpoint != "static" or not filename or "v" in values:
                return
            if filename not in static_versions:
                try:
                    contents = (Path(app.static_folder) / filename).read_bytes()
                except OSError:
                    return
                static_versions[filename] = sha256(contents).hexdigest()[:12]
            values["v"] = static_versions[filename]

    source_link_serializer = URLSafeTimedSerializer(
        app.config["SECRET_KEY"], salt="mariner-source-link"
    )
    app.extensions["source_link_serializer"] = source_link_serializer

    @app.before_request
    def initialize_request_context():
        g.request_id = str(uuid4())
        g.request_started_at = time.monotonic()

    @app.after_request
    def log_completed_request(response):
        request_id = _request_id()
        started_at = getattr(g, "request_started_at", time.monotonic())
        duration_ms = round((time.monotonic() - started_at) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["Server-Timing"] = f"{'app_headers' if response.is_streamed else 'app'};dur={duration_ms}"
        metadata = {
            "request_id": request_id, "method": request.method,
            "route": _route_template(), "status": response.status_code,
        }
        if response.is_streamed:
            logger.info("HTTP stream started", extra={
                **metadata, "event": "http_stream_started", "duration_ms": duration_ms,
            })
            response.call_on_close(lambda: logger.info("HTTP request completed", extra={
                **metadata, "event": "http_request_completed",
                "duration_ms": round((time.monotonic() - started_at) * 1000),
            }))
            return response
        logger.info(
            "HTTP request completed",
            extra={
                "event": "http_request_completed",
                **metadata,
                "duration_ms": duration_ms,
            },
        )
        return response

    @app.before_request
    def require_password_authentication():
        if application_settings.auth_mode != "password":
            return None
        if request.endpoint in {"login", "health", "ready", "static"}:
            return None
        if identity_provider():
            return None
        if request.path.startswith("/api/"):
            return _error_response(
                "AUTHENTICATION_REQUIRED",
                "Authentication is required.",
                _request_id(),
                401,
            )
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if application_settings.auth_mode != "password":
            return redirect(url_for("index"))
        if identity_provider():
            return redirect(url_for("index"))

        error = None
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            username_matches = hmac.compare_digest(
                username, application_settings.login_username or ""
            )

            # Get the hash value
            stored_hash = application_settings.login_password_hash
            # Strictly ensure stored_hash is a text string and password is not empty
            if isinstance(stored_hash, str) and password:
                password_matches = check_password_hash(stored_hash, password)
            else:
                password_matches = False

            if username_matches and password_matches:
                session.clear()
                session["user_id"] = sha256(username.encode("utf-8")).hexdigest()
                return redirect(url_for("index"))
            error = "The username or password is incorrect."

        return render_template("login.html", error=error), 401 if error else 200

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            max_message_characters=application_settings.max_message_characters,
            local_mode=application_settings.auth_mode == "local",
            password_mode=application_settings.auth_mode == "password",
        )

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/ready")
    def ready():
        is_ready = app.extensions["readiness_cache"].check(service.check_readiness)
        status_code = 200 if is_ready else 503
        return jsonify(status="ready" if is_ready else "unavailable"), status_code

    @app.post("/api/v1/chat/stream")
    @app.post("/api/v1/chat")
    def chat():
        started_at = time.monotonic()
        request_id = _request_id()
        if not request.is_json:
            return _error_response(
                "INVALID_REQUEST", "Content-Type must be application/json.", request_id, 400
            )
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error_response(
                "INVALID_REQUEST", "The request body must be a JSON object.", request_id, 400
            )
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            return _error_response(
                "INVALID_MESSAGE", "Message must be a non-empty string.", request_id, 400
            )
        message = message.strip()
        if len(message) > application_settings.max_message_characters:
            return _error_response(
                "MESSAGE_TOO_LONG",
                f"Message cannot exceed {application_settings.max_message_characters} characters.",
                request_id,
                413,
            )

        conversation_id = payload.get("conversationId")
        if conversation_id is None:
            conversation_id = str(uuid4())
        elif not _is_uuid(conversation_id):
            return _error_response(
                "INVALID_CONVERSATION_ID",
                "conversationId must be a valid UUID.",
                request_id,
                400,
            )

        input_guardrail_reason = _input_guardrail_reason(message)
        if input_guardrail_reason:
            logger.warning(
                "Chat input intercepted; request_id=%s category=%s",
                request_id,
                input_guardrail_reason,
            )
            if input_guardrail_reason == "self_harm":
                return jsonify(
                    conversationId=conversation_id,
                    requestId=request_id,
                    answer=SELF_HARM_SUPPORT_MESSAGE,
                    sources=[],
                )
            return _error_response(
                "MESSAGE_NOT_ALLOWED",
                INPUT_GUARDRAIL_REFUSAL,
                request_id,
                400,
            )

        user_id = identity_provider()
        if not user_id:
            return _error_response(
                "AUTHENTICATION_REQUIRED", "Authentication is required.", request_id, 401
            )
        session_id = _supervisor_session_id(user_id, conversation_id)

        def record_event(
            status, *, answer="", sources=(), agents_used=(), error_message="", usage=None,
            inference_ms=None, citations_ms=None, stage_ms=None,
        ):
            try:
                analytics.record(
                    ChatLogEvent(
                        user_id=user_id,
                        session_id=session_id,
                        app_version=application_settings.app_version,
                        latency_ms=round((time.monotonic() - started_at) * 1000),
                        event_id=request_id,
                        event_timestamp=datetime.now(timezone.utc),
                        question=message,
                        answer=answer,
                        sources=tuple(sources),
                        status=status,
                        agents_used=tuple(agents_used),
                        error_message=error_message,
                        usage=usage,
                        inference_ms=inference_ms,
                        citations_ms=citations_ms,
                        stage_ms=stage_ms,
                    )
                )
            except Exception as error:
                logger.warning(
                    "Analytics logging failed; request_id=%s error_type=%s",
                    request_id,
                    type(error).__name__,
                )

        try:
            history = persistence.load_history(user_id, conversation_id)
        except ConversationPersistenceError:
            record_event("error", error_message="conversation_history_unavailable")
            return _error_response(
                "CONVERSATION_UNAVAILABLE",
                "Conversation history is temporarily unavailable.",
                request_id,
                503,
            )

        # Coaching360 demo flow: setup steps are answered here; questions go to the Supervisor
        # with a level directive instead of the normal routing.
        coaching = None
        stage_ms = {}  # where the time went, for the analytics log
        if coaching360 is not None:
            try:
                coaching_started = time.monotonic()
                coaching = coaching360.handle(user_id, conversation_id, message)
                if coaching is not None:
                    stage_ms["coaching360"] = round((time.monotonic() - coaching_started) * 1000)
            except Exception as error:
                logger.error("Coaching360 failed; request_id=%s error_type=%s", request_id, type(error).__name__)
                record_event("error", error_message="coaching360_unavailable")
                return _error_response(
                    "AGENT_UNAVAILABLE", "Coaching360 is temporarily unavailable. Please try again.", request_id, 503
                )
        if coaching is not None and coaching.reply is not None:
            try:
                persistence.record_turn(ConversationTurn(
                    conversation_id=conversation_id, request_id=request_id, user_id=user_id,
                    created_at=datetime.now(timezone.utc), question=message, answer=coaching.reply,
                ), history)
            except ConversationPersistenceError:
                pass  # setup replies are not needed for later turns
            record_event("success", answer=coaching.reply, agents_used=("coaching360-setup",))
            if request.path.endswith("/stream"):
                events = (
                    _chat_event("status", {"conversationId": conversation_id, "requestId": request_id, "phase": "generating"})
                    + _chat_event("answer", {"conversationId": conversation_id, "requestId": request_id,
                                             "answer": coaching.reply, "citationStatus": "none"})
                    + _chat_event("sources", {"sources": []})
                    + _chat_event("done", {"conversationId": conversation_id, "requestId": request_id})
                )
                return Response(events, mimetype="text/event-stream", headers={
                    "Cache-Control": "no-cache, no-store, private", "X-Accel-Buffering": "no"})
            return jsonify(conversationId=conversation_id, requestId=request_id, answer=coaching.reply, sources=[])
        supervisor_message = coaching.supervisor_message if coaching is not None else _supervisor_input(message)
        fresh_history = coaching is not None or _has_direct_route(message)

        if request.path.endswith("/stream"):
            @stream_with_context
            def stream_answer():
                finished = False
                marks = {}  # seconds since the model call started, per stage
                try:
                    yield _chat_event("status", {
                        "conversationId": conversation_id, "requestId": request_id,
                        "phase": "generating",
                    })
                    supervisor_history = ConversationHistory() if fresh_history else history
                    progressive = callable(getattr(service, "prepare_answer", None)) and callable(
                        getattr(service, "resolve_answer", None)
                    )
                    direct = (
                        _direct_route(message)
                        if coaching is None and callable(getattr(service, "prepare_direct_answer", None)) else None
                    )
                    if progressive:
                        target = service.prepare_direct_answer if direct else service.prepare_answer

                        def prepare(**live):
                            if direct:
                                return service.prepare_direct_answer(
                                    *direct, _supervisor_input(message), session_id, **live
                                )
                            return service.prepare_answer(
                                supervisor_message, session_id, supervisor_history, **live
                            )

                        if _accepts_live_events(target):
                            pending = yield from _prepare_with_live_events(
                                prepare, marks,
                                timeout_seconds=application_settings.coaching360_timeout_seconds if coaching is not None else None,
                            )
                            stage_ms.update(_milliseconds(marks))
                        else:
                            pending = prepare()
                    if progressive:
                        raw_answer = pending.answer
                        needs_citations = pending.citations_pending
                    else:
                        # Compatibility with mock and injected synchronous services.
                        result = service.answer(
                            supervisor_message, session_id, supervisor_history
                        )
                        raw_answer = result.answer
                        needs_citations = False
                    safe_answer, categories, blocked = _apply_output_guardrails(raw_answer)
                    if categories:
                        logger.warning(
                            "Stream output filtered; request_id=%s categories=%s action=%s",
                            request_id, ",".join(categories), "replaced" if blocked else "masked",
                        )
                    yield _chat_event("answer", {
                        "conversationId": conversation_id, "requestId": request_id,
                        "answer": safe_answer,
                        "citationStatus": "pending" if needs_citations and not blocked else "none",
                    })
                    # Yield the checked draft before running citation SQL. Do not
                    # persist or mark the turn complete until validation succeeds.
                    if progressive:
                        result = (
                            AgentAnswer(answer=safe_answer, usage=pending.usage,
                                        agents_used=pending.agents_used,
                                        inference_ms=pending.inference_ms)
                            if blocked else service.resolve_answer(pending)
                        )
                    safe_sources = () if blocked else result.sources
                    public_sources = [_public_source(source, catalog_service) for source in safe_sources]
                    persistence.record_turn(ConversationTurn(
                        conversation_id=conversation_id, request_id=request_id,
                        user_id=user_id, created_at=datetime.now(timezone.utc),
                        question=message, answer=safe_answer, sources=safe_sources,
                        usage=result.usage,
                    ), history)
                    yield _chat_event("sources", {"sources": public_sources})
                    if stage_ms:
                        logger.info("Chat stages; request_id=%s stage_ms=%s", request_id,
                                    json.dumps(stage_ms, separators=(",", ":")))
                    record_event(
                        "success", answer=safe_answer, sources=safe_sources,
                        agents_used=result.agents_used, usage=_reported_usage(result.usage),
                        inference_ms=result.inference_ms, citations_ms=result.citations_ms,
                        stage_ms=stage_ms or None,
                    )
                    finished = True
                    yield _chat_event("done", {
                        "conversationId": conversation_id, "requestId": request_id,
                    })
                except GeneratorExit:
                    if not finished:
                        # flask_app_logs.status allows success, error and timeout only.
                        record_event("error", error_message="stream_disconnected")
                    raise
                except AnswerTimeout:
                    stage_ms.update(_milliseconds(marks))
                    logger.warning("Chat stream timed out; request_id=%s stage_ms=%s", request_id,
                                   json.dumps(stage_ms, separators=(",", ":")))
                    record_event("timeout", error_message="answer_timeout", stage_ms=stage_ms or None)
                    yield _chat_event("error", {"code": "TIMEOUT", "message": COACHING360_TIMEOUT_MESSAGE})
                except Exception as error:
                    if isinstance(error, CitationResolutionError):
                        code = "CITATIONS_UNAVAILABLE"
                        text = "Sources could not be verified. Treat this answer as unverified. Please try again."
                    elif isinstance(error, ConversationPersistenceError):
                        code = "CONVERSATION_UNAVAILABLE"
                        text = "The answer could not be saved. Please try again."
                    else:
                        code = "AGENT_UNAVAILABLE"
                        text = "The employee support service is temporarily unavailable. Please try again."
                    logger.error(
                        "Chat stream failed; request_id=%s error_type=%s", request_id, type(error).__name__
                    )
                    record_event("error", error_message=code.lower())
                    yield _chat_event("error", {"code": code, "message": text})

            return Response(stream_answer(), mimetype="text/event-stream", headers={
                "Cache-Control": "no-cache, no-store, private",
                "X-Accel-Buffering": "no",
            })

        try:
            # Explicit slash commands are authoritative one-shot routes. Do not
            # let prior cross-domain turns bias the selected specialist's answer;
            # the completed turn is still persisted in the current conversation.
            supervisor_history = ConversationHistory() if fresh_history else history
            direct = (
                _direct_route(message)
                if coaching is None and callable(getattr(service, "prepare_direct_answer", None)) else None
            )
            if direct and callable(getattr(service, "resolve_answer", None)):
                result = service.resolve_answer(service.prepare_direct_answer(
                    *direct, _supervisor_input(message), session_id
                ))
            else:
                result = service.answer(
                    supervisor_message,
                    session_id,
                    supervisor_history,
                )
        except InvalidQuestionError:
            record_event("error", error_message="invalid_question")
            return _error_response(
                "INVALID_MESSAGE", "Message must be a non-empty string.", request_id, 400
            )
        except SupervisorInvocationError as error:
            logger.error("Supervisor invocation failed; request_id=%s", request_id)
            timed_out = _is_timeout_error(error)
            record_event(
                "timeout" if timed_out else "error",
                error_message="supervisor_timeout" if timed_out else "supervisor_unavailable",
            )
            return _error_response(
                "AGENT_UNAVAILABLE",
                "The employee support service is temporarily unavailable.",
                request_id,
                502,
            )
        except CitationResolutionError:
            logger.error("Citation resolution failed; request_id=%s", request_id)
            record_event("error", error_message="citation_resolution_failed")
            return _error_response(
                "CITATIONS_UNAVAILABLE",
                _citation_recovery_message(message),
                request_id,
                502,
            )
        except (DatabricksAuthenticationError, ReadinessCheckError):
            logger.error("Databricks authentication failed; request_id=%s", request_id)
            record_event("error", error_message="databricks_authentication_failed")
            return _error_response(
                "AGENT_UNAVAILABLE",
                "The employee support service is temporarily unavailable.",
                request_id,
                503,
            )

        safe_answer, output_filter_categories, output_was_blocked = (
            _apply_output_guardrails(result.answer)
        )
        safe_sources = () if output_was_blocked else result.sources
        if output_filter_categories:
            logger.warning(
                "Supervisor output filtered; request_id=%s categories=%s action=%s",
                request_id,
                ",".join(output_filter_categories),
                "replaced" if output_was_blocked else "masked",
            )

        turn = ConversationTurn(
            conversation_id=conversation_id,
            request_id=request_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            question=message,
            answer=safe_answer,
            sources=safe_sources,
            usage=result.usage,
        )
        try:
            persistence.record_turn(turn, history)
        except ConversationPersistenceError:
            record_event(
                "error",
                error_message="conversation_persistence_failed",
                usage=_reported_usage(result.usage),
            )
            return _error_response(
                "CONVERSATION_UNAVAILABLE",
                "The answer could not be saved. Please try again.",
                request_id,
                503,
            )

        record_event(
            "success",
            answer=safe_answer,
            sources=safe_sources,
            agents_used=result.agents_used,
            usage=_reported_usage(result.usage),
            inference_ms=result.inference_ms,
            citations_ms=result.citations_ms,
        )
        return jsonify(
            conversationId=conversation_id,
            requestId=request_id,
            answer=safe_answer,
            sources=[_public_source(source, catalog_service) for source in safe_sources],
        )

    @app.get("/api/v1/sources")
    def source_catalogs():
        authentication_error = _require_identity(identity_provider)
        if authentication_error:
            return authentication_error
        return jsonify(catalogs=catalog_service.catalogs() if catalog_service else [])

    @app.get("/api/v1/sources/search")
    def search_source_catalogs():
        request_id = _request_id()
        if not identity_provider():
            return _error_response(
                "AUTHENTICATION_REQUIRED", "Authentication is required.", request_id, 401
            )
        if catalog_service is None:
            return _error_response(
                "SOURCE_CATALOG_NOT_CONFIGURED",
                "The source catalog is not configured.",
                request_id,
                404,
            )
        try:
            result = catalog_service.search(request.args.get("q", ""))
        except InvalidSourcePathError:
            return _error_response(
                "INVALID_SOURCE_SEARCH",
                "Enter between 2 and 80 characters to search documents.",
                request_id,
                400,
            )
        except (DatabricksAuthenticationError, SourceCatalogError):
            return _error_response(
                "SOURCE_CATALOG_UNAVAILABLE",
                "The source catalog is temporarily unavailable.",
                request_id,
                503,
            )
        result["contentResults"] = []
        if document_search is not None:
            try:
                hits = document_search.search(result["query"])
            except Exception as error:
                # File-name results still work when the document text cannot be loaded.
                logger.warning("Document text search failed; error_type=%s", type(error).__name__)
                result["contentUnavailable"] = True
            else:
                labels = {catalog["id"]: catalog["label"] for catalog in catalog_service.catalogs()}
                for hit in hits:
                    reference = catalog_service.reference_for_location(hit["volumePath"])
                    if not reference:
                        continue
                    result["contentResults"].append({
                        **reference,
                        "catalogLabel": labels.get(reference["catalogId"], ""),
                        "name": PurePosixPath(reference["path"]).name,
                        "kind": document_kind(reference["path"]),
                        **({"page": hit["page"]} if hit["page"] else {}),
                        "snippet": hit["snippet"],
                    })
        return jsonify(result)

    @app.get("/api/v1/sources/<catalog_id>/children")
    def source_catalog_children(catalog_id):
        request_id = _request_id()
        if not identity_provider():
            return _error_response(
                "AUTHENTICATION_REQUIRED", "Authentication is required.", request_id, 401
            )
        if catalog_service is None:
            return _error_response(
                "SOURCE_CATALOG_NOT_CONFIGURED",
                "The source catalog is not configured.",
                request_id,
                404,
            )
        try:
            result = catalog_service.list_children(
                catalog_id, request.args.get("path", ""), request.args.get("cursor")
            )
        except InvalidSourcePathError:
            return _error_response(
                "INVALID_SOURCE_PATH", "The source path is invalid.", request_id, 400
            )
        except (DatabricksAuthenticationError, SourceCatalogError):
            return _error_response(
                "SOURCE_CATALOG_UNAVAILABLE",
                "The source catalog is temporarily unavailable.",
                request_id,
                503,
            )
        return jsonify(result)

    @app.post("/api/v1/sources/<catalog_id>/open")
    def open_source_document(catalog_id):
        request_id = _request_id()
        user_id = identity_provider()
        if not user_id:
            return _error_response(
                "AUTHENTICATION_REQUIRED", "Authentication is required.", request_id, 401
            )
        payload = request.get_json(silent=True) if request.is_json else None
        if not isinstance(payload, dict) or not isinstance(payload.get("path"), str):
            return _error_response(
                "INVALID_SOURCE_PATH", "The source path is invalid.", request_id, 400
            )
        if catalog_service is None:
            return _error_response(
                "SOURCE_CATALOG_NOT_CONFIGURED",
                "The source catalog is not configured.",
                request_id,
                404,
            )
        try:
            result = catalog_service.open_document(catalog_id, payload["path"])
        except InvalidSourcePathError:
            return _error_response(
                "INVALID_SOURCE_PATH", "The source path is invalid.", request_id, 400
            )
        except (DatabricksAuthenticationError, SourceCatalogError):
            return _error_response(
                "SOURCE_CATALOG_UNAVAILABLE",
                "The source catalog is temporarily unavailable.",
                request_id,
                503,
            )
        public_result = {
            "label": result["label"],
            "embeddable": bool(result.get("embeddable")),
            **({"kind": result["kind"]} if result.get("kind") else {}),
        }
        if result.get("url"):
            public_result["url"] = result["url"]
        elif result.get("catalogId") and result.get("path"):
            token = source_link_serializer.dumps(
                {
                    "userId": user_id,
                    "catalogId": result["catalogId"],
                    "path": result["path"],
                }
            )
            public_result["url"] = url_for("view_source_document", token=token)
            public_result["downloadUrl"] = url_for("download_source_document", token=token)
        return jsonify(public_result)

    def signed_document_reference(token):
        """Return (reference, None) for a valid link, or (None, error response)."""
        user_id = identity_provider()
        if not user_id:
            return None, Response("Authentication is required.", status=401)
        if catalog_service is None:
            return None, Response("The source catalog is not configured.", status=404)
        try:
            reference = source_link_serializer.loads(
                token,
                max_age=application_settings.source_url_ttl_seconds,
            )
        except SignatureExpired:
            return None, Response("This document link has expired.", status=410)
        except BadSignature:
            return None, Response("Invalid document link.", status=400)
        if (
            not isinstance(reference, dict)
            or reference.get("userId") != user_id
            or not isinstance(reference.get("catalogId"), str)
            or not isinstance(reference.get("path"), str)
        ):
            return None, Response("Document access is denied.", status=403)
        return reference, None

    def fetch_document(download_method, reference, not_found=None):
        """Return (download, None), or (None, error response)."""
        try:
            download = download_method(reference["catalogId"], reference["path"])
            if _field(download, "contents") is None:
                raise SourceCatalogError("Databricks returned an empty document")
        except InvalidSourcePathError:
            return None, Response("Invalid document.", status=400)
        except DatabricksAuthenticationError:
            return None, Response("Document access is denied.", status=403)
        except SourceDocumentNotFoundError:
            return None, not_found or Response("Document not found.", status=404)
        except SourceCatalogError:
            return None, Response("Document temporarily unavailable.", status=502)
        return download, None

    @app.get("/documents/<token>")
    def view_source_document(token):
        reference, error = signed_document_reference(token)
        if error:
            return error
        path = reference["path"]
        name = PurePosixPath(path).name
        kind = document_kind(path)
        download_url = url_for("download_source_document", token=token)

        if kind == "word":
            # Word documents are shown from their PDF copy, so cited pages match.
            download, error = fetch_document(
                catalog_service.download_rendition,
                reference,
                not_found=_html_response(render_message(
                    name,
                    "A preview of this Word document is not available yet.",
                    download_url,
                )),
            )
            if error:
                return error
            return _file_response(download, "application/pdf", "inline", f"{name}.pdf")

        download, error = fetch_document(catalog_service.download_document, reference)
        if error:
            return error
        if kind != "excel":
            return _file_response(download, "application/pdf", "inline", name)

        contents = _field(download, "contents")
        try:
            data = contents.read(MAX_SPREADSHEET_PREVIEW_BYTES + 1)
        finally:
            contents.close()
        if len(data) > MAX_SPREADSHEET_PREVIEW_BYTES:
            return _html_response(render_message(
                name, "This workbook is too large to preview.",
                download_url,
            ))
        try:
            sheets = read_workbook(data, PurePosixPath(path).suffix)
        except SpreadsheetError:
            logger.warning("Spreadsheet preview failed", exc_info=True)
            return _html_response(render_message(
                name, "This workbook could not be previewed.",
                download_url,
            ))
        return _html_response(render_workbook(name, sheets, download_url))

    @app.get("/documents/<token>/download")
    def download_source_document(token):
        reference, error = signed_document_reference(token)
        if error:
            return error
        download, error = fetch_document(catalog_service.download_document, reference)
        if error:
            return error
        return _file_response(
            download,
            document_media_type(reference["path"]),
            "attachment",
            PurePosixPath(reference["path"]).name,
        )

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return _error_response(
            "REQUEST_TOO_LARGE", "The request body is too large.", _request_id(), 413
        )

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error, HTTPException):
            return error
        request_id = _request_id()
        started_at = getattr(g, "request_started_at", time.monotonic())
        logger.exception(
            "Unhandled application exception",
            extra={
                "event": "unhandled_exception",
                "request_id": request_id,
                "method": request.method,
                "route": _route_template(),
                "status": 500,
                "duration_ms": round((time.monotonic() - started_at) * 1000),
                "exception_type": type(error).__name__,
            },
        )
        if request.path.startswith("/api/"):
            return _error_response(
                "INTERNAL_ERROR",
                "An unexpected error occurred.",
                request_id,
                500,
            )
        return Response("An unexpected error occurred.", status=500, mimetype="text/plain")

    return app


def start_warm_up(app: Flask) -> Thread | None:
    """Warm Databricks connections in the background so the worker serves at once."""
    warm_up = getattr(app.extensions.get("supervisor_service"), "warm_up", None)
    if not callable(warm_up):
        return None

    def run():
        started_at = time.monotonic()
        try:
            warm_up()
        except Exception as error:
            logger.warning("Warm-up failed; error_type=%s", type(error).__name__)
            return
        logger.info(
            "Warm-up completed; duration_ms=%s",
            round((time.monotonic() - started_at) * 1000),
        )

    thread = Thread(target=run, name="warm-up", daemon=True)
    thread.start()
    return thread


def _accepts_live_events(prepare) -> bool:
    try:
        return "on_event" in inspect.signature(prepare).parameters
    except (TypeError, ValueError):
        return False


INTERIM_RESULT_LEAD = "Here is what I found. Writing up the answer…\n\n"
COACHING360_TIMEOUT_MESSAGE = (
    "This Coaching360 question is taking longer than expected, so I stopped waiting. "
    "Please try again, or ask about one person, branch or month at a time."
)


class AnswerTimeout(Exception):
    """The answer did not arrive within the allowed time."""


def _interim_result(tool, text):
    """A Coaching360 data table to show while the Supervisor writes the answer, or None."""
    if not (str(tool).startswith("coaching360_") and str(tool).endswith("_data")):
        return None
    table = tidy_table(text)
    return INTERIM_RESULT_LEAD + table if table else None


def _prepare_with_live_events(prepare, timings=None, timeout_seconds=None):
    """Run prepare(on_event=...) in a worker thread, yielding progress and checked text.

    Returns the prepared answer; its full output checks still run afterwards.
    When given, timings receives seconds since start for the first "tool"
    call, the tool "result", the first answer "text" and "prepared".
    With timeout_seconds, raises AnswerTimeout when the answer is not ready in
    time (the worker is left to finish in the background; its result is dropped).
    """
    events = queue.Queue()
    result = {}
    started = time.monotonic()
    mark = (lambda name: timings.setdefault(name, round(time.monotonic() - started, 3))) if timings is not None else (lambda name: None)

    def work():
        try:
            result["pending"] = prepare(on_event=lambda kind, value: events.put((kind, value)))
        except BaseException as error:  # re-raised in the request thread below
            result["error"] = error
        finally:
            events.put(None)

    Thread(target=work, name="chat-live", daemon=True).start()
    preview = LivePreview(check=_apply_output_guardrails, mask=_mask_personal_data)
    last_progress = None
    deadline = started + timeout_seconds if timeout_seconds else None
    while True:
        try:
            item = events.get(timeout=max(0.0, deadline - time.monotonic()) if deadline else None)
        except queue.Empty:
            mark("timeout")
            raise AnswerTimeout() from None
        if item is None:
            break
        kind, value = item
        out = []
        if kind == "progress":
            mark("tool")
            text = _progress_message(value)
            if text != last_progress:
                last_progress = text
                out = [("progress", {"message": text})]
        elif kind == "result":
            mark("result")
            interim = _interim_result(*value)
            out = preview.interim(interim) if interim else []
        elif kind == "text":
            mark("text")
            out = preview.feed(value)
        elif kind == "reset":
            out = preview.reset()
        for event, payload in out:
            yield _chat_event(event, payload)
    mark("prepared")
    if "error" in result:
        raise result["error"]
    return result["pending"]


def _milliseconds(marks):
    return {name: round(seconds * 1000) for name, seconds in marks.items()}


def _progress_message(name) -> str:
    """A user-facing activity label; internal agent and tool names are never shown."""
    name = str(name or "").casefold()
    if "coaching360" in name:
        return "Checking the Coaching360 Guide…" if "guide" in name else "Looking up your Coaching360 data…"
    if "handbook" in name:
        return "Checking the Employee Handbook…"
    if "benefit" in name:
        return "Checking the benefits documentation…"
    if "genie" in name or "fast-path" in name:
        return "Looking up performance data…"
    if "perf" in name:
        return "Checking the performance policy…"
    if "policy" in name or "branch" in name:
        return "Checking the branch operations policies…"
    return "Consulting a specialist…"


def _mask_personal_data(text: str) -> str:
    for _category, pattern, replacement in OUTPUT_PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _require_identity(identity_provider):
    if identity_provider():
        return None
    return _error_response(
        "AUTHENTICATION_REQUIRED", "Authentication is required.", _request_id(), 401
    )


def _input_guardrail_reason(message: str) -> str | None:
    """Return a non-sensitive category when an input should not be forwarded."""
    for pattern in SELF_HARM_INPUT_PATTERNS:
        if pattern.search(message):
            return "self_harm"
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(message):
            return "prompt_injection"
    for pattern in PII_GENERATION_PATTERNS:
        if pattern.search(message):
            return "pii_generation"
    for pattern in HATE_OR_ABUSE_INPUT_PATTERNS:
        if pattern.search(message):
            return "hate_or_abuse"
    for pattern in EXPLICIT_OFF_TOPIC_PATTERNS:
        if pattern.search(message):
            return "off_topic"

    command = message.split(maxsplit=1)[0].casefold() if message.split() else ""
    if command in SUPERVISOR_ROUTE_COMMANDS:
        return None
    if SUPPORTED_DOMAIN_PATTERN.search(message):
        return None
    if SAFE_CONVERSATIONAL_PATTERN.search(message):
        return None

    # Preserve short topic phrases such as "PPO" or "jury duty" so the
    # Supervisor can ask a domain-specific clarification when appropriate.
    if len(message.split()) <= 2 and re.fullmatch(r"[\w'’&+./? -]+", message):
        return None
    # Domain vocabulary is an allow signal, not an exhaustive business-topic
    # classifier. Forward unmatched or ambiguous requests to the Supervisor;
    # only the explicit off-topic patterns above are rejected in Flask.
    return None


def _apply_output_guardrails(answer: str) -> tuple[str, tuple[str, ...], bool]:
    """Mask PII and replace outputs containing prohibited internal or binding content."""
    filtered_answer = answer
    categories: list[str] = []
    for category, pattern, replacement in OUTPUT_PII_PATTERNS:
        filtered_answer, replacement_count = pattern.subn(replacement, filtered_answer)
        if replacement_count:
            categories.append(category)

    if any(pattern.search(filtered_answer) for pattern in INTERNAL_DETAIL_PATTERNS):
        categories.append("internal_system_details")
    if any(pattern.search(filtered_answer) for pattern in BINDING_DECISION_PATTERNS):
        categories.append("binding_decision")
    if any(pattern.search(filtered_answer) for pattern in SELF_HARM_OUTPUT_PATTERNS):
        categories.append("unsafe_self_harm")
    if any(pattern.search(filtered_answer) for pattern in HATE_OR_ABUSE_OUTPUT_PATTERNS):
        categories.append("hate_or_abuse")

    output_was_blocked = any(
        category
        in {
            "internal_system_details",
            "binding_decision",
            "unsafe_self_harm",
            "hate_or_abuse",
        }
        for category in categories
    )
    if output_was_blocked:
        if "unsafe_self_harm" in categories:
            return SELF_HARM_SUPPORT_MESSAGE, tuple(categories), True
        return OUTPUT_GUARDRAIL_FALLBACK, tuple(categories), True
    return filtered_answer, tuple(categories), False


def _request_id() -> str:
    return getattr(g, "request_id", str(uuid4()))


def _route_template() -> str:
    return request.url_rule.rule if request.url_rule is not None else "<unmatched>"


def _reported_usage(usage):
    """Return usage only when the serving endpoint reported a non-zero count."""
    if usage is None:
        return None
    if usage.input_tokens or usage.output_tokens or usage.total_tokens:
        return usage
    return None


def _file_response(download, mimetype: str, disposition: str, filename: str) -> Response:
    contents = _field(download, "contents")

    def stream_file():
        try:
            while chunk := contents.read(64 * 1024):
                yield chunk
        finally:
            contents.close()

    response = Response(stream_file(), mimetype=mimetype)
    response.headers.set("Content-Disposition", disposition, filename=filename)
    content_length = _field(download, "content_length")
    if content_length is not None:
        response.content_length = content_length
    last_modified = _field(download, "last_modified")
    if last_modified:
        response.headers["Last-Modified"] = str(last_modified)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _html_response(html: str) -> Response:
    response = Response(html, mimetype="text/html")
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _is_uuid(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
    except (ValueError, AttributeError):
        return False
    return True


def _chat_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _error_response(code: str, message: str, request_id: str, status_code: int):
    return jsonify(error={"code": code, "message": message}, requestId=request_id), status_code


def _citation_recovery_message(message: str) -> str:
    command = message.split(maxsplit=1)[0].casefold() if message else ""
    examples = {
        "/policy": '/policy What does the policy say about paid loan file retention?',
        "/handbook": '/handbook What does the handbook say about jury duty leave?',
        "/benefits": '/benefits How many PTO hours do full-time employees receive?',
        "/benfits": '/benefits How many PTO hours do full-time employees receive?',
        "/performance": '/performance What do the performance ratings from 1 to 5 mean?',
    }
    example = examples.get(command)
    direct_option = (
        f'1. Ask a more specific question, for example: "{example}"'
        if example
        else "1. Route directly with /policy, /handbook, /benefits, or /performance and ask a specific question."
    )
    return (
        "I found a response, but could not match it to an approved source document, "
        "so I did not display it as verified policy.\n\nOptions:\n"
        f"{direct_option}\n"
        "2. Rephrase the question with the policy topic, employee group, state, or benefit name.\n"
        "3. Use Employee resources to search and open the approved documents directly."
    )


def _public_source(source, catalog_service) -> dict:
    public = {
        "number": source.number,
        "label": source.label,
        **({"domain": source.domain} if source.domain else {}),
        **({"page": source.page} if source.page else {}),
        **({"url": source.url} if source.url else {}),
    }
    reference = catalog_service.reference_for_location(source.location) if catalog_service else None
    if reference:
        public["catalog"] = reference
    return public


DEFAULT_SPECIALIST_QUESTION = (
    "Introduce the topics you support and ask me for my specific question."
)
CHART_REQUEST_PATTERN = re.compile(
    r"\b(?:chart|graph|plot|visualize|visualise|visualization)\b", re.IGNORECASE
)
CHART_FORMAT_REQUIREMENT = (
    "\n\nApplication chart format requirement: Include exactly one fenced code "
    "block whose language is mariner-chart. The block must contain strict JSON "
    "with this shape: {\"type\":\"bar\",\"title\":\"Chart title\","
    "\"xLabel\":\"Category label\",\"yLabel\":\"Metric label\","
    "\"unit\":\"optional unit\",\"labels\":[\"A\",\"B\"],"
    "\"values\":[1,2]}. Use a bar chart, 1 to 30 labels, finite "
    "non-negative numeric values, and matching label/value counts. Base the "
    "chart only on grounded data from the current answer or conversation. Do "
    "not claim that a chart was created unless this block is present. A short "
    "written interpretation may follow the block."
)
TABLE_FORMAT_REQUIREMENT = (
    "\n\nApplication table format requirement: Return a valid Markdown table. "
    "Put each column heading in its own cell, include a separator row with the "
    "same number of cells, and keep every data row at that same column count."
)


def _supervisor_input(message: str) -> str:
    command, _, question = message.strip().partition(" ")
    specialist = SUPERVISOR_ROUTE_COMMANDS.get(command.casefold())
    if specialist is None:
        supervisor_message = message
    else:
        employee_question = question.strip() or DEFAULT_SPECIALIST_QUESTION
        supervisor_message = (
            f"Mandatory application routing directive: Call the {specialist} "
            "subagent/tool now and wait for it to complete. Return the worker's final "
            "grounded answer and source information. Do not merely announce that you "
            "will query, consult, or route to the specialist. Do not answer from general "
            "model knowledge and do not route to a different specialist. "
            f"Employee question: {employee_question}"
        )

    if CHART_REQUEST_PATTERN.search(message):
        supervisor_message += CHART_FORMAT_REQUIREMENT

    if re.search(r"\btable\b", message, re.IGNORECASE):
        supervisor_message += TABLE_FORMAT_REQUIREMENT

    return supervisor_message


def _direct_route(message: str) -> tuple[str, str] | None:
    """Return (command, specialist question) when a slash command can skip the Supervisor.

    Chart requests stay on the Supervisor route, which produces the mariner-chart block.
    """
    command, _, question = message.strip().partition(" ")
    command = command.casefold()
    if command not in SUPERVISOR_ROUTE_COMMANDS or CHART_REQUEST_PATTERN.search(message):
        return None
    specialist_question = question.strip() or DEFAULT_SPECIALIST_QUESTION
    if re.search(r"\btable\b", message, re.IGNORECASE):
        specialist_question += TABLE_FORMAT_REQUIREMENT
    return ("/benefits" if command == "/benfits" else command), specialist_question


def _has_direct_route(message: str) -> bool:
    command = message.strip().partition(" ")[0].casefold()
    return command in SUPERVISOR_ROUTE_COMMANDS


def _supervisor_session_id(user_id: str, conversation_id: str) -> str:
    return sha256(f"{user_id}:{conversation_id}".encode("utf-8")).hexdigest()


def _is_timeout_error(error: Exception) -> bool:
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, TimeoutError) or "timeout" in type(current).__name__.casefold():
            return True
        current = current.__cause__ or current.__context__
    return False
