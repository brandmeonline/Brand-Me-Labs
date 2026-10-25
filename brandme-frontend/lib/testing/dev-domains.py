"""Local emulator composition. No production mounts, mocks or seeded domain records."""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import threading
from pathlib import Path

if (os.environ.get("BRANDME_MODE") != "development" or os.environ.get("NODE_ENV") == "production"
        or os.environ.get("SPANNER_EMULATOR_HOST") != "127.0.0.1:9010"):
    raise RuntimeError("The local development composition requires the loopback Spanner emulator")
reference = Path(os.environ["BRANDME_DOMAIN_REFERENCE"]).resolve()
secret = os.environ["BRANDME_DEV_ASSERTION_KEY"].encode()
if len(secret) < 64:
    raise RuntimeError("A runtime assertion key is required")
sys.path.insert(0, str(reference))
sys.path.insert(0, str(reference / "tests"))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from test_persona_harness import emulator_up, new_migrated_database
from brandme_core.domains.persona.kernel import member_principal
from brandme_core.domains.persona.api import create_persona_router
from brandme_core.domains.persona.service import PersonaService
from brandme_core.domains.persona.onboarding import GuestMigrationService
from brandme_core.domains.wardrobe.api import create_wardrobe_router
from brandme_core.domains.wardrobe.service import WardrobeService
from brandme_core.domains.wardrobe.outfits import OutfitService
from brandme_core.domains.wardrobe import guest_sections
from brandme_core.domains.social.api import create_social_router
from brandme_core.domains.social.relationships import RelationshipService, friendship_proposal_policy
from brandme_core.domains.social.decisions import DecisionService
from brandme_core.domains.social.shares import ShareService
from brandme_core.domains.social.notifications import NotificationService
from brandme_core.domains.social.reports import ReportService
from brandme_core.domains.rewards.api import create_rewards_router
from brandme_core.domains.rewards.service import RewardsService
from brandme_core.domains.rewards.benefits import BenefitService
from brandme_core.domains.rewards.consumer import RewardsConsumer
from brandme_core.events.outbox import OutboxDispatcher

if not emulator_up():
    raise RuntimeError("Emulator unreachable: live journey verification cannot run")
database = new_migrated_database()
print(json.dumps({"database": database.database_id, "project": "consumer-domains-test", "instance": "consumer-domains"}), flush=True)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
nonces = {}

@app.middleware("http")
async def authenticated_relay(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    try:
        encoded, signature = request.headers.get("x-brandme-dev-assertion", "").split(".", 1)
        if len(encoded) > 4096 or not hmac.compare_digest(signature, hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()):
            raise ValueError()
        claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        now = time.time()
        if abs(now - claims["issued_at"]) > 30 or claims["method"] != request.method or claims["path"] != request.url.path:
            raise ValueError()
        for nonce, expiry in list(nonces.items()):
            if expiry < now:
                del nonces[nonce]
        if claims["nonce"] in nonces or len(nonces) > 10000:
            raise ValueError()
        nonces[claims["nonce"]] = now + 60
        request.state.principal = member_principal(claims["member_id"], claims["scopes"]) if claims["member_id"] else None
    except (ValueError, KeyError, TypeError):
        return JSONResponse({"code": "unauthenticated", "title": "Verified development relay required", "status": 401}, status_code=401)
    return await call_next(request)

def resolve_principal(request):
    return request.state.principal

@app.get("/health")
def health():
    with database.snapshot() as snapshot:
        list(snapshot.execute_sql("SELECT 1"))
    return {"status": "ok", "database": "spanner"}

persona = PersonaService(database)
app.include_router(create_persona_router(persona, GuestMigrationService(database, persona), resolve_principal))
app.include_router(create_wardrobe_router(WardrobeService(database), OutfitService(database, proposal_policy=friendship_proposal_policy), resolve_principal))
app.include_router(create_social_router(RelationshipService(database), DecisionService(database), ShareService(database),
                                      NotificationService(database), resolve_principal, ReportService(database)))
app.include_router(create_rewards_router(RewardsService(database), BenefitService(database), resolve_principal))
stop = threading.Event()
dispatcher = OutboxDispatcher(database, RewardsConsumer(database).handle)
def settle_rewards():
    while not stop.wait(0.5):
        dispatcher.run_once()
worker = threading.Thread(target=settle_rewards, daemon=True)
worker.start()
try:
    uvicorn.run(app, host="127.0.0.1", port=8011, access_log=False, log_level="warning")
finally:
    stop.set()
    worker.join(timeout=5)
    database.drop()
