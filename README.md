# Kate: personal guidance for every KBC customer

Team Compass, Tectonic Hackathon 2026, KBC challenge.
Code that goes with our demo (`demo/index.html`). All customer data is synthetic.

## Architecture

```
 KBC data (income, events, products)
          │
          ▼
 ┌─────────────────────┐   life event    ┌──────────────────┐
 │ kate_engine.py      │ ──────────────► │ server.py        │
 │ signals → risk limit│                 │ stores rec + rid │
 │ → suitable pathway  │                 └────────┬─────────┘
 └─────────────────────┘                          │ push: generic text + rid only
                                                  ▼
                                           Apple APNs (push.py)
                                                  │
                                                  ▼
 ┌────────────────────────────────────────────────────────────┐
 │ iOS app: tap → Face ID → GET /v1/recommendations/{rid}      │
 │          → RecommendationView (pathway, risk scale, reasons)│
 └────────────────────────────────────────────────────────────┘
```

**Key idea:** the notification says only *"You have a new suggestion."* The personal content is fetched after unlock, over HTTPS, with the customer's own session. See [SECURITY.md](SECURITY.md).

## Files

| File | What it does |
|------|--------------|
| `backend/kate_engine.py` | Scoring engine: risk capacity, risk limit (lower of questionnaire and capacity), tone, next best action. Never suggests above the risk limit. |
| `backend/push.py` | Builds the APNs payload and sends it (JWT ES256, HTTP/2). Dry-run without keys. |
| `backend/server.py` | FastAPI: device registration, trigger, fetch recommendation. |
| `backend/test_kate.py` | 11 tests: engine logic + security rules. |
| `ios/KateApp/KateApp.swift` | App entry, push registration, privacy shield. |
| `ios/KateApp/NotificationManager.swift` | Permission, categories, tap handling, local demo notification. |
| `ios/KateApp/APIClient.swift` | HTTPS client, Keychain storage, model. |
| `ios/KateApp/Views.swift` | Home screen with Kate card, recommendation screen. |

## Run the backend

```bash
cd backend
pip install fastapi uvicorn httpx pyjwt cryptography pytest
pytest -q                       # 11 passed
INTERNAL_KEY=dev uvicorn server:app --reload
```

Try it:
```bash
TOKEN=$(curl -s -X POST localhost:8000/v1/demo/login/lotte | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -X POST localhost:8000/v1/devices -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d "{\"device_token\":\"$(printf 'a%.0s' {1..64})\"}"
curl -X POST localhost:8000/v1/internal/trigger/lotte -H "X-Internal-Key: dev"
# console prints the (generic) push payload with its rid
curl localhost:8000/v1/recommendations/<rid> -H "Authorization: Bearer $TOKEN"
```

## Run the iOS app

1. Xcode 15+, new iOS App project (SwiftUI, iOS 17), name `KateApp`.
2. Replace the generated files with the four files in `ios/KateApp/`.
3. Signing & Capabilities → add **Push Notifications**.
4. Info.plist → add `NSFaceIDUsageDescription` = "Protects your personal suggestions."
5. Run on a device or simulator. Tap **Allow notifications**, then **Send demo notification** and lock the screen.
   The demo uses a local notification with the exact server payload, so no Apple Developer push key is needed.

Real pushes: create an APNs key (.p8) in the Apple Developer portal and set
`APNS_AUTH_KEY`, `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID`.
