"""
Appraisal Bias & Reconsideration of Value (ROV) Audit Router (`/api/audits`).

Implements:
- `POST /api/audits/create`: Run spatial regression, NLP Form 1004 prohibited-phrase detection,
  Gemini Vision UAD condition/quality scoring, and GCS V4 Signed URL generation, persisted to Firestore.
- `GET /api/audits`: List all ROV audits.
- `GET /api/audits/{audit_id}`: Retrieve a specific ROV audit record.
- `POST /api/audits/{audit_id}/acknowledge-compliance`: Record mandatory Interagency ROV & USPAP
  compliance attestation before unlocking official ROV dossier exports.
- `GET /api/audits/{audit_id}/export/{fmt}`: Export `.json`, `.md`, or `.csv` ROV Appeal Dossiers.
- `GET /api/audits/{audit_id}/share` & `POST /api/audits/{audit_id}/lender-approve`: Shareable
  read-only review link and lender/underwriter sign-off workflow.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Response, status

from app.api.uploads import generate_batch_signed_urls
from app.models.schemas import (
    ComplianceAttestationRequest,
    LenderShareApprovalRequest,
    RovAuditCreateRequest,
    RovAuditRecord,
)
from app.services.exporter import (
    export_rov_appeal_markdown,
    export_rov_comps_csv,
    export_rov_dossier_json,
)
from app.services.rov_engine import execute_rov_valuation_audit
from app.services.store import DEFAULT_DEMO_USER_ID, db_store

router = APIRouter(prefix="/api/audits", tags=["audits"])


@router.post("/create", response_model=RovAuditRecord, status_code=status.HTTP_201_CREATED)
def create_rov_audit(req: RovAuditCreateRequest) -> RovAuditRecord:
    """
    Execute an Algorithmic Real Estate Appraisal Bias & Reconsideration of Value (ROV) Audit
    and persist the resulting record to Google Cloud Firestore.
    """
    audit_id = uuid4()
    owner_id = req.user_id or DEFAULT_DEMO_USER_ID
    valuation_result = execute_rov_valuation_audit(req)
    signed_urls = generate_batch_signed_urls(
        filenames=req.photo_filenames,
        audit_id=str(audit_id),
    )

    record = RovAuditRecord(
        id=audit_id,
        user_id=owner_id,
        property_address=req.property_address,
        census_tract_geoid=req.census_tract_geoid,
        subject_lat=req.subject_lat,
        subject_lon=req.subject_lon,
        subject_gla_sqft=req.subject_gla_sqft,
        subject_bedrooms=req.subject_bedrooms,
        subject_bathrooms=req.subject_bathrooms,
        form_1004_neighborhood_commentary=req.form_1004_neighborhood_commentary,
        valuation_result=valuation_result,
        signed_upload_urls=signed_urls,
        compliance_acknowledged=False,
        compliance_acknowledged_at=None,
    )
    return db_store.save_audit(record)


@router.get("", response_model=List[RovAuditRecord])
def list_rov_audits(user_id: Optional[UUID] = None) -> List[RovAuditRecord]:
    """List saved ROV property audits from Firestore / in-memory store."""
    return db_store.list_audits(user_id=user_id)


@router.get("/{audit_id}", response_model=RovAuditRecord)
def get_rov_audit(audit_id: UUID) -> RovAuditRecord:
    """Retrieve a single ROV property audit by UUID."""
    audit = db_store.get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ROV Audit not found.")
    return audit


@router.post("/{audit_id}/acknowledge-compliance", response_model=RovAuditRecord)
def acknowledge_rov_compliance(audit_id: UUID, req: ComplianceAttestationRequest) -> RovAuditRecord:
    """
    Record an immutable Interagency ROV & USPAP Non-Appraisal compliance attestation in Firestore,
    unlocking official lender-ready ROV Appeal Dossier downloads.
    """
    audit = db_store.get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ROV Audit not found.")
    if not req.acknowledged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compliance attestation checkbox must be explicitly acknowledged.",
        )

    now_utc = datetime.now(timezone.utc)
    audit.compliance_acknowledged = True
    audit.compliance_acknowledged_at = now_utc
    audit.compliance_analyst_id = req.analyst_name_or_license.strip()
    db_store.save_audit(audit)

    db_store.log_rov_compliance_event(
        audit_id=audit.id,
        user_id=audit.user_id,
        analyst_name_or_license=audit.compliance_analyst_id,
        uspap_non_appraisal_verified=req.uspap_non_appraisal_verified,
        acknowledged_at=now_utc,
    )
    return audit


@router.get("/{audit_id}/export/{fmt}")
def export_rov_dossier(
    audit_id: UUID,
    fmt: Literal["json", "md", "csv"],
) -> Response:
    """
    Export the ROV Appeal Dossier in `.json`, `.md`, or `.csv` format.
    Blocks `.md` and `.csv` lender-submission exports with HTTP 403 until the mandatory
    Interagency ROV & USPAP compliance attestation is completed.
    """
    audit = db_store.get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ROV Audit not found.")

    if fmt in ("md", "csv") and not audit.compliance_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Export blocked: You must complete the Mandatory Interagency ROV & USPAP "
                "Regulatory Compliance Attestation before downloading official lender submission dossiers."
            ),
        )

    if fmt == "json":
        content = export_rov_dossier_json(audit)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="equityval_rov_{audit_id}.json"'},
        )
    if fmt == "md":
        content = export_rov_appeal_markdown(audit)
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="equityval_rov_appeal_{audit_id}.md"'},
        )

    content = export_rov_comps_csv(audit)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="equityval_uad_comps_{audit_id}.csv"'},
    )


@router.get("/{audit_id}/share")
def get_shareable_rov_summary(audit_id: UUID):
    """Return read-only shareable ROV dossier summary for mortgage underwriters & borrowers."""
    audit = db_store.get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ROV Audit not found.")
    return {
        "audit_id": str(audit.id),
        "property_address": audit.property_address,
        "census_tract_geoid": audit.census_tract_geoid,
        "appraised_value_usd": audit.valuation_result.appraised_value_usd,
        "equityval_fair_value_usd": audit.valuation_result.equityval_fair_value_usd,
        "estimated_undervaluation_gap_usd": audit.valuation_result.estimated_undervaluation_gap_usd,
        "bias_risk_score": audit.valuation_result.bias_risk_score,
        "lender_approved": audit.lender_approved,
        "lender_approved_by": audit.lender_approved_by,
        "lender_approved_at": audit.lender_approved_at.isoformat() if audit.lender_approved_at else None,
        "mandatory_disclaimer": audit.mandatory_disclaimer,
    }


@router.post("/{audit_id}/lender-approve", response_model=RovAuditRecord)
def approve_rov_by_lender(audit_id: UUID, req: LenderShareApprovalRequest) -> RovAuditRecord:
    """Record underwriter / lender approval of the Reconsideration of Value (ROV) appeal."""
    audit = db_store.get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ROV Audit not found.")
    audit.lender_approved = req.approved
    audit.lender_approved_by = req.reviewer_name_or_email.strip()
    audit.lender_approved_at = datetime.now(timezone.utc)
    audit.lender_notes = req.notes
    return db_store.save_audit(audit)
