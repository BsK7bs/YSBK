#!/bin/bash

BACKEND_URL="https://archive-deploy-safe.preview.emergentagent.com"
VALID_CODE="AOJ-YI7D-5A56"
INVALID_CODE="INVALID-CODE-XXX"

echo "=========================================="
echo "Test 1: Missing config (expect exit 4)"
echo "=========================================="
TMP_DIR="/app/tmp_bootstrap_test_1"
rm -rf "$TMP_DIR" && mkdir -p "$TMP_DIR"
export DTA_CONFIG_DIR="$TMP_DIR"
export DTA_BOOTSTRAP_DIR="$TMP_DIR"
cd /app/agent
set +e
python3 -m digital_twin_agent bootstrap 2>&1
EXIT_CODE=$?
set -e
echo "Exit code: $EXIT_CODE"
if [ $EXIT_CODE -eq 4 ]; then
    echo "✅ PASS: Got expected exit code 4 for missing config"
else
    echo "❌ FAIL: Expected exit code 4, got $EXIT_CODE"
fi
rm -rf "$TMP_DIR"
echo ""

echo "=========================================="
echo "Test 2: Invalid token (expect exit 5)"
echo "=========================================="
TMP_DIR="/app/tmp_bootstrap_test_2"
rm -rf "$TMP_DIR" && mkdir -p "$TMP_DIR"
export DTA_CONFIG_DIR="$TMP_DIR"
export DTA_BOOTSTRAP_DIR="$TMP_DIR"
cat > "$TMP_DIR/config.json" << INNER_EOF
{
  "backend_url": "$BACKEND_URL",
  "enrollment_token": "$INVALID_CODE",
  "label": "test-invalid",
  "provisioned": false
}
INNER_EOF
cd /app/agent
set +e
python3 -m digital_twin_agent bootstrap 2>&1
EXIT_CODE=$?
set -e
echo "Exit code: $EXIT_CODE"
if [ $EXIT_CODE -eq 5 ]; then
    echo "✅ PASS: Got expected exit code 5 for invalid token"
else
    echo "❌ FAIL: Expected exit code 5, got $EXIT_CODE"
fi
rm -rf "$TMP_DIR"
echo ""

echo "=========================================="
echo "Test 3: Valid token (expect exit 0)"
echo "=========================================="
TMP_DIR="/app/tmp_bootstrap_test_3"
rm -rf "$TMP_DIR" && mkdir -p "$TMP_DIR"
export DTA_CONFIG_DIR="$TMP_DIR"
export DTA_BOOTSTRAP_DIR="$TMP_DIR"
cat > "$TMP_DIR/config.json" << INNER_EOF
{
  "backend_url": "$BACKEND_URL",
  "enrollment_token": "$VALID_CODE",
  "label": "test-valid-bootstrap",
  "provisioned": false
}
INNER_EOF
cd /app/agent
set +e
python3 -m digital_twin_agent bootstrap 2>&1
EXIT_CODE=$?
set -e
echo "Exit code: $EXIT_CODE"
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ PASS: Got expected exit code 0 for valid token"
    # Check if device was created
    echo "Checking if device was enrolled..."
    if [ -f "$TMP_DIR/config.enc" ]; then
        echo "✅ config.enc was created (device enrolled)"
    else
        echo "⚠️  config.enc not found"
    fi
else
    echo "❌ FAIL: Expected exit code 0, got $EXIT_CODE"
fi
rm -rf "$TMP_DIR"
echo ""

echo "=========================================="
echo "Summary: All bootstrap exit code tests completed"
echo "=========================================="
