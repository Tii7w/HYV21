"""
HKY Estates V2 - Kaynak bazlı istek sınırlayıcı
Dakikalık ve saatlik Token Bucket ile eşzamanlılık sınırını birlikte uygular.
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


class AcquireCancelled(Exception):
    """Bekleme sırasında görev durduruldu."""


class TokenBucket:
    def __init__(self, capacity: int, refill_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = max(1, capacity)
        self.rate = self.capacity / refill_seconds
        self._clock = clock
        self._tokens = float(self.capacity)
        self._updated = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
        self._updated = now

    def wait_time(self) -> float:
        """Bir jeton için beklenecek süre; 0 ise hemen alınabilir."""
        with self._lock:
            self._refill()
            return 0.0 if self._tokens >= 1 else (1 - self._tokens) / self.rate

    def try_consume(self) -> bool:
        with self._lock:
            self._refill()
            if self._tokens < 1:
                return False
            self._tokens -= 1
            return True

    def refund(self) -> None:
        with self._lock:
            self._tokens = min(self.capacity, self._tokens + 1)


@dataclass(frozen=True)
class RateLimitConfig:
    per_minute: int = 30
    per_hour: int = 600
    max_concurrency: int = 2
    min_interval_ms: int = 1000


class SourceRateLimiter:
    """Bir veri kaynağının kuyruğu: sıradaki istek jeton ve boş yuva bulana kadar bekler."""

    def __init__(self, config: RateLimitConfig, should_cancel: Optional[Callable[[], bool]] = None) -> None:
        self.config = config
        self.should_cancel = should_cancel or (lambda: False)
        self._minute = TokenBucket(config.per_minute, 60.0)
        self._hour = TokenBucket(config.per_hour, 3600.0)
        self._slots = threading.BoundedSemaphore(max(1, config.max_concurrency))
        self._interval_lock = threading.Lock()
        self._last_request = 0.0
        self._waiting = 0
        self._waiting_lock = threading.Lock()

    @property
    def waiting(self) -> int:
        with self._waiting_lock:
            return self._waiting

    def _sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            if self.should_cancel():
                raise AcquireCancelled()
            time.sleep(min(0.2, remaining))

    def acquire(self) -> None:
        with self._waiting_lock:
            self._waiting += 1
        try:
            while not self._slots.acquire(timeout=0.2):
                if self.should_cancel():
                    raise AcquireCancelled()
            try:
                self._wait_for_tokens()
                self._respect_interval()
            except BaseException:
                self._slots.release()
                raise
        finally:
            with self._waiting_lock:
                self._waiting -= 1

    def _wait_for_tokens(self) -> None:
        while True:
            wait = max(self._minute.wait_time(), self._hour.wait_time())
            if wait > 0:
                self._sleep(wait)
                continue
            # İki kovadan biri yetersizse diğerinden jeton harcanmaz.
            if self._minute.try_consume():
                if self._hour.try_consume():
                    return
                self._minute.refund()

    def _respect_interval(self) -> None:
        with self._interval_lock:
            gap = self.config.min_interval_ms / 1000 - (time.monotonic() - self._last_request)
            if gap > 0:
                self._sleep(gap)
            self._last_request = time.monotonic()

    def release(self) -> None:
        self._slots.release()
