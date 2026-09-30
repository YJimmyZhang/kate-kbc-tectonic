"""Run: cd backend && pytest -q"""
import os

os.environ["INTERNAL_KEY"] = "test-internal-key"
os.environ["SESSION_SECRET"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from kate_engine import DEMO_CUSTOMERS, recommend, understand  # noqa: E402
from push import GENERIC_BODY, build_payload  # noqa: E402

client = TestClient(server.app)
TOKEN = "a" * 64
INTERNAL = {"X-Internal-Key": "test-internal-key"}


def login(cid):
    return {"Authorization": f"Bearer {client.post(f'/v1/demo/login/{cid}').json()['token']}"}


def setup_function():
    server.devices.clear(); server.recs.clear(); server.push_log.clear()


# ---------------- engine
def test_each_customer_gets_expected_pathway():
    expected = {"lotte": "equity", "ahmed": "equity", "marc": "equity", "anna": "gov"}
    for cid, key in expected.items():
        assert recommend(DEMO_CUSTOMERS[cid])[0].pathway.key == key


def test_never_recommends_above_risk_limit():
    for c in DEMO_CUSTOMERS.values():
        limit = understand(c).max_sri
        for r in recommend(c):
            assert r.pathway.risk is None or r.pathway.risk <= limit


def test_no_consent_no_recommendation():
    c = DEMO_CUSTOMERS["lotte"]
    c.personalised = False
    try:
        assert recommend(c) == []
    finally:
        c.personalised = True


# ---------------- push payload
def test_push_contains_no_personal_data():
    text = str(build_payload("x" * 32)).lower()
    for leak in ["salary", "raise", "euro", "child", "pension", "lotte", "bonus"]:
        assert leak not in text
    assert build_payload("r")["aps"]["alert"]["body"] == GENERIC_BODY


# ---------------- API security
def test_full_flow():
    h = login("lotte")
    assert client.post("/v1/devices", json={"device_token": TOKEN}, headers=h).status_code == 200
    assert client.post("/v1/internal/trigger/lotte", headers=INTERNAL).json()["sent"]
    rid = next(iter(server.recs))
    r = client.get(f"/v1/recommendations/{rid}", headers=h)
    assert r.status_code == 200 and r.json()["pathway"]["name"] == "Global equities"


def test_other_customer_cannot_read_recommendation():
    client.post("/v1/devices", json={"device_token": TOKEN}, headers=login("lotte"))
    client.post("/v1/internal/trigger/lotte", headers=INTERNAL)
    rid = next(iter(server.recs))
    assert client.get(f"/v1/recommendations/{rid}", headers=login("marc")).status_code == 404


def test_no_or_forged_session_rejected():
    assert client.get("/v1/recommendations/abc").status_code == 401
    forged = {"Authorization": "Bearer lotte.9999999999.fakesig"}
    assert client.post("/v1/devices", json={"device_token": TOKEN}, headers=forged).status_code == 401


def test_trigger_needs_internal_key():
    assert client.post("/v1/internal/trigger/lotte").status_code == 403
    assert client.post("/v1/internal/trigger/lotte", headers={"X-Internal-Key": "guess"}).status_code == 403


def test_invalid_device_token_rejected():
    r = client.post("/v1/devices", json={"device_token": "<script>"}, headers=login("lotte"))
    assert r.status_code == 422


def test_weekly_push_limit():
    client.post("/v1/devices", json={"device_token": TOKEN}, headers=login("lotte"))
    sent = [client.post("/v1/internal/trigger/lotte", headers=INTERNAL).json()["sent"] for _ in range(4)]
    assert sent == [True, True, False, False]


def test_logout_stops_pushes():
    h = login("lotte")
    client.post("/v1/devices", json={"device_token": TOKEN}, headers=h)
    client.delete("/v1/devices", headers=h)
    assert client.post("/v1/internal/trigger/lotte", headers=INTERNAL).json()["sent"] is False
