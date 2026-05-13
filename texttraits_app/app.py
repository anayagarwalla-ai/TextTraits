from __future__ import annotations

import os

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
ALLOW_DEMO_MODE = env_flag("TEXTTRAITS_ALLOW_DEMO", True)

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
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


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
    return jsonify(
        {
            "ok": not isinstance(predictor, MissingPredictor),
            "demo": bool(getattr(predictor, "is_demo", False)),
            "model": public_model_info(),
            "dev_tools_enabled": ENABLE_DEV_TOOLS,
        }
    )


@app.get("/dev/model")
def dev_model():
    if not ENABLE_DEV_TOOLS:
        return jsonify({"error": "Developer tools are disabled."}), 404
    return jsonify({"metadata": predictor.metadata, "metrics": predictor.metrics})


@app.post("/evaluate")
def evaluate():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    model_id = str(payload.get("model", "local")).strip() or "local"
    if not text:
        return jsonify({"error": "Please enter text to evaluate."}), 400
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
