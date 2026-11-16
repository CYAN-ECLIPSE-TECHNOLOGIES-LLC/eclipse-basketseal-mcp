"""Cyan Eclipse Basketseal — builder test suite.

Builder tests are not evidence; they exist so the bench's claims
have fixtures to re-derive. Claim map: BK-B1 recomputation
correctness · BK-B2 independent recomputation · BK-B3 record
pinning · BK-B4 separation · BK-B5 grammar closure · BK-B6 custody ·
ADV-1 sibling shapes · ADV-2 tolerance boundaries · kill criteria
K1 (receipt-locker), K2 (sibling), K3 (legal conclusions), K4
(checkout interception), K5 (evidence poisoning via rounding).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import basketseal
from basketseal import BasketsealError, BasketsealService
import licence
import server

FIX = os.path.join(ROOT, "fixtures")
CAPTURE = {"surface": "merchant.example/checkout",
           "attestation": "buyer-session-capture",
           "vantage": "checkout-surface"}


def load_fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


def tiny_basket(ref=None):
    b = {"merchant": "M", "currency": "USD",
         "lines": [{"description": "x", "quantity": "1",
                    "unit_price": "1.00", "line_total": "1.00"}],
         "charged_total": "1.00"}
    if ref:
        b["order_ref"] = ref
    return b


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bks-test-")
        self.svc = BasketsealService(
            state_root=self.tmp,
            licence_gate=licence.FixtureGate("valid"))

    def seal_fx(self, name):
        fx = load_fx(name)
        return self.svc.seal_basket(fx["basket"], fx.get("capture"))


class RecomputationTests(ServiceCase):
    def test_b1_clean_basket_recomputes(self):
        rec = self.seal_fx("fx-clean.json")
        self.assertEqual(rec["verdict"], "RECOMPUTES")
        self.assertEqual(rec["recomputation"]["diffs"], [])
        self.assertEqual(rec["recomputation"]["recomputed_total"], "113.00")
        self.assertEqual(rec["tolerance"],
                         {"applied": "0.005", "basis": "stated-precision"})

    def test_b1_line_miscompute_names_class_and_amount(self):
        rec = self.seal_fx("fx-line-miscompute.json")
        self.assertEqual(rec["verdict"], "MISCOMPUTES")
        diffs = rec["recomputation"]["diffs"]
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["class"], "line-sum")
        self.assertEqual(diffs[0]["component"], "line[1]")
        self.assertEqual(diffs[0]["diff"], "0.30")

    def test_b1_tax_rate_application(self):
        rec = self.seal_fx("fx-tax-rate.json")
        self.assertEqual(rec["verdict"], "MISCOMPUTES")
        classes = [d["class"] for d in rec["recomputation"]["diffs"]]
        self.assertEqual(classes, ["rate-application"])
        self.assertEqual(rec["recomputation"]["diffs"][0]["diff"], "0.50")

    def test_b1_total_miscompute(self):
        rec = self.seal_fx("fx-total-miscompute.json")
        self.assertEqual(rec["verdict"], "MISCOMPUTES")
        diffs = rec["recomputation"]["diffs"]
        self.assertEqual(diffs[0]["component"], "total")
        self.assertEqual(diffs[0]["diff"], "1.00")

    def test_b1_discount_over_base_class(self):
        rec = self.seal_fx("fx-discount-over-base.json")
        self.assertEqual(rec["verdict"], "MISCOMPUTES")
        self.assertEqual(rec["recomputation"]["diffs"][0]["class"],
                         "discount")

    def test_k5_per_line_discipline_recomputes(self):
        rec = self.seal_fx("fx-per-line-rounding.json")
        self.assertEqual(rec["verdict"], "RECOMPUTES")

    def test_k5_same_numbers_per_total_miscompute(self):
        # The identical components under the other stated discipline
        # miscompute — the basket's own stated rounding governs.
        rec = self.seal_fx("fx-per-total-rounding.json")
        self.assertEqual(rec["verdict"], "MISCOMPUTES")

    def test_adv2_subunit_edge_recomputes_no_wolf_cry(self):
        rec = self.seal_fx("fx-subunit-edge.json")
        self.assertEqual(rec["verdict"], "RECOMPUTES")
        self.assertEqual(rec["tolerance"]["basis"], "default-subunit")

    def test_adv2_subunit_over_miscomputes(self):
        rec = self.seal_fx("fx-subunit-over.json")
        self.assertEqual(rec["verdict"], "MISCOMPUTES")

    def test_k5_rounding_beyond_stated_precision_class(self):
        basket = {"merchant": "M", "currency": "USD",
                  "lines": [{"description": "x", "quantity": "1",
                             "unit_price": "20.00", "line_total": "20.007"}],
                  "charged_total": "20.007",
                  "rounding": {"mode": "per-total", "precision": "0.01"}}
        rec = self.svc.seal_basket(basket, CAPTURE)
        self.assertEqual(rec["verdict"], "MISCOMPUTES")
        self.assertEqual(rec["recomputation"]["diffs"][0]["class"],
                         "rounding-beyond-stated-precision")

    def test_decimal_strings_only(self):
        basket = tiny_basket()
        basket["lines"][0]["unit_price"] = 1.00  # a JSON number
        with self.assertRaises(BasketsealError) as cm:
            self.svc.seal_basket(basket, CAPTURE)
        self.assertEqual(cm.exception.code, "BASKET_FIELD_TYPE")

    def test_unknown_field_refused(self):
        basket = tiny_basket()
        basket["gift_wrap"] = "yes"
        with self.assertRaises(BasketsealError) as cm:
            self.svc.seal_basket(basket, CAPTURE)
        self.assertEqual(cm.exception.code, "BASKET_FIELD_UNKNOWN")


class WitnessTests(ServiceCase):
    def test_unwitnessed_without_capture(self):
        rec = self.seal_fx("fx-unwitnessed.json")
        self.assertEqual(rec["verdict"], "UNWITNESSED")
        self.assertIsNone(rec["recomputation"])
        kinds = [e["kind"] for e in self.svc._state["journal"]]
        self.assertEqual(kinds, ["seal"])  # no verdict receipt

    def test_unwitnessed_bad_vantage_and_missing_attestation(self):
        for capture in ({"surface": "s", "attestation": "a",
                         "vantage": "scraped-page"},
                        {"surface": "s", "vantage": "checkout-surface"}):
            rec = self.svc.seal_basket(tiny_basket(), capture)
            self.assertEqual(rec["verdict"], "UNWITNESSED")

    def test_k1_no_receipt_locker(self):
        # Every witnessed seal carries a recomputation and a verdict
        # from the closed grammar — a wrong total can never come
        # back as a plain sealed record.
        for name in ("fx-clean.json", "fx-line-miscompute.json",
                     "fx-tax-rate.json", "fx-total-miscompute.json"):
            rec = self.seal_fx(name)
            self.assertIn(rec["verdict"], ("RECOMPUTES", "MISCOMPUTES"))
            self.assertIsNotNone(rec["recomputation"])

    def test_supersession_versions_the_basket(self):
        v1 = self.seal_fx("fx-clean.json")
        fx2 = load_fx("fx-total-miscompute.json")
        fx2["basket"]["order_ref"] = "NB-1001"
        v2 = self.svc.seal_basket(fx2["basket"], fx2["capture"])
        self.assertEqual(v2["version"], 2)
        self.assertEqual(v2["supersedes"], v1["record_id"])
        self.assertEqual(self.svc.get_record(v1["record_id"])["state"],
                         "SUPERSEDED")
        self.assertEqual(v2["state"], "SEALED")


class RecordIntegrityTests(ServiceCase):
    def test_journal_chain_verifies_and_detects_tamper(self):
        self.seal_fx("fx-clean.json")
        self.seal_fx("fx-line-miscompute.json")
        ok, n = self.svc.verify_chain()
        self.assertTrue(ok)
        self.assertEqual(n, 4)  # seal + verdict, twice
        self.svc._state["journal"][1]["payload_digest"] = "0" * 64
        ok, _ = self.svc.verify_chain()
        self.assertFalse(ok)

    def test_b2_export_recompute_offline_and_verifier(self):
        rec = self.seal_fx("fx-line-miscompute.json")
        export = self.svc.export_record(rec["record_id"])
        self.assertEqual(export["chain_head"], self.svc.chain_head())
        state_path = os.path.join(self.tmp, "basketseal.json")
        with open(state_path, "rb") as fh:
            before = fh.read()
        out = basketseal.recompute_export(export["bundle"])
        self.assertEqual(out["verdict"], "MISCOMPUTES")
        self.assertTrue(out["matches_recorded"])
        with open(state_path, "rb") as fh:
            self.assertEqual(fh.read(), before)  # no state touched
        path = os.path.join(self.tmp, "export.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(export, fh)
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "verifier.py"), path],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("DIGEST OK", proc.stdout)
        self.assertIn("MATCH", proc.stdout)

    def test_b3_substituted_components_fail_digest(self):
        rec = self.seal_fx("fx-clean.json")
        export = self.svc.export_record(rec["record_id"])
        bundle = json.loads(json.dumps(export["bundle"]))
        bundle["canonical"]["components"][0]["line_total"] = "1.00"
        with self.assertRaises(BasketsealError) as cm:
            basketseal.recompute_export(bundle)
        self.assertEqual(cm.exception.code, "EXPORT_DIGEST_MISMATCH")

    def test_check_is_summary_only(self):
        rec = self.seal_fx("fx-line-miscompute.json")
        chk = self.svc.check(rec["record_id"])
        self.assertEqual(set(chk), {"record_id", "state", "verdict",
                                    "diffs", "tolerance"})
        self.assertEqual(chk["verdict"], "MISCOMPUTES")
        self.assertEqual(chk["diffs"][0]["class"], "line-sum")

    def test_b6_store_census_and_custody(self):
        rec = self.seal_fx("fx-clean.json")
        blob = json.dumps(rec)
        self.assertNotIn("Trail Shoes", blob)  # text hash-sealed
        allowed = {"record_id", "merchant", "order_ref", "currency",
                   "components", "charged_total", "presented_at",
                   "captured_at", "vantage", "description_posture",
                   "canonical", "canonical_digest", "discipline",
                   "tolerance", "recomputation", "verdict",
                   "verdict_issuance", "state", "version", "supersedes",
                   "record_hash"}
        self.assertLessEqual(set(rec), allowed)
        kinds = {c["kind"] for c in rec["components"]}
        self.assertLessEqual(kinds, {"line", "discount", "fee", "tax"})

        def walk(obj):
            if isinstance(obj, dict):
                self.assertFalse(set(obj) & basketseal.FORBIDDEN_KEYS)
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)
        walk(rec)

    def test_custody_field_refused_at_intake(self):
        basket = tiny_basket()
        basket["lines"][0]["card_number"] = "4242424242424242"
        with self.assertRaises(BasketsealError) as cm:
            self.svc.seal_basket(basket, CAPTURE)
        self.assertEqual(cm.exception.code, "BASKET_CUSTODY_REFUSED")


class SeparationTests(ServiceCase):
    def test_adv1_sibling_pair_fixture_refused(self):
        fx = load_fx("fx-sibling-po-pair.json")
        with self.assertRaises(BasketsealError):
            self.svc.seal_basket(fx["basket"], fx["capture"])

    def test_k2_denylist_refusal_byte_identical(self):
        unknown = server.dispatch(
            "tools/call", {"name": "totally_made_up_tool", "arguments": {}})
        for name in sorted(server.DENYLIST):
            out = server.dispatch("tools/call",
                                  {"name": name, "arguments": {}})
            self.assertEqual(out, unknown, name)
            self.assertIn("NO_SUCH_TOOL",
                          out["content"][0]["text"])

    def test_k4_tool_surface_is_exactly_five(self):
        names = {t["name"] for t in server.TOOLS}
        self.assertEqual(names, {
            "basketseal_seal_basket", "basketseal_get_record",
            "basketseal_check", "basketseal_recompute",
            "basketseal_export_record"})

    def test_k4_sealing_never_mutates_the_basket(self):
        basket = tiny_basket()
        snapshot = json.loads(json.dumps(basket))
        self.svc.seal_basket(basket, CAPTURE)
        self.assertEqual(basket, snapshot)


class GrammarTests(ServiceCase):
    def test_b5_verdict_words_closed(self):
        seen = set()
        for name in ("fx-clean.json", "fx-line-miscompute.json",
                     "fx-unwitnessed.json"):
            seen.add(self.seal_fx(name)["verdict"])
        self.assertLessEqual(seen, set(basketseal.VERDICTS))
        states = {r["state"] for r in self.svc._state["records"].values()}
        self.assertLessEqual(states, set(basketseal.RECORD_STATES))
        classes = set()
        for r in self.svc._state["records"].values():
            if r["recomputation"]:
                classes |= {d["class"] for d in r["recomputation"]["diffs"]}
        self.assertLessEqual(classes, set(basketseal.DIFF_CLASSES))

    def test_k3_no_legal_conclusion_language(self):
        banned = ["over" + "charge proven", "fra" + "ud",
                  "deceptive" + " pricing", "refund" + " owed",
                  "entitl" + "ed", "basket" + " verified",
                  "prices were" + " fair"]
        surfaces = []
        for name in ("fx-clean.json", "fx-line-miscompute.json"):
            surfaces.append(json.dumps(self.seal_fx(name)))
        for fname in ("README.md", "server.py", "basketseal.py"):
            with open(os.path.join(ROOT, fname), encoding="utf-8") as fh:
                surfaces.append(fh.read())
        for text in surfaces:
            low = text.lower()
            for phrase in banned:
                self.assertNotIn(phrase, low)


class MeteringLicenceTests(unittest.TestCase):
    def make(self, gate_state):
        tmp = tempfile.mkdtemp(prefix="bks-meter-")
        gate = licence.FixtureGate(gate_state) if gate_state else None
        return BasketsealService(state_root=tmp, licence_gate=gate), tmp

    def test_metering_event_classes_exact(self):
        svc, _ = self.make("valid")
        fx = load_fx("fx-clean.json")
        svc.seal_basket(fx["basket"], fx["capture"])
        svc.seal_basket(fx["basket"], fx["capture"])
        entries = svc.meter_entries()
        self.assertEqual([(e["event_class"], e["count"]) for e in entries],
                         [("single", 1), ("single", 1)])
        unw = load_fx("fx-unwitnessed.json")
        rec = svc.seal_basket(unw["basket"], unw.get("capture"))
        svc.check(rec["record_id"])
        export = svc.export_record(rec["record_id"])
        basketseal.recompute_export(export["bundle"])
        self.assertEqual(len(svc.meter_entries()), 2)  # nothing added
        batch = [{"basket": tiny_basket(), "capture": CAPTURE}
                 for _ in range(100)]
        svc.seal_batch(batch)
        entries = svc.meter_entries()
        self.assertEqual((entries[-1]["event_class"], entries[-1]["count"]),
                         ("batch", 100))
        for e in entries:
            self.assertEqual(set(e), {"seq", "ts", "event_class", "count"})

    def test_licence_three_states(self):
        fx = load_fx("fx-clean.json")
        unw = load_fx("fx-unwitnessed.json")
        for gate_state, served in ((None, False), ("revoked", False),
                                   ("valid", True)):
            svc, _ = self.make(gate_state)
            rec = svc.seal_basket(fx["basket"], fx["capture"])
            if served:
                self.assertEqual(rec["verdict"], "RECOMPUTES")
            else:
                self.assertIsNone(rec["verdict"])
                self.assertTrue(
                    rec["verdict_issuance"].startswith("refused: LICEN"))
                self.assertEqual(svc.meter_entries(), [])
            # Unmetered legs serve identically in every state.
            rec_u = svc.seal_basket(unw["basket"], unw.get("capture"))
            self.assertEqual(rec_u["verdict"], "UNWITNESSED")
            got = svc.get_record(rec["record_id"])
            self.assertEqual(got["record_id"], rec["record_id"])
            chk = svc.check(rec["record_id"])
            self.assertEqual(chk["record_id"], rec["record_id"])
            export = svc.export_record(rec["record_id"])
            out = basketseal.recompute_export(export["bundle"])
            self.assertEqual(out["verdict"], "RECOMPUTES")


def cure_basket(merchant, ref, total="113.00"):
    """The bench F-1 probe shape: one fixed arithmetic, variable
    identity (merchant / order_ref / charged total)."""
    return {"merchant": merchant, "order_ref": ref, "currency": "USD",
            "lines": [{"description": "Trail Shoes",
                       "description_class": "footwear", "quantity": "1",
                       "unit_price": "80.00", "line_total": "80.00"},
                      {"description": "Wool Socks",
                       "description_class": "apparel", "quantity": "2",
                       "unit_price": "12.50", "line_total": "25.00"}],
            "discounts": [{"label": "Autumn sale", "amount": "5.00"}],
            "fees": [{"label": "Shipping", "amount": "5.00"}],
            "tax": {"amount": "8.00", "rate": "0.08", "base": "100.00"},
            "charged_total": total,
            "rounding": {"mode": "per-total", "precision": "0.01"}}


class CureF1RecordIdentityTests(ServiceCase):
    """Regression tests for Verity F-1 (HIGH, BK-B3): record_id
    collision / silent overwrite. Each fails on the pre-cure code."""

    def test_f1_two_distinct_baskets_same_arithmetic_coexist(self):
        a = self.svc.seal_basket(cure_basket("Merchant A", "ORD-001"),
                                 CAPTURE)
        b = self.svc.seal_basket(cure_basket("Merchant B", "ORD-002"),
                                 CAPTURE)
        self.assertNotEqual(a["record_id"], b["record_id"])
        self.assertEqual(len(self.svc._state["records"]), 2)
        got_a = self.svc.get_record(a["record_id"])
        self.assertEqual(got_a["merchant"], "Merchant A")
        self.assertEqual(got_a["order_ref"], "ORD-001")
        got_b = self.svc.get_record(b["record_id"])
        self.assertEqual(got_b["merchant"], "Merchant B")
        self.assertEqual(got_b["order_ref"], "ORD-002")
        ids = {e["record_id"] for e in self.svc._state["journal"]}
        self.assertEqual(ids, {a["record_id"], b["record_id"]})

    def test_f1_post_collision_supersession(self):
        r100 = self.svc.seal_basket(cure_basket("Merchant A", "ORD-100"),
                                    CAPTURE)
        r101 = self.svc.seal_basket(cure_basket("Merchant A", "ORD-101"),
                                    CAPTURE)
        self.assertNotEqual(r100["record_id"], r101["record_id"])
        self.assertEqual(len(self.svc._state["records"]), 2)
        r100b = self.svc.seal_basket(
            cure_basket("Merchant A", "ORD-100", total="114.00"), CAPTURE)
        self.assertEqual(r100b["version"], 2)
        self.assertEqual(r100b["supersedes"], r100["record_id"])
        self.assertEqual(self.svc.get_record(r100["record_id"])["state"],
                         "SUPERSEDED")
        still = self.svc.get_record(r101["record_id"])
        self.assertEqual(still["state"], "SEALED")
        self.assertEqual(still["version"], 1)
        self.assertEqual(len(self.svc._state["records"]), 3)


class CureF2UnwitnessedExportTests(ServiceCase):
    """Regression test for Verity F-2 (MED, BK-B5/BK-B2 edge): an
    exported UNWITNESSED record misreported as divergence. Fails on
    the pre-cure code (matches_recorded False; verifier exit 1)."""

    def test_f2_unwitnessed_export_reports_no_recorded_verdict(self):
        rec = self.seal_fx("fx-unwitnessed.json")
        self.assertEqual(rec["verdict"], "UNWITNESSED")
        export = self.svc.export_record(rec["record_id"])
        out = basketseal.recompute_export(export["bundle"])
        self.assertIsNone(out["matches_recorded"])
        path = os.path.join(self.tmp, "export-unwitnessed.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(export, fh)
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "verifier.py"), path],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("DIGEST OK", proc.stdout)
        self.assertIn("UNRECORDED", proc.stdout)
        self.assertNotIn("DIVERGENT", proc.stdout)


class CureF3ReadIntegrityTests(ServiceCase):
    """Regression test for Verity F-3 (MED, QA P6): reads did not
    re-verify integrity — a stored component edited in the state
    file was served under the original verdict with no signal.
    Fails on the pre-cure code (tampered record serves)."""

    def test_f3_tampered_stored_record_refused_on_read(self):
        rec = self.seal_fx("fx-clean.json")
        # An honest record verifies and serves after a reload.
        fresh = BasketsealService(
            state_root=self.tmp,
            licence_gate=licence.FixtureGate("valid"))
        self.assertEqual(fresh.get_record(rec["record_id"])["verdict"],
                         "RECOMPUTES")
        # Tamper: edit a stored component in the state file itself.
        state_path = os.path.join(self.tmp, "basketseal.json")
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
        stored = state["records"][rec["record_id"]]
        stored["components"][0]["line_total"] = "1.00"
        stored["canonical"]["components"][0]["line_total"] = "1.00"
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        reloaded = BasketsealService(
            state_root=self.tmp,
            licence_gate=licence.FixtureGate("valid"))
        for read in (reloaded.get_record, reloaded.check,
                     reloaded.export_record):
            with self.assertRaises(BasketsealError) as cm:
                read(rec["record_id"])
            self.assertEqual(cm.exception.code,
                             "RECORD_INTEGRITY_MISMATCH")


class TransportTests(unittest.TestCase):
    def test_stdio_dispatch_and_content_free(self):
        init = server.dispatch("initialize", {})
        self.assertEqual(init["serverInfo"]["name"], "eclipse-basketseal")
        listed = server.dispatch("tools/list", {})
        self.assertEqual(len(listed["tools"]), 5)
        self.assertEqual(server.dispatch("ping", {}), {})
        refused = server.dispatch(
            "tools/call", {"name": "basketseal_check",
                           "arguments": {"record_id": "x",
                                         "_content_free": True}})
        self.assertTrue(refused["isError"])
        self.assertIn("CONTENT_FREE_REFUSED",
                      refused["content"][0]["text"])

    def test_version_lockstep(self):
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
            version = fh.read().strip()
        with open(os.path.join(ROOT, "pyproject.toml"),
                  encoding="utf-8") as fh:
            self.assertIn('version = "%s"' % version, fh.read())
        with open(os.path.join(ROOT, "server.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["version"], version)
        self.assertEqual(basketseal.TOOL_VERSION, version)


if __name__ == "__main__":
    unittest.main()
