# What changed from the uploads

The current standalone landing page is authoritative. The `ClarityBS.html` and later `ClarityBS(1).html` copies inspected in the conversation were byte-identical, with SHA-256 `11edaef9a611a986020c70d686a8042965dddf708f68829a65c1fad299beaa2e`. This build preserves its Inter/Instrument Serif typography, ivory/green/gold palette, hero/phone preview, cards, pricing and FAQ layout. Forms necessarily collect the contact, consent and screening details required for the backend.

The supplied ZIP had a React prototype and a FastAPI backend using global dictionaries, permissive mock authentication, unprotected approval endpoints, hardcoded health statuses and placeholder workers. It did not provide working provider delivery or reliable deployment Dockerfiles. The standalone page had an unwired modal report path, an inline form reading hidden modal values, unsafe result HTML and checkout triggered by an unvalidated response.

This package replaces those demo runtime paths with a compact FastAPI/PostgreSQL service, a protected workspace and a private portal. The unused React mock UI is not included in the deployable runtime; no mock patients, doctor endorsements, AI-generated clinical recommendations or default users are shipped.

Every report explanation and personalised routine requires actual professional approval. Report entry is manual; uploaded PDFs, extracted values and lab reference ranges are not ingested. Input bounds are technical validation, not medical triage thresholds. Self-reported urgent concerns are referred, and all other personalised cases are reviewed before approval. The professional must interpret context and manage suitability within scope.

Service definitions and refund terms in the landing page are proposed operating choices: verify that you can honour them before launch. This package gives you implemented software and a launch checklist, not a claim that the business is already market-ready or medically/legal compliant.

## Landing update — 5 October 2026

Integrated the user-supplied `ClarityBS_public_launch_elegant (1).html` presentation: Bavitha Sri's supplied contact details, generic WhatsApp enquiry actions, refined footer, mobile spacing and illustrative feedback cards. Contact details are supplied by the owner; professional credentials still require independent verification before account approval rights are granted. The owner subsequently confirmed the feedback represents original experiences; the example labels were removed at their request.

The uploaded inline report handler read hidden modal fields and the modal report submission had no report branch. Replaced those scripts with the existing validated intake handlers and retained required contact/consent/screening fields. Enquiry CTAs open generic WhatsApp messages while intake is paused, and open the appropriate secure intake when intake is enabled. Health values are never added to the WhatsApp enquiry URL. Opening WhatsApp does not register an enquiry or send a message.

The 30-day card now advertises support from ₹999. Backend checkout remains ₹999 for the defined base service; any additional support/fee requires a separate agreement and is not automatically charged. Every personalised routine still requires practitioner approval. No report upload, instant explanation, automatic threshold-based escalation or live provider activation was added.

## Brand and feedback update — 5 October 2026

Display name expanded to Clarity Blood Sugar across the public page, app views, metadata and enquiry messages. Domain and backend routes remain claritybs.in. Feedback quotes, names and ratings are unchanged; the owner confirmed they reflect original experiences and requested removal of illustrative/sample labels. This does not add an independent verification claim.

Brand accent update: Blood Sugar uses the existing muted red #B5483B and italic Instrument Serif in brand displays. Body copy, domain, workflows and launch settings are unchanged.
