# dontAskUs - Complete API Documentation

**Base URL:** `http://localhost:8000` (development)  
**Version:** 1.2.0  
**Last Updated:** January 4, 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [User Endpoints](#user-endpoints)
4. [Group Endpoints](#group-endpoints)
5. [Daily Questions & Voting](#daily-questions--voting)
6. [Question Sets](#question-sets)
7. [Leaderboard](#leaderboard)
8. [Admin Authentication](#admin-authentication)
9. [Admin: Account Management](#admin-account-management)
10. [Admin: Dashboard](#admin-dashboard)
11. [Admin: User Management](#admin-user-management)
12. [Admin: Group Management](#admin-group-management)
13. [Admin: Question Set Management](#admin-question-set-management)
14. [Admin: Audit Logs](#admin-audit-logs)
15. [Group Creator: Private Question Sets](#group-creator-private-question-sets)
16. [Push Notifications](#push-notifications)
17. [WebSocket](#websocket)
18. [Error Codes](#error-codes)
19. [Rate Limiting](#rate-limiting)
20. [Health Check](#health-check)

---

## Overview

dontAskUs is a group-based daily question and voting platform. It supports:

- **User Flow:** Join groups, answer daily questions, vote on members/duos/choices
- **Group Admin Flow:** Create groups, manage question sets, view analytics
- **Instance Admin Flow:** Manage users, groups, question sets, audit logs with 2FA
- **Group Creator Flow:** Create private question sets (max 5 per group)

### Automatic Daily Questions

The backend **automatically generates a new question for each group every day**:

- Runs on server startup and every 24 hours (configurable via `SCHEDULE_INTERVAL_SECONDS`)
- Selects questions from assigned question sets (or public templates as fallback)
- Never repeats a question within the same group until all are exhausted
- Different groups receive different questions on the same day
- Requires at least 2 members for `member_choice` and `duo_choice` questions
- Sends push notifications to group members (if FCM is configured)

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
  "group_id": "group-uuid-here",
  "display_name": "Alice",
  "color_avatar": "#3B82F6",
  "avatar_url": null,
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

Check if a session token is valid. Also auto-refreshes the session expiry.

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
  "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp",
  "answer_streak": 2,
  "longest_answer_streak": 5,
  "session_expires_at": "2026-01-20T10:00:00Z"
}
```

---

### Refresh Session

Explicitly extend the session token expiry. Useful for keeping sessions alive during periods of low
activity or for "keep me logged in" functionality.

> **Note:** Sessions are automatically refreshed on any authenticated API call, so this endpoint is
> only needed for explicit refresh requests when no other API calls are being made.

```http
POST /api/users/refresh-session
X-Session-Token: <session_token>
```

**Headers:**

- `X-Session-Token` (required): User's current session token

**Response (200):**

```json
{
  "message": "Session refreshed successfully",
  "user_id": "uuid",
  "display_name": "Alice",
  "group_id": "group-uuid",
  "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp",
  "session_expires_at": "2026-01-20T10:00:00Z",
  "expires_in_days": 7
}
```

**Errors:**

- `401` Invalid or expired session token

---

## Session Management

### Auto-Refresh Behavior

Session tokens are **automatically extended** whenever a user makes any authenticated API call. This
means:

- Users who regularly use the app will never have their session expire
- The session expiry is reset to `SESSION_TOKEN_EXPIRY_DAYS` (default: 7 days) from the current time
- Only inactive users (no API calls for the full expiry period) will need to re-authenticate

### Session Expiry

If a session expires:

1. The user's **data is preserved** (streaks, votes, display name, avatar, etc.)
2. The user cannot make authenticated API calls until their session is recovered
3. **Recovery options:**
   - Admin can generate a new token via `POST /api/admin/users/{user_id}/recover-token`
   - User must rejoin the group (creates a new account, loses streak history)

### Streak Reset

Answer streaks are reset to zero if a user misses answering a daily question:

- If the user answers today and answered yesterday → streak continues
- If the user answers today but last answered 2+ days ago → streak resets to 1
- Longest streak is preserved for historical tracking

---

## Avatar Upload Endpoints

Users can upload custom profile avatars. Images are automatically processed, resized, and converted
to WebP format for optimal storage and delivery.

### Upload Avatar

Upload or replace a user's profile avatar image.

```http
POST /api/users/{user_id}/avatar
Content-Type: multipart/form-data
X-Session-Token: <session_token>

file: <image file>
```

**Headers:**

- `X-Session-Token` (required): User's session token

**Request:**

- File must be uploaded as `multipart/form-data` with field name `file`
- Supported formats: JPEG, PNG, GIF, WebP
- Maximum file size: 2MB
- Image is automatically:
  - Resized to max 256x256 pixels (maintains aspect ratio)
  - Converted to WebP format
  - Transparency converted to white background

**Response (200):**

```json
{
  "message": "Avatar uploaded successfully",
  "avatar_url": "https://api.example.com/uploads/avatars/abc123def456.webp",
  "avatar_filename": "abc123def456.webp",
  "uploaded_at": "2025-12-17T10:00:00Z"
}
```

**Errors:**

- `400` No file provided
- `400` File too large (max 2MB)
- `400` Invalid file type (only JPEG, PNG, GIF, WebP allowed)
- `400` Invalid or corrupted image file
- `401` Session token required / Invalid session
- `403` Cannot modify another user's avatar
- `404` User not found

**Example (curl):**

```bash
curl -X POST "https://api.example.com/api/users/{user_id}/avatar" \
  -H "X-Session-Token: YOUR_TOKEN" \
  -F "file=@/path/to/avatar.jpg"
```

**Example (JavaScript):**

```javascript
const formData = new FormData();
formData.append("file", imageFile);

const response = await fetch(`${API_URL}/api/users/${userId}/avatar`, {
  method: "POST",
  headers: {
    "X-Session-Token": token
  },
  body: formData
});
```

---

### Delete Avatar

Remove a user's profile avatar, reverting to the color avatar.

```http
DELETE /api/users/{user_id}/avatar
X-Session-Token: <session_token>
```

**Headers:**

- `X-Session-Token` (required): User's session token

**Response (200):**

```json
{
  "message": "Avatar deleted successfully",
  "color_avatar": "#3B82F6"
}
```

**Errors:**

- `401` Session token required / Invalid session
- `403` Cannot modify another user's avatar
- `404` User not found / No avatar to delete

---

### Accessing Avatar Images

Avatar images are served as static files:

```http
GET /uploads/avatars/{filename}
```

The `avatar_url` field in user responses contains the full URL to the avatar image. If `avatar_url`
is `null`, the client should display the user's `color_avatar` as a fallback.

**Example usage in frontend:**

```javascript
// Display avatar with color fallback
function getAvatarDisplay(user) {
  if (user.avatar_url) {
    return `<img src="${user.avatar_url}" alt="${user.display_name}" />`;
  } else {
    return `<div style="background: ${user.color_avatar}">${user.display_name[0]}</div>`;
  }
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
[
  {
    "user_id": "uuid",
    "display_name": "Alice",
    "color_avatar": "#3B82F6",
    "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp",
    "created_at": "2025-12-17T10:00:00Z",
    "answer_streak": 2,
    "longest_answer_streak": 5
  }
]
```

---

## Leaderboard

### Get Group Leaderboard

Get leaderboard sorted by answer streak (requires session token).

```http
GET /api/groups/{group_id}/leaderboard?session_token=<token>
```

**Response (200):**

```json
[
  {
    "display_name": "Alice",
    "color_avatar": "#3B82F6",
    "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp",
    "answer_streak": 15,
    "longest_answer_streak": 20
  },
  {
    "display_name": "Bob",
    "color_avatar": "#EF4444",
    "answer_streak": 10,
    "longest_answer_streak": 12
  }
]
```

**Notes:**

- Results sorted by `answer_streak` descending, then by `longest_answer_streak`
- User must be a member of the group

**Errors:**

- `401` Invalid or missing session token
- `403` User not in this group
- `404` Group not found

---

## Daily Questions & Voting

**Note:** Questions are automatically generated daily by the server. See
[Automatic Daily Questions](#automatic-daily-questions) in Overview. The endpoints below are for
manual creation (admin override) or retrieving the current question.

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

### Get Question History

Retrieve paginated history of all questions in a group (most recent first).

```http
GET /api/groups/{group_id}/questions/history?skip=0&limit=20
```

**Query Parameters:**

| Parameter | Type | Default | Description                     |
| --------- | ---- | ------- | ------------------------------- |
| `skip`    | int  | 0       | Number of questions to skip     |
| `limit`   | int  | 20      | Max questions to return (1-100) |

**Response (200):**

```json
{
  "group_id": "group-uuid",
  "total_count": 45,
  "skip": 0,
  "limit": 20,
  "questions": [
    {
      "question_id": "uuid-1",
      "question_text": "Who is the funniest?",
      "question_type": "member_choice",
      "option_a": null,
      "option_b": null,
      "options": ["Alice", "Bob", "Charlie"],
      "option_counts": {
        "Alice": 4,
        "Bob": 2,
        "Charlie": 1
      },
      "question_date": "2025-12-17T00:00:00Z",
      "is_active": false,
      "vote_count_a": 0,
      "vote_count_b": 0,
      "total_votes": 7,
      "allow_multiple": false
    },
    {
      "question_id": "uuid-2",
      "question_text": "Best movie of 2025?",
      "question_type": "single_choice",
      "option_a": "Movie A",
      "option_b": "Movie B",
      "options": ["Movie A", "Movie B", "Movie C"],
      "option_counts": {
        "Movie A": 3,
        "Movie B": 2,
        "Movie C": 4
      },
      "question_date": "2025-12-16T00:00:00Z",
      "is_active": false,
      "vote_count_a": 3,
      "vote_count_b": 2,
      "total_votes": 9,
      "allow_multiple": false
    }
  ]
}
```

**Notes:**

- Results are ordered by `question_date` descending (most recent first)
- Includes both active and inactive questions
- No authentication required (public endpoint)
- Use `skip` and `limit` for pagination

**Errors:**

- `404` Group not found

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

Instance admins have full platform access with optional 2FA security.

### Initial Setup

The admin user is **automatically created on first container startup** using environment variables:

```bash
ADMIN_INITIAL_USERNAME=admin           # Default: admin
ADMIN_INITIAL_PASSWORD=your_password   # Required - change this!
```

**Important:**

- Change your password immediately after first login
- Enable 2FA (TOTP) in Account Settings for enhanced security
- The admin user is only created if no admin exists yet

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

### Generate TOTP Secret

Generate a new TOTP secret and provisioning URI for setup.

```http
POST /api/admin/totp/setup
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "totp_secret": "JBSWY3DPEHPK3PXP",
  "provisioning_uri": "otpauth://totp/dontAskUs:admin?secret=JBSWY3DPEHPK3PXP&issuer=dontAskUs",
  "message": "Scan the QR code with your authenticator app or enter the secret manually"
}
```

---

### Enable TOTP (Alternative Method)

Enable TOTP by providing both the secret and a verification code.

```http
POST /api/admin/totp/enable
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "totp_secret": "JBSWY3DPEHPK3PXP",
  "verification_code": "123456"
}
```

**Response (200):**

```json
{
  "message": "TOTP enabled successfully"
}
```

**Errors:**

- `400`: Missing totp_secret or verification_code
- `400`: Invalid verification code

---

### Disable TOTP

Disable TOTP (requires password verification for security).

```http
POST /api/admin/totp/disable
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "password": "currentPassword123"
}
```

**Response (200):**

```json
{
  "message": "TOTP disabled successfully"
}
```

**Errors:**

- `400`: Password required to disable TOTP
- `401`: Invalid password

---

### Get TOTP Status

Get current TOTP configuration status.

```http
GET /api/admin/totp/status
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "totp_enabled": true,
  "totp_configured": true
}
```

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

### Create User (Admin)

Create a new user in a specific group.

```http
POST /api/admin/users
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "display_name": "NewUser",
  "group_id": 1,
  "color_avatar": "#FF5733"
}
```

**Response (200):**

```json
{
  "id": 42,
  "display_name": "NewUser",
  "group_id": 1,
  "session_token": "plaintext-session-token",
  "color_avatar": "#FF5733"
}
```

**Errors:**

- `400`: Display name must be at least 2 characters
- `400`: Group ID is required
- `400`: Group not found
- `400`: Display name already taken in this group

---

### Delete User (Admin)

Delete a user and all their answers.

```http
DELETE /api/admin/users/{user_id}
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "status": "deleted"
}
```

**Errors:**

- `404`: User not found

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

### Create Group (Admin)

Create a new group. Generates invite code and admin token automatically.

```http
POST /api/admin/groups
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "New Discussion Group"
}
```

**Response (200):**

```json
{
  "id": 42,
  "name": "New Discussion Group"
}
```

**Errors:**

- `400`: Group name must be at least 2 characters
- `400`: Group name must be at most 255 characters
- `400`: Group name already exists

---

### Delete Group (Admin)

Delete a group and all related data (users, questions, associations).

```http
DELETE /api/admin/groups/{group_id}
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "status": "deleted"
}
```

**Errors:**

- `404`: Group not found

---

### Get Admin Leaderboard

Get group leaderboard (admin access via X-Admin-Token).

```http
GET /api/admin/groups/{group_id}/leaderboard
X-Admin-Token: <admin_token>
```

**Response (200):**

```json
[
  {
    "display_name": "Alice",
    "color_avatar": "#FF5733",
    "answer_streak": 15,
    "longest_answer_streak": 30
  },
  {
    "display_name": "Bob",
    "color_avatar": "#33FF57",
    "answer_streak": 12,
    "longest_answer_streak": 20
  }
]
```

---

### Get Question Status

Get question exhaustion status for a group.

```http
GET /api/admin/groups/{group_id}/question-status
X-Admin-Token: <admin_token>
```

**Response (200):**

```json
{
  "group_id": "abc123",
  "total_available_templates": 100,
  "used_templates_count": 45,
  "exhausted": false,
  "total_questions_created": 45,
  "message": "Questions available"
}
```

When exhausted:

```json
{
  "group_id": "abc123",
  "total_available_templates": 50,
  "used_templates_count": 50,
  "exhausted": true,
  "total_questions_created": 50,
  "message": "All questions have been used. Cycle will reset on next question."
}
```

---

### Reset Question Cycle

Reset question cycle by clearing all used questions for a group.

```http
POST /api/admin/groups/{group_id}/reset-question-cycle
X-Admin-Token: <admin_token>
```

**Response (200):**

```json
{
  "group_id": "abc123",
  "message": "Question cycle reset. 45 questions deleted.",
  "deleted_count": 45
}
```

---

### Regenerate Today's Question

Delete today's question (if any) and create a new one from current question sets.

```http
POST /api/admin/groups/{group_id}/regenerate-today
X-Admin-Token: <admin_token>
```

**Response (200):**

```json
{
  "id": 123,
  "question_id": 456,
  "question_text": "What's your favorite...",
  "question_type": "single_choice",
  "options": ["Option A", "Option B", "Option C"],
  "option_counts": {},
  "question_date": "2025-12-17",
  "is_active": true,
  "total_votes": 0
}
```

**Errors:**

- `400`: Unable to generate today's question (insufficient members or no templates)

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

### Get Questions in Set (Admin)

Get all questions in a specific question set.

```http
GET /api/admin/question-sets/{set_id}/questions
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "set_id": 1,
  "questions": [
    {
      "id": 101,
      "template_id": 1,
      "question_text": "What's your favorite color?",
      "type": "single_choice",
      "options": ["Red", "Blue", "Green"],
      "allow_multiple": false
    },
    {
      "id": 102,
      "template_id": 2,
      "question_text": "Do you like coffee?",
      "type": "binary_vote",
      "options": ["Yes", "No"],
      "allow_multiple": false
    }
  ]
}
```

**Errors:**

- `404`: Question set not found

---

### Create Question Set (Admin)

Create a new question set.

```http
POST /api/admin/question-sets
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "New Question Set",
  "is_public": true
}
```

**Response (200):**

```json
{
  "id": 42,
  "name": "New Question Set",
  "is_public": true
}
```

**Errors:**

- `400`: Question set name must be at least 2 characters
- `400`: Question set name must be at most 255 characters
- `400`: Question set name already exists

---

### Add Question to Set (Admin)

Add a question to an existing question set.

```http
POST /api/admin/question-sets/{set_id}/questions
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "question_text": "What's your favorite color?",
  "question_type": "choice",
  "options": ["Red", "Blue", "Green", "Yellow"]
}
```

**Question Types:**

- `yesno`: Binary yes/no question (maps to `binary_vote`)
- `choice`: Multiple choice with custom options (maps to `single_choice`)
- `text` / `free_text`: Free text response
- `member_choice`: Choose a group member
- `duo_choice`: Choose two group members

**Response (200):**

```json
{
  "id": 101,
  "question_text": "What's your favorite color?",
  "type": "single_choice",
  "options": ["Red", "Blue", "Green", "Yellow"]
}
```

**Errors:**

- `400`: Question text must be at least 3 characters
- `400`: Invalid question type
- `400`: Choice questions need at least 2 options
- `404`: Question set not found

---

### Delete Question Set (Admin)

Delete a question set and all related data.

```http
DELETE /api/admin/question-sets/{set_id}
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "status": "deleted"
}
```

**Errors:**

- `404`: Question set not found

---

### Delete Question from Set (Admin)

Delete a specific question from a question set.

```http
DELETE /api/admin/question-sets/{set_id}/questions/{question_id}
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "status": "deleted"
}
```

**Errors:**

- `404`: Question not found

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

### Update Private Set

Update a private question set name and/or questions. Only the group creator can update sets.

```http
PUT /api/groups/{group_id}/question-sets/{set_id}
session_token: <token>
Content-Type: application/json

{
  "name": "Updated Set Name",
  "questions": [
    {
      "text": "Updated question?",
      "question_type": "binary_vote",
      "options": ["Yes", "No"]
    }
  ]
}
```

**Response (200):**

```json
{
  "message": "Question set updated successfully",
  "set_id": 42,
  "name": "Updated Set Name"
}
```

**Errors:**

- `401`: Invalid session token
- `403`: Only group creator can update private sets
- `404`: Question set not found

---

### Delete Private Set

Delete a private question set. Cannot delete sets currently assigned to the group.

```http
DELETE /api/groups/{group_id}/question-sets/{set_id}
session_token: <token>
```

**Response (200):**

```json
{
  "message": "Question set deleted successfully",
  "set_id": 42
}
```

**Errors:**

- `401`: Invalid session token
- `403`: Only group creator can delete private sets
- `400`: Cannot delete a set that is currently assigned to the group

---

### Get Question Set Usage

Get usage statistics for a private question set (how many times each question has been asked).

```http
GET /api/groups/{group_id}/question-sets/{set_id}/usage
session_token: <token>
```

**Response (200):**

```json
{
  "set_id": 42,
  "set_name": "My Custom Questions",
  "total_times_used": 15,
  "total_questions_asked": 45,
  "questions": [
    {
      "template_id": 101,
      "text": "What's your favorite color?",
      "question_type": "single_choice",
      "times_asked": 5
    },
    {
      "template_id": 102,
      "text": "Do you prefer morning or evening?",
      "question_type": "binary_vote",
      "times_asked": 3
    }
  ]
}
```

**Errors:**

- `401`: Invalid session token
- `403`: Only group creator can view usage stats
- `404`: Question set not found

---

## Push Notifications

Push notifications are **optional** and use Firebase Cloud Messaging (FCM) HTTP v1 API.

### Configuration

To enable push notifications, set these environment variables:

```bash
FCM_PROJECT_ID=your-firebase-project-id
FCM_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}
```

Or use a file path:

```bash
FCM_PROJECT_ID=your-firebase-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### Check Push Notification Status

```http
GET /api/push-notifications/status
```

**Response (200):**

```json
{
  "enabled": true,
  "message": "Push notifications are enabled"
}
```

Or if disabled:

```json
{
  "enabled": false,
  "message": "Push notifications are not configured on this server"
}
```

### Register Device Token

Register a device to receive push notifications.

```http
POST /api/users/{user_id}/device-token
X-Session-Token: <session_token>
Content-Type: application/json

{
  "token": "fcm-device-token-from-firebase-sdk",
  "platform": "ios",  // "ios", "android", or "web"
  "device_name": "iPhone 15 Pro"  // optional
}
```

**Response (200):**

```json
{
  "id": 1,
  "token": "fcm-device-token...",
  "platform": "ios",
  "device_name": "iPhone 15 Pro",
  "created_at": "2026-01-04T10:00:00Z",
  "is_active": true
}
```

**Errors:**

- `401`: Invalid session token
- `503`: Push notifications not enabled on server

### Unregister Device Token

Remove a device token (e.g., on logout or when disabling notifications).

```http
DELETE /api/users/{user_id}/device-token?token=<device_token>
X-Session-Token: <session_token>
```

**Response (200):**

```json
{
  "message": "Device token removed successfully"
}
```

### List Device Tokens

List all registered device tokens for a user.

```http
GET /api/users/{user_id}/device-tokens
X-Session-Token: <session_token>
```

**Response (200):**

```json
[
  {
    "id": 1,
    "token": "fcm-device-token...",
    "platform": "ios",
    "device_name": "iPhone 15 Pro",
    "created_at": "2026-01-04T10:00:00Z",
    "is_active": true
  },
  {
    "id": 2,
    "token": "fcm-device-token-2...",
    "platform": "android",
    "device_name": "Pixel 8",
    "created_at": "2026-01-03T10:00:00Z",
    "is_active": true
  }
]
```

**Errors:**

- `401`: Invalid session token

### Notification Types

The server sends these notification types automatically:

| Type                | Trigger                    | Title Example                       |
| ------------------- | -------------------------- | ----------------------------------- |
| `new_question`      | New daily question created | "New Question in MyGroup! 🎯"       |
| `daily_reminder`    | User hasn't answered today | "Don't break your 5-day streak! 🔥" |
| `results_available` | Voting results ready       | "Results are in! 📊"                |

### Mobile App Integration

To receive notifications in your app:

1. **Add Firebase SDK** to your iOS/Android/Web app
2. **Get device token** from Firebase SDK on app startup
3. **Register token** with this API when user logs in
4. **Unregister token** when user logs out

---

## WebSocket

### Live Vote Updates

```text
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
# ═══════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════
DATABASE_URL=postgresql://dontaskus:password@db:5432/dontaskus
REDIS_URL=redis://redis:6379

# ═══════════════════════════════════════════════════════════════════════
# SECURITY - Generate with: openssl rand -base64 32
# ═══════════════════════════════════════════════════════════════════════
SECRET_KEY=your-super-secret-key-change-in-production
ADMIN_JWT_SECRET=another-secret-for-admin-jwt-tokens

# ═══════════════════════════════════════════════════════════════════════
# INITIAL ADMIN USER (auto-created on first startup)
# Change password after first login!
# ═══════════════════════════════════════════════════════════════════════
ADMIN_INITIAL_USERNAME=admin
ADMIN_INITIAL_PASSWORD=changeme123

# ═══════════════════════════════════════════════════════════════════════
# CORS - Comma-separated list of allowed origins
# ═══════════════════════════════════════════════════════════════════════
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# ═══════════════════════════════════════════════════════════════════════
# OPTIONAL SETTINGS
# ═══════════════════════════════════════════════════════════════════════
SESSION_TOKEN_EXPIRY_DAYS=7
LOG_LEVEL=INFO
SCHEDULE_INTERVAL_SECONDS=86400
```

### Environment Variable Reference

| Variable                    | Description                   | Required | Default |
| --------------------------- | ----------------------------- | -------- | ------- |
| `DATABASE_URL`              | PostgreSQL connection string  | Yes      | -       |
| `REDIS_URL`                 | Redis connection string       | Yes      | -       |
| `SECRET_KEY`                | JWT secret for user sessions  | Yes      | -       |
| `ADMIN_JWT_SECRET`          | JWT secret for admin sessions | Yes      | -       |
| `ADMIN_INITIAL_USERNAME`    | Initial admin username        | No       | `admin` |
| `ADMIN_INITIAL_PASSWORD`    | Initial admin password        | Yes      | -       |
| `ALLOWED_ORIGINS`           | CORS allowed origins          | Yes      | -       |
| `SESSION_TOKEN_EXPIRY_DAYS` | User session expiry           | No       | `7`     |
| `LOG_LEVEL`                 | Logging level                 | No       | `INFO`  |
| `SCHEDULE_INTERVAL_SECONDS` | Question scheduling interval  | No       | `86400` |
| `FCM_PROJECT_ID`            | Firebase project ID           | No\*     | -       |
| `FCM_SERVICE_ACCOUNT_JSON`  | Firebase service account JSON | No\*     | -       |

\*Required only if push notifications are enabled

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

## Health Check

Simple health check endpoint to verify the API is running.

```http
GET /health
```

**Response (200):**

```json
{
  "status": "healthy",
  "timestamp": "2025-12-17T10:00:00Z"
}
```

---

<!-- End of Documentation -->
