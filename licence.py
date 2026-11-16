"""Licence gate for Cyan Eclipse Basketseal's metered service.

The metered recomputation-with-verdict service operates only under a
valid licence on the Cyan Eclipse License Server (BKS-REQ-018).
Intake sealing, basketseal_check, export, and offline recomputation
from an exported record are never licence-gated and never call here.

Two gate implementations:
- LicenseServerGate: live checks against the deployed License
  Server's thin HTTP face — artefact verification plus the
  revocation list, read at issuance time, so revocation is honoured
  in real time.
- FixtureGate: deterministic three-state gate for tests and fixture
  deployments (valid / revoked / none).
"""

import json
import os
import urllib.request
import urllib.error

PRODUCT_ID = "basketseal"
DEFAULT_TENANT = "cet"
DEFAULT_BASE_URL = "http://127.0.0.1:8799"


class FixtureGate:
    def __init__(self, state="valid"):
        self.state = state

    def serves(self):
        if self.state == "valid":
            return True, "LICENSE_VALID"
        if self.state == "revoked":
            return False, "LICENSE_REVOKED"
        return False, "LICENCE_NOT_ACTIVE"


class LicenseServerGate:
    def __init__(self, base_url=DEFAULT_BASE_URL, tenant_id=DEFAULT_TENANT,
                 artefact=None, product_id=PRODUCT_ID):
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.artefact = artefact
        self.product_id = product_id

    def _post(self, path, obj):
        req = urllib.request.Request(
            self.base_url + path, data=json.dumps(obj).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode())
            except Exception:
                return {"state": "LICENSE_SERVER_UNREACHABLE"}
        except Exception:
            return {"state": "LICENSE_SERVER_UNREACHABLE"}

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base_url + path,
                                        timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return {"state": "LICENSE_SERVER_UNREACHABLE"}

    def serves(self):
        if not self.artefact:
            return False, "LICENCE_NOT_ACTIVE"
        verdict = self._post("/verify", {"tenant_id": self.tenant_id,
                                         "artefact": self.artefact,
                                         "product_id": self.product_id})
        state = verdict.get("state")
        if state not in ("LICENSE_VALID", "LICENSE_GRACE"):
            return False, state or "LICENCE_NOT_ACTIVE"
        revocations = self._get("/revocation-list?tenant_id=%s&product_id=%s"
                                % (self.tenant_id, self.product_id))
        entries = revocations.get("revocations") or \
            revocations.get("entries") or []
        licence_id = verdict.get("license_id") or verdict.get("licence_id")
        for entry in entries:
            if isinstance(entry, dict) and licence_id and \
                    entry.get("license_id") == licence_id:
                return False, "LICENSE_REVOKED"
            if isinstance(entry, str) and licence_id and entry == licence_id:
                return False, "LICENSE_REVOKED"
        return True, state


def gate_from_env():
    """The server's gate: a live License Server gate when an operator
    licence artefact is configured, else None (no active licence —
    verdict issuance refused, unmetered legs serve)."""
    artefact = os.environ.get("BASKETSEAL_LICENSE_ARTEFACT")
    if not artefact:
        return None
    return LicenseServerGate(
        base_url=os.environ.get("BASKETSEAL_LICENSE_SERVER_URL",
                                DEFAULT_BASE_URL),
        tenant_id=os.environ.get("BASKETSEAL_LICENSE_TENANT", DEFAULT_TENANT),
        artefact=artefact,
        product_id=os.environ.get("BASKETSEAL_PRODUCT_ID", PRODUCT_ID))
