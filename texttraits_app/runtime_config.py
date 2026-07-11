from __future__ import annotations

import logging
import os


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        value = int(default)
    else:
        try:
            value = int(raw.strip())
        except ValueError:
            logging.warning("invalid_integer_environment name=%s fallback=%s", name, default)
            value = int(default)
    if minimum is not None and value < minimum:
        logging.warning("integer_environment_below_minimum name=%s value=%s minimum=%s", name, value, minimum)
        value = minimum
    if maximum is not None and value > maximum:
        logging.warning("integer_environment_above_maximum name=%s value=%s maximum=%s", name, value, maximum)
        value = maximum
    return value
