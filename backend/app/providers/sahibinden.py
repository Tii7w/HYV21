"""
HKY Estates V2 - Sahibinden.com sağlayıcısı
Scrapling StealthyFetcher (Camoufox) ile bot tespitini atlatarak veri çeker.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from typing import Any, Iterator, List, Optional

from ..schemas import ListingFilters
from ..services.scraper.sahibinden_scraper import (
    PAGE_SIZE,
    CATEGORY_SLUG,
    NotAListingPage,
    build_search_url,
    fetch_page,
)
from .base import STATE_OK, STATE_NOT_CONFIGURED, ListingProvider, ProviderCheck, ProviderPage, ProviderUnavailable

REQUIRED_PACKAGES = ("scrapling", "patchright")

# Engel (bot doğrulaması / giriş yönlendirmesi) sonrası kimlik dinlenmeye alınır; bu sürede yeni
# tarama başlatılmaz. Engeli aşmaya çalışılmaz, yalnızca beklenir.
BLOCK_COOLDOWN = timedelta(minutes=30)
BLOCK_MARKER = "Sahibinden.com erişimi engelledi"


class SahibindenBlocked(ProviderUnavailable):
    """Sahibinden ilan listesi yerine doğrulama/engel sayfası döndürdü."""


def cooldown_message(source: Any, now: datetime) -> Optional[str]:
    """Kaynak engel sonrası beklemedeyse kullanıcıya gösterilecek mesaj, değilse None."""
    if getattr(source, "key", None) != "sahibinden" or source.last_checked_at is None:
        return None
    if BLOCK_MARKER not in (source.status_message or ""):
        return None
    remaining = source.last_checked_at + BLOCK_COOLDOWN - now
    if remaining.total_seconds() <= 0:
        return None
    minutes = int(remaining.total_seconds() // 60) + 1
    return (
        f"Sahibinden son denemede erişimi engelledi (bot doğrulaması). Kimlik dinlenmede: yaklaşık {minutes} dk "
        "sonra tekrar denenebilir. Bu sürede denemek engeli uzatır."
    )


def missing_packages() -> List[str]:
    return [name for name in REQUIRED_PACKAGES if importlib.util.find_spec(name) is None]


class SahibindenProvider(ListingProvider):
    """
    Sahibinden.com'dan ilan çeken provider.
    Her çağrıda StealthyFetcher (Camoufox) açılır; proxy_manager entegrasyonu
    camoufox_client üzerinden sağlanabilir.
    """

    def check(self) -> ProviderCheck:
        missing = missing_packages()
        if missing:
            return ProviderCheck(
                STATE_NOT_CONFIGURED,
                f"Scraper paketleri kurulu değil: {', '.join(missing)}",
            )
        return ProviderCheck(STATE_OK, "Scraper paketleri hazır.")

    def fetch(self, filters: ListingFilters, cursor: Optional[Any]) -> Iterator[ProviderPage]:
        # Kategori seçimi: filters.categories içindeki ilk tanınan kategori kullanılır.
        categories = [c for c in (filters.categories or []) if c in CATEGORY_SLUG]
        if not categories:
            # Ana kategori bazlı varsayılan
            if filters.main_category == "vasita":
                categories = ["otomobil"]
            else:
                categories = ["satilik-konut"]

        page_offset: int = int(cursor) if cursor is not None else 0

        for category in categories:
            offset = page_offset
            while True:
                url = build_search_url(category, filters, page_offset=offset)
                try:
                    records, has_next = fetch_page(url)
                except NotAListingPage as exc:
                    raise SahibindenBlocked(f"{BLOCK_MARKER}: {exc}") from exc
                except Exception as exc:
                    raise ProviderUnavailable(f"Sahibinden.com çekilemedi: {exc}") from exc

                next_cursor = offset + PAGE_SIZE if has_next else None
                yield ProviderPage(records=records, next_cursor=next_cursor)

                if not has_next:
                    break
                offset += PAGE_SIZE
