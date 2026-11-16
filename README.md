# Cyan Eclipse Basketseal

basket-arithmetic witness

Basketseal answers exactly one question about exactly one artifact:
does this basket's charged total equal the sum of its own sealed
components?

A basket is captured as presented at a first-party surface — the
checkout surface itself or the order confirmation — sealed at
intake, and recomputed from the sealed components alone under the
basket's own stated rounding discipline. The record names the
outcome in a closed grammar: the basket RECOMPUTES, or it
MISCOMPUTES and the record names the differing component class and
the amount of the difference, or it is UNWITNESSED because no
first-party capture record was present and no verdict is issued.

A RECOMPUTES verdict says the basket's arithmetic is internally
consistent under its stated discipline — nothing more. It makes no
statement about whether any price was right, competitive, or
correctly set, and a MISCOMPUTES verdict names an arithmetic
difference and its class; it is not a legal characterisation of
anyone's conduct, and no record this product issues decides that
anything is owed to anyone.

## Scope fence

Basketseal holds one artifact and one state per record. It never
compares a basket against a second artifact (a purchase order, a
mandate, a delivery record, a quote, or an earlier view of the same
basket), never evaluates a payment or a surcharge rule, and never
sits in a checkout path: it cannot block, hold, reprice, or alter
anything. Shapes that would bind a second state are refused at the
surface; they belong to sibling products, not to this one.

## Tools

| Tool | What it does |
| --- | --- |
| `basketseal_seal_basket` | Seal one basket as presented, with its capture record, and recompute its total. |
| `basketseal_get_record` | Read a full sealed record. |
| `basketseal_check` | Read only a record's verdict class and per-component diff summary. |
| `basketseal_recompute` | Recompute a verdict from an exported bundle, offline, with no service state. |
| `basketseal_export_record` | Export a record bundle plus the receipt chain head. |

Any other tool name — known sibling shapes included — receives the
same refusal. The surface is these five tools.

## The basket artifact

Amounts and quantities are decimal strings exactly as presented;
JSON numbers are refused, so no float normalization ever occurs.
Component lines keep presentation order: item lines (quantity, unit
price, line total), discount lines and fee lines as signed
components with their presented labels, the stated tax as its own
component (amount, plus rate and base where presented), and the
charged total. Line descriptions are hash-sealed by default; the
description class travels in clear, and the posture is named in
every record.

Canonicalization: the component list, in presentation order, with
the currency, the charged total, and the stated rounding, digested
SHA-256 at seal time. Recomputation is defined over the canonical
components alone.

## Rounding discipline

The basket's own stated rounding governs: per-line or per-total,
at its stated precision. Where a basket states no rounding, the
declared default tolerance is one half of the smallest presented
currency sub-unit, applied once at the total. The tolerance used
is named in every record. A difference inside tolerance is not a
miscompute; the boundary fixtures in the suite pin both sides of
the line.

Diff classes (closed set): line-sum · discount · fee · tax ·
rate-application · rounding-beyond-stated-precision. A
MISCOMPUTES verdict always states the diff amount per component.

## Supersession

A basket presented again under the same order reference supersedes
the earlier record: the earlier record's state becomes SUPERSEDED,
the new record names the version it supersedes, and verdicts are
always read against a named basket version.

## Receipt chain

Every seal and every verdict appends exactly one hash-chained
journal record (sequence, timestamp, kind, payload digest,
previous-hash link, record hash). The chain verifies end to end;
exports carry the chain head.

## Metering and licence

The charge event is the recomputation-with-verdict-record,
following the firm's PC-4 pattern (single / batch at threshold) as
a pattern fit only — no price is adopted for this product, and the
metering ledger records event class and count only, never basket
content. Intake sealing, offline recomputation from an exported
record, `basketseal_check`, and re-verification are never metered.

The metered service operates only under a valid licence on the
Cyan Eclipse License Server: with no licence or a revoked licence
the record still seals at intake and the unmetered tools serve,
and verdict issuance is refused with the reason named; under a
valid licence the verdict issues. Revocation is read live at
issuance time.

## Custody

A record holds only what the basket itself carries, plus the
recomputation: merchant identity as presented, the components,
the charged total, timestamps, the presenting-surface attestation,
the tolerance, the verdict, the record state. Payment credentials,
account identifiers beyond the order reference as presented, and
personal data beyond what the basket itself carries are refused at
intake and never stored. There is no second state to leak: the
sealed components govern every later recomputation.

## Offline verification

`verifier.py` re-derives the digest and the verdict from an
exported bundle alone — no service, no store, no shared code with
the core:

```
python3 verifier.py export.json
```

## Run

```
python3 server.py            # stdio
python3 server.py --http     # HTTP on 127.0.0.1:8798
```

Environment: `ECLIPSE_BASKETSEAL_STATE` (state root),
`ECLIPSE_BASKETSEAL_HTTP_TOKEN`, `ECLIPSE_BASKETSEAL_HTTP_HOST`,
`ECLIPSE_BASKETSEAL_HTTP_PORT`, `BASKETSEAL_LICENSE_SERVER_URL`,
`BASKETSEAL_LICENSE_TENANT`, `BASKETSEAL_LICENSE_ARTEFACT`,
`BASKETSEAL_PRODUCT_ID`.

## Tests and smoke

```
python3 -m unittest discover -s tests -v
python3 smoke.py
```

Status: v0.1.0, fixture scope. Nothing about this build is a
public claim; the name is provisional and internal pending the
trademark screen, and every surface carries the composite name
with the descriptor above.

License: MIT (see LICENSE).
