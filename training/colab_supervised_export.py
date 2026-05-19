# -*- coding: utf-8 -*-
"""Supervised one-shot Colab export for TextTraits.

This wrapper runs ``colab_one_shot_export_logged.py`` while writing durable
status files to Google Drive. It is meant for high-RAM Colab sessions where the
training process may run for a long time or disconnect from the notebook UI.

Typical Colab command:

    !python training/colab_supervised_export.py run --candidate-profile balanced --selection-sample 500000

Monitor an existing run without loading PANDORA:

    !python training/colab_supervised_export.py monitor --watch
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import psutil
except Exception:
    psutil = None


HARD_PANDORA_PATH = "/content/drive/MyDrive/Anay Agarwalla/Data/PANDORA.csv"
HARD_PROFILES_PATH = "/content/drive/MyDrive/Anay Agarwalla/Data/author_profiles.csv"
DEFAULT_OUTPUT_DIR = "/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_full_export"

EXPECTED_FILES = [
    "RUN_STATUS.json",
    "run.log",
    "texttraits_full_model.joblib",
    "texttraits_full_manifest.json",
    "texttraits_full_metrics.csv",
    "texttraits_linear_js_bundle.json.gz",
    "texttraits_checkpoint_latest.joblib",
    "texttraits_checkpoint_metrics.csv",
    "texttraits_checkpoint_state.json",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{size}B"


def memory_snapshot() -> Dict[str, Any]:
    if psutil is None:
        return {"available": False, "note": "psutil unavailable"}
    process = psutil.Process(os.getpid())
    virtual = psutil.virtual_memory()
    return {
        "available": True,
        "supervisor_rss_gb": round(process.memory_info().rss / (1024**3), 3),
        "system_used_gb": round(virtual.used / (1024**3), 3),
        "system_total_gb": round(virtual.total / (1024**3), 3),
        "system_percent": virtual.percent,
    }


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def file_status(out_dir: Path) -> Dict[str, Dict[str, Any]]:
    statuses: Dict[str, Dict[str, Any]] = {}
    for name in EXPECTED_FILES:
        path = out_dir / name
        if path.exists():
            stat = path.stat()
            statuses[name] = {
                "exists": True,
                "size_bytes": stat.st_size,
                "size": human_bytes(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
            }
        else:
            statuses[name] = {"exists": False}
    return statuses


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": repr(exc)}


def metrics_tail(path: Path, limit: int = 8) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return rows[-limit:]
    except Exception as exc:
        return [{"error": repr(exc)}]


def log_tail(path: Path, limit: int = 30) -> List[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except Exception as exc:
        return [f"[monitor-error] Could not read log: {exc!r}"]


def build_snapshot(out_dir: Path, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    checkpoint_state = read_json(out_dir / "texttraits_checkpoint_state.json")
    full_manifest = read_json(out_dir / "texttraits_full_manifest.json")
    payload: Dict[str, Any] = {
        "updated_at": utc_now(),
        "out_dir": str(out_dir),
        "files": file_status(out_dir),
        "memory": memory_snapshot(),
        "checkpoint_state": checkpoint_state,
        "metrics_tail": metrics_tail(out_dir / "texttraits_checkpoint_metrics.csv")
        or metrics_tail(out_dir / "texttraits_full_metrics.csv"),
        "full_manifest_summary": summarize_manifest(full_manifest),
        "log_tail": log_tail(out_dir / "run.log", limit=20),
    }
    if extra:
        payload.update(extra)
    return payload


def summarize_manifest(manifest: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not manifest:
        return manifest
    return {
        "format": manifest.get("format"),
        "targets": manifest.get("targets"),
        "model_path": manifest.get("model_path"),
        "metrics_path": manifest.get("metrics_path"),
        "js_bundle_path": manifest.get("js_bundle_path"),
        "selected_metrics": manifest.get("selected_metrics"),
        "config": manifest.get("config"),
    }


def mount_drive_if_colab() -> None:
    try:
        from google.colab import drive  # type: ignore

        drive.mount("/content/drive/")
    except Exception as exc:
        print(f"[warn] Drive mount skipped or failed: {exc}", flush=True)


def resolve_script_path() -> Path:
    here = Path(__file__).resolve()
    script = here.with_name("colab_one_shot_export_logged.py")
    if not script.exists():
        raise FileNotFoundError(f"Could not find trainer beside supervisor: {script}")
    return script


def trainer_command(args: argparse.Namespace) -> List[str]:
    cmd = [
        sys.executable,
        str(resolve_script_path()),
        "--pandora",
        args.pandora,
        "--profiles",
        args.profiles,
        "--out-dir",
        args.out_dir,
        "--selection-sample",
        str(args.selection_sample),
        "--selection-metric",
        args.selection_metric,
        "--split-mode",
        args.split_mode,
        "--author-col",
        args.author_col,
        "--candidate-profile",
        args.candidate_profile,
        "--heartbeat-seconds",
        str(args.heartbeat_seconds),
        "--skip-drive-mount",
    ]
    if args.max_rows is not None:
        cmd.extend(["--max-rows", str(args.max_rows)])
    if args.no_full_refit:
        cmd.append("--no-full-refit")
    return cmd


def validate_inputs(args: argparse.Namespace, out_dir: Path, status_path: Path) -> None:
    missing = [path for path in [args.pandora, args.profiles] if not Path(path).exists()]
    if missing:
        snapshot = build_snapshot(
            out_dir,
            {
                "status": "blocked",
                "reason": "missing_input_files",
                "missing": missing,
                "pandora": args.pandora,
                "profiles": args.profiles,
            },
        )
        atomic_write_json(status_path, snapshot)
        raise FileNotFoundError(f"Missing required input files: {missing}")


def run_training(args: argparse.Namespace) -> int:
    if not args.skip_drive_mount:
        mount_drive_if_colab()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "RUN_STATUS.json"
    log_path = out_dir / "run.log"
    validate_inputs(args, out_dir, status_path)

    cmd = trainer_command(args)
    started = time.time()
    shared: Dict[str, Any] = {
        "status": "running",
        "started_at": utc_now(),
        "command": cmd,
        "last_log_line": None,
        "pid": None,
    }
    stop = threading.Event()

    def write_status_loop() -> None:
        while not stop.wait(args.poll_seconds):
            elapsed = round((time.time() - started) / 60, 3)
            atomic_write_json(status_path, build_snapshot(out_dir, {**shared, "elapsed_min": elapsed}))

    print(f"[supervisor] Output dir: {out_dir}", flush=True)
    print(f"[supervisor] Status:     {status_path}", flush=True)
    print(f"[supervisor] Log:        {log_path}", flush=True)
    print(f"[supervisor] Command:    {' '.join(cmd)}", flush=True)

    atomic_write_json(status_path, build_snapshot(out_dir, shared))
    thread = threading.Thread(target=write_status_loop, daemon=True)
    thread.start()

    with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"\n\n[supervisor] started_at={shared['started_at']}\n")
        log_file.write(f"[supervisor] command={' '.join(cmd)}\n")
        log_file.flush()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        shared["pid"] = process.pid
        try:
            assert process.stdout is not None
            for line in process.stdout:
                line = line.rstrip("\n")
                shared["last_log_line"] = line
                print(line, flush=True)
                log_file.write(line + "\n")
                log_file.flush()
        finally:
            return_code = process.wait()
            stop.set()
            thread.join(timeout=5)

    elapsed = round((time.time() - started) / 60, 3)
    final_status = "completed" if return_code == 0 else "failed"
    atomic_write_json(
        status_path,
        build_snapshot(
            out_dir,
            {
                **shared,
                "status": final_status,
                "return_code": return_code,
                "finished_at": utc_now(),
                "elapsed_min": elapsed,
            },
        ),
    )
    print(f"[supervisor] Finished with status={final_status} return_code={return_code}", flush=True)
    print_monitor_summary(out_dir)
    return int(return_code)


def print_monitor_summary(out_dir: Path) -> None:
    snapshot = build_snapshot(out_dir)
    checkpoint = snapshot.get("checkpoint_state") or {}
    print("\n[monitor] Output directory")
    print(f"  {out_dir}")
    print("[monitor] Files")
    for name, info in snapshot["files"].items():
        if info.get("exists"):
            print(f"  yes {name} ({info.get('size')}, modified {info.get('modified_at')})")
        else:
            print(f"   no {name}")
    if checkpoint:
        print("[monitor] Checkpoint")
        print(f"  last_completed_target: {checkpoint.get('last_completed_target')}")
        print(f"  completed_targets: {checkpoint.get('completed_targets')}")
    if snapshot.get("metrics_tail"):
        print("[monitor] Recent metrics")
        for row in snapshot["metrics_tail"][-5:]:
            target = row.get("target", "?")
            candidate = row.get("candidate", "?")
            acc = row.get("accuracy", row.get("error", ""))
            macro = row.get("macro_f1", "")
            print(f"  {target} :: {candidate} accuracy={acc} macro_f1={macro}")
    if snapshot.get("log_tail"):
        print("[monitor] Log tail")
        for line in snapshot["log_tail"][-10:]:
            print(f"  {line}")


def monitor(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    while True:
        print_monitor_summary(out_dir)
        status = read_json(out_dir / "RUN_STATUS.json") or {}
        if not args.watch or status.get("status") in {"completed", "failed", "blocked"}:
            return 0
        print(f"\n[monitor] sleeping {args.poll_seconds}s; Ctrl-C to stop monitor only\n", flush=True)
        time.sleep(args.poll_seconds)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT_DIR, help="Drive output directory for artifacts and status.")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Status refresh interval.")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full supervised export.")
    add_common_args(run_parser)
    run_parser.add_argument("--pandora", default=HARD_PANDORA_PATH, help="Path to PANDORA.csv.")
    run_parser.add_argument("--profiles", default=HARD_PROFILES_PATH, help="Path to author_profiles.csv.")
    run_parser.add_argument("--max-rows", type=int, default=None, help="Optional debug row cap. Omit for full data.")
    run_parser.add_argument("--selection-sample", type=int, default=500_000, help="Rows per target for model selection.")
    run_parser.add_argument(
        "--selection-metric",
        choices=["accuracy", "macro_f1", "balanced_accuracy"],
        default="macro_f1",
        help="Metric used by the trainer to choose each target model.",
    )
    run_parser.add_argument(
        "--split-mode",
        choices=["author", "row"],
        default="author",
        help="Validation split for model selection. Author split is the honest PANDORA benchmark.",
    )
    run_parser.add_argument("--author-col", default="author", help="Author column for author-held-out splitting.")
    run_parser.add_argument("--candidate-profile", choices=["fast", "balanced", "heavy"], default="balanced")
    run_parser.add_argument("--heartbeat-seconds", type=int, default=60)
    run_parser.add_argument("--no-full-refit", action="store_true", help="Skip final all-row refit for debugging.")
    run_parser.add_argument("--skip-drive-mount", action="store_true", help="Do not call drive.mount.")

    monitor_parser = subparsers.add_parser("monitor", help="Inspect output files without loading PANDORA.")
    add_common_args(monitor_parser)
    monitor_parser.add_argument("--watch", action="store_true", help="Poll until completed, failed, or blocked.")

    args = parser.parse_args(argv)
    if args.poll_seconds < 5:
        parser.error("--poll-seconds must be at least 5")
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.command == "run":
            return run_training(args)
        if args.command == "monitor":
            return monitor(args)
        raise ValueError(args.command)
    except FileNotFoundError as exc:
        print(f"[blocked] {exc}", flush=True)
        return 2
    except KeyboardInterrupt:
        print("[interrupted] Monitor or training supervisor interrupted by user.", flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
