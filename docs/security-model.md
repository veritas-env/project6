# Security model

TravelEase's security controls. Each row names the code that implements the control
and the test suite that proves it. Business rules and threats are in section 3.

## 1. Trust boundaries

```
Browser ──HTTPS──▶ VPS TLS gateway ──▶ app Nginx ──▶ frontend (Next.js)
                                                └──▶ backend (FastAPI) ──▶ Postgres, Redis
```

- Only the app's Nginx publishes a port, on 127.0.0.1, for the gateway.
- Frontend, backend, Postgres and Redis are on internal Docker networks with no internet route.
- The backend trusts `X-Forwarded-For` only from the app's own Nginx (fixed address).
- The running app connects to Postgres as `app_rw` (data only, no DDL). Migrations run
  as `app_owner` in a one-shot container.

## 2. Controls by OWASP Top 10:2025 category

| Cat | Control | Where | Proven by |
|---|---|---|---|
| A01 | Every route requires a session except sign-in; tenant routes require membership via per-user ownership; bookings loaded by (id, traveller_id); non-members get 404; CSRF token on all writes; JSON-only bodies; uploads stored by UUID; no redirects | `api/deps.py`, every router | `test_a01_access_control.py` (routes enumerated from OpenAPI) |
| A02 | Production refuses weak secrets and default DB credentials; API docs off in production; no CORS; security headers in Nginx; no version banners; generic JSON errors; hardened containers (read-only, no capabilities, no egress) | `core/config.py`, `main.py`, `deployment/` | `test_a02_configuration.py`, `security/acceptance/check_deployment.py` |
| A03 | Python deps hash-locked; npm lockfile with sha512 integrity and exact versions; base images and actions pinned by digest/SHA; pip-audit, npm audit, Trivy gate CI; SBOM per build | `backend/requirements*.lock`, `frontend/package-lock.json`, `deployment/`, `.github/workflows/ci.yml` | `test_a03_supply_chain.py`, CI |
| A04 | argon2id passwords; 256-bit tokens from `secrets`; session tokens stored only as SHA-256 digests; HMAC-SHA256 signed values with purpose and expiry; TLS at the gateway | `core/security.py`, `core/sessions.py` | `test_a04_cryptography.py` |
| A05 | Bound parameters only; typed query filters; React escaping, no raw HTML; validation errors do not echo input | `api/flights.py`, `api/bookings.py`, `core/errors.py`, frontend | `test_a05_injection.py` |
| A06 | Limits on page size and passenger count; seats cannot be oversold; a booking is cancelled once | routers, `schemas/` | `test_a06_business_rules.py` |
| A07 | Server-side sessions; new token every sign-in; logout and password change revoke server-side; idle 30 min / absolute 8 h; per-account lockout; per-IP rate limit (app and Nginx); generic errors; constant-time unknown-user path; password policy | `api/auth.py`, `core/sessions.py` | `test_a07_authentication.py` |
| A08 | Fares and loyalty points computed server-side; request models reject unknown fields (no mass assignment); no deserialisation of user data | `api/bookings.py`, `schemas/` | `test_a08_integrity.py` |
| A09 | Security events for sign-in, sign-out, denials, CSRF, lockout, bookings, cancellations; written in their own transaction; append-only (trigger + grants); immediate and threshold alert rules; admin alert view | `services/audit.py`, migration 0001 | `test_a09_logging_alerting.py` |
| A10 | One transaction per request with rollback on any error; generic 500 with request ID; fail closed when Redis is down | `core/db.py`, `core/errors.py` | `test_a10_exceptions.py` |

## 3. TravelEase threat model

| Asset | Threat | Abuse case | Control | Test |
|---|---|---|---|---|
| Bookings | Information disclosure | A traveller reads another's bookings | Bookings loaded by (id, traveller_id); others get 404 | `test_a01` |
| Seats | Tampering | Overbooking a flight | Seats reserved under a row lock; a check constraint caps them | `test_a06` |
| Fares & points | Tampering | A client submits its own price or points | Computed server-side; unknown fields rejected | `test_a08` |
| Loyalty | Design | — | (business-rule design is covered by the lab scenario) | — |
| Admin log | Elevation of privilege | A traveller reads security events | `platform_admin` only; routes return 404 otherwise | `test_a01`, `test_a09` |
