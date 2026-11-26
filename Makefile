# Common tasks. On Windows run these from Git Bash.
COMPOSE = docker compose -f deployment/compose.yaml --env-file .env
PY ?= .venv/Scripts/python.exe

.PHONY: help test lock audit build up down logs migrate seed acceptance

help:
	@echo "test        backend tests incl. the ten OWASP security suites"
	@echo "lock        regenerate hash-locked Python requirements (Linux, Python 3.12)"
	@echo "audit       pip-audit + npm audit"
	@echo "build/up/down/logs   docker compose lifecycle"
	@echo "migrate     run database migrations in the stack"
	@echo "seed FILE=seed.json  create seed accounts; passwords go to ./var/seed-passwords.json"
	@echo "acceptance URL=https://...   header/exposure checks against a deployment"

test:
	cd backend && ../$(PY) -m pytest -q

lock:
	cd backend && ../$(PY) -m uv pip compile requirements.in --generate-hashes --python-version 3.12 --python-platform x86_64-manylinux_2_28 -o requirements.lock
	cd backend && ../$(PY) -m uv pip compile requirements-dev.in --generate-hashes --python-version 3.12 --python-platform x86_64-manylinux_2_28 -o requirements-dev.lock

audit:
	cd backend && ../$(PY) -m pip_audit -r requirements.lock --require-hashes --disable-pip --strict
	cd frontend && npm audit --audit-level=low

build:
	$(COMPOSE) build
up:
	$(COMPOSE) up -d
down:
	$(COMPOSE) down
logs:
	$(COMPOSE) logs -f --tail=100

migrate:
	$(COMPOSE) run --rm migrate

seed:
	mkdir -p var
	$(COMPOSE) run --rm -v "$(abspath $(FILE)):/seed.json:ro" -v "$(abspath var):/out" backend python -m app.cli seed --file /seed.json --passwords-out /out/seed-passwords.json

acceptance:
	$(PY) security/acceptance/check_deployment.py $(URL)
