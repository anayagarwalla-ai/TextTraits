from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(os.getenv("TEXTTRAITS_LOG_LEVEL", "INFO").upper())
    root.handlers.clear()

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=int(os.getenv("TEXTTRAITS_LOG_MAX_BYTES", "10485760")),
        backupCount=int(os.getenv("TEXTTRAITS_LOG_BACKUPS", "5")),
    )
    console_handler = logging.StreamHandler()
    if os.getenv("TEXTTRAITS_LOG_JSON", "false").strip().lower() in {"1", "true", "yes", "on"}:
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


def init_error_reporting(app=None) -> dict[str, Any]:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return {"provider": "not_configured", "configured": False}
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except ImportError:
        logging.warning("SENTRY_DSN is set, but sentry-sdk is not installed.")
        return {"provider": "sentry", "configured": False, "error": "missing_dependency"}

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        environment=os.getenv("TEXTTRAITS_ENV", "production"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        send_default_pii=False,
    )
    if app is not None:
        app.config["SENTRY_CONFIGURED"] = True
    return {"provider": "sentry", "configured": True}
