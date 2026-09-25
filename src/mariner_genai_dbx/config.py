"""Validated configuration for the Databricks multi-agent application."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .errors import ConfigurationError
from .models import CitationTableConfig, SupervisorConfig, VolumeCatalog


APPLICATION_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOTENV_PATH = APPLICATION_ROOT / ".env"
ALLOWED_DOTENV_SETTINGS = {
    "APP_VERSION",
    "APP_ENV",
    "AUTH_MODE",
    "CHAT_HISTORY_LIMIT",
    "CHAT_SESSION_TTL_SECONDS",
    "DATABRICKS_HOST",
    "DATABRICKS_LOG_TABLE",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
    "DATABRICKS_TOKEN",
    "DATABRICKS_WAREHOUSE_ID",
    "LOGIN_PASSWORD_HASH",
    "LOGIN_USERNAME",
    "LOG_LEVEL",
    "MAX_MESSAGE_CHARACTERS",
    "REQUEST_TIMEOUT_SECONDS",
    "SESSION_SECRET_KEY",
    "SOURCE_URL_TTL_SECONDS",
    "SUPERVISOR_ENDPOINT",
    "DATABRICKS_SUPERVISOR_ENDPOINT",
    "SUPERVISOR_MODE",
    "VOLUME_CATALOGS_JSON",
}

CITATION_TABLES = (
    CitationTableConfig(
        table_name="workspace.default.branch_operations_chunks",
        domain="Branch Operations",
        source_label_aliases=(
            ("Record Retention", "BRANCH_OPERATIONS_RECORD_RETENTION"),
            ("Record Retention Policy", "BRANCH_OPERATIONS_RECORD_RETENTION"),
            (
                "Branch Record Retention Policy",
                "BRANCH_OPERATIONS_RECORD_RETENTION",
            ),
            (
                "Branch Operations Record Retention Policy",
                "BRANCH_OPERATIONS_RECORD_RETENTION",
            ),
        ),
    ),
    CitationTableConfig(
        table_name="workspace.default.employee_handbook_chunks",
        domain="Employee Handbook",
    ),
    CitationTableConfig(
        table_name="workspace.default.benefits_chunks",
        domain="Employee Benefits",
    ),
    CitationTableConfig(
        table_name="workspace.performance_test.app_policy_chunks",
        domain="Employee Performance Policy",
        document_title_column="document_name",
        volume_path_column="source_volume_path",
        page_number_column="page_start",
        chunk_text_column="chunk_text",
        source_label_aliases=(
            (
                "Employee Performance Management Policy",
                "INSTRUCTIONS_PERFORMANCE.pdf",
            ),
            ("Employee Performance Policy", "INSTRUCTIONS_PERFORMANCE.pdf"),
        ),
    ),
)


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    app_version: str = "development"
    auth_mode: str = "local"
    supervisor_mode: str = "mock"
    log_level: str = "INFO"
    login_username: str | None = field(default=None, repr=False)
    login_password_hash: str | None = field(default=None, repr=False)
    databricks_host: str | None = field(default=None, repr=False)
    databricks_token: str | None = field(default=None, repr=False)
    databricks_client_id: str | None = field(default=None, repr=False)
    databricks_client_secret: str | None = field(default=None, repr=False)
    databricks_warehouse_id: str | None = None
    databricks_log_table: str = "workspace.default.flask_app_logs"
    supervisor_endpoint: str | None = None
    session_secret_key: str | None = field(default=None, repr=False)
    request_timeout_seconds: int = 60
    source_url_ttl_seconds: int = 300
    max_message_characters: int = 4000
    chat_history_limit: int = 20
    chat_session_ttl_seconds: int = 1800
    volume_catalogs: tuple[VolumeCatalog, ...] = field(default=(), repr=False)
    citation_tables: tuple[CitationTableConfig, ...] = CITATION_TABLES

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def supervisor_config(self) -> SupervisorConfig:
        if not self.databricks_host or not self.supervisor_endpoint:
            raise ConfigurationError(
                "DATABRICKS_HOST and SUPERVISOR_ENDPOINT are required in Databricks mode"
            )
        return SupervisorConfig(
            workspace_host=self.databricks_host,
            endpoint_name=self.supervisor_endpoint,
            token=self.databricks_token,
            client_id=self.databricks_client_id,
            client_secret=self.databricks_client_secret,
            request_timeout_seconds=self.request_timeout_seconds,
        )


def load_settings(
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> Settings:
    process_environment = dict(os.environ if environ is None else environ)
    process_app_env = process_environment.get("APP_ENV", "development").strip().lower()
    dotenv_values = {}
    if environ is None and process_app_env != "production":
        dotenv_values = _read_allowed_dotenv(dotenv_path or DEFAULT_DOTENV_PATH)
    values = {**dotenv_values, **process_environment}

    settings = Settings(
        app_env=values.get("APP_ENV", "development").strip().lower(),
        app_version=values.get("APP_VERSION", "development").strip(),
        auth_mode=values.get("AUTH_MODE", "local").strip().lower(),
        supervisor_mode=values.get("SUPERVISOR_MODE", "mock").strip().lower(),
        log_level=values.get("LOG_LEVEL", "INFO").strip().upper(),
        login_username=_optional(values, "LOGIN_USERNAME"),
        login_password_hash=_optional(values, "LOGIN_PASSWORD_HASH"),
        databricks_host=_optional(values, "DATABRICKS_HOST"),
        databricks_token=_optional(values, "DATABRICKS_TOKEN"),
        databricks_client_id=_optional(values, "DATABRICKS_CLIENT_ID"),
        databricks_client_secret=_optional(values, "DATABRICKS_CLIENT_SECRET"),
        databricks_warehouse_id=_optional(values, "DATABRICKS_WAREHOUSE_ID"),
        databricks_log_table=(
            _optional(values, "DATABRICKS_LOG_TABLE")
            or "workspace.default.flask_app_logs"
        ),
        supervisor_endpoint=(
            _optional(values, "DATABRICKS_SUPERVISOR_ENDPOINT")
            or _optional(values, "SUPERVISOR_ENDPOINT")
        ),
        session_secret_key=_optional(values, "SESSION_SECRET_KEY"),
        request_timeout_seconds=_integer(values, "REQUEST_TIMEOUT_SECONDS", 60, minimum=1),
        source_url_ttl_seconds=_integer(
            values, "SOURCE_URL_TTL_SECONDS", 300, minimum=60, maximum=900
        ),
        max_message_characters=_integer(
            values, "MAX_MESSAGE_CHARACTERS", 4000, minimum=1
        ),
        chat_history_limit=_integer(values, "CHAT_HISTORY_LIMIT", 20, minimum=1),
        chat_session_ttl_seconds=_integer(
            values, "CHAT_SESSION_TTL_SECONDS", 1800, minimum=60
        ),
        volume_catalogs=_volume_catalogs(values.get("VOLUME_CATALOGS_JSON", "[]")),
    )
    _validate_settings(settings)
    return settings


def _validate_settings(settings: Settings) -> None:
    if settings.app_env not in {"development", "test", "production"}:
        raise ConfigurationError("APP_ENV must be development, test, or production")
    if settings.auth_mode not in {"local", "password", "databricks"}:
        raise ConfigurationError("AUTH_MODE must be local, password, or databricks")
    if settings.supervisor_mode not in {"mock", "databricks"}:
        raise ConfigurationError("SUPERVISOR_MODE must be mock or databricks")
    if settings.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError(
            "LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"
        )
    if not settings.app_version or len(settings.app_version) > 100:
        raise ConfigurationError("APP_VERSION must contain 1-100 characters")
    if not re.fullmatch(
        r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+",
        settings.databricks_log_table,
    ):
        raise ConfigurationError("DATABRICKS_LOG_TABLE must be fully qualified")
    if settings.auth_mode == "password":
        if not settings.login_username:
            raise ConfigurationError("Password authentication requires LOGIN_USERNAME")
        if not settings.login_password_hash:
            raise ConfigurationError(
                "Password authentication requires LOGIN_PASSWORD_HASH"
            )
        if not settings.session_secret_key or len(settings.session_secret_key) < 32:
            raise ConfigurationError(
                "Password authentication requires SESSION_SECRET_KEY with at least 32 characters"
            )
    if settings.supervisor_mode == "databricks":
        settings.supervisor_config()
        if not settings.databricks_host.startswith("https://"):
            raise ConfigurationError("DATABRICKS_HOST must be an HTTPS workspace URL")
        if not settings.databricks_token and not (
            settings.databricks_client_id and settings.databricks_client_secret
        ):
            raise ConfigurationError(
                "Databricks mode requires DATABRICKS_CLIENT_ID and "
                "DATABRICKS_CLIENT_SECRET"
            )
    if settings.is_production:
        if settings.auth_mode != "databricks":
            raise ConfigurationError("Production requires AUTH_MODE=databricks")
        if settings.supervisor_mode != "databricks":
            raise ConfigurationError("Production cannot use the mock Supervisor")
        if settings.databricks_token:
            raise ConfigurationError(
                "Production must use workload identity, not DATABRICKS_TOKEN"
            )
        if not settings.session_secret_key or len(settings.session_secret_key) < 32:
            raise ConfigurationError(
                "Production requires SESSION_SECRET_KEY with at least 32 characters"
            )


def _read_allowed_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator:
            raise ConfigurationError(f"Invalid .env syntax on line {line_number}")
        if key not in ALLOWED_DOTENV_SETTINGS:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def _volume_catalogs(raw_value: str) -> tuple[VolumeCatalog, ...]:
    try:
        records = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ConfigurationError("VOLUME_CATALOGS_JSON must be valid JSON") from error
    if not isinstance(records, list):
        raise ConfigurationError("VOLUME_CATALOGS_JSON must be a JSON array")

    catalogs: list[VolumeCatalog] = []
    seen_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ConfigurationError("Each Volume catalog must be a JSON object")
        catalog_id = record.get("id")
        label = record.get("label")
        volume_path = record.get("volumePath")
        if not isinstance(catalog_id, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9-]{1,39}", catalog_id
        ):
            raise ConfigurationError("Volume catalog ids must use lowercase kebab-case")
        if catalog_id in seen_ids:
            raise ConfigurationError("Volume catalog ids must be unique")
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 80:
            raise ConfigurationError("Volume catalog labels must be 1-80 characters")
        if not isinstance(volume_path, str) or not volume_path.startswith("/Volumes/"):
            raise ConfigurationError("Volume catalog paths must start with /Volumes/")
        catalogs.append(VolumeCatalog(catalog_id, label.strip(), volume_path.rstrip("/")))
        seen_ids.add(catalog_id)
    return tuple(catalogs)


def _optional(values: Mapping[str, str], name: str) -> str | None:
    value = values.get(name, "").strip()
    return value or None


def _integer(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    raw_value = values.get(name)
    try:
        value = default if raw_value is None or not raw_value.strip() else int(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer") from error
    if value < minimum or (maximum is not None and value > maximum):
        boundary = f"between {minimum} and {maximum}" if maximum else f"at least {minimum}"
        raise ConfigurationError(f"{name} must be {boundary}")
    return value
