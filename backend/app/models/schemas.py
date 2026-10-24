"""
Pydantic v2 Data Models & Regulatory Compliance Schemas for EquityVal AI.

Implements:
- Algorithmic Real Estate Appraisal Bias & Reconsideration of Value (ROV) Audit schemas
- Fannie Mae Form 1004 / Freddie Mac Form 70 UAD Condition & Quality (C1-C6 / Q1-Q6) models
- FHFA / HUD / Fair Housing Act NLP Prohibited Phrase Violation schemas
- Geospatial Redlining Boundary & Hedonic Comparable Sales Regression schemas
- Mandatory Interagency ROV & USPAP Regulatory Compliance Attestation Shield
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

MANDATORY_ROV_ATTESTATION_DISCLAIMER = (
    "EquityVal AI outputs constitute an automated algorithmic valuation compliance audit and "
    "Reconsideration of Value (ROV) evidence dossier under FHFA, Fannie Mae, Freddie Mac, HUD, "
    "and FHA Interagency ROV guidance. This dossier does not constitute a licensed USPAP appraisal; "
    "final collateral valuation and underwriting determinations remain the sole responsibility of "
    "the Certified Residential Appraiser, Appraisal Management Company (AMC), and Mortgage Lender."
)


class UserPlan(str, Enum):
    TRIAL = "trial"
    SINGLE_AUDIT = "single_audit"
    PRO_MONTHLY = "pro_monthly"
    ENTERPRISE = "enterprise"


class UserRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    email: str
    full_name: str = "Fair Lending & ROV Compliance Analyst"
    license_or_nmls_id: Optional[str] = "NMLS-ROV-884120"
    password_hash: Optional[str] = None
    plan: UserPlan = UserPlan.TRIAL
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ComparableSaleInput(BaseModel):
    comp_id: str = Field(..., min_length=1, max_length=64)
    address: str = Field(..., min_length=3, max_length=255)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    sale_price_usd: float = Field(..., gt=10000.0)
    gla_sqft: int = Field(..., gt=200, le=25000, description="Gross Living Area in sq ft")
    bedrooms: int = Field(default=3, ge=1, le=15)
    bathrooms: float = Field(default=2.0, ge=1.0, le=15.0)
    days_since_sale: int = Field(default=45, ge=0, le=1095)
    condition_uad: str = Field(default="C3", description="UAD Condition rating C1-C6")
    quality_uad: str = Field(default="Q3", description="UAD Quality rating Q1-Q6")
    appraiser_net_adj_usd: float = Field(default=0.0)
    is_distressed_or_reo: bool = Field(default=False)
    crossed_redlining_boundary: bool = Field(default=False)
    census_tract_minority_pct: float = Field(default=72.0, ge=0.0, le=100.0)
    selection_source: Literal["appraiser_selected", "equityval_recommended"] = "appraiser_selected"


class EvaluatedComparableSale(ComparableSaleInput):
    distance_miles: float
    price_per_sqft_usd: float
    hedonic_adjusted_value_usd: float
    similarity_weight: float
    audit_flags: List[str] = Field(default_factory=list)


class NlpFlaggedPhrase(BaseModel):
    phrase: str
    category: str
    severity: Literal["critical", "high", "moderate"]
    regulatory_citation: str
    context_snippet: str
    recommended_neutral_replacement: str


class VisionConditionAudit(BaseModel):
    appraiser_condition_code: str = Field(default="C4")
    ai_vision_condition_score: float = Field(default=3.2, ge=1.0, le=6.0)
    appraiser_quality_code: str = Field(default="Q4")
    ai_vision_quality_score: float = Field(default=3.3, ge=1.0, le=6.0)
    detected_upgrades: List[str] = Field(default_factory=list)
    unjustified_negative_adjustment_usd: float = Field(default=18500.0, ge=0.0)
    condition_discrepancy_summary: str
    model_provider: str = "vertex_ai_gemini_local_fallback"


class CensusTractAdvisory(BaseModel):
    census_tract_geoid: str
    holc_historical_grade: Literal["A", "B", "C", "D"]
    majority_demographic: str
    fhfa_undervaluation_risk_tier: str
    brookings_metro_gap_benchmark_usd: float
    rov_federal_mandate_ref: str


class SpatialValuationResult(BaseModel):
    appraised_value_usd: float
    contract_price_usd: float
    equityval_fair_value_usd: float
    estimated_undervaluation_gap_usd: float
    undervaluation_pct: float
    condition_recovery_usd: float
    comp_selection_recovery_usd: float
    bias_risk_score: int = Field(..., ge=0, le=100)
    fhfa_undervaluation_flag: bool
    evaluated_comps: List[EvaluatedComparableSale]
    nlp_flags: List[NlpFlaggedPhrase]
    vision_audit: VisionConditionAudit
    census_tract_advisory: CensusTractAdvisory
    summary_findings: List[str]


class SignedUploadUrlItem(BaseModel):
    filename: str
    blob_name: str
    upload_url: str
    method: str = "PUT"
    expires_in_minutes: int = 15
    content_type: str = "image/jpeg"
    lifecycle_auto_delete_days: int = 14


class RovAuditCreateRequest(BaseModel):
    user_id: Optional[UUID] = None
    property_address: str = Field(
        default="1428 Cascade Rd SW, Atlanta, GA 30311",
        min_length=5,
        max_length=255,
    )
    census_tract_geoid: str = Field(default="13121006100")
    subject_lat: float = Field(default=33.7254, ge=-90.0, le=90.0)
    subject_lon: float = Field(default=-84.4512, ge=-180.0, le=180.0)
    subject_gla_sqft: int = Field(default=2280, gt=300, le=20000)
    subject_bedrooms: int = Field(default=4, ge=1, le=15)
    subject_bathrooms: float = Field(default=3.0, ge=1.0, le=15.0)
    appraised_value_usd: float = Field(default=412000.0, gt=20000.0)
    contract_price_usd: float = Field(default=465000.0, gt=20000.0)
    appraiser_condition_code: str = Field(default="C4")
    appraiser_quality_code: str = Field(default="Q4")
    appraiser_Apply_Condition_Adjustment_Usd: float = Field(default=-18500.0)
    form_1004_neighborhood_commentary: str = Field(
        default=(
            "The subject property is located in a changing demographic trends area with mixed "
            "pride of ownership compared to northern districts. Several older blocks nearby show "
            "deferred maintenance and high crime perception, warranting a C4 condition rating and "
            "conservative comparable selection from the adjacent southern distressed corridor."
        )
    )
    photo_filenames: List[str] = Field(
        default_factory=lambda: [
            "front_elevation_renovated_brick.jpg",
            "kitchen_quartz_island_c3.jpg",
            "primary_bath_frameless_glass.jpg",
            "form_1004_appraisal_excerpt.pdf",
        ]
    )
    comparable_sales: Optional[List[ComparableSaleInput]] = None


class ComplianceAttestationRequest(BaseModel):
    acknowledged: bool = Field(...)
    analyst_name_or_license: str = Field(..., min_length=2, max_length=128)
    uspap_non_appraisal_verified: bool = Field(default=True)


class LenderShareApprovalRequest(BaseModel):
    reviewer_name_or_email: str = Field(..., min_length=3, max_length=128)
    approved: bool = Field(default=True)
    notes: Optional[str] = Field(default="Verified ROV comparable sales and condition adjustments.")


class RovAuditRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    property_address: str
    census_tract_geoid: str
    subject_lat: float
    subject_lon: float
    subject_gla_sqft: int
    subject_bedrooms: int
    subject_bathrooms: float
    status: str = "completed"
    form_1004_neighborhood_commentary: str
    valuation_result: SpatialValuationResult
    signed_upload_urls: List[SignedUploadUrlItem] = Field(default_factory=list)
    compliance_acknowledged: bool = False
    compliance_acknowledged_at: Optional[datetime] = None
    compliance_analyst_id: Optional[str] = None
    lender_approved: bool = False
    lender_approved_by: Optional[str] = None
    lender_approved_at: Optional[datetime] = None
    lender_notes: Optional[str] = None
    mandatory_disclaimer: str = MANDATORY_ROV_ATTESTATION_DISCLAIMER
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
