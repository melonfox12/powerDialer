import http.client
import threading

class _ConnectionPool:
    """Reuse a few HTTPS connections to the Supabase host."""

    def __init__(self, host, timeout, size=4):
        self.host = host
        self.timeout = timeout
        self.size = size
        self._lock = threading.Lock()
        self._idle = []

    def _new(self):
        return http.client.HTTPSConnection(self.host, timeout=self.timeout)

    def send(self, method, path, body, headers):
        last_error = None
        for _attempt in range(2):
            with self._lock:
                conn = self._idle.pop() if self._idle else None
            if conn is None:
                conn = self._new()
            try:
                conn.request(method, path, body=body, headers=headers)
                response = conn.getresponse()
                payload = response.read()
                status = response.status
            except (http.client.HTTPException, OSError, TimeoutError) as exc:
                conn.close()
                last_error = exc
                continue
            with self._lock:
                if len(self._idle) < self.size:
                    self._idle.append(conn)
                else:
                    conn.close()
            return status, payload
        raise OSError(f"Could not reach Supabase: {last_error}")

import base64
import json
import threading
import time
import urllib.parse

class SupabaseClient:
    def __init__(self, url, service_key, timeout=20, anon_key=""):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("SUPABASE_URL must be an HTTPS project URL.")
        if not service_key:
            raise ValueError("Set SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY in .env.")
        if service_key.startswith(("sb_publishable_", "sb_anon_")):
            raise ValueError(
                "A publishable/anon Supabase key cannot access server-side storage. "
                "Use a Supabase secret key or legacy service_role key."
            )
        if service_key.count(".") == 2:
            try:
                payload = service_key.split(".")[1]
                claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("The Supabase server key is invalid.") from exc
            if not isinstance(claims, dict) or claims.get("role") != "service_role":
                raise ValueError(
                    "The Supabase JWT must have the service_role role for server-side storage."
                )
        self.project_url = url.rstrip("/")
        self.base_url = self.project_url + "/rest/v1/"
        self.service_key = service_key
        self.anon_key = (anon_key or "").strip()
        self.timeout = timeout
        self._pool = _ConnectionPool(urllib.parse.urlsplit(self.project_url).netloc, timeout)
        self._auth_cache = {}
        self._auth_lock = threading.Lock()

    @classmethod
    def from_env(cls, values):
        url = values.get("SUPABASE_URL", "").strip()
        key = (
            values.get("SUPABASE_SECRET_KEY", "").strip()
            or values.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        )
        anon = (
            values.get("SUPABASE_ANON_KEY", "").strip()
            or values.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
        )
        if bool(url) != bool(key):
            raise ValueError(
                "Configure both SUPABASE_URL and SUPABASE_SECRET_KEY "
                "(or SUPABASE_SERVICE_ROLE_KEY), or remove both to use local JSON storage."
            )
        return cls(url, key, anon_key=anon) if url else None

    def auth_user(self, access_token):
        token = (access_token or "").strip()
        if not token:
            return None
        now = time.time()
        with self._auth_lock:
            cached = self._auth_cache.get(token)
            if cached and cached[0] > now:
                return cached[1]
        user = self._fetch_auth_user(token)
        if user:
            with self._auth_lock:
                self._auth_cache[token] = (now + 60, user)
                if len(self._auth_cache) > 64:
                    self._auth_cache = {
                        key: value for key, value in self._auth_cache.items() if value[0] > now
                    }
        return user

    def _fetch_auth_user(self, token):
        status, result = self._pool.send("GET", "/auth/v1/user", None, {
            "apikey": self.anon_key or self.service_key,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        if status in (401, 403):
            return None
        if status >= 400:
            raise OSError(f"Supabase auth HTTP {status}")
        try:
            payload = json.loads(result.decode("utf-8")) if result else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OSError("Supabase auth returned an invalid JSON response.") from exc
        user_id = payload.get("id") if isinstance(payload, dict) else None
        if not user_id:
            return None
        return {"id": str(user_id), "email": str(payload.get("email") or "")}

    def request(self, method, resource, params=None, payload=None, prefer=None):
        path = "/rest/v1/" + resource
        if params:
            path += "?" + urllib.parse.urlencode(params)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        status, result = self._pool.send(method, path, body, headers)
        if status >= 400:
            try:
                error_body = json.loads(result.decode("utf-8"))
                if not isinstance(error_body, dict):
                    raise ValueError("Unexpected error response")
                message = error_body.get("message", "Supabase request failed")
            except (ValueError, OSError, UnicodeDecodeError):
                message = "Supabase request failed"
            raise OSError(f"Supabase HTTP {status}: {message}")
        if not result:
            return None
        try:
            return json.loads(result.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OSError("Supabase returned an invalid JSON response.") from exc

    def select_all(self, resource, params=None, page_size=500):
        rows = []
        offset = 0
        while True:
            page_params = dict(params or {})
            page_params.update({"limit": str(page_size), "offset": str(offset)})
            page = self.request("GET", resource, page_params)
            if not isinstance(page, list):
                raise OSError(f"Supabase returned an invalid {resource} response.")
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += page_size
