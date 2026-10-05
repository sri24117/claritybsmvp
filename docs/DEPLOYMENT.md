# Deployment and operating guide

## Host on the VPS

This is a self-hostable Docker project for a Linux VPS, including a KVM4-style server. Antigravity may be used to edit the source; it is not a required runtime. The package has not been installed on your server.

### Recommended first deployment on a clean Ubuntu VPS

Upload the complete ZIP and `scripts/deploy_ubuntu_vps.sh` to the server. Run the script with the real monitored support address:

```sh
sudo bash deploy_ubuntu_vps.sh /tmp/ClarityBS-MVP.zip \
  "Clarity Blood Sugar" support@claritybs.in claritybs.in
```

The script installs Docker from Docker's official Ubuntu repository when needed, refuses to overwrite an existing `/srv/claritybs-mvp`, refuses to take ports 80/443 from another proxy, generates secrets, deploys the stack, checks internal liveness and installs the daily encrypted local-backup schedule. Intake and payments remain paused. It does not change DNS, create real users, enable providers or copy backups off the server.

This compose file includes its own Caddy proxy. Do not use the script on a server that already runs Coolify, because Coolify's proxy also owns ports 80/443. A Coolify deployment must omit the `caddy` service/host port mappings and route the domain to the API container's internal port 8000.

Keep the old website available while preparing the VPS. After internal health passes, change only the root and `www` website DNS records to the VPS. Preserve MX/TXT records used for email. Verify HTTPS and the closed workflow, then remove the old website if desired.

Install Docker Engine and the Compose plugin using the vendor instructions for your server's Linux distribution. Use a non-root SSH account with the minimum required privileges. Allow SSH and ports 80/443; do not expose PostgreSQL or the API port publicly. Only Caddy publishes ports in this Compose stack.

Upload and extract `claritybs-mvp`, then run from its root:

```sh
python3 scripts/bootstrap_env.py
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

The generated `.env` is private and contains unique database/encryption secrets. Do not commit or send it in chat. Save the encryption key securely off-server. Do not replace it on a running database; existing ciphertext depends on it.

Configure DNS A records for the root and `www` to the actual VPS IPv4 address. Add AAAA only if IPv6 is correctly configured. Caddy obtains TLS for the configured `DOMAIN` after DNS and ports work. Inspect current records before editing. A single origin serves `/`, `/api`, `/portal` and `/app`; no wildcard CORS is enabled.

Create accounts interactively:

```sh
docker compose exec api python -m app.cli create-user --email your-real-email@example.com --name "Owner name" --role admin
docker compose exec api python -m app.cli create-user --email dietitian-real-email@example.com --name "Dietitian name" --role practitioner --credential "Independently verified qualification" --verified-credential
```

Replace the example addresses and names. Passwords are entered privately and must be 12–128 characters. Admins without a credential perform operations but cannot approve clinical content. Assign each intake from the admin workspace. A practitioner sees only assigned cases.

## Start closed, then enable intake

Set actual `BUSINESS_NAME` and `SUPPORT_EMAIL`. Review the proposed privacy/service/refund text in `web/assets/landing.js` against your actual operation. Confirm professional scope, capacity, retention and processors. Never enable intake just because the landing page renders.

After the checklist is complete, set `PUBLIC_INTAKE_ENABLED=true` and apply configuration:

```sh
docker compose up -d --force-recreate api worker
```

Check `/health/live`, then sign in and inspect the workspace health line. The database check actually queries SQL; worker heartbeat becomes stale after three minutes without a cycle. Set an external uptime monitor for liveness and arrange a staff check of worker/queue status. Default notification mode is manual, and payment mode is disabled.

## Razorpay setup

Use test mode first. Set `PAYMENT_MODE=razorpay`, key ID, key secret and a separate webhook secret. Subscribe to `payment_link.paid`, `payment.refunded` and `refund.processed` at `/api/webhooks/razorpay`. Then recreate API and worker.

The server sets prices: ₹299 and ₹999, in paise. Checkout requires contact verification, eligibility and a current approved plan. A redirect back from the provider never marks a payment paid. Signed provider events or authenticated provider reconciliation confirm payment. Full refunds cancel paid access; partial refund totals are recorded without automatically withdrawing all service. Initiate refunds in the provider dashboard and resolve the service arrangements with the patient.

If payment-link creation times out, the attempt becomes `uncertain`, preventing a new potentially duplicate link. Find its `reference_id` in the provider dashboard. Compare amount and currency, then recover it using:

```sh
docker compose exec api python -m app.cli recover-payment-link --attempt-id REAL_ATTEMPT_UUID --provider-id plink_REAL_ID
```

If the provider created no link, investigate with provider support before changing stored attempt state; no automated reset is shipped. Do not manually set a case `paid` to bypass verification. Dashboard reconciliation fetches registered link/payment state; a later signed paid event also fills the payment ID needed for refund matching.

Payment links expire after 24 hours. Deleting an unpaid case or referring it queues cancellation of any registered open link; the worker checks this with the provider. Cancellation and a payment can cross in flight, so inspect the workspace's Payment actions count and run `docker compose exec api python -m app.cli list-open-payments`. This list contains financial IDs/status only, without health details. `cancel_requested=1` means cancellation pending; `2` means the provider reported paid during cancellation and support must resolve the service/refund. An uncertain creation with no registered provider ID needs CLI recovery before its link can be cancelled. Deletion itself does not automatically initiate a refund.

## WhatsApp setup

Keep `NOTIFICATION_MODE=manual` until Meta credentials and approved templates are available. Configure all WhatsApp fields in `.env`, using a currently supported Graph API version for your app. Set webhook GET verification and POST callbacks to `/api/webhooks/whatsapp`; subscribe to messages/status events.

Create an approved utility/service template in your chosen language with one body parameter. Proposed text (review against Meta's approval requirements):

> Your ClarityBS service has an update. Open your private portal using your saved access link. Portal: {{1}}. This inbox is not an emergency service. Reply STOP to stop reminders.

The server passes the public portal URL as `{{1}}`, never report values, plan text or private access tokens. Test with a consenting test contact. Staff must verify the number's ownership and record evidence. The patient separately opts in. A STOP/UNSUBSCRIBE message from a verified contact turns off subsequent automatic reminders.

Accepted, sent, delivered and read are distinct states. A 429 rejection is retried with backoff up to five attempts. Timeout, server uncertainty or an interrupted worker becomes `uncertain`; inspect provider state before a human action. Staff can record actual manual task completion with a note. Future reminders schedule from first plan activation, not from intake or checkout, and a plan revision does not restart the service period.

## Backup, deletion and recovery

Run `sh scripts/backup.sh` from the project root. It exports a consistent PostgreSQL snapshot and encrypts it with the application key; no plaintext health export is saved. It omits login sessions, heartbeat and rate limits. For this small pilot it reads the snapshot into memory; adopt a streaming/database-native backup system before the dataset becomes large.

Install a daily host cron job using your actual absolute project directory:

```cron
0 2 * * * cd /srv/claritybs-mvp && sh scripts/backup.sh >> /var/log/claritybs-backup.log 2>&1
```

Store an encrypted off-server copy and the encryption key separately. Enforce the same seven-day expiry on off-server copies. The deletion notice's seven-day backup statement depends on this scheduled policy; do not publish it if you do not operate that policy.

Restore into a new empty database, first running schema initialisation. Example after configuring a separate restore deployment:

```sh
docker compose run --rm --no-deps -v /absolute/backup-directory:/backups:ro api python -m app.cli restore --file /backups/claritybs-TIMESTAMP.enc
```

Use the original data key. Verify recovered records and token scope before routing traffic. Replay any deletion/cancellation requests made after the backup timestamp before enabling access; restoration can otherwise resurrect old data. Keep a separate operations record of those requests, with case IDs and timestamps only. Never test restore over production; the CLI refuses a non-empty database.

Case deletion removes active health/contact content, plans, check-ins, queued notifications and access. Financial order IDs/amounts remain separately without a case relationship; pseudonymous audit events remain for up to one year. Tombstones keep deleted intake keys from being recreated by a stale retry for the retention period. Provider-held information follows provider policies. An already in-flight generic notification cannot be recalled after deletion.

## Accounts and updates

```sh
docker compose exec api python -m app.cli reset-password --email REAL_EMAIL
docker compose exec api python -m app.cli disable-user --email REAL_EMAIL
```

Both revoke existing sessions. Recovery of a patient's lost link is available in the workspace after verified contact; staff must verify identity again and document it. Replacing a link invalidates the old one. Do not share links through public channels.

Back up before an upgrade. This initial release has schema version 1 and initialisation via SQLAlchemy metadata. Future schema changes require explicit versioned migrations; `create_all` is not a migration engine. Do not change columns in-place and assume init-db will migrate them. The database and encryption key are external to the application image.

## Server verification still required

Docker, actual PostgreSQL, DNS, HTTPS, live payment/messaging and load testing require your server/accounts. Run tests against an isolated PostgreSQL database ending in `_test` by setting `TEST_POSTGRES_URL` before pytest. The test suite drops/recreates its tables: never provide a production database.

This is a single-practice MVP. Plan publication is in the private portal; WhatsApp only notifies. Clinical review, qualification verification, identity callbacks, support, refunds and promised progress reviews remain staffed tasks. Add MFA/SSO, tenant isolation, monitoring alerts, uploads/OCR, invoices and key rotation in later phases.
