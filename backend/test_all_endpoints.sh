#!/bin/bash
#
# Comprehensive endpoint test script for dontAskUs backend
# Tests ALL endpoints with test data and reports PASS/FAIL
#
set -o pipefail

BASE="http://localhost:8000"
PASS=0
FAIL=0
SKIP=0
ERRORS=""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

check() {
    local label="$1"
    local expected_code="$2"
    local actual_code="$3"
    local body="$4"

    if [ "$actual_code" = "$expected_code" ]; then
        echo -e "  ${GREEN}✅ PASS${NC} [${actual_code}] ${label}"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}❌ FAIL${NC} [${actual_code}] ${label}  (expected ${expected_code})"
        ERRORS="${ERRORS}\n  ❌ ${label}: got ${actual_code}, expected ${expected_code} — ${body}"
        FAIL=$((FAIL + 1))
    fi
}

skip() {
    local label="$1"
    local reason="$2"
    echo -e "  ${YELLOW}⏭️  SKIP${NC} ${label} — ${reason}"
    SKIP=$((SKIP + 1))
}

# Helper: make a request and capture code+body
req() {
    local method="$1"; shift
    local url="$1"; shift
    # remaining args are passed to curl
    local resp
    resp=$(curl -s -w "\n%{http_code}" -X "$method" "$url" "$@" 2>&1)
    local code
    code=$(echo "$resp" | tail -1)
    local body
    body=$(echo "$resp" | sed '$d')
    echo "$code"
    echo "$body"
}

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  dontAskUs — Full Endpoint Test Suite${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

# ════════════════════════════════════════════════════════════
echo -e "${BOLD}[0] Health Check${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/health")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /health" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[1] Admin Auth Endpoints${NC}"
echo -e "    ${CYAN}POST /api/admin/login${NC}"
# ════════════════════════════════════════════════════════════

# 1a. Admin login — success
resp=$(req POST "$BASE/api/admin/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme123"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/login (valid credentials)" "$code" "200" "$body"
# The response can be 200 with tokens (no TOTP) — that's what we expect
ADMIN_ACCESS=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)
ADMIN_REFRESH=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('refresh_token',''))" 2>/dev/null)

if [ -z "$ADMIN_ACCESS" ]; then
    echo -e "  ${RED}  ⚠ Could not extract admin access token. Remaining admin tests may fail.${NC}"
fi

# 1b. Admin login — wrong password
resp=$(req POST "$BASE/api/admin/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"wrongpassword"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/login (wrong password)" "401" "$code" "$body"

# 1c. Admin login — nonexistent user
resp=$(req POST "$BASE/api/admin/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"nobody","password":"doesntmatter"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/login (nonexistent user)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/admin/refresh${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/admin/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$ADMIN_REFRESH\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/refresh (valid token)" "200" "$code" "$body"

resp=$(req POST "$BASE/api/admin/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"invalid.token.here"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/refresh (invalid token)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/admin/profile${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/admin/profile" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/admin/profile (authenticated)" "200" "$code" "$body"

resp=$(req GET "$BASE/api/admin/profile")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/admin/profile (no auth)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/admin/totp/status${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/admin/totp/status" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/admin/totp/status" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/admin/account/change-password${NC}"
# ════════════════════════════════════════════════════════════
# Wrong current password
resp=$(req POST "$BASE/api/admin/account/change-password" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"wrongpass","new_password":"NewPass1234!"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/account/change-password (wrong current)" "400" "$code" "$body"

# Password too weak
resp=$(req POST "$BASE/api/admin/account/change-password" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"changeme123","new_password":"weak"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/account/change-password (weak password)" "422" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/admin/logout${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/admin/logout" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/logout" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[2] Admin Dashboard & Audit${NC}"
# ════════════════════════════════════════════════════════════
# Re-login to get a fresh token (logout didn't invalidate JWT)
ADMIN_ACCESS=$(curl -s -X POST "$BASE/api/admin/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme123"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

resp=$(req GET "$BASE/api/admin/dashboard/stats" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/admin/dashboard/stats" "200" "$code" "$body"

resp=$(req GET "$BASE/api/admin/audit-logs?limit=5&offset=0" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/admin/audit-logs" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[3] User Auth Endpoints${NC}"
echo -e "    ${CYAN}POST /api/auth/register${NC}"
# ════════════════════════════════════════════════════════════
TIMESTAMP=$(date +%s)

# 3a. Register new user
resp=$(req POST "$BASE/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test_${TIMESTAMP}@example.com\",\"password\":\"TestPass1\",\"display_name\":\"TestUser${TIMESTAMP}\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/register (new account)" "200" "$code" "$body"
USER_ACCESS=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
USER_REFRESH=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('refresh_token',''))" 2>/dev/null)
USER_ACCOUNT_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('account_id',''))" 2>/dev/null)

# 3b. Register duplicate email
resp=$(req POST "$BASE/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test_${TIMESTAMP}@example.com\",\"password\":\"TestPass1\",\"display_name\":\"Duplicate\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/register (duplicate email)" "409" "$code" "$body"

# 3c. Register weak password
resp=$(req POST "$BASE/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"weak@test.com","password":"weak","display_name":"Weak"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/register (weak password)" "422" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/auth/login${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test_${TIMESTAMP}@example.com\",\"password\":\"TestPass1\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/login (valid)" "200" "$code" "$body"
USER_ACCESS=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
USER_REFRESH=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('refresh_token',''))" 2>/dev/null)

resp=$(req POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"nobody@test.com","password":"WrongPass1"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/login (wrong email)" "401" "$code" "$body"

resp=$(req POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test_${TIMESTAMP}@example.com\",\"password\":\"WrongPass1\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/login (wrong password)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/auth/refresh${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$USER_REFRESH\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/refresh (valid)" "200" "$code" "$body"
USER_ACCESS=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

resp=$(req POST "$BASE/api/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"garbage"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/refresh (invalid)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/auth/me${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/auth/me" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/auth/me (authenticated)" "200" "$code" "$body"

resp=$(req GET "$BASE/api/auth/me")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/auth/me (no auth)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/auth/change-password${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/auth/change-password" \
  -H "Authorization: Bearer $USER_ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"WrongPass1","new_password":"NewTestPass1"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/change-password (wrong current)" "401" "$code" "$body"

resp=$(req POST "$BASE/api/auth/change-password" \
  -H "Authorization: Bearer $USER_ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"TestPass1","new_password":"weak"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/change-password (weak new pass)" "422" "$code" "$body"

# Change to a new password, then change back
resp=$(req POST "$BASE/api/auth/change-password" \
  -H "Authorization: Bearer $USER_ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"TestPass1","new_password":"NewTestPass1"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/change-password (valid)" "200" "$code" "$body"

# Change back for subsequent tests
req POST "$BASE/api/auth/change-password" \
  -H "Authorization: Bearer $USER_ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"NewTestPass1","new_password":"TestPass1"}' > /dev/null

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/auth/forgot-password${NC}"
# ════════════════════════════════════════════════════════════
# Existing email — should return 200 (always, to prevent enumeration)
resp=$(req POST "$BASE/api/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test_${TIMESTAMP}@example.com\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/forgot-password (existing email)" "200" "$code" "$body"

# Non-existent email — should also return 200
resp=$(req POST "$BASE/api/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d '{"email":"nonexistent@example.com"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/forgot-password (unknown email)" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/auth/reset-password${NC}"
# ════════════════════════════════════════════════════════════
# Invalid/wrong code — should return 400
resp=$(req POST "$BASE/api/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test_${TIMESTAMP}@example.com\",\"token\":\"000000\",\"new_password\":\"ResetPass1\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/reset-password (invalid code)" "400" "$code" "$body"

# Non-existent email
resp=$(req POST "$BASE/api/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d '{"email":"nobody@example.com","token":"123456","new_password":"ResetPass1"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/reset-password (unknown email)" "400" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[4] Group Endpoints${NC}"
echo -e "    ${CYAN}POST /api/groups (unauthenticated - should not exist)${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/groups" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"TestGroup_${TIMESTAMP}\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/groups (unauthenticated - rejected)" "404" "$code" "$body"
UNAUTH_GROUP_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('group_id',''))" 2>/dev/null)
UNAUTH_INVITE_CODE=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('invite_code',''))" 2>/dev/null)
# admin_token no longer returned — group creator identified via JWT + creator_id

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/auth/groups/create (authenticated)${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/auth/groups/create" \
  -H "Authorization: Bearer $USER_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"AuthGroup_${TIMESTAMP}\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/groups/create (authenticated)" "200" "$code" "$body"
AUTH_GROUP_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('group_id',''))" 2>/dev/null)
AUTH_INVITE_CODE=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('invite_code',''))" 2>/dev/null)
# admin_token no longer returned — group creator identified via JWT + creator_id
AUTH_GROUP_INT_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{invite_code}${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_INVITE_CODE")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{invite_code} (valid)" "200" "$code" "$body"

resp=$(req GET "$BASE/api/groups/ZZZZZZ")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{invite_code} (invalid)" "404" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/info${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/info" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{group_id}/info" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/members${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/members" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{group_id}/members" "200" "$code" "$body"

# Get the user_id for later tests
FIRST_USER_ID=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['user_id'] if d else '')" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/auth/groups/join${NC}"
# ════════════════════════════════════════════════════════════
# Register a second user to join the group
resp=$(req POST "$BASE/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test2_${TIMESTAMP}@example.com\",\"password\":\"TestPass1\",\"display_name\":\"User2_${TIMESTAMP}\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
USER2_ACCESS=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

resp=$(req POST "$BASE/api/auth/groups/join" \
  -H "Authorization: Bearer $USER2_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"invite_code\":\"$AUTH_INVITE_CODE\",\"display_name\":\"User2InGroup\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/groups/join (valid)" "200" "$code" "$body"
USER2_USER_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('user_id',''))" 2>/dev/null)

# Join same group again — should fail
resp=$(req POST "$BASE/api/auth/groups/join" \
  -H "Authorization: Bearer $USER2_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"invite_code\":\"$AUTH_INVITE_CODE\",\"display_name\":\"DuplicateJoin\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/groups/join (already member)" "400" "$code" "$body"

resp=$(req POST "$BASE/api/auth/groups/join" \
  -H "Authorization: Bearer $USER2_ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"invite_code":"ZZZZZZ","display_name":"Nobody"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/auth/groups/join (bad invite code)" "404" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/leaderboard${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/leaderboard" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{group_id}/leaderboard (authenticated)" "200" "$code" "$body"

resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/leaderboard")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{group_id}/leaderboard (no auth)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[5] Question Set Endpoints${NC}"
echo -e "    ${CYAN}GET /api/question-sets${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/question-sets")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/question-sets (list public)" "200" "$code" "$body"
FIRST_SET_ID=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['set_id'] if d else '')" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/question-sets/{set_id}${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$FIRST_SET_ID" ]; then
    resp=$(req GET "$BASE/api/question-sets/$FIRST_SET_ID")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "GET /api/question-sets/{set_id}" "200" "$code" "$body"
else
    skip "GET /api/question-sets/{set_id}" "no question set available"
fi

resp=$(req GET "$BASE/api/question-sets/nonexistent-id")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/question-sets/{set_id} (not found)" "404" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/question-sets${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/question-sets" \
  -H "Authorization: Bearer $USER_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"TestSet_${TIMESTAMP}\",\"is_public\":true}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/question-sets (create)" "200" "$code" "$body"
NEW_SET_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('set_id',''))" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/groups/{group_id}/question-sets (assign)${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$FIRST_SET_ID" ]; then
    resp=$(req POST "$BASE/api/groups/$AUTH_GROUP_ID/question-sets" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $USER_ACCESS" \
      -d "{\"question_set_ids\":[\"$FIRST_SET_ID\"],\"replace\":false}")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "POST /api/groups/{group_id}/question-sets (assign via JWT)" "200" "$code" "$body"
else
    skip "POST /api/groups/{group_id}/question-sets" "missing set_id"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/question-sets${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/question-sets" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{group_id}/question-sets" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[6] Daily Questions & Voting${NC}"
echo -e "    ${CYAN}GET /api/groups/{group_id}/questions/today${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/questions/today" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
# Might be 404 if no question yet, or 200 if auto-question was created on group create
if [ "$code" = "200" ] || [ "$code" = "404" ]; then
    check "GET /api/groups/{group_id}/questions/today" "$code" "$code" "$body"
    if [ "$code" = "200" ]; then
        QUESTION_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('question_id',''))" 2>/dev/null)
    fi
else
    check "GET /api/groups/{group_id}/questions/today" "200 or 404" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/admin/groups/{group_id}/set-today-question (instance admin)${NC}"
# ════════════════════════════════════════════════════════════
# Use instance admin JWT to set today's question
resp=$(req POST "$BASE/api/admin/groups/$AUTH_GROUP_INT_ID/set-today-question" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/groups/{group_id}/set-today-question" "200" "$code" "$body"
QUESTION_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('question_id',''))" 2>/dev/null)
Q_TYPE=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('question_type',''))" 2>/dev/null)

# Now get today's question (should exist)
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/questions/today" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{group_id}/questions/today (after regenerate)" "200" "$code" "$body"
QUESTION_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('question_id',''))" 2>/dev/null)
Q_OPTIONS=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); opts=d.get('options',[]); print(opts[0] if opts else '')" 2>/dev/null)
Q_TYPE=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('question_type',''))" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/groups/{group_id}/questions/{question_id}/answer${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$QUESTION_ID" ] && [ -n "$Q_OPTIONS" ]; then
    # Answer the question
    if [ "$Q_TYPE" = "free_text" ]; then
        ANSWER_PAYLOAD='{"text_answer":"My test answer"}'
    else
        ANSWER_PAYLOAD="{\"answer\":\"$Q_OPTIONS\"}"
    fi
    resp=$(req POST "$BASE/api/groups/$AUTH_GROUP_ID/questions/$QUESTION_ID/answer" \
      -H "Authorization: Bearer $USER_ACCESS" \
      -H "Content-Type: application/json" \
      -d "$ANSWER_PAYLOAD")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "POST /api/groups/{group_id}/questions/{question_id}/answer (valid)" "200" "$code" "$body"

    # No auth
    resp=$(req POST "$BASE/api/groups/$AUTH_GROUP_ID/questions/$QUESTION_ID/answer" \
      -H "Content-Type: application/json" \
      -d "$ANSWER_PAYLOAD")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "POST .../answer (no auth)" "401" "$code" "$body"
elif [ -n "$QUESTION_ID" ] && [ "$Q_TYPE" = "free_text" ]; then
    resp=$(req POST "$BASE/api/groups/$AUTH_GROUP_ID/questions/$QUESTION_ID/answer" \
      -H "Authorization: Bearer $USER_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"text_answer":"My test answer"}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "POST .../answer (free_text)" "200" "$code" "$body"
else
    skip "POST .../answer" "no question or options available"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/questions/history${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/questions/history?skip=0&limit=5" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{group_id}/questions/history" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/question-status (group creator via JWT)${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/question-status" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{group_id}/question-status (creator JWT)" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/leaderboard (group member via JWT)${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_ID/leaderboard" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{group_id}/leaderboard (JWT)" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[7] Push Notifications${NC}"
echo -e "    ${CYAN}GET /api/push-notifications/status${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/push-notifications/status")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/push-notifications/status" "200" "$code" "$body"

# Device token registration (push not enabled, expect 503)
if [ -n "$FIRST_USER_ID" ]; then
    resp=$(req POST "$BASE/api/users/$FIRST_USER_ID/device-token" \
      -H "Authorization: Bearer $USER_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"token":"test-fcm-token-12345","platform":"android","device_name":"TestDevice"}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    # 503 if push not enabled, 200 if enabled
    if [ "$code" = "503" ] || [ "$code" = "200" ]; then
        check "POST /api/users/{user_id}/device-token" "$code" "$code" "$body"
    else
        check "POST /api/users/{user_id}/device-token" "200 or 503" "$code" "$body"
    fi

    resp=$(req GET "$BASE/api/users/$FIRST_USER_ID/device-tokens" \
      -H "Authorization: Bearer $USER_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "GET /api/users/{user_id}/device-tokens" "200" "$code" "$body"
else
    skip "Push notification endpoints" "no user_id available"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[8] Avatar Endpoints${NC}"
echo -e "    ${CYAN}POST /api/users/{user_id}/avatar${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$FIRST_USER_ID" ]; then
    # Create a tiny valid PNG for testing (1x1 red pixel)
    python3 -c "
import struct, zlib, sys
def make_png():
    sig = b'\\x89PNG\\r\\n\\x1a\\n'
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data)
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc & 0xffffffff)
    raw = b'\\x00\\xff\\x00\\x00'
    compressed = zlib.compress(raw)
    idat_crc = zlib.crc32(b'IDAT' + compressed)
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc & 0xffffffff)
    iend_crc = zlib.crc32(b'IEND')
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc & 0xffffffff)
    sys.stdout.buffer.write(sig + ihdr + idat + iend)
make_png()
" > /tmp/test_avatar.png

    resp=$(req POST "$BASE/api/users/$FIRST_USER_ID/avatar" \
      -H "Authorization: Bearer $USER_ACCESS" \
      -F "file=@/tmp/test_avatar.png;type=image/png")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "POST /api/users/{user_id}/avatar (upload PNG)" "200" "$code" "$body"

    # Delete avatar
    resp=$(req DELETE "$BASE/api/users/$FIRST_USER_ID/avatar" \
      -H "Authorization: Bearer $USER_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "DELETE /api/users/{user_id}/avatar" "200" "$code" "$body"

    # Delete again — no avatar
    resp=$(req DELETE "$BASE/api/users/$FIRST_USER_ID/avatar" \
      -H "Authorization: Bearer $USER_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "DELETE /api/users/{user_id}/avatar (no avatar)" "404" "$code" "$body"
else
    skip "Avatar endpoints" "no user_id available"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[9] Instance Admin — User Management${NC}"
# ════════════════════════════════════════════════════════════
echo -e "    ${CYAN}GET /api/admin/users${NC}"
resp=$(req GET "$BASE/api/admin/users?limit=5&offset=0" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/admin/users" "200" "$code" "$body"
ADMIN_TARGET_USER_ID=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); users=d.get('users',[]); print(users[0]['id'] if users else '')" 2>/dev/null)
ADMIN_TARGET_USER_EMAIL=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); users=d.get('users',[]); print(users[0].get('account_email','') if users else '')" 2>/dev/null)

resp=$(req GET "$BASE/api/admin/users" )
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/admin/users (no auth)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/admin/users (create user in group)${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/admin/users" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"display_name\":\"AdminCreated_${TIMESTAMP}\",\"group_id\":$AUTH_GROUP_INT_ID}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/users (create)" "200" "$code" "$body"
ADMIN_CREATED_USER_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}PUT /api/admin/users/{user_id}/suspension${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$ADMIN_CREATED_USER_ID" ]; then
    resp=$(req PUT "$BASE/api/admin/users/$ADMIN_CREATED_USER_ID/suspension" \
      -H "Authorization: Bearer $ADMIN_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"is_suspended":true,"suspension_reason":"Test suspension"}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "PUT /api/admin/users/{id}/suspension (suspend)" "200" "$code" "$body"

    resp=$(req PUT "$BASE/api/admin/users/$ADMIN_CREATED_USER_ID/suspension" \
      -H "Authorization: Bearer $ADMIN_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"is_suspended":false}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "PUT /api/admin/users/{id}/suspension (unsuspend)" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/admin/users/{user_id}/reset-password${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$ADMIN_TARGET_USER_ID" ]; then
    resp=$(req POST "$BASE/api/admin/users/$ADMIN_TARGET_USER_ID/reset-password" \
      -H "Authorization: Bearer $ADMIN_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"new_password":"ResetPass1","reason":"Test admin reset"}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    # 200 if user has account, 400 if not
    if [ "$code" = "200" ] || [ "$code" = "400" ]; then
        check "POST /api/admin/users/{id}/reset-password" "$code" "$code" "$body"
    else
        check "POST /api/admin/users/{id}/reset-password" "200 or 400" "$code" "$body"
    fi
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}DELETE /api/admin/users/{user_id}${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$ADMIN_CREATED_USER_ID" ]; then
    resp=$(req DELETE "$BASE/api/admin/users/$ADMIN_CREATED_USER_ID" \
      -H "Authorization: Bearer $ADMIN_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "DELETE /api/admin/users/{id}" "200" "$code" "$body"
fi

resp=$(req DELETE "$BASE/api/admin/users/99999" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "DELETE /api/admin/users/{id} (not found)" "404" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[10] Instance Admin — Group Management${NC}"
echo -e "    ${CYAN}GET /api/admin/groups${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/admin/groups?limit=5" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/admin/groups" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/admin/groups${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/admin/groups" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"AdminGroup_${TIMESTAMP}\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/groups (create)" "200" "$code" "$body"
ADMIN_GROUP_TO_DELETE=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}PUT /api/admin/groups/{group_id}/notes${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$ADMIN_GROUP_TO_DELETE" ]; then
    resp=$(req PUT "$BASE/api/admin/groups/$ADMIN_GROUP_TO_DELETE/notes" \
      -H "Authorization: Bearer $ADMIN_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"notes":"Test admin notes for this group"}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "PUT /api/admin/groups/{id}/notes" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}DELETE /api/admin/groups/{group_id}${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$ADMIN_GROUP_TO_DELETE" ]; then
    resp=$(req DELETE "$BASE/api/admin/groups/$ADMIN_GROUP_TO_DELETE" \
      -H "Authorization: Bearer $ADMIN_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "DELETE /api/admin/groups/{id}" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[11] Instance Admin — Question Set Management${NC}"
echo -e "    ${CYAN}GET /api/admin/question-sets${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/admin/question-sets?limit=5" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/admin/question-sets" "200" "$code" "$body"
ADMIN_FIRST_SET_ID=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); sets=d.get('sets',[]); print(sets[0]['id'] if sets else '')" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/admin/question-sets${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req POST "$BASE/api/admin/question-sets" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"AdminTestSet_${TIMESTAMP}\",\"is_public\":true}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/question-sets (create)" "200" "$code" "$body"
ADMIN_NEW_SET_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}POST /api/admin/question-sets/{set_id}/questions${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$ADMIN_NEW_SET_ID" ]; then
    resp=$(req POST "$BASE/api/admin/question-sets/$ADMIN_NEW_SET_ID/questions" \
      -H "Authorization: Bearer $ADMIN_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"question_text":"Who is the funniest?","question_type":"member_choice"}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "POST /api/admin/question-sets/{id}/questions (add member_choice)" "200" "$code" "$body"

    resp=$(req POST "$BASE/api/admin/question-sets/$ADMIN_NEW_SET_ID/questions" \
      -H "Authorization: Bearer $ADMIN_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"question_text":"Is this a test?","question_type":"yesno"}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "POST /api/admin/question-sets/{id}/questions (add yesno)" "200" "$code" "$body"

    resp=$(req POST "$BASE/api/admin/question-sets/$ADMIN_NEW_SET_ID/questions" \
      -H "Authorization: Bearer $ADMIN_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"question_text":"Pick A or B","question_type":"choice","options":["Option A","Option B"]}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "POST /api/admin/question-sets/{id}/questions (add choice)" "200" "$code" "$body"
    ADMIN_Q_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

    resp=$(req POST "$BASE/api/admin/question-sets/$ADMIN_NEW_SET_ID/questions" \
      -H "Authorization: Bearer $ADMIN_ACCESS" \
      -H "Content-Type: application/json" \
      -d '{"question_text":"Tell me something","question_type":"free_text"}')
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "POST /api/admin/question-sets/{id}/questions (add free_text)" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/admin/question-sets/{set_id}/questions${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$ADMIN_NEW_SET_ID" ]; then
    resp=$(req GET "$BASE/api/admin/question-sets/$ADMIN_NEW_SET_ID/questions" \
      -H "Authorization: Bearer $ADMIN_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "GET /api/admin/question-sets/{id}/questions" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}DELETE /api/admin/question-sets/{set_id}/questions/{q_id}${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$ADMIN_NEW_SET_ID" ] && [ -n "$ADMIN_Q_ID" ]; then
    resp=$(req DELETE "$BASE/api/admin/question-sets/$ADMIN_NEW_SET_ID/questions/$ADMIN_Q_ID" \
      -H "Authorization: Bearer $ADMIN_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "DELETE /api/admin/question-sets/{id}/questions/{qid}" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}DELETE /api/admin/question-sets/{set_id}${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$ADMIN_NEW_SET_ID" ]; then
    resp=$(req DELETE "$BASE/api/admin/question-sets/$ADMIN_NEW_SET_ID" \
      -H "Authorization: Bearer $ADMIN_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "DELETE /api/admin/question-sets/{id}" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[12] Group Admin — Question Cycle${NC}"
# ════════════════════════════════════════════════════════════
echo -e "    ${CYAN}POST /api/admin/groups/{group_id}/reset-question-cycle (instance admin)${NC}"
resp=$(req POST "$BASE/api/admin/groups/$AUTH_GROUP_INT_ID/reset-question-cycle" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/groups/{group_id}/reset-question-cycle" "200" "$code" "$body"

# No auth
resp=$(req POST "$BASE/api/admin/groups/$AUTH_GROUP_INT_ID/reset-question-cycle")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST .../reset-question-cycle (no auth)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[13] Admin 2FA Endpoints (TOTP)${NC}"
# ════════════════════════════════════════════════════════════
echo -e "    ${CYAN}POST /api/admin/totp/setup${NC}"
resp=$(req POST "$BASE/api/admin/totp/setup" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/totp/setup (generate secret)" "200" "$code" "$body"

echo -e "    ${CYAN}POST /api/admin/account/totp/setup-initiate${NC}"
resp=$(req POST "$BASE/api/admin/account/totp/setup-initiate" \
  -H "Authorization: Bearer $ADMIN_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/account/totp/setup-initiate" "200" "$code" "$body"

# We can't verify TOTP without a real TOTP code, but we can test invalid codes
echo -e "    ${CYAN}POST /api/admin/account/totp/setup-verify (invalid code)${NC}"
resp=$(req POST "$BASE/api/admin/account/totp/setup-verify" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"code":"000000"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/account/totp/setup-verify (invalid code)" "400" "$code" "$body"

echo -e "    ${CYAN}POST /api/admin/2fa (no token)${NC}"
resp=$(req POST "$BASE/api/admin/2fa" \
  -H "Content-Type: application/json" \
  -d '{"temp_token":"invalid","totp_code":"000000"}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/admin/2fa (invalid temp token)" "401" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[14] Group Creator — Private Question Sets${NC}"
# ════════════════════════════════════════════════════════════
echo -e "    ${CYAN}POST /api/groups/{group_id}/question-sets/private${NC}"
resp=$(req POST "$BASE/api/groups/$AUTH_GROUP_INT_ID/question-sets/private" \
  -H "Authorization: Bearer $USER_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"PrivateSet_${TIMESTAMP}\",\"questions\":[{\"text\":\"Test Q1\",\"question_type\":\"binary_vote\"},{\"text\":\"Test Q2\",\"question_type\":\"free_text\"}]}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST /api/groups/{id}/question-sets/private (create)" "200" "$code" "$body"
PRIVATE_SET_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('set_id',''))" 2>/dev/null)

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/question-sets/my${NC}"
# ════════════════════════════════════════════════════════════
resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_INT_ID/question-sets/my" \
  -H "Authorization: Bearer $USER_ACCESS")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "GET /api/groups/{id}/question-sets/my" "200" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/question-sets/{set_id} (private details)${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$PRIVATE_SET_ID" ]; then
    resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_INT_ID/question-sets/$PRIVATE_SET_ID" \
      -H "Authorization: Bearer $USER_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "GET /api/groups/{id}/question-sets/{set_id}" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}PUT /api/groups/{group_id}/question-sets/{set_id} (update)${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$PRIVATE_SET_ID" ]; then
    resp=$(req PUT "$BASE/api/groups/$AUTH_GROUP_INT_ID/question-sets/$PRIVATE_SET_ID" \
      -H "Authorization: Bearer $USER_ACCESS" \
      -H "Content-Type: application/json" \
      -d "{\"name\":\"UpdatedSet_${TIMESTAMP}\"}")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "PUT /api/groups/{id}/question-sets/{set_id}" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}GET /api/groups/{group_id}/question-sets/{set_id}/usage${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$PRIVATE_SET_ID" ]; then
    resp=$(req GET "$BASE/api/groups/$AUTH_GROUP_INT_ID/question-sets/$PRIVATE_SET_ID/usage" \
      -H "Authorization: Bearer $USER_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "GET /api/groups/{id}/question-sets/{set_id}/usage" "200" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "    ${CYAN}DELETE /api/groups/{group_id}/question-sets/{set_id}${NC}"
# ════════════════════════════════════════════════════════════
if [ -n "$PRIVATE_SET_ID" ]; then
    resp=$(req DELETE "$BASE/api/groups/$AUTH_GROUP_INT_ID/question-sets/$PRIVATE_SET_ID" \
      -H "Authorization: Bearer $USER_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "DELETE /api/groups/{id}/question-sets/{set_id}" "200" "$code" "$body"
fi

# Non-creator trying to access
resp=$(req POST "$BASE/api/groups/$AUTH_GROUP_INT_ID/question-sets/private" \
  -H "Authorization: Bearer $USER2_ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"name":"ShouldFail","questions":[{"text":"Q","question_type":"binary_vote"}]}')
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
check "POST .../private (non-creator → 403)" "403" "$code" "$body"

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[15] Delete Group (Owner)${NC}"
# ════════════════════════════════════════════════════════════

# Create a temporary group to delete
echo -e "    ${CYAN}DELETE /api/auth/groups/{group_id} (owner deletes group)${NC}"
resp=$(req POST "$BASE/api/auth/groups/create" \
  -H "Authorization: Bearer $USER_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"DeleteMe_${TIMESTAMP}\"}")
code=$(echo "$resp" | head -1)
body=$(echo "$resp" | tail -n +2)
DELETE_GROUP_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('group_id',''))" 2>/dev/null)

if [ -n "$DELETE_GROUP_ID" ]; then
    # Non-owner trying to delete (should fail)
    resp=$(req DELETE "$BASE/api/auth/groups/$DELETE_GROUP_ID" \
      -H "Authorization: Bearer $USER2_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "DELETE /api/auth/groups/{group_id} (non-owner → 403)" "403" "$code" "$body"

    # Owner deletes
    resp=$(req DELETE "$BASE/api/auth/groups/$DELETE_GROUP_ID" \
      -H "Authorization: Bearer $USER_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "DELETE /api/auth/groups/{group_id} (owner)" "200" "$code" "$body"

    # Try to get deleted group (should 404)
    resp=$(req GET "$BASE/api/groups/$DELETE_GROUP_ID/info" \
      -H "Authorization: Bearer $USER_ACCESS")
    code=$(echo "$resp" | head -1)
    body=$(echo "$resp" | tail -n +2)
    check "GET /api/groups/{group_id}/info (deleted → 404)" "404" "$code" "$body"
fi

# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  TEST RESULTS${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""
TOTAL=$((PASS + FAIL + SKIP))
echo -e "  ${GREEN}✅ Passed:  $PASS${NC}"
echo -e "  ${RED}❌ Failed:  $FAIL${NC}"
echo -e "  ${YELLOW}⏭️  Skipped: $SKIP${NC}"
echo -e "  ${BOLD}   Total:   $TOTAL${NC}"
echo ""

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}${BOLD}  Failed Tests:${NC}"
    echo -e "$ERRORS"
    echo ""
fi

if [ $FAIL -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}🎉 All tests passed!${NC}"
else
    echo -e "  ${RED}${BOLD}⚠️  $FAIL test(s) failed. See details above.${NC}"
fi
echo ""
