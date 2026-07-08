# Enterprise Demo Script

For the backend governance dashboard, load the synthetic CRM fixture first:

```bash
python scripts/migrate.py
python scripts/seed_demo_crm.py
```

The seed uses workspace `demo_hubspot_crm` and fictional accounts, contacts, deals, owners, campaigns, review actions, and outcomes from `texttraits_app/demo_data/hubspot_crm_demo.json`.

Use one HubSpot contact, such as Brian Halligan, and run three existing draft emails through the TextTraits email-fit card.

## 1. Good Email

Subject:

`Factory tour checklist`

Body:

`Hi Brian, I wanted to confirm whether Wednesday still works for the factory tour. If it does, reply by Friday and I will send the short checklist your team can review before the visit.`

Expected result:

- Gate: `ready`
- Route: `Sending system`
- Why: clear subject, enough body context, direct reply cue, timing cue, personalization, and no risky terms.

## 2. Vague Email

Subject:

`Checking`

Body:

`Thoughts?`

Expected result:

- Gate: `blocked`
- Route: `Marketing review`
- Why: body is too short, no clear next step, too little specificity, and weak audit evidence.

## 3. Risky Email

Subject:

`Guaranteed renewal savings`

Body:

`Hi Brian, this renewal is guaranteed to save 100% of the time your team spends on the process. Please approve today.`

Expected result:

- Gate: `blocked`
- Route: `Compliance review`
- Why: configured risk terms such as `guaranteed` and `100%` route the draft to compliance review.

## Demo Flow

1. Open a HubSpot contact record.
2. Paste each existing draft into the TextTraits email-fit card.
3. Show score, gate, route, evidence, and failed checks.
4. Use `Copy recommendation`, `Mark reviewed`, `Send to marketing review`, and `Re-run analysis`.
5. Show admin exports and dashboard endpoints for reporting.
