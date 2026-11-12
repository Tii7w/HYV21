"""
HKY Estates V2 - API çıktı biçimleri
"""

from typing import Any, Dict, Optional

from .models import Listing, OpportunityScore

LISTING_FIELDS = (
    "id", "source_key", "source_listing_id", "is_demo", "status", "main_category", "category", "property_type", "title",
    "url", "photo_url", "country", "city", "district", "neighbourhood", "price", "currency", "price_per_m2",
    "price_drop_pct", "m2_gross", "m2_net", "rooms", "living_rooms", "building_age", "floor", "total_floors", "heating",
    "bathrooms", "balcony", "elevator", "parking", "in_site", "deed_status", "credit_eligible", "furnished", "brand",
    "series", "model", "year", "km", "fuel", "transmission", "engine_cc", "engine_hp", "body_type", "drive_type",
    "color", "damage_record", "paint_status", "changed_parts", "heavy_damage", "seller_type", "data_quality",
)
SCORE_FIELDS = (
    "id", "job_id", "is_opportunity", "is_suspicious", "rank", "score", "classification", "price_advantage_score",
    "nlp_score", "freshness_score", "discount_pct", "reference_kind", "reference_value", "market_median_price",
    "market_avg_price", "estimated_gap", "comparable_count", "comparable_level", "gross_yield_pct", "confidence",
    "confidence_label", "risk_score", "risk_level", "reliability", "warnings",
)


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def listing_dict(listing: Listing) -> Dict[str, Any]:
    data = {field: getattr(listing, field) for field in LISTING_FIELDS}
    data.update(
        listed_at=_iso(listing.listed_at),
        first_seen_at=_iso(listing.first_seen_at) and _iso(listing.first_seen_at) + "Z",
        last_seen_at=_iso(listing.last_seen_at) and _iso(listing.last_seen_at) + "Z",
    )
    return data


def score_dict(score: Optional[OpportunityScore], with_summary: bool = True) -> Optional[Dict[str, Any]]:
    if score is None:
        return None
    data = {field: getattr(score, field) for field in SCORE_FIELDS}
    data["signals"] = [s for s in score.nlp.get("signals", []) if s.get("counted")]
    data["ineligible_reason"] = score.nlp.get("ineligible_reason")
    data["analyzed_at"] = score.created_at.isoformat() + "Z"
    if with_summary:
        data["summary"] = score.report.summary if score.report else ""
    return data
