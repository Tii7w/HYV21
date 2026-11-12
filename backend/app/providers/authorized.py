"""
HKY Estates V2 - Yetkili veri sağlayıcı
Kullanıcının izin/sözleşme ile eriştiği JSON beslemelerini okur. Tüm istekler NetworkClient'tan geçer.
"""

from typing import Any, Callable, Dict, Iterator, Optional

from ..network.client import AccessDeniedError, BlockedHostError, NetworkClient, NetworkError, RateLimitedError
from ..schemas import ListingFilters
from ..security import decrypt_secret
from .base import (
    STATE_ACCESS_DENIED,
    STATE_ERROR,
    STATE_NOT_CONFIGURED,
    STATE_OK,
    ListingProvider,
    ProviderCheck,
    ProviderPage,
    ProviderUnavailable,
)

MAX_PAGES = 2000


def read_path(document: Any, path: str) -> Any:
    """'data.items' biçimindeki yolu JSON içinde izler."""
    current = document
    for part in filter(None, path.split(".")):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


class AuthorizedDataProvider(ListingProvider):
    def __init__(self, source, client_factory: Callable[[], NetworkClient]) -> None:
        super().__init__(source)
        self.client_factory = client_factory

    @property
    def _config(self) -> Dict[str, Any]:
        return self.source.config or {}

    def _headers(self) -> Dict[str, str]:
        key = decrypt_secret(self.source.secret_encrypted)
        if not key:
            return {}
        return {self._config.get("auth_header") or "Authorization": f"{self._config.get('auth_prefix', 'Bearer ')}{key}"}

    def _missing_config(self) -> Optional[str]:
        if not self._config.get("base_url"):
            return "Besleme adresi tanımlı değil."
        if not self._config.get("authorized_use"):
            return "Bu kaynağı kullanma yetkiniz olduğunu Ayarlar ekranından onaylayın."
        return None

    def check(self) -> ProviderCheck:
        missing = self._missing_config()
        if missing:
            return ProviderCheck(STATE_NOT_CONFIGURED, missing)
        client = self.client_factory()
        try:
            document = client.get_json(self._config["base_url"], headers=self._headers())
        except AccessDeniedError as exc:
            return ProviderCheck(STATE_ACCESS_DENIED, str(exc))
        except (RateLimitedError, BlockedHostError, NetworkError) as exc:
            return ProviderCheck(STATE_ERROR, str(exc))
        finally:
            client.close()
        records = read_path(document, self._config.get("results_path") or "items")
        if not isinstance(records, list):
            return ProviderCheck(STATE_ERROR, "Yanıtta ilan listesi bulunamadı; sonuç yolunu kontrol edin.")
        return ProviderCheck(STATE_OK, f"Bağlantı başarılı; ilk yanıtta {len(records)} kayıt var.")

    def _query(self, filters: ListingFilters, cursor: Optional[Any]) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        for name, value in (
            ("main_category", filters.main_category),
            ("category", ",".join(filters.categories)),
            ("city", ",".join(filters.cities)),
            ("district", ",".join(filters.districts)),
            ("neighbourhood", ",".join(filters.neighbourhoods)),
        ):
            if value:
                params[name] = value
        if cursor is not None:
            params[self._config.get("cursor_param") or "cursor"] = cursor
        return params

    def fetch(self, filters: ListingFilters, cursor: Optional[Any]) -> Iterator[ProviderPage]:
        missing = self._missing_config()
        if missing:
            raise ProviderUnavailable(missing)

        client = self.client_factory()
        try:
            for _page in range(MAX_PAGES):
                document = client.get_json(self._config["base_url"], headers=self._headers(), params=self._query(filters, cursor))
                records = read_path(document, self._config.get("results_path") or "items")
                if not isinstance(records, list):
                    raise NetworkError("Yanıtta ilan listesi bulunamadı; sonuç yolunu kontrol edin.")
                cursor = read_path(document, self._config.get("next_cursor_path") or "next")
                yield ProviderPage(records=[r for r in records if isinstance(r, dict)], next_cursor=cursor)
                if cursor in (None, ""):
                    return
        finally:
            client.close()
