"""
HKY Estates V2 - Ortak ilan filtresi
Ana sayfa araması ve agent aday seçimi aynı sorguyu kullanır; tüm değerler parametre olarak bağlanır.
"""

from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import Select, and_, or_, select

from .models import Listing, OpportunityScore
from .schemas import CONFIDENCE_MINIMUMS, ListingFilters


def _in(stmt: Select, column, values) -> Select:
    return stmt.where(column.in_(values)) if values else stmt


def _between(stmt: Select, column, low, high) -> Select:
    if low is not None:
        stmt = stmt.where(column >= low)
    if high is not None:
        stmt = stmt.where(column <= high)
    return stmt


def _equals(stmt: Select, column, value) -> Select:
    return stmt.where(column == value) if value is not None else stmt


def _signal(key: str):
    return OpportunityScore.signal_keys.contains(f",{key},", autoescape=True)


def apply_listing_filters(stmt: Select, f: ListingFilters, today: Optional[date] = None) -> Select:
    """İlan sütunlarına uygulanan filtreler; skor gerektirmez."""
    today = today or date.today()
    stmt = stmt.where(Listing.is_demo.is_(f.data_mode == "demo"), Listing.duplicate_of_id.is_(None))
    stmt = stmt.where(Listing.status == "active", Listing.currency == f.currency, Listing.country == f.country)

    if f.main_category:
        stmt = stmt.where(Listing.main_category == f.main_category)
    stmt = _in(stmt, Listing.category, f.categories)
    stmt = _in(stmt, Listing.city, f.cities)
    stmt = _in(stmt, Listing.district, f.districts)
    stmt = _in(stmt, Listing.neighbourhood, f.neighbourhoods)

    stmt = _between(stmt, Listing.price, f.price_min, f.price_max)
    stmt = _between(stmt, Listing.price_per_m2, f.unit_price_min, f.unit_price_max)

    if f.opportunity_from or f.opportunity_to:
        stmt = _between(stmt, Listing.listed_at, f.opportunity_from, f.opportunity_to)
    elif f.opportunity_window_days:
        stmt = stmt.where(Listing.listed_at >= today - timedelta(days=f.opportunity_window_days))

    if f.main_category != "vasita":
        area = Listing.m2_net if f.m2_basis == "net" else Listing.m2_gross
        stmt = _between(stmt, area, f.m2_min, f.m2_max)
        stmt = _in(stmt, Listing.rooms, f.rooms)
        stmt = _in(stmt, Listing.living_rooms, f.living_rooms)
        stmt = _between(stmt, Listing.building_age, f.building_age_min, f.building_age_max)
        stmt = _in(stmt, Listing.floor, f.floors)
        stmt = _between(stmt, Listing.total_floors, f.total_floors_min, f.total_floors_max)
        stmt = _in(stmt, Listing.heating, f.heating)
        stmt = _in(stmt, Listing.bathrooms, f.bathrooms)
        stmt = _in(stmt, Listing.deed_status, f.deed_status)
        for column, value in (
            (Listing.balcony, f.balcony),
            (Listing.elevator, f.elevator),
            (Listing.parking, f.parking),
            (Listing.in_site, f.in_site),
            (Listing.credit_eligible, f.credit_eligible),
            (Listing.furnished, f.furnished),
        ):
            stmt = _equals(stmt, column, value)

    if f.main_category != "emlak":
        stmt = _in(stmt, Listing.brand, f.brands)
        stmt = _in(stmt, Listing.series, f.series)
        stmt = _between(stmt, Listing.year, f.year_min, f.year_max)
        stmt = _between(stmt, Listing.km, f.km_min, f.km_max)
        stmt = _in(stmt, Listing.fuel, f.fuels)
        stmt = _in(stmt, Listing.transmission, f.transmissions)
        stmt = _between(stmt, Listing.engine_cc, f.engine_cc_min, f.engine_cc_max)
        stmt = _between(stmt, Listing.engine_hp, f.engine_hp_min, f.engine_hp_max)
        stmt = _in(stmt, Listing.body_type, f.body_types)
        stmt = _in(stmt, Listing.drive_type, f.drive_types)
        stmt = _in(stmt, Listing.color, f.colors)
        stmt = _equals(stmt, Listing.damage_record, f.damage_record)
        stmt = _in(stmt, Listing.paint_status, f.paint_status)
        stmt = _between(stmt, Listing.changed_parts, None, f.changed_parts_max)
        stmt = _equals(stmt, Listing.heavy_damage, f.heavy_damage)

    # "Kimden" hem emlak hem vasıta ilanlarında bulunur.
    stmt = _in(stmt, Listing.seller_type, f.seller_types)
    return stmt


# (filtre alanı, skor sinyal anahtarı, kullanıcıya görünen ad) — arama ve agent aynı tabloyu kullanır.
SIGNAL_FLAGS = (
    ("urgent", "urgent", "Acil satılık"),
    ("need_sale", "need_sale", "İhtiyaçtan / nakit ihtiyacı"),
    ("below_market", "below_market", "Piyasa altı (satıcı beyanı)"),
    ("negotiable", "negotiable", "Pazarlığa açık"),
    ("bargain", "bargain", "Kelepir"),
    ("swap", "swap", "Takaslı"),
    ("high_investment", "high_investment", "Yüksek yatırım potansiyeli"),
    ("cheapest_in_region", "cheapest_region", "Bölgenin en ucuz %25'i"),
)


def unmet_opportunity_flags(
    f: ListingFilters,
    signal_keys: set,
    price: Optional[float],
    market_avg: Optional[float],
    market_median: Optional[float],
    price_drop_pct: Optional[float],
) -> List[str]:
    """Agent taramasında seçili fırsat kutularından karşılanmayanların adlarını döndürür.

    Arama ekranındaki apply_score_filters ile aynı kuralları uygular; böylece
    "Acil satılık" seçilip başlatılan tarama yalnızca acil ilanları fırsat sayar.
    """
    unmet = [label for attr, key, label in SIGNAL_FLAGS if getattr(f, attr) and key not in signal_keys]
    if f.price_dropped and not ((price_drop_pct or 0) > 0 or "price_drop" in signal_keys):
        unmet.append("Fiyatı düşen")
    if f.below_regional_avg and not (market_avg is not None and price is not None and market_avg > price):
        unmet.append("Bölge ortalamasının altında")
    if f.below_regional_median and not (market_median is not None and price is not None and market_median > price):
        unmet.append("Bölge medyanının altında")
    return unmet


def apply_score_filters(stmt: Select, f: ListingFilters) -> Select:
    """Analiz sonucu gerektiren filtreler; sorguda son skorla birleşim bulunmalıdır."""
    if f.below_regional_avg:
        stmt = stmt.where(OpportunityScore.market_avg_price > Listing.price)
    if f.below_regional_median:
        stmt = stmt.where(OpportunityScore.market_median_price > Listing.price)
    for attr, key, _label in SIGNAL_FLAGS:
        if getattr(f, attr):
            stmt = stmt.where(_signal(key))
    if f.price_dropped:
        stmt = stmt.where(or_(Listing.price_drop_pct > 0, _signal("price_drop")))
    if f.only_opportunities:
        stmt = stmt.where(OpportunityScore.is_opportunity.is_(True))
    if f.min_score is not None:
        stmt = stmt.where(OpportunityScore.score >= f.min_score)
    if f.min_advantage is not None:
        stmt = stmt.where(OpportunityScore.discount_pct >= f.min_advantage)
    if f.min_confidence:
        stmt = stmt.where(OpportunityScore.confidence >= CONFIDENCE_MINIMUMS[f.min_confidence])
    return stmt


def needs_score(f: ListingFilters) -> bool:
    return any(
        (
            f.below_regional_avg, f.below_regional_median, f.urgent, f.need_sale, f.below_market, f.price_dropped,
            f.negotiable, f.bargain, f.swap, f.high_investment, f.cheapest_in_region, f.only_opportunities,
            f.min_score is not None, f.min_advantage is not None, f.min_confidence is not None,
        )
    )


def search_statement(f: ListingFilters, today: Optional[date] = None) -> Select:
    """İlanı son skoruyla birlikte seçer; skor filtresi yoksa analiz edilmemiş ilanlar da gelir."""
    join_condition = and_(OpportunityScore.listing_id == Listing.id, OpportunityScore.is_latest.is_(True))
    stmt = select(Listing, OpportunityScore).join(OpportunityScore, join_condition, isouter=not needs_score(f))
    return apply_score_filters(apply_listing_filters(stmt, f, today), f)
