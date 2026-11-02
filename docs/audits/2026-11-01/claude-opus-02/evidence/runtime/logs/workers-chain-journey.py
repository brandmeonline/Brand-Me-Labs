"""Audit-only: friend decision -> close -> outbox -> Pub/Sub emulator -> lane ingress -> reward settlement,
through the canonical processes (events.worker, persona.ingress, persona.jobs). Stdlib only. Synthetic identities.

Usage: journey2.py <out.json>   (env: PY, PUBSUB_EMULATOR_HOST, TOPIC_PUBLIC/MEMBER_PRIVATE/RESTRICTED, LANE_SUB, WT, Spanner vars)
"""
import json, os, subprocess, sys, time, uuid, urllib.request, urllib.error, http.cookiejar

GW = "http://127.0.0.1:3001/api/v1"; ORIGIN = "http://localhost:3000"
steps = []; out = {"steps": steps, "processes": []}
def rec(name, ok, detail=""):
    steps.append({"name": name, "result": "passed" if ok else "failed", "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (" — " + detail if detail else ""), flush=True); return ok

class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar(); self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def req(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        h = {"Accept": "application/json"}; h.update({"Content-Type": "application/json"} if data is not None else {}); h.update(headers or {})
        try:
            with self.opener.open(urllib.request.Request(GW + path, data=data, method=method, headers=h), timeout=20) as r:
                raw = r.read(); return r.status, dict(r.headers), (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try: p = json.loads(raw)
            except Exception: p = raw[:200].decode(errors="replace")
            return e.code, dict(e.headers), p
    def csrf(self):
        s, _, b = self.req("GET", "/session"); return b["csrf_token"] if s == 200 else ""
    def command(self, path, body=None, method="POST", extra=None):
        h = {"Origin": ORIGIN, "X-CSRF-Token": self.csrf()}; h.update(extra or {}); return self.req(method, path, body, h)

def session(name):
    c = Client(); s, h, b = c.req("POST", "/session/dev", {"test_identity": name}, {"Origin": ORIGIN})
    assert s == 201, (s, b); return c, b["member_id"]

alice, alice_id = session("audit-alice-w"); bob, bob_id = session("audit-bob-w")
rec("two dev sessions", alice_id != bob_id, f"alice {alice_id[:8]}… bob {bob_id[:8]}…")

s, _, b = alice.command("/wardrobe/items", {"source": "manual", "title": "Audit decision jacket", "category": "outerwear"}, extra={"Idempotency-Key": str(uuid.uuid4())})
item = (b.get("items") or [b])[0] if isinstance(b, dict) else {}
item_id = item.get("id"); rec("alice adds a wardrobe item", s == 201 and bool(item_id), f"HTTP {s}")

s, _, b = alice.command("/relationships", {"target_member_id": bob_id})
rel_id = (b or {}).get("id") or (b or {}).get("relationship_id") if isinstance(b, dict) else None
rec("alice invites bob", s == 201 and bool(rel_id), f"HTTP {s}, keys {sorted(b.keys())[:8] if isinstance(b, dict) else b}")
s, _, b = bob.command(f"/relationships/{rel_id}/accept")
rec("bob accepts", s == 200, f"HTTP {s}, state {(b or {}).get('state') if isinstance(b, dict) else b}")

body = {"subject_type": "wardrobe_item", "subject_id": item_id, "prompt": "Audit: wear this tonight?", "recipient_ids": [bob_id],
        "duration_seconds": 300, "discussion_mode": "blind_until_response"}
s, _, b = alice.command("/decisions", body, extra={"Idempotency-Key": str(uuid.uuid4())})
dec = b if isinstance(b, dict) else {}; dec_id = dec.get("id") or dec.get("decision_id")
rec("alice creates a five-minute decision", s == 201 and bool(dec_id), f"HTTP {s}, state {dec.get('state')}")
if dec.get("state") == "draft":
    s, _, b = alice.command(f"/decisions/{dec_id}/open"); dec = b if isinstance(b, dict) else dec
    rec("draft opened", s == 200 and dec.get("state") == "open", f"HTTP {s}")
s, _, d = alice.req("GET", f"/decisions/{dec_id}")
try:
    from datetime import datetime
    span = (datetime.fromisoformat(d["closes_at"].replace("Z", "+00:00")) - datetime.fromisoformat(d["opened_at"].replace("Z", "+00:00"))).total_seconds()
except Exception: span = None
rec("decision is open with a 300 s server deadline", s == 200 and d.get("state") == "open" and span == 300, f"HTTP {s}, span {span}")

s, _, b = bob.command(f"/decisions/{dec_id}/responses", {"choice": "pass"})
rec("bob responds 'pass'", s == 200, f"HTTP {s}")
s, _, b = alice.command(f"/decisions/{dec_id}/close")
rec("alice closes early; result pass=1", s == 200 and (b or {}).get("state") == "closed" and ((b or {}).get("result") or {}).get("pass") == 1,
    f"HTTP {s}, state {(b or {}).get('state')}, result {(b or {}).get('result')}")

s, _, b = bob.req("GET", "/rewards"); before = ((b or {}).get("account") or {}).get("available")
rec("bob's rewards before any worker runs", s == 200 and before == 0, f"available {before}")

# ---- canonical worker processes ----
env = dict(os.environ); PY = env["PY"]; WT = env["WT"]
env.update({"ENVIRONMENT": "development", "BRANDME_MODE": "development", "LANE_PUBSUB_SUBSCRIPTION": env["LANE_SUB"],
            "OUTBOX_PUBSUB_TOPIC_PUBLIC": env["TOPIC_PUBLIC"], "OUTBOX_PUBSUB_TOPIC_MEMBER_PRIVATE": env["TOPIC_MEMBERS"],
            "OUTBOX_PUBSUB_TOPIC_RESTRICTED": env["TOPIC_RESTRICTED"], "PYTHONPATH": WT})
def run(mod, *args):
    r = subprocess.run([PY, "-m", mod, *args], env=env, cwd=WT, capture_output=True, text=True, timeout=180)
    tail = (r.stdout.strip().splitlines() or [""])[-1][:300]; err = (r.stderr.strip().splitlines() or [""])[-1][:200]
    out["processes"].append({"module": mod, "args": list(args), "exit": r.returncode, "stdout_tail": tail, "stderr_tail": err}); return r.returncode, tail, err

rc, t, e = run("brandme_core.events.worker", "--check"); rec("events.worker --check (schema, config, topics)", rc == 0, f"exit {rc}: {t or e}")
rc, t, e = run("brandme_core.events.worker", "--once"); rec("events.worker --once publishes pending outbox rows to Pub/Sub", rc == 0, f"exit {rc}: {t or e}")
applied = []
for i in range(6):
    rc, t, e = run("brandme_core.domains.persona.ingress", "--once"); applied.append(t)
    if rc != 0 or '"applied"' not in t or t.strip().endswith('"applied"}'): pass
rec("persona.ingress --once consumes lane events (x6)", all(p["exit"] == 0 for p in out["processes"][-6:]), " | ".join(a[:80] for a in applied[:3]))
rc, t, e = run("brandme_core.domains.persona.jobs", "--once"); rec("persona.jobs --once (close_due / expire_due) runs", rc == 0, f"exit {rc}: {t or e}")

s, _, b = bob.req("GET", "/rewards"); after = ((b or {}).get("account") or {}).get("available")
rec("bob's reward settled through worker -> Pub/Sub -> ingress (friend_decision_response = 10 points)", s == 200 and after == 10, f"available {after}, account {(b or {}).get('account')}")
s, _, b = alice.req("GET", "/rewards"); rec("alice's rewards readable after settlement (no rule credits the asker)", s == 200, f"available {((b or {}).get('account') or {}).get('available')}")
s, _, b = bob.req("GET", "/notifications?limit=24"); unread = [n for n in (b or {}).get("items", []) if not n.get("read_at")] if isinstance(b, dict) else []
rec("bob has in-app notifications from the decision flow", s == 200 and len(unread) > 0, f"unread {len(unread)}")
s, _, b = alice.command("/blocks", {"target_member_id": bob_id}); rec("alice blocks bob", s in (200, 201), f"HTTP {s}")
s, _, b = bob.req("GET", f"/decisions/{dec_id}"); rec("after the block bob can no longer read the decision", s == 404, f"HTTP {s}")
for c in (alice, bob): c.command("/session", None, method="DELETE")
out.update({"passed": sum(1 for x in steps if x["result"] == "passed"), "failed": sum(1 for x in steps if x["result"] == "failed"), "decision_id": dec_id})
json.dump(out, open(sys.argv[1], "w"), indent=2); print(f"SUMMARY passed={out['passed']} failed={out['failed']}")
sys.exit(1 if out["failed"] else 0)
