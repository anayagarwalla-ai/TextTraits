# -*- coding: utf-8 -*-
"""Evaluate TextTraits model quality from prediction outputs.

This script predicts from a CSV with text and optional ground-truth labels, then
scores accuracy, macro F1, balanced accuracy, baselines, confidence/margin
quality, abstention coverage, and output diagnostics.

It is designed to run locally on small samples and in Colab for full PANDORA
or author-level evaluations.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    classification_report,
    f1_score,
    mean_absolute_error,
)
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = ROOT / "texttraits_app" / "models" / "texttraits_inference_bundle.joblib"
DEFAULT_OUT_DIR = ROOT / "output" / "model_diagnostics"
TEXT_COL = "body"
RANDOM_STATE = 42

TARGET_SPECS: Dict[str, Dict[str, Any]] = {
    "gender": {
        "kind": "classification",
        "label_col": "gender",
        "model_names": ["gender"],
        "label_map": {"m": "m", "f": "f", "t": "t"},
    },
    "is_female": {
        "kind": "classification",
        "label_col": "is_female",
        "model_names": ["is_female", "gender"],
        "label_map": {"0": "0", "1": "1", "0.0": "0", "1.0": "1", "m": "0", "f": "1"},
    },
    "age_under_25": {
        "kind": "classification",
        "label_col": "age_under_25",
        "model_names": ["age_under_25"],
        "label_map": {"0": "0", "1": "1", "0.0": "0", "1.0": "1"},
    },
    "age_35_plus": {
        "kind": "classification",
        "label_col": "age_35_plus",
        "model_names": ["age_35_plus"],
        "label_map": {"0": "0", "1": "1", "0.0": "0", "1.0": "1"},
    },
    "age_bucket": {
        "kind": "classification",
        "label_col": "age_bucket",
        "model_names": ["age_bucket"],
        "label_map": {
            "under 25": "under_25",
            "under_25": "under_25",
            "25-34": "25_34",
            "25_34": "25_34",
            "35+": "35_plus",
            "35_plus": "35_plus",
        },
    },
    "introverted": {
        "kind": "classification",
        "label_col": "introverted",
        "model_names": ["introverted"],
        "label_map": {"0": "0", "1": "1", "0.0": "0", "1.0": "1", "extraverted": "0", "introverted": "1"},
    },
    "intuitive": {
        "kind": "classification",
        "label_col": "intuitive",
        "model_names": ["intuitive"],
        "label_map": {"0": "0", "1": "1", "0.0": "0", "1.0": "1", "sensing": "0", "intuitive": "1"},
    },
    "thinking": {
        "kind": "classification",
        "label_col": "thinking",
        "model_names": ["thinking"],
        "label_map": {"0": "0", "1": "1", "0.0": "0", "1.0": "1", "feeling": "0", "thinking": "1"},
    },
    "perceiving": {
        "kind": "classification",
        "label_col": "perceiving",
        "model_names": ["perceiving"],
        "label_map": {"0": "0", "1": "1", "0.0": "0", "1.0": "1", "judging": "0", "perceiving": "1"},
    },
    "country_us": {
        "kind": "classification",
        "label_col": "country_us",
        "model_names": ["country_us"],
        "label_map": {"0": "0", "1": "1", "0.0": "0", "1.0": "1", "false": "0", "true": "1"},
    },
    "mbti": {
        "kind": "classification",
        "label_col": "mbti",
        "model_names": ["mbti"],
        "label_map": {},
    },
    "age_estimate": {
        "kind": "regression",
        "label_col": "age",
        "model_names": ["age_estimate"],
        "label_map": {},
    },
}


def normalize_label(value: Any, label_map: Dict[str, str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip().lower()
    if not text or text == "nan":
        return None
    return label_map.get(text, text)


def normalize_age_bucket(age: Any) -> Optional[str]:
    try:
        value = float(age)
    except Exception:
        return None
    if math.isnan(value):
        return None
    if value < 25:
        return "under_25"
    if value < 35:
        return "25_34"
    return "35_plus"


def to_bool_target(series: pd.Series, predicate) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    out = pd.Series(np.nan, index=series.index, dtype="object")
    out.loc[values.notna()] = np.where(predicate(values.loc[values.notna()]), "1", "0")
    return out


def prepare_labels(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "age" in out.columns:
        out["age_bucket"] = out["age"].map(normalize_age_bucket)
        out["age_under_25"] = to_bool_target(out["age"], lambda s: s < 25)
        out["age_35_plus"] = to_bool_target(out["age"], lambda s: s >= 35)
    if "gender" in out.columns and "is_female" not in out.columns:
        out["is_female"] = out["gender"].astype(str).str.lower().map({"f": "1", "m": "0"})
    if "country" in out.columns and "country_us" not in out.columns:
        country = out["country"].fillna("").astype(str).str.strip().str.lower()
        country_us = pd.Series(np.nan, index=out.index, dtype="object")
        known = country != ""
        country_us.loc[known] = np.where(country.loc[known] == "us", "1", "0")
        out["country_us"] = country_us
    return out


def load_model(path: Path) -> Dict[str, Any]:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
        artifact = joblib.load(path)
    if "models" not in artifact:
        raise ValueError(f"Model artifact at {path} has no 'models' key")
    return artifact


def final_estimator(model):
    steps = getattr(model, "steps", None)
    if steps:
        return steps[-1][1]
    return model


def normalize_loaded_models(models: Dict[str, Any]) -> None:
    for model in models.values():
        estimator = final_estimator(model)
        if type(estimator).__name__ == "LogisticRegression" and not hasattr(estimator, "multi_class"):
            estimator.multi_class = "auto"


def available_target_names(models: Dict[str, Any]) -> List[str]:
    names = []
    for target, spec in TARGET_SPECS.items():
        if any(name in models for name in spec["model_names"]):
            names.append(target)
    return names


def select_model(models: Dict[str, Any], target: str):
    for name in TARGET_SPECS[target]["model_names"]:
        if name in models:
            return name, models[name]
    return None, None


def predict_model(model: Any, texts: pd.Series, shared_vectorizer: Any = None) -> Tuple[np.ndarray, Optional[np.ndarray], List[str]]:
    if shared_vectorizer is not None:
        X = shared_vectorizer.transform(texts.astype(str))
        pred = model.predict(X)
        classes = [str(item) for item in getattr(model, "classes_", [])]
        proba = model.predict_proba(X) if hasattr(model, "predict_proba") else None
        return np.asarray(pred), proba, classes

    pred = model.predict(texts.astype(str))
    classes = [str(item) for item in getattr(model, "classes_", [])]
    proba = model.predict_proba(texts.astype(str)) if hasattr(model, "predict_proba") else None
    return np.asarray(pred), proba, classes


def confidence_rows(pred: Sequence[Any], proba: Optional[np.ndarray], classes: List[str]) -> pd.DataFrame:
    rows = []
    for idx, value in enumerate(pred):
        row = {"pred": str(value), "confidence": np.nan, "margin": np.nan, "entropy": np.nan}
        if proba is not None and len(proba[idx]):
            probs = np.asarray(proba[idx], dtype=float)
            order = np.argsort(probs)[::-1]
            top = float(probs[order[0]])
            second = float(probs[order[1]]) if len(order) > 1 else 0.0
            entropy = float(-np.sum([p * math.log(p) for p in probs if p > 0]))
            row.update(
                {
                    "pred": classes[order[0]] if classes else str(value),
                    "confidence": top,
                    "margin": max(top - second, 0.0),
                    "entropy": entropy,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def canonical_classes(classes: List[str], label_map: Dict[str, str]) -> List[str]:
    return [normalize_label(item, label_map) or str(item).strip().lower() for item in classes]


def canonicalize_prediction_frame(pred: pd.DataFrame, label_map: Dict[str, str]) -> pd.DataFrame:
    out = pred.copy()
    out["pred"] = out["pred"].map(lambda value: normalize_label(value, label_map) or str(value).strip().lower())
    return out


def abstain_mask(predictions: pd.DataFrame, min_confidence: float, min_margin: float) -> pd.Series:
    confidence = pd.to_numeric(predictions["confidence"], errors="coerce")
    margin = pd.to_numeric(predictions["margin"], errors="coerce")
    known = confidence.notna() & margin.notna()
    return known & ((confidence < min_confidence) | (margin < min_margin))


def baseline_scores(y_true: pd.Series) -> Dict[str, Any]:
    y_true = y_true.dropna().astype(str)
    if y_true.empty:
        return {}
    majority = y_true.value_counts().idxmax()
    majority_pred = pd.Series([majority] * len(y_true), index=y_true.index)
    rng = np.random.default_rng(RANDOM_STATE)
    classes = y_true.value_counts(normalize=True)
    sampled = rng.choice(classes.index.to_numpy(), p=classes.to_numpy(), size=len(y_true))
    return {
        "majority_class": str(majority),
        "majority_accuracy": float(accuracy_score(y_true, majority_pred)),
        "majority_macro_f1": float(f1_score(y_true, majority_pred, average="macro", zero_division=0)),
        "stratified_random_accuracy": float(accuracy_score(y_true, sampled)),
        "stratified_random_macro_f1": float(f1_score(y_true, sampled, average="macro", zero_division=0)),
    }


def brier_if_binary(y_true: pd.Series, pred: pd.DataFrame, proba: Optional[np.ndarray], classes: List[str]) -> Optional[float]:
    unique = sorted(y_true.dropna().astype(str).unique().tolist())
    if len(unique) != 2 or proba is None or len(classes) != 2:
        return None
    positive = unique[-1]
    if positive not in classes:
        return None
    pos_idx = classes.index(positive)
    return float(brier_score_loss((y_true.astype(str) == positive).astype(int), proba[:, pos_idx]))


def expected_calibration_error(y_true: pd.Series, pred: pd.DataFrame, bins: int = 10) -> Optional[float]:
    confidence = pd.to_numeric(pred["confidence"], errors="coerce")
    usable = confidence.notna()
    if not usable.any():
        return None
    y = y_true.astype(str).reset_index(drop=True)
    p = pred["pred"].astype(str).reset_index(drop=True)
    c = confidence.reset_index(drop=True)
    correct = (y == p).astype(float)
    ece = 0.0
    for low in np.linspace(0, 1, bins + 1)[:-1]:
        high = low + 1 / bins
        if high >= 1:
            mask = (c >= low) & (c <= high)
        else:
            mask = (c >= low) & (c < high)
        if mask.any():
            ece += float(mask.mean()) * abs(float(correct[mask].mean()) - float(c[mask].mean()))
    return float(ece)


def classification_metrics(
    target: str,
    y_true: pd.Series,
    pred: pd.DataFrame,
    proba: Optional[np.ndarray],
    classes: List[str],
    min_confidence: float,
    min_margin: float,
) -> Dict[str, Any]:
    y_true = y_true.astype(str).reset_index(drop=True)
    y_pred = pred["pred"].astype(str).reset_index(drop=True)
    labels = sorted(pd.unique(pd.concat([y_true, y_pred], ignore_index=True)).tolist())
    abstain = abstain_mask(pred, min_confidence, min_margin)
    kept = ~abstain

    metrics: Dict[str, Any] = {
        "target": target,
        "kind": "classification",
        "n": int(len(y_true)),
        "classes": labels,
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "baseline": baseline_scores(y_true),
        "mean_confidence": float(pd.to_numeric(pred["confidence"], errors="coerce").mean(skipna=True)),
        "mean_margin": float(pd.to_numeric(pred["margin"], errors="coerce").mean(skipna=True)),
        "mean_entropy": float(pd.to_numeric(pred["entropy"], errors="coerce").mean(skipna=True)),
        "abstention": {
            "min_confidence": min_confidence,
            "min_margin": min_margin,
            "abstained_n": int(abstain.sum()),
            "coverage": float(kept.mean()),
        },
        "ece_10_bin": expected_calibration_error(y_true, pred),
        "brier_score_binary": brier_if_binary(y_true, pred, proba, classes),
        "classification_report": classification_report(y_true, y_pred, labels=labels, zero_division=0, output_dict=True),
    }
    if kept.any() and kept.sum() < len(kept):
        metrics["abstention"].update(
            {
                "kept_accuracy": float(accuracy_score(y_true[kept], y_pred[kept])),
                "kept_macro_f1": float(f1_score(y_true[kept], y_pred[kept], average="macro", zero_division=0)),
            }
        )
    return metrics


def regression_metrics(target: str, y_true: pd.Series, y_pred: Sequence[Any]) -> Dict[str, Any]:
    y = pd.to_numeric(y_true, errors="coerce")
    p = pd.to_numeric(pd.Series(y_pred), errors="coerce")
    mask = y.notna() & p.notna()
    y = y[mask]
    p = p[mask]
    return {
        "target": target,
        "kind": "regression",
        "n": int(len(y)),
        "mean_absolute_error": float(mean_absolute_error(y, p)) if len(y) else None,
        "median_absolute_error": float(np.median(np.abs(y - p))) if len(y) else None,
        "mean_prediction": float(p.mean()) if len(y) else None,
        "mean_truth": float(y.mean()) if len(y) else None,
    }


def text_quality(frame: pd.DataFrame, text_col: str) -> Dict[str, Any]:
    text = frame[text_col].fillna("").astype(str)
    word_counts = text.str.findall(r"[A-Za-z0-9']+").map(len)
    char_counts = text.str.len()
    return {
        "rows": int(len(frame)),
        "empty_text_rows": int((text.str.strip() == "").sum()),
        "median_words": float(word_counts.median()) if len(word_counts) else 0,
        "mean_words": float(word_counts.mean()) if len(word_counts) else 0,
        "short_under_35_words": int((word_counts < 35).sum()),
        "median_chars": float(char_counts.median()) if len(char_counts) else 0,
    }


def author_split_sample(frame: pd.DataFrame, author_col: str, max_rows: Optional[int], sample_mode: str) -> pd.DataFrame:
    if max_rows is None or len(frame) <= max_rows:
        return frame
    if sample_mode == "author" and author_col in frame.columns:
        authors = np.asarray(frame[author_col].dropna().astype(str).unique(), dtype=object)
        rng = np.random.default_rng(RANDOM_STATE)
        rng.shuffle(authors)
        keep_authors = []
        row_count = 0
        counts = frame[author_col].astype(str).value_counts()
        for author in authors:
            keep_authors.append(author)
            row_count += int(counts.get(author, 0))
            if row_count >= max_rows:
                break
        return frame[frame[author_col].astype(str).isin(set(keep_authors))].copy()
    return frame.sample(n=max_rows, random_state=RANDOM_STATE).copy()


def evaluate_dataframe(
    frame: pd.DataFrame,
    model_path: Path,
    text_col: str,
    targets: List[str],
    output_dir: Path,
    min_confidence: float,
    min_margin: float,
) -> Dict[str, Any]:
    artifact = load_model(model_path)
    models = artifact["models"]
    normalize_loaded_models(models)
    shared_vectorizer = artifact.get("vectorizer")
    frame = prepare_labels(frame)
    frame[text_col] = frame[text_col].fillna("").astype(str)
    frame = frame[frame[text_col].str.strip() != ""].reset_index(drop=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary: Dict[str, Any] = {
        "model_path": str(model_path),
        "bundle_format": artifact.get("format", "legacy_shared_vectorizer"),
        "available_model_targets": sorted(models.keys()),
        "requested_targets": targets,
        "text_quality": text_quality(frame, text_col),
        "targets": {},
    }

    row_outputs = frame[[text_col]].copy()
    for maybe_col in ["author", "subreddit"]:
        if maybe_col in frame.columns:
            row_outputs[maybe_col] = frame[maybe_col]

    for target in targets:
        spec = TARGET_SPECS[target]
        model_name, model = select_model(models, target)
        if model is None:
            summary["targets"][target] = {"error": "model_unavailable", "model_names": spec["model_names"]}
            continue

        if spec["kind"] == "classification":
            label_col = spec["label_col"]
            if label_col not in frame.columns:
                summary["targets"][target] = {"error": "label_column_missing", "label_col": label_col}
                continue
            y = frame[label_col].map(lambda value: normalize_label(value, spec["label_map"]))
            mask = y.notna()
            if not mask.any():
                summary["targets"][target] = {"error": "no_labels", "label_col": label_col}
                continue
            pred_raw, proba, classes = predict_model(model, frame.loc[mask, text_col], shared_vectorizer)
            classes = canonical_classes(classes, spec["label_map"])
            pred_df = canonicalize_prediction_frame(confidence_rows(pred_raw, proba, classes), spec["label_map"])
            y_true = y.loc[mask].reset_index(drop=True)
            metrics = classification_metrics(target, y_true, pred_df, proba, classes, min_confidence, min_margin)
            metrics["model_name"] = model_name
            summary["targets"][target] = metrics

            row_outputs.loc[mask, f"{target}_truth"] = y_true.to_numpy()
            row_outputs.loc[mask, f"{target}_pred"] = pred_df["pred"].to_numpy()
            row_outputs.loc[mask, f"{target}_confidence"] = pred_df["confidence"].to_numpy()
            row_outputs.loc[mask, f"{target}_margin"] = pred_df["margin"].to_numpy()
            row_outputs.loc[mask, f"{target}_abstain"] = abstain_mask(pred_df, min_confidence, min_margin).to_numpy()
        else:
            label_col = spec["label_col"]
            if label_col not in frame.columns:
                summary["targets"][target] = {"error": "label_column_missing", "label_col": label_col}
                continue
            y = pd.to_numeric(frame[label_col], errors="coerce")
            mask = y.notna()
            if not mask.any():
                summary["targets"][target] = {"error": "no_labels", "label_col": label_col}
                continue
            pred_raw, _, _ = predict_model(model, frame.loc[mask, text_col], shared_vectorizer)
            metrics = regression_metrics(target, y.loc[mask].reset_index(drop=True), pred_raw)
            metrics["model_name"] = model_name
            summary["targets"][target] = metrics
            row_outputs.loc[mask, f"{target}_truth"] = y.loc[mask].to_numpy()
            row_outputs.loc[mask, f"{target}_pred"] = pred_raw

    summary_path = output_dir / "model_diagnostics_summary.json"
    rows_path = output_dir / "model_diagnostics_rows.csv"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    row_outputs.to_csv(rows_path, index=False)
    return summary


def desired_columns(path: Path, text_col: str, targets: List[str], author_col: str) -> Optional[List[str]]:
    header = pd.read_csv(path, nrows=0).columns.tolist()
    wanted = {text_col, author_col, "subreddit"}
    for target in targets:
        spec = TARGET_SPECS[target]
        wanted.add(spec["label_col"])
        if target in {"age_bucket", "age_under_25", "age_35_plus"}:
            wanted.add("age")
        if target in {"gender", "is_female"}:
            wanted.update(["gender", "is_female"])
        if target == "country_us":
            wanted.update(["country", "country_us"])
    existing = [col for col in header if col in wanted]
    return existing or None


def load_csv(path: Path, max_rows: Optional[int], sample_mode: str, author_col: str, text_col: str, targets: List[str]) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=desired_columns(path, text_col, targets, author_col), low_memory=False)
    return author_split_sample(frame, author_col, max_rows, sample_mode).reset_index(drop=True)


def print_summary(summary: Dict[str, Any]) -> None:
    print(json.dumps({"text_quality": summary["text_quality"], "available_model_targets": summary["available_model_targets"]}, indent=2))
    for target, metrics in summary["targets"].items():
        if "error" in metrics:
            print(f"[{target}] {metrics['error']}")
            continue
        if metrics["kind"] == "classification":
            baseline = metrics.get("baseline", {})
            print(
                f"[{target}] n={metrics['n']} "
                f"acc={metrics['accuracy']:.4f} macro_f1={metrics['macro_f1']:.4f} "
                f"balanced={metrics['balanced_accuracy']:.4f} "
                f"majority_f1={baseline.get('majority_macro_f1', float('nan')):.4f} "
                f"coverage={metrics['abstention']['coverage']:.3f}"
            )
        else:
            print(f"[{target}] n={metrics['n']} mae={metrics['mean_absolute_error']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True, help="CSV with text and optional ground-truth labels.")
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH), help="Path to TextTraits joblib bundle.")
    parser.add_argument("--text-col", default=TEXT_COL, help="Text column name.")
    parser.add_argument("--targets", default="auto", help="Comma-separated targets or 'auto'.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR), help="Directory for diagnostics JSON/CSV.")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional row cap for local/smoke runs.")
    parser.add_argument("--sample-mode", choices=["row", "author"], default="author", help="How to sample when --max-rows is set.")
    parser.add_argument("--author-col", default="author", help="Author column used for author-aware sampling.")
    parser.add_argument("--min-confidence", type=float, default=0.55, help="Abstain below this confidence.")
    parser.add_argument("--min-margin", type=float, default=0.08, help="Abstain below this top-two probability margin.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = Path(args.model)
    input_csv = Path(args.input_csv)
    if not model_path.exists():
        print(f"[error] model not found: {model_path}", file=sys.stderr)
        return 2
    if not input_csv.exists():
        print(f"[error] input CSV not found: {input_csv}", file=sys.stderr)
        return 2

    artifact = load_model(model_path)
    models = artifact["models"]
    targets = available_target_names(models) if args.targets == "auto" else [item.strip() for item in args.targets.split(",") if item.strip()]
    frame = load_csv(input_csv, args.max_rows, args.sample_mode, args.author_col, args.text_col, targets)
    if args.text_col not in frame.columns:
        print(f"[error] text column {args.text_col!r} not found. Columns: {list(frame.columns)}", file=sys.stderr)
        return 2
    unknown = [target for target in targets if target not in TARGET_SPECS]
    if unknown:
        print(f"[error] unknown targets: {unknown}", file=sys.stderr)
        return 2

    summary = evaluate_dataframe(
        frame,
        model_path,
        args.text_col,
        targets,
        Path(args.output_dir),
        args.min_confidence,
        args.min_margin,
    )
    print_summary(summary)
    print(f"[done] wrote {Path(args.output_dir) / 'model_diagnostics_summary.json'}")
    print(f"[done] wrote {Path(args.output_dir) / 'model_diagnostics_rows.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
