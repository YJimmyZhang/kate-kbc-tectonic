# Security: Kate notifications

Push notifications for a bank are a real attack surface. Below: what can go wrong, and what this code does about it. Each fix points to where it lives.

| # | Risk | What could happen | Our fix | Where |
|---|------|-------------------|---------|-------|
| 1 | **Lock-screen leak** | Anyone near the phone reads "Your salary went up" or "Congratulations on your baby". Salary, pregnancy, pension are sensitive data (GDPR). | Push text is generic and identical for everyone: *"You have a new suggestion."* Details only inside the app. | `push.py` `build_payload` |
| 2 | **Data passes through Apple** | Payload travels via APNs servers and sits in iOS notification storage. | Payload holds only an opaque random id (`rid`), no personal data. Test enforces it. | `push.py`, `test_push_contains_no_personal_data` |
| 3 | **Someone else taps it** | Unlocked phone on a table, colleague or child taps the banner. | Face ID / passcode before the suggestion loads. | `Views.swift` `RecommendationView.load` |
| 4 | **Guessing or stealing an id** | Attacker tries ids to read other customers' suggestions (IDOR). | 192-bit random id, expires in 7 days, only readable with the owner's session. Wrong owner, expired, or unknown all return the same 404. | `server.py` `get_recommendation` |
| 5 | **Malicious payload / phishing link** | A crafted push or deep link opens a fake login page. | App accepts only an id matching a strict regex. No URLs in pushes, ever. Kate never asks for codes. | `NotificationManager.swift` `didReceive` |
| 6 | **Fake "Kate" SMS or WhatsApp** | Scammers copy the style of Kate's messages. | Kate only speaks inside the KBC app, never links. The app itself warns: KBC never asks for card reader codes. | Product rule + home screen card |
| 7 | **Device-token hijack** | Attacker registers their phone for someone else's pushes. | Token registration needs a signed session; a token belongs to one customer; logout deletes it. | `server.py` `register_device`, `unregister_device` |
| 8 | **Leaked APNs key** | With the `.p8` key anyone can send pushes "as KBC". | Key read from environment / secret manager, never committed. `.gitignore` blocks `*.p8`. | `push.py` `_provider_token`, `.gitignore` |
| 9 | **Anyone can trigger pushes** | Spam or social engineering via the send endpoint. | Internal endpoint needs a secret key, constant-time compare. | `server.py` `internal_only` |
| 10 | **Notification spam** | Too many pushes: customers ignore or distrust them. | Max 2 per week per customer. Respect consent toggle. | `server.py` `trigger` |
| 11 | **Stolen session / MITM** | Traffic read or session reused. | HTTPS only (App Transport Security), 15-min signed sessions, token in Keychain (`WhenUnlockedThisDeviceOnly`), no disk cache. | `APIClient.swift` |
| 12 | **App switcher screenshot** | Balances visible in the multitasking view. | Privacy shield covers the app when not active. | `KateApp.swift` `PrivacyShield` |

## What we'd add in production
- Real KBC login (itsme / KBC Sign) instead of the demo session.
- Certificate pinning to KBC's API.
- Optional "rich preview" via a Notification Service Extension: the phone fetches and decrypts a personal preview itself, only if the customer opts in.
- Audit log of every push and every recommendation viewed (compliance, MiFID II suitability).
- Rate limiting and anomaly detection on the API.
