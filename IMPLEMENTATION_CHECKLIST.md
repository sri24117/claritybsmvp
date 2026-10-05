# ClarityBS MVP core implementation checklist

Prepared 1 October 2026. Source implementation is complete for a practitioner-reviewed pilot; the site is not deployed and live integrations are not yet verified.

## Built in this package

- [x] Preserve the current landing fonts, colours, cards, hero and visual style; remove Hyderabad targeting and unfinished developer instructions.
- [x] Correct inline and modal report submission; connect the general-diet form to the same backend.
- [x] Collect name/contact, adult age, service consent/version, screening and separate optional messaging consent.
- [x] Validate supported values/units on the server. Reject missing consent, children, unsupported units and unknown fields.
- [x] Persist intake in SQLAlchemy/PostgreSQL; use SQLite only for local testing.
- [x] Encrypt contact/health input, plan text, review notes, check-ins and access-token storage. No built-in key or fallback cipher.
- [x] Password-hashed staff accounts, expiring server-side sessions, secure production cookies, CSRF checks, same-origin mutations, rate limits and body limits.
- [x] Administrator assignment; practitioners can access only assigned cases. Qualification verification is an owner task; approval rights require a verified credential on the account.
- [x] Practitioner suitability review, referral gate, versioned drafts and approval of the exact saved plan.
- [x] Private patient portal with plan/reviewer/version, payment eligibility, check-ins and deletion.
- [x] Razorpay payment-link adapter with server-owned prices, durable attempts, raw-body signature checks, replay handling and payment reconciliation.
- [x] Refund event handling; a provider-confirmed full refund cancels paid access and pending notifications. Refund requests are initiated manually in Razorpay.
- [x] 24-hour payment-link expiry and queued cancellation after referral/deletion, with financial exception tasks for payments crossing cancellation.
- [x] Scheduled check-ins: days 3/7/14 for 14-day service, plus 21/30 for 30-day service.
- [x] Durable notification queue, worker heartbeat, bounded 429 retries, no blind resend after an uncertain acknowledgement.
- [x] Optional approved-template WhatsApp adapter, webhook signature verification, delivery/read status and STOP opt-out.
- [x] Manual fallback tasks with evidence of actual completion, patient-visible practitioner check-in feedback and lost-link recovery.
- [x] Case deletion, token revocation, child-record removal, automatic case expiry and encrypted backup/restore commands.
- [x] Safe text rendering, form busy states, request timeouts, modal focus handling, reduced motion, canonical/OG metadata, robots and sitemap.
- [x] Docker/Compose/Caddy deployment source and operational documentation.

## Before accepting real people

- [ ] Deploy the stack on your server and verify PostgreSQL, Docker build, Caddy certificate and worker health there. These infrastructure checks cannot be completed without server access.
- [ ] Point `claritybs.in` and `www.claritybs.in` to the server. Check any existing DNS records before changing them.
- [ ] Configure actual business name and a monitored support email. Replace any proposed policy terms you will not operate.
- [ ] Verify dietitian qualifications and scope independently; create individual accounts. Do not use synthetic test credentials as real qualifications.
- [ ] Agree realistic capacity and turnaround. Confirm who handles flagged cases, daily follow-up tasks, check-in reviews, cancellations and refunds.
- [ ] Review privacy/consent, processors, service limits, retention and refund policy for the actual business. Have appropriate India-specific professional/legal review.
- [ ] Store the encryption key separately from the server. Install the daily backup schedule, enforce seven-day expiry on every backup location and test restoration into an empty database.
- [ ] Run the test suite against a separate PostgreSQL test database on the server. Perform a basic independent security review before collecting health information.
- [ ] Pilot the full intake-to-approved-plan flow with synthetic details first, including deletion, wrong access links and worker interruption.
- [ ] Set `PUBLIC_INTAKE_ENABLED=true` only after the above checks; recreate API and worker containers to apply configuration.

## Before selling the paid plans

- [ ] Activate the merchant account. Configure Razorpay test credentials and a separate webhook secret.
- [ ] Subscribe to `payment_link.paid`, `payment.refunded` and `refund.processed` at `https://claritybs.in/api/webhooks/razorpay`.
- [ ] Test a successful and abandoned payment, an uncertain setup, duplicate events, amount mismatch, delayed webhook and full refund.
- [ ] Verify service pricing/tax treatment, cancellation policy and support capacity before switching to live credentials.
- [ ] Launch with a small, manageable cohort; review the queue daily. Automated operations do not replace practitioner sign-off.

## Optional WhatsApp launch

- [ ] Configure Meta business account, phone ID, app secret, verification token, supported Graph API version and server-side access token.
- [ ] Obtain approval for the exact template described in the deployment guide; it has one body parameter containing the public portal URL.
- [ ] Verify contact ownership and keep explicit opt-in evidence. Test STOP, delivery/read callbacks, invalid signatures, rate rejection and uncertain delivery.
- [ ] Switch `NOTIFICATION_MODE=whatsapp`; until then, handle visible staff tasks manually.

## Three-day launch scope

| Day | Deliverable                                                                           | Completion gate                                                                   |
| --- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| 1   | Host the closed preview, configure domain/HTTPS, create staff accounts                | Public intake and payments remain paused; synthetic browser flow works            |
| 2   | Verify professionals, scope, support policies, backup/restore; test provider accounts | Staff can process a case correctly; payment/refund tests pass                     |
| 3   | Enable a small reviewed pilot and monitor every case                                  | Someone owns review, follow-up and support; live payment verified before charging |

A three-day pilot is feasible only if the server, verified practitioner and merchant account are already available. Provider/business approvals can take longer.

## Phase 2–3, deliberately outside this core

- [ ] Multi-clinic organisations, tenant isolation, clinic billing and invitations.
- [ ] Secure report uploads, malware scanning, OCR and verification of extracted values.
- [ ] Scheduling/video consultations, patient identity OTP, secure staff MFA/SSO and richer access recovery.
- [ ] Consent-aware approved-content library and practitioner-reviewed drafting assistance; no autonomous diagnosis or medication changes.
- [ ] Clinic/EHR integration, multilingual support, reporting, invoices/tax handling and audited service limits.
- [ ] Monitoring/alert integration, key rotation, high-load/concurrency validation and independent penetration testing.

Use one shared backend now with separate public, patient and practitioner views. Add clinic tenants after the dietitian pilot demonstrates actual demand.
