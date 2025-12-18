# dontAskUs - Complete API Documentation

**Base URL:** `http://localhost:8000` (development)  
**Version:** 1.0  
**Last Updated:** December 17, 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [User Endpoints](#user-endpoints)
4. [Group Endpoints](#group-endpoints)
5. [Daily Questions & Voting](#daily-questions--voting)
6. [Question Sets](#question-sets)
7. [Admin Authentication](#admin-authentication)
8. [Admin: Account Management](#admin-account-management)
9. [Admin: Dashboard](#admin-dashboard)
10. [Admin: User Management](#admin-user-management)
11. [Admin: Group Management](#admin-group-management)
12. [Admin: Question Set Management](#admin-question-set-management)
13. [Admin: Audit Logs](#admin-audit-logs)
14. [Group Creator: Private Question Sets](#group-creator-private-question-sets)
15. [WebSocket](#websocket)
16. [Error Codes](#error-codes)
17. [Rate Limiting](#rate-limiting)

---

## Overview

dontAskUs is a group-based daily question and voting platform. It supports:

- **User Flow:** Join groups, answer daily questions, vote on members/duos/choices
- **Group Admin Flow:** Create groups, manage question sets, view analytics
- **Instance Admin Flow:** Manage users, groups, question sets, audit logs with 2FA
- **Group Creator Flow:** Create private question sets (max 5 per group)

### Authentication Types

| Flow            | Method              | Storage      |
| --------------- | ------------------- | ------------ |
| Users           | Session Token       | Query param  |
| Group Admins    | Admin Token         | Header       |
| Instance Admins | JWT (TOTP required) | Bearer Token |

---

## Authentication

### Session Tokens (Users)

- Generated on group join
- Hashed and stored server-side
- Passed as `?session_token=<token>` in query params
- Expires after `SESSION_TOKEN_EXPIRY_DAYS` (default: 7 days)

### Admin Tokens (Group Creators)

- Generated on group creation
- Passed as `X-Admin-Token` header
- Never expires (tied to group)

### JWT Tokens (Instance Admins)

- Access Token: 60 minutes
- Refresh Token: 7 days
- Passed as `Authorization: Bearer <token>` header
- Requires TOTP 2FA

---

## User Endpoints

### Join Group

Create a user account within a group.

```http
POST /api/users/join
Content-Type: application/json

{
  "display_name": "Alice",
  "group_invite_code": "ABC123",
  "color_avatar": "#3B82F6"  // optional
}
```

**Response (200):**

```json
{
  "id": 10,
  "user_id": "uuid-here",
  "display_name": "Alice",
  "color_avatar": "#3B82F6",
  "session_token": "plaintext-token-save-this",
  "created_at": "2025-12-17T10:00:00Z",
  "answer_streak": 0,
  "longest_answer_streak": 0
}
```

**Validation:**

- Display name must be unique within group
- Display name: 1-50 characters
- Invite code: 6-8 uppercase alphanumeric
- Color avatar: hex format `#RRGGBB` (optional, auto-assigned if omitted)

**Errors:**

- `400` Invalid invite code or color format
- `404` Group not found
- `409` Display name already taken in group

---

### Validate Session

Check if a session token is valid.

```http
GET /api/users/validate-session/{session_token}
```

**Response (200):**

```json
{
  "valid": true,
  "user_id": "uuid",
  "display_name": "Alice",
  "group_id": "group-uuid",
  "answer_streak": 2,
  "longest_answer_streak": 5
}
```

---

## Group Endpoints

### Create Group

```http
POST /api/groups
Content-Type: application/json

{
  "name": "My Awesome Group"
}
```

**Response (200):**

```json
{
  "id": 1,
  "group_id": "uuid",
  "name": "My Awesome Group",
  "invite_code": "ABC123",
  "admin_token": "plaintext-admin-token-save-this",
  "creator_id": null,
  "created_at": "2025-12-17T10:00:00Z",
  "member_count": 0
}
```

---

### Get Group by Invite Code (Public)

```http
GET /api/groups/{invite_code}
```

**Response (200):**

```json
{
  "id": 1,
  "group_id": "uuid",
  "name": "My Awesome Group",
  "invite_code": "ABC123",
  "created_at": "2025-12-17T10:00:00Z",
  "member_count": 5
}
```

---

### Get Group Info

```http
GET /api/groups/{group_id}/info
```

**Response (200):**

```json
{
  "id": 1,
  "group_id": "uuid",
  "name": "My Awesome Group",
  "invite_code": "ABC123",
  "member_count": 5,
  "created_at": "2025-12-17T10:00:00Z"
}
```

---

### List Group Members

```http
GET /api/groups/{group_id}/members
```

**Response (200):**

```json
{
  "members": [
    {
      "user_id": "uuid",
      "display_name": "Alice",
      "color_avatar": "#3B82F6",
      "answer_streak": 2,
      "longest_answer_streak": 5
    }
  ]
}
```

---

## Daily Questions & Voting

### Question Types

| Type            | Options Source         | Allow Multiple | Notes                         |
| --------------- | ---------------------- | -------------- | ----------------------------- |
| `binary_vote`   | Yes/No (automatic)     | No             | Simple binary choice          |
| `single_choice` | Custom list            | No             | Single selection from options |
| `member_choice` | Group members          | Optional       | Choose member(s) from group   |
| `duo_choice`    | Generated member pairs | No             | Choose from random duos       |
| `free_text`     | None                   | N/A            | Open-ended text response      |

---

### Create Daily Question (Admin)

Group admins create today's question.

```http
POST /api/groups/{group_id}/questions
X-Admin-Token: <admin_token>
Content-Type: application/json

{
  "question_text": "Who is the funniest?",
  "question_type": "member_choice"
}
```

**Response (200):**

```json
{
  "id": 1,
  "question_id": "uuid",
  "question_text": "Who is the funniest?",
  "question_type": "member_choice",
  "options": ["Alice", "Bob", "Charlie"],
  "question_date": "2025-12-17T00:00:00Z",
  "is_active": true,
  "allow_multiple": false
}
```

**Rules:**

- One question per day per group
- Requires ≥2 members for member/duo types
- Options auto-generated for member/duo types

---

### Get Today's Question

```http
GET /api/groups/{group_id}/questions/today?session_token=<token>
```

**Response (200):**

```json
{
  "id": 1,
  "question_id": "uuid",
  "question_text": "Who is the funniest?",
  "question_type": "member_choice",
  "options": ["Alice", "Bob", "Charlie"],
  "option_counts": {
    "Alice": 3,
    "Bob": 1,
    "Charlie": 2
  },
  "question_date": "2025-12-17T00:00:00Z",
  "is_active": true,
  "total_votes": 6,
  "allow_multiple": false,
  "user_vote": "Alice",
  "user_text_answer": null,
  "user_streak": 3,
  "longest_streak": 5
}
```

**Note:** `user_vote` is `null` if not answered, a string for single-select, or an array for
multi-select when `allow_multiple` is `true`.

---

### Submit Answer/Vote

```http
POST /api/groups/{group_id}/questions/{question_id}/answer?session_token=<token>
Content-Type: application/json

// Single choice
{
  "answer": "Alice"
}

// Multi-select (when allow_multiple=true)
{
  "answer": ["Alice", "Bob"]
}

// Free text
{
  "text_answer": "My detailed response here"
}
```

**Response (200):**

```json
{
  "message": "Vote recorded",
  "question_id": "uuid",
  "options": ["Alice", "Bob", "Charlie"],
  "option_counts": {
    "Alice": 4,
    "Bob": 1,
    "Charlie": 2
  },
  "total_votes": 7,
  "user_answer": "Alice",
  "current_streak": 4,
  "longest_streak": 5
}
```

**Validation:**

- `answer` must be in `options` for choice-based types
- Array required when `allow_multiple` is true
- Only one vote per user per question

**Errors:**

- `400` Invalid answer or already voted
- `401` Invalid session token
- `404` Question not found

---

## Question Sets

### Create Question Set

```http
POST /api/question-sets
Content-Type: application/json

{
  "name": "Icebreakers",
  "description": "Fun conversation starters",
  "template_ids": ["template-uuid-1", "template-uuid-2"]
}
```

**Response (200):**

```json
{
  "id": 1,
  "set_id": "uuid",
  "name": "Icebreakers",
  "description": "Fun conversation starters",
  "is_public": true,
  "created_at": "2025-12-17T10:00:00Z"
}
```

---

### List Public Question Sets

```http
GET /api/question-sets
```

**Response (200):**

```json
{
  "sets": [
    {
      "id": 1,
      "set_id": "uuid",
      "name": "Icebreakers",
      "is_public": true,
      "template_count": 10
    }
  ]
}
```

---

### Get Question Set Details

```http
GET /api/question-sets/{set_id}
```

**Response (200):**

```json
{
  "id": 1,
  "set_id": "uuid",
  "name": "Icebreakers",
  "is_public": true,
  "templates": [
    {
      "id": 1,
      "template_id": "uuid",
      "question_text": "What's your superpower?",
      "question_type": "free_text"
    }
  ]
}
```

---

### Assign Sets to Group (Admin)

```http
POST /api/groups/{group_id}/question-sets
X-Admin-Token: <admin_token>
Content-Type: application/json

{
  "question_set_ids": ["set-uuid-1", "set-uuid-2"],
  "replace": false
}
```

**Response (200):**

```json
{
  "group_id": "uuid",
  "question_sets": [
    {
      "set_id": "uuid",
      "name": "Icebreakers",
      "template_count": 10
    }
  ]
}
```

---

### List Group Question Sets

```http
GET /api/groups/{group_id}/question-sets
```

**Response (200):**

```json
{
  "group_id": "uuid",
  "question_sets": [
    {
      "set_id": "uuid",
      "name": "Icebreakers",
      "is_public": true,
      "template_count": 10
    }
  ]
}
```

---

## Admin Authentication

Instance admins have full platform access with 2FA security.

### Initial Setup

Set environment variables:

```bash
ADMIN_INITIAL_USERNAME=admin
ADMIN_INITIAL_PASSWORD=changeme123
```

On first container start, the admin user is auto-created without TOTP. After first login, configure
TOTP via the UI.

---

### Step 1: Login with Password

```http
POST /api/admin/login
Content-Type: application/json

{
  "username": "admin",
  "password": "securepassword123"
}
```

**Response (200) - TOTP Not Configured:**

```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Response (200) - TOTP Configured:**

```json
{
  "temp_token": "eyJhbGc...",
  "message": "Password verified. Please provide 2FA code."
}
```

**Rate Limit:** 5 requests/minute per IP

---

### Step 2: Verify TOTP (if configured)

```http
POST /api/admin/2fa
Content-Type: application/json

{
  "temp_token": "eyJhbGc...",
  "totp_code": "123456"
}
```

**Response (200):**

```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Rate Limit:** 10 requests/minute per IP

---

### Refresh Token

```http
POST /api/admin/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGc..."
}
```

**Response (200):**

```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

---

### Logout

```http
POST /api/admin/logout
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "message": "Logged out successfully"
}
```

---

## Admin: Account Management

### Get Profile

```http
GET /api/admin/profile
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "id": 1,
  "username": "admin",
  "email": null,
  "is_active": true,
  "totp_configured": false,
  "created_at": "2025-12-17T10:00:00Z",
  "last_login_ip": "192.168.1.100"
}
```

---

### Change Password

```http
POST /api/admin/account/change-password
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "current_password": "oldPass123",
  "new_password": "newStrongPass456"
}
```

**Response (200):**

```json
{
  "message": "Password updated successfully"
}
```

**Errors:**

- `400` Current password incorrect or new password too weak

---

### Initiate TOTP Setup

```http
POST /api/admin/account/totp/setup-initiate
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "provisioning_uri": "otpauth://totp/dontAskUs:admin?secret=JBSWY3DPEHPK3PXP&issuer=dontAskUs"
}
```

**Usage:**

- Display QR code from `provisioning_uri`
- User scans with authenticator app
- Secret stored temporarily until verified

**Errors:**

- `400` TOTP already configured

---

### Verify TOTP Setup

```http
POST /api/admin/account/totp/setup-verify
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "code": "123456"
}
```

**Response (200):**

```json
{
  "message": "TOTP configured successfully"
}
```

**Errors:**

- `400` Invalid TOTP code or no setup session

---

## Admin: Dashboard

### Get Dashboard Stats

```http
GET /api/admin/dashboard/stats
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "total_groups": 42,
  "total_users": 256,
  "total_question_sets": 18,
  "public_sets": 10,
  "private_sets": 8,
  "active_sessions_today": 15,
  "recent_audit_logs": [
    {
      "id": 1,
      "admin_id": 1,
      "action": "LOGIN",
      "target_type": "ADMIN_USER",
      "target_id": 1,
      "timestamp": "2025-12-17T10:00:00Z",
      "ip_address": "192.168.1.100",
      "reason": "Password-only login (TOTP not configured)"
    }
  ]
}
```

---

## Admin: User Management

### List All Users

```http
GET /api/admin/users?limit=50&offset=0&suspended_only=false
Authorization: Bearer <access_token>
```

**Query Parameters:**

- `limit`: 1-500 (default: 50)
- `offset`: Starting position (default: 0)
- `suspended_only`: Show only suspended users (default: false)

**Response (200):**

```json
{
  "users": [
    {
      "id": 1,
      "name": "Alice",
      "email": null,
      "created_at": "2025-12-17T10:00:00Z",
      "is_suspended": false,
      "suspension_reason": null,
      "last_known_ip": "192.168.1.50"
    }
  ],
  "total": 256,
  "limit": 50,
  "offset": 0
}
```

---

### Suspend/Unsuspend User

```http
PUT /api/admin/users/{user_id}/suspension
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "is_suspended": true,
  "suspension_reason": "Violates community guidelines"
}
```

**Response (200):**

```json
{
  "message": "User suspension status updated",
  "user_id": 1
}
```

---

### Recover User Token

Generate a new session token for account recovery.

```http
POST /api/admin/users/{user_id}/recover-token
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "reason": "User lost access to their account"
}
```

**Response (200):**

```json
{
  "session_token": "new-plaintext-token",
  "message": "New session token generated for user Alice"
}
```

---

## Admin: Group Management

### List All Groups

```http
GET /api/admin/groups?limit=50&offset=0
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "groups": [
    {
      "id": 1,
      "name": "Tech Discussion",
      "created_by": "user@example.com",
      "created_at": "2025-12-01T10:00:00Z",
      "member_count": 25,
      "instance_admin_notes": "Active group"
    }
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

---

### Update Group Notes

```http
PUT /api/admin/groups/{group_id}/notes
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "notes": "Flagged for monitoring"
}
```

**Response (200):**

```json
{
  "message": "Group notes updated",
  "group_id": 1
}
```

---

## Admin: Question Set Management

### List All Question Sets

```http
GET /api/admin/question-sets?limit=50&offset=0&public_only=false&private_only=false
Authorization: Bearer <access_token>
```

**Query Parameters:**

- `limit`: 1-500 (default: 50)
- `offset`: Starting position (default: 0)
- `public_only`: Show only public sets (default: false)
- `private_only`: Show only private sets (default: false)

**Response (200):**

```json
{
  "sets": [
    {
      "id": 1,
      "name": "Default Questions",
      "is_public": true,
      "creator_id": null,
      "usage_count": 142,
      "created_at": "2025-12-01T00:00:00Z",
      "question_count": 10
    }
  ],
  "total": 18,
  "limit": 50,
  "offset": 0
}
```

---

## Admin: Audit Logs

### Get Audit Logs

```http
GET /api/admin/audit-logs?limit=50&offset=0
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "logs": [
    {
      "id": 1,
      "admin_id": 1,
      "action": "LOGIN",
      "target_type": "ADMIN_USER",
      "target_id": 1,
      "before_state": null,
      "after_state": { "last_login_ip": "192.168.1.100" },
      "timestamp": "2025-12-17T10:00:00Z",
      "ip_address": "192.168.1.100",
      "reason": "Password-only login"
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

---

## Group Creator: Private Question Sets

Group creators can create up to 5 private question sets per group.

### Create Private Set

```http
POST /api/groups/{group_id}/question-sets/private
session_token: <token>
Content-Type: application/json

{
  "name": "My Custom Questions",
  "description": "Optional",
  "questions": [
    {
      "text": "Is this good?",
      "question_type": "binary_vote",
      "options": ["Yes", "No"]
    }
  ]
}
```

**Response (200):**

```json
{
  "message": "Private question set created successfully",
  "set_id": 42,
  "name": "My Custom Questions",
  "question_count": 1,
  "is_public": false
}
```

**Validation:**

- Name: 3-200 characters
- Questions: 1-100 per set
- Max 5 sets per group
- Only group creator can create

---

### List My Private Sets

```http
GET /api/groups/{group_id}/question-sets/my?limit=50&offset=0
session_token: <token>
```

**Response (200):**

```json
{
  "sets": [
    {
      "id": 42,
      "name": "My Custom Questions",
      "question_count": 1,
      "usage_count": 5,
      "is_public": false,
      "created_at": "2025-12-17T10:00:00Z"
    }
  ],
  "total": 3,
  "limit": 50,
  "offset": 0,
  "max_sets": 5,
  "current_count": 3
}
```

---

### Get Set Details

```http
GET /api/groups/{group_id}/question-sets/{set_id}
session_token: <token>
```

**Response (200):**

```json
{
  "id": 42,
  "name": "My Custom Questions",
  "is_public": false,
  "creator_id": 1,
  "usage_count": 5,
  "created_at": "2025-12-17T10:00:00Z",
  "question_count": 1,
  "questions": [
    {
      "id": 101,
      "text": "Is this good?",
      "question_type": "binary_vote"
    }
  ]
}
```

---

## WebSocket

### Live Vote Updates

```
WS /ws/groups/{group_id}/questions/{question_id}
```

**Send:**

```json
{
  "type": "vote",
  "session_token": "token",
  "answer": "Alice"
}
```

**Receive:**

```json
{
  "type": "vote_update",
  "option_counts": {
    "Alice": 4,
    "Bob": 2
  },
  "total_votes": 6
}
```

---

## Error Codes

| Code | Meaning                          |
| ---- | -------------------------------- |
| 200  | Success                          |
| 201  | Created                          |
| 400  | Bad Request                      |
| 401  | Unauthorized                     |
| 403  | Forbidden                        |
| 404  | Not Found                        |
| 409  | Conflict                         |
| 429  | Too Many Requests (Rate Limited) |
| 500  | Internal Server Error            |

---

## Rate Limiting

| Endpoint                | Limit              |
| ----------------------- | ------------------ |
| `POST /api/admin/login` | 5 requests/minute  |
| `POST /api/admin/2fa`   | 10 requests/minute |
| General endpoints       | No specific limits |

---

## Security Best Practices

1. **Store tokens securely** - Use secure storage (e.g., httpOnly cookies for web)
2. **HTTPS in production** - Always use TLS
3. **Rotate tokens** - Use refresh tokens to avoid storing credentials
4. **Monitor audit logs** - Review admin actions regularly
5. **Strong passwords** - Minimum 8 characters, mixed case, numbers, symbols
6. **Backup TOTP** - Store backup codes during TOTP setup
7. **IP whitelisting** - Consider restricting admin endpoints by IP

---

## Environment Variables

### Backend Configuration

```bash
# Database
DATABASE_URL=postgresql+psycopg2://user:pass@db:5432/qadb

# Redis
REDIS_URL=redis://redis:6379/0

# Security
SECRET_KEY=your-super-secret-key-change-in-production
SESSION_TOKEN_EXPIRY_DAYS=7

# CORS
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# Admin Setup
ADMIN_INITIAL_USERNAME=admin
ADMIN_INITIAL_PASSWORD=changeme123

# Scheduling
SCHEDULE_INTERVAL_SECONDS=86400
```

---

## Quick Start Examples

### Complete User Flow

```bash
# 1. Create group
curl -X POST http://localhost:8000/api/groups \
  -H "Content-Type: application/json" \
  -d '{"name":"My Group"}'

# Save: invite_code, admin_token

# 2. Join group
curl -X POST http://localhost:8000/api/users/join \
  -H "Content-Type: application/json" \
  -d '{"display_name":"Alice","group_invite_code":"ABC123"}'

# Save: session_token

# 3. Get today's question
curl "http://localhost:8000/api/groups/1/questions/today?session_token=TOKEN"

# 4. Submit answer
curl -X POST "http://localhost:8000/api/groups/1/questions/1/answer?session_token=TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"answer":"Alice"}'
```

### Admin Flow

```bash
# 1. Login
curl -X POST http://localhost:8000/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme123"}'

# Save: access_token (or temp_token if TOTP configured)

# 2. Get dashboard
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/admin/dashboard/stats

# 3. List users
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/admin/users?limit=50"
```

---

**End of Documentation**
