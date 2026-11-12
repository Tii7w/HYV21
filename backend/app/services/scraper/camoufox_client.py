"""
Scrapling StealthyFetcher tabanlı sayfa çekici.
Önceki Camoufox doğrudan kullanımının yerini aldı.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .sahibinden_scraper import fetch_page
from .proxy_manager import ProxyManager, RotationStrategy


def fetch_with_stealth(
    url: str,
    proxy_manager: ProxyManager | None = None,
    headless: bool = True,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    URL'yi StealthyFetcher ile çeker.
    (records, has_next) döndürür.
    proxy_manager geçilirse başarı/başarısızlık rapor edilir (ileride entegrasyon için).
    """
    proxy = proxy_manager.get_proxy() if proxy_manager else None
    try:
        records, has_next = fetch_page(url, headless=headless)
        if proxy and proxy_manager:
            proxy_manager.report_success(proxy)
        return records, has_next
    except Exception as exc:
        if proxy and proxy_manager:
            proxy_manager.report_failure(proxy, is_block=True)
        raise
