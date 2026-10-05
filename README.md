# ClarityBS MVP — reviewed nutrition support

This project turns the uploaded landing page into a single-practice pilot: public intake, a private patient portal, a protected practitioner workspace, PostgreSQL persistence, payment adapters and scheduled follow-ups. Personalised content is written and approved by a qualified practitioner. No patient-facing AI advice is generated.

Read **IMPLEMENTATION_CHECKLIST.md** first. For a clean VPS use **docs/DEPLOYMENT.md**; for a VPS already running Coolify use **docs/COOLIFY_DEPLOYMENT.md** and **compose.coolify.yaml**. The source is implemented; deployment, provider credentials and service operations still require setup. Intake and payments are paused by default.

## Pages

| URL       | Purpose                                                                       |
| --------- | ----------------------------------------------------------------------------- |
| `/`       | Existing landing visual style with corrected intake forms                     |
| `/portal` | Private access link, status, approved plan, payment, check-ins, deletion      |
| `/app`    | Staff sign-in, assignment, verification, review, plan approval and follow-ups |
| `/docs`   | API documentation in development only                                         |

## Local preview

Python 3.12 is required. Commands run from this folder:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install --require-hashes -r requirements.txt
python scripts/bootstrap_env.py --local
python scripts/run_local.py
```

Open `http://localhost:8000`. The preview initially pauses intake. For synthetic test submissions, set `BUSINESS_NAME`, `SUPPORT_EMAIL`, and `PUBLIC_INTAKE_ENABLED=true` in the local `.env`. Create your own account; no user/password is shipped:

```sh
python scripts/run_local.py create-user --email your-address@example.com --name "Your name" --role admin
```

An operations account cannot review or approve plans. After independently verifying a real practitioner's qualification, create their account with `--credential "Verified qualification and registration, if applicable" --verified-credential`. An admin may also be a qualified practitioner. Run the worker in a second terminal using the same environment: `python scripts/run_local.py worker`.

## Core workflow

1. Adult gives service consent, enters report values or general-diet details, and separately chooses optional WhatsApp reminders.
2. Backend records a persistent intake and returns a private bearer access link. Keep it private. It is sent as an Authorization header, never a server query string.
3. Administrator assigns the case. Staff verify contact ownership via an inbound business message or callback and record evidence.
4. Verified practitioner reviews suitability. Urgent-screen cases must be referred; numeric inputs do not receive automated diagnostic labels.
5. Practitioner writes a draft and approves its exact saved version. Edits withdraw approval until reviewed again.
6. Free report explanations are published after approval. Paid routines require both approval and provider-confirmed payment.
7. Worker records notification tasks and due check-ins. Manual mode creates staff tasks. WhatsApp mode requires configured credentials, verified contact, opt-in and an approved template.
8. Patient submits due check-ins; practitioner reviews them. Patient can withdraw optional messaging consent or delete the case.

## Boundaries

This is a single-practice pilot, not multi-clinic SaaS. It has no report uploads/OCR, autonomous medical advice, appointment/video infrastructure, mobile app, invoices/tax engine, refund initiation API, email delivery or automatic phone OTP. Contact verification, clinical decisions, plan writing, check-in review, support and refund initiation remain human tasks. Provider adapters are tested with synthetic responses, not live accounts.

Current policies in the landing information dialogs are a proposed operating policy: the owner must review the service scope, retention, processors, refund terms and support details before enabling public intake. This package is not a compliance certification or an independent security audit.

## Tests

```sh
pip install --require-hashes -r requirements-dev.txt
sh scripts/test.sh
```

Tests use a disposable database and synthetic details. They do not contact payment/messaging providers. Node 20+ is required only for frontend checks; the production site has no Node build dependency.

For optional real-browser validation, install test-only `playwright`, `@sparticuz/chromium` and `tar-fs` on a supported Linux/Node 24 environment, then run `node tests/browser_test.cjs`. This starts and stops a disposable local server with synthetic test accounts and writes screenshots to `test-results/`. Use `CLARITY_TEST_PYTHON` to select the Python environment. No browser-test account is installed in production.

## Source layout

`app/` contains configuration, SQLAlchemy tables, validation, authentication, API handlers, providers, worker and operations CLI. `web/` contains the preserved landing page and new workspace/portal. `scripts/` contains setup, local launcher, backup and tests. `compose.yaml` runs PostgreSQL, API, worker and Caddy on a clean host. `compose.coolify.yaml` omits Caddy and host port bindings so Coolify can route the site alongside existing domains. There is no Redis dependency.

## Integration references

- [Razorpay payment links](https://razorpay.com/docs/api/payments/payment-links/create-standard/)
- [Razorpay webhook validation](https://razorpay.com/docs/webhooks/validate-test/)
- [Razorpay payment-link events](https://razorpay.com/docs/webhooks/payment-links/)
- [Meta webhook signature and verification](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/)

Versions are pinned in `requirements.in` and a hash-locked `requirements.txt`. Keep dependencies and container images patched, and rerun checks when upgrading.
