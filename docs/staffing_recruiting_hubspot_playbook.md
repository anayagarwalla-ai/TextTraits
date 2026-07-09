# TextTraits HubSpot Playbook for Staffing and Recruiting

This playbook frames TextTraits for enterprises that use HubSpot across recruiting, client acquisition, lead routing, and campaign reporting.

## Best-fit HubSpot areas

- Campaigns: review marketing emails, forms, landing pages, pages, blog posts, sequences, and mapped-copy assets before scheduling.
- Marketing emails: run a pre-publish guardrail that returns score, gate, route, blocker, and next step without generating copy.
- Workflows: branch on `texttraits_gate`, `texttraits_route`, `texttraits_coverage_score`, and review-owner fields.
- Lists/segments: create or map Ready, Needs review, and Blocked segments for candidate/client routing.
- CRM records: treat contacts as candidates, companies as hiring clients, deals as job orders or placements, and tickets as support/compliance escalations.
- Owners/tasks: assign recruiter, marketing ops, compliance/legal, and regional-owner review tasks.
- Custom objects/timeline: persist TextTraits analysis records and timeline events for auditability.
- Reporting/export: inspect blocked-by-region, risky-claim type, review SLA, send-ready by business unit, and outcomes by audience segment.

## Workflow templates

1. Candidate nurture
   - Context: candidate status, skill family, region, recruiter, consent state.
   - Gate: block risky placement/guarantee language; review vague role descriptions.

2. Job alerts
   - Context: job ID, job family, location, pay/benefit source, job board.
   - Gate: require concrete role details and a clear next step.

3. Passive candidate reactivation
   - Context: stale segment, last contact date, skill family, region.
   - Gate: avoid pressure-heavy language and vague opportunity claims.

4. Client hiring campaigns
   - Context: client account, business unit, region, campaign ID.
   - Gate: route guaranteed-hire or candidate-availability claims to compliance.

5. Regional lead routing
   - Context: region, owner, business unit, skill family.
   - Gate: send high-risk copy to compliance/legal or regional owner before routing.

## Policy packs

TextTraits includes general staffing, US, EU, APAC, healthcare staffing, finance staffing, and public sector staffing policy packs. These are conservative defaults for claim review and should be tuned with the customer’s compliance team.

## What to demo

- Paste a job-alert email and show score, blocker, next step, policy version, and owner queue.
- Review a HubSpot campaign and show coverage score versus metadata-only assets.
- Import mapped SMS/social/ad copy from CSV and show that non-email assets can be scored without fake HubSpot API claims.
- Show the dashboard rollups: blocked by region, risky claim type, review SLA, send-ready by business unit, and outcomes by audience segment.
- Export the enriched audit CSV with policy version, reviewer, decision, timestamp, blocker, and final resolution.

## Honest limits

TextTraits does not generate emails and does not pretend to fetch draft copy from HubSpot surfaces where HubSpot only returns campaign associations or metadata. For ads, CTAs, marketing SMS, social posts, and workflow steps, teams should provide mapped copy from exports, workflow fields, or approved internal middleware until HubSpot exposes reviewable copy through a stable API surface.
