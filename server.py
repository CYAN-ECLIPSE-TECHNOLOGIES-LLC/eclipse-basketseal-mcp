#!/usr/bin/env python3
"""Cyan Eclipse Basketseal — MCP server (stdio + HTTP).

Agent-neutral MCP: standard protocol, stdio + HTTP transports,
host-agnostic. Tool surface is exactly the five tools of SPEC §4.1.
Any tool name outside the surface — an unknown name, or a sibling-
shape name binding a second state, a payment verdict, or checkout
interception — receives the byte-identical NO_SUCH_TOOL refusal:
the sibling shape does not exist here (BK-C3).

Transports share one dispatch. Content-free mode: a tools/call with
{"_content_free": true} is refused before dispatch (P1 pattern).
HTTP face: bearer token from ECLIPSE_BASKETSEAL_HTTP_TOKEN when set;
GET /health is the identity surface and carries no record data.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import basketseal
from basketseal import BasketsealError, BasketsealService
import licence as licence_mod

PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {
        "name": "basketseal_seal_basket",
        "title": "Seal a basket and recompute its total",
        "description": "Seal one checkout basket exactly as presented "
                       "(with its first-party capture record) and "
                       "recompute the charged total from the sealed "
                       "components under the basket's own rounding "
                       "discipline. Verdict: RECOMPUTES, MISCOMPUTES "
                       "(per-component diff class + amount), or "
                       "UNWITNESSED when no first-party capture record "
                       "is present. Verdict issuance is the metered "
                       "service and operates under a valid licence; "
                       "intake sealing itself is never gated.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "basket": {"type": "object"},
                "capture": {"type": "object"},
            },
            "required": ["basket"],
        },
    },
    {
        "name": "basketseal_get_record",
        "title": "Read a sealed basket record",
        "description": "Return the full sealed record: components as "
                       "sealed, the recomputation, the tolerance "
                       "applied, the verdict, and the record state.",
        "inputSchema": {
            "type": "object",
            "properties": {"record_id": {"type": "string"}},
            "required": ["record_id"],
        },
    },
    {
        "name": "basketseal_check",
        "title": "Check a record's verdict",
        "description": "Return only the verdict class and the "
                       "per-component diff summary for a sealed "
                       "record — never basket content.",
        "inputSchema": {
            "type": "object",
            "properties": {"record_id": {"type": "string"}},
            "required": ["record_id"],
        },
    },
    {
        "name": "basketseal_recompute",
        "title": "Recompute from an exported record (offline)",
        "description": "Recompute the verdict from an exported "
                       "record bundle alone. Runs with no service "
                       "state, is never metered and never licence-"
                       "gated; any verifier can run it.",
        "inputSchema": {
            "type": "object",
            "properties": {"export": {"type": "object"}},
            "required": ["export"],
        },
    },
    {
        "name": "basketseal_export_record",
        "title": "Export a sealed record bundle",
        "description": "Export a sealed record as a portable bundle "
                       "(canonical form, digest, verdict, discipline "
                       "version) together with the receipt chain head, "
                       "for offline recomputation anywhere.",
        "inputSchema": {
            "type": "object",
            "properties": {"record_id": {"type": "string"}},
            "required": ["record_id"],
        },
    },
]

TOOL_NAMES = {t["name"] for t in TOOLS}

# Sibling-shape names (BK-C3 separation): shapes that bind a second
# state, a payment verdict, a view state, a surcharge rule, or
# checkout interception. They are refused byte-identically to any
# unknown name — the refusal does not confirm the shape exists
# anywhere; it states only that it is not a tool here.
DENYLIST = {
    "payseal_evaluate", "payseal_verify_payment", "invoiceseal_diff",
    "invoiceseal_compare", "cartseal_compare", "shelfseal_check_view",
    "trueprice_judge", "minseal_evaluate",
    "basketseal_evaluate_payment", "basketseal_verify_payment",
    "basketseal_block_checkout", "basketseal_reprice_basket",
    "basketseal_refund_decision", "basketseal_compare_baskets",
    "basketseal_check_view", "basketseal_judge_surcharge",
}

_service = None


def service():
    global _service
    if _service is None:
        _service = BasketsealService(licence_gate=licence_mod.gate_from_env())
    return _service


def _result(obj):
    return {"content": [{"type": "text",
                         "text": json.dumps(obj, indent=1,
                                            ensure_ascii=False)}]}


def _error(code, message):
    return {"content": [{"type": "text", "text": "%s: %s" % (code, message)}],
            "isError": True}


def _no_such_tool():
    return _error("NO_SUCH_TOOL",
                  "that tool is not part of the Basketseal surface; the "
                  "surface is the five basketseal_* tools of the "
                  "basket-arithmetic witness")


def dispatch(method, params):
    params = params or {}
    if method == "initialize":
        return {"protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": basketseal.SERVER_NAME,
                               "version": basketseal.TOOL_VERSION,
                               "title": "%s — %s" % (basketseal.PRODUCT_NAME,
                                                     basketseal.DESCRIPTOR)}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in TOOL_NAMES:
            return _no_such_tool()
        if args.get("_content_free") is True:
            return _error("CONTENT_FREE_REFUSED",
                          "content-free calls carry no basket and are "
                          "refused before dispatch; present the basket "
                          "as captured")
        try:
            return _result(_call(name, args))
        except BasketsealError as e:
            return _error(e.code, e.message)
        except Exception as e:  # never leak a stack to the surface
            return _error("INTERNAL", "internal error: %s" % type(e).__name__)
    return _error("METHOD_NOT_FOUND", "method not supported: %s" % method)


def _call(name, args):
    svc = service()
    if name == "basketseal_seal_basket":
        return svc.seal_basket(args.get("basket"), args.get("capture"))
    if name == "basketseal_get_record":
        return svc.get_record(args.get("record_id"))
    if name == "basketseal_check":
        return svc.check(args.get("record_id"))
    if name == "basketseal_recompute":
        bundle = args.get("export") or {}
        if isinstance(bundle, dict) and "bundle" in bundle:
            bundle = bundle["bundle"]
        return basketseal.recompute_export(bundle)
    if name == "basketseal_export_record":
        return svc.export_record(args.get("record_id"))
    return _no_such_tool()


# ---------------------------------------------------------------------
# stdio transport
# ---------------------------------------------------------------------

def serve_stdio():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in msg:  # notification: no response
            continue
        result = dispatch(msg.get("method"), msg.get("params"))
        if isinstance(result, dict) and "content" in result:
            payload = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        else:
            payload = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------

def serve_http(host, port):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    token = os.environ.get("ECLIPSE_BASKETSEAL_HTTP_TOKEN")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"ok": True,
                                 "product": basketseal.PRODUCT_NAME,
                                 "descriptor": basketseal.DESCRIPTOR,
                                 "server": basketseal.SERVER_NAME,
                                 "version": basketseal.TOOL_VERSION})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if token and self.headers.get("Authorization") != \
                    "Bearer " + token:
                self._send(401, {"error": "unauthorized"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                msg = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                self._send(400, {"error": "bad request"})
                return
            result = dispatch(msg.get("method"), msg.get("params"))
            self._send(200, {"jsonrpc": "2.0", "id": msg.get("id"),
                             "result": result})

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main():
    if "--http" in sys.argv:
        host = os.environ.get("ECLIPSE_BASKETSEAL_HTTP_HOST", "127.0.0.1")
        port = int(os.environ.get("ECLIPSE_BASKETSEAL_HTTP_PORT", "8798"))
        serve_http(host, port)
    else:
        serve_stdio()


if __name__ == "__main__":
    main()
