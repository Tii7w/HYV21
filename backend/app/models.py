"""
HKY Estates V2 - Veri modelleri
Telefon ve satıcı adı gibi kişisel veriler bilinçli olarak modelde yer almaz.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="not_configured")
    status_message: Mapped[str] = mapped_column(Text, default="")
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    secret_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ScrapingSettings(Base):
    """Tek satırlık ayar kaydı; içerik schemas.AppSettings ile doğrulanır."""

    __tablename__ = "scraping_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    proxy_password_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_key", "source_listing_id", name="uq_listing_source"),
        Index("ix_listing_location", "main_category", "category", "city", "district", "neighbourhood"),
        Index("ix_listing_state", "is_demo", "status", "listed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(40))
    source_listing_id: Mapped[str] = mapped_column(String(120))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    duplicate_of_id: Mapped[Optional[int]] = mapped_column(ForeignKey("listings.id"))
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    data_quality: Mapped[int] = mapped_column(Integer, default=0)

    main_category: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(40))
    property_type: Mapped[Optional[str]] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(400), default="")
    url: Mapped[Optional[str]] = mapped_column(String(600))
    photo_url: Mapped[Optional[str]] = mapped_column(String(600))

    country: Mapped[str] = mapped_column(String(60), default="Türkiye")
    city: Mapped[Optional[str]] = mapped_column(String(60))
    district: Mapped[Optional[str]] = mapped_column(String(80))
    neighbourhood: Mapped[Optional[str]] = mapped_column(String(120))

    price: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(6), default="TL")
    price_per_m2: Mapped[Optional[float]] = mapped_column(Float)
    price_drop_pct: Mapped[Optional[float]] = mapped_column(Float)

    m2_gross: Mapped[Optional[int]] = mapped_column(Integer)
    m2_net: Mapped[Optional[int]] = mapped_column(Integer)
    rooms: Mapped[Optional[str]] = mapped_column(String(12))
    living_rooms: Mapped[Optional[int]] = mapped_column(Integer)
    building_age: Mapped[Optional[int]] = mapped_column(Integer)
    floor: Mapped[Optional[str]] = mapped_column(String(30))
    total_floors: Mapped[Optional[int]] = mapped_column(Integer)
    heating: Mapped[Optional[str]] = mapped_column(String(60))
    bathrooms: Mapped[Optional[int]] = mapped_column(Integer)
    balcony: Mapped[Optional[bool]] = mapped_column(Boolean)
    elevator: Mapped[Optional[bool]] = mapped_column(Boolean)
    parking: Mapped[Optional[bool]] = mapped_column(Boolean)
    in_site: Mapped[Optional[bool]] = mapped_column(Boolean)
    deed_status: Mapped[Optional[str]] = mapped_column(String(60))
    credit_eligible: Mapped[Optional[bool]] = mapped_column(Boolean)
    furnished: Mapped[Optional[bool]] = mapped_column(Boolean)

    brand: Mapped[Optional[str]] = mapped_column(String(60))
    series: Mapped[Optional[str]] = mapped_column(String(80))
    model: Mapped[Optional[str]] = mapped_column(String(120))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    km: Mapped[Optional[int]] = mapped_column(Integer)
    fuel: Mapped[Optional[str]] = mapped_column(String(30))
    transmission: Mapped[Optional[str]] = mapped_column(String(30))
    engine_cc: Mapped[Optional[int]] = mapped_column(Integer)
    engine_hp: Mapped[Optional[int]] = mapped_column(Integer)
    body_type: Mapped[Optional[str]] = mapped_column(String(40))
    drive_type: Mapped[Optional[str]] = mapped_column(String(30))
    color: Mapped[Optional[str]] = mapped_column(String(30))
    damage_record: Mapped[Optional[bool]] = mapped_column(Boolean)
    paint_status: Mapped[Optional[str]] = mapped_column(String(40))
    changed_parts: Mapped[Optional[int]] = mapped_column(Integer)
    heavy_damage: Mapped[Optional[bool]] = mapped_column(Boolean)
    seller_type: Mapped[Optional[str]] = mapped_column(String(30))

    listed_at: Mapped[Optional[date]] = mapped_column(Date)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    description: Mapped[Optional["ListingDescription"]] = relationship(back_populates="listing", uselist=False)
    price_history: Mapped[List["ListingPriceHistory"]] = relationship(
        back_populates="listing", order_by="ListingPriceHistory.observed_at"
    )


class ListingDescription(Base):
    __tablename__ = "listing_descriptions"

    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True)
    text: Mapped[str] = mapped_column(Text, default="")
    text_hash: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    listing: Mapped[Listing] = relationship(back_populates="description")


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(36))
    source_key: Mapped[str] = mapped_column(String(40))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    price: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(6))
    status: Mapped[str] = mapped_column(String(20))
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class ListingPriceHistory(Base):
    __tablename__ = "listing_price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    source_key: Mapped[str] = mapped_column(String(40))
    price: Mapped[int] = mapped_column(BigInteger)
    previous_price: Mapped[Optional[int]] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(6))
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    listing: Mapped[Listing] = relationship(back_populates="price_history")


class SearchProfile(Base):
    __tablename__ = "search_profiles"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_profile_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    filters: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    rows: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    dropped_columns: Mapped[List[str]] = mapped_column(JSON, default=list)
    attested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentJob(Base):
    __tablename__ = "agent_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[Optional[int]] = mapped_column(ForeignKey("search_profiles.id", ondelete="SET NULL"))
    profile_name: Mapped[str] = mapped_column(String(120), default="Anlık filtre")
    filters: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    settings_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    source_keys: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(30), default="collect")
    collect_state: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    examined: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    opportunities: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0)
    last_action: Mapped[str] = mapped_column(String(300), default="")
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class AgentJobItem(Base):
    """Veritabanı tabanlı kuyruk; devam ettirmede işlenmiş kayıtları atlamayı sağlar."""

    __tablename__ = "agent_job_items"
    __table_args__ = (
        UniqueConstraint("job_id", "kind", "key", name="uq_job_item"),
        Index("ix_job_item_status", "job_id", "kind", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("agent_jobs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    key: Mapped[str] = mapped_column(String(180))
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    listing_id: Mapped[Optional[int]] = mapped_column(ForeignKey("listings.id", ondelete="SET NULL"))
    error: Mapped[Optional[str]] = mapped_column(Text)


class AgentJobLog(Base):
    __tablename__ = "agent_job_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text)


class DeadLetter(Base):
    __tablename__ = "dead_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_jobs.id", ondelete="SET NULL"), index=True)
    source_key: Mapped[str] = mapped_column(String(40))
    url: Mapped[str] = mapped_column(String(600), default="")
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MarketBenchmark(Base):
    __tablename__ = "market_benchmarks"
    __table_args__ = (UniqueConstraint("job_id", "segment_key", name="uq_benchmark_segment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True)
    segment_key: Mapped[str] = mapped_column(String(300), index=True)
    segment_label: Mapped[str] = mapped_column(String(300))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    market_days: Mapped[int] = mapped_column(Integer)
    coverage_days: Mapped[int] = mapped_column(Integer, default=0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    avg_price: Mapped[Optional[float]] = mapped_column(Float)
    median_price: Mapped[Optional[float]] = mapped_column(Float)
    min_price: Mapped[Optional[float]] = mapped_column(Float)
    max_price: Mapped[Optional[float]] = mapped_column(Float)
    avg_unit_price: Mapped[Optional[float]] = mapped_column(Float)
    median_unit_price: Mapped[Optional[float]] = mapped_column(Float)
    distribution: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    trend_pct: Mapped[Optional[float]] = mapped_column(Float)
    breakdowns: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"
    __table_args__ = (
        UniqueConstraint("job_id", "listing_id", name="uq_score_job_listing"),
        Index("ix_score_latest", "is_latest", "is_opportunity", "score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("agent_jobs.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    is_opportunity: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer)

    score: Mapped[float] = mapped_column(Float, default=0)
    classification: Mapped[str] = mapped_column(String(30), default="Normal ilan")
    price_advantage_score: Mapped[float] = mapped_column(Float, default=0)
    nlp_score: Mapped[float] = mapped_column(Float, default=0)
    freshness_score: Mapped[float] = mapped_column(Float, default=0)

    discount_pct: Mapped[Optional[float]] = mapped_column(Float)
    reference_kind: Mapped[Optional[str]] = mapped_column(String(10))
    reference_value: Mapped[Optional[float]] = mapped_column(Float)
    market_median_price: Mapped[Optional[float]] = mapped_column(Float)
    market_avg_price: Mapped[Optional[float]] = mapped_column(Float)
    estimated_gap: Mapped[Optional[float]] = mapped_column(Float)
    comparable_count: Mapped[int] = mapped_column(Integer, default=0)
    comparable_level: Mapped[Optional[str]] = mapped_column(String(160))
    comparable_ids: Mapped[List[int]] = mapped_column(JSON, default=list)
    segment_key: Mapped[Optional[str]] = mapped_column(String(300))
    gross_yield_pct: Mapped[Optional[float]] = mapped_column(Float)

    confidence: Mapped[float] = mapped_column(Float, default=0)
    confidence_label: Mapped[str] = mapped_column(String(10), default="Düşük")
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    risk_level: Mapped[str] = mapped_column(String(10), default="Düşük")
    reliability: Mapped[float] = mapped_column(Float, default=0)
    warnings: Mapped[List[str]] = mapped_column(JSON, default=list)
    nlp: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    signal_keys: Mapped[str] = mapped_column(String(200), default=",")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    listing: Mapped[Listing] = relationship()
    report: Mapped[Optional["OpportunityReport"]] = relationship(back_populates="score", uselist=False)


class OpportunityReport(Base):
    __tablename__ = "opportunity_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    score_id: Mapped[int] = mapped_column(ForeignKey("opportunity_scores.id", ondelete="CASCADE"), unique=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    generator: Mapped[str] = mapped_column(String(30), default="rule-v1")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    score: Mapped[OpportunityScore] = relationship(back_populates="report")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notification_user", "user_id", "read_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    listing_id: Mapped[Optional[int]] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    score_id: Mapped[Optional[int]] = mapped_column(ForeignKey("opportunity_scores.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    score: Mapped[Optional[float]] = mapped_column(Float)
    advantage_pct: Mapped[Optional[float]] = mapped_column(Float)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
