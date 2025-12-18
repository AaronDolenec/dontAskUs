# dontAskUs Admin UI

Complete web-based admin panel for managing the dontAskUs platform.

## Features

- **Authentication**: Two-factor authentication (TOTP) with optional setup during onboarding
- **Dashboard**: Platform statistics, recent audit logs, quick metrics
- **User Management**: View users, suspend/unsuspend, recover session tokens
- **Group Management**: List groups, add admin notes
- **Question Sets**: Browse public/private sets, view question counts
- **Audit Logs**: Complete audit trail with pagination and filtering
- **Account Settings**: Change password, configure TOTP 2FA

## Requirements

- Node.js 18+ / npm
- React 18
- TypeScript
- Vite

## Development

### Install Dependencies

```bash
cd admin-ui
npm install
```

### Development Server

```bash
npm run dev
```

Runs on `http://localhost:5173` with hot reload.

### Build for Production

```bash
npm run build
```

Creates optimized production build in `admin-ui/dist/`.

## Architecture

```
admin-ui/
├── src/
│   ├── pages/           # Page components (Login, Dashboard, etc)
│   ├── components/      # Reusable components (Layout, ProtectedRoute)
│   ├── context/         # React context for auth state
│   ├── api/             # API client and calls
│   ├── styles/          # CSS stylesheets
│   ├── App.tsx          # Main app and routing
│   └── main.tsx         # Entry point
├── public/              # Static assets
├── vite.config.ts       # Vite configuration
└── package.json         # Dependencies
```

## API Integration

The admin UI communicates with the FastAPI backend via REST APIs. Base URL defaults to `/api`:

### Authentication Flow

1. **Login**: `POST /api/admin/login` (username + password)
   - Returns `temp_token` if TOTP enabled, or direct `access_token` if not
2. **2FA Verify**: `POST /api/admin/2fa` (temp_token + TOTP code)
   - Returns `access_token` and `refresh_token`
3. **Refresh**: `POST /api/admin/refresh` (refresh_token)
   - Returns new `access_token`

### Authorization

All authenticated endpoints require:

```
Authorization: Bearer <access_token>
```

### Auto-Refresh

Access tokens auto-refresh on 401 using stored refresh token.

## Deployment

### Docker

The UI is built as part of the multi-stage Docker build process:

1. **Stage 1**: Node builder image compiles React/Vite
2. **Stage 2**: Python image copies built assets and serves via FastAPI

Built assets are mounted at `/admin` route.

### Environment Variables

The UI accepts backend API via proxy configuration in `vite.config.ts`:

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    }
  }
}
```

## First Login

### Without TOTP (Initial Setup)

1. Access `/admin` (redirects to login)
2. Enter username and password (from `ADMIN_INITIAL_USERNAME` and `ADMIN_INITIAL_PASSWORD` env vars)
3. Immediately logged in; redirects to dashboard
4. Go to Account → Set Up 2FA (recommended)

### With TOTP (After Setup)

1. Enter username and password
2. Enter 6-digit code from authenticator app
3. Logged in with tokens

## Features Deep-Dive

### Dashboard

- **Statistics Cards**: Total groups, users, question sets, active sessions
- **Audit Logs**: Recent admin actions with timestamp, IP, action type

### User Management

- **List**: Paginated user list with search/filter
- **Actions**:
  - Suspend/Unsuspend users (mark as banned, optionally with reason)
  - Recover Token: Generate new session token for account recovery
- **Status Indicators**: Shows active/suspended status

### Group Management

- **List**: All groups with member counts
- **Admin Notes**: Add/edit instance admin notes per group

### Question Sets

- **Filter**: Public-only, private-only, or all
- **Info**: Name, type, question count, usage count

### Audit Logs

- **Full Trail**: All admin actions logged (login, user changes, group edits, etc)
- **Details**: Admin ID, action, target, timestamp, IP, reason

### Account Settings

- **Profile**: View current admin info (username, status, TOTP config, etc)
- **Password**: Change password with current password verification
- **TOTP**: Setup or reconfigure 2FA with QR code scanning

## Styling

CSS-in-modules approach with responsive design:

- **Color Scheme**: Purple/blue gradient (#667eea, #764ba2)
- **Mobile**: Hamburger sidebar below 768px
- **Dark Mode**: Not yet implemented; light-only

## Error Handling

- **400 Bad Request**: Form validation or invalid data
- **401 Unauthorized**: Expired/missing token; auto-refresh or logout
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Resource doesn't exist
- **429 Too Many Requests**: Rate limited; retry later
- **500 Internal Server Error**: Backend error

## Security

- Tokens stored in `localStorage` (browser storage)
- Access tokens auto-refresh before expiry (on 401)
- HTTPS enforced in production
- CORS restricted to backend origin
- All admin actions logged in audit trail

## Roadmap

- [ ] Dark mode toggle
- [ ] Search/filter on all list pages
- [ ] Bulk actions (suspend multiple users, etc)
- [ ] Analytics & reporting dashboard
- [ ] Admin user management (create/delete admins)
- [ ] Two-step verification backup codes
- [ ] Export audit logs (CSV, JSON)

---

**Docs**: See `/api/admin/docs` (Swagger UI) for full API spec.
