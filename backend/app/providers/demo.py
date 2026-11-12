"""
HKY Estates V2 - DEMO veri kaynağı
Tamamen sentetik ilan üretir. Kayıtlar is_demo olarak işaretlenir, arayüzde DEMO etiketi taşır,
gerçek ilanlarla aynı emsal havuzuna asla girmez ve orijinal ilan bağlantısı içermez.
"""

import random
from datetime import date, timedelta
from typing import Any, Dict, Iterator, List, Optional

from ..schemas import ListingFilters
from .base import STATE_OK, ListingProvider, ProviderCheck, ProviderPage

PAGE_SIZE = 50
HISTORY_DAYS = 45

DEMO_AREAS = {
    "Bursa": {"Nilüfer": {"Ataevler": 58000, "Görükle": 41000, "Beşevler": 49000}},
    "İstanbul": {"Kadıköy": {"Caferağa": 142000, "Fenerbahçe": 168000}},
    "Ankara": {"Çankaya": {"Çukurambar": 76000, "Bahçelievler": 69000}},
}
ROOM_SIZES = [("1+1", 62), ("2+1", 95), ("3+1", 130), ("4+1", 175)]
VEHICLES = [
    ("Renault", "Clio", "1.5 dCi Touch", "Dizel", "Manuel", 1_050_000),
    ("Fiat", "Egea", "1.3 Multijet Urban", "Dizel", "Manuel", 890_000),
    ("Toyota", "Corolla", "1.8 Hybrid Dream", "Hibrit", "Otomatik", 1_620_000),
]
URGENT_TEXTS = [
    "Acil satılıktır, nakit ihtiyacımdan dolayı fiyatı 400 bin TL düşürdüm. Pazarlık payı vardır.",
    "İhtiyaçtan satılık, yurt dışına taşınacağım için elden çıkarmak istiyorum.",
    "Sahibinden acil. Borçtan dolayı satılıktır, piyasa altı fiyata verilecektir.",
]
NEUTRAL_TEXTS = [
    "Temiz kullanılmış, bakımları düzenli yapılmıştır.",
    "Acil satılık değildir, fiyatlar piyasadaki fiyatlarla aynıdır.",
    "Acil çıkış merdiveni mevcuttur, ulaşıma yakın konumdadır. Pazarlık yoktur.",
    "Yatırımlık, kira getirisi yüksek bir konumdadır.",
]
RISK_TEXTS = ["Hisseli tapu olup ipotekli olduğu bilinmelidir.", "Görmeden kapora gönderebilirsiniz."]


def _format_date(day: date) -> str:
    return day.isoformat()


def _housing(today: date, rng: random.Random) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for city, districts in DEMO_AREAS.items():
        for district, hoods in districts.items():
            for hood, unit in hoods.items():
                for room, size in ROOM_SIZES:
                    for serial in range(9):
                        age = rng.randint(0, HISTORY_DAYS)
                        m2 = int(size * rng.uniform(0.92, 1.08))
                        noise, text = rng.uniform(0.94, 1.08), rng.choice(NEUTRAL_TEXTS)
                        if serial == 0:
                            age, noise, text = rng.randint(0, 3), rng.uniform(0.76, 0.84), rng.choice(URGENT_TEXTS)
                        elif serial == 1:
                            age, noise, text = rng.randint(0, 6), rng.uniform(0.40, 0.50), rng.choice(RISK_TEXTS)
                        rows.append(
                            {
                                "İlan No": f"DEMO-E-{city[:2]}{hood[:3]}{room}{serial}",
                                "Kategori": "Satılık Daire",
                                "İl": city,
                                "İlçe": district,
                                "Mahalle": hood,
                                "Fiyat": f"{int(unit * m2 * noise / 1000) * 1000} TL",
                                "m² (Brüt)": str(m2),
                                "m² (Net)": str(int(m2 * 0.86)),
                                "Oda Sayısı": room,
                                "Bina Yaşı": str(rng.choice([2, 4, 8, 12, 18])),
                                "Bulunduğu Kat": str(rng.randint(1, 7)),
                                "Kat Sayısı": "8",
                                "Isıtma": rng.choice(["Kombi (Doğalgaz)", "Merkezi"]),
                                "Banyo Sayısı": "1",
                                "Balkon": "Var",
                                "Asansör": rng.choice(["Var", "Yok"]),
                                "Otopark": rng.choice(["Açık Otopark", "Yok"]),
                                "İlan Başlığı": f"[DEMO] {hood} {room} Satılık Daire",
                                "Açıklama": text,
                                "İlan Tarihi": _format_date(today - timedelta(days=age)),
                                "Kimden": "Sahibinden",
                            }
                        )
    return rows


def _vehicles(today: date, rng: random.Random) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for brand, series, model, fuel, gear, base in VEHICLES:
        for serial in range(16):
            age = rng.randint(0, HISTORY_DAYS)
            year = 2021 + serial % 2
            km = rng.randint(50_000, 70_000)
            noise, text = rng.uniform(0.95, 1.07), rng.choice(NEUTRAL_TEXTS)
            if serial == 0:
                age, noise, text = 1, 0.80, "Acil satılık, nakit ihtiyacım var. Takas yapılmaz, fiyatı 100 bin TL indirdim."
            rows.append(
                {
                    "İlan No": f"DEMO-V-{brand[:3]}{series[:3]}{serial}",
                    "Kategori": "Otomobil",
                    "İl": "Bursa",
                    "İlçe": "Nilüfer",
                    "Fiyat": f"{int(base * noise / 1000) * 1000} TL",
                    "Marka": brand,
                    "Seri": series,
                    "Model": model,
                    "Yıl": str(year),
                    "KM": str(km),
                    "Yakıt": fuel,
                    "Vites": gear,
                    "Kasa Tipi": "Sedan",
                    "Renk": rng.choice(["Beyaz", "Gri", "Siyah"]),
                    "Hasar Durumu": "Hasarsız",
                    "Boya": "Orijinal",
                    "Değişen": "0",
                    "İlan Başlığı": f"[DEMO] {brand} {series} {year}",
                    "Açıklama": text,
                    "İlan Tarihi": _format_date(today - timedelta(days=age)),
                    "Kimden": rng.choice(["Sahibinden", "Galeriden"]),
                }
            )
    return rows


class DemoProvider(ListingProvider):
    is_demo = True

    def check(self) -> ProviderCheck:
        return ProviderCheck(STATE_OK, "Sentetik test verisi. Sonuçlar DEMO etiketiyle gösterilir.")

    def fetch(self, filters: ListingFilters, cursor: Optional[Any]) -> Iterator[ProviderPage]:
        today = date.today()
        # Tohum sabit olduğundan aynı gün tekrar çalıştırmak aynı ilanları üretir.
        rng = random.Random(today.isoformat())
        rows = _housing(today, rng) + _vehicles(today, rng)
        offset = int(cursor or 0)
        while offset < len(rows):
            chunk = rows[offset : offset + PAGE_SIZE]
            offset += len(chunk)
            yield ProviderPage(records=chunk, next_cursor=offset if offset < len(rows) else None)
