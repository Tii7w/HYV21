"""
HKY Estates V2 - Olay tabanlı bildirim
Skor eşiği aşıldığında bildirim merkezine kaydeder ve açık oturumlara anlık iletir.
Aynı ilan için tekrar bildirim engeli kullanıcı ayarına bağlıdır.
"""

from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..events import bus
from ..models import Listing, Notification, OpportunityScore, utcnow
from ..schemas import NotificationSettings

CATEGORY_LABELS = {
    "satilik-konut": "Satılık", "kiralik-konut": "Kiralık", "satilik-isyeri": "Satılık İş Yeri",
    "kiralik-isyeri": "Kiralık İş Yeri", "satilik-arsa": "Satılık Arsa",
}


def listing_headline(listing: Listing) -> str:
    if listing.main_category == "vasita":
        return " ".join(filter(None, (listing.brand, listing.series, str(listing.year or ""))))
    prefix = CATEGORY_LABELS.get(listing.category, "")
    return " ".join(filter(None, (prefix, listing.rooms, listing.property_type)))


def notification_payload(note: Notification) -> dict:
    return {
        "id": note.id, "listing_id": note.listing_id, "score_id": note.score_id, "title": note.title, "body": note.body,
        "score": note.score, "advantage_pct": note.advantage_pct, "is_demo": note.is_demo,
        "read": note.read_at is not None, "created_at": note.created_at.isoformat() + "Z",
    }


def maybe_notify(
    db: Session, user_id: int, listing: Listing, score: OpportunityScore, settings: NotificationSettings
) -> Optional[Notification]:
    if not score.is_opportunity or score.score <= settings.min_score:
        return None
    if settings.dedupe:
        since = utcnow() - timedelta(hours=settings.dedupe_hours)
        already = db.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id, Notification.listing_id == listing.id, Notification.created_at >= since
            )
        )
        if already:
            return None

    place = " / ".join(filter(None, (listing.city, listing.district)))
    demo = "[DEMO] " if listing.is_demo else ""
    advantage = score.discount_pct or 0
    body = (
        f"{place}\n{listing_headline(listing)}\n\nFırsat Skoru: {score.score:.0f}/100\n"
        f"Piyasa Avantajı: %{advantage:.1f}".replace(".", ",") + "\n\nAI Agent yeni bir piyasa altı ilan tespit etti."
    )
    note = Notification(
        user_id=user_id, listing_id=listing.id, score_id=score.id, title=f"🚨 {demo}YENİ FIRSAT BULUNDU!",
        body=body, score=score.score, advantage_pct=score.discount_pct, is_demo=listing.is_demo,
    )
    db.add(note)
    db.commit()
    bus.publish(
        "notification",
        {**notification_payload(note), "popup": settings.popup, "browser": settings.browser},
        user_id=user_id,
    )
    return note
