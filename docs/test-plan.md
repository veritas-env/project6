# Test plan

| Layer | What | Where | When |
|---|---|---|---|
| Unit + integration | API behaviour on real PostgreSQL | `backend/tests/` | every push (CI) |
| Negative security | one suite per OWASP 2025 category | `backend/tests/security/test_a01…a10_*.py` | every push (CI) |
| Supply chain | lockfiles, pins, audits, image scan | `test_a03_supply_chain.py`, CI jobs | every push |
| Deployment acceptance | headers, exposure, CORS, cookies | `security/acceptance/check_deployment.py` | after each deploy |
| Baseline DAST | ZAP baseline + Nuclei against the deployed app | run from the lab scanner host | before each release |

A release is accepted only when all of the above pass.
