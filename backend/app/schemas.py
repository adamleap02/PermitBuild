"""Pydantic (v2) request/response schemas for the API layer."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_size_score: float
    project_size_explanation: str
    budget_tier: str
    budget_tier_explanation: str
    urgency_score: float
    urgency_explanation: str
    luxury_likelihood: float
    luxury_explanation: str
    remodel_vs_repair: str
    remodel_vs_repair_explanation: str
    investment_property_likelihood: float
    investment_property_explanation: str
    lead_score: float
    lead_score_explanation: str
    confidence_score: float
    confidence_explanation: str
    computed_at: datetime


class PermitVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_number: int
    snapshot: dict[str, Any]
    changed_fields: dict[str, Any]
    recorded_at: datetime


class PermitListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jurisdiction_id: int
    permit_number: str
    permit_type: Optional[str] = None
    status: Optional[str] = None
    issue_date: Optional[datetime] = None
    application_date: Optional[datetime] = None
    property_address: Optional[str] = None
    estimated_cost: Optional[float] = None
    valuation: Optional[float] = None
    work_category: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source: Optional[str] = None


class PermitDetail(PermitListItem):
    contractor: Optional[str] = None
    builder: Optional[str] = None
    architect: Optional[str] = None
    engineer: Optional[str] = None
    parcel_number: Optional[str] = None
    description: Optional[str] = None
    square_footage: Optional[float] = None
    units: Optional[int] = None
    completion_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    permit_url: Optional[str] = None
    property_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    versions: list[PermitVersionOut] = Field(default_factory=list)
    latest_score: Optional[ScoreOut] = None


class PermitListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PermitListItem]


class OwnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    owner_type: Optional[str] = None
    mailing_address: Optional[str] = None
    is_owner_occupied: Optional[bool] = None


class PropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    address: str
    normalized_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    parcel_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    property_type: Optional[str] = None
    year_built: Optional[int] = None
    lot_size_sqft: Optional[float] = None
    building_size_sqft: Optional[float] = None
    bedrooms: Optional[float] = None
    bathrooms: Optional[float] = None
    stories: Optional[float] = None
    owners: list[OwnerOut] = Field(default_factory=list)
    permits: list[PermitListItem] = Field(default_factory=list)


class IngestRunRequest(BaseModel):
    jurisdiction_id: int
    since: Optional[datetime] = None
    limit: Optional[int] = Field(default=None, ge=1, le=10000)
    compute_scores: bool = True


class IngestRunResponse(BaseModel):
    jurisdiction_id: int
    jurisdiction_name: str
    fetched: int
    created: int
    updated: int
    unchanged: int
    errors: int
    scored: int


class JurisdictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    state: str
    level: str
    source_system: str
    source_config: dict[str, Any]
    is_active: bool


class JurisdictionCreate(BaseModel):
    name: str
    state: str
    level: str = "city"
    timezone: str = "UTC"
    source_system: str
    source_config: dict[str, Any]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)
    full_name: Optional[str] = None
    organization_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------


class CheckoutSessionRequest(BaseModel):
    plan: str = Field(description="Plan identifier, e.g. 'starter', 'pro', 'enterprise'")
    success_url: str = "http://localhost:8000/billing/success"
    cancel_url: str = "http://localhost:8000/billing/cancel"


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class BillingStatusResponse(BaseModel):
    configured: bool
    plan: Optional[str] = None
    status: Optional[str] = None
    current_period_end: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Saved searches + alerts
# ---------------------------------------------------------------------------


class SavedSearchCreate(BaseModel):
    name: str
    filters: dict[str, Any] = Field(default_factory=dict, description="Same filter keys as GET /permits")


class SavedSearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    user_id: int
    name: str
    filters: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AlertCreate(BaseModel):
    saved_search_id: int
    channel: str = Field(default="email", description="'email' or 'sms' (both stubbed -- see BLOCKERS.md)")
    recipient: str = Field(description="Email address or phone number to (stub-)notify")
    frequency: str = Field(default="daily", description="'instant', 'daily', or 'weekly'")


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    saved_search_id: int
    organization_id: int
    user_id: int
    channel: str
    recipient: str
    frequency: str
    is_active: bool
    last_checked_at: Optional[datetime] = None
    created_at: datetime


class AlertRunResult(BaseModel):
    alert_id: int
    matched_permits: int
    delivery_status: str
    delivery_log_id: Optional[int] = None
