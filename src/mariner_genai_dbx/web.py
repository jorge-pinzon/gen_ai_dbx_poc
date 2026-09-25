"""Flask application and stable HTTP API for the Databricks frontend."""

from __future__ import annotations

import logging
import hmac
import re
import secrets
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import PurePosixPath
from threading import Lock
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
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.security import check_password_hash

from .analytics import ChatLogEvent
from .bootstrap import (
    create_analytics_service,
    create_conversation_persistence,
    create_source_catalog_service,
    create_supervisor_service,
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
    SupervisorInvocationError,
)
from .models import ConversationHistory, ConversationTurn
from .logging_config import configure_logging


MAX_REQUEST_BYTES = 16 * 1024
READINESS_CACHE_SECONDS = 30
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
    "/coaching": "Employee Performance Agent",
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
    analytics_service=None,
    identity_provider=None,
    readiness_cache: ReadinessCache | None = None,
) -> Flask:
    application_settings = settings or load_settings()
    configure_logging(application_settings.log_level)
    service = supervisor_service or create_supervisor_service(application_settings)
    analytics = analytics_service or create_analytics_service(application_settings)
    persistence = conversation_persistence or create_conversation_persistence(
        application_settings
    )
    catalog_service = source_catalog_service
    if catalog_service is None:
        catalog_service = create_source_catalog_service(application_settings)
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
    )
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
        logger.info(
            "HTTP request completed",
            extra={
                "event": "http_request_completed",
                "request_id": request_id,
                "method": request.method,
                "route": _route_template(),
                "status": response.status_code,
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
            password_matches = check_password_hash(
                application_settings.login_password_hash or "", password
            )
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
            status, *, answer="", sources=(), agents_used=(), error_message="", usage=None
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

        try:
            # Explicit slash commands are authoritative one-shot routes. Do not
            # let prior cross-domain turns bias the selected specialist's answer;
            # the completed turn is still persisted in the current conversation.
            supervisor_history = (
                ConversationHistory() if _has_direct_route(message) else history
            )
            result = service.answer(
                _supervisor_input(message),
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
        return jsonify(public_result)

    @app.get("/documents/<token>")
    def view_source_document(token):
        user_id = identity_provider()
        if not user_id:
            return Response("Authentication is required.", status=401)
        if catalog_service is None:
            return Response("The source catalog is not configured.", status=404)
        try:
            reference = source_link_serializer.loads(
                token,
                max_age=application_settings.source_url_ttl_seconds,
            )
        except SignatureExpired:
            return Response("This document link has expired.", status=410)
        except BadSignature:
            return Response("Invalid document link.", status=400)
        if (
            not isinstance(reference, dict)
            or reference.get("userId") != user_id
            or not isinstance(reference.get("catalogId"), str)
            or not isinstance(reference.get("path"), str)
        ):
            return Response("Document access is denied.", status=403)
        try:
            download = catalog_service.download_document(
                reference["catalogId"], reference["path"]
            )
            contents = _field(download, "contents")
            if contents is None:
                raise SourceCatalogError("Databricks returned an empty document")
        except InvalidSourcePathError:
            return Response("Invalid document.", status=400)
        except DatabricksAuthenticationError:
            return Response("Document access is denied.", status=403)
        except SourceCatalogError:
            return Response("Document temporarily unavailable.", status=502)

        def stream_file():
            try:
                while chunk := contents.read(64 * 1024):
                    yield chunk
            finally:
                contents.close()

        response = Response(stream_file(), mimetype="application/pdf")
        response.headers.set(
            "Content-Disposition",
            "inline",
            filename=PurePosixPath(reference["path"]).name,
        )
        content_length = _field(download, "content_length")
        if content_length is not None:
            response.content_length = content_length
        last_modified = _field(download, "last_modified")
        if last_modified:
            response.headers["Last-Modified"] = str(last_modified)
        response.headers["Cache-Control"] = "private, no-store"
        return response

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


def _error_response(code: str, message: str, request_id: str, status_code: int):
    return jsonify(error={"code": code, "message": message}, requestId=request_id), status_code


def _citation_recovery_message(message: str) -> str:
    command = message.split(maxsplit=1)[0].casefold() if message else ""
    examples = {
        "/policy": '/policy What does the policy say about paid loan file retention?',
        "/handbook": '/handbook What does the handbook say about jury duty leave?',
        "/benefits": '/benefits How many PTO hours do full-time employees receive?',
        "/benfits": '/benefits How many PTO hours do full-time employees receive?',
        "/coaching": '/coaching What do the performance ratings from 1 to 5 mean?',
    }
    example = examples.get(command)
    direct_option = (
        f'1. Ask a more specific question, for example: "{example}"'
        if example
        else "1. Route directly with /policy, /handbook, /benefits, or /coaching and ask a specific question."
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


def _supervisor_input(message: str) -> str:
    command, _, question = message.strip().partition(" ")
    specialist = SUPERVISOR_ROUTE_COMMANDS.get(command.casefold())
    if specialist is None:
        supervisor_message = message
    else:
        employee_question = question.strip() or (
            "Introduce the topics you support and ask me for my specific question."
        )
        supervisor_message = (
            f"Mandatory application routing directive: Call the {specialist} "
            "subagent/tool now and wait for it to complete. Return the worker's final "
            "grounded answer and source information. Do not merely announce that you "
            "will query, consult, or route to the specialist. Do not answer from general "
            "model knowledge and do not route to a different specialist. "
            f"Employee question: {employee_question}"
        )

    if re.search(
        r"\b(?:chart|graph|plot|visualize|visualise|visualization)\b",
        message,
        re.IGNORECASE,
    ):
        supervisor_message += (
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

    if re.search(r"\btable\b", message, re.IGNORECASE):
        supervisor_message += (
            "\n\nApplication table format requirement: Return a valid Markdown table. "
            "Put each column heading in its own cell, include a separator row with the "
            "same number of cells, and keep every data row at that same column count."
        )

    return supervisor_message


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
