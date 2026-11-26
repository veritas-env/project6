# Operations

- **Configure:** copy `.env.example` to `.env`; every secret is required (compose refuses to start otherwise).
- **Start / stop:** `make up`, `make down`. Logs: `make logs` (JSON lines, one per request plus security events).
- **Accounts:** `make seed FILE=seed.json`; generated passwords land in `var/seed-passwords.json` (git-ignored).
- **Reset to empty:** `docker compose ... run --rm backend python -m app.cli reset --yes --force`.
- **Alerts:** platform admins see them at `/admin`.
- **Backups:** `docker compose ... exec postgres pg_dump -U postgres app > backup.sql` (store encrypted).
- **Emergency stop:** `make down` stops every container of the app; the gateway then returns 502.
