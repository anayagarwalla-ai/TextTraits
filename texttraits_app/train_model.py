from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "legacy_project" / "Data" / "pandora_big_info.csv"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "texttraits_model.joblib"
METRICS_PATH = ARTIFACT_DIR / "metrics.json"

RANDOM_STATE = 42
MAX_ROWS = 120_000
VALID_MBTI = {
    "intj",
    "intp",
    "entj",
    "entp",
    "infj",
    "infp",
    "enfj",
    "enfp",
    "istj",
    "isfj",
    "estj",
    "esfj",
    "istp",
    "isfp",
    "estp",
    "esfp",
}


def normalize_age_bucket(age: float) -> str:
    if age < 25:
        return "under 25"
    if age < 35:
        return "25-34"
    return "35+"


def train_classifier(name: str, X, y: pd.Series) -> tuple[LogisticRegression, dict]:
    train_idx, test_idx = train_test_split(
        np.arange(len(y)),
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=y,
    )
    model = LogisticRegression(
        max_iter=1_000,
        class_weight="balanced",
        solver="saga",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    model.fit(X[train_idx], y.iloc[train_idx])
    pred = model.predict(X[test_idx])
    metrics = {
        "accuracy": float(accuracy_score(y.iloc[test_idx], pred)),
        "macro_f1": float(f1_score(y.iloc[test_idx], pred, average="macro")),
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "classes": [str(cls) for cls in model.classes_],
    }
    return model, metrics


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    cols = ["body", "gender", "age", "mbti", "introverted", "intuitive", "thinking", "perceiving"]
    df = pd.read_csv(DATA_PATH, usecols=cols, low_memory=False)
    df = df.dropna(subset=["body"])
    df["body"] = df["body"].astype(str)
    df = df[df["body"].str.strip().astype(bool)]
    df = df.sample(n=min(MAX_ROWS, len(df)), random_state=RANDOM_STATE).reset_index(drop=True)

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=3,
        max_df=0.85,
        max_features=60_000,
        sublinear_tf=True,
    )
    X = vectorizer.fit_transform(df["body"])

    models = {}
    metrics = {
        "data_path": str(DATA_PATH),
        "rows_sampled": int(len(df)),
        "vectorizer_features": int(len(vectorizer.get_feature_names_out())),
    }

    target_frames = {
        "gender": df["gender"].dropna().astype(str),
        "mbti": df["mbti"].dropna().astype(str).str.lower(),
        "age_bucket": df["age"].dropna().astype(float).map(normalize_age_bucket),
        "introverted": df["introverted"].dropna().astype(int).map({0: "extraverted", 1: "introverted"}),
        "intuitive": df["intuitive"].dropna().astype(int).map({0: "sensing", 1: "intuitive"}),
        "thinking": df["thinking"].dropna().astype(int).map({0: "feeling", 1: "thinking"}),
        "perceiving": df["perceiving"].dropna().astype(int).map({0: "judging", 1: "perceiving"}),
    }

    for name, y in target_frames.items():
        if name == "mbti":
            y = y[y.isin(VALID_MBTI)]
        y = y.dropna()
        if y.nunique() < 2:
            continue
        model, model_metrics = train_classifier(name, X[y.index.to_numpy()], y.reset_index(drop=True))
        models[name] = model
        metrics[name] = model_metrics

    age_y = df["age"].dropna().astype(float)
    age_idx = age_y.index.to_numpy()
    train_idx, test_idx = train_test_split(
        np.arange(len(age_y)),
        test_size=0.2,
        random_state=RANDOM_STATE,
    )
    age_model = Ridge(alpha=2.0, random_state=RANDOM_STATE)
    age_model.fit(X[age_idx[train_idx]], age_y.iloc[train_idx])
    age_pred = np.clip(age_model.predict(X[age_idx[test_idx]]), 13, 80)
    models["age_estimate"] = age_model
    metrics["age_estimate"] = {
        "mean_absolute_error": float(mean_absolute_error(age_y.iloc[test_idx], age_pred)),
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
    }

    artifact = {
        "vectorizer": vectorizer,
        "models": models,
        "metrics": metrics,
        "label_notes": {
            "gender": {"m": "male", "f": "female", "t": "trans/other label in source data"},
            "age_bucket": "under 25, 25-34, or 35+",
            "mbti": "16-class MBTI type prediction plus the four binary MBTI dimensions",
        },
    }
    joblib.dump(artifact, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Saved model to {MODEL_PATH}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
