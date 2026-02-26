# dontAskUs - Complete API Documentation

**Base URL:** `http://localhost:8000` (development)  
**Version:** 1.8.0  
**Last Updated:** February 26, 2026

**IMPORTANT:** All API endpoints require authentication unless explicitly marked as "Public" or "No
Auth". After registration or login, include the access token in the `Authorization: Bearer <token>`
header for all requests.

---

### Verify Email

**Authentication:** None (public endpoint)

Complete registration when email verification is required. Provide the email address used during
signup along with the six-digit verification code sent to that address. This endpoint is rarely used
when the admin toggle `require_email_verification` is off; in that case it acts as a no-op.

```http
POST /api/auth/verify-email
Content-Type: application/json

{
  "email": "alice@example.com",
  "code": "123456"
}
```

**Response (200):**

```json
{ "message": "Email verified successfully" }
```

**Errors:**

- `400` Invalid email or code (expired/used/wrong)

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [User Auth Endpoints](#user-auth-endpoints)
4. [Account Recovery](#account-recovery)
5. [Avatar Upload Endpoints](#avatar-upload-endpoints) 5.1
   [User Settings & Preferences](#user-settings--preferences)
6. [Group Endpoints](#group-endpoints)
7. [Daily Questions & Voting](#daily-questions--voting)
   - [`{member}` Placeholder — Personalized Questions](#member-placeholder--personalized-questions)
   - [`answer_details` — Who Answered What](#answer_details--who-answered-what-all-question-types)
   - [`featured_member` — Personalized Questions](#featured_member--personalized-questions)
8. [Question Sets](#question-sets)
9. [Leaderboard](#leaderboard)
10. [Admin Authentication](#admin-authentication)
11. [Admin: Account Management (Self)](#admin-account-management)
12. [Admin: Dashboard](#admin-dashboard)
13. [Admin: Account Management (Platform Users)](#admin-account-management-platform-users)
14. [Admin: User Management (Group Memberships)](#admin-user-management-group-memberships)
15. [Admin: Group Management](#admin-group-management)
16. [Admin: Question Set Management](#admin-question-set-management)
17. [Admin: Audit Logs](#admin-audit-logs)
18. [Group Creator: Private Question Sets](#group-creator-private-question-sets)
19. [Push Notifications](#push-notifications)
20. [WebSocket — Real-Time Events](#websocket--real-time-events)
    - [Group-Level WebSocket (Recommended)](#group-level-websocket-recommended)
    - [Event Types Reference](#event-types-reference)
    - [Question-Level WebSocket (Legacy)](#question-level-websocket-legacy)
    - [Integration Guide](#websocket-integration-guide)
21. [Error Codes](#error-codes)
22. [Rate Limiting](#rate-limiting)
23. [Health Check](#health-check)

---

## Overview

dontAskUs is a group-based daily question and voting platform. **All features require user
authentication** - users must register an account before they can join groups or participate.

**User Flow:**

1. Register account with email/password (`POST /api/auth/register`)
2. Login to receive JWT access and refresh tokens (`POST /api/auth/login`)
3. Create or join groups using authenticated endpoints
4. Answer daily questions, vote on members/duos/choices
5. View group leaderboards and streaks

**Additional Flows:**

- **Group Creator Flow:** Create groups, manage question sets via creator JWT
- **Instance Admin Flow:** Manage all users, groups, question sets, audit logs with 2FA
- **Group Creator Flow:** Create private question sets (max 5 per group)

### Authentication Required

**All endpoints require authentication** except:

- `/health` - Health check
- `/docs` - API documentation
- `/api/auth/register` - Account registration
- `/api/auth/login` - Account login
- `/api/auth/refresh` - Token refresh
- `/api/admin/login` - Instance admin login
- `/api/admin/2fa` - Instance admin 2FA verification
- `/api/admin/refresh` - Instance admin token refresh

Everything else requires a valid JWT access token.

### Automatic Daily Questions

The backend **automatically generates a new question for each group once per day**:

- Each group has its own **"new day" rollover hour** (`question_hour`, 0–23 UTC). When a group is
  created, this hour is set to approximately the creation hour **±3 hours of random jitter**. This
  means different groups roll over to a new question at different times of day.
- The scheduler runs **every hour** to check all groups and create questions for those whose day has
  rolled over.
- **One question at a time:** When a new question is created, all previous questions for the group
  are automatically deactivated (`is_active = false`). Only one question per group is active at any
  given time.
- **Streak check on rollover:** When a new question is created, the system checks which members did
  **not** answer the previous question and resets their streaks to 0.
- **On-demand fallback:** If the scheduler hasn't run yet (e.g. timing edge-case, server restart),
  the `GET /groups/{group_id}/questions/today` endpoint will **automatically create** the group's
  question on the first request — users never see a stale "no question" state
- Selects questions from assigned question sets (or public templates as fallback)
- Never repeats a question within the same group until all are exhausted (90+ default questions)
- Different groups receive different questions on the same day
- Requires at least 2 members for `member_choice` and `duo_choice` questions
- Sends push notifications to group members (if FCM is configured)

#### Per-Group Day Rollover

A group's "question day" does **not** flip at midnight UTC. Instead, it flips at the group's
`question_hour` UTC. Before that hour, the group is still on the previous calendar day.

**Example:** A group with `question_hour = 14`:

- At 13:59 UTC on Feb 19 → the group's question day is still **Feb 18**
- At 14:00 UTC on Feb 19 → the group's question day is now **Feb 19**, and a new question is created

This ensures each group gets a new question roughly **24 hours after the previous one**, with
natural variation (±3 hours) between groups so they don't all roll over at the same instant.

> **For app developers:** The `question_hour` is internal — you don't need to know it. Just call
> `GET /groups/{group_id}/questions/today` and the backend will always return the correct current
> question for that group. If the group's day has rolled over but no question exists yet, one will
> be created on-demand.

### `{member}` Placeholder — Personalized Questions

Question templates can include the **`{member}` placeholder** in their `question_text`. When the
daily question is generated, `{member}` is replaced with a **randomly chosen group member's name**.

This works with **every question type**: `binary_vote`, `free_text`, `single_choice`,
`member_choice`, and `duo_choice`.

**Examples of `{member}` templates:**

| Template                                           | Type            | Resolved Example                              |
| -------------------------------------------------- | --------------- | --------------------------------------------- |
| `"Do you think {member} could beat a bear?"`       | `binary_vote`   | `"Do you think Charlie could beat a bear?"`   |
| `"What is {member}'s most annoying habit?"`        | `free_text`     | `"What is Alice's most annoying habit?"`      |
| `"Who would {member} call first in an emergency?"` | `member_choice` | `"Who would Bob call first in an emergency?"` |
| `"Rate {member}'s fashion sense"`                  | `binary_vote`   | `"Rate Alice's fashion sense"`                |

**How it works:**

1. The scheduler picks a template that contains `{member}` in its `question_text`
2. A random member of the group is chosen
3. All occurrences of `{member}` in the question text are replaced with that member's display name
4. The resolved text is stored in `DailyQuestion.question_text`
5. The chosen member's ID is stored in `DailyQuestion.featured_member_id`
6. The API response includes `featured_member` (the chosen member's display name)

> **For app developers:** When displaying a `{member}` question, the `featured_member` field tells
> you which group member was randomly selected. You can use this to highlight them in the UI — for
> example, show their avatar next to the question or tag them. The `question_text` already has the
> placeholder resolved, so you can display it directly.

**Creating `{member}` questions (Group Creator):**

When creating a private question set via the Group Creator API, include `{member}` literally in the
`text` field:

```json
{
  "name": "Personalized Questions",
  "questions": [
    {
      "text": "Do you think {member} could survive a zombie apocalypse?",
      "question_type": "binary_vote"
    },
    {
      "text": "What is {member}'s hidden talent?",
      "question_type": "free_text"
    }
  ]
}
```

The `{member}` placeholder is resolved at **question creation time** (when the scheduler picks the
template for a group), not at display time. Each group gets a different random member.

### Authentication Types

| Flow            | Method               | Storage      |
| --------------- | -------------------- | ------------ |
| Users           | JWT (Email/Password) | Bearer Token |
| Group Creators  | JWT (Creator ID)     | Bearer Token |
| Instance Admins | JWT (TOTP optional)  | Bearer Token |

---

## Security Architecture

### Transport Security

- **HTTPS required in production** — passwords are transmitted in JSON request bodies, which are
  encrypted by TLS in transit
- HSTS header (`Strict-Transport-Security`) is automatically added when served over HTTPS
- Auth endpoints return `Cache-Control: no-store, no-cache, must-revalidate` and `Pragma: no-cache`
  to prevent browsers from caching tokens or credentials

### Password Security

- **Hashing:** bcrypt with automatic salt generation (server-side)
- **Requirements:** Minimum 8 characters, at least one uppercase letter, lowercase letter, and digit
- **Maximum length:** 128 characters (prevents bcrypt DoS via extremely long passwords)
- **Timing-safe checks:** Failed logins always perform a dummy bcrypt comparison to prevent email
  enumeration via response timing

### JWT Security

- **Separate secrets:** User and Admin JWT tokens use independent signing secrets (`USER_JWT_SECRET`
  and `SECRET_KEY`)
- **Algorithm:** HS256 (HMAC-SHA256)
- **Claims:** All tokens include `sub`, `type`, `exp`, `iat`, and `jti` (JWT ID for
  uniqueness/future revocation)
- **Insecure default warnings:** Server logs loud warnings if JWT secrets are left at default values

### Brute-Force Protection

| Setting               | Users  | Admins |
| --------------------- | ------ | ------ |
| Max login attempts    | 10     | 5      |
| Lockout duration      | 15 min | 30 min |
| Rate limit (login)    | 10/min | 5/min  |
| Rate limit (register) | 10/min | —      |

### Security Headers

All responses include:

- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy` (restricted to `self` + CDN for Swagger UI)
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HTTPS only)

### Reverse Proxy Support

- Configure `TRUSTED_PROXIES` env var to trust `X-Forwarded-For` headers from specific IPs/CIDRs
- Example: `TRUSTED_PROXIES=172.16.0.0/12` for Docker networks

### Password Reset

- Self-service password reset via email (6-digit code, 15 minute expiry)
- Requires SMTP configuration (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
  `SMTP_FROM_EMAIL` — see `.env.example`)
- Reset codes are bcrypt-hashed before storage (same as passwords)
- Requesting a new code invalidates all previous unused codes
- Successful reset clears any account lockout
- Endpoint always returns `200` regardless of email existence (prevents enumeration)
- Without SMTP configured, the app still works but codes are logged at WARNING level

---

## Authentication

### JWT Tokens (Users)

- Users register with email/password via `/api/auth/register`
- Login via `/api/auth/login` returns access + refresh tokens
- Access Token: `USER_JWT_ACCESS_EXPIRE_MINUTES` (default: 30 minutes)
- Refresh Token: `USER_JWT_REFRESH_EXPIRE_DAYS` (default: 30 days)
- Passed as `Authorization: Bearer <token>` header
- All JWTs include a `jti` (JWT ID) claim for token uniqueness and future revocation support
- Password requirements: min 8 chars, uppercase, lowercase, digit

### Group Creator Identification

- The user who creates a group is stored as `creator_id` on the Group model
- Group creator endpoints verify the requesting user's JWT and check `group.creator_id == user.id`
- No separate admin token is used — the creator's standard JWT is sufficient

### JWT Tokens (Instance Admins)

- Access Token: 60 minutes
- Refresh Token: 7 days
- Passed as `Authorization: Bearer <token>` header
- All JWTs include a `jti` (JWT ID) claim for token uniqueness and future revocation support
- TOTP 2FA optional (can be enabled in account settings)

---

## User Auth Endpoints

> **Configurable behavior:** An admin may require email verification for new registrations. When
> this setting is enabled, registered accounts are marked unverified, and users must call
> `POST /api/auth/verify-email` using the code sent to their inbox before they can login. See
> "Admin: Application Settings" for details.
>
> **Cleanup note:** any account that remains unverified for more than 24 hours is automatically
> deleted by the server's background scheduler. This helps prevent bots from creating large numbers
> of inactive accounts.

### Register

**Authentication:** None (public endpoint)

Create a new account with email and password.

```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "alice@example.com",
  "password": "SecurePass1!",
  "display_name": "Alice"
}
```

**Response (200):**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "account_id": "uuid",
  "display_name": "Alice",
  "email": "alice@example.com",
  "avatar_url": null,
  "color_avatar": null,
  "answer_streak": 0,
  "longest_answer_streak": 0
}
```

| Field                   | Type           | Description                                  |
| ----------------------- | -------------- | -------------------------------------------- |
| `avatar_url`            | string \| null | Full URL to the user's uploaded avatar image |
| `color_avatar`          | string \| null | Hex color fallback avatar (e.g. `"#BB8FCE"`) |
| `answer_streak`         | int            | Current consecutive-question answer streak   |
| `longest_answer_streak` | int            | All-time longest streak                      |

> **Note:** For newly registered accounts (no group memberships yet), `avatar_url` and
> `color_avatar` will be `null`, and streaks will be `0`. These fields are aggregated from the
> user's group memberships.

**Errors:**

- `400` Password too weak (min 8 chars, uppercase, lowercase, digit)
- `409` Email already registered

> **Behavior note:** If the **Require email verification** setting in the admin panel is enabled,
> the server will not return JWT tokens from this endpoint. Instead you'll receive a message
> instructing the user to verify their email. A six‑digit verification code is emailed to the
> provided address; the code must be submitted via `POST /api/auth/verify-email` before the user can
> log in.

---

### Login

**Authentication:** None (public endpoint)

Authenticate with email and password.

> **Note:** If email verification is required (admin setting) and the account has not been verified
> yet, this endpoint will respond with `403` and `"Email address not verified"`.

```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "alice@example.com",
  "password": "SecurePass1!"
}
```

**Response (200):**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "account_id": "uuid",
  "display_name": "Alice",
  "email": "alice@example.com",
  "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp",
  "color_avatar": "#BB8FCE",
  "answer_streak": 5,
  "longest_answer_streak": 12
}
```

| Field                   | Type           | Description                                       |
| ----------------------- | -------------- | ------------------------------------------------- |
| `avatar_url`            | string \| null | Full URL to user's uploaded avatar (null if none) |
| `color_avatar`          | string \| null | Hex color fallback from first group membership    |
| `answer_streak`         | int            | Max current streak across all group memberships   |
| `longest_answer_streak` | int            | Max all-time streak across all group memberships  |

**Errors:**

- `401` Invalid email or password
- `403` Account locked (too many failed attempts)

---

### Refresh Token

**Authentication:** Requires valid refresh_token

Get a new access token using a refresh token.

```http
POST /api/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ..."
}
```

**Response (200):**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "account_id": "uuid",
  "display_name": "Alice",
  "email": "alice@example.com",
  "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp",
  "color_avatar": "#BB8FCE",
  "answer_streak": 5,
  "longest_answer_streak": 12
}
```

The response includes the same `avatar_url`, `color_avatar`, `answer_streak`, and
`longest_answer_streak` fields as login.

**Errors:**

- `401`: Invalid or expired refresh token

---

### Get Current User

**Authentication:** Required (JWT Bearer token)

Get the authenticated user's account info.

```http
GET /api/auth/me
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "account": {
    "account_id": "uuid",
    "email": "alice@example.com",
    "display_name": "Alice",
    "is_active": true,
    "is_verified": false,
    "created_at": "2026-02-18T00:00:00Z",
    "last_login": "2026-02-18T12:00:00Z",
    "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp",
    "color_avatar": "#BB8FCE",
    "answer_streak": 5,
    "longest_answer_streak": 12
  },
  "groups": [
    {
      "user_id": "uuid",
      "group_id": "group-uuid",
      "group_name": "My Group",
      "display_name": "Alice",
      "color_avatar": "#BB8FCE",
      "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp",
      "answer_streak": 5,
      "longest_answer_streak": 12,
      "joined_at": "2026-02-01T10:00:00Z"
    }
  ]
}
```

| Field (account level)   | Type           | Description                                        |
| ----------------------- | -------------- | -------------------------------------------------- |
| `avatar_url`            | string \| null | Uploaded avatar from first membership that has one |
| `color_avatar`          | string \| null | Color avatar from first group membership           |
| `answer_streak`         | int            | Max current streak across all memberships          |
| `longest_answer_streak` | int            | Max all-time longest streak across all memberships |

Each group membership also includes per-group `avatar_url`, `color_avatar`, `answer_streak`,
`longest_answer_streak`, and `joined_at`.

**Errors:**

- `401`: Authorization header required / Invalid token

---

### Change Password

**Authentication:** Required (JWT Bearer token)

Change the authenticated user's password.

```http
POST /api/auth/change-password
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "current_password": "OldPass1!",
  "new_password": "NewPass1!"
}
```

**Response (200):**

```json
{
  "message": "Password changed successfully"
}
```

**Errors:**

- `401`: Authorization header required / Invalid token / Incorrect current password
- `400`: New password doesn't meet requirements (min 8 chars, uppercase, lowercase, digit)

---

### Forgot Password (Request Reset Code)

**Authentication:** None (public endpoint)

Request a password reset code. A 6-digit code is sent to the email address. Always returns `200`
regardless of whether the email exists (prevents email enumeration).

> **Note:** Requires SMTP to be configured (see `.env.example`). Without SMTP, the code is logged at
> WARNING level for development/debugging.

```http
POST /api/auth/forgot-password
Content-Type: application/json

{
  "email": "alice@example.com"
}
```

**Response (200):**

```json
{
  "message": "If an account with that email exists, a reset code has been sent."
}
```

**Rate limit:** 5/minute

---

### Reset Password (Use Reset Code)

**Authentication:** None (public endpoint)

Reset the account password using the 6-digit code received via email.

```http
POST /api/auth/reset-password
Content-Type: application/json

{
  "email": "alice@example.com",
  "token": "312863",
  "new_password": "MyNewPass1"
}
```

**Response (200):**

```json
{
  "message": "Password has been reset successfully. You can now log in with your new password."
}
```

**Errors:**

- `400`: Invalid or expired reset code
- `422`: New password doesn't meet requirements (min 8 chars, uppercase, lowercase, digit)

**Notes:**

- Reset codes expire after 15 minutes
- Only the most recent unused code is valid; requesting a new code invalidates previous ones
- A successful reset also clears any account lockout

---

### Join Group

Join an existing group using an invite code.

```http
POST /api/auth/groups/join
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "invite_code": "ABC123",
  "display_name": "Alice",
  "color_avatar": "#3B82F6"
}
```

**Response (200):**

```json
{
  "user_id": "uuid",
  "group_id": "group-uuid",
  "group_name": "My Group",
  "display_name": "Alice",
  "color_avatar": "#BB8FCE",
  "avatar_url": null,
  "answer_streak": 0,
  "longest_answer_streak": 0,
  "joined_at": "2026-02-18T10:00:00Z"
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
- `409` Display name already taken in group or already a member

---

### Create Group

**Authentication:** Required (JWT Bearer token)

Create a new group and automatically join as the first member. The creator is identified by
`creator_id` on the group model.

```http
POST /api/auth/groups/create
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "My New Group"
}
```

**Response (200):**

```json
{
  "id": 1,
  "group_id": "group-uuid",
  "name": "My New Group",
  "invite_code": "XYZ789",
  "created_at": "2026-02-09T10:00:00Z",
  "member_count": 1
}
```

**Notes:**

- Creator is automatically joined with their account's `display_name`
- Creator gets a random color avatar
- Default question set is automatically assigned
- A daily question is automatically created for the group
- The group creator is identified by `creator_id` — no separate admin token is needed
- Group creator endpoints use the creator's JWT for authentication

**Errors:**

- `401` Authorization header required / Invalid token

---

## Account Recovery

If a user forgets their password:

1. **Admin can reset password** via `POST /api/admin/users/{user_id}/reset-password`
2. The user's **data is preserved** (streaks, votes, display name, avatar, etc.)
3. Account lockout is cleared on password reset

### Streak System

Answer streaks track how many consecutive questions a user has answered:

- **+1 per question answered:** Each time a user answers a daily question, their streak increases by
  1
- **Reset on missed question:** When a new question appears for the group and the user **did not
  answer** the previous question, their streak resets to 0
- **Editing an answer does not re-increment:** Re-submitting or editing an answer for the same
  question does not increase the streak again
- **Longest streak** is preserved for historical tracking (never decreases)
- **Group streak** is the highest current streak among all group members
- **Group longest streak** is the highest all-time streak among all group members

> **For app developers:** Streaks are per-group — a user has a separate streak for each group they
> belong to. The account-level `answer_streak` shown on login/register is the max across all groups.

---

## Avatar Upload Endpoints

Users can upload custom profile avatars. Images are automatically processed, resized, and converted
to WebP format for optimal storage and delivery.

### Upload Avatar

**Authentication:** Required (JWT Bearer token - must match user_id in URL)

Upload or replace a user's profile avatar image.

```http
POST /api/users/{user_id}/avatar
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: <image file>
```

**Request:**

- File must be uploaded as `multipart/form-data` with field name `file`
- Supported formats: **JPEG, PNG, GIF, WebP, BMP, TIFF, ICO, HEIC, HEIF, AVIF, SVG**
- Maximum file size: 2MB
- Image is automatically:
  - Resized to max 256x256 pixels (maintains aspect ratio)
  - Converted to WebP format
  - Transparency converted to white background
- The `user_id` in the URL must match the authenticated user's ID
- Mobile browsers that send `application/octet-stream` as the content type are also accepted (the
  server validates the actual file contents via magic bytes)

**Response (200):**

```json
{
  "message": "Avatar uploaded successfully",
  "avatar_url": "https://api.example.com/uploads/avatars/user123_abc456.webp",
  "avatar_filename": "user123_abc456.webp",
  "uploaded_at": "2026-02-09T10:00:00Z"
}
```

**Errors:**

- `400` No file provided
- `400` File too large (max 2MB)
- `400` Invalid file type (only JPEG, PNG, GIF, WebP, BMP, TIFF, ICO, HEIC, HEIF, AVIF, SVG allowed)
- `400` Invalid or corrupted image file
- `401` Authorization header required / Invalid token / User ID mismatch
- `500` Failed to save avatar file

**Example (curl):**

```bash
curl -X POST "https://api.example.com/api/users/{user_id}/avatar" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/avatar.jpg"
```

**Example (JavaScript):**

```javascript
const formData = new FormData();
formData.append("file", imageFile);

const response = await fetch(`${API_URL}/api/users/${userId}/avatar`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${token}`
  },
  body: formData
});
```

---

### Delete Avatar

**Authentication:** Required (JWT Bearer token - must match user_id in URL)

Remove a user's profile avatar, reverting to the color avatar.

```http
DELETE /api/users/{user_id}/avatar
Authorization: Bearer <access_token>
```

**Notes:**

- The `user_id` in the URL must match the authenticated user's ID
- After deletion, client should use the returned `color_avatar` for display

**Response (200):**

```json
{
  "message": "Avatar deleted successfully",
  "color_avatar": "#3B82F6"
}
```

**Errors:**

- `401` Authorization header required / Invalid token / User ID mismatch
- `404` No avatar to delete

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

## User Settings & Preferences

These endpoints allow a user to manage per-group settings such as display name and notification
preferences. Every route under `/api/users/{user_id}` requires the JWT access token for the matching
`user_id`.

### Get Current Membership Settings

**Authentication:** Required (JWT Bearer token - must match `user_id` in URL)

Retrieve the membership-specific settings for the authenticated user.

```http
GET /api/users/{user_id}/settings
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "user_id": "abcd-1234",
  "display_name": "Alice",
  "avatar_filename": "alice.webp",
  "email_on_new_question": false,
  "email_on_reminder": true,
  "push_notifications_enabled": false
}
```

`push_notifications_enabled` is a new flag (default `false`) indicating whether the user has opted
in to receive system-level Firebase push notifications. It is handled separately from device token
registration.

### Update Display Name

**Authentication:** Required (JWT Bearer token - must match `user_id` in URL)

Change the user's display name within a group. Names must be unique within the group and between 1
and 50 characters long.

```http
PUT /api/users/{user_id}/display-name
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "display_name": "NewName"
}
```

**Response (200):**

```json
{
  "message": "Display name updated",
  "display_name": "NewName"
}
```

**Errors:** `400` invalid name, `409` name already taken in group.

### Update Email Notification Preferences

**Authentication:** Required (JWT Bearer token - must match `user_id` in URL)

Toggle email delivery for new-question notifications and reminder emails. Both options default to
`false` for new memberships.

```http
PUT /api/users/{user_id}/email-settings
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "email_on_new_question": true,
  "email_on_reminder": false
}
```

Only boolean values are allowed; omitted keys are unchanged.

**Response (200):**

```json
{
  "message": "Email settings updated",
  "email_on_new_question": true,
  "email_on_reminder": false
}
```

### Update Push Notification Preference

**Authentication:** Required (JWT Bearer token - must match `user_id` in URL)

Controls whether the user should receive system-level push notifications from the server (Firebase
Cloud Messaging). Defaults to `false` to respect privacy.

```http
PUT /api/users/{user_id}/push-settings
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "push_notifications_enabled": true
}
```

Only a boolean value is accepted; non-boolean requests return `400`.

**Response (200):**

```json
{
  "message": "Push settings updated",
  "push_notifications_enabled": true
}
```

The scheduler will skip sending push notifications for groups where the user's membership has this
flag set to `false`, even if device tokens are registered.

---

## Group Endpoints

### Create Group

**Authentication:** Required (JWT Bearer token)

Create a new group. The creator is automatically added as the first member and identified by
`creator_id` on the group model.

```http
POST /api/auth/groups/create
Authorization: Bearer <access_token>
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
  "created_at": "2026-02-09T10:00:00Z",
  "member_count": 1
}
```

**Notes:**

- Default question set is automatically assigned to new groups
- A daily question is automatically created for the group
- Creator is auto-joined as first member

**Errors:**

- `401` Authorization header required / Invalid token
- `400` Invalid group name

---

### Delete Group

**Authentication:** Required (JWT Bearer token, must be group creator/owner)

Permanently delete a group and all associated data. Only the group creator (owner) can delete their
group. This action is irreversible.

**What gets deleted:**

- All members (user memberships in this group)
- All daily questions and votes
- All streaks and device tokens
- Group analytics and question set assignments

**What is NOT deleted:**

- Member accounts themselves (only their membership in this group)
- Question sets created by the group (ownership is cleared, sets become orphaned)

```http
DELETE /api/auth/groups/{group_id}
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "message": "Group 'My Awesome Group' has been permanently deleted"
}
```

**WebSocket Event:** Broadcasts `group_deleted` to all connected group clients:

```json
{
  "type": "group_deleted",
  "timestamp": "2026-02-09T10:00:00Z",
  "data": {
    "group_id": "uuid",
    "group_name": "My Awesome Group"
  }
}
```

**Errors:**

- `401` Authorization header required / Invalid token
- `403` You are not a member of this group
- `403` Only the group creator can delete this group
- `404` Group not found

---

### Get Group by Invite Code

**Authentication:** Required (JWT Bearer token)

Get basic group information using an invite code. Used when a user wants to preview a group before
joining.

```http
GET /api/groups/{invite_code}
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "id": 1,
  "group_id": "uuid",
  "name": "My Awesome Group",
  "invite_code": "ABC123",
  "created_at": "2026-02-09T10:00:00Z",
  "member_count": 5
}
```

**Errors:**

- `401` Authorization header required / Invalid token
- `404` Group not found

---

### Get Group Info

**Authentication:** Required (JWT Bearer token + Group Membership)

Get complete group information. Requires the authenticated user to be a member of the group.

```http
GET /api/groups/{group_id}/info
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "id": 1,
  "group_id": "uuid",
  "name": "My Awesome Group",
  "invite_code": "ABC123",
  "member_count": 5,
  "created_at": "2026-02-09T10:00:00Z"
}
```

**Errors:**

- `401` Authorization header required / Invalid token
- `403` You are not a member of this group
- `404` Group not found

---

### List Group Members

**Authentication:** Required (JWT Bearer token + Group Membership)

Get all members in a group including their streaks. User must be a member of the group.

```http
GET /api/groups/{group_id}/members
Authorization: Bearer <access_token>
```

**Response (200):**

```json
[
  {
    "user_id": "uuid",
    "display_name": "Alice",
    "color_avatar": "#3B82F6",
    "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp",
    "created_at": "2026-02-09T10:00:00Z",
    "answer_streak": 2,
    "longest_answer_streak": 5
  }
]
```

**Errors:**

- `401` Authorization header required / Invalid token
- `403` You are not a member of this group
- `404` Group not found

---

## Leaderboard

### Get Group Leaderboard

**Authentication:** Required (JWT Bearer token + Group Membership)

Get leaderboard sorted by answer streak. User must be a member of the group to view streaks.
Includes the group streak (highest current streak among all members) and group longest streak.

```http
GET /api/groups/{group_id}/leaderboard
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "group_streak": 15,
  "group_longest_streak": 20,
  "members": [
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
      "avatar_url": null,
      "answer_streak": 10,
      "longest_answer_streak": 12
    }
  ]
}
```

| Field                             | Type  | Description                                                |
| --------------------------------- | ----- | ---------------------------------------------------------- |
| `group_streak`                    | int   | Highest current streak among all group members             |
| `group_longest_streak`            | int   | Highest all-time streak among all group members            |
| `members`                         | array | List of members sorted by streak                           |
| `members[].answer_streak`         | int   | Current consecutive-question answer streak for this member |
| `members[].longest_answer_streak` | int   | All-time longest streak for this member                    |

**Notes:**

- Results sorted by `answer_streak` descending, then by `longest_answer_streak`
- User must be a member of the group
- Streaks are only visible to group members
- `group_streak` is useful for displaying a group-wide streak counter in the UI

**Errors:**

- `401` Authorization header required / Invalid token
- `403` You are not a member of this group
- `404` Group not found

---

## Daily Questions & Voting

**Note:** Questions are automatically generated daily by the server. See
[Automatic Daily Questions](#automatic-daily-questions) in Overview. The endpoints below are for
manual creation (admin override) or retrieving the current question.

### Question Types

| Type            | Options Source         | Allow Multiple | `{member}` Compatible | Notes                         |
| --------------- | ---------------------- | -------------- | --------------------- | ----------------------------- |
| `binary_vote`   | Yes/No or custom       | No             | ✅ Yes                | Simple binary choice          |
| `single_choice` | Custom list            | No             | ✅ Yes                | Single selection from options |
| `member_choice` | Group members          | Optional       | ✅ Yes                | Choose member(s) from group   |
| `duo_choice`    | Generated member pairs | No             | ✅ Yes                | Choose from random duos       |
| `free_text`     | None                   | N/A            | ✅ Yes                | Open-ended text response      |

> **`{member}` placeholder:** Any question type can include `{member}` in its template text. It is
> replaced with a random group member's display name when the daily question is created. See
> [`{member}` Placeholder](#member-placeholder--personalized-questions) for details.

---

### Set Today's Question (Instance Admin Only)

**Authentication:** Instance Admin JWT (Bearer token)

Instance admins can manually override today's question for a group. This deletes any existing
question and votes for today and creates a new one.

```http
POST /api/admin/groups/{group_id}/set-today-question
Authorization: Bearer <admin_access_token>
```

**Response (200):**

```json
{
  "message": "Today's question set successfully",
  "question_id": "uuid",
  "question_text": "Who is the funniest?",
  "question_type": "member_choice",
  "options": ["Alice", "Bob", "Charlie"]
}
```

**Notes:**

- Only instance admins can set questions — users cannot manually change questions
- Questions are automatically assigned on group creation and rotate daily
- Uses integer group ID (from admin groups list)

**Errors:**

- `401` Admin authentication required
- `400` Unable to generate question (not enough members or templates)
- `404` Group not found

---

### Get Today's Question

**Authentication:** Required (JWT Bearer token + Group Membership)

Get the current day's question for a group. User must be a member of the group.

```http
GET /api/groups/{group_id}/questions/today
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "id": 1,
  "question_id": "uuid",
  "question_text": "Do you think Charlie could beat a bear in a fight?",
  "question_type": "binary_vote",
  "options": ["Yes", "No"],
  "option_counts": {
    "Yes": 4,
    "No": 2
  },
  "question_date": "2026-02-19T00:00:00Z",
  "is_active": true,
  "total_votes": 6,
  "allow_multiple": false,
  "user_vote": "Yes",
  "user_text_answer": null,
  "text_answers": null,
  "answer_details": [
    {
      "display_name": "Alice",
      "answer": "Yes",
      "text_answer": null,
      "color_avatar": "#FF6B6B",
      "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp"
    },
    {
      "display_name": "Bob",
      "answer": "No",
      "text_answer": null,
      "color_avatar": "#4ECDC4",
      "avatar_url": null
    },
    {
      "display_name": "Charlie",
      "answer": "Yes",
      "text_answer": null,
      "color_avatar": "#45B7D1",
      "avatar_url": null
    }
  ],
  "featured_member": "Charlie",
  "user_streak": 3,
  "longest_streak": 5
}
```

#### Response Field Reference

| Field              | Type                       | Description                                                                                     |
| ------------------ | -------------------------- | ----------------------------------------------------------------------------------------------- |
| `question_id`      | string                     | UUID of the question (use this for submitting answers)                                          |
| `question_text`    | string                     | The resolved question text (any `{member}` placeholder already replaced)                        |
| `question_type`    | string                     | One of: `binary_vote`, `single_choice`, `member_choice`, `duo_choice`, `free_text`              |
| `options`          | string[] \| null           | Available answer choices (`null` for `free_text`)                                               |
| `option_counts`    | object \| null             | Vote count per option (e.g. `{"Yes": 4, "No": 2}`)                                              |
| `total_votes`      | int                        | Total number of users who have answered                                                         |
| `allow_multiple`   | bool                       | Whether multi-select is allowed for this question                                               |
| `user_vote`        | string \| string[] \| null | Current user's answer. `null` = not yet answered. Array if `allow_multiple` is true             |
| `user_text_answer` | string \| null             | Current user's free-text answer (only for `free_text` questions)                                |
| `text_answers`     | object[] \| null           | All free-text answers with avatars (only for `free_text` — see below)                           |
| `answer_details`   | object[] \| null           | **Who answered what** — every vote with user info (all question types — see below)              |
| `featured_member`  | string \| null             | Display name of the randomly chosen member if `{member}` placeholder was used, otherwise `null` |
| `user_streak`      | int                        | Current user's consecutive-day answer streak                                                    |
| `longest_streak`   | int                        | Current user's all-time longest streak                                                          |

#### `answer_details` — Who Answered What (All Question Types)

The `answer_details` array is returned for **every question type** once at least one user has
answered. It lets you show each group member's individual answer alongside their avatar.

```json
"answer_details": [
  {
    "display_name": "Alice",
    "answer": "Yes",
    "text_answer": null,
    "color_avatar": "#FF6B6B",
    "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp"
  },
  {
    "display_name": "Bob",
    "answer": ["Alice", "Charlie"],
    "text_answer": null,
    "color_avatar": "#4ECDC4",
    "avatar_url": null
  }
]
```

| Field          | Type                       | Description                                                                                                         |
| -------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `display_name` | string                     | The member who voted                                                                                                |
| `answer`       | string \| string[] \| null | Their choice. String for single-select, array for `allow_multiple`. For `free_text`, this equals the `text_answer`. |
| `text_answer`  | string \| null             | The free-text response (only present for `free_text` questions)                                                     |
| `color_avatar` | string                     | Hex color fallback avatar (e.g. `"#FF6B6B"`)                                                                        |
| `avatar_url`   | string \| null             | Full URL to uploaded avatar image, or `null`                                                                        |

> **For app developers:** Use `answer_details` to build a "who voted what" UI. For example, show
> each member's avatar next to their answer, or group members by their chosen option. This is
> returned as `null` when nobody has answered yet, so check for `null` before iterating.

> **Privacy note:** `answer_details` is visible to all group members — there are no anonymous votes.

#### `featured_member` — Personalized Questions

When a question was generated from a template containing the `{member}` placeholder,
`featured_member` contains the display name of the randomly selected group member.

> **For app developers:** If `featured_member` is not `null`, consider highlighting that member in
> the question UI — for example, show their avatar next to the question text, or apply a special
> "featured" badge.

#### `text_answers` — Free-Text Responses

For `free_text` questions only, `text_answers` contains all submitted answers with user info:

```json
"text_answers": [
  {
    "display_name": "Alice",
    "text_answer": "I love coding!",
    "color_avatar": "#BB8FCE",
    "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp"
  },
  {
    "display_name": "Bob",
    "text_answer": "Hiking and photography",
    "color_avatar": "#4ECDC4",
    "avatar_url": null
  }
]
```

> **Tip:** For `free_text` questions, both `text_answers` and `answer_details` are populated.
> `text_answers` is a simpler structure focused on the text; `answer_details` includes the `answer`
> field as well. Use whichever fits your UI better.

**Errors:**

- `401` Authorization header required / Invalid token
- `403` You are not a member of this group
- `404` No question for today / Group not found

---

### Submit Answer/Vote

**Authentication:** Required (JWT Bearer token + Group Membership)

Submit an answer to the current question. Increments streak by 1 on first submission for this
question.

```http
POST /api/groups/{group_id}/questions/{question_id}/answer
Authorization: Bearer <access_token>
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
  "success": true,
  "question_type": "binary_vote",
  "vote_count_a": 4,
  "vote_count_b": 2,
  "total_votes": 6,
  "option_counts": {
    "Yes": 4,
    "No": 2
  },
  "options": ["Yes", "No"],
  "user_answer": "Yes",
  "current_streak": 4,
  "longest_streak": 5,
  "answer_details": [
    {
      "display_name": "Alice",
      "answer": "Yes",
      "text_answer": null,
      "color_avatar": "#FF6B6B",
      "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp"
    },
    {
      "display_name": "Bob",
      "answer": "No",
      "text_answer": null,
      "color_avatar": "#4ECDC4",
      "avatar_url": null
    }
  ],
  "featured_member": "Charlie"
}
```

The submit response **always** includes `answer_details` (the complete list of who answered what)
and `featured_member` (the randomly selected member, or `null` if this question doesn't use the
`{member}` placeholder).

For `free_text` questions, the response also includes `text_answers`:

```json
{
  "success": true,
  "question_type": "free_text",
  "total_votes": 2,
  "text_answers": [
    {
      "display_name": "Alice",
      "text_answer": "I love coding!",
      "color_avatar": "#BB8FCE",
      "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp"
    }
  ],
  "answer_details": [
    {
      "display_name": "Alice",
      "answer": "I love coding!",
      "text_answer": "I love coding!",
      "color_avatar": "#BB8FCE",
      "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp"
    }
  ],
  "featured_member": null
}
```

**Validation:**

- `answer` must be in `options` for choice-based types
- Array required when `allow_multiple` is true
- Can update answer by resubmitting (replaces previous vote)
- Streaks only increment on first answer per question

**Errors:**

- `400` Invalid answer / Answer required / Only one selection allowed
- `401` Authorization header required / Invalid token
- `403` User not in this group
- `404` Question not found

---

### Get Question History

**Authentication:** Required (JWT Bearer token + Group Membership)

Retrieve paginated history of all questions in a group (most recent first). User must be a member.

```http
GET /api/groups/{group_id}/questions/history?skip=0&limit=20
Authorization: Bearer <access_token>
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
      "question_text": "Do you think Charlie could beat a bear?",
      "question_type": "binary_vote",
      "option_a": "Yes",
      "option_b": "No",
      "options": ["Yes", "No"],
      "option_counts": {
        "Yes": 4,
        "No": 2
      },
      "question_date": "2026-02-19T00:00:00Z",
      "is_active": false,
      "vote_count_a": 4,
      "vote_count_b": 2,
      "total_votes": 6,
      "allow_multiple": false,
      "user_vote": "Yes",
      "answer_details": [
        {
          "display_name": "Alice",
          "answer": "Yes",
          "text_answer": null,
          "color_avatar": "#FF6B6B",
          "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp"
        },
        {
          "display_name": "Bob",
          "answer": "No",
          "text_answer": null,
          "color_avatar": "#4ECDC4",
          "avatar_url": null
        }
      ],
      "featured_member": "Charlie"
    },
    {
      "question_id": "uuid-2",
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
      "question_date": "2026-02-18T00:00:00Z",
      "is_active": false,
      "vote_count_a": 0,
      "vote_count_b": 0,
      "total_votes": 7,
      "allow_multiple": false,
      "user_vote": "Alice",
      "answer_details": [
        {
          "display_name": "Alice",
          "answer": "Bob",
          "text_answer": null,
          "color_avatar": "#FF6B6B",
          "avatar_url": "https://api.example.com/uploads/avatars/abc123.webp"
        },
        {
          "display_name": "Bob",
          "answer": "Alice",
          "text_answer": null,
          "color_avatar": "#4ECDC4",
          "avatar_url": null
        }
      ],
      "featured_member": null
    }
  ]
}
```

Each history entry includes `answer_details` (who answered what) and `featured_member` (the randomly
chosen member if the question used the `{member}` placeholder, otherwise `null`).

For `free_text` questions in history, each entry also includes `text_answers`:

```json
{
  "question_id": "uuid-3",
  "question_text": "What is Alice's most annoying habit?",
  "question_type": "free_text",
  "featured_member": "Alice",
  "text_answers": [
    {
      "display_name": "Bob",
      "text_answer": "She always corrects my grammar",
      "color_avatar": "#4ECDC4",
      "avatar_url": null
    }
  ],
  "answer_details": [
    {
      "display_name": "Bob",
      "answer": "She always corrects my grammar",
      "text_answer": "She always corrects my grammar",
      "color_avatar": "#4ECDC4",
      "avatar_url": null
    }
  ]
}
```

**Notes:**

- Results are ordered by `question_date` descending (most recent first)
- Includes both active and inactive questions
- Authentication required (JWT Bearer token + group membership)
- Use `skip` and `limit` for pagination
- `answer_details` is `null` if no one has answered that question
- `featured_member` is `null` for questions that didn't use the `{member}` placeholder

**Errors:**

- `404` Group not found

---

## Question Sets

### Create Question Set

**Authentication:** Required (JWT Bearer token)

Create a new question set. Any authenticated user can create sets.

```http
POST /api/question-sets
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "Icebreakers",
  "description": "Fun conversation starters",
  "is_public": true,
  "template_ids": ["template-uuid-1", "template-uuid-2"]
}
```

**Response (200):**

```json
{
  "set_id": "uuid",
  "name": "Icebreakers",
  "description": "Fun conversation starters",
  "is_public": true,
  "templates": [
    {
      "template_id": "uuid",
      "category": "Default",
      "question_text": "What's your superpower?",
      "question_type": "free_text",
      "allow_multiple": false,
      "is_public": true,
      "created_at": "2026-02-09T10:00:00Z"
    }
  ],
  "created_at": "2026-02-09T10:00:00Z"
}
```

**Errors:**

- `401` Authorization header required / Invalid token

---

### List Public Question Sets

**Authentication:** Required (JWT Bearer token)

Get all public question sets with their templates.

```http
GET /api/question-sets
Authorization: Bearer <access_token>
```

**Response (200):**

```json
[
  {
    "set_id": "uuid",
    "name": "Icebreakers",
    "description": "Fun conversation starters",
    "is_public": true,
    "created_at": "2026-02-09T10:00:00Z",
    "templates": [
      {
        "template_id": "uuid-1",
        "category": "Default",
        "question_text": "What's your superpower?",
        "option_a_template": null,
        "option_b_template": null,
        "question_type": "free_text",
        "allow_multiple": false,
        "is_public": true,
        "created_at": "2026-02-09T10:00:00Z"
      },
      {
        "template_id": "uuid-2",
        "category": "Default",
        "question_text": "Do you think {member} could beat a bear in a fight?",
        "option_a_template": null,
        "option_b_template": null,
        "question_type": "binary_vote",
        "allow_multiple": false,
        "is_public": true,
        "created_at": "2026-02-09T10:00:00Z"
      }
    ]
  }
]
```

> **Note:** Templates containing `{member}` in the `question_text` will have the placeholder
> replaced with a random group member's name when the scheduler creates a daily question. The raw
> template text is returned as-is in this listing.

**Errors:**

- `401` Authorization header required / Invalid token

---

### Get Question Set Details

**Authentication:** Required (JWT Bearer token)

Get a single question set by ID with all templates.

```http
GET /api/question-sets/{set_id}
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "set_id": "uuid",
  "name": "Icebreakers",
  "description": "Fun conversation starters",
  "is_public": true,
  "created_at": "2026-02-09T10:00:00Z",
  "templates": [
    {
      "template_id": "uuid",
      "category": "Default",
      "question_text": "What's your superpower?",
      "option_a_template": null,
      "option_b_template": null,
      "question_type": "free_text",
      "allow_multiple": false,
      "is_public": true,
      "created_at": "2026-02-09T10:00:00Z"
    }
  ]
}
```

**Errors:**

- `401` Authorization header required / Invalid token
- `404` Question set not found

---

### Assign Sets to Group (Admin)

**Authentication:** Group Creator JWT (Bearer token)

Assign question sets to a group. The group will use these sets for daily question generation. Only
the group creator can assign question sets.

```http
POST /api/groups/{group_id}/question-sets
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "question_set_ids": ["set-uuid-1", "set-uuid-2"],
  "replace": false
}
```

**Parameters:**

- `question_set_ids`: Array of question set UUIDs to assign
- `replace`: If `true`, removes all existing assignments first

**Response (200):**

```json
{
  "group_id": "uuid",
  "question_sets": [
    {
      "set_id": "uuid",
      "name": "Icebreakers",
      "is_active": true
    }
  ]
}
```

**Errors:**

- `401` Authentication required
- `403` Only group creator can assign question sets
- `404` Group not found

---

### List Group Question Sets

**Authentication:** Required (JWT Bearer token + Group Membership)

Get all question sets assigned to a group. User must be a member of the group.

```http
GET /api/groups/{group_id}/question-sets
Authorization: Bearer <access_token>
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
      "is_active": true
    }
  ]
}
```

**Errors:**

- `401` Authorization header required / Invalid token
- `403` You are not a member of this group
- `404` Group not found

---

## Admin Authentication

Instance admins have full platform access with optional 2FA security.

**Authentication:** Admin endpoints (except `/api/admin/login`, `/api/admin/2fa`,
`/api/admin/refresh`) require the `Authorization: Bearer <admin_access_token>` header with a valid
admin JWT token.

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

**Authentication:** None (public endpoint)

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

**Authentication:** Requires temp_token from Step 1

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

### Refresh Token (Admin)

**Authentication:** Requires valid refresh_token

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

**Authentication:** Required (Admin JWT Bearer token)

```http
POST /api/admin/logout
Authorization: Bearer <admin_access_token>
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

**Authentication:** Required (Admin JWT Bearer token)

```http
GET /api/admin/profile
Authorization: Bearer <admin_access_token>
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

### Change Password (Admin)

```http
POST /api/admin/account/change-password
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "current_password": "oldPass123!",
  "new_password": "newStrongPass456!"
}
```

**Response (200):**

```json
{
  "message": "Password updated successfully"
}
```

**Errors:**

- `400` Current password incorrect
- `422` New password too weak (min 8 chars, uppercase, lowercase, digit)

---

## Admin: Application Settings

The backend exposes a simple settings API consumed by the admin UI. Currently the only configurable
option is the requirement that users verify their email before they may log in.

Unverified accounts are also automatically purged after 24 hours by a periodic background job,
regardless of this setting; the toggle merely controls whether verification is enforced at login
time.

### Get Settings

```http
GET /api/admin/settings
Authorization: Bearer <admin_access_token>
```

**Response (200):**

```json
{ "require_email_verification": false }
```

### Update Settings

```http
PUT /api/admin/settings
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{ "require_email_verification": true }
```

**Response (200):**

```json
{ "require_email_verification": true }
```

Changes are audited under `SETTINGS_UPDATE`.

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

## Admin: Account Management (Platform Users)

Accounts represent platform-level user identities (email + password). An account can exist without
being in any group, and can be a member of multiple groups.

### List All Accounts

**Authentication:** Required (Admin JWT Bearer token)

```http
GET /api/admin/accounts?limit=50&offset=0&search=alice
Authorization: Bearer <admin_access_token>
```

**Query Parameters:**

- `limit`: 1-500 (default: 50)
- `offset`: Starting position (default: 0)
- `search`: Optional search by email or display name

**Response (200):**

```json
{
  "accounts": [
    {
      "id": 1,
      "account_id": "uuid-string",
      "email": "alice@example.com",
      "display_name": "Alice",
      "is_active": true,
      "created_at": "2026-02-09T10:00:00Z",
      "last_login": "2026-02-09T09:00:00Z",
      "group_count": 2,
      "groups": [
        {
          "user_id": 10,
          "group_id": 1,
          "group_name": "Fun Group",
          "display_name": "Alice"
        },
        {
          "user_id": 15,
          "group_id": 3,
          "group_name": "Work Group",
          "display_name": "AliceW"
        }
      ]
    }
  ],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

---

### Create Account (Admin)

**Authentication:** Required (Admin JWT Bearer token)

Create a new user account. The account can be created **without** assigning to any group, or
optionally added to a group at creation time.

```http
POST /api/admin/accounts
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{
  "email": "newuser@example.com",
  "password": "SecurePass1",
  "display_name": "NewUser",
  "group_id": 1,
  "group_display_name": "NewUserInGroup",
  "color_avatar": "#FF5733"
}
```

**Fields:**

- `email` (required): Unique email address
- `password` (required): Password (min 8 characters)
- `display_name` (required): Default display name for the account
- `group_id` (optional): Group ID to add the account to
- `group_display_name` (optional): Display name within the group (defaults to `display_name`)
- `color_avatar` (optional): Hex color for avatar (random if not provided)

**Response (200) - Account only (no group):**

```json
{
  "id": 5,
  "account_id": "uuid-string",
  "email": "newuser@example.com",
  "display_name": "NewUser",
  "is_active": true,
  "created_at": "2026-02-09T10:00:00Z",
  "group_membership": null
}
```

**Response (200) - Account with group:**

```json
{
  "id": 5,
  "account_id": "uuid-string",
  "email": "newuser@example.com",
  "display_name": "NewUser",
  "is_active": true,
  "created_at": "2026-02-09T10:00:00Z",
  "group_membership": {
    "user_id": 42,
    "group_id": 1,
    "group_name": "Fun Group",
    "display_name": "NewUserInGroup"
  }
}
```

**Errors:**

- `400`: Email is required
- `400`: Password must be at least 8 characters
- `400`: Display name is required
- `400`: Account with this email already exists
- `400`: Group not found (if group_id provided)
- `400`: Display name already taken in group (if group_id provided)

---

### Delete Account (Admin)

**Authentication:** Required (Admin JWT Bearer token)

Delete an account and all their group memberships and votes.

```http
DELETE /api/admin/accounts/{account_id}
Authorization: Bearer <admin_access_token>
```

**Response (200):**

```json
{
  "status": "deleted",
  "email": "newuser@example.com"
}
```

**Errors:**

- `404`: Account not found

---

## Admin: User Management (Group Memberships)

Users represent group memberships. A user entry links an account to a specific group with a display
name and avatar.

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

### Reset User Password

Reset the password for a user's linked account.

```http
POST /api/admin/users/{user_id}/reset-password
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "new_password": "NewSecurePass1",
  "reason": "User forgot their password"
}
```

**Response (200):**

```json
{
  "message": "Password reset successfully for user Alice",
  "account_email": "alice@example.com"
}
```

**Errors:**

- `404` User not found
- `400` User has no linked account

---

### Create User / Group Membership (Admin)

**Authentication:** Required (Admin JWT Bearer token)

Create a new group membership for a user. Optionally link to an existing account by email. To create
an account without a group, use `POST /api/admin/accounts` instead.

```http
POST /api/admin/users
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{
  "display_name": "NewUser",
  "group_id": 1,
  "color_avatar": "#FF5733",
  "account_email": "newuser@example.com"
}
```

**Fields:**

- `display_name` (required): Display name within the group (min 2 characters)
- `group_id` (required): Group to add the user to
- `color_avatar` (optional): Hex color for avatar (random if not provided)
- `account_email` (optional): Link to an existing account by email

**Response (200):**

```json
{
  "id": 42,
  "user_id": "uuid-string",
  "display_name": "NewUser",
  "group_id": 1,
  "color_avatar": "#FF5733",
  "account_email": "newuser@example.com"
}
```

**Errors:**

- `400`: Display name must be at least 2 characters
- `400`: Group ID is required
- `400`: Group not found
- `400`: Display name already taken in this group
- `400`: No account found with provided email
- `400`: Account is already a member of this group

---

### Delete User / Group Membership (Admin)

**Authentication:** Required (Admin JWT Bearer token)

Delete a user's group membership and all their answers in that group. This does **not** delete the
linked account.

```http
DELETE /api/admin/users/{user_id}
Authorization: Bearer <admin_access_token>
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

Create a new group. Generates invite code automatically.

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

Get group leaderboard. Requires JWT authentication and group membership.

```http
GET /api/groups/{group_id}/leaderboard
Authorization: Bearer <access_token>
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

Get question exhaustion status for a group. Requires JWT authentication and group creator
permission.

```http
GET /api/groups/{group_id}/question-status
Authorization: Bearer <access_token>
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

### Reset Question Cycle (Instance Admin Only)

Reset question cycle by clearing all used questions for a group.

```http
POST /api/admin/groups/{group_id}/reset-question-cycle
Authorization: Bearer <admin_access_token>
```

**Response (200):**

```json
{
  "group_id": "abc123",
  "message": "Question cycle reset. 45 questions deleted.",
  "deleted_count": 45
}
```

**Notes:**

- Uses integer group ID (from admin groups list)
- Only instance admins can reset question cycles

---

## Admin: API Logs

### Get API Logs

Get server-side request logs. Logs all non-admin API requests.

```http
GET /api/admin/api-logs?page=1&per_page=50&method=POST&path=/auth
Authorization: Bearer <admin_access_token>
```

**Query Parameters:**

- `page` (optional, default: 1): Page number
- `per_page` (optional, default: 50): Items per page (max 200)
- `method` (optional): Filter by HTTP method (GET, POST, etc.)
- `path` (optional): Filter by path substring
- `status_code` (optional): Filter by status code
- `min_duration_ms` (optional): Filter by minimum duration in ms

**Response (200):**

```json
{
  "logs": [
    {
      "id": 1,
      "timestamp": "2026-02-17T14:00:00Z",
      "method": "POST",
      "path": "/api/auth/register",
      "query_string": "",
      "status_code": 200,
      "duration_ms": 45.2,
      "client_ip": "127.0.0.1",
      "user_agent": "Mozilla/5.0...",
      "account_id": "uuid",
      "response_size": 256
    }
  ],
  "total": 100,
  "page": 1,
  "per_page": 50
}
```

### Delete API Logs

Clear all API logs.

```http
DELETE /api/admin/api-logs
Authorization: Bearer <admin_access_token>
```

**Response (200):**

```json
{
  "message": "All API logs cleared",
  "deleted_count": 100
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

**Authentication:** Required (JWT Bearer token - must be group creator)

```http
POST /api/groups/{group_id}/question-sets/private
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "My Custom Questions",
  "description": "Optional",
  "questions": [
    {
      "text": "Is this good?",
      "question_type": "binary_vote",
      "options": ["Yes", "No"]
    },
    {
      "text": "Do you think {member} could survive on a desert island?",
      "question_type": "binary_vote"
    },
    {
      "text": "What is {member}'s hidden talent?",
      "question_type": "free_text"
    }
  ]
}
```

> **`{member}` placeholder:** Include `{member}` literally in the `text` field. When the scheduler
> picks this template for a group, `{member}` is replaced with a randomly chosen group member's
> display name. Works with all question types.

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

**Errors:**

- `401`: Authorization header required / Invalid token
- `403`: Only group creator can manage private sets
- `404`: Group not found
- `400`: Max 5 private sets per group / Invalid validation

---

### List My Private Sets

**Authentication:** Required (JWT Bearer token - must be group creator)

```http
GET /api/groups/{group_id}/question-sets/my?limit=50&offset=0
Authorization: Bearer <access_token>
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

**Authentication:** Required (JWT Bearer token + group membership, group creator for private sets)

```http
GET /api/groups/{group_id}/question-sets/{set_id}
Authorization: Bearer <access_token>
```

**Notes:**

- Public sets: Any group member can view
- Private sets: Only the group creator can view

**Response (200):**

```json
{
  "id": 42,
  "name": "My Custom Questions",
  "is_public": false,
  "creator_id": 1,
  "usage_count": 5,
  "created_at": "2026-02-09T10:00:00Z",
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

**Errors:**

- `401`: Authorization header required / Invalid token
- `403`: Not a member of the group / Only group creator can view private sets
- `404`: Group not found / Question set not found

---

### Update Private Set

**Authentication:** Required (JWT Bearer token - must be group creator)

Update a private question set name and/or questions. Only the group creator can update sets.

```http
PUT /api/groups/{group_id}/question-sets/{set_id}
Authorization: Bearer <access_token>
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

- `401`: Invalid or missing auth token
- `403`: Only group creator can update private sets
- `404`: Question set not found

---

### Delete Private Set

**Authentication:** Required (JWT Bearer token - must be group creator)

Delete a private question set. Cannot delete sets currently assigned to the group.

```http
DELETE /api/groups/{group_id}/question-sets/{set_id}
Authorization: Bearer <access_token>
```

**Response (200):**

```json
{
  "message": "Question set deleted successfully",
  "set_id": 42
}
```

**Errors:**

- `401`: Invalid or missing auth token
- `403`: Only group creator can delete private sets
- `400`: Cannot delete a set that is currently assigned to the group

---

### Get Question Set Usage

**Authentication:** Required (JWT Bearer token - must be group creator)

Get usage statistics for a private question set (how many times each question has been asked).

```http
GET /api/groups/{group_id}/question-sets/{set_id}/usage
Authorization: Bearer <access_token>
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

- `401`: Authorization header required / Invalid token
- `403`: Only group creator can view usage stats
- `404`: Question set not found

---

## Push Notifications

Push notifications are **optional** and use Firebase Cloud Messaging (FCM) HTTP v1 API.

> **Note:** Even when the server is configured for FCM, individual users must **opt in** to receive
> push alerts. Use the `/api/users/{user_id}/push-settings` endpoint to toggle
> `push_notifications_enabled` (defaults to `false`). The scheduler will not send pushes to users
> who have opted out, regardless of registered device tokens.

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

**Authentication:** None (public endpoint)

Check if push notifications are enabled on this server.

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

**Authentication:** Required (JWT Bearer token - must match user_id in URL)

Register a device to receive push notifications.

```http
POST /api/users/{user_id}/device-token
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "token": "fcm-device-token-from-firebase-sdk",
  "platform": "ios",  // "ios", "android", or "web"
  "device_name": "iPhone 15 Pro"  // optional
}
```

**Notes:**

- The `user_id` in the URL must match the authenticated user's ID
- If the token already exists, it will be updated instead of creating a duplicate
- Automatically marks the token as active and updates `last_used_at`

**Response (200):**

```json
{
  "id": 1,
  "token": "fcm-device-token...",
  "platform": "ios",
  "device_name": "iPhone 15 Pro",
  "created_at": "2026-02-09T10:00:00Z",
  "is_active": true
}
```

**Errors:**

- `401`: Authorization header required / Invalid token / User ID mismatch
- `503`: Push notifications not enabled on server

### Unregister Device Token

**Authentication:** Required (JWT Bearer token - must match user_id in URL)

Remove a device token (e.g., on logout or when disabling notifications).

```http
DELETE /api/users/{user_id}/device-token?token=<device_token>
Authorization: Bearer <access_token>
```

**Notes:**

- The `user_id` in the URL must match the authenticated user's ID
- Returns success message even if token wasn't found

**Response (200):**

```json
{
  "message": "Device token removed successfully"
}
```

**Errors:**

- `401`: Authorization header required / Invalid token / User ID mismatch

### List Device Tokens

**Authentication:** Required (JWT Bearer token - must match user_id in URL)

List all registered device tokens for a user.

```http
GET /api/users/{user_id}/device-tokens
Authorization: Bearer <access_token>
```

**Notes:**

- The `user_id` in the URL must match the authenticated user's ID
- Only returns active tokens

**Response (200):**

```json
[
  {
    "id": 1,
    "token": "fcm-device-token...",
    "platform": "ios",
    "device_name": "iPhone 15 Pro",
    "created_at": "2026-02-09T10:00:00Z",
    "is_active": true
  },
  {
    "id": 2,
    "token": "fcm-device-token-2...",
    "platform": "android",
    "device_name": "Pixel 8",
    "created_at": "2026-02-09T09:00:00Z",
    "is_active": true
  }
]
```

**Errors:**

- `401`: Authorization header required / Invalid token / User ID mismatch

### Notification Types

The server sends these notification types automatically:

| Type                | Trigger                                    | Title Example                       |
| ------------------- | ------------------------------------------ | ----------------------------------- |
| `new_question`      | New daily question created                 | "New Question in MyGroup! 🎯"       |
| `daily_reminder`    | User hasn't answered and streak is at risk | "Don't break your 5-day streak! 🔥" |
| `results_available` | Voting results ready                       | "Results are in! 📊"                |

**Streak-at-Risk Reminders:** Approximately one hour _before_ a group's daily question rolls over,
all members with a positive answer streak are sent a `daily_reminder` push notification (and
optionally email) if they have opted in. The advance notice gives users a chance to answer the
upcoming question and avoid having their streak reset to zero. Previously the alert was issued after
a missed question; the new timing is intended to be proactive.

### Mobile App Integration

To receive push notifications + real-time updates in your app:

1. **Add Firebase SDK** to your iOS/Android/Web app
2. **Get device token** from Firebase SDK on app startup
3. **Register token** with this API when user logs in
4. **Unregister token** when user logs out
5. **Connect to the group WebSocket** for live in-app updates (see
   [WebSocket section](#websocket--real-time-events))

---

## WebSocket — Real-Time Events

The backend provides **two** WebSocket endpoints for real-time updates. For new integrations, use
the **Group-Level WebSocket** — it receives ALL event types with a single connection.

| Endpoint                                       | Scope                  | Auth            | Use Case                       |
| ---------------------------------------------- | ---------------------- | --------------- | ------------------------------ |
| `ws/groups/{group_id}?token=JWT`               | All events for a group | Query param JWT | ⭐ Recommended for mobile apps |
| `ws/groups/{group_id}/questions/{question_id}` | Vote updates only      | In-message JWT  | Legacy / web widgets           |

---

### Group-Level WebSocket (Recommended)

**Connect to receive ALL real-time events for a group with a single persistent connection.**

```text
WS /ws/groups/{group_id}?token=<jwt-access-token>
```

**Authentication:**

- JWT access token is passed as the `token` query parameter
- User must be a member of the specified group
- If authentication fails, the server accepts the connection and immediately closes it with code
  `4001` and reason `"Authentication failed"`

**Connection Example (JavaScript):**

```javascript
const ws = new WebSocket(`wss://your-server.com/ws/groups/${groupId}?token=${accessToken}`);

ws.onopen = () => {
  console.log("Connected to group real-time feed");
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  switch (message.type) {
    case "vote_update":
      handleVoteUpdate(message.data);
      break;
    case "new_question":
      handleNewQuestion(message.data);
      break;
    case "streak_update":
      handleStreakUpdate(message.data);
      break;
    case "member_joined":
      handleMemberJoined(message.data);
      break;
    case "member_left":
      handleMemberLeft(message.data);
      break;
    case "pong":
      // keepalive response
      break;
  }
};

ws.onclose = (event) => {
  if (event.code === 4001) {
    console.error("Auth failed — re-login and reconnect");
  }
};
```

**Connection Example (Swift / iOS):**

```swift
let url = URL(string: "wss://your-server.com/ws/groups/\(groupId)?token=\(accessToken)")!
let task = URLSession.shared.webSocketTask(with: url)
task.resume()

func receiveMessage() {
    task.receive { result in
        switch result {
        case .success(let message):
            if case .string(let text) = message,
               let data = text.data(using: .utf8),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let type = json["type"] as? String {
                switch type {
                case "vote_update":  handleVoteUpdate(json["data"])
                case "new_question": handleNewQuestion(json["data"])
                case "streak_update": handleStreakUpdate(json["data"])
                case "member_joined": handleMemberJoined(json["data"])
                default: break
                }
            }
            receiveMessage() // Continue listening
        case .failure(let error):
            print("WS error: \(error)")
        }
    }
}
receiveMessage()
```

**Keepalive (Ping/Pong):**

Send a ping to keep the connection alive and check how many users are online:

```json
// → Send:
{"type": "ping"}

// ← Receive:
{
  "type": "pong",
  "timestamp": "2026-02-24T14:30:00.000Z",
  "online_count": 3
}
```

**Recommended:** Send a ping every 30 seconds. If no pong is received within 10 seconds, reconnect.

---

### Event Types Reference

All events follow the same envelope format:

```json
{
  "type": "<event_type>",
  "timestamp": "2026-02-24T14:30:00.000Z",
  "data": { ... }
}
```

#### `vote_update`

**Trigger:** A group member submits or changes their answer (via REST API or WebSocket vote).

```json
{
  "type": "vote_update",
  "timestamp": "2026-02-24T14:30:00.000Z",
  "data": {
    "question_id": "a1b2c3d4-...",
    "option_counts": {
      "Alice": 4,
      "Bob": 2
    },
    "total_votes": 6,
    "allow_multiple": false,
    "options": ["Alice", "Bob"],
    "user": {
      "display_name": "Charlie",
      "color_avatar": "#FF6B6B",
      "voted": "Alice"
    }
  }
}
```

| Field               | Type               | Description                                 |
| ------------------- | ------------------ | ------------------------------------------- |
| `question_id`       | string             | UUID of the question that was answered      |
| `option_counts`     | object             | Map of option → vote count (updated totals) |
| `total_votes`       | integer            | Total number of votes on this question      |
| `allow_multiple`    | boolean            | Whether multiple selections are allowed     |
| `options`           | string[]           | All available options                       |
| `user.display_name` | string             | Who just voted                              |
| `user.color_avatar` | string             | Voter's avatar color                        |
| `user.voted`        | string \| string[] | What they voted for                         |

#### `new_question`

**Trigger:** The daily question rolls over (scheduler or on-demand creation). Sent when a new
question is created and the previous one is deactivated.

```json
{
  "type": "new_question",
  "timestamp": "2026-02-24T14:00:00.000Z",
  "data": {
    "question_id": "e5f6a7b8-...",
    "question_text": "Who would survive longest in a zombie apocalypse?",
    "question_type": "member_choice",
    "options": ["Alice", "Bob", "Charlie"],
    "question_date": "2026-02-24T00:00:00",
    "is_active": true,
    "allow_multiple": false,
    "featured_member": null
  }
}
```

| Field             | Type         | Description                                                                |
| ----------------- | ------------ | -------------------------------------------------------------------------- |
| `question_id`     | string       | UUID of the new question                                                   |
| `question_text`   | string       | The question text                                                          |
| `question_type`   | string       | `member_choice`, `duo_choice`, `binary_vote`, `free_text`, `single_choice` |
| `options`         | string[]     | Available answer options                                                   |
| `question_date`   | string       | ISO date of the question                                                   |
| `is_active`       | boolean      | Always `true` for new questions                                            |
| `allow_multiple`  | boolean      | Whether multiple selections allowed                                        |
| `featured_member` | string\|null | Display name if `{member}` placeholder was used                            |

**App behavior:** When receiving `new_question`, refresh the question UI and reset vote state.

#### `streak_update`

**Trigger:** Sent in two scenarios:

1. **After a vote:** The voter's streak is updated (+1 or unchanged if already answered)
2. **On question rollover:** All members' streaks are recalculated (missed question → streak reset
   to 0)

**After a vote (single user):**

```json
{
  "type": "streak_update",
  "timestamp": "2026-02-24T14:30:00.000Z",
  "data": {
    "user_id": "abc123-...",
    "display_name": "Alice",
    "current_streak": 5,
    "longest_streak": 12
  }
}
```

**On question rollover (all members):**

```json
{
  "type": "streak_update",
  "timestamp": "2026-02-24T14:00:00.000Z",
  "data": {
    "reason": "question_rollover",
    "members": [
      {
        "user_id": "abc123-...",
        "display_name": "Alice",
        "current_streak": 5,
        "longest_streak": 12
      },
      {
        "user_id": "def456-...",
        "display_name": "Bob",
        "current_streak": 0,
        "longest_streak": 3
      }
    ]
  }
}
```

| Field            | Type    | Description                                             |
| ---------------- | ------- | ------------------------------------------------------- |
| `reason`         | string  | `"question_rollover"` (only present in rollover events) |
| `members`        | array   | All members' updated streaks (only in rollover events)  |
| `user_id`        | string  | UUID of the user whose streak changed                   |
| `display_name`   | string  | User's display name                                     |
| `current_streak` | integer | Current consecutive-answer streak                       |
| `longest_streak` | integer | All-time best streak                                    |

**App behavior:** Update leaderboard UI, show streak animations, display streak-lost notifications.

#### `member_joined`

**Trigger:** A new user joins the group via invite code.

```json
{
  "type": "member_joined",
  "timestamp": "2026-02-24T15:00:00.000Z",
  "data": {
    "user_id": "ghi789-...",
    "display_name": "NewMember",
    "color_avatar": "#4ECDC4",
    "avatar_url": null,
    "member_count": 5
  }
}
```

**App behavior:** Add member to member list, show a toast notification ("NewMember joined!"),
refresh the question options if it's a `member_choice` question.

#### `member_left`

**Trigger:** A member is removed from the group (admin action).

```json
{
  "type": "member_left",
  "timestamp": "2026-02-24T15:00:00.000Z",
  "data": {
    "user_id": "ghi789-...",
    "display_name": "FormerMember"
  }
}
```

**App behavior:** Remove member from member list, refresh question if needed.

#### `group_deleted`

**Trigger:** The group creator deletes the group via `DELETE /api/auth/groups/{group_id}`.

```json
{
  "type": "group_deleted",
  "timestamp": "2026-02-24T15:00:00.000Z",
  "data": {
    "group_id": "abc123-...",
    "group_name": "My Awesome Group"
  }
}
```

**App behavior:** Show notification that the group was deleted, navigate user away from group view,
remove the group from local state/storage.

---

### Question-Level WebSocket (Legacy)

For backward compatibility, the per-question WebSocket endpoint is still available. It only receives
vote updates for a specific question.

```text
WS /ws/groups/{group_id}/questions/{question_id}
```

**Authentication:** JWT access token sent in each message (not query param).

**Send Vote:**

```json
{
  "type": "vote",
  "token": "your-jwt-access-token",
  "answer": "Alice"
}
```

For free-text questions:

```json
{
  "type": "vote",
  "token": "your-jwt-access-token",
  "text_answer": "My detailed answer here"
}
```

For multiple-choice questions allowing multiple selections:

```json
{
  "type": "vote",
  "token": "your-jwt-access-token",
  "answer": ["Alice", "Bob"]
}
```

**Receive Updates:**

```json
{
  "type": "update",
  "timestamp": "2026-02-24T14:30:00.000Z",
  "data": {
    "option_counts": { "Alice": 4, "Bob": 2 },
    "total_votes": 6,
    "allow_multiple": false,
    "options": ["Alice", "Bob"],
    "user": {
      "display_name": "Charlie",
      "voted": "Alice"
    }
  }
}
```

**Notes:**

- Connection is silently ignored if token is invalid, user not in group, or question doesn't exist
- Vote updates are broadcast to all connected clients for that question AND to group-level WebSocket
  clients
- Updates existing vote if user has already voted

---

### WebSocket Integration Guide

#### Recommended Architecture

For mobile apps, the recommended real-time architecture is:

```
┌──────────────────────────────────────────────────────────┐
│  Mobile App                                              │
│                                                          │
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │ REST API      │  │ Group WebSocket │  │ FCM Push       │ │
│  │ (actions)     │  │ (live updates)  │  │ (background)   │ │
│  └───────────────┘  └────────────────┘  └────────────────┘ │
│        │                  │                    │              │
└────────┼──────────────────┼────────────────────┼──────────────┘
        │                  │                    │
        ▼                  ▼                    ▼
┌──────────────────────────────────────────────────────────┐
│  DontAskUs Backend                                       │
│                                                          │
│  REST POST /answer ────────────────────────────┐       │
│       │                                    │       │
│       ▼                                    ▼       │
│  Save to DB  ───────────────────> WS broadcast  │
│                                     (vote_update,  │
│  Scheduler (hourly) ────────────>  streak_update, │
│       │                              new_question)  │
│       ▼                                    │       │
│  FCM Push (offline users) <─────────────┘       │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

1. **REST API** for all user actions (register, login, answer questions, etc.)
2. **Group WebSocket** for live in-app updates (connect on app open, disconnect on close)
3. **FCM Push Notifications** for background alerts (new question, streak-at-risk)

#### Connection Lifecycle

```
App Opens → Login (REST) → Get token → Connect WS with token
                                        │
                                        ├── Receive events (update UI in real-time)
                                        ├── Send pings every 30s
                                        ├── If pong timeout → reconnect
                                        ├── If 4001 close → re-login, then reconnect
                                        │
App Backgrounds → Close WS (optional, depends on platform)
                   FCM push keeps user informed while backgrounded
                                        │
App Foregrounds → Reconnect WS → Fetch latest via REST to sync state
```

#### Reconnection Strategy

WebSocket connections can drop due to network changes, server restarts, or token expiry. Implement
exponential backoff:

```javascript
let reconnectDelay = 1000; // Start at 1 second
const MAX_DELAY = 30000; // Max 30 seconds

function connectWebSocket() {
  const ws = new WebSocket(`wss://server/ws/groups/${groupId}?token=${token}`);

  ws.onopen = () => {
    reconnectDelay = 1000; // Reset on successful connect
  };

  ws.onclose = (event) => {
    if (event.code === 4001) {
      // Auth failed — refresh token first, then reconnect
      refreshToken().then(connectWebSocket);
      return;
    }
    // Exponential backoff
    setTimeout(connectWebSocket, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, MAX_DELAY);
  };

  ws.onmessage = handleMessage;
}
```

#### State Synchronization

The WebSocket provides **incremental updates** — not the full state. On reconnect, always fetch the
latest state via REST to avoid stale data:

```
Reconnect → GET /api/groups/{id}/questions/today  (sync question + votes)
         → GET /api/groups/{id}/leaderboard       (sync streaks)
         → GET /api/groups/{id}/members            (sync member list)
```

Then apply subsequent WebSocket events on top of the synced state.

#### Event Handling Best Practices

| Event                      | App Action                                                                |
| -------------------------- | ------------------------------------------------------------------------- |
| `vote_update`              | Update vote counts/chart, add vote animation for `user.display_name`      |
| `new_question`             | Replace question UI, clear previous votes, show "New question!" alert     |
| `streak_update` (single)   | Update the voter's streak badge in leaderboard                            |
| `streak_update` (rollover) | Refresh entire leaderboard, show streak-lost animations for reset users   |
| `member_joined`            | Add to member list, show join toast, potentially refresh question options |
| `member_left`              | Remove from member list, potentially refresh question options             |
| `group_deleted`            | Show deletion notice, navigate away, remove group from local state        |

---

## Error Codes

Common HTTP status codes used across the API:

| Code | Meaning                          | Common Causes                                                            |
| ---- | -------------------------------- | ------------------------------------------------------------------------ |
| 200  | Success                          | Request completed successfully                                           |
| 201  | Created                          | Resource created successfully                                            |
| 400  | Bad Request                      | Invalid request format, missing required fields, invalid file type/size  |
| 401  | Unauthorized                     | Missing/invalid/expired JWT token, user ID mismatch, invalid credentials |
| 403  | Forbidden                        | Not a member of the group, insufficient permissions                      |
| 404  | Not Found                        | Resource doesn't exist (group, question, user)                           |
| 409  | Conflict                         | Resource already exists (duplicate email, etc.)                          |
| 429  | Too Many Requests (Rate Limited) | Exceeded rate limit for endpoint                                         |
| 500  | Internal Server Error            | Unexpected server error                                                  |
| 503  | Service Unavailable              | Feature not configured (e.g., push notifications)                        |

**Authentication Error Details:**

- `401` with "Authorization header required" - No `Authorization` header provided
- `401` with "Invalid token" - JWT token is malformed, expired, or has invalid signature
- `401` with "User ID mismatch" - Authenticated user doesn't match `user_id` in URL path
- `403` with "Not a member" - User is authenticated but not a member of the requested group

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
# USER JWT
# ═══════════════════════════════════════════════════════════════════════
USER_JWT_SECRET=your-user-jwt-secret-change-in-production
USER_JWT_ACCESS_EXPIRE_MINUTES=30
USER_JWT_REFRESH_EXPIRE_DAYS=30

# ═══════════════════════════════════════════════════════════════════════
# REVERSE PROXY — Uncomment if running behind nginx/traefik/etc.
# Ensures real client IPs are logged instead of the proxy IP.
# ═══════════════════════════════════════════════════════════════════════
# TRUSTED_PROXIES=*

# ═══════════════════════════════════════════════════════════════════════
# OPTIONAL SETTINGS
# ═══════════════════════════════════════════════════════════════════════
LOG_LEVEL=INFO
# SCHEDULE_INTERVAL_SECONDS is deprecated — the scheduler now runs hourly with per-group rollover
```

### Environment Variable Reference

| Variable                         | Description                                                                      | Required | Default |
| -------------------------------- | -------------------------------------------------------------------------------- | -------- | ------- |
| `DATABASE_URL`                   | PostgreSQL connection string                                                     | Yes      | -       |
| `REDIS_URL`                      | Redis connection string                                                          | Yes      | -       |
| `SECRET_KEY`                     | JWT secret for user sessions                                                     | Yes      | -       |
| `ADMIN_JWT_SECRET`               | JWT secret for admin sessions                                                    | Yes      | -       |
| `ADMIN_INITIAL_USERNAME`         | Initial admin username                                                           | No       | `admin` |
| `ADMIN_INITIAL_PASSWORD`         | Initial admin password                                                           | Yes      | -       |
| `ALLOWED_ORIGINS`                | CORS allowed origins                                                             | Yes      | -       |
| `USER_JWT_SECRET`                | JWT secret for user tokens                                                       | Yes      | -       |
| `USER_JWT_ACCESS_EXPIRE_MINUTES` | User access token expiry (mins)                                                  | No       | `30`    |
| `USER_JWT_REFRESH_EXPIRE_DAYS`   | User refresh token expiry (days)                                                 | No       | `30`    |
| `TRUSTED_PROXIES`                | Trusted proxy IPs/CIDRs for X-Forwarded-For                                      | No       | -       |
| `LOG_LEVEL`                      | Logging level                                                                    | No       | `INFO`  |
| `SCHEDULE_INTERVAL_SECONDS`      | _(Deprecated)_ Scheduler now runs hourly with per-group `question_hour` rollover | No       | -       |
| `FCM_PROJECT_ID`                 | Firebase project ID                                                              | No\*     | -       |
| `FCM_SERVICE_ACCOUNT_JSON`       | Firebase service account JSON                                                    | No\*     | -       |

\*Required only if push notifications are enabled

---

## Quick Start Examples

### Complete User Flow

```bash
# 1. Register account
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"SecurePass1","display_name":"Alice"}'

# Save: access_token, refresh_token

# 2. Create group
curl -X POST http://localhost:8000/api/auth/groups/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -d '{"group_name":"My Group","display_name":"Alice"}'

# Save: invite_code (group creator is identified via JWT + creator_id)

# 3. Get today's question
curl -H "Authorization: Bearer ACCESS_TOKEN" \
  "http://localhost:8000/api/groups/{group_id}/questions/today"

# 4. Submit answer
curl -X POST "http://localhost:8000/api/groups/{group_id}/questions/{question_id}/answer" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
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
