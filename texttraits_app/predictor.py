from __future__ import annotations

import re
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import InconsistentVersionWarning


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
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
            self.artifact = joblib.load(self.model_path)
        self.format = self.artifact.get("format", "legacy_shared_vectorizer")
        self.vectorizer = self.artifact.get("vectorizer")
        self.models = self.artifact["models"]
        self._normalize_loaded_models()
        self.metrics = self.artifact.get("metrics", self.artifact.get("selected_metrics", {}))
        self.metadata = {
            "model_path": str(self.model_path),
            "bundle_format": self.format,
            "model_count": len(self.models),
            "targets": sorted(self.models.keys()),
            "metrics": self.metrics,
            "trained_at": self.artifact.get("trained_at") or self.artifact.get("created_at") or "Unknown",
            "dataset": self.artifact.get("dataset") or self.artifact.get("dataset_name") or "Unknown",
        }

    def _normalize_loaded_models(self) -> None:
        for model in self.models.values():
            estimator = self._final_estimator(model)
            if type(estimator).__name__ == "LogisticRegression" and not hasattr(estimator, "multi_class"):
                estimator.multi_class = "auto"

    def _final_estimator(self, model):
        steps = getattr(model, "steps", None)
        if steps:
            return steps[-1][1]
        return model

    def predict(self, text: str) -> dict:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Please enter text to evaluate.")

        if self.vectorizer is None:
            predictions = self._predict_pipeline_bundle(cleaned)
        else:
            predictions = self._predict_legacy_bundle(cleaned)

        return self._enrich_response(cleaned, predictions)

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
        result["cue_terms"] = self._cue_terms_for_pipeline(model, text, pred)
        return result

    def _enrich_response(self, text: str, predictions: dict) -> dict:
        for prediction in self._walk_predictions(predictions):
            self._add_confidence_details(prediction)

        return {
            **predictions,
            "text_stats": self._text_stats(text),
            "input_quality": self._input_quality(text),
            "available_targets": sorted(self.models.keys()),
        }

    def _walk_predictions(self, value):
        if isinstance(value, dict):
            if "label" in value and (
                "alternatives" in value or "raw_label" in value or "raw_value" in value
            ):
                yield value
            for child in value.values():
                yield from self._walk_predictions(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._walk_predictions(child)

    def _add_confidence_details(self, prediction: dict) -> None:
        alternatives = prediction.get("alternatives") or []
        if not alternatives:
            prediction["confidence_label"] = "Unavailable"
            return

        top = float(alternatives[0].get("probability", 0))
        second = float(alternatives[1].get("probability", 0)) if len(alternatives) > 1 else 0
        margin = max(top - second, 0)
        prediction["confidence"] = top
        prediction["margin"] = margin

        if top < 0.55 or margin < 0.08:
            label = "Low confidence"
        elif top < 0.70 or margin < 0.18:
            label = "Mixed signal"
        else:
            label = "Strong signal"
        prediction["confidence_label"] = label

    def _text_stats(self, text: str) -> dict:
        words = re.findall(r"[A-Za-z0-9']+", text)
        sentences = [part for part in re.split(r"[.!?]+", text) if part.strip()]
        characters = len(text)
        word_count = len(words)
        sentence_count = max(len(sentences), 1)
        avg_word_length = sum(len(word) for word in words) / word_count if word_count else 0
        punctuation_count = len(re.findall(r"[^\w\s]", text))
        punctuation_density = punctuation_count / characters if characters else 0
        reading_level = self._reading_level(words, sentence_count)

        return {
            "characters": characters,
            "words": word_count,
            "sentences": len(sentences),
            "avg_word_length": round(avg_word_length, 1),
            "punctuation_density": round(punctuation_density, 3),
            "reading_level": reading_level,
        }

    def _reading_level(self, words: list[str], sentence_count: int) -> str:
        if not words:
            return "Unavailable"
        syllables = sum(self._estimate_syllables(word) for word in words)
        score = 0.39 * (len(words) / sentence_count) + 11.8 * (syllables / len(words)) - 15.59
        if score < 6:
            return "Plain"
        if score < 10:
            return "Moderate"
        if score < 14:
            return "Dense"
        return "Very dense"

    def _estimate_syllables(self, word: str) -> int:
        word = word.lower()
        groups = re.findall(r"[aeiouy]+", word)
        count = len(groups)
        if word.endswith("e") and count > 1:
            count -= 1
        return max(count, 1)

    def _input_quality(self, text: str) -> dict:
        words = re.findall(r"[A-Za-z0-9']+", text.lower())
        unique_ratio = len(set(words)) / len(words) if words else 0
        warnings = []

        if len(words) < 35:
            warnings.append("Text is short; predictions may be unstable.")
        if len(words) >= 35 and unique_ratio < 0.35:
            warnings.append("Text has repeated wording; it may carry limited author signal.")
        if re.search(r"(lorem ipsum|terms and conditions|privacy policy|unsubscribe)", text, re.I):
            warnings.append("Text looks boilerplate-like; results may reflect the template more than the author.")
        if len(text) > 0 and len(re.findall(r"[A-Za-z]", text)) / len(text) < 0.55:
            warnings.append("Text has low natural-language density.")

        return {
            "level": "good" if not warnings else ("caution" if len(warnings) == 1 else "low"),
            "warnings": warnings,
        }

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
        result["cue_terms"] = self._cue_terms_for_estimator(model, X, pred, self.vectorizer)
        return result

    def _cue_terms_for_pipeline(self, pipeline, text: str, pred: str) -> list[dict]:
        named_steps = getattr(pipeline, "named_steps", {})
        vectorizer = None
        estimator = None
        for step in named_steps.values():
            if hasattr(step, "get_feature_names_out") and hasattr(step, "transform"):
                vectorizer = step
            elif hasattr(step, "coef_"):
                estimator = step

        if vectorizer is None or estimator is None:
            return []
        X = vectorizer.transform(pd.Series([text]))
        return self._cue_terms_for_estimator(estimator, X, pred, vectorizer)

    def _cue_terms_for_estimator(self, estimator, X, pred: str, vectorizer) -> list[dict]:
        if not hasattr(estimator, "coef_") or not hasattr(vectorizer, "get_feature_names_out"):
            return []

        classes = [str(item) for item in getattr(estimator, "classes_", [])]
        if not classes:
            return []

        coefs = estimator.coef_
        class_index = classes.index(pred) if pred in classes else 0
        if coefs.shape[0] == 1:
            weights = coefs[0] if class_index == 1 or len(classes) == 2 else -coefs[0]
        else:
            weights = coefs[class_index]

        row = X[0]
        contributions = row.multiply(weights).toarray()[0]
        if not np.any(contributions):
            return []

        feature_names = vectorizer.get_feature_names_out()
        top_indices = np.argsort(contributions)[::-1][:6]
        return [
            {
                "term": str(feature_names[index]),
                "weight": float(contributions[index]),
            }
            for index in top_indices
            if contributions[index] > 0
        ]
