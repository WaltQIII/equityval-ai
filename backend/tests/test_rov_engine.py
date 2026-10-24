"""Unit tests for the Spatial Hedonic Regression, NLP Prohibited Phrase Scanner, and Vision UAD Auditor."""

from __future__ import annotations

from app.models.schemas import RovAuditCreateRequest
from app.services.rov_engine import (
    execute_rov_valuation_audit,
    haversine_miles,
    scan_form_1004_commentary,
)


def test_haversine_distance_calculation():
    # Distance between Cascade Heights points (~0.25 miles)
    d = haversine_miles(33.7254, -84.4512, 33.7275, -84.4494)
    assert 0.10 <= d <= 0.35


def test_nlp_prohibited_phrase_scanner_flags_fhfa_violations():
    commentary = (
        "Subject lies in a changing demographic trends district with mixed pride of ownership "
        "and elevated crime near the southern distressed corridor."
    )
    flags = scan_form_1004_commentary(commentary)
    flagged_phrases = {f.phrase for f in flags}
    assert "changing demographic trends" in flagged_phrases
    assert "pride of ownership" in flagged_phrases
    assert "crime" in flagged_phrases
    assert "distressed corridor" in flagged_phrases
    assert all(f.regulatory_citation for f in flags)
    assert all(f.recommended_neutral_replacement for f in flags)


def test_execute_rov_valuation_audit_quantifies_undervaluation_gap():
    req = RovAuditCreateRequest(
        property_address="1428 Cascade Rd SW, Atlanta, GA 30311",
        appraised_value_usd=412000.0,
        contract_price_usd=465000.0,
        appraiser_condition_code="C4",
        appraiser_quality_code="Q4",
    )
    res = execute_rov_valuation_audit(req)
    assert res.equityval_fair_value_usd > res.appraised_value_usd
    assert res.estimated_undervaluation_gap_usd >= 40000.0
    assert res.undervaluation_pct > 8.0
    assert res.vision_audit.ai_vision_condition_score < 4.0
    assert res.vision_audit.unjustified_negative_adjustment_usd >= 15000.0
    assert res.bias_risk_score >= 60
    assert res.fhfa_undervaluation_flag is True
    assert len(res.evaluated_comps) == 6
