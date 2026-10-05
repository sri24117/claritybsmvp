# Deploy Clarity Blood Sugar with Coolify

This is the recommended deployment for a VPS that already runs Coolify and
hosts another website such as `jyutrix.io`. The Coolify proxy keeps both sites
separate. Do not publish ports 80 or 443 from this application.

## Before you deploy

- Keep `jyutrix.io` and its DNS records unchanged.
- Put this project in a private Git repository.
- Do not commit `.env`, database exports, access links, or encryption keys.
- Have a monitored support email ready.
- Keep public intake, payments, and automatic notifications disabled for the
  first controlled pilot.

## 1. Generate the production environment block

From the project folder, run:

```bash
python scripts/generate_coolify_env.py --support-email support@claritybs.in
```

Copy the complete output into a password manager and into the Coolify
Environment Variables screen. Replace the example support address if it is not
monitored.

Important: never regenerate `DATA_ENCRYPTION_KEY` after real participant data
has been created. Losing or changing it can make encrypted data unreadable.

## 2. Create the Coolify resource

1. Open the existing Coolify dashboard.
2. Create a new project named `Clarity Blood Sugar` and choose the Production
   environment.
3. Add a resource from the private Git repository.
4. Select Docker Compose.
5. Set the base directory to `/` and the compose file to
   `/compose.coolify.yaml`.
6. Leave **Raw Compose Deployment** off so Coolify can add its managed proxy
   labels and resource network.
7. Paste the generated environment variables. Keep build-time variables off;
   these values are runtime secrets.
8. Save, then deploy.

The Compose file contains four services: `db`, a one-time `migrate` job, `api`,
and `worker`. It contains no Caddy container and no host port bindings, so it
will not conflict with the existing sites on the VPS.

## 3. Attach the domain

In the `api` service, set the domain to:

```text
https://claritybs.in:8000
```

The `:8000` suffix tells Coolify which internal container port receives web
traffic. Visitors still use the normal URL `https://claritybs.in`.

If you want `www`, add `https://www.claritybs.in:8000` and configure it to
redirect to the root domain.

## 4. Point DNS to the Coolify VPS

At the DNS provider for `claritybs.in`:

- Set the root `A` record (`@`) to the VPS IPv4 address.
- Set `www` as a CNAME to `claritybs.in`, or as an A record to the same IPv4.
- Remove only old web-hosting A/AAAA records that conflict with these names.
- Preserve MX, TXT, DKIM, SPF, DMARC, and other email-verification records.
- Do not change any `jyutrix.io` records.

Wait for DNS propagation and for Coolify to issue the TLS certificate.

## 5. Verify the deployment

Confirm these URLs load over HTTPS:

- `https://claritybs.in/`
- `https://claritybs.in/health/live`
- `https://claritybs.in/app`
- `https://claritybs.in/portal`

In Coolify, confirm `db`, `api`, and `worker` are healthy. The `migrate` service
is expected to finish successfully and exit.

## 6. Create the first staff account

Open a terminal for the `api` service in Coolify and run:

```bash
python -m app.cli create-user --role admin --email you@example.com --name "Your name"
```

Use a real team email and store the generated credentials securely. Create
dietitian access only for people who are actively working in the pilot.

## 7. Controlled launch settings

Start with these values:

```text
PUBLIC_INTAKE_ENABLED=false
PAYMENT_MODE=disabled
NOTIFICATION_MODE=manual
```

This keeps the website public while participant intake remains invite-only.
Enable intake only after consent text, privacy policy, practitioner workflow,
support response times, and backup recovery have been reviewed.

## Rollback

If the new deployment has a problem, restore the old `claritybs.in` web DNS
record while you investigate. This does not affect `jyutrix.io`. Do not delete
the PostgreSQL volume during a rollback.
