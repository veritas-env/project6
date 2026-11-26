"""Acceptance checks against a DEPLOYED instance (headers, cookies, exposure).
Things unit tests can't see because Nginx and TLS aren't in the loop there.

    python security/acceptance/check_deployment.py https://app.lab.example.com

Standard library only. Read-only: GET/OPTIONS plus one failed login with a random
address (which is logged as a failed sign-in, as it should be).
Exit 0 = all checks passed."""

from __future__ import annotations

import json
import secrets
import sys
import urllib.error
import urllib.request

REQUIRED_HEADERS = {
    "strict-transport-security": lambda v: "max-age=" in v and int(v.split("max-age=")[1].split(";")[0]) >= 15552000,
    "x-content-type-options": lambda v: v.lower() == "nosniff",
    "x-frame-options": lambda v: v.upper() == "DENY",
    "referrer-policy": lambda v: bool(v),
    "permissions-policy": lambda v: "camera=()" in v,
    "content-security-policy": lambda v: "unsafe-inline" not in v.split("script-src")[-1].split(";")[0] and "frame-ancestors 'none'" in v,
}
LEAKY_HEADERS = ["server", "x-powered-by", "x-aspnet-version"]
MUST_404 = ["/.git/config", "/.env", "/api/docs", "/api/openapi.json", "/docs", "/server-status", "/.DS_Store"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


opener = urllib.request.build_opener(NoRedirect)


def fetch(url: str, method: str = "GET", headers: dict | None = None, data: bytes | None = None):
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    try:
        with opener.open(req, timeout=15) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.headers.get_all("Set-Cookie") or []


def main(base: str) -> int:
    base = base.rstrip("/")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, info: str = ""):
        results.append((name, ok, info))

    for path in ("/login", "/api/health"):
        status, h, _ = fetch(base + path)
        check(f"{path} reachable", status == 200, str(status))
        for name, rule in REQUIRED_HEADERS.items():
            v = h.get(name, "")
            check(f"{path} header {name}", bool(v) and rule(v), v[:80])
        for name in LEAKY_HEADERS:
            v = h.get(name, "")
            check(f"{path} no version in {name}", not any(ch.isdigit() for ch in v), v)

    for path in MUST_404:
        status, _, _ = fetch(base + path)
        check(f"{path} not exposed", status == 404, str(status))

    status, h, _ = fetch(base + "/api/v1/auth/me", "OPTIONS",
                         {"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    check("no CORS for foreign origin", "access-control-allow-origin" not in h, h.get("access-control-allow-origin", ""))

    body = json.dumps({"email": f"probe-{secrets.token_hex(4)}@invalid.test", "password": "Not-a-real-password-1"}).encode()
    status, h, cookies = fetch(base + "/api/v1/auth/login", "POST", {"Content-Type": "application/json"}, body)
    check("failed login is generic 401", status == 401, str(status))
    check("failed login sets no session", not any(c.startswith("__Host-sid=") for c in cookies), "; ".join(cookies))

    status, h, _ = fetch(base + "/api/v1/auth/login", "POST", {"Content-Type": "application/x-www-form-urlencoded"}, b"a=b")
    check("form-encoded API post refused", status == 415, str(status))

    if base.startswith("https://"):
        status, h, _ = fetch("http://" + base[len("https://"):] + "/login")
        check("plain HTTP redirects to HTTPS", status in (301, 308) and h.get("location", "").startswith("https://"),
              f"{status} {h.get('location', '')}")

    width = max(len(n) for n, _, _ in results)
    for name, ok, info in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {info if not ok else ''}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
