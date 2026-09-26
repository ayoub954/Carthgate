"""ORM tables. Every analytic row keeps provenance (source_key / source_url / retrieved_at / period)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now() -> datetime:
    return datetime.utcnow()


class DataMode:
    """Legacy column kept for schema compatibility: every row is real data."""
    data_mode: Mapped[str | None] = mapped_column(String(8), default="REAL", index=True)


class Provenance:
    source_key: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(Text)
    access_type: Mapped[str] = mapped_column(String(64))  # PUBLIC_OPEN_DATA / OFFICIAL_ACCESS / AUTHORIZED_API ...
    status: Mapped[str] = mapped_column(String(32))  # CONNECTED / AVAILABLE / ERROR / ACCESS REQUIRED / NOT AVAILABLE
    message: Mapped[str | None] = mapped_column(Text)
    period: Mapped[str | None] = mapped_column(String(64))
    records: Mapped[int] = mapped_column(Integer, default=0)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime)
    license: Mapped[str | None] = mapped_column(String(255))


class RawRecord(Base, Provenance):
    """One cached raw download (local data cache)."""

    __tablename__ = "raw_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_path: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(128))
    period: Mapped[str | None] = mapped_column(String(64))
    last_updated: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)


class Country(Base, Provenance):
    __tablename__ = "countries"
    iso3: Mapped[str] = mapped_column(String(3), primary_key=True)
    m49: Mapped[str | None] = mapped_column(String(3))
    iso2: Mapped[str | None] = mapped_column(String(2))
    name_en: Mapped[str] = mapped_column(String(255))
    name_fr: Mapped[str | None] = mapped_column(String(255))
    continent: Mapped[str | None] = mapped_column(String(64))
    region: Mapped[str | None] = mapped_column(String(128))
    capital: Mapped[str | None] = mapped_column(String(128))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)


class HSCode(Base, Provenance):
    __tablename__ = "hs_codes"
    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    parent: Mapped[str | None] = mapped_column(String(12))
    level: Mapped[int] = mapped_column(Integer)  # 2, 4, 6


class Product(Base, Provenance):
    """A monitored product = an HS heading (official classification unit)."""

    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # HS code
    hs_code: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(64))
    chapter: Mapped[str | None] = mapped_column(String(2))
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)


class Brand(Base, Provenance):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    brand_origin_country: Mapped[str | None] = mapped_column(String(128))  # only if a source states it
    observations: Mapped[int] = mapped_column(Integer, default=0)


class Seller(Base, Provenance, DataMode):
    """Public commercial location / online seller as published by a legal source."""

    __tablename__ = "sellers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)  # e.g. osm:node/123
    name: Mapped[str | None] = mapped_column(String(255))
    shop_type: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(64))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    governorate: Mapped[str | None] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(128))
    website: Mapped[str | None] = mapped_column(Text)
    facebook: Mapped[str | None] = mapped_column(Text)
    instagram: Mapped[str | None] = mapped_column(Text)
    tiktok: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(255))
    geo_cluster: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[dict | None] = mapped_column(JSON)
    platform: Mapped[str | None] = mapped_column(String(64))


class Business(Base, Provenance, DataMode):
    """Official business registry entry (only filled with RNE access)."""

    __tablename__ = "businesses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registry_id: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    declared_activity: Mapped[str | None] = mapped_column(Text)
    governorate: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(64))
    # link to customs declarations ONLY when an official source provides it (never inferred)
    importer_hash: Mapped[str | None] = mapped_column(String(64))


class CommerceObservation(Base, Provenance, DataMode):
    __tablename__ = "commerce_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True)
    platform: Mapped[str] = mapped_column(String(64))
    page_name: Mapped[str | None] = mapped_column(String(255))
    page_url: Mapped[str | None] = mapped_column(Text)
    post_url: Mapped[str | None] = mapped_column(Text)
    product: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(128))
    raw_categories: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    public_business_location: Mapped[str | None] = mapped_column(String(255))
    manufacturing_place: Mapped[str | None] = mapped_column(Text)  # as declared by the source
    origin: Mapped[str | None] = mapped_column(Text)  # origin of ingredients/product as declared
    product_id: Mapped[str | None] = mapped_column(String(12), index=True)  # matched HS heading
    match_score: Mapped[float | None] = mapped_column(Float)
    image_hash: Mapped[str | None] = mapped_column(String(32))
    group_key: Mapped[str | None] = mapped_column(String(255), index=True)


class CustomsRecord(Base, Provenance, DataMode):
    """Official AGGREGATED trade statistics (INS, UN Comtrade). Not declarations."""

    __tablename__ = "customs_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(64), index=True)  # ins_chapter_month / ins_country_month / comtrade_hs4_partner ...
    flow: Mapped[str] = mapped_column(String(1))  # M / X
    period: Mapped[str] = mapped_column(String(10), index=True)  # YYYY or YYYY-MM
    period_type: Mapped[str] = mapped_column(String(1))  # A / M
    hs_code: Mapped[str | None] = mapped_column(String(12), index=True)
    hs_description: Mapped[str | None] = mapped_column(Text)
    partner_iso3: Mapped[str | None] = mapped_column(String(3), index=True)
    partner_name: Mapped[str | None] = mapped_column(String(255))
    value: Mapped[float | None] = mapped_column(Float)
    value_unit: Mapped[str] = mapped_column(String(16))  # TND / USD / MTND
    weight_kg: Mapped[float | None] = mapped_column(Float)
    quantity: Mapped[float | None] = mapped_column(Float)
    quantity_unit: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (Index("ix_cr_ds_hs_period", "dataset", "hs_code", "period"),)


class CustomsImport(Base, Provenance, DataMode):
    """Declaration-level customs data — ONLY loaded from an authorized extract (SINDA)."""

    __tablename__ = "customs_imports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    declaration_ref_hash: Mapped[str | None] = mapped_column(String(64))
    declaration_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    hs_code: Mapped[str] = mapped_column(String(12), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    importer_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    origin_iso3: Mapped[str | None] = mapped_column(String(3))
    provenance_iso3: Mapped[str | None] = mapped_column(String(3))
    entry_point_id: Mapped[str | None] = mapped_column(String(64), index=True)
    transport_mode: Mapped[str | None] = mapped_column(String(8))  # SEA / AIR / LAND
    quantity: Mapped[float | None] = mapped_column(Float)
    declared_value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    destination_governorate: Mapped[str | None] = mapped_column(String(128))
    import_batch: Mapped[str | None] = mapped_column(String(64))


class EntryPoint(Base, Provenance):
    __tablename__ = "entry_points"
    entry_point_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    official_name: Mapped[str] = mapped_column(String(255))
    entry_type: Mapped[str] = mapped_column(String(16))  # AIRPORT / SEAPORT / LAND_BORDER
    governorate: Mapped[str | None] = mapped_column(String(128))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    iata: Mapped[str | None] = mapped_column(String(8))
    neighbor_country: Mapped[str | None] = mapped_column(String(64))
    name_source: Mapped[str | None] = mapped_column(Text)


class Tariff(Base, Provenance):
    __tablename__ = "tariffs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hs_code: Mapped[str] = mapped_column(String(12))
    year: Mapped[int] = mapped_column(Integer)
    rate_pct: Mapped[float | None] = mapped_column(Float)


class Location(Base, Provenance):
    """Tunisian administrative zones (governorates) with geometry."""

    __tablename__ = "locations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    level: Mapped[str] = mapped_column(String(32))
    centroid_lat: Mapped[float | None] = mapped_column(Float)
    centroid_lon: Mapped[float | None] = mapped_column(Float)
    geometry: Mapped[dict | None] = mapped_column(JSON)


class BusinessMatch(Base, DataMode):
    __tablename__ = "business_matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id"))
    business_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40))  # VERIFIED / PROBABLE_MATCH / NOT_FOUND / UNKNOWN / INSTITUTIONAL_ACCESS_REQUIRED
    score: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(String(128))
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ProductMatch(Base, DataMode):
    __tablename__ = "product_matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32))  # observation / shop_type / question
    subject_id: Mapped[str] = mapped_column(String(128))
    subject_text: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[str] = mapped_column(String(12))
    score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(128))


class Cluster(Base, DataMode):
    __tablename__ = "clusters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # GEO_COMMERCIAL / FRAGMENTATION
    label: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    centroid_lat: Mapped[float | None] = mapped_column(Float)
    centroid_lon: Mapped[float | None] = mapped_column(Float)
    params: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class FragmentationPattern(Base, DataMode):
    __tablename__ = "fragmentation_patterns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hs_code: Mapped[str] = mapped_column(String(12))
    window_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(48))  # NORMAL / MONITOR / POSSIBLE FRAGMENTATION PATTERN
    score: Mapped[float] = mapped_column(Float)
    features: Mapped[dict | None] = mapped_column(JSON)
    period: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class NetworkNode(Base):
    __tablename__ = "network_nodes"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(255))
    attrs: Mapped[dict | None] = mapped_column(JSON)


class NetworkEdge(Base, DataMode):
    __tablename__ = "network_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    target: Mapped[str] = mapped_column(String(128), index=True)
    relation_type: Mapped[str] = mapped_column(String(64))
    evidence_type: Mapped[str] = mapped_column(String(32))  # VERIFIED / OBSERVED / STATISTICAL / AI_INFERENCE
    weight: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    source_key: Mapped[str | None] = mapped_column(String(64))
    period: Mapped[str | None] = mapped_column(String(32))


class Anomaly(Base, DataMode):
    __tablename__ = "anomalies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32))  # HS_CHAPTER_MONTH / PARTNER_HS_UNIT_VALUE / ENTRY
    subject_id: Mapped[str] = mapped_column(String(128), index=True)
    hs_code: Mapped[str | None] = mapped_column(String(12), index=True)
    period: Mapped[str | None] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)  # 0..100 (higher = more unusual)
    is_anomaly: Mapped[bool] = mapped_column(Boolean)
    reasons: Mapped[list | None] = mapped_column(JSON)
    features: Mapped[dict | None] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(64))
    source_key: Mapped[str | None] = mapped_column(String(64))
    data_coverage: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class RiskScore(Base, DataMode):
    __tablename__ = "risk_scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(String(12), index=True)
    score: Mapped[float | None] = mapped_column(Float)
    level: Mapped[str | None] = mapped_column(String(16))
    factors: Mapped[dict] = mapped_column(JSON)  # factor -> {value|None, weight, detail}
    explanation: Mapped[list | None] = mapped_column(JSON)  # max 5 signed factors
    data_coverage: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(8))
    period: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PriorityScore(Base, DataMode):
    __tablename__ = "priority_scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str] = mapped_column(String(128))
    score: Mapped[float] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSON)
    window: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Recommendation(Base, DataMode):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer)
    window: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64))
    what: Mapped[str] = mapped_column(Text)
    where: Mapped[str | None] = mapped_column(Text)
    why: Mapped[list] = mapped_column(JSON)
    priority_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str | None] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    data_coverage: Mapped[float] = mapped_column(Float)
    period: Mapped[str | None] = mapped_column(String(64))
    sources: Mapped[list] = mapped_column(JSON)
    recommended_review: Mapped[str] = mapped_column(Text)
    product_id: Mapped[str | None] = mapped_column(String(12))
    evidence: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Alert(Base, DataMode):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(Text)
    product_id: Mapped[str | None] = mapped_column(String(12))
    severity: Mapped[str] = mapped_column(String(16))
    period: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="TO_REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Feedback(Base, DataMode):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32))  # recommendation / alert / anomaly
    target_id: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(24))  # USEFUL / NOT_USEFUL / INVESTIGATE / FALSE_POSITIVE
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class EconomicIndicator(Base, Provenance, DataMode):
    __tablename__ = "economic_indicators"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(255))
    period: Mapped[str] = mapped_column(String(10))
    frequency: Mapped[str] = mapped_column(String(1))  # A / M
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("indicator", "period", "source_key"),)


class Forecast(Base, DataMode):
    __tablename__ = "forecasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(64))
    period: Mapped[str] = mapped_column(String(10))
    predicted: Mapped[float] = mapped_column(Float)
    lower: Mapped[float | None] = mapped_column(Float)
    upper: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ScenarioResult(Base, DataMode):
    __tablename__ = "scenario_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    assumptions: Mapped[dict] = mapped_column(JSON)
    results: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AgentRun(Base, DataMode):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(64))
    plan: Mapped[dict | None] = mapped_column(JSON)
    results: Mapped[list | None] = mapped_column(JSON)
    answer: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    llm_used: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    execution_time: Mapped[float | None] = mapped_column(Float)


class Report(Base, DataMode):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    meta: Mapped[dict | None] = mapped_column(JSON)
    institution: Mapped[str | None] = mapped_column(String(32), index=True)  # DOUANE / FINANCE
    created_by: Mapped[int | None] = mapped_column(Integer)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(24))
    log: Mapped[list | None] = mapped_column(JSON)


class SellerReview(Base, DataMode):
    """Result of the 'Vendeurs à vérifier' analysis (priority for human verification — never an accusation)."""

    __tablename__ = "seller_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(Integer, index=True)
    score: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(16))
    formalization: Mapped[str] = mapped_column(String(48))
    customs_activity: Mapped[str | None] = mapped_column(Text)
    consistency: Mapped[str | None] = mapped_column(Text)
    reasons: Mapped[list] = mapped_column(JSON)
    facts: Mapped[dict] = mapped_column(JSON)
    window: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ============================================================================ ACCOUNTS & ROLES
class User(Base):
    """Institutional account. The role is stored server-side (never inferred from the e-mail domain)."""

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))  # ROLE_DOUANE / ROLE_FINANCE / ROLE_ADMIN
    institution: Mapped[str] = mapped_column(String(32))  # DOUANE / FINANCE / ADMINISTRATION
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)


class AccessLog(Base):
    """Security journal: logins and refused accesses (403)."""

    __tablename__ = "access_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    email: Mapped[str | None] = mapped_column(String(255))
    event: Mapped[str] = mapped_column(String(32))  # LOGIN_OK / LOGIN_FAILED / FORBIDDEN
    path: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)


# ============================================================================ DOSSIERS (CASES)
class Case(Base):
    """A situation detected by the analysis that deserves human verification (never an accusation)."""

    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    signature: Mapped[str] = mapped_column(String(128), unique=True, index=True)  # dedup key of the detected situation
    kind: Mapped[str] = mapped_column(String(32))  # FRAGMENTATION / VALEUR / HAUSSE / POINT_ENTREE / MODE_ENTREE / COMMERCE_DOUANE
    motif: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    period: Mapped[str | None] = mapped_column(String(64))
    period_end: Mapped[datetime | None] = mapped_column(DateTime)
    product_id: Mapped[str | None] = mapped_column(String(12), index=True)
    product: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    country: Mapped[str | None] = mapped_column(String(128))
    country_iso3: Mapped[str | None] = mapped_column(String(3))
    continent: Mapped[str | None] = mapped_column(String(64))
    entry_mode: Mapped[str | None] = mapped_column(String(8))
    operations: Mapped[list | None] = mapped_column(JSON)
    entry_points: Mapped[list | None] = mapped_column(JSON)
    geographic_zone: Mapped[str | None] = mapped_column(String(128))
    online_observations: Mapped[dict | None] = mapped_column(JSON)
    risk_indicators: Mapped[list | None] = mapped_column(JSON)
    priority_score: Mapped[float] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(32))  # HABITUEL / A_SURVEILLER / A_VERIFIER / PRIORITAIRE
    confidence: Mapped[str | None] = mapped_column(String(16))
    explanation: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    value_concerned: Mapped[float | None] = mapped_column(Float)  # value of the operations concerned
    gap_to_verify: Mapped[float | None] = mapped_column(Float)  # potential gap (never a tax assessment)
    amount_unit: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(24), default="A_ANALYSER", index=True)
    assigned_customs_user: Mapped[int | None] = mapped_column(Integer)
    finance_status: Mapped[str | None] = mapped_column(String(24))  # RECU / EN_ANALYSE / TRAITE
    created_by: Mapped[str] = mapped_column(String(64), default="Analyse IA")


class CaseEvent(Base):
    """Mandatory history of every dossier."""

    __tablename__ = "case_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(Integer, index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    user_id: Mapped[int | None] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(255))
    institution: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(16), default="ALL")  # ALL / DOUANE / FINANCE


class CaseTransfer(Base):
    __tablename__ = "case_transfers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(Integer, index=True)
    sender_user_id: Mapped[int] = mapped_column(Integer)
    sender_institution: Mapped[str] = mapped_column(String(32))
    receiver_institution: Mapped[str] = mapped_column(String(32))
    motif: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list | None] = mapped_column(JSON)
    snapshot: Mapped[dict | None] = mapped_column(JSON)  # what Finance receives (frozen at transfer time)
    transferred_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    status: Mapped[str] = mapped_column(String(24), default="TRANSMIS")  # TRANSMIS / RECU / EN_ANALYSE / TRAITE
    received_at: Mapped[datetime | None] = mapped_column(DateTime)
    received_by: Mapped[int | None] = mapped_column(Integer)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    finance_comment: Mapped[str | None] = mapped_column(Text)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    institution: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[dict | None] = mapped_column(JSON)
    case_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
