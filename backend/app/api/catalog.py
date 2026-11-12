"""Filtre seçenekleri ve hiyerarşik konum listesi."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Listing, User
from ..security import current_user

router = APIRouter(prefix="/api/catalog", tags=["catalog"])
LOCATIONS_FILE = Path(__file__).resolve().parents[1] / "data" / "tr_locations.json"
HOOD_SUFFIX = re.compile(r"\s+Mah$")

CATEGORIES = {
    "emlak": [
        {"value": "satilik-konut", "label": "Satılık Konut"}, {"value": "kiralik-konut", "label": "Kiralık Konut"},
        {"value": "satilik-isyeri", "label": "Satılık İş Yeri"}, {"value": "kiralik-isyeri", "label": "Kiralık İş Yeri"},
        {"value": "satilik-arsa", "label": "Satılık Arsa"}, {"value": "diger-emlak", "label": "Diğer Emlak"},
    ],
    "vasita": [
        {"value": "otomobil", "label": "Otomobil"}, {"value": "arazi-suv-pickup", "label": "Arazi, SUV ve Pickup"},
        {"value": "motosiklet", "label": "Motosiklet"}, {"value": "ticari-arac", "label": "Ticari Araç"},
        {"value": "diger-vasita", "label": "Diğer Vasıta"},
    ],
}
DEFAULT_OPTIONS = {
    "rooms": ["1+0", "1+1", "2+1", "3+1", "4+1", "5+1", "6+"],
    "heating": ["Kombi (Doğalgaz)", "Merkezi", "Merkezi (Pay Ölçer)", "Yerden Isıtma", "Klima", "Soba", "Yok"],
    "deed_status": ["Kat Mülkiyetli", "Kat İrtifakı", "Hisseli Tapu", "Müstakil Tapulu", "Arsa Tapulu"],
    "fuels": ["Benzin", "Dizel", "Lpg & Benzin", "Hibrit", "Elektrik"],
    "transmissions": ["Manuel", "Otomatik", "Yarı Otomatik"],
    "body_types": ["Sedan", "Hatchback/5", "Station Wagon", "Coupe", "Cabrio", "SUV", "MPV"],
    "drive_types": ["Önden Çekiş", "Arkadan İtiş", "4x4"],
    "paint_status": ["Orijinal", "Boyalı", "Lokal Boyalı"],
    "seller_types": ["Sahibinden", "Emlak Ofisinden", "İnşaat Firmasından", "Galeriden", "Yetkili Bayiden"],
}
DB_OPTION_COLUMNS = {
    "rooms": Listing.rooms, "heating": Listing.heating, "deed_status": Listing.deed_status, "brands": Listing.brand,
    "series": Listing.series, "fuels": Listing.fuel, "transmissions": Listing.transmission, "body_types": Listing.body_type,
    "drive_types": Listing.drive_type, "colors": Listing.color, "paint_status": Listing.paint_status,
    "seller_types": Listing.seller_type, "floors": Listing.floor,
}


@lru_cache(maxsize=1)
def _locations() -> Dict[str, Dict[str, List[str]]]:
    return json.loads(LOCATIONS_FILE.read_text(encoding="utf-8"))


def _tr_sort(values: List[str]) -> List[str]:
    order = "abcçdefgğhıijklmnoöprsştuüvyz"
    key = lambda text: [order.index(c) if c in order else 100 + ord(c) for c in text.replace("İ", "i").replace("I", "ı").lower()]
    return sorted(values, key=key)


@router.get("/options")
def options(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Varsayılan seçenekler veritabanındaki gerçek değerlerle birleştirilir."""
    result = {"categories": CATEGORIES}
    for name, column in DB_OPTION_COLUMNS.items():
        found = [value for value in db.scalars(select(column).where(column.is_not(None)).distinct()) if value]
        result[name] = _tr_sort(list(dict.fromkeys(DEFAULT_OPTIONS.get(name, []) + found)))
    result["countries"] = _tr_sort(list({"Türkiye", *db.scalars(select(Listing.country).distinct())}))
    result["has_demo"] = bool(db.scalar(select(func.count(Listing.id)).where(Listing.is_demo.is_(True))))
    return result


@router.get("/cities")
def cities(user: User = Depends(current_user)) -> List[str]:
    return list(_locations().keys())


@router.get("/districts")
def districts(city: List[str] = Query(default=[]), user: User = Depends(current_user)) -> Dict[str, List[str]]:
    tree = _locations()
    return {name: list(tree.get(name, {}).keys()) for name in city}


@router.get("/neighbourhoods")
def neighbourhoods(
    city: str, district: List[str] = Query(default=[]), user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Dict[str, List[str]]:
    """PTT listesi ile veritabanında geçen mahalleler birleştirilir; ilanlarda 'Mah' eki bulunmaz."""
    tree = _locations().get(city, {})
    result: Dict[str, List[str]] = {}
    for name in district:
        official = [HOOD_SUFFIX.sub("", hood) for hood in tree.get(name, [])]
        seen = db.scalars(
            select(Listing.neighbourhood).where(Listing.city == city, Listing.district == name, Listing.neighbourhood.is_not(None)).distinct()
        )
        result[name] = _tr_sort(list(dict.fromkeys(official + [hood for hood in seen if hood])))
    return result
