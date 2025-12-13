# dontAskUs API Documentation

Base URL: `http://localhost:8000`

## Auth & Headers
- `X-Session-Token`: plaintext session token returned on join (required for user endpoints)
- `X-Admin-Token`: admin token for group management (returned on create group)
- `Content-Type: application/json`

## Groups

### Create Group
- `POST /api/groups`
- Body:
```json
{
  "name": "My Group"
}
```
- Response:
```json
{
  "id": 1,
  "group_id": "uuid",
  "name": "My Group",
  "invite_code": "ABC123",
  "admin_token": "plaintext-admin-token",
  "creator_id": null,
  "created_at": "2025-12-13T10:50:00Z",
  "member_count": 0
}
```

### Get Group (Public)
- `GET /api/groups/{group_id}`
- Response:
```json
{
  "id": 1,
  "group_id": "uuid",
  "name": "My Group",
  "invite_code": "ABC123",
  "created_at": "2025-12-13T10:50:00Z",
  "member_count": 3
}
```

## Users

### Join Group
- `POST /api/users/join`
- Body:
```json
{
  "display_name": "Alice",
  "group_invite_code": "ABC123",
  "color_avatar": "#3B82F6" // optional, if omitted a random color is assigned
}
```
- Rules:
  - Display name must be unique within the group
  - If `color_avatar` missing, server assigns a random color
  - Returns the session token (plaintext) once
- Response:
```json
{
  "id": 10,
  "user_id": "uuid",
  "display_name": "Alice",
  "color_avatar": "#3B82F6",
  "session_token": "plaintext-session-token",
  "created_at": "2025-12-13T10:50:00Z",
  "answer_streak": 0,
  "longest_answer_streak": 0
}
```

### Me (Get Current User)
- `GET /api/users/me`
- Headers: `X-Session-Token: <plaintext token>`
- Response:
```json
{
  "id": 10,
  "user_id": "uuid",
  "display_name": "Alice",
  "color_avatar": "#3B82F6",
  "created_at": "2025-12-13T10:50:00Z",
  "answer_streak": 2,
  "longest_answer_streak": 5
}
```

## Daily Questions

### Create Question (Admin)
- `POST /api/questions`
- Headers: `X-Admin-Token`
- Body:
```json
{
  "question_text": "Coffee or Tea?",
  "option_a": "Coffee",
  "option_b": "Tea",
  "question_type": "binary_vote"
}
```
- Response:
```json
{
  "id": 100,
  "question_id": "uuid",
  "group_id": 1,
  "question_text": "Coffee or Tea?",
  "option_a": "Coffee",
  "option_b": "Tea",
  "created_at": "2025-12-13T10:50:00Z",
  "expires_at": "2025-12-14T10:50:00Z",
  "is_active": true
}
```

## Voting

### Vote on Question
- `POST /api/votes`
- Headers: `X-Session-Token`
- Body:
```json
{
  "question_id": "uuid-or-id",
  "vote": "A" // or "B"; for free text questions, send `text_answer`
}
```
- Response:
```json
{
  "id": 200,
  "vote_id": "uuid",
  "question_id": 100,
  "user_id": 10,
  "answer": "A",
  "voted_at": "2025-12-13T10:50:00Z"
}
```

## Admin: Question Sets

### Assign Set to Group
- `POST /api/groups/{group_id}/assign-set`
- Headers: `X-Admin-Token`
- Body:
```json
{
  "set_id": "uuid"
}
```
- Response: `204 No Content`

## Common Errors
- `400 Bad Request` – validation failed (invalid invite code, non-hex color)
- `401 Unauthorized` – missing/invalid `X-Session-Token` or `X-Admin-Token`
- `404 Not Found` – group not found or question not found
- `409 Conflict` – display name already exists in group

## Notes
- Tokens are stored hashed and only shown once.
- Session tokens expire after `SESSION_TOKEN_EXPIRY_DAYS`.
- CORS is restricted to `ALLOWED_ORIGINS`.
