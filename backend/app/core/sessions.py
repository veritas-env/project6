"""Server-side sessions in Redis (A07).

- The cookie holds a random 256-bit token; Redis stores only its SHA-256 digest.
- A new token is issued at every login (no fixation).
- Idle timeout is enforced by the Redis TTL; absolute timeout by `created`.
- Logout destroys the session; password change destroys all of the user's sessions.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from redis import Redis

from .security import new_token, token_digest

SESSION_COOKIE = "__Host-sid"
CSRF_COOKIE = "__Host-csrf"
CSRF_HEADER = "X-CSRF-Token"


@dataclass
class SessionData:
    digest: str
    user_id: str
    csrf: str
    created: float


class SessionStore:
    def __init__(self, redis: Redis, idle_seconds: int, absolute_seconds: int):
        self.r = redis
        self.idle = idle_seconds
        self.absolute = absolute_seconds

    @staticmethod
    def _key(digest: str) -> str:
        return f"sess:{digest}"

    @staticmethod
    def _user_key(user_id: str) -> str:
        return f"usess:{user_id}"

    def create(self, user_id: str) -> tuple[str, SessionData]:
        token = new_token()
        data = SessionData(token_digest(token), user_id, new_token(), time.time())
        payload = json.dumps({"user_id": user_id, "csrf": data.csrf, "created": data.created})
        pipe = self.r.pipeline()
        pipe.set(self._key(data.digest), payload, ex=self.idle)
        pipe.sadd(self._user_key(user_id), data.digest)
        pipe.expire(self._user_key(user_id), self.absolute)
        pipe.execute()
        return token, data

    def get(self, token: str | None) -> SessionData | None:
        if not token or len(token) > 128:
            return None
        digest = token_digest(token)
        raw = self.r.get(self._key(digest))
        if raw is None:
            return None
        obj = json.loads(raw)
        if time.time() - obj["created"] > self.absolute:
            self.destroy_digest(digest, obj["user_id"])
            return None
        self.r.expire(self._key(digest), self.idle)  # sliding idle timeout
        return SessionData(digest, obj["user_id"], obj["csrf"], obj["created"])

    def destroy_digest(self, digest: str, user_id: str) -> None:
        pipe = self.r.pipeline()
        pipe.delete(self._key(digest))
        pipe.srem(self._user_key(user_id), digest)
        pipe.execute()

    def destroy_all(self, user_id: str) -> int:
        digests = self.r.smembers(self._user_key(user_id))
        pipe = self.r.pipeline()
        for d in digests:
            pipe.delete(self._key(d.decode() if isinstance(d, bytes) else d))
        pipe.delete(self._user_key(user_id))
        pipe.execute()
        return len(digests)


def hit_rate_limit(r: Redis, key: str, limit: int, window_seconds: int) -> bool:
    """Fixed-window counter. Returns True when the caller is OVER the limit."""
    k = f"rl:{key}"
    count = r.incr(k)
    if count == 1:
        r.expire(k, window_seconds)
    return count > limit
