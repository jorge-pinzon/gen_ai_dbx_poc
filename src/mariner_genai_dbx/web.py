"""Flask application and stable HTTP API for the Databricks frontend."""

from __future__ import annotations

import logging
import hmac
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
from .models import ConversationTurn
from .logging_config import configure_logging


MAX_REQUEST_BYTES = 16 * 1024
READINESS_CACHE_SECONDS = 30
LOCAL_USER_ID = "local-development-user"
logger = logging.getLogger(__name__)
SUPERVISOR_ROUTE_COMMANDS = {
    "/policy": "Branch Operations Agent",
    "/benfits": "Benefits Agent",
    "/benefits": "Benefits Agent",
    "/handbook": "Employee Handbook Agent",
}


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
            result = service.answer(
                _supervisor_input(message),
                session_id,
                history,
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

        turn = ConversationTurn(
            conversation_id=conversation_id,
            request_id=request_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            question=message,
            answer=result.answer,
            sources=result.sources,
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
            answer=result.answer,
            sources=result.sources,
            agents_used=result.agents_used,
            usage=_reported_usage(result.usage),
        )
        return jsonify(
            conversationId=conversation_id,
            requestId=request_id,
            answer=result.answer,
            sources=[_public_source(source, catalog_service) for source in result.sources],
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
    }
    example = examples.get(command)
    direct_option = (
        f'1. Ask a more specific question, for example: "{example}"'
        if example
        else "1. Route directly with /policy, /handbook, or /benefits and ask a specific question."
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
        return message
    employee_question = question.strip() or (
        "Introduce the topics you support and ask me for my specific question."
    )
    return (
        f"Mandatory application routing directive: Call the {specialist} "
        "subagent/tool now and wait for it to complete. Return the worker's final "
        "grounded answer and source information. Do not merely announce that you "
        "will query, consult, or route to the specialist. Do not answer from general "
        "model knowledge and do not route to a different specialist. "
        f"Employee question: {employee_question}"
    )


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
