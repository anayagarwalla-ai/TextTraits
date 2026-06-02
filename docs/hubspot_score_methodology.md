# HubSpot Email Fit Score Methodology

TextTraits Email Fit scores an existing draft as a routing and governance signal. It does not write or rewrite the email.

## Score Inputs

The score starts with a 0-100 weighted checklist:

- Subject clarity, 15 points: subject exists, is scannable, and names the topic.
- Body completeness, 15 points: body has enough context without exceeding the configured CRM outreach length.
- Next-step clarity, 20 points: detects reply, confirm, schedule, review, send, or choose cues.
- Specificity, 20 points: rewards dates, times, numbers, names, and concrete anchors; flags vague phrases.
- Personalization, 10 points: detects named greetings, merge tokens, recipient-focused wording, and supplied CRM contact/company context.
- Readability, 10 points: checks average sentence length.
- Risk terms, 10 points: detects configured risky claims or pressure language.

Risk terms also apply explicit scoring penalties during the score calculation. Medium-risk language subtracts 25 points. High-risk language, such as `guaranteed`, `guarantee`, or `100%`, subtracts 45 points. That means a draft with strong structure can still receive a low score when the text itself contains risky claims.

Model confidence is shown as supporting evidence only. It is not averaged into the score.

## Evidence

Every failed check returns:

- `id`
- `severity`
- `title`
- `detail`
- `evidence`
- `next_step`
- `owner_queue`
- `blocker_level`
- `action`

Example: if no CTA pattern is found, the finding evidence says: `No reply, confirm, schedule, review, send, or choose cue was detected.`

## Policy Controls

Admins can configure policy with `PUT /api/enterprise/hubspot/policy`:

- `ready_score_threshold`
- `review_score_threshold`
- `block_score_threshold`
- `block_if_no_cta`
- `block_high_severity_findings`
- `compliance_review_on_risk_terms`
- `require_personalization`
- `min_body_words`
- `max_body_words`

Saved policy affects future HubSpot CRM-card and workflow-action analyses for the configured workspace/environment.
