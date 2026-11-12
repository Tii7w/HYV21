"""
HKY Estates V2 - Sağlayıcı kayıt defteri
Ayarlardan hız sınırı, proxy ve hata geri çağrılarıyla kaynağa özel istemci kurar.
"""

from typing import Callable, Optional

from ..db import session_scope
from ..models import DataSource
from ..network.client import NetworkClient, ProxyConfig
from ..network.rate_limiter import RateLimitConfig, SourceRateLimiter
from ..schemas import AppSettings
from .authorized import AuthorizedDataProvider
from .base import ListingProvider
from .demo import DemoProvider
from .manual_import import ManualImportProvider
from .sahibinden import SahibindenProvider


def build_proxy(settings: AppSettings, password: Optional[str]) -> Optional[ProxyConfig]:
    proxy = settings.proxy
    if not (proxy.enabled and proxy.authorized_use and proxy.host and proxy.port):
        return None
    return ProxyConfig(proxy.scheme, proxy.host, proxy.port, proxy.username or None, password)


def build_client_factory(
    source: DataSource,
    settings: AppSettings,
    password: Optional[str],
    on_failure=None,
    on_request_failed=None,
    should_cancel=None,
) -> Callable[[], NetworkClient]:
    scan = settings.scan
    limiter = SourceRateLimiter(
        RateLimitConfig(scan.per_minute, scan.per_hour, scan.max_concurrent, scan.request_interval_ms),
        should_cancel=should_cancel,
    )

    def factory() -> NetworkClient:
        return NetworkClient(
            source.key,
            limiter,
            timeout_seconds=scan.timeout_seconds,
            max_retries=scan.max_retries,
            proxy=build_proxy(settings, password),
            on_failure=on_failure,
            on_request_failed=on_request_failed,
            should_cancel=should_cancel,
        )

    return factory


def build_provider(source: DataSource, client_factory: Callable[[], NetworkClient]) -> ListingProvider:
    if source.key == "sahibinden":
        return SahibindenProvider(source)
    if source.key == "authorized":
        return AuthorizedDataProvider(source, client_factory)
    if source.key == "manual_import":
        return ManualImportProvider(source, session_scope)
    if source.key == "demo":
        return DemoProvider(source)
    raise ValueError(f"Bilinmeyen kaynak: {source.key}")
