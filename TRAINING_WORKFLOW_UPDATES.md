# TextTraits Training Workflow Updates

This branch adds infrastructure for running and evaluating TextTraits model
workflows without requiring the local Codex machine to load the full PANDORA
dataset.

## What Was Added

### Supervised Colab Export

`training/colab_supervised_export.py`

Runs the existing logged Colab trainer while writing durable progress artifacts
to Google Drive:

- `RUN_STATUS.json`
- `run.log`
- `texttraits_checkpoint_state.json`
- `texttraits_checkpoint_metrics.csv`
- final model, manifest, metrics, and JavaScript bundle when complete

This is the recommended path for high-RAM Colab training. It does not change the
model architecture by itself; it makes long runs observable and recoverable.

### Pasteable Colab Instructions

`training/COLAB_ONE_SHOT.md`

Contains cells for:

- cloning/updating the repo in Colab;
- running a fast smoke test;
- running the full supervised export;
- monitoring an existing run without reloading PANDORA.

### PyCharm Colab Setup

`training/pycharm_colab_one_shot.ipynb`

Notebook entrypoint for PyCharm's Google Colab support.

`training/PYCHARM_COLAB_SETUP.md`

Explains how to open the notebook in PyCharm, sign into Google, create a Colab
server, and run smoke/full/monitor cells.

Note: PyCharm was installed locally as `PyCharm 2026.1.1`, but the actual Google
sign-in and Colab runtime selection remain interactive UI steps.

### Colab Remote Worker

`training/colab_remote_worker.py`

Optional polling worker for browser Colab sessions. It avoids SSH, tunnels,
credential scraping, and inbound ports. The worker polls a small GitHub job JSON
and only runs whitelisted actions:

- `noop`
- `monitor_once`
- `run_supervised_export`
- `stop`

Job file:

`training/colab_jobs/current_job.json`

Documentation:

`training/COLAB_REMOTE_WORKER.md`

### Model Output Diagnostics

`training/evaluate_model_outputs.py`

Evaluates an existing TextTraits model against a labeled CSV and writes:

- summary metrics JSON;
- row-level prediction CSV;
- accuracy, macro F1, balanced accuracy;
- majority/random baselines;
- confidence, margin, entropy;
- abstention coverage;
- calibration proxies;
- text-quality stats.

This can run locally on the available 500k PANDORA-derived CSV. Full 17.6M-row
PANDORA evaluation still belongs in Colab.

Example:

```powershell
python training\evaluate_model_outputs.py `
  --input-csv legacy_project\Data\pandora_big_info.csv `
  --max-rows 50000 `
  --sample-mode author `
  --output-dir output\model_diagnostics_local_50k
```

## Local Verification Performed

- `python -m py_compile` on new Python scripts.
- Notebook JSON validation for `training/pycharm_colab_one_shot.ipynb`.
- Local smoke test of the supervised export failure/status path.
- Local smoke test of the remote worker against the pushed GitHub branch.
- Local 5k and 50k model diagnostics runs against
  `legacy_project/Data/pandora_big_info.csv`.

The 50k diagnostic output was written locally under:

`output/model_diagnostics_local_50k/`

The `output/` directory remains ignored and is not committed.

## Current Boundary

These changes make high-RAM training easier to launch, monitor, and diagnose.
They do not include a new full-PANDORA trained model. The current committed model
artifacts are unchanged.

For a real full retrain/export, run the Colab one-shot workflow on a high-RAM
Colab runtime and monitor the Drive output directory:

`/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_full_export`
