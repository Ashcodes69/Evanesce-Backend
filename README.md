# evanesce — backend

FastAPI backend for evanesce, a privacy-focused messaging app inspired by disappearing-message concepts. Nobody can message you until you approve them, messages don't stick around, and files you share are deleted from the server once they've been downloaded.

## Stack

- **FastAPI** + **WebSockets** for real-time messaging, presence, and typing indicators
- **PostgreSQL** (via SQLAlchemy) — hosted on [Supabase](https://supabase.com) in production
- **Supabase Storage** — private bucket holding encrypted file blobs (a local-disk backend is used in development)
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

### Encrypted file sharing
Share a file without the server ever storing it in readable form.

How it works:
1. The sender's browser encrypts the file (AES-256-GCM, in 1 MiB chunks) and uploads only the encrypted bytes.
2. The server stores the blob in a private Supabase Storage bucket under a random key, plus a `file_transfers` row (sender, receiver, size, status, expiry). It never receives the original filename or content type.
3. The sender sends the receiver a chat message carrying the transfer id, filename, size, and the decryption key (`evanesce-file:1:{...}`). The WebSocket layer only accepts a message like this if it points at a real, pending, unexpired transfer from that sender to that receiver.
4. The receiver's browser downloads the encrypted bytes, decrypts them locally, saves the file, and then reports completion.
5. About 10 seconds after completion the file card disappears from the chat, and a cleanup sweeper deletes the stored blob and the transfer row.

Encrypted file format ("DEAD" v2): an 18-byte header followed by encrypted chunks.
- Header: magic `DEAD`, version `2`, algorithm `1` (AES-256-GCM), chunk size (1 MiB, big-endian u32), 8-byte random nonce prefix
- Each chunk: up to 1 MiB of data plus a 16-byte GCM tag
- Every chunk is authenticated together with the header, its position, and a final-chunk flag, so reordering, swapping, or truncating chunks makes decryption fail
- The server only checks that an upload has this shape; it cannot look inside

Endpoints:

| Method | Path | Who | What |
| --- | --- | --- | --- |
| `POST` | `/files/upload` | sender (must be connected to the receiver) | multipart form with `receiver_id` and `file`; returns `201` with `id`, `size_bytes`, `expires_at` |
| `GET` | `/files/{id}/download` | receiver only | returns the encrypted bytes |
| `POST` | `/files/{id}/complete` | receiver only | marks the transfer downloaded and shortens the file message's timer |

Rules:
- Only users with an accepted connection can send each other files, and the receiver must still be connected to download.
- A transfer that doesn't exist and a transfer that belongs to someone else both return `404`, so ids can't be probed. Expired or already-completed transfers return `410`.
- Limits are constants at the top of `app/services/storage_service.py`: 20 MB per encrypted file, 48 hour lifetime, 600 MB total of pending files (sized for Supabase's free tier).
- If a download or decryption fails, completion is never reported, and the receiver can retry until the transfer expires.
- The browser side lives in the frontend repo (`evanesce-frontend-v2`, `src/features/files`). The message prefix `evanesce-file:1:` must match in both repos.

### Background tasks
- Disappearing-message sweeper (event-driven wake + idle polling, not constant tight polling)
- OTP cleanup: deleted immediately on successful verification, swept periodically if expired and unused
- File cleanup sweeper: every 30 seconds, deletes the stored blob and then the row for downloaded transfers (after a 60 second grace period) and for pending transfers past their expiry, together with the linked file message. A failed blob delete keeps the row so the next pass retries.

## Security notes

What the design protects:
- File contents and filenames are encrypted or withheld before they reach the server, so storage holds only ciphertext under random names.
- The upload request carries neither the original file bytes nor the key.
- Blobs, rows, and key messages are deleted after download or expiry.

What it does not protect (read this before relying on it):
- **Not end-to-end encrypted.** The file's key travels in a chat message. Live delivery over the WebSocket is plaintext to the server, and messages are decryptable by the server while they exist. Someone with access to the running server could read the key and decrypt the blob during the transfer's lifetime. Deleting both after download keeps that window short.
- The server still sees who sent what to whom, file sizes, and timing.
- The receiver keeps whatever they downloaded. Nothing stops them from copying, screenshotting, or forwarding a file, and "downloaded" means decrypted and handed to the browser, not opened.
- Uploads are checked for shape only. Ciphertext can't be scanned, so there is no malware or content scanning.
- Deletion relies on the storage provider. If the bucket ever gains versioning or backups, revisit this.
- The bucket must stay private, and the Supabase secret key belongs on the server only.

## Project structure

```
app/
├── api/            # route handlers (users, messages, connections, files, websocket)
├── core/           # security (hashing, encryption, JWT), email sending
├── db/             # database engine/session setup
├── models/         # SQLAlchemy models
├── schemas/        # Pydantic request/response schemas
└── services/       # business logic (otp, connections, messages/sweeper, file cleanup, blob storage)
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

# file storage (production)
SUPABASE_URL=https://<project-ref>.supabase.co   # project URL, not the database host
SUPABASE_SERVICE_KEY=...                         # secret key, server-side only
SUPABASE_BUCKET=...                              # a private bucket

# development only
STORAGE_BACKEND=local        # keeps blobs in .dev_storage/ instead of Supabase
```

Storage notes:
- Create the bucket in the Supabase dashboard with **Public bucket turned off**. No storage policies are needed, because the server uses the secret key.
- `STORAGE_BACKEND` defaults to `supabase`. Leave it unset in production, and never set it to `local` on Render, whose disk is temporary.
- Keep `.dev_storage/` in `.gitignore`.

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

Commit the new file in `alembic/versions/` — without it production has nothing to run.

## Deploying

Render does **not** run migrations on deploy. Before merging a change that includes a migration, apply it to the production database from your own machine. Set the production `DATABASE_URL` for that shell session only (a value already in the environment takes precedence over `.env`), check where the database stands, upgrade, then clear it:

```powershell
$env:DATABASE_URL = "<production url>"
alembic current
alembic upgrade head
Remove-Item Env:DATABASE_URL
```

If `alembic current` prints `(head)` right away, the URL is pointing at your local database, not production.

## Notes

- Free-tier hosting (Render) means the backend sleeps after ~15 minutes of inactivity. The first request after a period of inactivity can take 30–60 seconds to wake it back up — this is expected, not a bug.
- The sweepers run inside the web process, so they pause while the service sleeps. Expired files can stay in storage until it wakes, but downloads of expired transfers are refused regardless.
- Outbound SMTP is blocked on Render's free tier, which is why email goes through Brevo's HTTPS API rather than raw SMTP.
