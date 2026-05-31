# B2B Profile Intelligence Platform

This branch extends TextTraits from email policy scoring into a B2B marketing intelligence workspace.

The product goal is to help a revenue, lifecycle, or marketing-operations team answer:

- What business priorities are visible in the communication history?
- Which objections should the next response address?
- Which buying-stage or workflow route should the account enter?
- What context can safely be passed to an LLM for response generation?

## Privacy Boundary

The profile engine is intentionally not a hidden PII or sensitive-trait inference system.

It does not return raw emails, phone numbers, demographic guesses, health status, religion, politics, sexual orientation, financial eligibility, or other sensitive personal labels. It returns business-facing signals such as operational risk, workflow fit, compliance concerns, budget timing, likely business role context, communication density, and next-best-action guidance.

## Runtime Surface

- `POST /v1/b2b/profile` builds a minimized B2B profile from consented communication history.
- The `/enterprise` UI includes a relationship-profile builder with sample account histories.
- The output includes safe features, matched business evidence terms, business priorities, objections, recommended angles, generation guardrails, CRM fields, and workflow uses. It does not return transcript previews.

## Model Roadmap

The current implementation is a deterministic profile engine that can run locally. The script `scripts/prepare_b2b_profile_model.py` prepares privacy-safe JSONL rows and a cloud-training manifest from consented exports. It does not train locally.

Expected training labels are business-safe:

- buying stage
- business priority
- objection signal
- role context
- next-best-action class
- outcome label

Blocked labels include raw identifiers, demographics, and sensitive personal attributes.

## Data Contract

The preparation script expects CSV rows with:

- `tenant_id`
- `account_id`
- `contact_id_hash`
- `consent_basis`
- `opt_out_state`
- `communication_history`
- `account_context`
- `campaign_goal`
- `outcome_label`

Each row keeps consent and opt-out state next to the communication evidence so downstream model training can enforce data boundaries.
