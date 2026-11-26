# TravelEase

A flight-booking site for travellers: search flights, book and cancel, earn loyalty
points, and see your trips. Travellers self-register. Runs on synthetic data only.

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| Data | PostgreSQL 16, Redis 7 |
| Deploy | Docker Compose behind Nginx and the lab TLS gateway |

Each traveller has their own account, bookings and loyalty balance; a platform admin can
see the security event log and alerts.

## Run the tests

```
cd backend
../.venv/Scripts/python.exe -m pytest -q
```

## Run with Docker

```
cp .env.example .env      # fill in every secret
make build up
docker compose -f deployment/compose.yaml --env-file .env run --rm backend \
    python -m app.cli seed-demo --passwords-out /data/uploads/../demo-passwords.json
```

Demo data: travellers, a 60-day flight schedule across 12 airports, and some bookings.
Passwords are written only to the `--passwords-out` file.

## Documentation

- [docs/architecture.md](docs/architecture.md)
- [docs/security-model.md](docs/security-model.md)
- [docs/test-plan.md](docs/test-plan.md)
- [docs/operations.md](docs/operations.md)
