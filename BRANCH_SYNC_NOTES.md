# Branch Sync Notes

This branch exists to keep the advanced production app work in sync with the
newer public-demo and training workflow commits.

## Branches Reviewed

- `main`: simpler deploy-ready public demo branch.
- `origin/codex/pycharm-colab-setup`: current `main` plus Colab/PyCharm/training
  diagnostics workflow additions.
- `origin/codex/production-readiness`: advanced application branch with auth,
  workspace persistence, Postgres support, legal/security docs, and a larger
  Explorer/Enterprise app surface.

## Sync Branch

Current branch:

`codex/sync-production-readiness`

Base:

`origin/codex/production-readiness`

Merged in:

`origin/codex/pycharm-colab-setup`

Conflict policy used during sync:

- Keep `production-readiness` versions for the advanced app shell, WSGI,
  deployment config, requirements, and production/security test files.
- Bring in the newer training/Colab/model-diagnostics files.
- Keep the production Postgres/auth branch as the authoritative deploy target
  for the advanced app until it is explicitly merged to `main`.

## Supabase/Postgres Status

The app selects Postgres when either `TEXTTRAITS_DATABASE_URL` or `DATABASE_URL`
is set. `DATABASE_URL` alone is now covered by regression tests with a Supabase
pooler-shaped URL.

Relevant files:

- `texttraits_app/storage.py`
- `SUPABASE_POSTGRES_SETUP.md`
- `.env.example`
- `DEPLOYMENT.md`
- `tests/env_storage_regression_test.py`
- `tests/config_regression_test.py`

## Recommended Next Merge

1. Review and test `codex/sync-production-readiness`.
2. If accepted, merge it into `codex/production-readiness`.
3. Deploy `codex/production-readiness` or merge that reviewed branch into
   `main`.

Do not fast-forward `main` blindly. The production branch contains auth,
persistence, email/reset flows, legal/security docs, and a larger application
surface than the current simple public demo.
