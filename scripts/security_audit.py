from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".venv", "venv", "node_modules", "artifacts"}
SKIP_SUFFIXES = {".joblib", ".sqlite", ".sqlite3", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip"}

RISK_PATTERNS = (
    (re.compile(r'TEXTTRAITS_ALLOW_DEMO",\s*True'), "Demo mode must not default on."),
    (re.compile(r'TEMPLATES_AUTO_RELOAD"\]\s*=\s*True'), "Template auto-reload must follow dev-only config."),
    (re.compile(r"debug\s*=\s*True"), "Flask debug mode must not be hard-coded on."),
    (re.compile(r"data-copy-text"), "Do not place generated/user text into HTML data attributes."),
    (re.compile(r"(verification_token|reset_token)\s*=\s*\?\s+OR\s+\1\s*=\s*\?"), "Token lookup must not allow plaintext fallback."),
    (re.compile(r'public_url\(f?"/api/(reset-password|verify-email)\?token='), "Account emails must not create tokenized query-string URLs."),
    (re.compile(r"console_email.*body="), "Console email logs must not include email bodies or one-time codes."),
    (re.compile(r'TEXTTRAITS_DEV_ACCOUNT_LINKS",\s*not\s+PRODUCTION'), "Development account links must default off and be explicitly enabled."),
    (re.compile(r'"client_secret_env"\s*:'), "Public JSON must never expose client secret environment variable names."),
    (re.compile(r'@app\.get\("/api/integrations/<provider>/oauth/start"\)'), "OAuth start must be CSRF-protected POST."),
    (re.compile(r"uses:\s*actions/(checkout|setup-python|setup-node)@v[1-5]\b"), "Use Node 24-ready GitHub Actions v6 or newer."),
)


def iter_text_files():
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path == Path(__file__).resolve():
            continue
        if path.stat().st_size > 1_000_000:
            continue
        yield path


def main() -> int:
    failures: list[str] = []
    for path in iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(ROOT)
        for pattern, message in RISK_PATTERNS:
            if pattern.search(text):
                failures.append(f"{relative}: {message}")

    if failures:
        print("Security audit found issues:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Security audit checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
