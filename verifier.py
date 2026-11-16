#!/usr/bin/env python3
"""Cyan Eclipse Basketseal — standalone export verifier.

Independent recomputation (bench claim BK-B2): given ONLY an
exported record bundle, this program re-derives the canonical
digest and the verdict from the bundle's components, without the
service, its store, or its code. It shares no code with the core:
the arithmetic and canonicalization are re-implemented here so a
verdict agreement is evidence, not an echo.

Usage: python3 verifier.py <export.json>
Prints DIGEST OK/MISMATCH and VERDICT <class> MATCH/DIVERGENT.
Exit 0 iff digest ok and (no recorded verdict or verdicts match).
"""

import hashlib
import json
import sys
from decimal import Decimal, ROUND_HALF_UP

MINOR_UNITS = {"JPY": 0, "KRW": 0, "VND": 0, "ISK": 0,
               "BHD": 3, "KWD": 3, "OMR": 3}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def q(value, unit):
    return value.quantize(unit, rounding=ROUND_HALF_UP)


def recompute(form):
    rounding = form.get("rounding") or {}
    if rounding.get("precision"):
        unit = Decimal(rounding["precision"])
    else:
        unit = Decimal(1).scaleb(-MINOR_UNITS.get(form["currency"], 2))
    tolerance = unit / 2
    mode = rounding.get("mode") or "per-total"
    diffs = 0
    lines = Decimal(0)
    discounts = Decimal(0)
    fees = Decimal(0)
    tax = Decimal(0)
    for comp in form["components"]:
        kind = comp["kind"]
        if kind == "line":
            exact = Decimal(comp["quantity"]) * Decimal(comp["unit_price"])
            expected = q(exact, unit) if mode == "per-line" else exact
            check_against = expected if mode == "per-line" else q(exact, unit)
            if abs(Decimal(comp["line_total"]) - check_against) > tolerance:
                diffs += 1
            lines += expected
        elif kind in ("discount", "fee"):
            magnitude = abs(Decimal(comp["amount"]))
            used = magnitude
            if comp.get("rate") is not None and comp.get("base") is not None:
                expected = q(Decimal(comp["base"]) * Decimal(comp["rate"]),
                             unit)
                if abs(magnitude - expected) > tolerance:
                    diffs += 1
                used = expected
            elif comp.get("base") is not None:
                if magnitude - Decimal(comp["base"]) > tolerance:
                    diffs += 1
            if kind == "discount":
                discounts += used
            else:
                fees += used
        elif kind == "tax":
            amount = Decimal(comp["amount"])
            used = amount
            if comp.get("rate") is not None and comp.get("base") is not None:
                expected = q(Decimal(comp["base"]) * Decimal(comp["rate"]),
                             unit)
                if abs(amount - expected) > tolerance:
                    diffs += 1
                used = expected
            if comp.get("base") is not None:
                if abs(Decimal(comp["base"]) - (lines - discounts)) > tolerance:
                    diffs += 1
            tax = used
    total = lines - discounts + fees + tax
    if abs(Decimal(form["charged_total"]) - total) > tolerance:
        diffs += 1
    return "MISCOMPUTES" if diffs else "RECOMPUTES"


def main():
    if len(sys.argv) != 2:
        print("usage: verifier.py <export.json>")
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        export = json.load(fh)
    bundle = export.get("bundle", export)
    form = bundle["canonical"]
    digest = sha(canon(form))
    digest_ok = digest == bundle["canonical_digest"]
    print("DIGEST", "OK" if digest_ok else "MISMATCH")
    verdict = recompute(form)
    recorded = bundle.get("verdict")
    # Only an issued recomputation verdict can match or diverge;
    # UNWITNESSED and verdict-null (licence-refused) records carry
    # no recorded verdict and report UNRECORDED.
    match = (recorded == verdict) \
        if recorded in ("RECOMPUTES", "MISCOMPUTES") else None
    print("VERDICT", verdict,
          "MATCH" if match else ("DIVERGENT" if match is False
                                  else "UNRECORDED"))
    return 0 if digest_ok and match is not False else 1


if __name__ == "__main__":
    sys.exit(main())
