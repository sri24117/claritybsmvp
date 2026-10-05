# Verification — 1 October 2026

The final source was verified after a clean, hash-locked installation into a new Python 3.12 environment.

| Check | Result |
|---|---|
| Backend integration suite | 37 passed |
| Python source checks | Ruff undefined/unused-name checks passed |
| Frontend JavaScript | Syntax and contract checks passed |
| Desktop browser workflow | Report intake → private portal → staff login → contact verification → suitability review → versioned plan → approval → patient publication passed |
| Mobile browser workflow | General-diet intake, focus restore and no horizontal overflow passed at 390px |
| Session/device clearing | Staff sign-out and patient device clearing removed rendered private content in browser checks |
| Dependency installation | Fresh install of hash-locked development dependencies succeeded |
| Compose structure | YAML parsed; only Caddy publishes ports; API filesystem is read-only |

Backend coverage includes invalid login, staff authentication, CSRF/origin checks, case assignment/qualification scope, consent/adult/unit validation, idempotency, urgent referral, approval/version gates, private-token scope, provider signatures/replayed/mismatched events, uncertain payment attempts, full refunds and late paid events, check-in timing/product limits, patient-visible practitioner feedback, notification status ordering, STOP opt-out, bounded rate retries, uncertain acknowledgement handling, deletion/child cleanup/tombstones, queued payment cancellation, retention, encrypted backup/restore and lost-link recovery.

Provider tests use synthetic responses and signatures. Browser tests use a disposable local server, database and clearly synthetic practitioner account. No real patient information or provider account was used.

The suite produces one deprecation warning from Starlette's current TestClient/httpx compatibility layer. Tests pass; no production failure was observed from that warning. Review the test client dependency when upgrading the framework.

## Not verified here

Docker image build/runtime, actual PostgreSQL behaviour/concurrency, VPS networking, DNS, HTTPS certificates, live Razorpay creation/payment/refund, approved Meta templates/delivery, backup scheduling/off-server expiry, service capacity, professional qualifications and business-specific policy/legal review need verification in the deployment environment. This is not a penetration test or clinical validation.

The release excludes local databases, environment secrets, browser binaries, test screenshots and dependency directories. Tests and the optional browser-test source are included so the checks can be rerun.

## UI update — 5 October 2026

After merging the new presentation, frontend contract checks and the existing real-browser workflow passed again: report intake, portal, practitioner review/approval/publication, mobile general-diet intake, focus restoration, device clearing and sign-out. Backend code and schema did not change; the earlier 37 backend test results remain the recorded backend verification.

The closed hosted-preview source also passed browser checks at 1440, 768, 390 and 320 pixels: no content overflow, disabled online intake, modal focus/restore, privacy and portal notices, and the generic WhatsApp enquiry destination. WhatsApp navigation was intercepted offline; no external message was sent.
