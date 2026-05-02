from __future__ import annotations

import json

from predictor import TextTraitsPredictor


def main() -> None:
    predictor = TextTraitsPredictor()
    summary = {
        "model_path": str(predictor.model_path),
        "vectorizer": type(predictor.vectorizer).__name__,
        "models": {name: type(model).__name__ for name, model in predictor.models.items()},
        "metrics": predictor.metrics,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
