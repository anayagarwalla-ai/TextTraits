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

Generic subject lines such as `Checking in`, `Follow up`, and `Quick question` receive a subject-specific finding because they do not name the concrete topic or decision. Specificity scoring also drops more sharply when a draft contains multiple configured vague phrases, so weak copy is lowered by the underlying checklist rather than by a hidden display cap.

HubSpot Email Fit does not run the separate TextTraits demographic/personality association model. That model was trained for a different task and is not an email-quality measure. HubSpot responses identify the versioned rules engine in `analysis_engine` and `texttraits_analysis_engine`, making the actual scoring source explicit and auditable.

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

- `rule_pack`: `general`, `sales`, `marketing`, `customer_success`, `healthcare`, or `finance`
- `ready_score_threshold`
- `review_score_threshold`
- `block_score_threshold`
- `block_if_no_cta`
- `block_high_severity_findings`
- `compliance_review_on_risk_terms`
- `require_personalization`
- `min_body_words`
- `max_body_words`
- `custom_risk_phrases`
- `custom_vague_phrases`
- `required_template_tokens`
- `required_headers`

Rule packs change the active risk phrases, vague-language phrases, required template tokens, and required sender headers. Custom phrase lists extend the selected pack. Saved policy affects future HubSpot CRM-card, workflow-action, and rendered-template-test analyses for the configured workspace/environment.
