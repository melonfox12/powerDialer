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
