import threading

class TokenIndex:
    def __init__(self):
        self._lock = threading.Lock()
        self._tokens = {}

    def register(self, token, dialer):
        with self._lock:
            self._tokens[token] = dialer

    def forget(self, token):
        with self._lock:
            self._tokens.pop(token, None)

    def lookup(self, token):
        if not token:
            return None
        with self._lock:
            return self._tokens.get(token)
