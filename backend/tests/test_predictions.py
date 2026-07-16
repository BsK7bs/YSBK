"""Tests for AI Prediction module.

Covers:
* GET /api/devices/{id}/predictions   (six failure types + schema)
* GET /api/devices/{id}/predictions/{failure_type} (single + 400 unknown)
* GET /api/devices/{id}/predictions/timeline (range + failure_type filter, growth)
* Failing telemetry -> high/critical severity for all six
* Nominal telemetry -> info/low severity (<20%)
* Auth required (401/403)
* Cross-org isolation (404/403)
"""
import os
import time
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

FAILURE_TYPES = ["ssd", "fan", "cpu_thermal", "battery", "memory", "network"]


# ---------- helpers ----------

def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _enroll_device(token, label="pred-test"):
    r = requests.post(f"{API}/enrollment/codes", json={"label": label}, headers=_headers(token))
    assert r.status_code in (200, 201), r.text
    code = r.json()["code"]
    r2 = requests.post(f"{API}/enrollment/enroll", json={
        "code": code,
        "hostname": f"pred-{uuid.uuid4().hex[:6]}",
        "os": "linux",
    })
    assert r2.status_code in (200, 201), r2.text
    return r2.json()["device_id"]


FAILING_METRICS = {
    "cpu_temp_c": 98,
    "cpu_percent": 92,
    "thermal_throttling": True,
    "ram_percent": 94,
    "memory_leak_detected": True,
    "ecc_errors": 8,
    "swap_percent": 55,
    "disk_percent": 88,
    "ssd_health_percent": 45,
    "smart": [{
        "assessment": "FAIL",
        "reallocated_sectors": 120,
        "pending_sectors": 40,
    }],
    "fans": [{"rpm": 0, "status": "failed"}],
    "battery": {
        "health_percent": 42,
        "cycle_count": 1200,
        "design_capacity": 5000,
        "full_charge_capacity": 2000,
    },
    "adapters": [{"name": "eth0", "is_up": False}],
    "latency_ms": 850,
    "packet_loss_percent": 12,
    "network_errors": 40,
}

NOMINAL_METRICS = {}  # empty -> all defaults


def _set_metrics(device_id, metrics):
    client = MongoClient(MONGO_URL)
    client[DB_NAME].devices.update_one(
        {"id": device_id}, {"$set": {"latest_metrics": metrics}}
    )
    client.close()


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def failing_device(admin_token):
    dev_id = _enroll_device(admin_token, label="pred-failing")
    _set_metrics(dev_id, FAILING_METRICS)
    yield dev_id


@pytest.fixture(scope="module")
def nominal_device(admin_token):
    dev_id = _enroll_device(admin_token, label="pred-nominal")
    _set_metrics(dev_id, NOMINAL_METRICS)
    yield dev_id


@pytest.fixture(scope="module")
def other_org_token():
    email = f"pred_other_{uuid.uuid4().hex[:6]}@example.com"
    pw = "Passw0rd!23"
    r = requests.post(f"{API}/auth/signup", json={
        "email": email, "password": pw,
        "organization_name": "PredTestOrg",
        "full_name": "Pred Tester",
    })
    assert r.status_code in (200, 201), r.text
    return _login(email, pw)


# ---------- schema + basic ----------

class TestPredictionsSchema:
    def test_get_predictions_shape(self, admin_token, failing_device):
        r = requests.get(f"{API}/devices/{failing_device}/predictions",
                         headers=_headers(admin_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["engine_version"] == "prediction-v1-hybrid"
        assert "ts" in body and isinstance(body["ts"], str) and "T" in body["ts"]
        assert body["device_id"] == failing_device
        preds = body["predictions"]
        assert isinstance(preds, list) and len(preds) == 6
        got_types = [p["failure_type"] for p in preds]
        assert sorted(got_types) == sorted(FAILURE_TYPES)
        for p in preds:
            for k in [
                "probability_percent", "confidence_percent", "severity",
                "reason", "recommendation", "features",
                "model_probability_percent", "rule_probability_percent",
            ]:
                assert k in p, f"missing {k} in {p}"
            assert 0 <= p["probability_percent"] <= 100
            assert 0 <= p["confidence_percent"] <= 100
            assert p["severity"] in ("info", "low", "medium", "high", "critical")

    @pytest.mark.parametrize("ft", ["ssd", "fan", "network"])
    def test_get_single_prediction(self, admin_token, failing_device, ft):
        r = requests.get(f"{API}/devices/{failing_device}/predictions/{ft}",
                         headers=_headers(admin_token))
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["failure_type"] == ft
        assert b["engine_version"] == "prediction-v1-hybrid"
        assert "probability_percent" in b and "confidence_percent" in b
        assert "reason" in b and "recommendation" in b
        assert "model_probability_percent" in b and "rule_probability_percent" in b

    def test_unknown_failure_type_400(self, admin_token, failing_device):
        r = requests.get(f"{API}/devices/{failing_device}/predictions/unknown_type",
                         headers=_headers(admin_token))
        assert r.status_code == 400


# ---------- timeline growth + filter ----------

class TestTimeline:
    def test_timeline_grows_and_filters(self, admin_token, failing_device):
        # Baseline
        r0 = requests.get(f"{API}/devices/{failing_device}/predictions/timeline",
                          headers=_headers(admin_token), params={"range": "24h"})
        assert r0.status_code == 200, r0.text
        c0 = r0.json()["count"]

        # Two more calls to /predictions -> two new snapshots
        for _ in range(2):
            requests.get(f"{API}/devices/{failing_device}/predictions",
                         headers=_headers(admin_token))
        time.sleep(0.3)
        r1 = requests.get(f"{API}/devices/{failing_device}/predictions/timeline",
                          headers=_headers(admin_token), params={"range": "24h"})
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1["count"] >= c0 + 2, f"expected >{c0+2} got {b1['count']}"
        assert isinstance(b1["items"], list) and len(b1["items"]) == b1["count"]

        # Filter by failure_type=ssd
        rf = requests.get(f"{API}/devices/{failing_device}/predictions/timeline",
                          headers=_headers(admin_token),
                          params={"range": "24h", "failure_type": "ssd"})
        assert rf.status_code == 200
        bf = rf.json()
        assert bf["failure_type"] == "ssd"
        assert bf["count"] >= 1
        for item in bf["items"]:
            assert item["failure_type"] == "ssd"
            assert "probability_percent" in item


# ---------- severity behaviour ----------

class TestSeverityBehaviour:
    def test_failing_telemetry_high_severity(self, admin_token, failing_device):
        # re-inject in case earlier tests overwrote
        _set_metrics(failing_device, FAILING_METRICS)
        r = requests.get(f"{API}/devices/{failing_device}/predictions",
                         headers=_headers(admin_token))
        assert r.status_code == 200
        preds = {p["failure_type"]: p for p in r.json()["predictions"]}
        problems = []
        for ft in FAILURE_TYPES:
            p = preds[ft]
            if p["severity"] not in ("high", "critical") or p["probability_percent"] < 70:
                problems.append((ft, p["severity"], p["probability_percent"], p["reason"]))
        assert not problems, f"failing telemetry did not escalate: {problems}"
        # reason strings coherent
        assert "SMART" in preds["ssd"]["reason"] or "sectors" in preds["ssd"]["reason"].lower()
        assert "fan" in preds["fan"]["reason"].lower() or "rpm" in preds["fan"]["reason"].lower()
        assert "temperature" in preds["cpu_thermal"]["reason"].lower()
        assert "battery" in preds["battery"]["reason"].lower()
        assert "memory" in preds["memory"]["reason"].lower() or "leak" in preds["memory"]["reason"].lower() or "ecc" in preds["memory"]["reason"].lower() or "ram" in preds["memory"]["reason"].lower()
        assert "packet loss" in preds["network"]["reason"].lower() or "latency" in preds["network"]["reason"].lower() or "adapter" in preds["network"]["reason"].lower()

    def test_nominal_telemetry_low_severity(self, admin_token, nominal_device):
        _set_metrics(nominal_device, NOMINAL_METRICS)
        r = requests.get(f"{API}/devices/{nominal_device}/predictions",
                         headers=_headers(admin_token))
        assert r.status_code == 200
        preds = r.json()["predictions"]
        problems = [(p["failure_type"], p["severity"], p["probability_percent"])
                    for p in preds
                    if p["severity"] not in ("info", "low") or p["probability_percent"] >= 20]
        assert not problems, f"nominal telemetry triggered false alarms: {problems}"


# ---------- auth + isolation ----------

class TestAuthAndIsolation:
    def test_unauthenticated_forbidden(self, failing_device):
        r = requests.get(f"{API}/devices/{failing_device}/predictions")
        assert r.status_code in (401, 403), r.status_code

    def test_cross_org_isolation(self, other_org_token, failing_device):
        r = requests.get(f"{API}/devices/{failing_device}/predictions",
                         headers=_headers(other_org_token))
        assert r.status_code in (403, 404), r.status_code
        r2 = requests.get(f"{API}/devices/{failing_device}/predictions/ssd",
                          headers=_headers(other_org_token))
        assert r2.status_code in (403, 404)
        r3 = requests.get(f"{API}/devices/{failing_device}/predictions/timeline",
                          headers=_headers(other_org_token))
        assert r3.status_code in (403, 404)
