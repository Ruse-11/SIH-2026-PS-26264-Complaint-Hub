"""Hub database tables (SQLAlchemy 2). One class = one table. See CLAUDE.md section 9.

Privacy: the reporter table keeps only a hashed fingerprint, never a name, phone or email.
"""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Institution(Base):
    __tablename__ = "institution"
    aicte_id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. SYN-0001
    official_name: Mapped[str] = mapped_column(String)
    name_normalized: Mapped[str] = mapped_column(String, index=True)  # lowercase, no punctuation (for matching)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("institution.aicte_id"))  # parent university
    address_line: Mapped[str | None] = mapped_column(String)
    area: Mapped[str | None] = mapped_column(String)
    district: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)
    pincode: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    type: Mapped[str | None] = mapped_column(String)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    programs: Mapped[str | None] = mapped_column(String)
    established_year: Mapped[int | None] = mapped_column(Integer)


class InstitutionAlias(Base):
    __tablename__ = "institution_alias"
    __table_args__ = (UniqueConstraint("alias_normalized", "institution_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String)  # as written in the dataset
    alias_normalized: Mapped[str] = mapped_column(String, index=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institution.aicte_id"), index=True)
    alias_type: Mapped[str] = mapped_column(String)  # ACRONYM, SHORT_NAME, COMMON_TYPO, ...
    source: Mapped[str] = mapped_column(String, default="curated")  # curated / auto / learned


class Reporter(Base):
    __tablename__ = "reporter"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # REP-0001
    fingerprint_hash: Mapped[str] = mapped_column(String, unique=True)  # HMAC of the verified phone
    reporter_type: Mapped[str | None] = mapped_column(String)  # student, parent, alumni, faculty, other
    validation_method: Mapped[str | None] = mapped_column(String)  # SEED now, MOCK_OTP from M4
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)


class Case(Base):
    __tablename__ = "cases"  # "case" is an SQL keyword, so the table is plural
    __table_args__ = (
        UniqueConstraint("source_system", "source_case_no"),
        Index("ix_cases_institution_status", "institution_id", "status"),
    )
    hub_case_id: Mapped[str] = mapped_column(String, primary_key=True)  # HUB-0001
    source_system: Mapped[str] = mapped_column(String)  # RB or PGRC (the portal it came from)
    source_case_no: Mapped[str] = mapped_column(String)  # the portal's own case number
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institution.aicte_id"), index=True)  # NULL = unverified
    resolution_method: Mapped[str] = mapped_column(String)  # REPORTER_CONFIRMED / GUIDED / UNLISTED
    finder_answers: Mapped[dict | None] = mapped_column(JSON)
    reporter_id: Mapped[str | None] = mapped_column(ForeignKey("reporter.id"), index=True)
    category: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String, index=True)  # Pending, Under Process, Disposed, ...
    assigned_bureau: Mapped[str | None] = mapped_column(String, index=True)
    assigned_officer: Mapped[str | None] = mapped_column(String)
    severity: Mapped[int] = mapped_column(Integer)  # 1..5
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)  # computed in M7
    expected_disposal_date: Mapped[date | None] = mapped_column(Date)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("cluster.id"))


class CaseAction(Base):
    __tablename__ = "case_action"
    __table_args__ = (UniqueConstraint("case_id", "seq"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.hub_case_id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String)
    stance: Mapped[str] = mapped_column(String)  # ENFORCING / REQUESTING / CLOSING / NEUTRAL
    actor: Mapped[str | None] = mapped_column(String)  # the officer
    bureau: Mapped[str] = mapped_column(String)
    remarks: Mapped[str | None] = mapped_column(Text)
    doc_ref: Mapped[str | None] = mapped_column(String)
    at: Mapped[datetime] = mapped_column(DateTime)
    from_bureau: Mapped[str | None] = mapped_column(String)  # only for transfers
    to_bureau: Mapped[str | None] = mapped_column(String)


class Cluster(Base):
    __tablename__ = "cluster"
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institution.aicte_id"))
    category: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LinkSuggestion(Base):
    """A suggested link between two cases. Officers confirm or reject; rejected pairs are never re-suggested."""
    __tablename__ = "link_suggestion"
    __table_args__ = (UniqueConstraint("case_a", "case_b", "link_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_a: Mapped[str] = mapped_column(ForeignKey("cases.hub_case_id"), index=True)
    case_b: Mapped[str] = mapped_column(ForeignKey("cases.hub_case_id"), index=True)
    link_type: Mapped[str] = mapped_column(String)  # SAME_REPORTER / CORROBORATION / CROSS_BUREAU / CONFLICT
    score: Mapped[float | None] = mapped_column(Float)
    reasons: Mapped[dict | None] = mapped_column(JSON)  # why the system suggested it
    status: Mapped[str] = mapped_column(String, default="SUGGESTED")  # SUGGESTED / CONFIRMED / REJECTED
    decided_by: Mapped[str | None] = mapped_column(String)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Alert(Base):
    __tablename__ = "alert"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String)  # OVERLAP, DUPLICATE, CONFLICT, SLA, STALLED, ESCALATION
    severity: Mapped[str] = mapped_column(String)  # info / warning / critical
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.hub_case_id"))
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institution.aicte_id"), index=True)
    link_id: Mapped[int | None] = mapped_column(ForeignKey("link_suggestion.id"))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    acknowledged_by: Mapped[str | None] = mapped_column(String)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)


class User(Base):
    __tablename__ = "user_account"  # "user" is reserved in some databases
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    bureau: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    display_name: Mapped[str | None] = mapped_column(String)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    actor: Mapped[str] = mapped_column(String)
    role: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)  # e.g. LINK_CONFIRMED
    entity_type: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(String)
    detail: Mapped[dict | None] = mapped_column(JSON)


# ---- configuration tables: editable assumptions, not hard-coded rules ----
class SlaPolicy(Base):
    __tablename__ = "sla_policy"
    id: Mapped[int] = mapped_column(primary_key=True)
    bureau: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)  # NULL = default for the bureau
    days: Mapped[int] = mapped_column(Integer)


class CategoryOwnership(Base):
    __tablename__ = "category_ownership"
    category: Mapped[str] = mapped_column(String, primary_key=True)
    bureau: Mapped[str] = mapped_column(String)  # the bureau that normally leads this category


class ActionTypeStance(Base):
    __tablename__ = "action_type_stance"
    action_type: Mapped[str] = mapped_column(String, primary_key=True)
    stance: Mapped[str] = mapped_column(String)


class Threshold(Base):
    __tablename__ = "thresholds"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(String)
