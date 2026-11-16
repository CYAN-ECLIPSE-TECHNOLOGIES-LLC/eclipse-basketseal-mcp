# Bench Request — Cyan Eclipse Basketseal v0.1.0 (initial build)

(INT — INTERNAL)

Filed: 2026-11-15 · Lane: basketseal-build-20261115 · Slate: ETO-99
(tkt-3e2544f5770d) · Loom: project 57, BKS-REQ-001..020 (req
2393–2412, CANDIDATE, not-run — ratification is the owner's act;
nothing in this filing baselines them).

Subject: Cyan Eclipse Basketseal v0.1.0, basket-arithmetic witness.
Spec of record: SPEC-BASKETSEAL.md (sha256
519cf815e7b7eafe1605cb762446bb34ba82a82a94c19b1bac9a211049c151ec).
Gate: argus-gate-basketseal-20261115.md, PASS-WITH-CONDITIONS,
ratified 2026-11-15; gate conditions BK-C1..C11 carried as
BKS-REQ-001..011; kill criteria K1..K5 mapped at BKS-REQ-002/003/
007/006/004. Build home: Shard E
/home/witness/app-family/cyan-eclipse-basketseal · Repo:
CYAN-ECLIPSE-TECHNOLOGIES-LLC/eclipse-basketseal-mcp (PRIVATE) ·
Head at filing: see the lane record STATE.md (the filing commit).

Scope label: fixture. No publication, listing, directory
submission, sale, or external pilot is requested or effected by
this filing; counsel questions BK-CQ-1..3 (Q44–Q46) remain filed
only, answers outstanding, and the gate §5 fences stand.

CONTRACT: Basketseal v0.1.0 initial build (fixture scope) — judge claims BK-B1..BK-B6 plus ADV-1 and ADV-2; a pass unlocks nothing external.

## Claim sheet

| Claim | Statement | Evidence offered (builder artefacts; re-derive, do not trust) | Verify by |
| --- | --- | --- | --- |
| BK-B1 | Recomputation correctness + rounding discipline: every witnessed fixture verdict matches an independent hand computation; every MISCOMPUTES names class + amount; per-line vs per-total and stated precision change verdicts exactly as the discipline requires. | fixtures/fx-clean, fx-line-miscompute, fx-tax-rate, fx-total-miscompute, fx-discount-over-base, fx-per-line-rounding, fx-per-total-rounding; tests RecomputationTests (10 tests). | Recompute the fixtures by hand / by the standalone verifier; probe tolerance boundaries with own baskets. |
| BK-B2 | Independent recomputation: verifier.py, sharing no code with the core, re-derives digest + verdict from an exported bundle alone. | verifier.py; test_b2_export_recompute_offline_and_verifier (incl. subprocess run, store bytes unchanged). | Export a record, run verifier.py, compare; repeat on a MISCOMPUTES record. |
| BK-B3 | Record pinning: recomputation runs over the sealed canonical components; substituted components fail the pinned digest; the receipt chain verifies end to end and detects tampering. | test_b3_substituted_components_fail_digest; test_journal_chain_verifies_and_detects_tamper; export carries chain head. | Tamper with a bundle and with a journal copy; observe refusal / chain failure. |
| BK-B4 | Separation: sibling shapes (PO/payment pair fixture; the 16-name denylist incl. payment-verdict, pair-diff, view-drift, surcharge, interception names) are refused; denylist refusals are byte-identical to unknown-name refusals. | fixtures/fx-sibling-po-pair.json; tests SeparationTests (4 tests); server.DENYLIST. | Drive the denylist and own sibling shapes at both transports; diff refusal bytes. |
| BK-B5 | Grammar closure: no output uses a verdict word outside {RECOMPUTES, MISCOMPUTES, UNWITNESSED}, a state outside {SEALED, SUPERSEDED}, or a diff class outside the six named classes; UNWITNESSED seals carry no recomputation and no verdict receipt. | tests GrammarTests + WitnessTests; basketseal.VERDICTS / RECORD_STATES / DIFF_CLASSES. | Census outputs across fixtures incl. unwitnessed captures. |
| BK-B6 | Custody: the store contains only the §2 field set; description text is hash-sealed (class in clear); excluded custody fields are refused at intake. | test_b6_store_census_and_custody; test_custody_field_refused_at_intake; FORBIDDEN_KEYS census. | Census a populated store; attempt custody-bearing baskets. |
| ADV-1 | Sibling-shape inputs are refused or seal UNWITNESSED; no payment verdict is mintable through any path (surface census = exactly five tools). | SeparationTests; TransportTests.test_stdio_dispatch_and_content_free; tool inventory in server.TOOLS. | Probe the surface for any sixth behaviour. |
| ADV-2 | Tolerance boundaries: a total off by exactly half the smallest sub-unit RECOMPUTES (zero wolf-cries); one milli-unit beyond MISCOMPUTES; the same components flip verdicts across stated disciplines. | fixtures/fx-subunit-edge, fx-subunit-over, fx-per-line-rounding, fx-per-total-rounding. | Re-derive boundaries at other currencies/precisions. |

Kill criteria, each with a named test: K1 receipt-locker —
test_k1_no_receipt_locker (every witnessed seal recomputes; a wrong
total can never return as a plain sealed record). K2 sibling
shapes — test_k2_denylist_refusal_byte_identical +
test_adv1_sibling_pair_fixture_refused. K3 legal conclusions —
test_k3_no_legal_conclusion_language (banned-phrase sweep over
outputs and surfaces; phrases assembled in parts in the test so
this suite is not itself a carrier). K4 checkout interception —
test_k4_tool_surface_is_exactly_five +
test_k4_sealing_never_mutates_the_basket. K5 evidence poisoning —
the K5 rounding set in RecomputationTests (per-line / per-total /
stated-precision class / sub-unit boundaries).

## Licence leg (BKS-REQ-018) — live fixture proof

Against the deployed License Server (Shard E, tenant cet):
product "basketseal" registered, tier "fixture" (feature
metered_recompute), fixture licence issued
(144797f7-4e68-4cd9-9dbd-8f2ef9efcf3a, artefact hash f2fa5d80…),
then, through the product's own LicenseServerGate: no licence →
refused · valid → served (service seal verdict RECOMPUTES, exactly
one single meter event) · revoked → refused in real time (record
still seals at intake, verdict issuance refused with reason, no
meter events, check serves). Fixture licence revoked at the end of
the proof. Receipt: lane evidence licence-proof-raw.json
(driver + raw output also on Shard E,
basketseal-licence-proof-20261115/). Server journal 360 → 365.
Known server defects F-A / E-36 were not touched; registration was
first-time.

## Metering (BKS-REQ-010/017)

Metering fixtures in MeteringLicenceTests: two witnessed singles →
two {single, 1} entries; UNWITNESSED seal, check, export and
offline recompute add none; a 100-basket batch → one {batch, 100}
entry. Ledger entries carry exactly {seq, ts, event_class, count}.
PC-4 figures are pattern constants only; no price is adopted.

## Coding Standard + QA-PATTERNS

Coding Standard checker (manifest manifests/basketseal.json in
coding-standard-checker-20261114): verdict PASS-WITH-UNCHECKED —
CM-1 PASS (five surfaces incl. live serverinfo) · CM-2 PASS ·
CM-3 PASS · CM-6 PASS (CLAIM-INVENTORY.json traces the README's
licence/posture sentences) · CM-7 / CM-8 NOT-APPLICABLE with
recorded reasons · CM-4 / CM-5 UNCHECKED-BY-MACHINE (no document
outputs; marking unset declared). Sealed report seal
2a9c284dca1c8f80cf494b1b3f0ee5da2d1d1ecfb50d1795fa28edc6cd711140,
verify: chain ok; report in lane evidence.

QA-PATTERNS conformance (builder-asserted; the bench adjudicates):

| Pattern | State | Note |
| --- | --- | --- |
| P1 content-free modes | CLEAR | _content_free refused pre-dispatch; one dispatch serves both transports, so no ingress lacks the close. |
| P2 disclosure matches build | CLEAR | README + tool descriptions name exactly the five implemented tools and the implemented behaviours; nothing is listed or published. |
| P3 save/close basics | CLEAR | Atomic tmp+replace state saves; fresh service instances reopen the same store across the suite. |
| P4 AI-applied content | N-A | The product applies no AI-generated content to anything. |
| P5 version discipline | CLEAR | VERSION = pyproject = server.json = TOOL_VERSION (lockstep test; CM-1 PASS incl. live initialize). |
| P6 integrity warnings | PARTIAL | Digest substitution is refused plainly and first (EXPORT_DIGEST_MISMATCH); exports carry the chain head and verify_chain exists, but reads do not re-verify the whole chain per call. |
| P7 erasure-class ops | CLEAR | No erasure-class operation exists on the surface (five-tool census); records are evidence by design. |
| P8 preview = apply | N-A | No preview/apply split exists in the product. |
| P9 Sealgate | N-A | No Mac artefact exists. |
| P10 Launchgate | N-A | No Windows artefact is published. |
| P11 native deps | CLEAR | Pure Python stdlib; no native dependency to omit. |
| P12 runtime-state paths | PARTIAL | State root: ECLIPSE_BASKETSEAL_STATE override, else module-dir data/ when writable, else per-user ~/.local/state/eclipse-basketseal. The unwritable-install-dir case is implemented but not exercised by a test in this build. |
| P13 claim-surface binding | CLEAR | CM-6 PASS with the in-tree claim inventory; README claims are the build's behaviours. |
| P14 refusal-path quality | HIT | MCP refusals lead with ALL_CAPS reason tokens (estate MCP convention), ahead of the plain-language sentence. |
| P15 key custody + journal | HIT | No key custody in-product (the licence artefact arrives by environment and is never persisted by the product); the receipt journal is disclosed in the README and exports carry its head, but journal custody on a hosted deployment is an operator matter, not a product control. |

## Branding + icon

Full branding set in branding/ (icon, splash lockup, tokens,
inventory). Icongate on branding/icon.svg: PASS (48px legible —
cap 5.6px, contrast 5.3, separability 0.80 · 32px legible — cap
3.8px, contrast 4.7, separability 0.90); contact sheet in lane
evidence. Owner approval of the icon is still owed before any
ship claim; none is made.

## Suite + smoke (builder-run, Shard E build home)

python3 -m unittest discover -s tests → 32 tests, OK.
python3 smoke.py → SMOKE PASS (12/12) — service seals across all
three verdict classes, chain verify, offline recompute match,
metering, stdio initialize/list/ping, HTTP health/bearer/401.

## What is NOT claimed

No surface beyond protocol scope is claimed (no GUI exists; the
HTTP /health identity face and MCP initialize are the identity
surfaces, exercised by smoke). No price, no listing, no pilot.
The build pins named in basketseal.py's module docstring
(decimal-strings-only intake; discount/fee sign rule; most-derived
recomputation; diff-class assignment incl. the tax-base and
rounding-beyond-stated-precision rules) are build decisions
offered for adjudication, not spec text.
