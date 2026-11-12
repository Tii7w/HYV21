"""
HKY Estates V2 - Piyasa analizi
Her ilan yalnızca benzer özellikteki emsalleriyle karşılaştırılır. Emsal havuzu fırsat tarih
aralığından bağımsızdır ve DEMO ilanlar gerçek ilanlarla asla aynı havuza girmez.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Listing

HISTOGRAM_BINS = 8
MIN_TREND_SAMPLES = 3
MIN_RENT_COMPARABLES = 3
OUTLIER_MIN_SAMPLES = 6
LEVEL_WEIGHTS = (1.0, 0.9, 0.7, 0.5)
DEPTH_LEVELS = {"hizli": 2, "standart": 3, "derin": 4}
M2_TOLERANCE, LAND_M2_TOLERANCE = 0.25, 0.5
KM_TOLERANCE, KM_TOLERANCE_WIDE = 0.3, 0.4


@dataclass(frozen=True)
class PoolItem:
    id: int
    is_demo: bool
    main_category: str
    category: str
    property_type: Optional[str]
    currency: str
    city: Optional[str]
    district: Optional[str]
    neighbourhood: Optional[str]
    rooms: Optional[str]
    m2: Optional[int]
    age: Optional[int]
    price: int
    unit: Optional[float]
    listed_at: date
    brand: Optional[str]
    series: Optional[str]
    model: Optional[str]
    year: Optional[int]
    km: Optional[int]
    fuel: Optional[str]
    transmission: Optional[str]
    damage_class: str


@dataclass
class MarketStats:
    count: int
    mean: float
    median: float
    minimum: float
    maximum: float
    spread: float


@dataclass
class ComparableResult:
    sufficient: bool
    level_index: Optional[int] = None
    level_label: Optional[str] = None
    kind: Optional[str] = None
    items: List[PoolItem] = field(default_factory=list)
    stats: Optional[MarketStats] = None
    best_count: int = 0
    outliers_removed: int = 0
    coverage_days: int = 0


def damage_class(listing: Listing) -> str:
    if listing.heavy_damage:
        return "agir"
    if listing.damage_record:
        return "hasarli"
    return "temiz" if listing.damage_record is False else "bilinmiyor"


def to_pool_item(listing: Listing) -> PoolItem:
    return PoolItem(
        id=listing.id, is_demo=listing.is_demo, main_category=listing.main_category, category=listing.category,
        property_type=listing.property_type, currency=listing.currency, city=listing.city, district=listing.district,
        neighbourhood=listing.neighbourhood, rooms=listing.rooms, m2=listing.m2_gross, age=listing.building_age,
        price=listing.price, unit=listing.price_per_m2, listed_at=listing.listed_at, brand=listing.brand,
        series=listing.series, model=listing.model, year=listing.year, km=listing.km, fuel=listing.fuel,
        transmission=listing.transmission, damage_class=damage_class(listing),
    )


def load_pool(db: Session, is_demo: bool, start: date, end: date) -> List[PoolItem]:
    """Piyasa penceresindeki ilanları yükler; kaldırılmış ilanlar geçmiş fiyat olarak geçerlidir."""
    stmt = select(Listing).where(
        Listing.is_demo.is_(is_demo), Listing.duplicate_of_id.is_(None),
        Listing.listed_at.is_not(None), Listing.listed_at >= start, Listing.listed_at <= end,
    )
    return [to_pool_item(listing) for listing in db.scalars(stmt)]


def market_window(today: date, days: int, start: Optional[date], end: Optional[date]) -> Tuple[date, date]:
    if start or end:
        return start or (today - timedelta(days=days)), end or today
    return today - timedelta(days=days), today


def age_band(age: Optional[int]) -> Optional[int]:
    if age is None:
        return None
    return 0 if age <= 5 else 1 if age <= 10 else 2 if age <= 20 else 3


def _close(a: Optional[float], b: Optional[float], tolerance: float) -> bool:
    return a is not None and b is not None and b > 0 and abs(a - b) / b <= tolerance


def _year_close(a: Optional[int], b: Optional[int], span: int) -> bool:
    return a is not None and b is not None and abs(a - b) <= span


def _quartile_trim(items: Sequence[PoolItem], value_of: Callable[[PoolItem], float]) -> Tuple[List[PoolItem], int]:
    """Tukey sınırlarıyla uç değerleri atar; az örnekte dokunmaz."""
    if len(items) < OUTLIER_MIN_SAMPLES:
        return list(items), 0
    values = sorted(value_of(item) for item in items)
    q1, _, q3 = statistics.quantiles(values, n=4)
    fence = 1.5 * (q3 - q1)
    kept = [item for item in items if q1 - fence <= value_of(item) <= q3 + fence]
    return kept, len(items) - len(kept)


def summarize(values: Sequence[float]) -> MarketStats:
    median = statistics.median(values)
    mean = statistics.fmean(values)
    spread = statistics.pstdev(values) / mean if len(values) > 1 and mean else 0.0
    return MarketStats(len(values), mean, median, min(values), max(values), spread)


def histogram(values: Sequence[float]) -> List[Dict[str, float]]:
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [{"start": low, "end": high, "count": len(values)}]
    width = (high - low) / HISTOGRAM_BINS
    counts = [0] * HISTOGRAM_BINS
    for value in values:
        counts[min(int((value - low) / width), HISTOGRAM_BINS - 1)] += 1
    return [{"start": low + width * i, "end": low + width * (i + 1), "count": c} for i, c in enumerate(counts)]


class MarketAnalyzer:
    def __init__(self, pool: List[PoolItem], today: date, start: date, end: date, min_comparables: int, depth: str) -> None:
        self.today, self.start, self.end = today, start, end
        self.min_comparables = max(3, min_comparables)
        self.max_levels = DEPTH_LEVELS.get(depth, 3)
        self._index: Dict[Tuple, List[PoolItem]] = defaultdict(list)
        self._rents: Dict[Tuple, List[int]] = defaultdict(list)
        for item in pool:
            self._index[self._bucket(item)].append(item)
            if item.category == "kiralik-konut" and item.neighbourhood and item.rooms:
                self._rents[(item.currency, item.city, item.district, item.neighbourhood, item.rooms)].append(item.price)

    @staticmethod
    def _bucket(item: PoolItem) -> Tuple:
        scope = item.brand if item.main_category == "vasita" else item.city
        return (item.currency, item.category, scope)

    def _emlak_levels(self, s: PoolItem) -> List[Tuple[str, Callable[[PoolItem], bool]]]:
        tolerance = LAND_M2_TOLERANCE if not s.rooms else M2_TOLERANCE
        same_type = lambda o: o.property_type == s.property_type and o.rooms == s.rooms
        similar_m2 = (lambda o: _close(o.m2, s.m2, tolerance)) if s.m2 else (lambda o: True)
        hood = lambda o: bool(s.neighbourhood) and o.neighbourhood == s.neighbourhood and o.district == s.district
        district = lambda o: bool(s.district) and o.district == s.district
        descriptor = f"aynı tip ve oda{', benzer m²' if s.m2 else ''}"
        return [
            (f"Aynı mahalle, {descriptor}, benzer bina yaşı", lambda o: hood(o) and same_type(o) and similar_m2(o) and age_band(o.age) == age_band(s.age)),
            (f"Aynı mahalle, {descriptor}", lambda o: hood(o) and same_type(o) and similar_m2(o)),
            (f"Aynı ilçe, {descriptor}", lambda o: district(o) and same_type(o) and similar_m2(o)),
            (f"Aynı il, {descriptor}", lambda o: same_type(o) and similar_m2(o)),
        ]

    def _vasita_levels(self, s: PoolItem) -> List[Tuple[str, Callable[[PoolItem], bool]]]:
        identity = lambda o: o.series == s.series and o.model == s.model
        close = lambda o: _year_close(o.year, s.year, 1) and _close(o.km, s.km, KM_TOLERANCE) and o.damage_class == s.damage_class
        drivetrain = lambda o: o.fuel == s.fuel and o.transmission == s.transmission
        return [
            ("Aynı il, aynı model, yıl ±1, benzer km, aynı yakıt/vites ve hasar", lambda o: o.city == s.city and identity(o) and close(o) and drivetrain(o)),
            ("Aynı model, yıl ±1, benzer km, aynı yakıt/vites ve hasar", lambda o: identity(o) and close(o) and drivetrain(o)),
            ("Aynı model, yıl ±1, benzer km ve hasar", lambda o: identity(o) and close(o)),
            ("Aynı seri, yıl ±2, yakın km ve hasar", lambda o: o.series == s.series and _year_close(o.year, s.year, 2) and _close(o.km, s.km, KM_TOLERANCE_WIDE) and o.damage_class == s.damage_class),
        ]

    def find_comparables(self, subject: PoolItem) -> ComparableResult:
        """En dar emsal grubundan başlar; yeterli örneklem yoksa bir üst seviyeye geçer."""
        if subject.main_category == "vasita" and not (subject.brand and subject.series and subject.year and subject.km):
            return ComparableResult(sufficient=False)
        if subject.main_category == "emlak" and not (subject.m2 or subject.rooms):
            return ComparableResult(sufficient=False)

        candidates = [o for o in self._index.get(self._bucket(subject), []) if o.id != subject.id]
        levels = self._vasita_levels(subject) if subject.main_category == "vasita" else self._emlak_levels(subject)
        uses_unit = subject.main_category == "emlak" and subject.unit is not None
        value_of: Callable[[PoolItem], float] = (lambda o: o.unit or 0.0) if uses_unit else (lambda o: float(o.price))
        if uses_unit:
            candidates = [o for o in candidates if o.unit]

        best = 0
        for index, (label, predicate) in enumerate(levels[: self.max_levels]):
            matched = [o for o in candidates if predicate(o)]
            best = max(best, len(matched))
            kept, removed = _quartile_trim(matched, value_of)
            if len(kept) >= self.min_comparables:
                earliest = min(o.listed_at for o in kept)
                return ComparableResult(
                    sufficient=True, level_index=index, level_label=label, kind="unit" if uses_unit else "price",
                    items=kept, stats=summarize([value_of(o) for o in kept]), best_count=len(kept), outliers_removed=removed,
                    coverage_days=(self.today - earliest).days,
                )
        return ComparableResult(sufficient=False, best_count=best)

    def confidence(self, result: ComparableResult, market_days: int) -> float:
        """Örneklem, eşleşme yakınlığı, fiyat dağılımı ve veri kapsamından 0-100 güven üretir."""
        if not result.sufficient or result.stats is None:
            return min(20.0, result.best_count * 4.0)
        sample = min(1.0, result.stats.count / (self.min_comparables * 3))
        level = LEVEL_WEIGHTS[result.level_index or 0]
        dispersion = max(0.0, 1.0 - result.stats.spread / 0.5)
        coverage = min(1.0, result.coverage_days / max(1, market_days))
        return round((sample * 0.40 + level * 0.25 + dispersion * 0.20 + coverage * 0.15) * 100, 1)

    def gross_yield(self, subject: PoolItem) -> Optional[float]:
        if subject.category != "satilik-konut" or not (subject.neighbourhood and subject.rooms):
            return None
        rents = self._rents.get((subject.currency, subject.city, subject.district, subject.neighbourhood, subject.rooms), [])
        if len(rents) < MIN_RENT_COMPARABLES:
            return None
        return round(statistics.median(rents) * 12 / subject.price * 100, 2)

    def segment_of(self, subject: PoolItem) -> Tuple[str, str, Callable[[PoolItem], bool]]:
        """Bölgesel piyasa özeti için (anahtar, etiket, koşul) döndürür."""
        if subject.main_category == "vasita":
            key = f"{subject.is_demo}|{subject.currency}|{subject.category}|{subject.brand}|{subject.series}"
            return key, f"{subject.brand} {subject.series}", lambda o: o.brand == subject.brand and o.series == subject.series
        place = " / ".join(filter(None, (subject.city, subject.district, subject.neighbourhood)))
        key = f"{subject.is_demo}|{subject.currency}|{subject.category}|{place}|{subject.property_type}"
        return key, f"{place} · {subject.property_type or subject.category}", (
            lambda o: o.property_type == subject.property_type and o.district == subject.district and o.neighbourhood == subject.neighbourhood
        )

    def benchmark(self, subject: PoolItem, market_days: int) -> Dict[str, Any]:
        key, label, predicate = self.segment_of(subject)
        items = [o for o in self._index.get(self._bucket(subject), []) if predicate(o)]
        prices = [float(o.price) for o in items]
        units = [o.unit for o in items if o.unit]
        data: Dict[str, Any] = {
            "segment_key": key, "segment_label": label, "is_demo": subject.is_demo, "market_days": market_days,
            "sample_size": len(items), "coverage_days": (self.today - min(o.listed_at for o in items)).days if items else 0,
            "distribution": histogram(units or prices), "trend_pct": self._trend(items), "breakdowns": self._breakdowns(items),
        }
        if prices:
            stats = summarize(prices)
            data.update(avg_price=stats.mean, median_price=stats.median, min_price=stats.minimum, max_price=stats.maximum)
        if units:
            stats = summarize(units)
            data.update(avg_unit_price=stats.mean, median_unit_price=stats.median)
        return data

    def _trend(self, items: Sequence[PoolItem]) -> Optional[float]:
        midpoint = self.start + (self.end - self.start) / 2
        value_of: Callable[[PoolItem], float] = lambda o: o.unit or float(o.price)
        older = [value_of(o) for o in items if o.listed_at < midpoint]
        newer = [value_of(o) for o in items if o.listed_at >= midpoint]
        if len(older) < MIN_TREND_SAMPLES or len(newer) < MIN_TREND_SAMPLES:
            return None
        base = statistics.median(older)
        return round((statistics.median(newer) - base) / base * 100, 2) if base else None

    @staticmethod
    def _breakdowns(items: Sequence[PoolItem]) -> Dict[str, List[Dict[str, Any]]]:
        def group(label_of: Callable[[PoolItem], Optional[str]]) -> List[Dict[str, Any]]:
            buckets: Dict[str, List[float]] = defaultdict(list)
            for item in items:
                label = label_of(item)
                if label:
                    buckets[label].append(item.unit or float(item.price))
            return [{"label": name, "count": len(v), "median": statistics.median(v)} for name, v in sorted(buckets.items())]

        if items and items[0].main_category == "vasita":
            return {
                "Model yılı": group(lambda o: str(o.year) if o.year else None),
                "Kilometre": group(lambda o: f"{o.km // 25_000 * 25}-{o.km // 25_000 * 25 + 25} bin km" if o.km is not None else None),
                "Yakıt ve vites": group(lambda o: f"{o.fuel} / {o.transmission}" if o.fuel and o.transmission else None),
                "Hasar durumu": group(lambda o: {"temiz": "Hasarsız", "hasarli": "Hasar kayıtlı", "agir": "Ağır hasarlı"}.get(o.damage_class)),
            }
        return {"Oda sayısı": group(lambda o: o.rooms)}
