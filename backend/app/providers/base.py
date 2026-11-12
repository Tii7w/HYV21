"""
HKY Estates V2 - Veri sağlayıcı sözleşmesi
Yeni bir platform eklemek için ListingProvider alt sınıfı yazıp registry'ye kaydetmek yeterlidir.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from ..models import DataSource
from ..schemas import ListingFilters

STATE_OK = "ok"
STATE_NOT_CONFIGURED = "not_configured"
STATE_ERROR = "error"
STATE_ACCESS_DENIED = "access_denied"


class ProviderUnavailable(Exception):
    """Kaynak yapılandırılmamış veya erişim izni yok."""


@dataclass
class ProviderCheck:
    state: str
    message: str


@dataclass
class ProviderPage:
    records: List[Dict[str, Any]] = field(default_factory=list)
    next_cursor: Optional[Any] = None


class ListingProvider(ABC):
    is_demo: bool = False

    def __init__(self, source: DataSource) -> None:
        self.source = source

    @property
    def key(self) -> str:
        return self.source.key

    @abstractmethod
    def check(self) -> ProviderCheck:
        """Kaynağın kullanılabilirliğini bildirir."""

    @abstractmethod
    def fetch(self, filters: ListingFilters, cursor: Optional[Any]) -> Iterator[ProviderPage]:
        """İmleçten itibaren sayfa sayfa ham kayıt üretir."""
