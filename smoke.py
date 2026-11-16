#!/usr/bin/env python3
"""Cyan Eclipse Basketseal — transport + surface smoke (fixture scope).

Exercises both transports against a throwaway state root with a
fixture licence gate in the valid state: stdio initialize/list/call,
HTTP health + call + auth, a clean seal, a miscompute seal, an
UNWITNESSED seal, check, export, and offline recompute. Prints one
line per check; exit 0 iff all pass. Builder smoke is not bench
evidence.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def fx(name):
    with open(os.path.join(ROOT, "fixtures", name), encoding="utf-8") as fh:
        return json.load(fh)


def stdio_session(calls, state_root):
    env = dict(os.environ, ECLIPSE_BASKETSEAL_STATE=state_root,
               BASKETSEAL_SMOKE_FIXTURE_GATE="1")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, env=env)
    out = []
    try:
        for i, (method, params) in enumerate(calls, start=1):
            proc.stdin.write(json.dumps(
                {"jsonrpc": "2.0", "id": i, "method": method,
                 "params": params}) + "\n")
            proc.stdin.flush()
            out.append(json.loads(proc.stdout.readline()))
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
    return out


def tool_text(resp):
    return json.loads(resp["result"]["content"][0]["text"])


def main():
    state_root = tempfile.mkdtemp(prefix="bks-smoke-")
    clean = fx("fx-clean.json")
    bad = fx("fx-line-miscompute.json")
    unw = fx("fx-unwitnessed.json")

    # The smoke runs the fixture gate in the valid state so the full
    # surface is exercised; the gate states are suite-tested.
    import licence
    import basketseal
    svc = basketseal.BasketsealService(
        state_root=state_root, licence_gate=licence.FixtureGate("valid"))
    rec = svc.seal_basket(clean["basket"], clean["capture"])
    check("seal clean -> RECOMPUTES", rec["verdict"] == "RECOMPUTES")
    rec2 = svc.seal_basket(bad["basket"], bad["capture"])
    check("seal miscompute -> MISCOMPUTES + class",
          rec2["verdict"] == "MISCOMPUTES" and
          rec2["recomputation"]["diffs"][0]["class"] == "line-sum")
    rec3 = svc.seal_basket(unw["basket"], unw.get("capture"))
    check("seal without capture -> UNWITNESSED",
          rec3["verdict"] == "UNWITNESSED")
    ok, _ = svc.verify_chain()
    check("receipt chain verifies", ok)
    export = svc.export_record(rec["record_id"])
    out = basketseal.recompute_export(export["bundle"])
    check("offline recompute matches", out["matches_recorded"] is True)
    check("metering: two single events",
          [(e["event_class"], e["count"]) for e in svc.meter_entries()] ==
          [("single", 1), ("single", 1)])

    resp = stdio_session(
        [("initialize", {}), ("tools/list", {}), ("ping", {})], state_root)
    check("stdio initialize", resp[0]["result"]["serverInfo"]["name"] ==
          "eclipse-basketseal")
    check("stdio tools/list = 5 tools",
          len(resp[1]["result"]["tools"]) == 5)
    check("stdio ping", resp[2]["result"] == {})

    port = 18798
    env = dict(os.environ, ECLIPSE_BASKETSEAL_STATE=state_root,
               ECLIPSE_BASKETSEAL_HTTP_PORT=str(port),
               ECLIPSE_BASKETSEAL_HTTP_TOKEN="smoke-token")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py"),
                             "--http"], env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        health = None
        for _ in range(50):
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/health" % port,
                        timeout=2) as r:
                    health = json.loads(r.read())
                break
            except Exception:
                time.sleep(0.1)
        check("http health identity", bool(health) and
              health.get("product") == "Cyan Eclipse Basketseal")
        req = urllib.request.Request(
            "http://127.0.0.1:%d/" % port,
            data=json.dumps({"jsonrpc": "2.0", "id": 1,
                             "method": "tools/list", "params": {}}).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer smoke-token"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            body = json.loads(r.read())
        check("http tools/list with bearer",
              len(body["result"]["tools"]) == 5)
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    "http://127.0.0.1:%d/" % port,
                    data=b"{}", method="POST"), timeout=5)
            check("http unauthenticated refused", False)
        except urllib.error.HTTPError as e:
            check("http unauthenticated refused", e.code == 401)
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    failed = [n for n, ok in RESULTS if not ok]
    print("SMOKE %s (%d/%d)" % ("PASS" if not failed else "FAIL",
                                len(RESULTS) - len(failed), len(RESULTS)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
