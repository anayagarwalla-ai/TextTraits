from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd


APP_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = APP_DIR / "models" / "texttraits_inference_bundle.joblib"

GENDER_LABELS = {
    "m": "Male",
    "f": "Female",
    "t": "Trans/other source label",
}

IS_FEMALE_LABELS = {
    "0": "Not female",
    "1": "Female",
}

AGE_UNDER_25_LABELS = {
    "0": "25 or older",
    "1": "Under 25",
}

AGE_35_PLUS_LABELS = {
    "0": "Under 35",
    "1": "35 or older",
}

AGE_BUCKET_LABELS = {
    "under_25": "Under 25",
    "25_34": "25 to 34",
    "35_plus": "35 or older",
}

MBTI_LABELS = {
    "introverted": {"0": "extraverted", "1": "introverted"},
    "intuitive": {"0": "sensing", "1": "intuitive"},
    "thinking": {"0": "feeling", "1": "thinking"},
    "perceiving": {"0": "judging", "1": "perceiving"},
}


class TextTraitsPredictor:
    def __init__(self, model_path: Path | str = DEFAULT_MODEL_PATH) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Runtime model not found at {self.model_path}. Run `python extract_trained_model.py` first."
            )
        self.artifact = joblib.load(self.model_path)
        self.format = self.artifact.get("format", "legacy_shared_vectorizer")
        self.vectorizer = self.artifact.get("vectorizer")
        self.models = self.artifact["models"]
        self.metrics = self.artifact.get("metrics", self.artifact.get("selected_metrics", {}))

    def predict(self, text: str) -> dict:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Please enter text to evaluate.")

        if self.vectorizer is None:
            return self._predict_pipeline_bundle(cleaned)
        return self._predict_legacy_bundle(cleaned)

    def _predict_legacy_bundle(self, text: str) -> dict:
        X = self.vectorizer.transform([text])
        age_value = float(np.clip(self.models["age_estimate"].predict(X)[0], 13, 80))

        return {
            "gender": self._top_prediction("gender", X, GENDER_LABELS),
            "mbti": self._top_prediction("mbti", X),
            "age_bucket": self._top_prediction("age_bucket", X),
            "age_estimate": {
                "label": f"{age_value:.1f} years",
                "raw_value": age_value,
            },
            "mbti_dimensions": {
                "energy": self._top_prediction("introverted", X),
                "information": self._top_prediction("intuitive", X),
                "decisions": self._top_prediction("thinking", X),
                "structure": self._top_prediction("perceiving", X),
            },
        }

    def _predict_pipeline_bundle(self, text: str) -> dict:
        age_prediction = self._pipeline_prediction("age_bucket", text, AGE_BUCKET_LABELS)
        if age_prediction is None:
            age_prediction = self._pipeline_prediction("age_under_25", text, AGE_UNDER_25_LABELS)
        if age_prediction is None:
            age_prediction = self._pipeline_prediction("age_35_plus", text, AGE_35_PLUS_LABELS)
        if age_prediction is None:
            age_prediction = {"label": "Unavailable"}

        gender = self._pipeline_prediction("is_female", text, IS_FEMALE_LABELS)
        if gender is None:
            gender = self._pipeline_prediction("gender", text, GENDER_LABELS)

        return {
            "gender": gender or {"label": "Unavailable"},
            "age_estimate": age_prediction,
            "mbti_dimensions": {
                "energy": self._pipeline_prediction("introverted", text, MBTI_LABELS["introverted"]) or {"label": "Unavailable"},
                "information": self._pipeline_prediction("intuitive", text, MBTI_LABELS["intuitive"]) or {"label": "Unavailable"},
                "decisions": self._pipeline_prediction("thinking", text, MBTI_LABELS["thinking"]) or {"label": "Unavailable"},
                "structure": self._pipeline_prediction("perceiving", text, MBTI_LABELS["perceiving"]) or {"label": "Unavailable"},
            },
        }

    def _pipeline_prediction(
        self,
        model_name: str,
        text: str,
        label_map: dict[str, str] | None = None,
    ) -> dict | None:
        model = self.models.get(model_name)
        if model is None:
            return None

        X = pd.Series([text])
        pred = str(model.predict(X)[0])
        label = label_map.get(pred, pred) if label_map else pred
        result = {"label": label, "raw_label": pred}

        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X)[0]
            ranked = sorted(zip(model.classes_, probs), key=lambda item: item[1], reverse=True)
            result["confidence"] = float(ranked[0][1])
            result["alternatives"] = [
                {
                    "label": label_map.get(str(cls), str(cls)) if label_map else str(cls),
                    "probability": float(prob),
                }
                for cls, prob in ranked[:5]
            ]
        return result

    def _top_prediction(self, model_name: str, X, label_map: dict[str, str] | None = None) -> dict:
        model = self.models[model_name]
        pred = str(model.predict(X)[0])
        label = label_map.get(pred, pred) if label_map else pred
        result = {"label": label, "raw_label": pred}

        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X)[0]
            ranked = sorted(zip(model.classes_, probs), key=lambda item: item[1], reverse=True)
            result["confidence"] = float(ranked[0][1])
            result["alternatives"] = [
                {
                    "label": label_map.get(str(cls), str(cls)) if label_map else str(cls),
                    "probability": float(prob),
                }
                for cls, prob in ranked[:5]
            ]
        return result
