"""Test login fix - verify seeded admin account works.

Tests the specific bug fix where admin@digitaltwin.com login was failing.
"""
import asyncio
import sys
import httpx

# Public endpoint from frontend/.env
BASE = "https://safe-import-pro.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@digitaltwin.com"
ADMIN_PASSWORD = "ChangeMe!2026"


class TestResults:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_pass(self, test_name: str):
        self.total += 1
        self.passed += 1
        print(f"  ✓ {test_name}")

    def record_fail(self, test_name: str, error: str):
        self.total += 1
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"  ✗ {test_name}: {error}")

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"Test Results: {self.passed}/{self.total} passed")
        if self.failed > 0:
            print(f"\nFailed tests ({self.failed}):")
            for error in self.errors:
                print(f"  - {error}")
        print(f"{'='*60}\n")
        return 0 if self.failed == 0 else 1


results = TestResults()


async def test_login_with_correct_credentials(client: httpx.AsyncClient):
    """Test POST /api/auth/login with correct admin credentials"""
    print("\n▶ Testing login with correct credentials (admin@digitaltwin.com)")
    
    try:
        r = await client.post(
            f"{BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember_me": False},
            timeout=30
        )
        
        if r.status_code == 200:
            data = r.json()
            
            # Check for required fields
            if not data.get("access_token"):
                results.record_fail("Login response - access_token", "Missing access_token")
                return None
            
            if not data.get("refresh_token"):
                results.record_fail("Login response - refresh_token", "Missing refresh_token")
                return None
            
            if not data.get("user"):
                results.record_fail("Login response - user", "Missing user object")
                return None
            
            if not data.get("organization"):
                results.record_fail("Login response - organization", "Missing organization object")
                return None
            
            results.record_pass("POST /api/auth/login with correct credentials returns 200")
            results.record_pass("Response contains access_token, refresh_token, user, organization")
            
            # Verify user details
            user = data["user"]
            org = data["organization"]
            
            if user.get("email") == ADMIN_EMAIL:
                results.record_pass(f"User email matches: {ADMIN_EMAIL}")
            else:
                results.record_fail("User email", f"Expected {ADMIN_EMAIL}, got {user.get('email')}")
            
            if user.get("role") == "owner":
                results.record_pass("User role is 'owner'")
            else:
                results.record_fail("User role", f"Expected 'owner', got {user.get('role')}")
            
            if org.get("name") == "Platform Admin":
                results.record_pass("Organization name is 'Platform Admin'")
            else:
                results.record_fail("Organization name", f"Expected 'Platform Admin', got {org.get('name')}")
            
            return data
        else:
            results.record_fail(
                "POST /api/auth/login with correct credentials",
                f"Expected 200, got {r.status_code}: {r.text}"
            )
            return None
    except Exception as e:
        results.record_fail("POST /api/auth/login with correct credentials", str(e))
        return None


async def test_login_with_wrong_password(client: httpx.AsyncClient):
    """Test POST /api/auth/login with wrong password returns 401"""
    print("\n▶ Testing login with wrong password")
    
    try:
        r = await client.post(
            f"{BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": "WrongPassword123!", "remember_me": False},
            timeout=30
        )
        
        if r.status_code == 401:
            results.record_pass("POST /api/auth/login with wrong password returns 401")
            
            # Check error message
            try:
                data = r.json()
                if "detail" in data and "Invalid credentials" in data["detail"]:
                    results.record_pass("Error message is 'Invalid credentials'")
                else:
                    results.record_fail("Error message", f"Expected 'Invalid credentials', got {data.get('detail')}")
            except Exception:
                results.record_fail("Error response format", "Could not parse JSON response")
        else:
            results.record_fail(
                "POST /api/auth/login with wrong password",
                f"Expected 401, got {r.status_code}: {r.text}"
            )
    except Exception as e:
        results.record_fail("POST /api/auth/login with wrong password", str(e))


async def test_auth_me_endpoint(client: httpx.AsyncClient, access_token: str):
    """Test GET /api/auth/me with valid access token"""
    print("\n▶ Testing GET /api/auth/me with valid token")
    
    try:
        r = await client.get(
            f"{BASE}/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30
        )
        
        if r.status_code == 200:
            data = r.json()
            
            if not data.get("user"):
                results.record_fail("GET /api/auth/me - user", "Missing user object")
                return
            
            if not data.get("organization"):
                results.record_fail("GET /api/auth/me - organization", "Missing organization object")
                return
            
            results.record_pass("GET /api/auth/me returns 200 with user and organization")
            
            # Verify user details
            user = data["user"]
            org = data["organization"]
            
            if user.get("email") == ADMIN_EMAIL:
                results.record_pass(f"User profile email matches: {ADMIN_EMAIL}")
            else:
                results.record_fail("User profile email", f"Expected {ADMIN_EMAIL}, got {user.get('email')}")
            
            if org.get("name") == "Platform Admin":
                results.record_pass("Organization is 'Platform Admin'")
            else:
                results.record_fail("Organization", f"Expected 'Platform Admin', got {org.get('name')}")
        else:
            results.record_fail(
                "GET /api/auth/me",
                f"Expected 200, got {r.status_code}: {r.text}"
            )
    except Exception as e:
        results.record_fail("GET /api/auth/me", str(e))


async def main():
    print("="*60)
    print("Testing Login Fix - Seeded Admin Account")
    print(f"Testing against: {BASE}")
    print(f"Credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        # Test 1: Login with correct credentials
        session = await test_login_with_correct_credentials(client)
        
        # Test 2: Login with wrong password
        await test_login_with_wrong_password(client)
        
        # Test 3: GET /auth/me with valid token
        if session and session.get("access_token"):
            await test_auth_me_endpoint(client, session["access_token"])
        else:
            results.record_fail("GET /api/auth/me", "Skipped - no valid access token from login")
    
    return results.print_summary()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
