from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "deep_research_runs"
DEFAULT_PLAN_PATH = ROOT / "texttraits_app" / "data" / "enterprise_integration_plan.json"

PENDING_MARKERS = (
    "deep research in progress",
    "researching",
    "still working",
    "generating",
    "log in",
    "sign up",
    "enable javascript",
    "just a moment",
)

COMPLETION_MARKERS = (
    "executive summary",
    "where to embed",
    "recommended touchpoints",
    "latency, privacy",
    "open questions",
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_url(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 TextTraitsDeepResearchPoller/1.0",
            "Accept": "text/html,text/plain,application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def extract_pdf(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise SystemExit("Install pypdf to extract PDFs: python -m pip install pypdf") from error

    reader = PdfReader(str(pdf_path))
    pages = []
    for index, page in enumerate(reader.pages, 1):
        pages.append(f"\n\n=== PAGE {index} ===\n\n{page.extract_text() or ''}")
    return normalize_text(f"PAGES: {len(reader.pages)}\n" + "".join(pages))


def looks_complete(text: str, min_chars: int) -> tuple[bool, str]:
    clean = normalize_text(text)
    lower = clean.lower()
    if len(clean) < min_chars:
        return False, f"only {len(clean)} characters"
    pending = [marker for marker in PENDING_MARKERS if marker in lower]
    if pending and not any(marker in lower for marker in COMPLETION_MARKERS):
        return False, f"pending/login markers found: {', '.join(pending[:3])}"
    found = [marker for marker in COMPLETION_MARKERS if marker in lower]
    if len(found) >= 2:
        return True, f"completion markers found: {', '.join(found[:4])}"
    return False, "completion markers not present yet"


def write_run(output_dir: Path, source: str, text: str, status: str, reason: str, plan_path: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    run_dir = output_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=False)

    text_path = run_dir / "deep_research_text.txt"
    text_path.write_text(text, encoding="utf-8")

    metadata = {
        "source": source,
        "status": status,
        "reason": reason,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "text_chars": len(text),
        "plan_path": str(plan_path.relative_to(ROOT)) if plan_path.exists() else None,
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        summary = [
            "# Deep Research Implementation Handoff",
            "",
            f"Source: {source}",
            f"Captured: {metadata['captured_at']}",
            f"Status: {status}",
            f"Reason: {reason}",
            "",
            "## Recommended Product Layer",
            "",
            plan["recommendation"]["positioning"],
            "",
            "## Primary Targets",
            "",
        ]
        for target in plan.get("targets", []):
            summary.append(f"- {target['label']}: {target['integration_layer']}")
        (run_dir / "implementation_handoff.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    return run_dir


def poll_url(args: argparse.Namespace) -> int:
    deadline = time.monotonic() + args.timeout
    last_text = ""
    last_reason = "not checked"
    attempt = 0

    while time.monotonic() <= deadline:
        attempt += 1
        try:
            text = fetch_url(args.url, args.request_timeout)
            complete, reason = looks_complete(text, args.min_chars)
            print(f"[poll] attempt={attempt} complete={complete} reason={reason}", flush=True)
            last_text = normalize_text(text)
            last_reason = reason
            if complete:
                run_dir = write_run(args.output_dir, args.url, last_text, "complete", reason, args.plan_path)
                print(f"[done] wrote {run_dir}", flush=True)
                return 0
        except (urllib.error.URLError, TimeoutError) as error:
            last_reason = str(error)
            print(f"[poll] attempt={attempt} error={last_reason}", flush=True)
        time.sleep(args.interval)

    if last_text:
        run_dir = write_run(args.output_dir, args.url, last_text, "incomplete", last_reason, args.plan_path)
        print(f"[timeout] latest response saved to {run_dir}", flush=True)
    else:
        print(f"[timeout] no readable response: {last_reason}", file=sys.stderr)
    return 2


def ingest_pdf(args: argparse.Namespace) -> int:
    text = extract_pdf(args.pdf)
    complete, reason = looks_complete(text, args.min_chars)
    status = "complete" if complete else "needs_review"
    run_dir = write_run(args.output_dir, str(args.pdf), text, status, reason, args.plan_path)
    print(f"[{status}] wrote {run_dir}", flush=True)
    return 0 if complete else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll or ingest deep research output for TextTraits enterprise work.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Public ChatGPT deep research URL to poll.")
    source.add_argument("--pdf", type=Path, help="Completed deep research PDF to extract immediately.")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between URL polls.")
    parser.add_argument("--timeout", type=int, default=3600, help="Total seconds to poll before giving up.")
    parser.add_argument("--request-timeout", type=int, default=20, help="Per-request timeout in seconds.")
    parser.add_argument("--min-chars", type=int, default=5000, help="Minimum extracted text length for a complete report.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    args = parser.parse_args()
    if args.pdf and not args.pdf.exists():
        parser.error(f"PDF does not exist: {args.pdf}")
    return args


def main() -> int:
    args = parse_args()
    if args.pdf:
        return ingest_pdf(args)
    return poll_url(args)


if __name__ == "__main__":
    raise SystemExit(main())
