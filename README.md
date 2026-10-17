# evanesce — backend

FastAPI backend for evanesce, a privacy-focused messaging app inspired by disappearing-message concepts. Nobody can message you until you approve them, and messages don't stick around.

## Stack

- **FastAPI** + **WebSockets** for real-time messaging, presence, and typing indicators
- **PostgreSQL** (via SQLAlchemy) — hosted on [Supabase](https://supabase.com) in production
- **Alembic** for schema migrations
- **Brevo** for transactional email (OTP verification)
- **Fernet** (symmetric encryption) for email and message content at rest
- **HMAC-SHA256** for deterministic, searchable hashes (email lookups, OTP codes) without storing anything reversible
- **JWT** (via `python-jose`) for auth, password reset, and signup verification tokens
- Deployed on [Render](https://render.com)

## Core features

### Auth
- Email-based signup with OTP verification (6-digit code, 10 min expiry, single-use)
- Dual-column email storage: Fernet-encrypted (recoverable) + HMAC-hashed (for uniqueness/lookup without ever decrypting)
- Change username (password-gated, forces re-login), change full name, OTP-verified forgot/reset password

### Connections (message-gating system)
Nobody can message anybody until both sides opt in:
- Send request → accept / reject (reject = silent auto-block) / block (while connected) / unblock
- Blocked users are fully hidden — search returns 404, same as a nonexistent user, so blocking is never revealed
- Enforced on both the REST layer and the WebSocket layer

### Messaging
- Real-time via a single shared WebSocket connection per user, with presence (online/offline + last seen) and typing indicators
- Message lifecycle: `sent` → `delivered` → `seen`
- Content encrypted at rest (Fernet); decrypted only when returned to an authorized party
- Live delivery over the socket stays plaintext (already known to both parties in that moment) — only storage is encrypted

### Disappearing messages
- Each message gets a length-based timer (short messages disappear faster, longer ones get more time, clamped between a floor and ceiling)
- Timer starts for the **sender** immediately on send, and separately for both parties once the message is marked **seen**
- Hard-deleted from the database once its timer runs out — not soft-deleted, genuinely gone
- A lightweight background sweeper checks for expiries and pushes live removal events over WebSocket, so messages vanish from open chats without a refresh

### Background tasks
- Disappearing-message sweeper (event-driven wake + idle polling, not constant tight polling)
- OTP cleanup: deleted immediately on successful verification, swept periodically if expired and unused

## Project structure

```
app/
├── api/            # route handlers (users, messages, connections, websocket)
├── core/           # security (hashing, encryption, JWT), email sending
├── db/             # database engine/session setup
├── models/         # SQLAlchemy models
├── schemas/        # Pydantic request/response schemas
└── services/       # business logic (otp, connections, messages/sweeper)
alembic/            # migrations
```

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with:

```
DATABASE_URL=postgresql://...
SECRET_KEY=...
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
ENCRYPTION_KEY=...           # Fernet key, for email
MESSAGE_ENCRYPTION_KEY=...   # Fernet key, for messages (separate from email key)
EMAIL_HASH_SECRET=...
OTP_HASH_SECRET=...
BREVO_API_KEY=...
SMTP_USER=your-verified-sender@example.com
```

Run migrations:

```bash
alembic upgrade head
```

Start the server:

```bash
uvicorn app.main:app --reload
```

## Schema changes

This project uses Alembic — never hand-edit the database schema. After changing a model:

```bash
alembic revision --autogenerate -m "describe the change"
```

Review the generated migration file before applying it, then:

```bash
alembic upgrade head
```

## Notes

- Free-tier hosting (Render) means the backend sleeps after ~15 minutes of inactivity. The first request after a period of inactivity can take 30–60 seconds to wake it back up — this is expected, not a bug.
- Outbound SMTP is blocked on Render's free tier, which is why email goes through Brevo's HTTPS API rather than raw SMTP.
