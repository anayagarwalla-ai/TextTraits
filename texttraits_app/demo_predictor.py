from __future__ import annotations

import hashlib
import re


class DemoPredictor:
    """Deterministic mock predictor used when real model files are unavailable."""

    is_demo = True
    metrics = {}
    metadata = {
        "model_path": "models/texttraits_inference_bundle.joblib",
        "bundle_format": "demo_mock",
        "model_count": 0,
        "targets": ["gender", "age_estimate", "introverted", "intuitive", "thinking", "perceiving"],
        "metrics": {},
        "trained_at": "Demo mode",
        "dataset": "Demo mode",
    }

    def __init__(self, reason: Exception | None = None) -> None:
        self.reason = reason

    def predict(self, text: str) -> dict:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Please enter text to evaluate.")

        seed = int(hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:8], 16)
        words = re.findall(r"[A-Za-z0-9']+", cleaned.lower())
        long_text_bonus = min(len(words) / 250, 0.18)
        analytical = self._count(words, {"because", "therefore", "system", "evidence", "model", "data"})
        social = self._count(words, {"people", "team", "feel", "share", "friend", "community"})

        gender_bias = ((seed % 17) - 8) / 100
        gender_top = self._bounded(0.52 + long_text_bonus + gender_bias, 0.51, 0.72)
        gender_label = "Female-associated" if social >= analytical else "Male-associated"
        gender_other = "Male-associated" if gender_label == "Female-associated" else "Female-associated"

        age = self._bounded(24 + (seed % 140) / 10 + min(len(words) / 30, 7), 18, 54)

        return self._enrich(cleaned, {
            "gender": self._prediction(gender_label, [(gender_label, gender_top), (gender_other, 1 - gender_top)]),
            "age_estimate": {
                "label": f"{age:.1f} years",
                "raw_value": age,
                "confidence_label": "Demo estimate",
                "cue_terms": [],
            },
            "mbti_dimensions": {
                "energy": self._pair("introverted", "extraverted", 0.55 + ((seed >> 1) % 12) / 100),
                "information": self._pair("intuitive", "sensing", 0.56 + ((seed >> 3) % 11) / 100),
                "decisions": self._pair("thinking", "feeling", 0.54 + ((seed >> 5) % 13) / 100),
                "structure": self._pair("judging", "perceiving", 0.53 + ((seed >> 7) % 12) / 100),
            },
        })

    def _pair(self, first: str, second: str, probability: float) -> dict:
        probability = self._bounded(probability, 0.51, 0.74)
        return self._prediction(first, [(first, probability), (second, 1 - probability)])

    def _prediction(self, label: str, alternatives: list[tuple[str, float]]) -> dict:
        ranked = sorted(alternatives, key=lambda item: item[1], reverse=True)
        top = ranked[0][1]
        second = ranked[1][1] if len(ranked) > 1 else 0
        margin = max(top - second, 0)
        if top < 0.55 or margin < 0.08:
            confidence_label = "Low confidence"
        elif top < 0.70 or margin < 0.18:
            confidence_label = "Mixed signal"
        else:
            confidence_label = "Strong signal"
        return {
            "label": label,
            "raw_label": label,
            "confidence": top,
            "margin": margin,
            "confidence_label": confidence_label,
            "alternatives": [
                {"label": item_label, "probability": float(probability)}
                for item_label, probability in ranked
            ],
            "cue_terms": [],
        }

    def _enrich(self, text: str, predictions: dict) -> dict:
        return {
            **predictions,
            "text_stats": self._text_stats(text),
            "input_quality": self._input_quality(text),
            "available_targets": self.metadata["targets"],
            "demo_notice": "Demo mode is using deterministic mock predictions because the trained model file is unavailable.",
        }

    def _text_stats(self, text: str) -> dict:
        words = re.findall(r"[A-Za-z0-9']+", text)
        sentences = [part for part in re.split(r"[.!?]+", text) if part.strip()]
        characters = len(text)
        punctuation_count = len(re.findall(r"[^\w\s]", text))
        return {
            "characters": characters,
            "words": len(words),
            "sentences": len(sentences),
            "avg_word_length": round(sum(len(word) for word in words) / len(words), 1) if words else 0,
            "punctuation_density": round(punctuation_count / characters, 3) if characters else 0,
            "reading_level": "Unavailable" if not words else ("Plain" if len(words) < 80 else "Dense"),
        }

    def _input_quality(self, text: str) -> dict:
        words = re.findall(r"[A-Za-z0-9']+", text.lower())
        warnings = []
        if len(words) < 35:
            warnings.append("Text is short; predictions may be unstable.")
        return {
            "level": "good" if not warnings else "caution",
            "warnings": warnings,
        }

    def _count(self, words: list[str], terms: set[str]) -> int:
        return sum(1 for word in words if word in terms)

    def _bounded(self, value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))
