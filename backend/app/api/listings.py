"""İlan arama, fırsatlar ve fırsat detayı."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from ..agent.scorer import DISCLAIMER
from ..db import get_db
from ..filters import search_statement
from ..models import AgentJob, DataSource, Listing, ListingPriceHistory, MarketBenchmark, OpportunityScore, User
from ..schemas import SearchRequest
from ..security import current_user
from ..serializers import listing_dict, score_dict

router = APIRouter(prefix="/api", tags=["listings"])

SORTS = {
    "score": lambda: (OpportunityScore.score.desc().nulls_last(), Listing.listed_at.desc()),
    "advantage": lambda: (OpportunityScore.discount_pct.desc().nulls_last(), Listing.id),
    "price_asc": lambda: (Listing.price.asc(), Listing.id),
    "price_desc": lambda: (Listing.price.desc(), Listing.id),
    "unit_asc": lambda: (Listing.price_per_m2.asc().nulls_last(), Listing.id),
    "newest": lambda: (Listing.listed_at.desc().nulls_last(), Listing.id),
}


@router.post("/listings/search")
def search(body: SearchRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    stmt = search_statement(body.filters)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.options(selectinload(OpportunityScore.report))
        .order_by(*SORTS[body.sort]())
        .offset((body.page - 1) * body.page_size)
        .limit(body.page_size)
    ).all()
    return {
        "total": total,
        "page": body.page,
        "page_size": body.page_size,
        "items": [{"listing": listing_dict(listing), "score": score_dict(score)} for listing, score in rows],
    }


@router.get("/opportunities")
def opportunities(
    data_mode: str = Query(default="real", pattern="^(real|demo)$"),
    limit: int = Query(default=6, ge=1, le=50),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Yalnızca fırsat koşullarını karşılayan ilanlar döner; eksik sayı doldurulmaz."""
    rows = db.execute(
        select(OpportunityScore, Listing)
        .join(Listing, Listing.id == OpportunityScore.listing_id)
        .where(
            OpportunityScore.is_latest.is_(True), OpportunityScore.is_opportunity.is_(True),
            Listing.is_demo.is_(data_mode == "demo"), Listing.status == "active",
        )
        .options(selectinload(OpportunityScore.report))
        .order_by(OpportunityScore.score.desc(), OpportunityScore.discount_pct.desc())
        .limit(limit)
    ).all()
    last_job = db.scalar(select(AgentJob).where(AgentJob.status == "completed").order_by(AgentJob.finished_at.desc()).limit(1))
    return {
        "items": [{"listing": listing_dict(listing), "score": score_dict(score)} for score, listing in rows],
        "last_completed_at": last_job.finished_at.isoformat() + "Z" if last_job else None,
        "disclaimer": DISCLAIMER,
    }


def _iso(value) -> Optional[str]:
    return value.isoformat() + "Z" if value else None


# Dinamik /opportunities/{score_id} rotasından ÖNCE tanımlanmalı.
@router.get("/opportunities/found")
def found_opportunities(
    data_mode: str = Query(default="real", pattern="^(real|demo)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Agent'ın şimdiye kadar fırsat olarak işaretlediği her ilan (kalıcı kayıt).

    Her ilan bir kez listelenir; kart, o ilanın en son fırsat analizini gösterir.
    Sonraki bir taramada fırsat olmaktan çıkan ilanlar kaybolmaz, `still_opportunity=false` ile işaretlenir.
    """
    found = (
        select(
            OpportunityScore.listing_id.label("listing_id"),
            func.max(OpportunityScore.id).label("score_id"),
            func.min(OpportunityScore.created_at).label("first_found_at"),
            func.max(OpportunityScore.created_at).label("last_found_at"),
            func.count(OpportunityScore.id).label("times_found"),
        )
        .join(Listing, Listing.id == OpportunityScore.listing_id)
        .where(OpportunityScore.is_opportunity.is_(True), Listing.is_demo.is_(data_mode == "demo"))
        .group_by(OpportunityScore.listing_id)
        .subquery()
    )
    total = db.scalar(select(func.count()).select_from(found))
    rows = db.execute(
        select(OpportunityScore, Listing, found.c.first_found_at, found.c.last_found_at, found.c.times_found)
        .join(found, found.c.score_id == OpportunityScore.id)
        .join(Listing, Listing.id == OpportunityScore.listing_id)
        .options(selectinload(OpportunityScore.report))
        .order_by(found.c.last_found_at.desc(), OpportunityScore.score.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    listing_ids = [listing.id for _score, listing, *_rest in rows]
    still = set()
    if listing_ids:
        still = set(db.scalars(
            select(OpportunityScore.listing_id).where(
                OpportunityScore.listing_id.in_(listing_ids),
                OpportunityScore.is_latest.is_(True),
                OpportunityScore.is_opportunity.is_(True),
            )
        ))
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "listing": listing_dict(listing),
                "score": score_dict(score),
                "first_found_at": _iso(first_found_at),
                "last_found_at": _iso(last_found_at),
                "times_found": times_found,
                "still_opportunity": listing.id in still and listing.status == "active",
            }
            for score, listing, first_found_at, last_found_at, times_found in rows
        ],
    }


@router.get("/opportunities/{score_id}")
def opportunity_detail(score_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    score = db.scalar(select(OpportunityScore).where(OpportunityScore.id == score_id).options(selectinload(OpportunityScore.report)))
    if score is None:
        raise HTTPException(404, "Analiz bulunamadı.")
    listing = db.get(Listing, score.listing_id)
    comparables = list(db.scalars(select(Listing).where(Listing.id.in_(score.comparable_ids or [])).order_by(Listing.price_per_m2, Listing.price)))
    benchmark = db.scalar(
        select(MarketBenchmark).where(and_(MarketBenchmark.job_id == score.job_id, MarketBenchmark.segment_key == score.segment_key))
    )
    history = db.scalars(select(ListingPriceHistory).where(ListingPriceHistory.listing_id == listing.id).order_by(ListingPriceHistory.observed_at))
    source = db.scalar(select(DataSource).where(DataSource.key == listing.source_key))
    report = score.report
    return {
        "listing": {**listing_dict(listing), "description": listing.description.text if listing.description else ""},
        "score": score_dict(score),
        "nlp": score.nlp,
        "report": {"summary": report.summary, "details": report.details, "generator": report.generator} if report else None,
        "comparables": [listing_dict(item) for item in comparables],
        "benchmark": None if benchmark is None else {
            column: getattr(benchmark, column)
            for column in (
                "segment_label", "market_days", "coverage_days", "sample_size", "avg_price", "median_price", "min_price",
                "max_price", "avg_unit_price", "median_unit_price", "distribution", "trend_pct", "breakdowns",
            )
        },
        "price_history": [
            {"price": item.price, "currency": item.currency, "observed_at": item.observed_at.isoformat() + "Z"} for item in history
        ],
        "source": {"key": listing.source_key, "name": source.name if source else listing.source_key, "last_seen_at": listing.last_seen_at.isoformat() + "Z"},
        "disclaimer": DISCLAIMER,
    }
