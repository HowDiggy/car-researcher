import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    Index,
    JSON,
    UniqueConstraint,
    ARRAY,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False


class Base(DeclarativeBase):
    pass


class SearchConfig(Base):
    __tablename__ = "search_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False, default="94103")
    radius_miles: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    min_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    powertrain: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    makes_models: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class VehicleModel(Base):
    __tablename__ = "vehicle_models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    make: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    trim: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    powertrain_type: Mapped[str] = mapped_column(String(20), default="BEV")
    base_msrp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    specs: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    recalls: Mapped[List["Recall"]] = relationship("Recall", back_populates="vehicle_model", cascade="all, delete-orphan")
    complaints: Mapped[List["Complaint"]] = relationship("Complaint", back_populates="vehicle_model", cascade="all, delete-orphan")
    listings: Mapped[List["Listing"]] = relationship("Listing", back_populates="vehicle_model")

    __table_args__ = (
        UniqueConstraint("make", "model", "year", "trim", name="uq_vehicle_model_trim"),
        Index("idx_vehicle_make_model_year", "make", "model", "year"),
    )


class Recall(Base):
    __tablename__ = "recalls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicle_models.id", ondelete="CASCADE"))
    nhtsa_campaign: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    component: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    consequence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remedy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)

    vehicle_model: Mapped["VehicleModel"] = relationship("VehicleModel", back_populates="recalls")


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicle_models.id", ondelete="CASCADE"))
    nhtsa_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    component: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    crash: Mapped[bool] = mapped_column(Boolean, default=False)
    fire: Mapped[bool] = mapped_column(Boolean, default=False)
    number_of_injuries: Mapped[int] = mapped_column(Integer, default=0)
    number_of_deaths: Mapped[int] = mapped_column(Integer, default=0)
    date_filed: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    vehicle_model: Mapped["VehicleModel"] = relationship("VehicleModel", back_populates="complaints")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vin: Mapped[Optional[str]] = mapped_column(String(17), nullable=True, index=True)
    vehicle_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicle_models.id"), nullable=True)
    platform: Mapped[str] = mapped_column(String(30), nullable=False)  # 'cargurus', 'autotrader', etc.
    platform_id: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    mileage: Mapped[int] = mapped_column(Integer, nullable=False)
    exterior_color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    interior_color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    trim_detail: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    seller_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    seller_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    seller_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_city: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    location_state: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    distance_miles: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    title_status: Mapped[str] = mapped_column(String(30), default="clean")
    accident_count: Mapped[int] = mapped_column(Integer, default=0)
    owner_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    photos: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    raw_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    vehicle_model: Mapped[Optional["VehicleModel"]] = relationship("VehicleModel", back_populates="listings")
    deal_scores: Mapped[List["DealScore"]] = relationship("DealScore", back_populates="listing", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("platform", "platform_id", name="uq_platform_listing_id"),
        Index("idx_active_listings_by_price", "is_active", "price"),
    )


class DealScore(Base):
    __tablename__ = "deal_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"))
    market_value: Mapped[int] = mapped_column(Integer, nullable=False)
    price_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    deal_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(30), nullable=False)
    score_breakdown: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    listing: Mapped["Listing"] = relationship("Listing", back_populates="deal_scores")


class PriceSnapshotModel(Base):
    """Mapped to TimescaleDB hypertable price_snapshots."""
    __tablename__ = "price_snapshots"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, default=datetime.utcnow)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    days_on_market: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_change: Mapped[int] = mapped_column(Integer, default=0)
