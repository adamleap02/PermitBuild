"""
Rules-based, fully explainable permit scoring engine.

Deliberately NOT machine learning: every score is a transparent
function of concrete fields (valuation, description keywords,
permit_type, dates, units, etc.) and every numeric score is returned
alongside a human-readable explanation string describing exactly why
it landed where it did. This keeps the "why" auditable for end users
(contractors/lenders/insurers) who need to trust a lead score.

Entry point: score_permit(permit) -> ScoreResult
`permit` can be a SQLAlchemy Permit instance, a PermitInput dataclass,
or anything with matching attributes (duck typing via getattr).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Input shape
# ---------------------------------------------------------------------------


@dataclass
class PermitInput:
    """Plain-data shape mirroring the fields of app.models.Permit that the
    scoring engine reads. Lets tests build example permits without a DB."""

    permit_type: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    work_category: Optional[str] = None
    contractor: Optional[str] = None
    builder: Optional[str] = None
    estimated_cost: Optional[float] = None
    valuation: Optional[float] = None
    square_footage: Optional[float] = None
    units: Optional[int] = None
    application_date: Optional[datetime] = None
    issue_date: Optional[datetime] = None
    completion_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    property_address: Optional[str] = None


def _attr(permit: Any, name: str) -> Any:
    return getattr(permit, name, None)


def _cost(permit: Any) -> Optional[float]:
    """Best available dollar figure: prefer valuation, fall back to estimated_cost."""
    valuation = _attr(permit, "valuation")
    if valuation:
        return float(valuation)
    est = _attr(permit, "estimated_cost")
    return float(est) if est else None


def _text_blob(permit: Any) -> str:
    parts = [
        _attr(permit, "description") or "",
        _attr(permit, "permit_type") or "",
        _attr(permit, "work_category") or "",
    ]
    return " ".join(parts).lower()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Individual scoring functions
# ---------------------------------------------------------------------------

# Budget tier thresholds (USD), tuned for typical single-family
# residential + light-commercial permit valuations.
BUDGET_TIERS = [
    (5_000, "micro"),
    (25_000, "small"),
    (100_000, "medium"),
    (500_000, "large"),
    (float("inf"), "major"),
]


def score_project_size(permit: Any) -> tuple[float, str]:
    """
    0-100 score combining square footage, unit count, and dollar value
    into a single "how big is this project" signal. Any single strong
    signal (e.g. a $2M job with no sqft data) is enough to score high.
    """
    cost = _cost(permit)
    sqft = _attr(permit, "square_footage")
    units = _attr(permit, "units")

    signals: list[float] = []
    reasons: list[str] = []

    if cost is not None:
        # log-ish scale: $10k -> ~20, $100k -> ~50, $1M+ -> ~90+
        cost_score = min(100.0, max(0.0, (cost ** 0.35) / 6.0))
        signals.append(cost_score)
        reasons.append(f"valuation ${cost:,.0f}")

    if sqft is not None and sqft > 0:
        sqft_score = min(100.0, (sqft / 5000.0) * 100.0)
        signals.append(sqft_score)
        reasons.append(f"{sqft:,.0f} sqft")

    if units is not None and units > 0:
        unit_score = min(100.0, (units / 20.0) * 100.0)
        signals.append(unit_score)
        reasons.append(f"{units} unit(s)")

    if not signals:
        return 0.0, "No cost, square footage, or unit data available -- defaulting to 0."

    score = round(max(signals), 1)
    explanation = "Project size score based on: " + ", ".join(reasons) + f" -> {score}/100."
    return score, explanation


def score_budget_tier(permit: Any) -> tuple[str, str]:
    cost = _cost(permit)
    if cost is None:
        return "unknown", "No estimated_cost or valuation present on the permit."

    for threshold, tier in BUDGET_TIERS:
        if cost < threshold:
            return tier, f"${cost:,.0f} falls in the '{tier}' tier (< ${threshold:,.0f})." if threshold != float("inf") else f"${cost:,.0f} falls in the '{tier}' tier."
    return "major", f"${cost:,.0f} falls in the 'major' tier."


URGENCY_KEYWORDS = ("emergency", "urgent", "unsafe", "hazard", "condemn", "fire damage", "storm damage", "collapse")


def score_urgency(permit: Any) -> tuple[float, str]:
    """
    Higher = more time-sensitive lead. Driven by: permit issued very
    recently (fresh lead), an approaching expiration date (contractor
    needs to act soon), or urgency-signaling keywords in the description.
    """
    score = 0.0
    reasons: list[str] = []
    now = _now()

    issue_date = _as_aware(_attr(permit, "issue_date"))
    if issue_date is not None:
        days_since_issue = (now - issue_date).days
        if days_since_issue < 0:
            days_since_issue = 0
        if days_since_issue <= 30:
            freshness = 60.0 * (1.0 - days_since_issue / 30.0)
            score += freshness
            reasons.append(f"issued {days_since_issue} day(s) ago (fresh)")
        else:
            reasons.append(f"issued {days_since_issue} day(s) ago (not fresh)")

    expiration_date = _as_aware(_attr(permit, "expiration_date"))
    if expiration_date is not None:
        days_to_expiry = (expiration_date - now).days
        if 0 <= days_to_expiry <= 60:
            expiry_boost = 40.0 * (1.0 - days_to_expiry / 60.0)
            score += expiry_boost
            reasons.append(f"expires in {days_to_expiry} day(s)")
        elif days_to_expiry < 0:
            reasons.append("permit already expired")

    text = _text_blob(permit)
    hit_keywords = [kw for kw in URGENCY_KEYWORDS if kw in text]
    if hit_keywords:
        score += 25.0
        reasons.append(f"urgency keywords found: {', '.join(hit_keywords)}")

    score = round(min(100.0, score), 1)
    if not reasons:
        return 0.0, "No issue/expiration dates or urgency keywords found -- defaulting to 0."
    return score, "Urgency score based on: " + "; ".join(reasons) + f" -> {score}/100."


LUXURY_KEYWORDS = (
    "pool", "spa", "wine cellar", "custom home", "high-end", "high end", "luxury",
    "elevator", "home theater", "guest house", "casita", "outdoor kitchen",
    "smart home", "solar", "rooftop deck", "penthouse",
)


def score_luxury_likelihood(permit: Any) -> tuple[float, str]:
    """
    0-100 likelihood the project is a high-end/luxury job, combining
    cost-per-square-foot (when both are available) with luxury-signaling
    keywords in the description/work category.
    """
    score = 0.0
    reasons: list[str] = []

    cost = _cost(permit)
    sqft = _attr(permit, "square_footage")
    if cost and sqft and sqft > 0:
        cost_per_sqft = cost / sqft
        # Rough heuristic: >$300/sqft on a remodel/addition starts to look
        # like a high-end finish-out; >$600/sqft is clearly luxury-tier.
        if cost_per_sqft >= 600:
            score += 70.0
        elif cost_per_sqft >= 300:
            score += 40.0
        elif cost_per_sqft >= 150:
            score += 15.0
        reasons.append(f"${cost_per_sqft:,.0f}/sqft")

    text = _text_blob(permit)
    hits = [kw for kw in LUXURY_KEYWORDS if kw in text]
    if hits:
        score += min(50.0, 15.0 * len(hits))
        reasons.append(f"luxury keywords: {', '.join(hits)}")

    score = round(min(100.0, score), 1)
    if not reasons:
        return 0.0, "No cost-per-sqft or luxury keywords detected -- defaulting to 0."
    return score, "Luxury likelihood based on: " + "; ".join(reasons) + f" -> {score}/100."


NEW_CONSTRUCTION_KEYWORDS = ("new construction", "new single family", "new sfd", "new dwelling", "ground up", "new building")
ADDITION_KEYWORDS = ("addition", "add ", "adu", "accessory dwelling", "second story", "expand")
# Note: deliberately excludes generic administrative labels like
# "alteration(s) permit" -- many jurisdictions (e.g. SF's "OTC
# Alterations Permit") use that as a catch-all permit *type* name for
# minor work, so it's not a reliable remodel signal on its own; we only
# trust more specific scope-of-work terms here.
REMODEL_KEYWORDS = ("remodel", "renovation", "renovate", "kitchen", "bathroom", "finish basement", "rehab")
REPAIR_KEYWORDS = ("repair", "replace", "reroof", "re-roof", "water heater", "furnace", "patch", "fix", "maintenance")


def classify_remodel_vs_repair(permit: Any) -> tuple[str, str]:
    """
    Classifies the permit into one of: new_construction, addition,
    remodel, repair, other -- based on keyword matches in permit_type/
    work_category/description, checked in order of specificity.
    """
    text = _text_blob(permit)

    def hits(keywords: tuple[str, ...]) -> list[str]:
        return [kw for kw in keywords if kw in text]

    new_hits = hits(NEW_CONSTRUCTION_KEYWORDS)
    if new_hits:
        return "new_construction", f"Classified as new_construction due to keyword(s): {', '.join(new_hits)}."

    addition_hits = hits(ADDITION_KEYWORDS)
    if addition_hits:
        return "addition", f"Classified as addition due to keyword(s): {', '.join(addition_hits)}."

    remodel_hits = hits(REMODEL_KEYWORDS)
    repair_hits = hits(REPAIR_KEYWORDS)
    if remodel_hits and (not repair_hits or len(remodel_hits) >= len(repair_hits)):
        return "remodel", f"Classified as remodel due to keyword(s): {', '.join(remodel_hits)}."
    if repair_hits:
        return "repair", f"Classified as repair due to keyword(s): {', '.join(repair_hits)}."

    return "other", "No new-construction/addition/remodel/repair keywords matched permit_type, work_category, or description."


INVESTMENT_KEYWORDS = ("rental", "tenant improvement", "ti permit", "multi-family", "multifamily", "apartment", "commercial", "landlord", "llc", "lp", "investors", "investment")


def score_investment_property_likelihood(permit: Any) -> tuple[float, str]:
    """
    0-100 likelihood the property is investor-owned / income property
    rather than an owner-occupied primary residence, based on unit
    count, contractor/builder name patterns (LLC/LP), and keyword hits.
    """
    score = 0.0
    reasons: list[str] = []

    units = _attr(permit, "units")
    if units is not None and units >= 2:
        boost = min(60.0, 15.0 * units)
        score += boost
        reasons.append(f"{units} units on the permit")

    contractor = (_attr(permit, "contractor") or "") + " " + (_attr(permit, "builder") or "")
    contractor_lower = contractor.lower()
    if re.search(r"\bllc\b|\bl\.l\.c\.\b|\blp\b|\bl\.p\.\b|\binc\b", contractor_lower):
        score += 20.0
        reasons.append("contractor/builder name suggests a business entity (LLC/LP/Inc)")

    text = _text_blob(permit)
    hits = [kw for kw in INVESTMENT_KEYWORDS if kw in text]
    if hits:
        score += min(30.0, 10.0 * len(hits))
        reasons.append(f"keywords: {', '.join(hits)}")

    score = round(min(100.0, score), 1)
    if not reasons:
        return 0.0, "No multi-unit, business-entity, or investment keywords detected -- defaulting to 0 (likely owner-occupied)."
    return score, "Investment-property likelihood based on: " + "; ".join(reasons) + f" -> {score}/100."


def score_confidence(permit: Any) -> tuple[float, str]:
    """
    Data-completeness confidence score: how much of the underlying data
    the other scores actually had to work with. Low confidence flags a
    permit whose scores should be treated with skepticism.
    """
    fields_to_check = (
        "estimated_cost", "valuation", "square_footage", "units",
        "description", "permit_type", "work_category", "issue_date",
        "application_date", "property_address",
    )
    present = [f for f in fields_to_check if _attr(permit, f) not in (None, "")]
    ratio = len(present) / len(fields_to_check)
    score = round(ratio * 100.0, 1)
    return score, (
        f"{len(present)}/{len(fields_to_check)} key fields populated "
        f"({', '.join(present) if present else 'none'}) -> {score}/100 confidence."
    )


def score_lead(
    project_size: float,
    urgency: float,
    luxury: float,
    investment: float,
    confidence: float,
    budget_tier: str,
) -> tuple[float, str]:
    """
    Composite 0-100 "how good a sales lead is this" score. Weighted
    blend of the sub-scores, scaled down by low data confidence (a
    high score built on missing data is not trustworthy).
    """
    tier_weight = {
        "unknown": 0.0, "micro": 0.1, "small": 0.3, "medium": 0.6, "large": 0.85, "major": 1.0,
    }.get(budget_tier, 0.3)

    raw = (
        0.35 * project_size
        + 0.20 * urgency
        + 0.15 * luxury
        + 0.15 * investment
        + 0.15 * (tier_weight * 100.0)
    )
    confidence_multiplier = 0.5 + 0.5 * (confidence / 100.0)  # never zero out entirely
    final = round(min(100.0, raw * confidence_multiplier), 1)

    explanation = (
        f"Lead score = weighted blend of project_size({project_size}), urgency({urgency}), "
        f"luxury({luxury}), investment_likelihood({investment}), and budget_tier('{budget_tier}'), "
        f"scaled by data confidence ({confidence}%) -> {final}/100."
    )
    return final, explanation


# ---------------------------------------------------------------------------
# Top-level result
# ---------------------------------------------------------------------------


@dataclass
class ScoreResult:
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

    def as_dict(self) -> dict:
        return {
            "project_size_score": self.project_size_score,
            "project_size_explanation": self.project_size_explanation,
            "budget_tier": self.budget_tier,
            "budget_tier_explanation": self.budget_tier_explanation,
            "urgency_score": self.urgency_score,
            "urgency_explanation": self.urgency_explanation,
            "luxury_likelihood": self.luxury_likelihood,
            "luxury_explanation": self.luxury_explanation,
            "remodel_vs_repair": self.remodel_vs_repair,
            "remodel_vs_repair_explanation": self.remodel_vs_repair_explanation,
            "investment_property_likelihood": self.investment_property_likelihood,
            "investment_property_explanation": self.investment_property_explanation,
            "lead_score": self.lead_score,
            "lead_score_explanation": self.lead_score_explanation,
            "confidence_score": self.confidence_score,
            "confidence_explanation": self.confidence_explanation,
        }


def score_permit(permit: Any) -> ScoreResult:
    """Compute the full explainable score set for a single permit."""
    project_size, project_size_expl = score_project_size(permit)
    tier, tier_expl = score_budget_tier(permit)
    urgency, urgency_expl = score_urgency(permit)
    luxury, luxury_expl = score_luxury_likelihood(permit)
    remodel_repair, remodel_repair_expl = classify_remodel_vs_repair(permit)
    investment, investment_expl = score_investment_property_likelihood(permit)
    confidence, confidence_expl = score_confidence(permit)
    lead, lead_expl = score_lead(project_size, urgency, luxury, investment, confidence, tier)

    return ScoreResult(
        project_size_score=project_size,
        project_size_explanation=project_size_expl,
        budget_tier=tier,
        budget_tier_explanation=tier_expl,
        urgency_score=urgency,
        urgency_explanation=urgency_expl,
        luxury_likelihood=luxury,
        luxury_explanation=luxury_expl,
        remodel_vs_repair=remodel_repair,
        remodel_vs_repair_explanation=remodel_repair_expl,
        investment_property_likelihood=investment,
        investment_property_explanation=investment_expl,
        lead_score=lead,
        lead_score_explanation=lead_expl,
        confidence_score=confidence,
        confidence_explanation=confidence_expl,
    )
