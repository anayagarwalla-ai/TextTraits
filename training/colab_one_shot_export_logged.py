# -*- coding: utf-8 -*-
"""Logged one-shot Colab training/export for TextTraits.

Run this in a high-RAM Colab runtime. It resolves the known Google Drive data
paths, joins raw PANDORA comments to author profile labels when needed, trains
target-specific text models, and exports everything needed by the local Flask
demo plus a portable linear-model JSON bundle for future JavaScript inference.

This version is tuned for observability and practical iteration:
    - timestamped, flush-on-write logging
    - heartbeat/memory logs during long vectorizer/classifier fits
    - faster candidates first, heavier models later
    - target-level checkpoints after every successful target
    - defaults that avoid spending an hour on the first candidate

Default input paths discovered from the legacy notebooks:
    /content/drive/MyDrive/Anay Agarwalla/Data/PANDORA.csv
    /content/drive/MyDrive/Anay Agarwalla/Data/author_profiles.csv

Default output directory:
    /content/drive/MyDrive/Anay Agarwalla/Models/texttraits_full_export
"""

from __future__ import annotations

import argparse
import gc
import gzip
import json
import os
import platform
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline

try:
    import psutil
except Exception:
    psutil = None


HARD_PANDORA_PATH = "/content/drive/MyDrive/Anay Agarwalla/Data/PANDORA.csv"
HARD_PROFILES_PATH = "/content/drive/MyDrive/Anay Agarwalla/Data/author_profiles.csv"
DEFAULT_OUTPUT_DIR = "/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_full_export"

TEXT_COL = "body"
RANDOM_STATE = 42
TEST_SIZE = 0.25
MIN_TEXT_CHARS = 15
MIN_CLASS_COUNT = 400
SELECTION_METRIC = "accuracy"

BINARY_TARGETS = [
    "is_female",
    "age_under_25",
    "age_35_plus",
    "introverted",
    "intuitive",
    "thinking",
    "perceiving",
    "country_us",
]

MULTICLASS_TARGETS = [
    "age_bucket",
]

LABEL_NOTES = {
    "is_female": {"0": "not female / source label m", "1": "female / source label f"},
    "age_under_25": {"0": "25 or older", "1": "under 25"},
    "age_35_plus": {"0": "under 35", "1": "35 or older"},
    "age_bucket": {"under_25": "under 25", "25_34": "25 to 34", "35_plus": "35 or older"},
    "introverted": {"0": "extraverted", "1": "introverted"},
    "intuitive": {"0": "sensing", "1": "intuitive"},
    "thinking": {"0": "feeling", "1": "thinking"},
    "perceiving": {"0": "judging", "1": "perceiving"},
    "country_us": {"0": "non-US", "1": "US"},
}


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def memory_snapshot() -> str:
    if psutil is None:
        return "memory=unavailable (pip install psutil for RSS logs)"
    process = psutil.Process(os.getpid())
    rss_gb = process.memory_info().rss / (1024**3)
    vm = psutil.virtual_memory()
    used_gb = vm.used / (1024**3)
    total_gb = vm.total / (1024**3)
    return f"rss={rss_gb:.2f}GB system={used_gb:.1f}/{total_gb:.1f}GB"


@contextmanager
def heartbeat(label: str, every_seconds: int = 60):
    stop = threading.Event()
    started = time.time()

    def run() -> None:
        while not stop.wait(every_seconds):
            elapsed = (time.time() - started) / 60
            log(f"[heartbeat] {label}: elapsed={elapsed:.1f} min {memory_snapshot()}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2)
        elapsed = (time.time() - started) / 60
        log(f"[done-step] {label}: elapsed={elapsed:.1f} min {memory_snapshot()}")


class TextStatsTransformer(BaseEstimator, TransformerMixin):
    """Small writing-style features that are cheap and JS-portable."""

    feature_names_ = np.array(
        [
            "chars",
            "words",
            "avg_word_len",
            "punctuation",
            "question_marks",
            "exclamation_marks",
            "uppercase_ratio",
        ]
    )

    def fit(self, X: Iterable[str], y: Optional[Iterable[Any]] = None):
        return self

    def transform(self, X: Iterable[str]):
        rows = []
        for value in X:
            text = "" if value is None else str(value)
            words = text.split()
            chars = len(text)
            word_count = len(words)
            letters = [c for c in text if c.isalpha()]
            uppercase = sum(1 for c in letters if c.isupper())
            rows.append(
                [
                    chars,
                    word_count,
                    float(np.mean([len(w) for w in words])) if words else 0.0,
                    sum(1 for c in text if not c.isalnum() and not c.isspace()),
                    text.count("?"),
                    text.count("!"),
                    uppercase / len(letters) if letters else 0.0,
                ]
            )
        return sparse.csr_matrix(np.asarray(rows, dtype=np.float32))

    def get_feature_names_out(self, input_features=None):
        return self.feature_names_


def mount_drive_if_colab() -> None:
    try:
        from google.colab import drive  # type: ignore

        drive.mount("/content/drive/")
    except Exception as exc:
        print(f"[warn] Drive mount skipped or failed: {exc}")


def resolve_path(explicit: Optional[str], candidates: List[str], description: str) -> str:
    if explicit:
        if os.path.exists(explicit):
            return explicit
        raise FileNotFoundError(f"{description} path does not exist: {explicit}")

    checked = []
    for candidate in candidates:
        checked.append(candidate)
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(f"Could not find {description}. Checked: {checked}")


def read_pandora(path: str, max_rows: Optional[int]) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0).columns.tolist()
    requested = [
        "author",
        TEXT_COL,
        "subreddit",
        "gender",
        "age",
        "mbti",
        "introverted",
        "intuitive",
        "thinking",
        "perceiving",
        "is_female",
        "country",
    ]
    usecols = [col for col in requested if col in header]
    kwargs: Dict[str, Any] = {"usecols": usecols, "low_memory": False}
    if max_rows is not None:
        kwargs["nrows"] = max_rows

    print(f"[load] PANDORA: {path}")
    print(f"[load] Columns: {usecols}")
    started = time.time()
    df = pd.read_csv(path, **kwargs)
    print(f"[load] Loaded {df.shape} in {(time.time() - started) / 60:.2f} min")
    return df


def attach_profile_labels(comments: pd.DataFrame, profiles_path: str) -> pd.DataFrame:
    label_cols = [
        "gender",
        "age",
        "mbti",
        "introverted",
        "intuitive",
        "thinking",
        "perceiving",
        "is_female",
        "country",
    ]
    existing = [col for col in label_cols if col in comments.columns]
    if existing:
        print(f"[profiles] PANDORA already has label columns: {existing}")

    if "author" not in comments.columns:
        if existing:
            return comments
        raise ValueError("PANDORA has no author column and no labels; cannot train profile models.")

    profile_header = pd.read_csv(profiles_path, nrows=0).columns.tolist()
    profile_cols = ["author", *[col for col in label_cols if col in profile_header]]
    if len(profile_cols) == 1:
        raise ValueError(f"No usable label columns found in {profiles_path}")

    print(f"[profiles] Profiles: {profiles_path}")
    print(f"[profiles] Columns: {profile_cols}")
    started = time.time()
    profiles = pd.read_csv(profiles_path, usecols=profile_cols, low_memory=False)
    profiles = profiles.dropna(subset=["author"]).drop_duplicates("author")
    profiles["author"] = profiles["author"].astype(str)
    print(f"[profiles] Loaded {len(profiles):,} authors in {(time.time() - started) / 60:.2f} min")

    out = comments.copy()
    out["author"] = out["author"].astype(str)
    before = len(out)
    out = out[out["author"].isin(set(profiles["author"]))].copy()
    print(f"[profiles] Kept {len(out):,}/{before:,} comments with author profiles")

    merge_cols = ["author"]
    for col in profile_cols:
        if col == "author":
            continue
        if col not in out.columns or out[col].isna().any():
            merge_cols.append(col)

    merged = out.merge(profiles[merge_cols], on="author", how="left", suffixes=("", "_profile"))
    for col in profile_cols:
        profile_col = f"{col}_profile"
        if profile_col not in merged.columns:
            continue
        if col in merged.columns:
            merged[col] = merged[col].where(merged[col].notna(), merged[profile_col])
            merged = merged.drop(columns=[profile_col])
        else:
            merged = merged.rename(columns={profile_col: col})

    print(f"[profiles] Joined shape: {merged.shape}")
    return merged


def to_binary(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.where(values.isin([0, 1]))


def prepare_targets(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], List[str]]:
    out = df.copy()
    out[TEXT_COL] = (
        out[TEXT_COL]
        .fillna("")
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    out = out[out[TEXT_COL].str.len() >= MIN_TEXT_CHARS].copy()

    for col in ["is_female", "introverted", "intuitive", "thinking", "perceiving"]:
        if col in out.columns:
            out[col] = to_binary(out[col])

    if "gender" in out.columns:
        if "is_female" not in out.columns:
            out["is_female"] = out["gender"].map({"f": 1, "m": 0})
        else:
            missing = out["is_female"].isna()
            out.loc[missing, "is_female"] = out.loc[missing, "gender"].map({"f": 1, "m": 0})

    if "age" in out.columns:
        age = pd.to_numeric(out["age"], errors="coerce")
        out["age_under_25"] = np.where(age.notna(), (age < 25).astype(float), np.nan)
        out["age_35_plus"] = np.where(age.notna(), (age >= 35).astype(float), np.nan)
        out["age_bucket"] = pd.cut(
            age,
            bins=[-np.inf, 24, 34, np.inf],
            labels=["under_25", "25_34", "35_plus"],
        ).astype("object")

    if "country" in out.columns:
        country = out["country"].fillna("").astype(str).str.strip().str.lower()
        out["country_us"] = np.where(country != "", (country == "us").astype(float), np.nan)

    binary = [target for target in BINARY_TARGETS if target in out.columns]
    multiclass = [target for target in MULTICLASS_TARGETS if target in out.columns]
    print("[targets] Binary:", binary)
    print("[targets] Multiclass:", multiclass)
    return out, binary, multiclass


def logistic(c: float, max_iter: int = 800) -> LogisticRegression:
    return LogisticRegression(
        C=c,
        max_iter=max_iter,
        class_weight="balanced",
        solver="saga",
        n_jobs=-1,
        random_state=RANDOM_STATE,
        verbose=1,
    )


def make_feature_union(max_word_features: int, max_char_features: int, include_stats: bool = True) -> FeatureUnion:
    transformer_list = [
        (
            "word",
            TfidfVectorizer(
                lowercase=True,
                strip_accents="unicode",
                stop_words="english",
                analyzer="word",
                ngram_range=(1, 2),
                min_df=3,
                max_df=0.95,
                max_features=max_word_features,
                sublinear_tf=True,
            ),
        ),
        (
            "char",
            TfidfVectorizer(
                lowercase=True,
                strip_accents="unicode",
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=5,
                max_df=0.95,
                max_features=max_char_features,
                sublinear_tf=True,
            ),
        ),
    ]
    if include_stats:
        transformer_list.append(("stats", TextStatsTransformer()))
    return FeatureUnion(
        transformer_list,
        n_jobs=-1,
    )


def word_tfidf(max_features: int) -> TfidfVectorizer:
    return TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        stop_words="english",
        analyzer="word",
        ngram_range=(1, 2),
        min_df=3,
        max_df=0.95,
        max_features=max_features,
        sublinear_tf=True,
    )


def make_candidates(binary: bool, profile: str = "balanced") -> List[Tuple[str, Pipeline]]:
    fast_candidates: List[Tuple[str, Pipeline]] = [
        (
            "word_tfidf_sgd_logloss_fast",
            Pipeline(
                [
                    ("features", word_tfidf(140_000)),
                    (
                        "clf",
                        SGDClassifier(
                            loss="log_loss",
                            alpha=1e-5,
                            class_weight="balanced",
                            max_iter=50,
                            tol=1e-3,
                            n_jobs=-1,
                            random_state=RANDOM_STATE,
                            verbose=1,
                        ),
                    ),
                ]
            ),
        ),
        (
            "word_tfidf_logreg_c1_fast",
            Pipeline([("features", word_tfidf(120_000)), ("clf", logistic(1.0, max_iter=450))]),
        ),
    ]

    balanced_candidates: List[Tuple[str, Pipeline]] = [
        (
            "word_char_sgd_logloss_balanced",
            Pipeline(
                [
                    ("features", make_feature_union(120_000, 60_000, include_stats=False)),
                    (
                        "clf",
                        SGDClassifier(
                            loss="log_loss",
                            alpha=7e-6,
                            class_weight="balanced",
                            max_iter=70,
                            tol=8e-4,
                            n_jobs=-1,
                            random_state=RANDOM_STATE,
                            verbose=1,
                        ),
                    ),
                ]
            ),
        ),
        (
            "word_char_stats_logreg_c1_balanced",
            Pipeline([("features", make_feature_union(120_000, 60_000)), ("clf", logistic(1.0, max_iter=700))]),
        ),
    ]

    heavy_candidates: List[Tuple[str, Pipeline]] = [
        (
            "word_char_stats_logreg_c1_heavy",
            Pipeline([("features", make_feature_union(160_000, 90_000)), ("clf", logistic(1.0, max_iter=1100))]),
        ),
        (
            "word_char_stats_logreg_c3_heavy",
            Pipeline([("features", make_feature_union(200_000, 120_000)), ("clf", logistic(3.0, max_iter=1300))]),
        ),
        (
            "word_char_stats_sgd_logloss_heavy",
            Pipeline(
                [
                    ("features", make_feature_union(220_000, 130_000)),
                    (
                        "clf",
                        SGDClassifier(
                            loss="log_loss",
                            alpha=1e-5,
                            class_weight="balanced",
                            max_iter=120,
                            tol=1e-3,
                            n_jobs=-1,
                            random_state=RANDOM_STATE,
                            verbose=1,
                        ),
                    ),
                ]
            ),
        ),
    ]

    if profile == "fast":
        candidates = fast_candidates
    elif profile == "heavy":
        candidates = fast_candidates + balanced_candidates + heavy_candidates
    else:
        candidates = fast_candidates + balanced_candidates

    if binary:
        candidates.append(
            (
                "word_tfidf_complement_nb",
                Pipeline(
                    [
                        (
                            "features",
                            word_tfidf(180_000),
                        ),
                        ("clf", ComplementNB(alpha=0.2)),
                    ]
                ),
            )
        )
    return candidates


def score_predictions(y_true: pd.Series, y_pred: Iterable[Any]) -> Dict[str, Any]:
    pred = pd.Series(list(y_pred), index=y_true.index)
    labels = sorted(pd.unique(pd.concat([y_true, pred], ignore_index=True)).tolist())
    return {
        "accuracy": float(accuracy_score(y_true, pred)),
        "macro_f1": float(f1_score(y_true, pred, average="macro", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
        "classification_report": classification_report(y_true, pred, labels=labels, zero_division=0, digits=4),
    }


def train_target(
    frame: pd.DataFrame,
    target: str,
    binary: bool,
    selection_sample: Optional[int],
    full_refit: bool,
    candidate_profile: str,
    heartbeat_seconds: int,
) -> Tuple[Optional[Pipeline], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    data = frame[[TEXT_COL, target]].dropna().copy()
    if binary:
        y = pd.to_numeric(data[target], errors="coerce")
        data = data[y.isin([0, 1])].copy()
        y = y[y.isin([0, 1])].astype(int)
    else:
        y = data[target].astype(str)

    vc = y.value_counts()
    if len(vc) < 2 or int(vc.min()) < MIN_CLASS_COUNT:
        log(f"[skip] {target}: insufficient class counts")
        log(vc.to_string())
        return None, None, []

    if selection_sample is not None and len(data) > selection_sample:
        keep_idx = (
            pd.DataFrame({"idx": data.index, "y": y.values})
            .groupby("y", group_keys=False)
            .apply(lambda g: g.sample(max(1, int(selection_sample * len(g) / len(data))), random_state=RANDOM_STATE))
            ["idx"]
            .to_numpy()
        )
        select_data = data.loc[keep_idx]
        select_y = y.loc[keep_idx]
        log(f"[select] {target}: using stratified sample {len(select_data):,}/{len(data):,}")
    else:
        select_data = data
        select_y = y

    X_train, X_test, y_train, y_test = train_test_split(
        select_data[TEXT_COL],
        select_y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=select_y,
    )

    log(f"[target] {target}")
    log(f"[target] full={len(data):,} select={len(select_data):,} train={len(X_train):,} test={len(X_test):,}")
    log(f"[target] class counts:\n{vc.to_string()}")

    rows: List[Dict[str, Any]] = []
    best_model: Optional[Pipeline] = None
    best_summary: Optional[Dict[str, Any]] = None
    best_score = -np.inf

    candidates = make_candidates(binary=binary, profile=candidate_profile)
    log(f"[target] {target}: candidate profile={candidate_profile}; candidates={[name for name, _ in candidates]}")

    for name, candidate in candidates:
        started = time.time()
        log(f"[fit] {target} :: {name} starting {memory_snapshot()}")
        try:
            model = clone(candidate)
            with heartbeat(f"{target}::{name} fit", every_seconds=heartbeat_seconds):
                model.fit(X_train, y_train)
            with heartbeat(f"{target}::{name} predict", every_seconds=heartbeat_seconds):
                pred = model.predict(X_test)
            metrics = score_predictions(y_test, pred)
            elapsed = (time.time() - started) / 60
            row = {
                "target": target,
                "candidate": name,
                "n_full": int(len(data)),
                "n_select": int(len(select_data)),
                "n_train": int(len(X_train)),
                "n_test": int(len(X_test)),
                "classes": [str(cls) for cls in sorted(pd.unique(select_y).tolist())],
                "elapsed_min": float(elapsed),
                **metrics,
            }
            rows.append(row)
            log(
                f"[score] {target} :: {name} "
                f"accuracy={metrics['accuracy']:.4f} macro_f1={metrics['macro_f1']:.4f} "
                f"balanced={metrics['balanced_accuracy']:.4f} elapsed={elapsed:.1f} min"
            )
            if float(metrics[SELECTION_METRIC]) > best_score:
                best_score = float(metrics[SELECTION_METRIC])
                best_model = model
                best_summary = row
        except Exception as exc:
            rows.append({"target": target, "candidate": name, "error": repr(exc)})
            log(f"[warn] {target} :: {name} failed: {exc}")
        finally:
            gc.collect()

    if best_model is None or best_summary is None:
        return None, None, rows

    if full_refit:
        log(f"[refit] {target}: refitting selected pipeline on all {len(data):,} rows")
        best_model = clone(best_model)
        with heartbeat(f"{target} final full refit", every_seconds=heartbeat_seconds):
            best_model.fit(data[TEXT_COL], y)

    best_summary = {
        **best_summary,
        "selected_metric": SELECTION_METRIC,
        "refit_on_full_target_rows": bool(full_refit),
    }
    return best_model, best_summary, rows


def export_pipeline_to_js(model: Pipeline, max_terms_per_component: Optional[int] = None) -> Dict[str, Any]:
    steps = dict(model.steps)
    clf = steps["clf"]
    features = steps["features"]

    components = []
    offset = 0

    if isinstance(features, FeatureUnion):
        transformers = features.transformer_list
    else:
        transformers = [("word", features)]

    for name, transformer in transformers:
        if isinstance(transformer, TextStatsTransformer):
            feature_names = transformer.get_feature_names_out().tolist()
            component_size = len(feature_names)
            components.append(
                {
                    "name": name,
                    "type": "text_stats",
                    "feature_names": feature_names,
                    "slice": [offset, offset + component_size],
                }
            )
            offset += component_size
            continue

        if not isinstance(transformer, TfidfVectorizer):
            raise TypeError(f"Unsupported transformer for JS export: {name} {type(transformer).__name__}")

        vocab_items = sorted(transformer.vocabulary_.items(), key=lambda item: item[1])
        if max_terms_per_component is not None:
            vocab_items = vocab_items[:max_terms_per_component]

        component_size = len(transformer.vocabulary_)
        components.append(
            {
                "name": name,
                "type": "tfidf",
                "analyzer": transformer.analyzer,
                "ngram_range": list(transformer.ngram_range),
                "lowercase": transformer.lowercase,
                "strip_accents": transformer.strip_accents,
                "stop_words": "english" if transformer.stop_words == "english" else None,
                "sublinear_tf": transformer.sublinear_tf,
                "norm": transformer.norm,
                "vocabulary": vocab_items,
                "idf": transformer.idf_.tolist(),
                "slice": [offset, offset + component_size],
            }
        )
        offset += component_size

    payload: Dict[str, Any] = {
        "classes": [str(cls) for cls in clf.classes_],
        "classifier": type(clf).__name__,
        "components": components,
    }
    if hasattr(clf, "coef_"):
        payload["kind"] = "linear_logits"
        payload["coef"] = np.asarray(clf.coef_).tolist()
        payload["intercept"] = np.asarray(clf.intercept_).tolist()
    elif hasattr(clf, "feature_log_prob_"):
        payload["kind"] = "naive_bayes_log_prob"
        payload["feature_log_prob"] = np.asarray(clf.feature_log_prob_).tolist()
        payload["class_log_prior"] = np.asarray(clf.class_log_prior_).tolist()
    else:
        raise TypeError(f"{type(clf).__name__} does not expose portable weights for JS export")
    return payload


def write_checkpoint(
    out_dir: str,
    models: Dict[str, Pipeline],
    selected: Dict[str, Dict[str, Any]],
    rows: List[Dict[str, Any]],
    config: Dict[str, Any],
    target: str,
) -> None:
    """Write a partial bundle so progress survives a Colab disconnect."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out / "texttraits_checkpoint_latest.joblib"
    metrics_path = out / "texttraits_checkpoint_metrics.csv"
    state_path = out / "texttraits_checkpoint_state.json"

    artifact = {
        "format": "texttraits_checkpoint_v1",
        "checkpoint_target": target,
        "created_at_unix": time.time(),
        "text_column": TEXT_COL,
        "models": models,
        "selected_metrics": selected,
        "label_notes": LABEL_NOTES,
        "config": config,
    }
    joblib.dump(artifact, checkpoint_path, compress=3)

    metric_rows = []
    for row in rows:
        cleaned = {k: v for k, v in row.items() if k != "classification_report"}
        if "classes" in cleaned:
            cleaned["classes"] = json.dumps(cleaned["classes"])
        metric_rows.append(cleaned)
    pd.DataFrame(metric_rows).to_csv(metrics_path, index=False)

    state_path.write_text(
        json.dumps(
            {
                "last_completed_target": target,
                "completed_targets": sorted(models.keys()),
                "checkpoint_path": str(checkpoint_path),
                "metrics_path": str(metrics_path),
                "updated_at_unix": time.time(),
                "config": config,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    log(f"[checkpoint] wrote latest checkpoint after {target}: {checkpoint_path}")


def export_artifacts(
    out_dir: str,
    pandora_path: str,
    profiles_path: str,
    models: Dict[str, Pipeline],
    selected: Dict[str, Dict[str, Any]],
    rows: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    model_path = out / "texttraits_full_model.joblib"
    manifest_path = out / "texttraits_full_manifest.json"
    metrics_path = out / "texttraits_full_metrics.csv"
    js_path = out / "texttraits_linear_js_bundle.json.gz"

    artifact = {
        "format": "texttraits_full_colab_v1",
        "created_at_unix": time.time(),
        "input_path": pandora_path,
        "profiles_path": profiles_path,
        "text_column": TEXT_COL,
        "models": models,
        "selected_metrics": selected,
        "label_notes": LABEL_NOTES,
        "config": config,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "pandas": pd.__version__,
        },
    }
    joblib.dump(artifact, model_path, compress=3)

    metric_rows = []
    for row in rows:
        cleaned = {k: v for k, v in row.items() if k != "classification_report"}
        if "classes" in cleaned:
            cleaned["classes"] = json.dumps(cleaned["classes"])
        metric_rows.append(cleaned)
    pd.DataFrame(metric_rows).to_csv(metrics_path, index=False)

    js_bundle = {
        "format": "texttraits_linear_js_v1",
        "created_at_unix": time.time(),
        "text_column": TEXT_COL,
        "label_notes": LABEL_NOTES,
        "targets": {},
    }
    for target, model in models.items():
        try:
            js_bundle["targets"][target] = export_pipeline_to_js(model)
        except Exception as exc:
            js_bundle["targets"][target] = {"error": repr(exc)}

    with gzip.open(js_path, "wt", encoding="utf-8") as f:
        json.dump(js_bundle, f)

    manifest = {
        "model_path": str(model_path),
        "metrics_path": str(metrics_path),
        "js_bundle_path": str(js_path),
        "pandora_path": pandora_path,
        "profiles_path": profiles_path,
        "format": artifact["format"],
        "targets": list(models.keys()),
        "selected_metrics": selected,
        "label_notes": LABEL_NOTES,
        "config": config,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\n[done] Exported:")
    print(f"  Python bundle: {model_path}")
    print(f"  JS bundle:     {js_path}")
    print(f"  Manifest:      {manifest_path}")
    print(f"  Metrics:       {metrics_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pandora", default=None, help="Path to PANDORA.csv. Defaults to discovered Drive paths.")
    parser.add_argument("--profiles", default=None, help="Path to author_profiles.csv. Defaults to discovered Drive paths.")
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for model artifacts.")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional debug row cap. Omit for full data.")
    parser.add_argument(
        "--selection-sample",
        type=int,
        default=500_000,
        help="Stratified rows per target used to choose model family. Use 0 to select on all labeled rows.",
    )
    parser.add_argument(
        "--candidate-profile",
        choices=["fast", "balanced", "heavy"],
        default="balanced",
        help="Candidate sweep size. Use fast for debugging, balanced for normal Colab runs, heavy for maximum search.",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=int,
        default=60,
        help="Log elapsed time and memory while long fits/predictions are running.",
    )
    parser.add_argument("--no-full-refit", action="store_true", help="Skip final refit on all rows for faster debugging.")
    parser.add_argument("--skip-drive-mount", action="store_true", help="Do not attempt google.colab drive.mount.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.skip_drive_mount:
        mount_drive_if_colab()

    pandora_path = resolve_path(
        args.pandora,
        [
            HARD_PANDORA_PATH,
            "/content/drive/MyDrive/Anay Agarwalla/Data/pandora_big_info.csv",
            "/content/drive/MyDrive/Anay Agarwalla/Data/pandora/PANDORA.csv",
            "/content/drive/MyDrive/PANDORA.csv",
        ],
        "PANDORA CSV",
    )
    profiles_path = resolve_path(
        args.profiles,
        [
            HARD_PROFILES_PATH,
            "/content/drive/MyDrive/Anay Agarwalla/Data/author_profiles.csv",
            "/content/drive/MyDrive/author_profiles.csv",
        ],
        "author profile CSV",
    )

    started = time.time()
    log(f"[start] args={vars(args)}")
    log(f"[start] {memory_snapshot()}")
    comments = read_pandora(pandora_path, args.max_rows)
    joined = attach_profile_labels(comments, profiles_path)
    frame, binary_targets, multiclass_targets = prepare_targets(joined)

    selection_sample = None if args.selection_sample == 0 else args.selection_sample
    full_refit = not args.no_full_refit

    models: Dict[str, Pipeline] = {}
    selected: Dict[str, Dict[str, Any]] = {}
    metric_rows: List[Dict[str, Any]] = []

    config = {
        "random_state": RANDOM_STATE,
        "test_size": TEST_SIZE,
        "min_text_chars": MIN_TEXT_CHARS,
        "min_class_count": MIN_CLASS_COUNT,
        "selection_metric": SELECTION_METRIC,
        "selection_sample": selection_sample,
        "candidate_profile": args.candidate_profile,
        "heartbeat_seconds": args.heartbeat_seconds,
        "full_refit": full_refit,
        "max_rows": args.max_rows,
        "frame_shape_after_join_and_clean": list(frame.shape),
    }

    for target in binary_targets:
        model, summary, rows = train_target(
            frame,
            target,
            True,
            selection_sample,
            full_refit,
            args.candidate_profile,
            args.heartbeat_seconds,
        )
        metric_rows.extend(rows)
        if model is not None and summary is not None:
            models[target] = model
            selected[target] = summary
            write_checkpoint(args.out_dir, models, selected, metric_rows, config, target)

    for target in multiclass_targets:
        model, summary, rows = train_target(
            frame,
            target,
            False,
            selection_sample,
            full_refit,
            args.candidate_profile,
            args.heartbeat_seconds,
        )
        metric_rows.extend(rows)
        if model is not None and summary is not None:
            models[target] = model
            selected[target] = summary
            write_checkpoint(args.out_dir, models, selected, metric_rows, config, target)

    if not models:
        raise RuntimeError("No models trained. Check profile join, labels, and class counts.")

    export_artifacts(args.out_dir, pandora_path, profiles_path, models, selected, metric_rows, config)
    log(f"[done] Total elapsed: {(time.time() - started) / 60:.2f} min")


if __name__ == "__main__":
    main()
