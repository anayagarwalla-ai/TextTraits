# TextTraits Legal And Privacy Review Checklist

This is an implementation checklist, not legal advice. Before a public launch, a qualified attorney or privacy specialist should review the final product, data flows, policies, and contracts.

## Product Behavior To Review

- Explorer accepts personal writing samples and may save writing history for signed-in users.
- Enterprise accepts prospect, campaign, brand voice, draft, reply, and outcome data.
- Text analysis runs through the Flask application. Workspace data syncs only for signed-in users.
- CRM, inbox, and sales engagement integrations are disabled until credentials are configured.
- Account export and account deletion routes are implemented.

## Policy Areas

- Privacy policy covers collected data, workspace sync, local storage, account data, logs, events, integrations, retention, export, deletion, and support contact.
- Terms cover generated copy review, acceptable use, team administrator responsibilities, integration credentials, compliance-sensitive outreach, and service availability.
- Enterprise agreements should address data processing, subprocessors, security controls, retention, audit logs, and incident response.
- Cold-email features need jurisdiction-specific review for CAN-SPAM, GDPR/ePrivacy, CASL, unsubscribe handling, and suppression lists.
- Sensitive inference copy and product limits should be reviewed for consumer-protection and employment/recruiting risks.

## Security And Privacy Controls

- Hosted Postgres has encrypted storage, automated backups, point-in-time recovery, and access controls.
- Secrets are stored in the deployment provider’s secret manager, not in source control.
- OAuth tokens are not stored unless encryption/key management has been reviewed.
- HTTPS is required, secure cookies are enabled, and Sentry/logging are configured without collecting unnecessary personal data.
- Data export and account deletion are tested end-to-end.

## Launch Gate

- Counsel-approved Privacy Policy and Terms are linked in the app.
- Production data retention and deletion behavior is documented.
- Integration scopes match the minimum permissions needed.
- Admin and support processes exist for deletion/export/security requests.
