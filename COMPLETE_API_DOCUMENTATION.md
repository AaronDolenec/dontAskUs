# dontAskUs - Complete API Documentation

**Base URL:** `http://localhost:8000` (development)  
**Version:** 1.3.0  
**Last Updated:** February 17, 2026

**IMPORTANT:** All API endpoints require authentication unless explicitly marked as "Public" or "No
Auth". After registration or login, include the access token in the `Authorization: Bearer <token>`
header for all requests.

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [User Auth Endpoints](#user-auth-endpoints)
4. [Account Recovery](#account-recovery)
5. [Avatar Upload Endpoints](#avatar-upload-endpoints)
6. [Group Endpoints](#group-endpoints)
7. [Daily Questions & Voting](#daily-questions--voting)
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
20. [WebSocket](#websocket)
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

The backend **automatically generates a new question for each group every day**:

- Runs on server startup and every 24 hours (configurable via `SCHEDULE_INTERVAL_SECONDS`)
- Selects questions from assigned question sets (or public templates as fallback)
- Never repeats a question within the same group until all are exhausted
- Different groups receive different questions on the same day
- Requires at least 2 members for `member_choice` and `duo_choice` questions
- Sends push notifications to group members (if FCM is configured)

### Authentication Types

| Flow            | Method               | Storage      |
| --------------- | -------------------- | ------------ |
| Users           | JWT (Email/Password) | Bearer Token |
| Group Creators  | JWT (Creator ID)     | Bearer Token |
| Instance Admins | JWT (TOTP optional)  | Bearer Token |

---

## Authentication

### JWT Tokens (Users)

- Users register with email/password via `/api/auth/register`
- Login via `/api/auth/login` returns access + refresh tokens
- Access Token: `USER_JWT_ACCESS_EXPIRE_MINUTES` (default: 30 minutes)
- Refresh Token: `USER_JWT_REFRESH_EXPIRE_DAYS` (default: 30 days)
- Passed as `Authorization: Bearer <token>` header
- Password requirements: min 8 chars, uppercase, lowercase, digit

### Group Creator Identification

- The user who creates a group is stored as `creator_id` on the Group model
- Group creator endpoints verify the requesting user's JWT and check `group.creator_id == user.id`
- No separate admin token is used — the creator's standard JWT is sufficient

### JWT Tokens (Instance Admins)

- Access Token: 60 minutes
- Refresh Token: 7 days
- Passed as `Authorization: Bearer <token>` header
- TOTP 2FA optional (can be enabled in account settings)

---

## User Auth Endpoints

### Register

**Authentication:** None (public endpoint)

Create a new account with email and password.

```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "alice@example.com",
  "password": "SecurePass1",
  "display_name": "Alice"
}
```

**Response (200):**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "account_id": 1,
    "email": "alice@example.com",
    "display_name": "Alice",
    "groups": []
  }
}
```

**Errors:**

- `400` Password too weak (min 8 chars, uppercase, lowercase, digit)
- `409` Email already registered

---

### Login

**Authentication:** None (public endpoint)

Authenticate with email and password.

```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "alice@example.com",
  "password": "SecurePass1"
}
```

**Response (200):**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "account_id": 1,
    "email": "alice@example.com",
    "display_name": "Alice",
    "groups": [
      {
        "user_id": 10,
        "group_id": "group-uuid",
        "group_name": "My Group",
        "display_name": "Alice"
      }
    ]
  }
}
```

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
  "user": { ... }
}
```

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
  "account_id": 1,
  "email": "alice@example.com",
  "display_name": "Alice",
  "groups": [
    {
      "user_id": 10,
      "group_id": "group-uuid",
      "group_name": "My Group",
      "display_name": "Alice"
    }
  ]
}
```

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
  "current_password": "OldPass1",
  "new_password": "NewPass1"
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
  "user_id": 10,
  "group_id": "group-uuid",
  "group_name": "My Group",
  "display_name": "Alice"
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
- Supported formats: JPEG, PNG, GIF, WebP
- Maximum file size: 2MB
- Image is automatically:
  - Resized to max 256x256 pixels (maintains aspect ratio)
  - Converted to WebP format
  - Transparency converted to white background
- The `user_id` in the URL must match the authenticated user's ID

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
- `400` Invalid file type (only JPEG, PNG, GIF, WebP allowed)
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

```http
GET /api/groups/{group_id}/leaderboard
Authorization: Bearer <access_token>
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
- Streaks are only visible to group members

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

| Type            | Options Source         | Allow Multiple | Notes                         |
| --------------- | ---------------------- | -------------- | ----------------------------- |
| `binary_vote`   | Yes/No (automatic)     | No             | Simple binary choice          |
| `single_choice` | Custom list            | No             | Single selection from options |
| `member_choice` | Group members          | Optional       | Choose member(s) from group   |
| `duo_choice`    | Generated member pairs | No             | Choose from random duos       |
| `free_text`     | None                   | N/A            | Open-ended text response      |

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

**Errors:**

- `401` Authorization header required / Invalid token
- `403` You are not a member of this group
- `404` No question for today / Group not found

---

### Submit Answer/Vote

**Authentication:** Required (JWT Bearer token + Group Membership)

Submit an answer to the current question. Updates streaks on first submission.

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
  "question_type": "member_choice",
  "vote_count_a": 4,
  "vote_count_b": 1,
  "total_votes": 7,
  "option_counts": {
    "Alice": 4,
    "Bob": 1,
    "Charlie": 2
  },
  "options": ["Alice", "Bob", "Charlie"],
  "user_answer": "Alice",
  "current_streak": 4,
  "longest_streak": 5
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
      "question_date": "2026-02-09T00:00:00Z",
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
      "question_date": "2026-02-08T00:00:00Z",
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
]
```

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

**Authentication:** Required (JWT access token sent in message)

Connect to receive real-time voting updates for a specific question.

```text
WS /ws/groups/{group_id}/questions/{question_id}
```

**Connection:**

- WebSocket connections don't use HTTP headers, so authentication is handled in messages
- Must send authentication token with every vote message
- User must be a member of the specified group

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
  "type": "vote_update",
  "option_counts": {
    "Alice": 4,
    "Bob": 2
  },
  "total_votes": 6
}
```

**Error Responses:**

```json
{
  "error": "text_answer required"
}
```

```json
{
  "error": "answer required"
}
```

```json
{
  "error": "invalid option"
}
```

**Notes:**

- Connection is silently ignored if:
  - Token is invalid or missing
  - User is not a member of the group
  - Question doesn't exist
- Vote updates are broadcast to all connected clients for that question
- Updates existing vote if user has already voted, otherwise creates new vote

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
SCHEDULE_INTERVAL_SECONDS=86400
```

### Environment Variable Reference

| Variable                         | Description                                 | Required | Default |
| -------------------------------- | ------------------------------------------- | -------- | ------- |
| `DATABASE_URL`                   | PostgreSQL connection string                | Yes      | -       |
| `REDIS_URL`                      | Redis connection string                     | Yes      | -       |
| `SECRET_KEY`                     | JWT secret for user sessions                | Yes      | -       |
| `ADMIN_JWT_SECRET`               | JWT secret for admin sessions               | Yes      | -       |
| `ADMIN_INITIAL_USERNAME`         | Initial admin username                      | No       | `admin` |
| `ADMIN_INITIAL_PASSWORD`         | Initial admin password                      | Yes      | -       |
| `ALLOWED_ORIGINS`                | CORS allowed origins                        | Yes      | -       |
| `USER_JWT_SECRET`                | JWT secret for user tokens                  | Yes      | -       |
| `USER_JWT_ACCESS_EXPIRE_MINUTES` | User access token expiry (mins)             | No       | `30`    |
| `USER_JWT_REFRESH_EXPIRE_DAYS`   | User refresh token expiry (days)            | No       | `30`    |
| `TRUSTED_PROXIES`                | Trusted proxy IPs/CIDRs for X-Forwarded-For | No       | -       |
| `LOG_LEVEL`                      | Logging level                               | No       | `INFO`  |
| `SCHEDULE_INTERVAL_SECONDS`      | Question scheduling interval                | No       | `86400` |
| `FCM_PROJECT_ID`                 | Firebase project ID                         | No\*     | -       |
| `FCM_SERVICE_ACCOUNT_JSON`       | Firebase service account JSON               | No\*     | -       |

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
