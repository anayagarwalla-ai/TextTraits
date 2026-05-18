# TextTraits Colab Training

This folder contains the high-RAM one-shot trainer for the full PANDORA export.

## Discovered Google Drive Paths

The legacy Colab notebooks and logs point to these Drive locations:

- `/content/drive/MyDrive/Anay Agarwalla/Data/PANDORA.csv`
- `/content/drive/MyDrive/Anay Agarwalla/Data/author_profiles.csv`

`PANDORA.csv` may only contain raw comment columns such as `author`, `body`, and
`subreddit`. The trainer joins `author_profiles.csv` on `author` to recover the
labels needed for the web-demo models.

## Colab Command

```python
from google.colab import drive
drive.mount("/content/drive/")

!git clone https://github.com/csboi/TextTraits.git
%cd TextTraits
!python training/colab_one_shot_export.py
```

## Better Logged Colab Command

If a run appears frozen, use the logged trainer. It starts with faster model
candidates, prints heartbeat/memory logs during long fits, and writes checkpoint
artifacts after each completed target.

```python
from google.colab import drive
drive.mount("/content/drive/")

!git clone https://github.com/csboi/TextTraits.git
%cd TextTraits
!python training/colab_one_shot_export_logged.py --candidate-profile balanced --selection-sample 500000
```

## Supervised One-Shot Command

For the most observable high-RAM run, prefer the supervisor wrapper. It runs the
logged trainer, tees output to Drive, and continuously updates `RUN_STATUS.json`
so a disconnected or frozen-looking notebook can be inspected later.

```python
from google.colab import drive
drive.mount("/content/drive/")

!git clone https://github.com/csboi/TextTraits.git
%cd TextTraits
!python training/colab_supervised_export.py run --candidate-profile balanced --selection-sample 500000
```

Monitor an existing supervised run without loading PANDORA:

```python
%cd /content/TextTraits
!python training/colab_supervised_export.py monitor --watch
```

For pasteable clone/update cells, see `training/COLAB_ONE_SHOT.md`.

## PyCharm Colab Setup

PyCharm 2025.3.2+ can connect a local notebook to a Google Colab server. For
that workflow, open `training/pycharm_colab_one_shot.ipynb` in PyCharm and use
the notebook server menu to sign in to Google and create a Colab server. See
`training/PYCHARM_COLAB_SETUP.md` for the local setup notes.

## Remote Worker Option

If PyCharm cannot reach a Colab server or does not expose the needed high-RAM
runtime shape, use `training/COLAB_REMOTE_WORKER.md`. That workflow starts a
browser Colab high-RAM cell that polls a GitHub job JSON and writes status to
Drive. It avoids SSH, tunnels, inbound ports, and arbitrary remote code
execution.

For a very fast debugging run:

```python
!python training/colab_one_shot_export_logged.py --candidate-profile fast --selection-sample 200000 --no-full-refit
```

For a slower maximum-search run:

```python
!python training/colab_one_shot_export_logged.py --candidate-profile heavy --selection-sample 1000000
```

For a faster smoke test:

```python
!python training/colab_one_shot_export.py --max-rows 500000 --selection-sample 200000 --no-full-refit
```

## Outputs

By default the script writes to:

`/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_full_export`

Expected files:

- `texttraits_full_model.joblib`: Python bundle for Flask/local inference.
- `texttraits_full_manifest.json`: model paths, config, target metrics, labels.
- `texttraits_full_metrics.csv`: candidate-by-candidate validation metrics.
- `texttraits_linear_js_bundle.json.gz`: portable linear model data for future
  JavaScript/browser-extension inference.
- `texttraits_checkpoint_latest.joblib`: partial checkpoint from the logged
  trainer after the latest completed target.
- `texttraits_checkpoint_state.json`: checkpoint state and completed targets.
- `RUN_STATUS.json`: supervised run state, file inventory, recent metrics, and
  log tail.
- `run.log`: durable stdout/stderr log from the supervised run.

The JS bundle is intentionally a data export, not a finished JS runtime. It
contains TF-IDF vocabularies, IDF values, linear coefficients, intercepts, class
labels, and feature metadata. A later JS predictor must reproduce the same
tokenization and TF-IDF normalization.
