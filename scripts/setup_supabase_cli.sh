#!/usr/bin/env bash
set -euo pipefail

PROJECT_REF="${SUPABASE_PROJECT_REF:-olacwelhrgzxzrxtmvto}"

cd "$(dirname "$0")/.."

if ! command -v supabase >/dev/null 2>&1; then
  cat >&2 <<'MSG'
Supabase CLI is not installed.

Install it first, then rerun this script:
  brew install supabase/tap/supabase

Or follow the latest Supabase CLI install guide for your OS.
MSG
  exit 1
fi

if ! supabase projects list >/dev/null 2>&1; then
  if [[ -n "${SUPABASE_ACCESS_TOKEN:-}" ]]; then
    supabase login --token "$SUPABASE_ACCESS_TOKEN"
  else
    supabase login
  fi
fi

if [[ ! -f "supabase/config.toml" ]]; then
  supabase init
fi

supabase link --project-ref "$PROJECT_REF"

cat <<MSG
Supabase CLI linked to project:
  $PROJECT_REF

Next:
  1. Copy the Supabase pooler connection string into DATABASE_URL.
  2. Run python scripts/preflight.py.
  3. Run python scripts/migrate.py.
MSG
