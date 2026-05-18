# -*- coding: utf-8 -*-
"""Git/Drive-polled remote worker for a TextTraits Colab runtime.

This is intentionally not a generic remote-code execution server. Colab is
best used here as a high-RAM worker that polls for small, whitelisted job specs,
runs approved TextTraits commands, and writes durable status back to Drive.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import psutil
except Exception:
    psutil = None


DEFAULT_BRANCH = "codex/pycharm-colab-setup"
DEFAULT_JOB_PATH = "training/colab_jobs/current_job.json"
DEFAULT_OUTPUT_DIR = "/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_full_export"
STATUS_NAME = "REMOTE_WORKER_STATUS.json"
HISTORY_NAME = "REMOTE_WORKER_HISTORY.jsonl"

ALLOWED_ACTIONS = {"noop", "monitor_once", "run_supervised_export", "stop"}
ALLOWED_PROFILES = {"fast", "balanced", "heavy"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def memory_snapshot() -> Dict[str, Any]:
    if psutil is None:
        return {"available": False, "note": "psutil unavailable"}
    virtual = psutil.virtual_memory()
    process = psutil.Process(os.getpid())
    return {
        "available": True,
        "worker_rss_gb": round(process.memory_info().rss / (1024**3), 3),
        "system_used_gb": round(virtual.used / (1024**3), 3),
        "system_total_gb": round(virtual.total / (1024**3), 3),
        "system_percent": virtual.percent,
    }


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": repr(exc)}


def mount_drive_if_colab() -> None:
    try:
        from google.colab import drive  # type: ignore

        drive.mount("/content/drive/")
    except Exception as exc:
        print(f"[warn] Drive mount skipped or failed: {exc}", flush=True)


def run_capture(cmd: List[str], cwd: Optional[Path] = None, log_path: Optional[Path] = None) -> Tuple[int, str]:
    print(f"[worker] running: {' '.join(cmd)}", flush=True)
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines: List[str] = []
    log_handle = log_path.open("a", encoding="utf-8", errors="replace") if log_path else None
    try:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\n")
            print(line, flush=True)
            lines.append(line)
            if log_handle:
                log_handle.write(line + "\n")
                log_handle.flush()
    finally:
        if log_handle:
            log_handle.close()
    return process.wait(), "\n".join(lines[-200:])


def load_job_from_git(repo_dir: Path, branch: str, job_path: str) -> Dict[str, Any]:
    subprocess.run(["git", "-C", str(repo_dir), "fetch", "origin", branch], check=False, stdout=subprocess.DEVNULL)
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "show", f"origin/{branch}:{job_path}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Could not read {job_path} from origin/{branch}")
    return json.loads(result.stdout)


def load_job(args: argparse.Namespace) -> Tuple[Optional[Dict[str, Any]], str]:
    if args.drive_job_file:
        path = Path(args.drive_job_file)
        if path.exists():
            payload = read_json(path)
            if payload is not None:
                return payload, str(path)
    try:
        payload = load_job_from_git(Path(args.repo_dir), args.git_branch, args.git_job_path)
        return payload, f"origin/{args.git_branch}:{args.git_job_path}"
    except Exception as exc:
        print(f"[worker] job fetch failed: {exc}", flush=True)
        return None, f"error: {exc!r}"


def validate_job(job: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    job_id = str(job.get("job_id") or "").strip()
    action = str(job.get("action") or "").strip()
    params = job.get("params") or {}
    if not job_id:
        raise ValueError("job_id is required")
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"action must be one of {sorted(ALLOWED_ACTIONS)}, got {action!r}")
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    return job_id, action, params


def bool_param(params: Dict[str, Any], name: str, default: bool = False) -> bool:
    value = params.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def int_param(params: Dict[str, Any], name: str, default: Optional[int] = None) -> Optional[int]:
    value = params.get(name, default)
    if value is None or value == "":
        return None
    return int(value)


def supervised_command(repo_dir: Path, out_dir: str, params: Dict[str, Any]) -> List[str]:
    profile = str(params.get("candidate_profile", "balanced"))
    if profile not in ALLOWED_PROFILES:
        raise ValueError(f"candidate_profile must be one of {sorted(ALLOWED_PROFILES)}")

    cmd = [
        sys.executable,
        "training/colab_supervised_export.py",
        "run",
        "--out-dir",
        out_dir,
        "--candidate-profile",
        profile,
        "--selection-sample",
        str(int_param(params, "selection_sample", 500_000)),
        "--heartbeat-seconds",
        str(int_param(params, "heartbeat_seconds", 60)),
        "--poll-seconds",
        str(int_param(params, "poll_seconds", 60)),
    ]
    max_rows = int_param(params, "max_rows", None)
    if max_rows is not None:
        cmd.extend(["--max-rows", str(max_rows)])
    if bool_param(params, "no_full_refit", False):
        cmd.append("--no-full-refit")
    return cmd


def monitor_command(out_dir: str) -> List[str]:
    return [
        sys.executable,
        "training/colab_supervised_export.py",
        "monitor",
        "--out-dir",
        out_dir,
        "--poll-seconds",
        "5",
    ]


def load_seen_job_ids(status_path: Path) -> List[str]:
    status = read_json(status_path) or {}
    seen = status.get("seen_job_ids") or []
    if isinstance(seen, list):
        return [str(item) for item in seen]
    return []


def worker_status(
    args: argparse.Namespace,
    status: str,
    source: str,
    seen_job_ids: List[str],
    current_job: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "updated_at": utc_now(),
        "status": status,
        "message": message,
        "repo_dir": args.repo_dir,
        "git_branch": args.git_branch,
        "git_job_path": args.git_job_path,
        "drive_job_file": args.drive_job_file,
        "job_source": source,
        "out_dir": args.out_dir,
        "poll_seconds": args.poll_seconds,
        "seen_job_ids": seen_job_ids[-50:],
        "current_job": current_job,
        "memory": memory_snapshot(),
    }


def execute_job(args: argparse.Namespace, job: Dict[str, Any], source: str, seen_job_ids: List[str]) -> bool:
    out_dir = Path(args.out_dir)
    status_path = out_dir / STATUS_NAME
    history_path = out_dir / HISTORY_NAME
    job_id, action, params = validate_job(job)

    if job_id in seen_job_ids:
        return False

    event = {
        "job_id": job_id,
        "action": action,
        "source": source,
        "started_at": utc_now(),
        "params": params,
    }
    append_jsonl(history_path, {**event, "event": "started"})
    atomic_write_json(status_path, worker_status(args, "running_job", source, seen_job_ids, job))

    return_code = 0
    output_tail = ""
    try:
        if action == "noop":
            output_tail = "noop"
        elif action == "stop":
            output_tail = "stop requested"
        elif action == "monitor_once":
            log_path = out_dir / f"remote_worker_job_{job_id}.log"
            return_code, output_tail = run_capture(monitor_command(args.out_dir), cwd=Path(args.repo_dir), log_path=log_path)
        elif action == "run_supervised_export":
            log_path = out_dir / f"remote_worker_job_{job_id}.log"
            return_code, output_tail = run_capture(
                supervised_command(Path(args.repo_dir), args.out_dir, params),
                cwd=Path(args.repo_dir),
                log_path=log_path,
            )
        else:
            raise ValueError(action)
    except Exception as exc:
        return_code = 1
        output_tail = repr(exc)

    event.update(
        {
            "event": "finished",
            "finished_at": utc_now(),
            "return_code": return_code,
            "output_tail": output_tail,
        }
    )
    append_jsonl(history_path, event)
    seen_job_ids.append(job_id)
    final_status = "stopped" if action == "stop" else "idle"
    atomic_write_json(status_path, worker_status(args, final_status, source, seen_job_ids, job, output_tail[-1000:]))
    return action == "stop"


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", default="/content/TextTraits", help="Cloned TextTraits repo directory in Colab.")
    parser.add_argument("--git-branch", default=DEFAULT_BRANCH, help="Branch to poll for the job spec.")
    parser.add_argument("--git-job-path", default=DEFAULT_JOB_PATH, help="Path to job JSON inside the git branch.")
    parser.add_argument("--drive-job-file", default=None, help="Optional Drive JSON job file. Takes priority if present.")
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT_DIR, help="Drive output directory for status and artifacts.")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Polling interval.")
    parser.add_argument("--skip-drive-mount", action="store_true", help="Do not call drive.mount.")
    parser.add_argument("--once", action="store_true", help="Poll and execute at most one new job.")
    args = parser.parse_args(argv)
    if args.poll_seconds < 10:
        parser.error("--poll-seconds must be at least 10")
    return args


def main() -> int:
    args = parse_args()
    if not args.skip_drive_mount:
        mount_drive_if_colab()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / STATUS_NAME
    seen_job_ids = load_seen_job_ids(status_path)
    print(f"[worker] status: {status_path}", flush=True)
    print(f"[worker] polling origin/{args.git_branch}:{args.git_job_path}", flush=True)

    while True:
        job, source = load_job(args)
        if job is None:
            atomic_write_json(status_path, worker_status(args, "waiting", source, seen_job_ids, None, "no job available"))
        else:
            try:
                should_stop = execute_job(args, job, source, seen_job_ids)
                if should_stop:
                    return 0
            except Exception as exc:
                atomic_write_json(status_path, worker_status(args, "error", source, seen_job_ids, job, repr(exc)))
                append_jsonl(out_dir / HISTORY_NAME, {"event": "error", "updated_at": utc_now(), "error": repr(exc), "job": job})

        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
