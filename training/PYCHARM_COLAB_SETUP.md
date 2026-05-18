# PyCharm Google Colab Setup

PyCharm's Google Colab support is useful here because full PANDORA training
needs a high-RAM Colab runtime, while the repo still benefits from IDE editing,
notebook execution, and remote file browsing.

## Local Prerequisite

Install PyCharm `2025.3.2` or newer. The local machine checked on
2026-05-18 did not have PyCharm installed through `winget list --name PyCharm`.

JetBrains setup flow:

1. Open this repo in PyCharm.
2. Open `training/pycharm_colab_one_shot.ipynb`.
3. Use the notebook server menu and select `Sign In to Google Account`.
4. After login, select `New Colab Server`.
5. Choose the largest/high-RAM Colab runtime available to the account.
6. Run the setup cell, then either the smoke-test, full-run, or monitor cell.

Current JetBrains limitation: debugging is not supported for Google Colab
servers. Treat this as an execution and inspection surface, not a debugger.

## Why This Is Still Useful

The notebook delegates training to `training/colab_supervised_export.py`, which:

- mounts Google Drive;
- verifies the expected Drive data files;
- runs the logged full-PANDORA trainer;
- writes a durable `run.log`;
- updates `RUN_STATUS.json`;
- writes checkpoints after completed targets;
- exports Python and JavaScript-portable model artifacts when training finishes.

Default output:

`/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_full_export`

## Important GitHub Detail

The notebook clones this GitHub repo into the Colab VM. For the notebook to see
new local scripts, those scripts must be pushed to the branch selected in the
notebook's `BRANCH` variable.

If you are testing local unpushed changes, use PyCharm's remote file view to
upload the changed files into `/content/TextTraits`, or push a temporary branch
and set `BRANCH` to that branch name.

## Monitor From Codex

Once the notebook is running, Codex can inspect Drive outputs from the local
environment through the Google Drive connector. The most useful files are:

- `RUN_STATUS.json`
- `run.log`
- `texttraits_checkpoint_state.json`
- `texttraits_checkpoint_metrics.csv`
- `texttraits_full_manifest.json`
- `texttraits_full_metrics.csv`
