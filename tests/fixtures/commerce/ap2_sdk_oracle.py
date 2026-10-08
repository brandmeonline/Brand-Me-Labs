"""Cross-verification oracle. Runs ONLY under an interpreter that has the official AP2 SDK
(google-agentic-commerce/AP2 @ e1ea56d) installed; invoked by tests/test_commerce_ap2.py via
subprocess so the SDK's conflicting pins never enter the application environment.

stdin JSON:
  {"mode": "verify", "kind": "checkout"|"payment", "token": str, "public_jwk": {...}, "current_time": int}
      -> {"ok": true, "payload": {...}} | {"ok": false, "error": str}
  {"mode": "create", "kind": ..., "payload": {...}, "private_jwk": {...}}
      -> {"token": str}
"""

import json
import sys

from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.mandate import MandateClient
from jwcrypto.jwk import JWK

MODELS = {"checkout": CheckoutMandate, "payment": PaymentMandate}


def main() -> None:
    req = json.load(sys.stdin)
    client = MandateClient()
    model = MODELS[req["kind"]]
    if req["mode"] == "verify":
        try:
            m = client.verify(req["token"], JWK(**req["public_jwk"]), payload_type=model,
                              current_time=req.get("current_time"))
            print(json.dumps({"ok": True, "payload": m.mandate_payload.model_dump(exclude_none=True)}))
        except Exception as exc:  # report, do not crash
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}))
    else:
        token = client.create([model.model_validate(req["payload"])], JWK(**req["private_jwk"]))
        print(json.dumps({"token": token}))


if __name__ == "__main__":
    main()
