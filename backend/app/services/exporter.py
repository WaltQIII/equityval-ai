"""
Multi-Format Reconsideration of Value (ROV) Dossier Compiler for EquityVal AI.

Supports:
- `.json`: Fannie Mae / Freddie Mac / FHA Standardized ROV Compliance Dossier
- `.md`: Formal Lender-Ready Reconsideration of Value (ROV) Appeal Brief
- `.csv`: UAD Comparable Sales & Adjustment Discrepancy Audit Matrix

Every exported artifact embeds the mandatory `MANDATORY_ROV_ATTESTATION_DISCLAIMER`
to enforce Interagency ROV & USPAP Non-Appraisal regulatory compliance.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from app.models.schemas import MANDATORY_ROV_ATTESTATION_DISCLAIMER, RovAuditRecord


def export_rov_dossier_json(audit: RovAuditRecord) -> str:
    """Compile standardized Fannie Mae / Freddie Mac / FHA ROV Dossier JSON."""
    val = audit.valuation_result
    payload = {
        "schema_version": "FHFA-ROV-2026.1",
        "regulatory_disclaimer": MANDATORY_ROV_ATTESTATION_DISCLAIMER,
        "dossier_id": str(audit.id),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "compliance_attestation": {
            "acknowledged": audit.compliance_acknowledged,
            "acknowledged_at": audit.compliance_acknowledged_at.isoformat() if audit.compliance_acknowledged_at else None,
            "analyst_or_license_id": audit.compliance_analyst_id,
        },
        "subject_property": {
            "address": audit.property_address,
            "census_tract_geoid": audit.census_tract_geoid,
            "coordinates": {"lat": audit.subject_lat, "lon": audit.subject_lon},
            "gla_sqft": audit.subject_gla_sqft,
            "bedrooms": audit.subject_bedrooms,
            "bathrooms": audit.subject_bathrooms,
        },
        "valuation_disparity_summary": {
            "appraised_value_usd": val.appraised_value_usd,
            "contract_price_usd": val.contract_price_usd,
            "equityval_fair_value_usd": val.equityval_fair_value_usd,
            "estimated_undervaluation_gap_usd": val.estimated_undervaluation_gap_usd,
            "undervaluation_pct": val.undervaluation_pct,
            "condition_recovery_usd": val.condition_recovery_usd,
            "comp_selection_recovery_usd": val.comp_selection_recovery_usd,
            "bias_risk_score": val.bias_risk_score,
            "fhfa_undervaluation_flag": val.fhfa_undervaluation_flag,
        },
        "vision_uad_audit": val.vision_audit.model_dump(mode="json"),
        "nlp_prohibited_phrase_flags": [f.model_dump(mode="json") for f in val.nlp_flags],
        "evaluated_comparable_sales": [c.model_dump(mode="json") for c in val.evaluated_comps],
        "census_tract_advisory": val.census_tract_advisory.model_dump(mode="json"),
    }
    return json.dumps(payload, indent=2)


def export_rov_appeal_markdown(audit: RovAuditRecord) -> str:
    """Compile formal Lender-Ready Reconsideration of Value (ROV) Appeal Brief in Markdown."""
    val = audit.valuation_result
    lines = [
        "# FORMAL RECONSIDERATION OF VALUE (ROV) COMPLIANCE DOSSIER",
        "",
        f"> **REGULATORY COMPLIANCE NOTICE:** {MANDATORY_ROV_ATTESTATION_DISCLAIMER}",
        "",
        "## 1. Subject Property & Valuation Disparity Summary",
        f"- **Audit Case ID:** `{audit.id}`",
        f"- **Subject Property Address:** {audit.property_address}",
        f"- **Census Tract GEOID:** `{audit.census_tract_geoid}` ({val.census_tract_advisory.majority_demographic})",
        f"- **Original Appraised Value (Form 1004):** ${val.appraised_value_usd:,.2f}",
        f"- **Agreed Purchase Contract Price:** ${val.contract_price_usd:,.2f}",
        f"- **EquityVal AI Hedonic Fair Market Value:** **${val.equityval_fair_value_usd:,.2f}**",
        f"- **Quantified Undervaluation Disparity:** **+${val.estimated_undervaluation_gap_usd:,.2f} (+{val.undervaluation_pct:.1f}%)**",
        f"- **Algorithmic Bias Risk Score:** `{val.bias_risk_score}/100`",
        f"- **Compliance Analyst Attestation:** `{audit.compliance_analyst_id or 'Pending'}` at `{audit.compliance_acknowledged_at.isoformat() if audit.compliance_acknowledged_at else 'N/A'}`",
        "",
        "## 2. Multimodal Computer Vision UAD Condition & Quality Audit",
        f"- **Appraiser Assigned Rating:** `{val.vision_audit.appraiser_condition_code}` / `{val.vision_audit.appraiser_quality_code}`",
        f"- **EquityVal AI Vision Score:** `C{val.vision_audit.ai_vision_condition_score}` / `Q{val.vision_audit.ai_vision_quality_score}`",
        f"- **Unjustified Condition Adjustment Recovery:** **+${val.vision_audit.unjustified_negative_adjustment_usd:,.2f}**",
        f"- **Summary:** {val.vision_audit.condition_discrepancy_summary}",
        "- **Verified Property Upgrades:**",
    ]
    for upg in val.vision_audit.detected_upgrades:
        lines.append(f"  - {upg}")

    lines.extend([
        "",
        "## 3. FHFA / HUD Fair Housing Act Prohibited Phrase Audit (Form 1004 Narrative)",
    ])
    if not val.nlp_flags:
        lines.append("- No prohibited demographic or subjective phrases detected.")
    else:
        for flag in val.nlp_flags:
            lines.append(
                f"- **Flagged Phrase:** `\"{flag.phrase}\"` ({flag.category} | Severity: `{flag.severity.upper()}`)"
            )
            lines.append(f"  - **Citation:** {flag.regulatory_citation}")
            lines.append(f"  - **Context:** _{flag.context_snippet}_")
            lines.append(f"  - **Compliant Replacement:** {flag.recommended_neutral_replacement}")

    lines.extend([
        "",
        "## 4. Spatial Regression & Comparable Sales Audit Matrix",
        "| Comp ID | Source | Address | Distance (mi) | Sale Price | GLA (sqft) | Hedonic Adj. Value | Distressed / Boundary Flag |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for c in val.evaluated_comps:
        flags_str = "; ".join(c.audit_flags) if c.audit_flags else "Compliant"
        lines.append(
            f"| {c.comp_id} | `{c.selection_source}` | {c.address} | {c.distance_miles:.2f} mi | "
            f"${c.sale_price_usd:,.0f} | {c.gla_sqft} | **${c.hedonic_adjusted_value_usd:,.0f}** | {flags_str} |"
        )

    lines.append("")
    return "\n".join(lines)


def export_rov_comps_csv(audit: RovAuditRecord) -> str:
    """Compile UAD Comparable Sales & Adjustment Discrepancy Matrix in CSV format."""
    buf = io.StringIO()
    buf.write(f"# {MANDATORY_ROV_ATTESTATION_DISCLAIMER}\n")
    buf.write(
        f"# Property: {audit.property_address} | Audit ID: {audit.id} | "
        f"Attested By: {audit.compliance_analyst_id or 'N/A'}\n"
    )
    writer = csv.writer(buf)
    writer.writerow([
        "comp_id",
        "selection_source",
        "address",
        "distance_miles",
        "sale_price_usd",
        "gla_sqft",
        "price_per_sqft_usd",
        "condition_uad",
        "quality_uad",
        "is_distressed_or_reo",
        "crossed_redlining_boundary",
        "hedonic_adjusted_value_usd",
        "similarity_weight",
        "audit_flags",
    ])
    for c in audit.valuation_result.evaluated_comps:
        writer.writerow([
            c.comp_id,
            c.selection_source,
            c.address,
            f"{c.distance_miles:.2f}",
            f"{c.sale_price_usd:.2f}",
            c.gla_sqft,
            f"{c.price_per_sqft_usd:.2f}",
            c.condition_uad,
            c.quality_uad,
            c.is_distressed_or_reo,
            c.crossed_redlining_boundary,
            f"{c.hedonic_adjusted_value_usd:.2f}",
            f"{c.similarity_weight:.3f}",
            " | ".join(c.audit_flags),
        ])
    return buf.getvalue()
