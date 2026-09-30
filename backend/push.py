"""
Sending Kate's notification to iOS through Apple Push Notification service (APNs).

SECURITY DESIGN (see SECURITY.md):
  * The push carries NO personal data. No amounts, no life events, no names.
    Lock screens are visible to anyone, and the payload passes through Apple.
  * It carries only an opaque, random, expiring recommendation id ("rid").
    The app fetches the real content over an authenticated HTTPS call.
  * The APNs signing key (.p8) is read from an environment variable / secret
    manager, never from the repository.
"""
from __future__ import annotations

import json
import os
import time

APNS_HOST = os.environ.get("APNS_HOST", "https://api.sandbox.push.apple.com")
BUNDLE_ID = os.environ.get("APNS_BUNDLE_ID", "be.kbc.kate.demo")

# Generic, identical for every customer: reveals nothing on a lock screen.
GENERIC_TITLE = "Kate"
GENERIC_BODY = "You have a new suggestion. Open the app to view it."


def build_payload(rid: str) -> dict:
    """The only thing that ever leaves KBC's servers in a push."""
    return {
        "aps": {
            "alert": {"title": GENERIC_TITLE, "body": GENERIC_BODY},
            "sound": "default",
            "category": "KATE_SUGGESTION",   # registered in the app; no action runs without unlock
            "thread-id": "kate",
        },
        "rid": rid,                          # opaque pointer, useless without a logged-in session
    }


def _provider_token() -> str:
    """Short-lived ES256 JWT that proves to Apple the push comes from KBC."""
    import jwt  # PyJWT

    key = os.environ["APNS_AUTH_KEY"]        # contents of the .p8, injected from a secret store
    return jwt.encode(
        {"iss": os.environ["APNS_TEAM_ID"], "iat": int(time.time())},
        key,
        algorithm="ES256",
        headers={"kid": os.environ["APNS_KEY_ID"]},
    )


def send_push(device_token: str, rid: str, dry_run: bool | None = None) -> dict:
    """Send one push. Without APNs credentials it runs in dry-run mode for the demo."""
    payload = build_payload(rid)
    if dry_run is None:
        dry_run = "APNS_AUTH_KEY" not in os.environ
    if dry_run:
        print(f"[DRY RUN] APNs -> {device_token[:8]}...: {json.dumps(payload)}")
        return {"status": "dry-run", "payload": payload}

    import httpx

    with httpx.Client(http2=True, timeout=10) as client:   # APNs requires HTTP/2
        r = client.post(
            f"{APNS_HOST}/3/device/{device_token}",
            headers={
                "authorization": f"bearer {_provider_token()}",
                "apns-topic": BUNDLE_ID,
                "apns-push-type": "alert",
                "apns-priority": "5",                         # normal, not urgent
                "apns-expiration": str(int(time.time()) + 7 * 86400),
            },
            json=payload,
        )
    # 410 = token no longer valid (app deleted): caller must remove it.
    return {"status": r.status_code, "reason": r.text or "ok"}
