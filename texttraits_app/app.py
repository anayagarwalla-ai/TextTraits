from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from predictor import TextTraitsPredictor


predictor = TextTraitsPredictor()
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.get("/")
def index():
    return render_template("index.html", metrics=predictor.metrics)


@app.post("/evaluate")
def evaluate():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify({"error": "Please enter text to evaluate."}), 400
    return jsonify({"predictions": predictor.predict(text)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
