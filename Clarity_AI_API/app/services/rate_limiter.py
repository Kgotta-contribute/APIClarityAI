import time
import threading
from collections import defaultdict
from typing import Tuple
from fastapi import Request

class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding-window rate limiter.
    Tracks timestamps of requests per client key (IP or user ID).
    """
    def __init__(self, max_requests: int = 2, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests = defaultdict(list)
        self._lock = threading.Lock()

    def check_rate_limit(self, client_id: str) -> Tuple[bool, int]:
        """
        Checks whether client_id is allowed to make a request.
        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        now = time.time()
        with self._lock:
            timestamps = self._requests[client_id]
            # Purge timestamps outside the active sliding window
            cutoff = now - self.window_seconds
            self._requests[client_id] = [t for t in timestamps if t > cutoff]
            active_requests = self._requests[client_id]

            if len(active_requests) < self.max_requests:
                # Allow request and record timestamp
                self._requests[client_id].append(now)
                return True, 0
            else:
                # Rate limit exceeded - calculate time until oldest request in window expires
                oldest_timestamp = active_requests[0]
                retry_after = max(1, int(oldest_timestamp + self.window_seconds - now))
                return False, retry_after

    def reset(self, client_id: str = None):
        with self._lock:
            if client_id:
                self._requests.pop(client_id, None)
            else:
                self._requests.clear()

# Global singleton rate limiter: 2 requests per 60 seconds
chat_rate_limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)

def get_client_ip(request: Request) -> str:
    """
    Extracts the true client IP address, checking reverse-proxy headers first.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First IP in the comma-separated list is the client IP
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"
