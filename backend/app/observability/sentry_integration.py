"""Sentry-style error tracking V5.9 dual-mode.

Mode :
  - Si SENTRY_DSN present : push vers Sentry Cloud via sentry-sdk
    (import lazy pour eviter la dep si absent)
  - Sinon : append vers /var/log/uba/errors-capture.jsonl (local)

Features :
  - PII scrubbing (email, telephone DZ)
  - Breadcrumbs context (tenant_id, domain_id, correlation_id)
  - Fingerprinting pour grouping
  - Ignore patterns (ClientDisconnected, BrokenPipe)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("uba.observability.sentry")


_DEFAULT_LOG_DIR = os.environ.get("UBA_SENTRY_LOG_DIR",
                                    str(Path(tempfile.gettempdir()) / "uba_sentry"))


# Exceptions a ignorer (noise)
IGNORE_EXCEPTIONS = {
    "ClientDisconnectedError",
    "BrokenPipeError",
    "ConnectionResetError",
    "KeyboardInterrupt",
    "SystemExit",
    "asyncio.CancelledError",
}


# PII regex patterns
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_DZ_RE = re.compile(r"\b(?:\+?213|0)[567]\d{8}\b")
_NIF_DZ_RE = re.compile(r"\b\d{15}\b")


def scrub_pii(text: str) -> str:
    """Masque emails + telephones DZ + NIF."""
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PHONE_DZ_RE.sub("[PHONE]", text)
    text = _NIF_DZ_RE.sub("[NIF]", text)
    return text


@dataclass
class ErrorEvent:
    exc_type: str
    message: str
    stack: str
    fingerprint: str
    level: str = "error"
    tenant_id: str | None = None
    user_id: str | None = None
    domain_id: str | None = None
    correlation_id: str | None = None
    release: str | None = None
    environment: str = "development"
    extra: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps({
            "timestamp": self.timestamp,
            "level": self.level,
            "exc_type": self.exc_type,
            "message": self.message,
            "stack": self.stack,
            "fingerprint": self.fingerprint,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "domain_id": self.domain_id,
            "correlation_id": self.correlation_id,
            "release": self.release,
            "environment": self.environment,
            "extra": self.extra,
        }, default=str)


@dataclass
class SentryConfig:
    dsn: str | None = None
    environment: str = "development"
    release: str | None = None
    sample_rate: float = 1.0
    log_file_path: str = _DEFAULT_LOG_DIR + "/errors-capture.jsonl"

    @classmethod
    def from_env(cls) -> "SentryConfig":
        return cls(
            dsn=os.environ.get("SENTRY_DSN") or None,
            environment=os.environ.get("SENTRY_ENV", "development"),
            release=os.environ.get("SENTRY_RELEASE",
                                     os.environ.get("UBA_VERSION")),
            sample_rate=float(os.environ.get("SENTRY_SAMPLE_RATE", "1.0")),
            log_file_path=os.environ.get("UBA_SENTRY_LOG_FILE",
                                           _DEFAULT_LOG_DIR + "/errors-capture.jsonl"),
        )

    @property
    def mode(self) -> str:
        return "cloud" if self.dsn else "file"


class SentryIntegration:
    """Capture + push erreurs avec fallback fichier local."""

    _instance: "SentryIntegration | None" = None

    def __init__(self, config: SentryConfig | None = None) -> None:
        self.config = config or SentryConfig.from_env()
        if self.config.mode == "file":
            Path(self.config.log_file_path).parent.mkdir(
                parents=True, exist_ok=True,
            )
        self._sdk_client: Any | None = None
        if self.config.mode == "cloud":
            self._init_sdk()

    @classmethod
    def instance(cls) -> "SentryIntegration":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_sdk(self) -> None:
        try:
            import sentry_sdk  # type: ignore[import-not-found]
            sentry_sdk.init(
                dsn=self.config.dsn,
                environment=self.config.environment,
                release=self.config.release,
                sample_rate=self.config.sample_rate,
                before_send=self._before_send_hook,
            )
            self._sdk_client = sentry_sdk
            logger.info("Sentry SDK initialized (env=%s)",
                         self.config.environment)
        except ImportError:
            logger.warning(
                "sentry-sdk not installed, falling back to file mode",
            )
            self.config.dsn = None

    def _before_send_hook(self, event: dict[str, Any], hint: Any) -> dict[str, Any] | None:
        """Sentry SDK hook : PII scrubbing + ignore noise."""
        exc_info = hint.get("exc_info") if isinstance(hint, dict) else None
        if exc_info:
            exc_name = exc_info[0].__name__ if exc_info[0] else ""
            if exc_name in IGNORE_EXCEPTIONS:
                return None
        # Scrub PII recursively
        _scrub_dict(event)
        return event

    def capture(
        self,
        exc: BaseException | None = None,
        message: str | None = None,
        level: str = "error",
        tenant_id: str | None = None,
        user_id: str | None = None,
        domain_id: str | None = None,
        correlation_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str | None:
        """Capture une exception ou un message. Retourne event_id ou None."""
        if exc is None and message is None:
            return None

        exc_type = type(exc).__name__ if exc else "LogMessage"
        if exc_type in IGNORE_EXCEPTIONS:
            return None

        if exc is not None:
            msg = scrub_pii(str(exc))
            stack = scrub_pii("".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__),
            ))
        else:
            msg = scrub_pii(message or "")
            stack = ""

        fingerprint = hashlib.sha256(
            f"{exc_type}::{msg[:200]}".encode("utf-8"),
        ).hexdigest()[:16]

        event = ErrorEvent(
            exc_type=exc_type, message=msg, stack=stack,
            fingerprint=fingerprint, level=level,
            tenant_id=tenant_id, user_id=user_id, domain_id=domain_id,
            correlation_id=correlation_id,
            release=self.config.release,
            environment=self.config.environment,
            extra={k: scrub_pii(str(v)) for k, v in (extra or {}).items()},
        )

        if self.config.mode == "cloud" and self._sdk_client is not None:
            try:
                with self._sdk_client.push_scope() as scope:
                    if tenant_id:
                        scope.set_tag("tenant_id", tenant_id)
                    if user_id:
                        scope.set_user({"id": user_id})
                    if domain_id:
                        scope.set_tag("domain_id", domain_id)
                    if correlation_id:
                        scope.set_tag("correlation_id", correlation_id)
                    scope.fingerprint = [fingerprint]
                    if exc is not None:
                        event_id = self._sdk_client.capture_exception(exc)
                    else:
                        event_id = self._sdk_client.capture_message(
                            msg, level=level,
                        )
                return str(event_id) if event_id else None
            except Exception as sentry_exc:
                logger.warning("sentry cloud push failed: %s", sentry_exc)
                # Fallback file

        return self._write_file(event)

    def _write_file(self, event: ErrorEvent) -> str:
        path = Path(self.config.log_file_path)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(event.to_json() + "\n")
        return event.fingerprint

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Lecture fichier local (mode file only)."""
        path = Path(self.config.log_file_path)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out

    def grouped_issues(self, limit: int = 50) -> list[dict[str, Any]]:
        """Groupe par fingerprint comme Sentry."""
        events = self.list_recent(limit=1000)
        groups: dict[str, dict[str, Any]] = {}
        for e in events:
            fp = e.get("fingerprint", "unknown")
            if fp not in groups:
                groups[fp] = {
                    "fingerprint": fp,
                    "exc_type": e["exc_type"],
                    "message": e["message"],
                    "count": 0,
                    "last_seen": e["timestamp"],
                    "first_seen": e["timestamp"],
                    "level": e.get("level", "error"),
                }
            groups[fp]["count"] += 1
            groups[fp]["last_seen"] = max(groups[fp]["last_seen"],
                                            e["timestamp"])
            groups[fp]["first_seen"] = min(groups[fp]["first_seen"],
                                             e["timestamp"])
        return sorted(groups.values(), key=lambda g: -g["count"])[:limit]


def _scrub_dict(obj: Any) -> None:
    """Scrub PII in-place recursively."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = scrub_pii(v)
            else:
                _scrub_dict(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = scrub_pii(v)
            else:
                _scrub_dict(v)
