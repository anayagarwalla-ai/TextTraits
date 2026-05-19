# TextTraits High-RAM Colab One-Shot

Use this when the local Codex environment cannot load full PANDORA.

## One Cell: Clone, Train, Export, And Monitor

Paste this into a high-RAM Colab runtime. It mounts Drive, clones or updates the
repo, runs the supervised exporter, and writes status artifacts to Drive.

```python
from google.colab import drive
drive.mount("/content/drive/")

import os, subprocess, textwrap

REPO_URL = "https://github.com/csboi/TextTraits.git"
REPO_DIR = "/content/TextTraits"

if os.path.exists(REPO_DIR):
    subprocess.run(["git", "-C", REPO_DIR, "pull", "--ff-only"], check=False)
else:
    subprocess.run(["git", "clone", REPO_URL, REPO_DIR], check=True)

os.chdir(REPO_DIR)

cmd = [
    "python",
    "training/colab_supervised_export.py",
    "run",
    "--candidate-profile", "balanced",
    "--selection-sample", "500000",
    "--heartbeat-seconds", "60",
    "--poll-seconds", "60",
]
print("Running:", " ".join(cmd))
subprocess.run(cmd, check=False)
```

## Monitor Only

If training is already running or the notebook UI looks frozen, run this in a
separate cell. It does not load PANDORA.

```python
import os, subprocess
os.chdir("/content/TextTraits")

subprocess.run([
    "python",
    "training/colab_supervised_export.py",
    "monitor",
    "--watch",
    "--poll-seconds", "60",
], check=False)
```

## Fast Smoke Test

Use this before a full run to verify Drive paths and export wiring.

```python
from google.colab import drive
drive.mount("/content/drive/")

import os, subprocess

REPO_URL = "https://github.com/csboi/TextTraits.git"
REPO_DIR = "/content/TextTraits"

if os.path.exists(REPO_DIR):
    subprocess.run(["git", "-C", REPO_DIR, "pull", "--ff-only"], check=False)
else:
    subprocess.run(["git", "clone", REPO_URL, REPO_DIR], check=True)

os.chdir(REPO_DIR)

subprocess.run([
    "python",
    "training/colab_supervised_export.py",
    "run",
    "--candidate-profile", "fast",
    "--selection-sample", "200000",
    "--max-rows", "500000",
    "--no-full-refit",
    "--heartbeat-seconds", "30",
    "--poll-seconds", "30",
], check=False)
```

## Output Location

The default output directory is:

`/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_full_export`

Key files:

- `RUN_STATUS.json`: current run state, file inventory, checkpoint summary, log tail.
- `run.log`: tee of the trainer output.
- `texttraits_checkpoint_state.json`: latest completed target.
- `texttraits_checkpoint_metrics.csv`: partial metrics after completed targets.
- `texttraits_full_model.joblib`: final Python model bundle.
- `texttraits_full_manifest.json`: final model manifest and selected metrics.
- `texttraits_full_metrics.csv`: candidate-by-candidate metrics.
- `texttraits_linear_js_bundle.json.gz`: portable linear-weight export for future JS inference.

## What Codex Can Monitor From Here

Codex cannot start a Colab runtime directly from the local terminal. Once the
Colab cell is running, however, the Drive connector can inspect the files above,
especially `RUN_STATUS.json`, `run.log`, checkpoint state, and metrics, without
loading the full dataset locally.
