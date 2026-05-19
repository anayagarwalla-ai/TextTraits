# Colab Set-And-Forget Model Decision Run

Use this when the question is not only "did training finish?" but:

- did the full-PANDORA model beat the committed model?
- did it use an honest author-held-out validation split?
- which targets are strong enough to expose prominently?
- can the model be exported for JavaScript/static inference?
- do we have enough confidence, margin, and cue-term material for explainability?

## Notebook

Open this in high-RAM Colab:

```text
training/colab_set_and_forget_decision_run.ipynb
```

It writes timestamped results under:

```text
/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_decision_exports/
```

It also writes:

```text
/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_decision_exports/LATEST_RUN.json
```

That pointer records the latest output directory so the run can be inspected
later without searching Drive manually.

## Default Full Run

The full run uses:

```text
candidate_profile=heavy
selection_sample=1000000
selection_metric=macro_f1
split_mode=author
full_refit=true
```

The important choices are `selection_metric=macro_f1` and
`split_mode=author`. The previous row-level accuracy workflow could overstate
quality on PANDORA because comments by the same author can leak across train and
test. Macro F1 is also safer than accuracy when labels are imbalanced.

## Expected Decision Artifacts

Inside the full run output folder:

- `RUN_STATUS.json` - live status, recent logs, file inventory.
- `run.log` - durable stdout/stderr.
- `texttraits_checkpoint_latest.joblib` - latest partial model bundle.
- `texttraits_checkpoint_metrics.csv` - target/candidate metrics as they finish.
- `texttraits_full_model.joblib` - final Python model bundle.
- `texttraits_full_manifest.json` - final model manifest and selected metrics.
- `texttraits_full_metrics.csv` - all candidate metrics.
- `texttraits_linear_js_bundle.json.gz` - portable model weights for a future JS runtime.
- `texttraits_model_decision_summary.json` - machine-readable deploy/explainability summary.
- `texttraits_model_decision_summary.md` - human-readable model decision report.

## How To Monitor

If Colab disconnects or the browser looks frozen, reconnect and run the monitor
cell in the notebook. It does not reload PANDORA.

Equivalent command:

```python
!python training/colab_supervised_export.py monitor \
  --out-dir "/content/drive/MyDrive/Anay Agarwalla/Models/texttraits_decision_exports/<RUN_ID>/full_run" \
  --watch \
  --poll-seconds 60
```

## What To Send Back

Send back either:

- the `LATEST_RUN.json` contents; or
- the full Drive path ending in `/full_run`; or
- `texttraits_model_decision_summary.md`.

With that, Codex can inspect whether the new model is actually better and which
targets should drive the product.
