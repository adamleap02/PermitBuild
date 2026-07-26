from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.scoring.engine import PermitInput, score_permit

NOW = datetime.now(timezone.utc)


def test_small_repair_permit_scores_low_and_classifies_as_repair():
    permit = PermitInput(
        permit_type="OTC Alterations Permit",
        status="issued",
        description="replace water heater",
        estimated_cost=1200.0,
        issue_date=NOW - timedelta(days=400),
    )
    result = score_permit(permit)

    assert result.budget_tier == "micro"
    assert result.remodel_vs_repair == "repair"
    assert result.lead_score < 20
    assert result.luxury_likelihood == 0.0


def test_large_new_construction_permit_scores_high_and_urgent():
    permit = PermitInput(
        permit_type="New Construction",
        status="issued",
        description="new single family dwelling, ground up construction, pool and spa, custom home",
        estimated_cost=1_500_000.0,
        square_footage=4000.0,
        units=1,
        issue_date=NOW - timedelta(days=5),
        expiration_date=NOW + timedelta(days=20),
    )
    result = score_permit(permit)

    assert result.budget_tier == "major"
    assert result.remodel_vs_repair == "new_construction"
    assert result.luxury_likelihood > 50
    assert result.urgency_score > 50
    assert result.lead_score > 50


def test_multifamily_permit_scores_investment_likely():
    permit = PermitInput(
        permit_type="Multi-Family Building Permit",
        description="new apartment building, 24 units, rental property for investors LLC",
        estimated_cost=3_000_000.0,
        units=24,
        contractor="Acme Builders LLC",
    )
    result = score_permit(permit)

    assert result.investment_property_likelihood > 50
    assert "unit" in result.investment_property_explanation.lower()


def test_remodel_keyword_beats_repair_when_more_specific():
    permit = PermitInput(
        permit_type="Alteration",
        description="kitchen and bathroom remodel, renovate interior finishes",
        estimated_cost=45000.0,
    )
    result = score_permit(permit)

    assert result.remodel_vs_repair == "remodel"
    assert result.budget_tier == "medium"


def test_addition_keyword_classified_correctly():
    permit = PermitInput(
        permit_type="Addition",
        description="add 1 new accessory dwelling unit (ADU), second story addition",
        estimated_cost=120000.0,
    )
    result = score_permit(permit)

    assert result.remodel_vs_repair == "addition"
    assert result.budget_tier == "large"


def test_no_data_permit_scores_zero_and_low_confidence():
    permit = PermitInput()
    result = score_permit(permit)

    assert result.project_size_score == 0.0
    assert result.budget_tier == "unknown"
    assert result.confidence_score == 0.0
    assert result.lead_score == 0.0


def test_confidence_score_reflects_field_completeness():
    sparse = PermitInput(estimated_cost=10000.0)
    rich = PermitInput(
        estimated_cost=10000.0,
        valuation=10500.0,
        square_footage=1200.0,
        units=1,
        description="kitchen remodel",
        permit_type="Alteration",
        work_category="residential",
        issue_date=NOW,
        application_date=NOW - timedelta(days=10),
        property_address="123 Main St",
    )

    sparse_result = score_permit(sparse)
    rich_result = score_permit(rich)

    assert rich_result.confidence_score > sparse_result.confidence_score


def test_explanations_are_nonempty_strings_for_every_field():
    permit = PermitInput(
        permit_type="Residential Remodel",
        description="bathroom remodel",
        estimated_cost=30000.0,
    )
    result = score_permit(permit)
    for explanation in (
        result.project_size_explanation,
        result.budget_tier_explanation,
        result.urgency_explanation,
        result.luxury_explanation,
        result.remodel_vs_repair_explanation,
        result.investment_property_explanation,
        result.lead_score_explanation,
        result.confidence_explanation,
    ):
        assert isinstance(explanation, str) and len(explanation) > 0
