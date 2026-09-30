"""
Kate backend API (FastAPI). Run:  uvicorn server:app --reload

Endpoints
  POST   /v1/demo/login/{customer_id}  demo only: returns a session token
  POST   /v1/devices                   app registers its APNs device token
  DELETE /v1/devices                   logout: remove the device token
  POST   /v1/internal/trigger/{cid}    life event detected -> compute + push
  GET    /v1/recommendations/{rid}     app fetches the content behind a push

Storage is in memory for the hackathon. In production: KBC's database,
KBC's real login (itsme / card reader), and a secret manager.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time

from fastapi import Depends, FastAPI, Header, HTTPException

from kate_engine import DEMO_CUSTOMERS, recommend
from push import send_push

app = FastAPI(title="Kate API (hackathon prototype)")

SESSION_SECRET = os.environ.get("SESSION_SECRET", secrets.token_bytes(32).hex()).encode()
INTERNAL_KEY = os.environ.get("INTERNAL_KEY", secrets.token_urlsafe(32))
DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"

SESSION_TTL = 15 * 60               # banking sessions are short
REC_TTL = 7 * 86400                 # a push link dies after 7 days
MAX_PUSH_PER_WEEK = 2               # anti-spam, and pushes that stay rare feel trustworthy

DEVICE_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")      # APNs token: 32 bytes as hex
RID_RE = re.compile(r"^[A-Za-z0-9_-]{22,64}$")

devices: dict[str, str] = {}                        # customer_id -> device token
recs: dict[str, dict] = {}                          # rid -> {customer, rec, expires}
push_log: dict[str, list[float]] = {}               # customer_id -> send times


# ---------------------------------------------------------------- sessions
def _sign(msg: str) -> str:
    mac = hmac.new(SESSION_SECRET, msg.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def issue_session(customer_id: str) -> str:
    msg = f"{customer_id}.{int(time.time()) + SESSION_TTL}"
    return f"{msg}.{_sign(msg)}"


def current_customer(authorization: str = Header(default="")) -> str:
    """Every customer endpoint requires a valid, unexpired, signed session."""
    try:
        scheme, token = authorization.split(" ", 1)
        cid, exp, sig = token.rsplit(".", 2)
    except ValueError:
        raise HTTPException(401, "Not authenticated")
    if scheme.lower() != "bearer" or not hmac.compare_digest(sig, _sign(f"{cid}.{exp}")):
        raise HTTPException(401, "Not authenticated")
    if int(exp) < time.time() or cid not in DEMO_CUSTOMERS:
        raise HTTPException(401, "Session expired")
    return cid


def internal_only(x_internal_key: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_internal_key, INTERNAL_KEY):
        raise HTTPException(403, "Forbidden")


# ---------------------------------------------------------------- endpoints
@app.post("/v1/demo/login/{customer_id}")
def demo_login(customer_id: str):
    if not DEMO_MODE or customer_id not in DEMO_CUSTOMERS:
        raise HTTPException(404, "Not found")
    return {"token": issue_session(customer_id), "expires_in": SESSION_TTL}


@app.post("/v1/devices")
def register_device(body: dict, cid: str = Depends(current_customer)):
    token = str(body.get("device_token", "")).lower()
    if not DEVICE_TOKEN_RE.fullmatch(token):
        raise HTTPException(422, "Invalid device token")
    # A token belongs to one customer only: re-registering moves it.
    for other, t in list(devices.items()):
        if t == token and other != cid:
            del devices[other]
    devices[cid] = token
    return {"ok": True}


@app.delete("/v1/devices")
def unregister_device(cid: str = Depends(current_customer)):
    devices.pop(cid, None)          # after logout, no more pushes to this phone
    return {"ok": True}


@app.post("/v1/internal/trigger/{customer_id}", dependencies=[Depends(internal_only)])
def trigger(customer_id: str):
    customer = DEMO_CUSTOMERS.get(customer_id)
    if customer is None:
        raise HTTPException(404, "Unknown customer")
    if not customer.personalised:
        return {"sent": False, "reason": "No consent for personalised suggestions"}
    if customer_id not in devices:
        return {"sent": False, "reason": "No registered device"}

    now = time.time()
    recent = [t for t in push_log.get(customer_id, []) if now - t < 7 * 86400]
    if len(recent) >= MAX_PUSH_PER_WEEK:
        return {"sent": False, "reason": "Weekly push limit reached"}

    top = recommend(customer)
    if not top:
        return {"sent": False, "reason": "No suitable suggestion"}

    rid = secrets.token_urlsafe(24)                 # unguessable, 192 bits
    recs[rid] = {"customer": customer_id, "rec": top[0], "expires": now + REC_TTL}
    push_log[customer_id] = recent + [now]
    result = send_push(devices[customer_id], rid)
    return {"sent": True, "apns": result["status"]}


@app.get("/v1/recommendations/{rid}")
def get_recommendation(rid: str, cid: str = Depends(current_customer)):
    entry = recs.get(rid) if RID_RE.fullmatch(rid) else None
    # Same 404 for "doesn't exist", "expired" and "not yours": leaks nothing.
    if entry is None or entry["customer"] != cid or entry["expires"] < time.time():
        raise HTTPException(404, "Not found")
    r = entry["rec"]
    return {
        "pathway": {"number": r.pathway.n, "name": r.pathway.name, "product": r.pathway.product,
                    "risk": r.pathway.risk, "keep_in_mind": r.pathway.boundary},
        "title": r.title, "body": r.body, "cta": r.cta,
        "reasons": r.reasons, "tone": r.tone, "risk_limit": r.max_sri,
    }
