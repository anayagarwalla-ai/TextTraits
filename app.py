from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "texttraits_app"
APP_FILE = APP_DIR / "app.py"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

spec = importlib.util.spec_from_file_location("texttraits_runtime_app", APP_FILE)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load TextTraits Flask app.")

module = importlib.util.module_from_spec(spec)
sys.modules.setdefault("texttraits_runtime_app", module)
spec.loader.exec_module(module)

app = module.app
application = app
