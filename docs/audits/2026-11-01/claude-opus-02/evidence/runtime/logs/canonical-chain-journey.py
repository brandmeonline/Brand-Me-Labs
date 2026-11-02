"""Audit-only API journey through gateway -> consumer-domain service -> Spanner (synthetic identities).

Not part of the repository. Uses only the Python standard library. Records every step with HTTP status.
"""
import json, sys, time, uuid, urllib.request, urllib.error, http.cookiejar

GW = "http://127.0.0.1:3001/api/v1"
ORIGIN = "http://localhost:3000"
steps = []

def rec(name, ok, detail=""):
    steps.append({"name": name, "result": "passed" if ok else "failed", "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (" — " + detail if detail else ""), flush=True)
    return ok

class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def req(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        h = {"Accept": "application/json"}
        if data is not None: h["Content-Type"] = "application/json"
        h.update(headers or {})
        r = urllib.request.Request(GW + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(r, timeout=20) as resp:
                raw = resp.read()
                return resp.status, dict(resp.headers), (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try: parsed = json.loads(raw)
            except Exception: parsed = raw[:200].decode(errors="replace")
            return e.code, dict(e.headers), parsed
    def csrf(self):
        s, _, b = self.req("GET", "/session")
        return b["csrf_token"] if s == 200 else None
    def command(self, path, body=None, method="POST", extra=None):
        h = {"Origin": ORIGIN, "X-CSRF-Token": self.csrf() or ""}
        h.update(extra or {})
        return self.req(method, path, body, h)

anon = Client()
s, _, b = anon.req("GET", "/wardrobe/items")
rec("anonymous GET /wardrobe/items is refused", s == 401, f"HTTP {s}")

alice = Client()
s, h, b = alice.req("POST", "/session/dev", {"test_identity": "audit-alice"}, {"Origin": ORIGIN})
alice_id = b.get("member_id") if isinstance(b, dict) else None
rec("dev session (labelled simulation) for audit-alice", s == 201 and "Simulated" in h.get("X-Brandme-Simulation", "") and bool(alice_id),
    f"HTTP {s}, assurance {b.get('assurance_level') if isinstance(b, dict) else b}")

s, _, b = alice.req("GET", "/me")
rec("GET /me returns the member", s == 200 and b.get("member", {}).get("id") == alice_id, f"HTTP {s}")

s, _, b = alice.req("GET", "/me/persona")
rec("GET /me/persona through gateway -> consumer-domain service (ES256 assertion) -> Spanner", s == 200 and "profile" in (b or {}),
    f"HTTP {s}, keys {sorted((b or {}).keys())[:6] if isinstance(b, dict) else b}")
version0 = (b or {}).get("profile", {}).get("version") if isinstance(b, dict) else None

key = str(uuid.uuid4())
item_body = {"source": "manual", "title": "Audit linen jacket", "category": "outerwear"}
s, _, b = alice.command("/wardrobe/items", item_body, extra={"Idempotency-Key": key})
item = (b or {}).get("items", [{}])[0] if isinstance(b, dict) and "items" in b else (b if isinstance(b, dict) else {})
item_id = item.get("id")
rec("POST /wardrobe/items creates a self-reported item", s in (200, 201) and bool(item_id) and item.get("claim_level") == "self_reported",
    f"HTTP {s}, id {str(item_id)[:8]}…, claim_level {item.get('claim_level')}")

s2, _, b2 = alice.command("/wardrobe/items", item_body, extra={"Idempotency-Key": key})
item2 = (b2 or {}).get("items", [{}])[0] if isinstance(b2, dict) and "items" in b2 else (b2 if isinstance(b2, dict) else {})
rec("same Idempotency-Key replays the same item (no duplicate)", s2 in (200, 201) and item2.get("id") == item_id, f"HTTP {s2}")

s, _, b = alice.req("GET", "/wardrobe/items")
ids = [i.get("id") for i in (b or {}).get("items", [])] if isinstance(b, dict) else []
rec("GET /wardrobe/items lists exactly the created item", s == 200 and ids == [item_id], f"HTTP {s}, count {len(ids)}")

s, _, b = alice.req("GET", "/recommendations")
items = (b or {}).get("items") if isinstance(b, dict) else None
rec("GET /recommendations answers 200 with an EMPTY list (F-ARCH-003 at runtime)", s == 200 and isinstance(b, dict) and not items,
    f"HTTP {s}, items {len(items) if isinstance(items, list) else items}, keys {sorted(b.keys())[:6] if isinstance(b, dict) else b}")

s, _, b = alice.req("GET", "/rewards")
rec("GET /rewards answers 200 (new member)", s == 200, f"HTTP {s}, account {(b or {}).get('account') if isinstance(b, dict) else b}")

bob = Client()
s, _, b = bob.req("POST", "/session/dev", {"test_identity": "audit-bob"}, {"Origin": ORIGIN})
bob_id = b.get("member_id") if isinstance(b, dict) else None
rec("second dev session for audit-bob is a distinct member", s == 201 and bob_id and bob_id != alice_id, f"HTTP {s}")
s, _, b = bob.req("GET", f"/wardrobe/items/{item_id}")
rec("bob cannot read alice's item (account isolation)", s in (403, 404), f"HTTP {s}")
s, _, b = bob.req("GET", "/wardrobe/items")
rec("bob's wardrobe is empty", s == 200 and (b or {}).get("items") == [], f"HTTP {s}")

s, _, b = alice.req("POST", "/wardrobe/items", item_body, {"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())})
rec("command without X-CSRF-Token is refused", s in (401, 403), f"HTTP {s}")
s, _, b = alice.command("/wardrobe/items", item_body, extra={"Idempotency-Key": str(uuid.uuid4()), "Origin": "http://evil.example"})
rec("command from a foreign Origin is refused", s in (401, 403), f"HTTP {s}")

s, _, b = alice.command("/session", None, method="DELETE")
rec("DELETE /session signs out", s == 204, f"HTTP {s}")
s, _, b = alice.req("GET", "/me")
rec("after sign-out GET /me is 401", s == 401, f"HTTP {s}")

result = {"started": None, "gateway": GW, "steps": steps, "passed": sum(1 for x in steps if x["result"] == "passed"), "failed": sum(1 for x in steps if x["result"] == "failed")}
json.dump(result, open(sys.argv[1], "w"), indent=2)
print(f"SUMMARY passed={result['passed']} failed={result['failed']}")
sys.exit(1 if result["failed"] else 0)
