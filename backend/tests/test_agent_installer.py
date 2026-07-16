"""Backend tests for Agent Installer v3 (Windows PyInstaller EXE flow).

Covers:
  - GET /api/agent/installer/info (unavailable / available)
  - GET /api/agent/installer/download (503 when missing / 200 stream + code + audit)
  - GET /api/agent/installer/verify (400 malformed / 404 unknown / 200 unused)
  - Auth requirements (401 anonymous)
  - RBAC on /download (viewer 403; admin/owner 200)
  - Legacy endpoint removal (/api/installers/*, /api/agent/installer/bundle, requirements.txt)
"""

import os
import re
import uuid
import shutil
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://complete-zip-deploy.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "admin@digitaltwin.com"
ADMIN_PASSWORD = "ChangeMe!2026"

INSTALLER_PATH = Path("/app/dist/DigitalTwinAgentSetup.exe")
STUB_BYTES = b"MZ" + os.urandom(1024) + b"STUB-DIGITAL-TWIN-INSTALLER"

CODE_RE = re.compile(r"^DT-[A-Z0-9]{4}-[A-Z0-9]{4}$")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def admin_login():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("access_token"), f"no access_token in login body: {body}"
    return body


@pytest.fixture(scope="session")
def admin_token(admin_login):
    return admin_login["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def admin_me(admin_login):
    # login response includes user dict with org_id + email
    return admin_login["user"]


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture
def no_installer():
    """Ensure /app/dist has no EXE before the test."""
    if INSTALLER_PATH.exists():
        INSTALLER_PATH.unlink()
    yield
    if INSTALLER_PATH.exists():
        INSTALLER_PATH.unlink()


@pytest.fixture
def stub_installer():
    """Place a stub EXE at /app/dist/DigitalTwinAgentSetup.exe."""
    INSTALLER_PATH.parent.mkdir(parents=True, exist_ok=True)
    INSTALLER_PATH.write_bytes(STUB_BYTES)
    yield INSTALLER_PATH
    if INSTALLER_PATH.exists():
        INSTALLER_PATH.unlink()


@pytest.fixture(scope="session")
def viewer_user(admin_me, mongo_db):
    """Insert a viewer user directly in Mongo (same org as admin), return login token."""
    from datetime import datetime, timezone
    import bcrypt

    email = f"test_viewer_{uuid.uuid4().hex[:8]}@example.com"
    password = "ViewerPass!2026"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    user_id = str(uuid.uuid4())
    mongo_db.users.insert_one({
        "id": user_id,
        "org_id": admin_me["org_id"],
        "email": email,
        "full_name": "Test Viewer",
        "role": "viewer",
        "is_active": True,
        "password_hash": password_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    if login.status_code != 200:
        mongo_db.users.delete_one({"id": user_id})
        pytest.skip(f"viewer login failed: {login.status_code} {login.text}")
    token = login.json()["access_token"]
    yield {"email": email, "token": token, "id": user_id}
    mongo_db.users.delete_one({"id": user_id})


# ---------------------------------------------------------------------------
# /info
# ---------------------------------------------------------------------------
class TestInstallerInfo:
    def test_anonymous_rejected(self, no_installer):
        r = requests.get(f"{API}/agent/installer/info", timeout=10)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_info_unavailable(self, admin_headers, no_installer):
        r = requests.get(f"{API}/agent/installer/info", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["available"] is False
        assert isinstance(data.get("reason"), str) and len(data["reason"]) > 5
        assert data["size"] == 0
        assert data["sha256"] is None
        assert data["filename"] == "DigitalTwinAgentSetup.exe"

    def test_info_available_after_stub(self, admin_headers, stub_installer):
        r = requests.get(f"{API}/agent/installer/info", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["available"] is True
        assert data["size"] == len(STUB_BYTES)
        assert isinstance(data.get("sha256"), str) and len(data["sha256"]) == 64
        assert data.get("updated_at")
        assert data.get("version")


# ---------------------------------------------------------------------------
# /download
# ---------------------------------------------------------------------------
class TestInstallerDownload:
    def test_anonymous_rejected(self):
        r = requests.get(f"{API}/agent/installer/download", timeout=10)
        assert r.status_code in (401, 403)

    def test_download_unavailable_returns_503(self, admin_headers, no_installer):
        r = requests.get(f"{API}/agent/installer/download", headers=admin_headers, timeout=10)
        assert r.status_code == 503
        body = r.json()
        assert "detail" in body
        assert "not available" in body["detail"].lower() or "installer" in body["detail"].lower()

    def test_download_success_streams_file_and_creates_code(
        self, admin_headers, admin_me, stub_installer, mongo_db
    ):
        r = requests.get(
            f"{API}/agent/installer/download",
            headers=admin_headers,
            params={"label": "TEST_pytest_label"},
            timeout=30,
        )
        assert r.status_code == 200, f"download failed: {r.status_code} {r.text[:400]}"
        # Body streams the stub bytes
        assert r.content == STUB_BYTES
        # X-Pairing-Code header
        code = r.headers.get("X-Pairing-Code")
        assert code and CODE_RE.match(code), f"bad or missing X-Pairing-Code: {code}"
        # Content-Disposition includes the code in filename
        cd = r.headers.get("Content-Disposition", "")
        assert f"DigitalTwinAgentSetup_{code}.exe" in cd, f"bad Content-Disposition: {cd}"

        # Enrollment code doc exists in Mongo
        doc = mongo_db.enrollment_codes.find_one({"code": code})
        assert doc is not None, f"enrollment code {code} not persisted"
        assert doc["org_id"] == admin_me["org_id"]
        assert doc["used"] is False
        assert doc["created_by"] == admin_me["email"]
        assert doc["issued_via"] == "agent_installer_download"
        assert doc.get("expires_at")
        assert doc.get("label") == "TEST_pytest_label"

        # Cleanup persisted code
        mongo_db.enrollment_codes.delete_one({"code": code})

    def test_viewer_role_blocked(self, viewer_user, stub_installer):
        r = requests.get(
            f"{API}/agent/installer/download",
            headers={"Authorization": f"Bearer {viewer_user['token']}"},
            timeout=15,
        )
        assert r.status_code == 403, f"expected 403 for viewer, got {r.status_code} {r.text[:200]}"

    def test_admin_owner_role_allowed(self, admin_headers, stub_installer, mongo_db):
        r = requests.get(f"{API}/agent/installer/download", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        code = r.headers.get("X-Pairing-Code")
        assert code and CODE_RE.match(code)
        mongo_db.enrollment_codes.delete_one({"code": code})


# ---------------------------------------------------------------------------
# /verify
# ---------------------------------------------------------------------------
class TestInstallerVerify:
    def test_anonymous_rejected(self):
        r = requests.get(f"{API}/agent/installer/verify", params={"code": "DT-AAAA-BBBB"}, timeout=10)
        assert r.status_code in (401, 403)

    def test_malformed_code_400(self, admin_headers):
        r = requests.get(
            f"{API}/agent/installer/verify",
            headers=admin_headers,
            params={"code": "not-a-code"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_unknown_code_404(self, admin_headers):
        r = requests.get(
            f"{API}/agent/installer/verify",
            headers=admin_headers,
            params={"code": "DT-ZZZZ-9999"},
            timeout=10,
        )
        assert r.status_code == 404

    def test_freshly_minted_code_paired_false(self, admin_headers, stub_installer, mongo_db):
        # Mint a code via /download
        dl = requests.get(f"{API}/agent/installer/download", headers=admin_headers, timeout=15)
        assert dl.status_code == 200
        code = dl.headers.get("X-Pairing-Code")
        assert code

        r = requests.get(
            f"{API}/agent/installer/verify",
            headers=admin_headers,
            params={"code": code},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == code
        assert data["paired"] is False
        assert data.get("device") is None
        assert data.get("expires_at")

        mongo_db.enrollment_codes.delete_one({"code": code})


# ---------------------------------------------------------------------------
# Legacy endpoint removal
# ---------------------------------------------------------------------------
class TestLegacyRemoved:
    @pytest.mark.parametrize(
        "path",
        [
            "/agent/installer/bundle",
            "/agent/installer/requirements.txt",
            "/installers/tokens",
            "/installers/config",
            "/installers/download",
            "/installers/sidecar",
            "/installers/info",
            "/installer/download",
        ],
    )
    def test_legacy_endpoint_returns_404(self, admin_headers, path):
        r = requests.get(f"{API}{path}", headers=admin_headers, timeout=10)
        assert r.status_code == 404, f"{path} did not return 404 (got {r.status_code})"


# ---------------------------------------------------------------------------
# Backend still starts / imports clean
# ---------------------------------------------------------------------------
class TestBackendHealth:
    def test_health(self):
        r = requests.get(f"{API}/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_root(self):
        r = requests.get(f"{API}/", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
