from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from predictor import TextTraitsPredictor


app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

predictor = None
startup_error = None

try:
    predictor = TextTraitsPredictor()
except FileNotFoundError as exc:
    startup_error = str(exc)


@app.get("/")
def index():
    model_status = (
        predictor.status_panel()
        if predictor is not None
        else {
            "bundle": "Unavailable",
            "format": "Unavailable",
            "trained_at": "Unavailable",
            "dataset": "Unavailable",
            "targets": [],
        }
    )
    return render_template("index.html", model_status=model_status, startup_error=startup_error)


@app.post("/evaluate")
def evaluate():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify({"error": "Please enter text to evaluate."}), 400
    if predictor is None:
        return jsonify({"error": startup_error or "Model bundle is unavailable."}), 503
    return jsonify({"predictions": predictor.predict(text)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
