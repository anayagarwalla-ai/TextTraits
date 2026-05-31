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
- The `/enterprise` UI also includes the Revenue Signal Lab, a front-end smoke surface that simulates how HubSpot, Salesforce, Marketo, Braze, or SendGrid/SES could call the profile and adapter APIs before any real customer credentials or user records exist.

## Integration Targets

The strongest B2B integration pattern is to sit inside tools teams already use rather than becoming another daily destination:

- HubSpot workflow custom action for lifecycle nurture routing and CRM property writeback.
- Salesforce Journey Builder activity for journey branching and revenue-operations review.
- Marketo Smart Campaign gate for program asset review before launch.
- Braze Canvas webhook step for lifecycle journey routing.
- SendGrid or Amazon SES middleware for pre-send policy gates and outcome joins.

The front-end simulator calls `/v1/b2b/profile` and `/v1/integrations/simulate` together, then displays the profile stage, next best action, adapter gate, writeback fields, and generation guardrails a platform user would see.

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
