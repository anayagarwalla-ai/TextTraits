from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, render_template, request

from demo_predictor import DemoPredictor
from predictor import DEFAULT_MODEL_PATH, TextTraitsPredictor


class MissingPredictor:
    is_demo = False
    metrics = {}
    metadata = {
        "model_path": str(DEFAULT_MODEL_PATH),
        "bundle_format": "unavailable",
        "model_count": 0,
        "targets": [],
        "metrics": {},
        "trained_at": "Unknown",
        "dataset": "Unknown",
    }

    def __init__(self, error: Exception) -> None:
        self.error = error

    def predict(self, text: str) -> dict:
        raise RuntimeError(
            f"Runtime model is unavailable at {DEFAULT_MODEL_PATH}. Run `python scripts/setup_models.py` or enable demo mode."
        ) from self.error


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


ENABLE_DEV_TOOLS = env_flag("ENABLE_DEV_TOOLS", False)
PRODUCTION = os.getenv("TEXTTRAITS_ENV", "").strip().lower() == "production"
ALLOW_STANDALONE_PRODUCTION = env_flag("TEXTTRAITS_STANDALONE_PRODUCTION_OK", False)
ALLOW_DEMO_MODE = env_flag("TEXTTRAITS_ALLOW_DEMO", False)
MAX_TEXT_WORDS = int(os.getenv("TEXTTRAITS_MAX_TEXT_WORDS", "1800"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("TEXTTRAITS_RATE_LIMIT_PER_MINUTE", "80"))

if PRODUCTION and not ALLOW_STANDALONE_PRODUCTION:
    raise RuntimeError(
        "The legacy accessible-text-inference-app is not configured for production. "
        "Deploy texttraits_app, or set TEXTTRAITS_STANDALONE_PRODUCTION_OK=true after a dedicated review."
    )
if PRODUCTION and (ENABLE_DEV_TOOLS or ALLOW_DEMO_MODE):
    raise RuntimeError("ENABLE_DEV_TOOLS and TEXTTRAITS_ALLOW_DEMO must be false in production.")

AVAILABLE_MODELS = [
    {
        "id": "local",
        "name": "Local inference model",
        "available": True,
        "description": "Runtime model bundle",
    },
    {
        "id": "pandora_cloud",
        "name": "PANDORA cloud-trained",
        "available": False,
        "description": "Cloud model placeholder",
    },
]


try:
    predictor = TextTraitsPredictor()
except FileNotFoundError as error:
    predictor = DemoPredictor(error) if ALLOW_DEMO_MODE else MissingPredictor(error)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = ENABLE_DEV_TOOLS
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("TEXTTRAITS_MAX_CONTENT_LENGTH", "1000000"))
rate_buckets: dict[str, deque[float]] = defaultdict(deque)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    return response


def request_allowed() -> bool:
    key = f"{request.remote_addr or 'local'}:{request.endpoint or 'unknown'}"
    now = time.time()
    bucket = rate_buckets[key]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        return False
    bucket.append(now)
    return True


def public_model_info() -> dict:
    return {
        "available": not isinstance(predictor, MissingPredictor),
        "demo": bool(getattr(predictor, "is_demo", False)),
        "name": "Demo predictor" if getattr(predictor, "is_demo", False) else "Local inference model",
        "target_count": len(getattr(predictor, "metadata", {}).get("targets", [])),
    }


@app.get("/")
def index():
    return render_template(
        "index.html",
        metrics=predictor.metrics,
        model_info=predictor.metadata,
        public_model_info=public_model_info(),
        available_models=AVAILABLE_MODELS,
        dev_tools_enabled=ENABLE_DEV_TOOLS,
    )


@app.get("/health")
def health():
    return jsonify({"ok": not isinstance(predictor, MissingPredictor)})


@app.get("/dev/model")
def dev_model():
    if not ENABLE_DEV_TOOLS:
        return jsonify({"error": "Developer tools are disabled."}), 404
    return jsonify({"metadata": predictor.metadata, "metrics": predictor.metrics})


@app.post("/evaluate")
def evaluate():
    if not request_allowed():
        return jsonify({"error": "Too many requests. Please wait a moment and try again."}), 429
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    model_id = str(payload.get("model", "local")).strip() or "local"
    if not text:
        return jsonify({"error": "Please enter text to evaluate."}), 400
    if len(text.split()) > MAX_TEXT_WORDS:
        return jsonify({"error": f"Please keep samples under {MAX_TEXT_WORDS} words."}), 413
    if model_id != "local":
        return jsonify({"error": "The PANDORA cloud-trained model is not connected yet."}), 503
    try:
        return jsonify(
            {
                "model": model_id,
                "demo": bool(getattr(predictor, "is_demo", False)),
                "predictions": predictor.predict(text),
            }
        )
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=ENABLE_DEV_TOOLS)
