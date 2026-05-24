# Enterprise Deep Research Integration Plan

Source reviewed: `Enterprise mass email architecture and third-party analysis integration.pdf`

## Product Decision

TextTraits should be incorporated into enterprise email stacks as an analytical scoring layer, not as a replacement ESP, CRM, marketing cloud, sales engagement platform, or MTA.

The best enterprise architecture is three-layered:

1. Authoring lint inside the campaign builder, template workflow, browser extension, or template CI/CD path.
2. Synchronous pre-send gate at publish, schedule, journey action, workflow action, or API-send middleware.
3. Asynchronous post-send analytics from provider webhooks, event streams, warehouse exports, or BI/CDP backfills.

This matters because no single hook sees the whole enterprise email lifecycle. Authoring sees templates and copy. Pre-send sees intent and launch context. Post-send sees delivery and outcome truth.

## Best Initial Targets

The highest-value first platform target is a HubSpot-style workflow custom action because it is understandable, mockable, and close to the actual business workflow: a contact enters a workflow, the email step is scored, and the workflow can continue, warn, or route to remediation.

The second target is Salesforce Marketing Cloud or Journey Builder because it is stronger for large-governance enterprise buyers, but it carries higher setup complexity.

The third target is SendGrid, Amazon SES, SparkPost, or Mailchimp Transactional API middleware because those systems are easier to model technically, but the integration is more latency-sensitive and less marketer-facing.

The fourth target is CDP and warehouse feedback through Segment, Snowflake, BigQuery, Databricks, Braze Currents, or similar exports because that is best for benchmarking, governance, and model tuning, but it cannot prevent a bad send by itself.

## Prototype Implemented In This Branch

This branch adds a research-backed integration lab to the enterprise optimizer. The lab lets a developer inspect:

- The recommended enterprise layer.
- Candidate platforms.
- What data TextTraits would receive.
- What verdicts and findings it would return.
- What a safe prototype should test.

The UI remains non-generative. It evaluates and routes existing email drafts rather than writing replacement copy.

## Design Constraints

- Do not bypass the system of record for consent, suppression, subscriber state, or unsubscribe handling.
- Preserve SPF, DKIM, DMARC, List-Unsubscribe, and one-click unsubscribe expectations.
- Prefer hashes, IDs, and minimized context over raw recipient PII.
- Keep fail-open and fail-closed behavior configurable by rule class.
- Attach deterministic request IDs and content hashes so findings can be joined back to campaign, template, and send records.
- Treat SMTP proxying as a legacy/drop-in option, not the primary enterprise product target.
