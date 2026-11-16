# Bench Request DELTA — Cyan Eclipse Basketseal v0.1.0 (cure delta for VERDICT-20261115)

(INT — INTERNAL)

Filed: 2026-11-15 · Lane: basketseal-build-20261115 (cure lane +
finishing pass) · Slate: ETO-99 (tkt-3e2544f5770d) · Loom: project
57, BKS-REQ-001..020 (req 2393–2412, CANDIDATE, not-run —
unchanged by this filing).

Subject: cure delta against Verity's verdict on the initial
build — VERDICT-20261115.md (this tree; sha256
67629f7f9695d6c33f96fdfae932fb61b8c1c9235095014ab0a686692669774e),
whose contract line reads FAIL — on BK-B3 / finding F-1 (HIGH),
with findings F-2
(MED), F-3 (MED), F-4 (LOW) recorded. Spec of record:
SPEC-BASKETSEAL.md (sha256
519cf815e7b7eafe1605cb762446bb34ba82a82a94c19b1bac9a211049c151ec
— unchanged). Repo:
CYAN-ECLIPSE-TECHNOLOGIES-LLC/eclipse-basketseal-mcp (PRIVATE) ·
pre-cure head c81de1fe79477537d53da149b79fa1f0f5a7eebc · head at
this filing e4d68ff854a7c8d846f5eb45fe502801123fe6e7 (four cure
commits, one per finding, each carrying its regression tests;
this filing rides as a further commit on top). Build home:
Shard E /home/witness/app-family/cyan-eclipse-basketseal · VM
mirror byte-identical (all 29 tracked files hash-verified).

Scope label: fixture. No publication, listing, directory
submission, sale, or external pilot is requested or effected by
this filing; counsel questions BK-CQ-1..3 (Q44–Q46) remain filed
only, and the gate §5 fences stand.

CONTRACT: Basketseal v0.1.0 cure delta (fixture scope) — judge only the four cured findings F-1 (re-filed as BK-B3), F-2, F-3, F-4 against VERDICT-20261115; claims BK-B1, BK-B2 (except the F-2 edge), BK-B4, BK-B6, ADV-1, ADV-2 and kill criteria K1–K5 stand as judged PASS and are not re-filed; a pass unlocks nothing external.

## Claim sheet (cures only)

| Claim | Cure | Evidence offered (builder artefacts; re-derive, do not trust) | Verify by |
| --- | --- | --- | --- |
| BK-B3 (F-1, HIGH) — record identity | record_id now derives from the canonical digest PLUS the seal's identity material (merchant · order_ref · journal seal sequence): record_id = bks-<sha256(canonical(identity))[:12]>-v<version>. The canonical form itself is unchanged — recomputation still runs over the canonical components alone. Supersession stays keyed to the order reference and is now deterministic across collisions (latest SEALED version + 1; all prior SEALED versions of that order_ref supersede). Commit c321dd78e8bbabbf33ad8aab7556cfc6429ef796. | tests/test_basketseal.py: test_f1_two_distinct_baskets_same_arithmetic_coexist · test_f1_post_collision_supersession (both fail pre-cure, pass post-cure). Reproduction: lane cure-20261115/repro_bk_b3.py with pre-cure output (ids identical, 1 record, silent loss) and post-cure output (distinct ids, 2 records coexist, ORD-100 re-seal → v2 supersedes v1). | Re-run the verdict's own probes: two merchants / distinct orders / identical arithmetic; same-merchant distinct orders then a re-seal; the 100-identical-basket batch (store retention vs the {batch, 100} meter entry). |
| BK-B5/BK-B2 edge (F-2, MED) — UNWITNESSED export path | recompute_export and verifier.py now take the no-recorded-verdict path for any record whose verdict is not an issued recomputation verdict: UNWITNESSED and verdict-null (licence-refused) both report matches_recorded=None / "UNRECORDED" instead of DIVERGENT / exit-1 divergence. Commit 1fbb86436a91fbb0fb54982e2f5b9a47a7dd7b7e. | test_f2_unwitnessed_export_reports_no_recorded_verdict (fails pre-cure, passes post-cure). | Export an UNWITNESSED record; run recompute_export and verifier.py on the bundle; repeat on a licence-refused record and on RECOMPUTES / MISCOMPUTES records (match/diverge behaviour unchanged). |
| QA P6 (F-3, MED) — reads re-verify integrity | Every read path (get_record · check · export_record, all via _record) now re-verifies the stored record before serving: the record body (state field excluded, as at seal time) must hash to its record_hash and its canonical form must digest to its pinned canonical_digest; a tampered state file is refused with RECORD_INTEGRITY_MISMATCH instead of serving altered components under the original verdict. Commit a7b2f622e890006706dda8e5361a7508f8c174a8. | test_f3_tampered_stored_record_refused_on_read (honest record serves after reload; the same record with a state-file component edit is refused on all three read paths; fails pre-cure, passes post-cure). | Edit a stored component in the state file, reload, read on each path; confirm refusal; confirm an untouched store (incl. a SUPERSEDED record) still serves. |
| BK-B5 surface (F-4, LOW) — capture shape + named verdict-null | (a) Capture validation now scans custody material first: a custody key in a capture takes the custody refusal (BASKET_CUSTODY_REFUSED, as in a basket); any other out-of-grammar capture field makes the capture invalid as presented and the basket seals UNWITNESSED, like every other invalid capture, instead of aborting the seal with BASKET_FIELD_UNKNOWN and no record. (b) check now carries verdict_issuance — the issuance-refusal text, or null when a verdict was issued or the record is UNWITNESSED — so the licence-refused verdict-null is a named state; no new verdict word is introduced and the grammar stays closed. Commit e4d68ff854a7c8d846f5eb45fe502801123fe6e7. | test_f4_capture_extra_key_seals_unwitnessed · test_f4_capture_custody_key_refused_as_custody · test_f4_check_names_unissued_verdict (all fail pre-cure, pass post-cure); test_check_is_summary_only updated to the cured check contract. | Seal with captures carrying (i) an extra benign key, (ii) a custody key; check a licence-refused record and confirm verdict_issuance names the refusal while verdict stays null and no fourth verdict word appears anywhere. |

## Cure pins offered for bench adjudication

Builder decisions, not spec text — they stand or fall at this
bench:

- Record-identity derivation: identity material (merchant ·
  order_ref · journal seal sequence) enters the record_id
  derivation only; the canonical form and the recomputation
  definition (BKS-REQ-013) are untouched. The derivation is
  recorded as a discipline pin in basketseal.py's docstring.
- F-3 read refusal: RECORD_INTEGRITY_MISMATCH is a new refusal
  token on the read paths; the record state field stays excluded
  from the record hash, as at seal time, so supersession is
  unaffected. Per-read verification covers the record's own
  sealed hashes; it is not a whole-chain re-verification per
  call (verify_chain remains the chain instrument).
- F-4 check surface: verdict_issuance is an added field on the
  check output naming why verdict is null; the §4.1 check
  contract otherwise stands (verdict class + diff summary only,
  never basket content).

## Suite + smoke + checker (builder-run on the cured tree)

python3 -m unittest discover -s tests → 39 tests, OK (32 as
judged + 7 cure regression tests). python3 smoke.py → SMOKE PASS
(12/12). Run on the VM mirror; mirror hash-verified
byte-identical to the Shard E build home at head e4d68ff.

Coding Standard checker re-run on the cured tree: verdict
PASS-WITH-UNCHECKED — CM-1 / CM-2 / CM-3 / CM-6 PASS · CM-7 /
CM-8 NOT-APPLICABLE · CM-4 / CM-5 UNCHECKED-BY-MACHINE (same
per-check statuses as the judged run). Report:
evidence/coding-standard-report-cure.json (generated
2026-11-16T05:45:51Z; artefact hashes updated to the cured files
— basketseal.py f93fb40b50878fb5…, verifier.py a12258fe53a3bef…;
report seal 2a9c284dca1c8f80cf494b1b3f0ee5da2d1d1ecfb50d1795fa28edc6cd711140,
unchanged, as the seal binds the process-clause record).

## What is NOT claimed

No re-judgment of the PASS claims is requested. No price, no
listing, no pilot, no ship claim; the icon's owner approval
(GAP-BKS-2) is still owed and untouched by this delta. This lane
does not self-certify: the cures above are builder evidence for
Verity's delta sitting.
