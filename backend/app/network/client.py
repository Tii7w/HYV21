"""
HKY Estates V2 - Network yönetimi
Tüm dış istekler buradan geçer: hız sınırı, zaman aşımı, kontrollü tekrar ve Dead Letter kaydı.
403 asla tekrar denenmez; 429 yalnızca Retry-After bildirilirse bir kez beklenip denenir.
Proxy tekildir ve ban sonrası değiştirilmez; platform kısıtlarını aşmak için kullanılamaz.
"""

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..security import redact
from .rate_limiter import AcquireCancelled, SourceRateLimiter

BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 30.0
MAX_RETRY_AFTER_SECONDS = 300
RETRY_429_LIMIT = 1

# Bu adreslere yalnızca resmi API sözleşmesiyle erişilebilir; site sayfaları istenmez.
BLOCKED_HOST_SUFFIXES = ("sahibinden.com",)


class NetworkError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, attempts: int = 1) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts


class AccessDeniedError(NetworkError):
    """403: yetkili erişim kontrol edilmeden kaynağa tekrar istek gönderilmez."""


class RateLimitedError(NetworkError):
    """429: kaynağın sınırına uyulamadı; tarama durdurulur."""


class BlockedHostError(NetworkError):
    """İzinli olmayan bir adrese istek engellendi."""


class RequestCancelled(NetworkError):
    pass


@dataclass(frozen=True)
class ProxyConfig:
    scheme: str
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None

    def url(self) -> str:
        auth = ""
        if self.username:
            auth = f"{httpx.URL('http://x').copy_with(username=self.username, password=self.password or '').userinfo.decode()}@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"


def safe_url(url: str) -> str:
    """Sorgu parametreleri anahtar içerebileceği için kayıtlardan çıkarılır."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))


def is_blocked_host(url: str, official_api: bool = False) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if official_api:
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in BLOCKED_HOST_SUFFIXES)


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class NetworkClient:
    def __init__(
        self,
        source_key: str,
        limiter: SourceRateLimiter,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        proxy: Optional[ProxyConfig] = None,
        official_api: bool = False,
        on_failure: Optional[Callable[[str, Optional[int], str, int], None]] = None,
        on_request_failed: Optional[Callable[[], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.source_key = source_key
        self.limiter = limiter
        self.max_retries = max(0, max_retries)
        self.official_api = official_api
        self.on_failure = on_failure or (lambda *_: None)
        self.on_request_failed = on_request_failed or (lambda: None)
        self.should_cancel = should_cancel or (lambda: False)
        self._sleep_fn = sleep
        self._http = httpx.Client(
            timeout=timeout_seconds,
            proxy=proxy.url() if proxy and transport is None else None,
            transport=transport,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._http.close()

    def _backoff(self, attempt: int) -> float:
        delay = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2**attempt))
        return delay / 2 + random.uniform(0, delay / 2)

    def _wait(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        if self._sleep_fn is not time.sleep:
            self._sleep_fn(seconds)
            return
        while (remaining := deadline - time.monotonic()) > 0:
            if self.should_cancel():
                raise RequestCancelled("İstek görev durdurulduğu için iptal edildi.")
            time.sleep(min(0.2, remaining))

    def _fail(self, error: NetworkError, url: str) -> NetworkError:
        self.on_failure(safe_url(url), error.status_code, redact(str(error)), error.attempts)
        return error

    def get_json(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        if is_blocked_host(url, self.official_api):
            raise self._fail(BlockedHostError(f"{safe_url(url)} adresine izinsiz istek engellendi."), url)

        attempt = 0
        limited_retries = 0
        while True:
            try:
                self.limiter.acquire()
            except AcquireCancelled as exc:
                raise RequestCancelled("İstek görev durdurulduğu için iptal edildi.") from exc

            attempts_made = attempt + limited_retries + 1
            try:
                response = self._http.get(url, headers=headers, params=params)
            except httpx.TimeoutException:
                self.on_request_failed()
                if attempt >= self.max_retries:
                    raise self._fail(NetworkError("Zaman aşımı; deneme hakkı bitti.", None, attempts_made), url)
                self._wait(self._backoff(attempt))
                attempt += 1
                continue
            except httpx.HTTPError as exc:
                self.on_request_failed()
                if attempt >= self.max_retries:
                    raise self._fail(NetworkError(f"Bağlantı hatası: {redact(exc)}", None, attempts_made), url)
                self._wait(self._backoff(attempt))
                attempt += 1
                continue
            finally:
                self.limiter.release()

            code = response.status_code
            if code == 403:
                self.on_request_failed()
                raise self._fail(
                    AccessDeniedError("403 Erişim reddedildi. Yetkili erişim bilgilerini kontrol edin.", 403, attempts_made),
                    url,
                )
            if code == 429:
                self.on_request_failed()
                retry_after = parse_retry_after(response.headers.get("Retry-After"))
                if retry_after is None or retry_after > MAX_RETRY_AFTER_SECONDS or limited_retries >= RETRY_429_LIMIT:
                    raise self._fail(
                        RateLimitedError("429 Hız sınırı aşıldı; tarama bu kaynak için durduruldu.", 429, attempts_made),
                        url,
                    )
                self._wait(retry_after)
                limited_retries += 1
                continue
            if code >= 500:
                self.on_request_failed()
                if attempt >= self.max_retries:
                    raise self._fail(NetworkError(f"Sunucu hatası ({code}); deneme hakkı bitti.", code, attempts_made), url)
                self._wait(self._backoff(attempt))
                attempt += 1
                continue
            if code >= 300:
                self.on_request_failed()
                raise self._fail(NetworkError(f"Beklenmeyen yanıt ({code}).", code, attempts_made), url)

            try:
                return response.json()
            except ValueError as exc:
                raise self._fail(NetworkError("Kaynak geçerli JSON döndürmedi.", code, attempts_made), url) from exc
