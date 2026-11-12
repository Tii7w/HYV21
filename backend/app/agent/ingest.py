"""
HKY Estates V2 - İlan kayıt katmanı
Aynı kaynak kimliği tekrar kaydedilmez; fiyat değişirse geçmişi, her görülmede anlık görüntüsü tutulur.
Farklı kaynaktan gelen aynı ilan, ilk kaydın kopyası olarak işaretlenir ve analize iki kez girmez.
"""

import hashlib
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Listing, ListingDescription, ListingPriceHistory, ListingSnapshot, utcnow
from .nlp import TfIdfIndex, cosine

LISTING_FIELDS = {column.key for column in Listing.__table__.columns} - {"id", "first_seen_at", "updated_at", "duplicate_of_id"}
NEAR_DUPLICATE_SIMILARITY = 0.9
NEAR_DUPLICATE_PRICE_GAP = 0.03
NEAR_DUPLICATE_SIZE_GAP = 0.03
STALE_AFTER_DAYS = 60


def upsert_listing(db: Session, record: Dict[str, Any], job_id: str) -> Tuple[Listing, bool, bool]:
    """(ilan, yeni mi, fiyat değişti mi) döndürür."""
    description = record.pop("description", "")
    values = {key: value for key, value in record.items() if key in LISTING_FIELDS}
    now = utcnow()

    listing = db.scalar(
        select(Listing).where(Listing.source_key == values["source_key"], Listing.source_listing_id == values["source_listing_id"])
    )
    created = listing is None
    price_changed = False

    if created:
        listing = Listing(**values, first_seen_at=now, last_seen_at=now)
        db.add(listing)
        db.flush()
        db.add(ListingPriceHistory(listing_id=listing.id, source_key=listing.source_key, price=listing.price, currency=listing.currency, observed_at=now))
    else:
        previous_price, previous_currency = listing.price, listing.currency
        first_price = db.scalar(
            select(ListingPriceHistory.price).where(ListingPriceHistory.listing_id == listing.id).order_by(ListingPriceHistory.observed_at).limit(1)
        )
        for key, value in values.items():
            # Kaynakta boş gelen alan, daha önce bilinen değeri silmez.
            if value is not None or key in ("status", "url", "photo_url"):
                setattr(listing, key, value)
        listing.last_seen_at = now
        if listing.price != previous_price or listing.currency != previous_currency:
            price_changed = True
            db.add(
                ListingPriceHistory(
                    listing_id=listing.id, source_key=listing.source_key, price=listing.price,
                    previous_price=previous_price, currency=listing.currency, observed_at=now,
                )
            )
            if first_price and listing.currency == previous_currency and listing.price < first_price:
                listing.price_drop_pct = round((first_price - listing.price) / first_price * 100, 2)
            elif first_price and listing.price >= first_price:
                listing.price_drop_pct = None

    text_hash = hashlib.sha256(description.encode("utf-8")).hexdigest()
    stored = db.get(ListingDescription, listing.id)
    if stored is None:
        db.add(ListingDescription(listing_id=listing.id, text=description, text_hash=text_hash))
    elif stored.text_hash != text_hash and description:
        stored.text, stored.text_hash = description, text_hash

    db.add(
        ListingSnapshot(
            listing_id=listing.id, job_id=job_id, source_key=listing.source_key, captured_at=now,
            price=listing.price, currency=listing.currency, status=listing.status,
            data={"title": listing.title, "data_quality": listing.data_quality},
        )
    )

    if created and listing.dedupe_key:
        original = db.scalar(
            select(Listing.id)
            .where(Listing.dedupe_key == listing.dedupe_key, Listing.id != listing.id, Listing.is_demo.is_(listing.is_demo), Listing.duplicate_of_id.is_(None))
            .order_by(Listing.id)
            .limit(1)
        )
        listing.duplicate_of_id = original
    return listing, created, price_changed


def _same_size(a: Listing, b: Listing) -> bool:
    """Aynı binadaki farklı daireler benzer metinle yayınlanabilir; kopya için ölçü de aynı olmalı."""
    for left, right in ((a.m2_gross, b.m2_gross), (a.km, b.km)):
        if left is not None and right is not None and abs(left - right) / max(left, right, 1) > NEAR_DUPLICATE_SIZE_GAP:
            return False
    return True


def mark_near_duplicates(db: Session, listing_ids: List[int]) -> int:
    """Aynı yerde, aynı ölçü ve neredeyse aynı fiyat/metinle tekrar yayınlanan ilanları işaretler."""
    if not listing_ids:
        return 0
    listings = list(db.scalars(select(Listing).where(Listing.id.in_(listing_ids), Listing.duplicate_of_id.is_(None))))
    texts = {item.id: f"{item.title} {item.description.text if item.description else ''}" for item in listings}
    index = TfIdfIndex(texts.values())
    groups: Dict[Tuple, List[Listing]] = {}
    for item in listings:
        key = (item.is_demo, item.category, item.district, item.neighbourhood, item.rooms, item.brand, item.series, item.year)
        groups.setdefault(key, []).append(item)

    marked = 0
    for members in groups.values():
        members.sort(key=lambda item: item.id)
        vectors = {item.id: index.vector(texts[item.id]) for item in members}
        for position, item in enumerate(members):
            if item.duplicate_of_id or not vectors[item.id]:
                continue
            for earlier in members[:position]:
                if earlier.duplicate_of_id or earlier.source_listing_id == item.source_listing_id:
                    continue
                if abs(earlier.price - item.price) / max(earlier.price, 1) > NEAR_DUPLICATE_PRICE_GAP or not _same_size(earlier, item):
                    continue
                if cosine(vectors[item.id], vectors[earlier.id]) >= NEAR_DUPLICATE_SIMILARITY:
                    item.duplicate_of_id = earlier.id
                    marked += 1
                    break
    db.commit()
    return marked


def mark_stale(db: Session, today: date) -> int:
    """Uzun süredir hiçbir kaynakta görülmeyen ilanları pasife alır."""
    cutoff = datetime.combine(today - timedelta(days=STALE_AFTER_DAYS), datetime.min.time())
    result = db.execute(update(Listing).where(Listing.status == "active", Listing.last_seen_at < cutoff).values(status="stale"))
    db.commit()
    return result.rowcount or 0
