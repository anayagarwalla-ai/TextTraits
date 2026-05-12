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

The JS bundle is intentionally a data export, not a finished JS runtime. It
contains TF-IDF vocabularies, IDF values, linear coefficients, intercepts, class
labels, and feature metadata. A later JS predictor must reproduce the same
tokenization and TF-IDF normalization.
