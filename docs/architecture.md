# Architecture

- **Frontend**: Next.js. Pages: login, register, flight search (with a booking dialog),
  my trips (with cancel), and a security-alerts admin page. Loyalty balance in the header.
- **Backend**: FastAPI. Routers: `auth` (login, register, logout, password, me),
  `flights` (search), `bookings` (book, list, get, cancel), `admin` (security events, alerts).
- **Data model**: per-user ownership. `users` (traveller, with `loyalty_points`),
  `flights` (shared synthetic inventory), `bookings` (owned by a traveller);
  `security_events` (append-only) and `alerts`. Money is integer pence.
- **Booking**: reserves seats and credits loyalty points in one transaction; cancel
  releases seats.
- **Demo data**: `python -m app.cli seed-demo` (see `app/demo_data.py`).
