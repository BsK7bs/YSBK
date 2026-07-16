"""Tests for GET /api/predictions/fleet/top-risk.

Covers:
* Response schema (count, total_devices, ts, engine_version, items[])
* Per-item shape: id/hostname/display_name/is_online/last_seen + worst + top_types
* limit param caps the result set + sorted DESC by worst.probability_percent
* min_probability filters low-risk devices out
* failure_type restricts ranking (unknown -> error payload)
* Auth required, cross-org isolation
* Injected failing device appears first with critical severity + >=90% prob
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "admin@digitaltwin.com"
ADMIN_PW = "ChangeMe!2026"

FAILING_METRICS = {
    "cpu_temp_c": 98, "cpu_percent": 92, "thermal_throttling": True,
    "ram_percent": 94, "memory_leak_detected": True, "ecc_errors": 8,
    "swap_percent": 55, "disk_percent": 88, "ssd_health_percent": 45,
    "smart": [{"assessment": "FAIL", "reallocated_sectors": 120, "pending_sectors": 40}],
    "fans": [{"rpm": 0, "status": "failed"}],
    "battery": {"health_percent": 42, "cycle_count": 1200,
                "design_capacity": 5000, "full_charge_capacity": 2000},
    "adapters": [{"name": "eth0", "is_up": False}],
    "latency_ms": 850, "packet_loss_percent": 12, "network_errors": 40,
}


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(t):
    return {"Authorization": f"Bearer {t}"}


def _enroll_device(token, label):
    r = requests.post(f"{API}/enrollment/codes", json={"label": label}, headers=_headers(token))
    assert r.status_code in (200, 201), r.text
    code = r.json()["code"]
    r2 = requests.post(f"{API}/enrollment/enroll", json={
        "code": code, "hostname": f"fleet-{uuid.uuid4().hex[:6]}", "os": "linux",
    })
    assert r2.status_code in (200, 201), r2.text
    return r2.json()["device_id"]


def _set_metrics(device_id, metrics):
    c = MongoClient(MONGO_URL)
    c[DB_NAME].devices.update_one({"id": device_id}, {"$set": {"latest_metrics": metrics}})
    c.close()


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def failing_device(admin_token):
    dev_id = _enroll_device(admin_token, "fleet-failing")
    _set_metrics(dev_id, FAILING_METRICS)
    yield dev_id


@pytest.fixture(scope="module")
def nominal_device(admin_token):
    dev_id = _enroll_device(admin_token, "fleet-nominal")
    _set_metrics(dev_id, {})
    yield dev_id


@pytest.fixture(scope="module")
def other_org_token():
    email = f"fleet_other_{uuid.uuid4().hex[:6]}@example.com"
    pw = "Passw0rd!23"
    r = requests.post(f"{API}/auth/signup", json={
        "email": email, "password": pw,
        "organization_name": "FleetTestOrg", "full_name": "Fleet Tester",
    })
    assert r.status_code in (200, 201), r.text
    return _login(email, pw)


# ---------- schema ----------

def test_schema_and_engine_version(admin_token, failing_device, nominal_device):
    r = requests.get(f"{API}/predictions/fleet/top-risk", headers=_headers(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("count", "total_devices", "ts", "engine_version", "items"):
        assert key in data
    assert data["engine_version"] == "prediction-v1-hybrid"
    assert isinstance(data["items"], list)
    assert data["total_devices"] >= 2
    assert data["count"] == len(data["items"])
    if data["items"]:
        it = data["items"][0]
        for k in ("id", "hostname", "display_name", "is_online", "last_seen", "worst", "top_types"):
            assert k in it, f"missing {k} in item"
        worst = it["worst"]
        for k in ("failure_type", "label", "probability_percent", "confidence_percent",
                  "severity", "reason", "recommendation"):
            assert k in worst, f"missing {k} in worst"
        assert isinstance(it["top_types"], list)
        assert len(it["top_types"]) <= 3
        # top_types sorted desc
        probs = [t["probability_percent"] for t in it["top_types"]]
        assert probs == sorted(probs, reverse=True)


def test_failing_device_ranked_first_critical(admin_token, failing_device, nominal_device):
    r = requests.get(f"{API}/predictions/fleet/top-risk", headers=_headers(admin_token))
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "expected at least one at-risk device"
    # sorted desc
    probs = [i["worst"]["probability_percent"] for i in items]
    assert probs == sorted(probs, reverse=True)
    # Our injected failing device must appear high on the list with critical severity.
    match = next((i for i in items if i["id"] == failing_device), None)
    assert match is not None, "failing device not present in ranked items"
    assert match["worst"]["severity"] == "critical"
    assert match["worst"]["probability_percent"] >= 90
    # First-ranked device overall must be critical + >=90 (there is a seeded failing device too).
    assert items[0]["worst"]["severity"] == "critical"
    assert items[0]["worst"]["probability_percent"] >= 90


def test_limit_param(admin_token, failing_device, nominal_device):
    r = requests.get(f"{API}/predictions/fleet/top-risk?limit=3", headers=_headers(admin_token))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) <= 3
    probs = [i["worst"]["probability_percent"] for i in items]
    assert probs == sorted(probs, reverse=True)


def test_min_probability_filter(admin_token, failing_device, nominal_device):
    r = requests.get(f"{API}/predictions/fleet/top-risk?min_probability=60",
                     headers=_headers(admin_token))
    assert r.status_code == 200
    items = r.json()["items"]
    for i in items:
        assert i["worst"]["probability_percent"] >= 60


def test_failure_type_filter_ssd(admin_token, failing_device):
    r = requests.get(f"{API}/predictions/fleet/top-risk?failure_type=ssd",
                     headers=_headers(admin_token))
    assert r.status_code == 200
    items = r.json()["items"]
    for i in items:
        assert i["worst"]["failure_type"] == "ssd"


def test_failure_type_unknown_returns_error(admin_token):
    r = requests.get(f"{API}/predictions/fleet/top-risk?failure_type=bogus",
                     headers=_headers(admin_token))
    # Backend returns 200 with error field (per current impl). Accept 400 too.
    if r.status_code == 200:
        assert r.json().get("error") == "unknown failure_type"
        assert r.json().get("items") == []
    else:
        assert r.status_code in (400, 422)


def test_auth_required():
    r = requests.get(f"{API}/predictions/fleet/top-risk")
    assert r.status_code in (401, 403)


def test_cross_org_isolation(admin_token, other_org_token, failing_device):
    r_admin = requests.get(f"{API}/predictions/fleet/top-risk", headers=_headers(admin_token))
    r_other = requests.get(f"{API}/predictions/fleet/top-risk", headers=_headers(other_org_token))
    assert r_admin.status_code == 200 and r_other.status_code == 200
    admin_ids = {i["id"] for i in r_admin.json()["items"]}
    other_ids = {i["id"] for i in r_other.json()["items"]}
    assert failing_device in admin_ids
    assert failing_device not in other_ids
    # Other org should have 0 devices
    assert r_other.json()["total_devices"] == 0
