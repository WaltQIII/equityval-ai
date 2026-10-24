"""Unit tests for the Multi-Format Reconsideration of Value (ROV) Dossier Exporter."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from app.models.schemas import (
    MANDATORY_ROV_ATTESTATION_DISCLAIMER,
    RovAuditCreateRequest,
    RovAuditRecord,
)
from app.services.exporter import (
    export_rov_appeal_markdown,
    export_rov_comps_csv,
    export_rov_dossier_json,
)
from app.services.rov_engine import execute_rov_valuation_audit


def _build_sample_audit_record() -> RovAuditRecord:
    req = RovAuditCreateRequest()
    val = execute_rov_valuation_audit(req)
    return RovAuditRecord(
        id=uuid4(),
        user_id=uuid4(),
        property_address=req.property_address,
        census_tract_geoid=req.census_tract_geoid,
        subject_lat=req.subject_lat,
        subject_lon=req.subject_lon,
        subject_gla_sqft=req.subject_gla_sqft,
        subject_bedrooms=req.subject_bedrooms,
        subject_bathrooms=req.subject_bathrooms,
        form_1004_neighborhood_commentary=req.form_1004_neighborhood_commentary,
        valuation_result=val,
        compliance_acknowledged=True,
        compliance_acknowledged_at=datetime.now(timezone.utc),
        compliance_analyst_id="NMLS-ROV-884120",
    )


def test_export_rov_dossier_json_contains_disclaimer_and_schema():
    record = _build_sample_audit_record()
    raw_json = export_rov_dossier_json(record)
    parsed = json.loads(raw_json)
    assert parsed["regulatory_disclaimer"] == MANDATORY_ROV_ATTESTATION_DISCLAIMER
    assert parsed["subject_property"]["address"] == record.property_address
    assert parsed["valuation_disparity_summary"]["estimated_undervaluation_gap_usd"] > 0


def test_export_rov_appeal_markdown_embeds_disclaimer_and_tables():
    record = _build_sample_audit_record()
    md = export_rov_appeal_markdown(record)
    assert MANDATORY_ROV_ATTESTATION_DISCLAIMER in md
    assert "FORMAL RECONSIDERATION OF VALUE (ROV) COMPLIANCE DOSSIER" in md
    assert "ROV-ALT-1 (EquityVal)" in md


def test_export_rov_comps_csv_embeds_disclaimer_and_rows():
    record = _build_sample_audit_record()
    csv_text = export_rov_comps_csv(record)
    assert MANDATORY_ROV_ATTESTATION_DISCLAIMER in csv_text
    lines = [line for line in csv_text.strip().splitlines() if not line.startswith("#")]
    assert len(lines) == 7  # 1 header + 6 comps
