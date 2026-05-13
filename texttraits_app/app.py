from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from predictor import DEFAULT_MODEL_PATH, TextTraitsPredictor


class MissingPredictor:
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
            f"Runtime model is unavailable at {DEFAULT_MODEL_PATH}. Run `python extract_trained_model.py` first."
        ) from self.error


AVAILABLE_MODELS = [
    {
        "id": "local",
        "name": "Local prototype",
        "available": True,
        "description": "Local model bundle",
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
    predictor = MissingPredictor(error)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.get("/")
def index():
    return render_template(
        "index.html",
        metrics=predictor.metrics,
        model_info=predictor.metadata,
        available_models=AVAILABLE_MODELS,
    )


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
        return jsonify({"model": model_id, "predictions": predictor.predict(text)})
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
