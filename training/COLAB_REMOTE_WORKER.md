# TextTraits Colab Remote Worker

This is the safest version of "remote control" for Colab: the Colab runtime
polls outward for a small job JSON, runs only approved TextTraits actions, and
writes status back to Google Drive. It does not open an inbound port, expose an
SSH server, or execute arbitrary code.

## Why Not Listen On A Port?

Colab runtimes are not normal public VMs. Inbound listeners are usually
unreachable without a tunnel, and tunnel/SSH approaches are brittle and can run
against Colab usage restrictions. A polling worker is more durable:

- Colab makes outbound requests to GitHub.
- Codex updates a job JSON and pushes it.
- Colab writes `REMOTE_WORKER_STATUS.json` and normal training artifacts to
  Drive.
- Codex can inspect those Drive artifacts.

## Start The Worker In Colab

Paste this into a browser Colab high-RAM runtime:

```python
from google.colab import drive
drive.mount("/content/drive/")

import os, subprocess

REPO_URL = "https://github.com/csboi/TextTraits.git"
BRANCH = "codex/pycharm-colab-setup"
REPO_DIR = "/content/TextTraits"

if os.path.exists(REPO_DIR):
    subprocess.run(["git", "-C", REPO_DIR, "fetch", "origin"], check=False)
else:
    subprocess.run(["git", "clone", REPO_URL, REPO_DIR], check=True)

subprocess.run(["git", "-C", REPO_DIR, "checkout", BRANCH], check=False)
subprocess.run(["git", "-C", REPO_DIR, "pull", "--ff-only", "origin", BRANCH], check=False)
os.chdir(REPO_DIR)

subprocess.run([
    "python",
    "training/colab_remote_worker.py",
    "--git-branch", BRANCH,
    "--poll-seconds", "60",
], check=False)
```

Leave the cell running. To stop the worker, dispatch a `stop` job.

## Dispatch A Job From Codex Or Local Git

Edit `training/colab_jobs/current_job.json`, change `job_id`, commit, and push
the branch the worker is polling.

Smoke test job:

```json
{
  "job_id": "smoke-2026-05-18-0001",
  "action": "run_supervised_export",
  "params": {
    "candidate_profile": "fast",
    "selection_sample": 200000,
    "max_rows": 500000,
    "no_full_refit": true,
    "heartbeat_seconds": 30,
    "poll_seconds": 30
  }
}
```

Full run job:

```json
{
  "job_id": "full-2026-05-18-0001",
  "action": "run_supervised_export",
  "params": {
    "candidate_profile": "balanced",
    "selection_sample": 500000,
    "heartbeat_seconds": 60,
    "poll_seconds": 60
  }
}
```

Monitor once:

```json
{
  "job_id": "monitor-2026-05-18-0001",
  "action": "monitor_once",
  "params": {}
}
```

Stop worker:

```json
{
  "job_id": "stop-2026-05-18-0001",
  "action": "stop",
  "params": {}
}
```

## Status Files

Default output directory:

`/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_full_export`

Worker files:

- `REMOTE_WORKER_STATUS.json`
- `REMOTE_WORKER_HISTORY.jsonl`
- `remote_worker_job_<job_id>.log`

Training files:

- `RUN_STATUS.json`
- `run.log`
- `texttraits_checkpoint_state.json`
- `texttraits_checkpoint_metrics.csv`
- `texttraits_full_manifest.json`
- `texttraits_full_metrics.csv`
- `texttraits_full_model.joblib`
- `texttraits_linear_js_bundle.json.gz`

## Guardrails

Supported actions are deliberately limited to:

- `noop`
- `monitor_once`
- `run_supervised_export`
- `stop`

Do not turn this into arbitrary code execution. If the training workflow needs a
new operation, add a named action to `colab_remote_worker.py`, review it, then
dispatch it through JSON.
