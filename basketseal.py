"""Cyan Eclipse Basketseal — basket-arithmetic witness (core).

Answers exactly one question about exactly one artifact: does this
basket's charged total equal the sum of its own sealed components?
The basket is captured as presented at a first-party surface (checkout
surface or order confirmation), canonicalized and hash-sealed at
intake, and the total is recomputed from the sealed components alone
under the basket's own stated rounding discipline. The verdict names
the recomputation outcome and, on a miscompute, the class and amount
of the difference per component.

Basketseal never compares two artifacts, never sees a payment, never
touches a checkout, and never issues a legal conclusion. Verdict
grammar is closed: RECOMPUTES / MISCOMPUTES / UNWITNESSED. Record
states are closed: SEALED / SUPERSEDED.

Discipline pins (build decisions, named for the bench):
- Money and quantities enter as decimal strings exactly as presented;
  JSON numbers are refused (no float normalization, ever).
- A discount component always reduces the total and a fee component
  always adds to it; the canonical signed amount is derived from the
  presented amount's magnitude under that rule.
- Recomputation builds the total from the most-derived values:
  expected line totals (quantity x unit price, disciplined), and
  expected amounts for any component presenting rate + base; all
  other components enter as presented. Every substitution is named
  in the diff list.
- Tolerance: half the basket's stated rounding precision unit where
  stated; otherwise half the smallest presented currency sub-unit.
  The tolerance used is named in every verdict record.
- Record identity: a record_id derives from the canonical digest
  plus the seal's identity material (merchant · order reference ·
  journal seal sequence), so distinct baskets always coexist in
  the store; supersession stays keyed to the order reference.
"""

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TOOL_VERSION = "0.1.0"
SERVER_NAME = "eclipse-basketseal"
PRODUCT_NAME = "Cyan Eclipse Basketseal"
DESCRIPTOR = "basket-arithmetic witness"
DISCIPLINE_ID = "basketseal-discipline"
DISCIPLINE_VERSION = "1.0"

# Price Book PC-4 pattern constants — pattern fit only. No price is
# adopted for this product; these figures name the pattern the
# metering classes follow, and the ledger records class + count only.
METER_PATTERN = {"single_amount": "0.10", "batch_amount": "0.02",
                 "batch_threshold": 100}

VERDICTS = ("RECOMPUTES", "MISCOMPUTES", "UNWITNESSED")
RECORD_STATES = ("SEALED", "SUPERSEDED")
DIFF_CLASSES = ("line-sum", "discount", "fee", "tax",
                "rate-application", "rounding-beyond-stated-precision")
VANTAGES = ("checkout-surface", "order-confirmation")

# Minor units per currency unit for the common ISO currencies the
# default tolerance derives from; anything else defaults to 2.
MINOR_UNITS = {"JPY": 0, "KRW": 0, "VND": 0, "ISK": 0,
               "BHD": 3, "KWD": 3, "OMR": 3}

BASKET_KEYS = {"merchant", "order_ref", "currency", "lines", "discounts",
               "fees", "tax", "charged_total", "rounding", "presented_at"}
LINE_KEYS = {"description", "description_class", "quantity",
             "unit_price", "line_total"}
DISCOUNT_KEYS = {"label", "amount", "rate", "base"}
FEE_KEYS = {"label", "amount", "rate", "base"}
TAX_KEYS = {"amount", "rate", "base"}
ROUNDING_KEYS = {"mode", "precision"}
ROUNDING_MODES = ("per-line", "per-total")
CAPTURE_KEYS = {"surface", "attestation", "vantage"}

# Custody fence (BK-C5): keys that may never appear anywhere in a
# basket artifact or a stored record.
FORBIDDEN_KEYS = {"card", "card_number", "pan", "cvv", "cvc", "iban",
                  "account", "account_number", "payment", "payment_method",
                  "credential", "credentials", "password", "secret",
                  "token", "ssn", "email", "phone", "address", "buyer",
                  "customer", "principal", "mandate", "purchase_order",
                  "po_number", "invoice", "receipt_id", "delivery"}


class BasketsealError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _dec(value, field):
    """A decimal string exactly as presented, or a named refusal."""
    if isinstance(value, bool) or not isinstance(value, str):
        raise BasketsealError(
            "BASKET_FIELD_TYPE",
            "%s must be a decimal string exactly as presented; "
            "JSON numbers are not accepted" % field)
    try:
        d = Decimal(value)
    except InvalidOperation:
        raise BasketsealError("BASKET_FIELD_VALUE",
                              "%s is not a decimal string" % field)
    if not d.is_finite():
        raise BasketsealError("BASKET_FIELD_VALUE",
                              "%s must be finite" % field)
    return d


def _places(d):
    exp = d.as_tuple().exponent
    return -exp if exp < 0 else 0


def _check_keys(obj, allowed, what):
    if not isinstance(obj, dict):
        raise BasketsealError("BASKET_FIELD_TYPE", "%s must be an object" % what)
    extra = set(obj) - allowed
    if extra:
        raise BasketsealError(
            "BASKET_FIELD_UNKNOWN",
            "%s carries field(s) outside the basket grammar: %s"
            % (what, ", ".join(sorted(extra))))
    bad = set(obj) & FORBIDDEN_KEYS
    if bad:
        raise BasketsealError(
            "BASKET_CUSTODY_REFUSED",
            "%s carries excluded custody field(s): %s"
            % (what, ", ".join(sorted(bad))))


def _scan_forbidden(obj, what):
    if isinstance(obj, dict):
        bad = set(obj) & FORBIDDEN_KEYS
        if bad:
            raise BasketsealError(
                "BASKET_CUSTODY_REFUSED",
                "%s carries excluded custody field(s): %s"
                % (what, ", ".join(sorted(bad))))
        for v in obj.values():
            _scan_forbidden(v, what)
    elif isinstance(obj, list):
        for v in obj:
            _scan_forbidden(v, what)


def _str_field(obj, key, what, required=True):
    v = obj.get(key)
    if v is None:
        if required:
            raise BasketsealError("BASKET_FIELD_MISSING",
                                  "%s.%s is required" % (what, key))
        return None
    if not isinstance(v, str) or not v.strip():
        raise BasketsealError("BASKET_FIELD_TYPE",
                              "%s.%s must be a non-empty string" % (what, key))
    return v


def validate_basket(basket):
    """Validate the basket artifact against the closed grammar.
    Returns the basket unchanged; raises BasketsealError on any
    shape outside the single-artifact basket question."""
    if not isinstance(basket, dict):
        raise BasketsealError("BASKET_FIELD_TYPE", "basket must be an object")
    _scan_forbidden(basket, "basket")
    _check_keys(basket, BASKET_KEYS, "basket")
    _str_field(basket, "merchant", "basket")
    if basket.get("order_ref") is not None:
        _str_field(basket, "order_ref", "basket")
    currency = _str_field(basket, "currency", "basket")
    if len(currency) != 3 or not currency.isalpha() \
            or currency != currency.upper():
        raise BasketsealError("BASKET_FIELD_VALUE",
                              "currency must be a three-letter ISO code")
    lines = basket.get("lines")
    if not isinstance(lines, list) or not lines:
        raise BasketsealError("BASKET_FIELD_MISSING",
                              "basket.lines must be a non-empty list")
    for i, line in enumerate(lines):
        what = "lines[%d]" % i
        _check_keys(line, LINE_KEYS, what)
        _str_field(line, "description", what)
        if line.get("description_class") is not None:
            _str_field(line, "description_class", what)
        _dec(line.get("quantity"), what + ".quantity")
        _dec(line.get("unit_price"), what + ".unit_price")
        _dec(line.get("line_total"), what + ".line_total")
    for key, keys, what in (("discounts", DISCOUNT_KEYS, "discounts"),
                            ("fees", FEE_KEYS, "fees")):
        items = basket.get(key)
        if items is None:
            continue
        if not isinstance(items, list):
            raise BasketsealError("BASKET_FIELD_TYPE",
                                  "basket.%s must be a list" % key)
        for i, item in enumerate(items):
            w = "%s[%d]" % (what, i)
            _check_keys(item, keys, w)
            _str_field(item, "label", w)
            _dec(item.get("amount"), w + ".amount")
            if item.get("rate") is not None:
                _dec(item["rate"], w + ".rate")
            if item.get("base") is not None:
                _dec(item["base"], w + ".base")
    tax = basket.get("tax")
    if tax is not None:
        _check_keys(tax, TAX_KEYS, "tax")
        _dec(tax.get("amount"), "tax.amount")
        if tax.get("rate") is not None:
            _dec(tax["rate"], "tax.rate")
        if tax.get("base") is not None:
            _dec(tax["base"], "tax.base")
    _dec(basket.get("charged_total"), "basket.charged_total")
    rounding = basket.get("rounding")
    if rounding is not None:
        _check_keys(rounding, ROUNDING_KEYS, "rounding")
        if rounding.get("mode") not in ROUNDING_MODES:
            raise BasketsealError(
                "BASKET_FIELD_VALUE",
                "rounding.mode must be per-line or per-total")
        if rounding.get("precision") is not None:
            _dec(rounding["precision"], "rounding.precision")
    if basket.get("presented_at") is not None:
        _str_field(basket, "presented_at", "basket")
    return basket


def classify_capture(capture):
    """Witnessed iff a first-party capture record is present with an
    attestation and an allowed vantage. Anything else seals as
    UNWITNESSED — an architectural outcome, not a policy verdict."""
    if not isinstance(capture, dict):
        return None, "capture absent"
    # Custody material in a capture is a custody refusal, as in a
    # basket (cure F-4); any other field outside the capture
    # grammar makes the capture invalid as presented, so the
    # basket seals UNWITNESSED like every other invalid capture
    # instead of aborting the seal with no record at all.
    _scan_forbidden(capture, "capture")
    if set(capture) - CAPTURE_KEYS:
        return None, "capture carries field(s) outside the capture grammar"
    vantage = capture.get("vantage")
    if vantage not in VANTAGES:
        return None, "vantage is not a first-party basket surface"
    if not capture.get("attestation"):
        return None, "capture attestation absent"
    if not capture.get("surface"):
        return None, "presenting surface absent"
    return vantage, None


def canonical_components(basket):
    """The canonical component list, in presentation order, amounts
    as decimal strings exactly as presented (discounts and fees as
    signed component lines)."""
    comps = []
    for line in basket["lines"]:
        comps.append({
            "kind": "line",
            "description_class": line.get("description_class") or "unspecified",
            "description_sha256": _sha(line["description"]),
            "quantity": line["quantity"],
            "unit_price": line["unit_price"],
            "line_total": line["line_total"],
        })
    for d in basket.get("discounts") or []:
        comp = {"kind": "discount", "label": d["label"],
                "amount": _signed(d["amount"], negative=True)}
        if d.get("rate") is not None:
            comp["rate"] = d["rate"]
        if d.get("base") is not None:
            comp["base"] = d["base"]
        comps.append(comp)
    for f in basket.get("fees") or []:
        comp = {"kind": "fee", "label": f["label"],
                "amount": _signed(f["amount"], negative=False)}
        if f.get("rate") is not None:
            comp["rate"] = f["rate"]
        if f.get("base") is not None:
            comp["base"] = f["base"]
        comps.append(comp)
    tax = basket.get("tax")
    if tax is not None:
        comp = {"kind": "tax", "amount": tax["amount"]}
        if tax.get("rate") is not None:
            comp["rate"] = tax["rate"]
        if tax.get("base") is not None:
            comp["base"] = tax["base"]
        comps.append(comp)
    return comps


def _signed(amount_str, negative):
    d = Decimal(amount_str)
    mag = abs(d)
    out = -mag if negative else mag
    return format(out, "f")


def canonical_form(basket):
    rounding = basket.get("rounding")
    form = {
        "discipline": DISCIPLINE_VERSION,
        "currency": basket["currency"],
        "components": canonical_components(basket),
        "charged_total": basket["charged_total"],
        "rounding": ({"mode": rounding["mode"],
                      "precision": rounding.get("precision")}
                     if rounding else None),
    }
    return form


def canonical_digest(form):
    return _sha(_canon(form))


# ---------------------------------------------------------------------
# Recomputation — defined over the canonical components alone.
# ---------------------------------------------------------------------

def _precision_unit(form):
    """(unit, basis): the basket's stated precision unit where the
    basket states one, else the currency's smallest sub-unit."""
    rounding = form.get("rounding") or {}
    if rounding.get("precision"):
        return Decimal(rounding["precision"]), "stated-precision"
    minor = MINOR_UNITS.get(form["currency"], 2)
    return Decimal(1).scaleb(-minor), "default-subunit"


def _q(value, unit):
    return value.quantize(unit, rounding=ROUND_HALF_UP)


def _fmt(d):
    return format(d, "f")


def recompute(form):
    """Recompute the basket total from its canonical components.
    Returns the recomputation block: verdict (RECOMPUTES or
    MISCOMPUTES), per-component diffs (class + amount always),
    the tolerance applied and its basis, and both totals."""
    unit, basis = _precision_unit(form)
    tolerance = unit / 2
    mode = (form.get("rounding") or {}).get("mode") or "per-total"
    diffs = []

    def add_diff(component, klass, presented, expected):
        diff = presented - expected
        if abs(diff) <= tolerance:
            return
        # A diff inside one precision unit on a value presented finer
        # than the stated precision is a rounding-representation
        # breach, not an arithmetic one.
        if basis == "stated-precision" and abs(diff) <= unit \
                and _places(presented) > _places(unit):
            klass = "rounding-beyond-stated-precision"
        diffs.append({"component": component, "class": klass,
                      "presented": _fmt(presented),
                      "expected": _fmt(expected), "diff": _fmt(diff)})

    lines_total = Decimal(0)
    discounts_total = Decimal(0)
    fees_total = Decimal(0)
    tax_total = Decimal(0)
    n_line = n_disc = n_fee = 0
    for comp in form["components"]:
        kind = comp["kind"]
        if kind == "line":
            qty = Decimal(comp["quantity"])
            price = Decimal(comp["unit_price"])
            presented_lt = Decimal(comp["line_total"])
            exact = qty * price
            expected_lt = _q(exact, unit) if mode == "per-line" else exact
            add_diff("line[%d]" % n_line, "line-sum", presented_lt,
                     _q(expected_lt, unit) if mode == "per-total"
                     else expected_lt)
            lines_total += expected_lt
            n_line += 1
        elif kind in ("discount", "fee"):
            idx = n_disc if kind == "discount" else n_fee
            name = "%s[%d]" % (kind, idx)
            amount = Decimal(comp["amount"])
            magnitude = abs(amount)
            used = magnitude
            if comp.get("rate") is not None and comp.get("base") is not None:
                expected = _q(Decimal(comp["base"]) * Decimal(comp["rate"]),
                              unit)
                add_diff(name, "rate-application", magnitude, expected)
                used = expected
            elif comp.get("base") is not None:
                base = Decimal(comp["base"])
                if magnitude - base > tolerance:
                    diffs.append({"component": name, "class": kind,
                                  "presented": _fmt(magnitude),
                                  "expected": _fmt(base),
                                  "diff": _fmt(magnitude - base)})
            if kind == "discount":
                discounts_total += used
                n_disc += 1
            else:
                fees_total += used
                n_fee += 1
        elif kind == "tax":
            amount = Decimal(comp["amount"])
            used = amount
            if comp.get("rate") is not None and comp.get("base") is not None:
                expected = _q(Decimal(comp["base"]) * Decimal(comp["rate"]),
                              unit)
                add_diff("tax", "rate-application", amount, expected)
                used = expected
            if comp.get("base") is not None:
                taxable = lines_total - discounts_total
                base = Decimal(comp["base"])
                if abs(base - taxable) > tolerance:
                    diffs.append({"component": "tax", "class": "tax",
                                  "presented": _fmt(base),
                                  "expected": _fmt(taxable),
                                  "diff": _fmt(base - taxable)})
            tax_total = used

    recomputed = lines_total - discounts_total + fees_total + tax_total
    charged = Decimal(form["charged_total"])
    total_diff = charged - recomputed
    if abs(total_diff) > tolerance and not diffs:
        diffs.append({"component": "total", "class": "line-sum",
                      "presented": _fmt(charged),
                      "expected": _fmt(_q(recomputed, unit)),
                      "diff": _fmt(total_diff)})
    verdict = "MISCOMPUTES" if (diffs or abs(total_diff) > tolerance) \
        else "RECOMPUTES"
    return {
        "verdict": verdict,
        "diffs": diffs,
        "recomputed_total": _fmt(_q(recomputed, unit)),
        "charged_total": form["charged_total"],
        "total_diff": _fmt(total_diff),
        "tolerance": _fmt(tolerance),
        "tolerance_basis": basis,
        "rounding_mode": mode,
        "discipline": DISCIPLINE_VERSION,
    }


def recompute_export(bundle):
    """Offline recomputation from an exported record bundle. Pure:
    reads no service state, writes nothing, is never metered and
    never licence-gated (BK-C9)."""
    if not isinstance(bundle, dict) or "canonical" not in bundle \
            or "canonical_digest" not in bundle:
        raise BasketsealError("EXPORT_SHAPE",
                              "bundle must carry canonical + canonical_digest")
    form = bundle["canonical"]
    if canonical_digest(form) != bundle["canonical_digest"]:
        raise BasketsealError(
            "EXPORT_DIGEST_MISMATCH",
            "the bundle's components do not hash to its pinned digest; "
            "the sealed components govern and this bundle is not them")
    result = recompute(form)
    recorded = bundle.get("verdict")
    # Only an issued recomputation verdict can match or diverge.
    # UNWITNESSED carries no recomputation verdict by construction,
    # and a licence-refused record carries verdict null; both take
    # the no-recorded-verdict path (cure F-2) instead of reporting
    # a no-verdict record as a failed verification.
    result["matches_recorded"] = (recorded == result["verdict"]) \
        if recorded in ("RECOMPUTES", "MISCOMPUTES") else None
    result["canonical_digest"] = bundle["canonical_digest"]
    return result


# ---------------------------------------------------------------------
# Service: sealed record store + receipt chain + metering ledger.
# ---------------------------------------------------------------------

def _default_state_root():
    override = os.environ.get("ECLIPSE_BASKETSEAL_STATE")
    if override:
        return override
    here = os.path.dirname(os.path.abspath(__file__))
    probe = os.path.join(here, ".write-probe")
    try:
        with open(probe, "w") as fh:
            fh.write("")
        os.unlink(probe)
        return os.path.join(here, "data")
    except OSError:
        return os.path.join(os.path.expanduser("~"), ".local", "state",
                            "eclipse-basketseal")


class BasketsealService:
    """One service instance over one state root. The licence gate is
    injected: None means no gate object was configured, which the
    service treats as no active licence (the metered verdict service
    is refused; intake, check, export and offline recompute serve)."""

    def __init__(self, state_root=None, licence_gate=None):
        self.state_root = state_root or _default_state_root()
        self.licence_gate = licence_gate
        self._lock = threading.Lock()
        os.makedirs(self.state_root, exist_ok=True)
        self._state_path = os.path.join(self.state_root, "basketseal.json")
        self._meter_path = os.path.join(self.state_root, "metering.jsonl")
        self._state = self._load()

    # -- persistence -------------------------------------------------
    def _load(self):
        if os.path.exists(self._state_path):
            with open(self._state_path, encoding="utf-8") as fh:
                return json.load(fh)
        return {"records": {}, "journal": []}

    def _save(self):
        fd, tmp = tempfile.mkstemp(dir=self.state_root,
                                   prefix=".basketseal-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=1, sort_keys=True)
            os.replace(tmp, self._state_path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- receipt chain ------------------------------------------------
    def _journal_append(self, kind, record_id, payload_digest):
        journal = self._state["journal"]
        prev = journal[-1]["hash"] if journal else "GENESIS"
        entry = {"seq": len(journal) + 1, "ts": _now(), "kind": kind,
                 "record_id": record_id, "payload_digest": payload_digest,
                 "prev": prev}
        entry["hash"] = _sha(prev + _canon(entry))
        journal.append(entry)
        return entry

    def verify_chain(self):
        prev = "GENESIS"
        for i, entry in enumerate(self._state["journal"]):
            body = {k: entry[k] for k in
                    ("seq", "ts", "kind", "record_id", "payload_digest",
                     "prev")}
            if entry["prev"] != prev or entry["seq"] != i + 1 \
                    or _sha(prev + _canon(body)) != entry["hash"]:
                return False, i + 1
            prev = entry["hash"]
        return True, len(self._state["journal"])

    def chain_head(self):
        journal = self._state["journal"]
        return journal[-1]["hash"] if journal else "GENESIS"

    # -- metering ------------------------------------------------------
    def _meter(self, event_class, count):
        seq = 1
        if os.path.exists(self._meter_path):
            with open(self._meter_path, encoding="utf-8") as fh:
                seq = sum(1 for _ in fh) + 1
        entry = {"seq": seq, "ts": _now(), "event_class": event_class,
                 "count": count}
        with open(self._meter_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def meter_entries(self):
        if not os.path.exists(self._meter_path):
            return []
        with open(self._meter_path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    # -- licence -------------------------------------------------------
    def _licence_serves(self):
        if self.licence_gate is None:
            return False, "LICENCE_NOT_ACTIVE"
        return self.licence_gate.serves()

    # -- sealing ---------------------------------------------------------
    def seal_basket(self, basket, capture=None):
        with self._lock:
            return self._seal_one(basket, capture, batch_count=1)

    def seal_batch(self, items):
        """Desk sweep entry (core API, not an MCP tool): seals a list
        of {basket, capture} items; verdict issuances in a batch of
        >= the PC-4 threshold meter at the batch class."""
        with self._lock:
            count = len(items)
            event_class = "batch" if count >= METER_PATTERN["batch_threshold"] \
                else "single"
            results = []
            issued = 0
            for item in items:
                rec = self._seal_one(item.get("basket"), item.get("capture"),
                                     batch_count=0)
                results.append(rec)
                if rec.get("verdict") in ("RECOMPUTES", "MISCOMPUTES"):
                    issued += 1
            if issued:
                self._meter(event_class, issued)
            return results

    def _seal_one(self, basket, capture, batch_count):
        validate_basket(basket)
        vantage, _why = classify_capture(capture)
        form = canonical_form(basket)
        digest = canonical_digest(form)
        order_ref = basket.get("order_ref")
        version = 1
        supersedes = None
        if order_ref:
            prior = [rec for rec in self._state["records"].values()
                     if rec["order_ref"] == order_ref
                     and rec["state"] == "SEALED"]
            if prior:
                latest = max(prior, key=lambda rec: rec["version"])
                version = latest["version"] + 1
                supersedes = latest["record_id"]
                for rec in prior:
                    rec["state"] = "SUPERSEDED"
        # Record identity (cure F-1 / BK-B3): the record_id derives
        # from the canonical digest PLUS this seal's identity
        # material — merchant, order reference, and the seal's own
        # journal sequence — so two distinct baskets with identical
        # arithmetic never share an id, every sealed record coexists
        # in the store, and no seal silently overwrites another
        # record. The canonical form is unchanged: recomputation
        # stays defined over the canonical components alone
        # (BKS-REQ-013), and supersession stays keyed to the order
        # reference.
        seal_seq = len(self._state["journal"]) + 1
        identity = {"digest": digest, "merchant": basket["merchant"],
                    "order_ref": order_ref, "seal_seq": seal_seq}
        record_id = "bks-%s-v%d" % (_sha(_canon(identity))[:12], version)
        record = {
            "record_id": record_id,
            "merchant": basket["merchant"],
            "order_ref": order_ref,
            "currency": basket["currency"],
            "components": form["components"],
            "charged_total": basket["charged_total"],
            "presented_at": basket.get("presented_at") or _now(),
            "captured_at": _now(),
            "vantage": vantage,
            "description_posture": "hash-sealed",
            "canonical": form,
            "canonical_digest": digest,
            "discipline": {"id": DISCIPLINE_ID, "version": DISCIPLINE_VERSION},
            "tolerance": None,
            "recomputation": None,
            "verdict": None,
            "state": "SEALED",
            "version": version,
            "supersedes": supersedes,
        }
        if vantage is None:
            record["verdict"] = "UNWITNESSED"
        else:
            block = recompute(form)
            record["tolerance"] = {"applied": block["tolerance"],
                                   "basis": block["tolerance_basis"]}
            serves, reason = self._licence_serves()
            if serves:
                record["recomputation"] = block
                record["verdict"] = block["verdict"]
            else:
                record["verdict_issuance"] = (
                    "refused: %s — the record is sealed at intake; "
                    "verdict issuance is the metered recomputation "
                    "service and operates only under a valid licence"
                    % reason)
        record["record_hash"] = _sha(_canon(
            {k: v for k, v in record.items()
             if k not in ("record_hash", "state")}))
        self._state["records"][record_id] = record
        self._journal_append("seal", record_id, record["record_hash"])
        if record["verdict"] in ("RECOMPUTES", "MISCOMPUTES"):
            v_digest = _sha(_canon(record["recomputation"]))
            self._journal_append("verdict", record_id, v_digest)
            if batch_count:
                self._meter("single", 1)
        self._save()
        return record

    # -- reads -----------------------------------------------------------
    def _verify_record(self, rec):
        """Per-read integrity (cure F-3): a stored record serves only
        if its sealed fields still hash to its record_hash and its
        canonical form still digests to its pinned canonical_digest.
        A tampered state file is refused with a named signal instead
        of serving altered components under the original verdict.
        (The record state field is excluded from the hash, as at
        seal time, because supersession legitimately changes it.)"""
        body = {k: v for k, v in rec.items()
                if k not in ("record_hash", "state")}
        canonical = rec.get("canonical")
        ok = rec.get("record_hash") == _sha(_canon(body)) \
            and isinstance(canonical, dict) \
            and rec.get("canonical_digest") == canonical_digest(canonical)
        if not ok:
            raise BasketsealError(
                "RECORD_INTEGRITY_MISMATCH",
                "the stored record does not verify against its sealed "
                "hashes; refusing to serve it")

    def _record(self, record_id):
        rec = self._state["records"].get(record_id)
        if rec is None:
            raise BasketsealError("RECORD_NOT_FOUND",
                                  "no sealed record under that id")
        self._verify_record(rec)
        return rec

    def get_record(self, record_id):
        return self._record(record_id)

    def check(self, record_id):
        """Verdict class + per-component diff summary only — never
        basket content (BKS-REQ-005). The verdict is null exactly
        when verdict issuance was refused (the licence leg);
        verdict_issuance names that refusal so the null is a named
        state, not a fourth unnamed one (cure F-4). It is null
        whenever a verdict was issued or the record is UNWITNESSED."""
        rec = self._record(record_id)
        diffs = []
        if rec.get("recomputation"):
            diffs = [{"component": d["component"], "class": d["class"],
                      "diff": d["diff"]}
                     for d in rec["recomputation"]["diffs"]]
        return {"record_id": rec["record_id"], "state": rec["state"],
                "verdict": rec["verdict"], "diffs": diffs,
                "tolerance": rec["tolerance"],
                "verdict_issuance": rec.get("verdict_issuance")}

    def export_record(self, record_id):
        rec = self._record(record_id)
        bundle = {"canonical": rec["canonical"],
                  "canonical_digest": rec["canonical_digest"],
                  "verdict": rec["verdict"],
                  "discipline": rec["discipline"],
                  "record_id": rec["record_id"],
                  "record_hash": rec["record_hash"]}
        return {"bundle": bundle, "chain_head": self.chain_head(),
                "journal_len": len(self._state["journal"]),
                "discipline": rec["discipline"]}
