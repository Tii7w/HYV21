"""
HKY Estates V2 - Dosya içe aktarma
Kullanıcının yetkili olduğunu beyan ettiği Excel/CSV/JSON dosyalarını okur.
Telefon ve satıcı adı gibi sütunlar daha veritabanına yazılmadan atılır.
"""

import io
import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ImportBatch
from ..schemas import ListingFilters
from .base import STATE_NOT_CONFIGURED, STATE_OK, ListingProvider, ProviderCheck, ProviderPage

MAX_ROWS = 50_000
PAGE_SIZE = 200
PII_COLUMN_HINTS = ("telefon", "phone", "gsm", "cep", "satıcı adı", "satici adi", "e-posta", "email", "tc kimlik")


class ImportError_(ValueError):
    """Dosya okunamadı veya biçimi desteklenmiyor."""


def _is_pii(column: object) -> bool:
    lowered = str(column).replace("İ", "i").replace("I", "ı").lower()
    return any(hint in lowered for hint in PII_COLUMN_HINTS)


def parse_import_file(filename: str, content: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Dosyayı satırlara çevirir; (satırlar, atılan kişisel veri sütunları) döndürür."""
    suffix = Path(filename).suffix.lower()
    try:
        if suffix in (".xlsx", ".xls"):
            frame = pd.read_excel(io.BytesIO(content), sheet_name=0, dtype=str, keep_default_na=False)
        elif suffix == ".csv":
            frame = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, sep=None, engine="python")
        elif suffix == ".json":
            document = json.loads(content.decode("utf-8-sig"))
            items = document.get("items") if isinstance(document, dict) else document
            if not isinstance(items, list):
                raise ImportError_("JSON dosyası ilan listesi veya 'items' alanı içermelidir.")
            frame = pd.DataFrame([item for item in items if isinstance(item, dict)]).astype(str)
        else:
            raise ImportError_("Yalnızca .xlsx, .csv ve .json dosyaları desteklenir.")
    except ImportError_:
        raise
    except Exception as exc:
        raise ImportError_(f"Dosya okunamadı: {type(exc).__name__}") from exc

    if frame.empty:
        raise ImportError_("Dosyada satır bulunamadı.")
    if len(frame) > MAX_ROWS:
        raise ImportError_(f"Dosya en fazla {MAX_ROWS} satır içerebilir.")

    dropped = [str(column) for column in frame.columns if _is_pii(column)]
    frame = frame.drop(columns=dropped)
    return frame.to_dict("records"), dropped


class ManualImportProvider(ListingProvider):
    def __init__(self, source, session_factory: Callable[[], Session]) -> None:
        super().__init__(source)
        self.session_factory = session_factory

    def check(self) -> ProviderCheck:
        with self.session_factory() as db:
            batches = db.scalar(select(func.count(ImportBatch.id))) or 0
            rows = db.scalar(select(func.sum(ImportBatch.row_count))) or 0
        if not batches:
            return ProviderCheck(STATE_NOT_CONFIGURED, "Henüz içe aktarılmış dosya yok.")
        return ProviderCheck(STATE_OK, f"{batches} dosyada {rows} satır hazır.")

    def fetch(self, filters: ListingFilters, cursor: Optional[Any]) -> Iterator[ProviderPage]:
        # En yeni dosya önce okunur: aynı ilan birden çok dosyada varsa güncel fiyat kuyruğa girer.
        position = cursor or {"batch": None, "offset": 0}
        with self.session_factory() as db:
            stmt = select(ImportBatch.id).order_by(ImportBatch.id.desc())
            if position["batch"] is not None:
                stmt = stmt.where(ImportBatch.id <= position["batch"])
            batch_ids = list(db.scalars(stmt))

        offset = position["offset"]
        for index, batch_id in enumerate(batch_ids):
            with self.session_factory() as db:
                batch = db.get(ImportBatch, batch_id)
                rows, name = list(batch.rows), batch.filename
            while offset < len(rows):
                chunk = rows[offset : offset + PAGE_SIZE]
                records = [{**row, "_import_ref": f"{batch_id}-{offset + i}"} for i, row in enumerate(chunk)]
                offset += len(chunk)
                if offset < len(rows):
                    next_cursor: Optional[Dict[str, int]] = {"batch": batch_id, "offset": offset}
                elif index + 1 < len(batch_ids):
                    next_cursor = {"batch": batch_ids[index + 1], "offset": 0}
                else:
                    next_cursor = None
                yield ProviderPage(records=records, next_cursor=next_cursor)
            offset = 0
