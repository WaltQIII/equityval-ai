"""
Google Cloud Firestore + In-Memory Fallback Repository Store for EquityVal AI.

Implements serverless, zero-idle-cost persistence on Google Cloud Firestore:
- Collection `users`: id (UUID), email, full_name, license_or_nmls_id, plan, created_at
- Collection `audits`: id (UUID), user_id, property_address, valuation_result, signed_upload_urls,
  compliance_acknowledged, compliance_acknowledged_at
- Collection `compliance_audit_logs`: immutable Interagency ROV & USPAP compliance acceptance logs

Automatically uses `google.cloud.firestore.Client` in GCP / Cloud Run environments (or when
injected in unit tests) and falls back to local in-memory storage when running offline without
GCP credentials.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from google.cloud import firestore

from app.models.schemas import (
    RovAuditRecord,
    UserPlan,
    UserRecord,
)

DEFAULT_DEMO_USER_ID = UUID("00000000-0000-4000-8000-000000000001")


class FirestoreDatabaseStore:
    def __init__(self, firestore_client: Optional[firestore.Client] = None) -> None:
        self._injected_client = firestore_client
        self.users: Dict[UUID, UserRecord] = {}
        self.audits: Dict[UUID, RovAuditRecord] = {}
        self.compliance_audit_logs: List[Dict[str, Any]] = []
        self._seed_default_user()

    def _get_firestore_client(self) -> Optional[firestore.Client]:
        if self._injected_client is not None:
            return self._injected_client
        force_mock = (
            os.getenv("EQUITYVAL_USE_MOCK_FIRESTORE", "false").lower() in ("1", "true", "yes")
            or os.getenv("SKYSIM_USE_MOCK_FIRESTORE", "false").lower() in ("1", "true", "yes")
        )
        has_gcp_creds = bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("K_SERVICE"))
        if has_gcp_creds and not force_mock:
            try:
                project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
                return firestore.Client(project=project_id)
            except Exception:
                return None
        return None

    def _seed_default_user(self) -> None:
        self.users[DEFAULT_DEMO_USER_ID] = UserRecord(
            id=DEFAULT_DEMO_USER_ID,
            email="analyst@equityval.ai",
            full_name="Lead Fair Lending & ROV Auditor",
            license_or_nmls_id="NMLS-ROV-884120",
            plan=UserPlan.PRO_MONTHLY,
            created_at=datetime.now(timezone.utc),
        )

    def upsert_user(self, user: UserRecord) -> UserRecord:
        self.users[user.id] = user
        fs = self._get_firestore_client()
        if fs is not None:
            try:
                fs.collection("users").document(str(user.id)).set(
                    user.model_dump(mode="json"), merge=True
                )
            except Exception:
                if self._injected_client is not None:
                    raise
        return user

    def get_user(self, user_id: UUID) -> Optional[UserRecord]:
        fs = self._get_firestore_client()
        if fs is not None:
            try:
                doc = fs.collection("users").document(str(user_id)).get()
                if doc.exists:
                    data = doc.to_dict()
                    if data:
                        return UserRecord(**data)
            except Exception:
                if self._injected_client is not None:
                    raise
        return self.users.get(user_id)

    def get_user_by_email(self, email: str) -> Optional[UserRecord]:
        email_norm = email.strip().lower()
        for u in self.users.values():
            if u.email.lower() == email_norm:
                return u
        fs = self._get_firestore_client()
        if fs is not None:
            try:
                docs = fs.collection("users").where("email", "==", email_norm).limit(1).stream()
                for d in docs:
                    data = d.to_dict()
                    if data:
                        user = UserRecord(**data)
                        self.users[user.id] = user
                        return user
            except Exception:
                if self._injected_client is not None:
                    raise
        return None

    def update_user_plan(self, user_id: UUID, new_plan: UserPlan, email: Optional[str] = None) -> UserRecord:
        user = self.get_user(user_id)
        if user is None:
            user = UserRecord(
                id=user_id,
                email=email or "customer@equityval.ai",
                plan=new_plan,
                created_at=datetime.now(timezone.utc),
            )
        else:
            user.plan = new_plan
            if email:
                user.email = email
        return self.upsert_user(user)

    def save_audit(self, audit: RovAuditRecord) -> RovAuditRecord:
        self.audits[audit.id] = audit
        fs = self._get_firestore_client()
        if fs is not None:
            try:
                fs.collection("audits").document(str(audit.id)).set(
                    audit.model_dump(mode="json")
                )
            except Exception:
                if self._injected_client is not None:
                    raise
        return audit

    def get_audit(self, audit_id: UUID) -> Optional[RovAuditRecord]:
        fs = self._get_firestore_client()
        if fs is not None:
            try:
                doc = fs.collection("audits").document(str(audit_id)).get()
                if doc.exists:
                    data = doc.to_dict()
                    if data:
                        return RovAuditRecord(**data)
            except Exception:
                if self._injected_client is not None:
                    raise
        return self.audits.get(audit_id)

    def list_audits(self, user_id: Optional[UUID] = None) -> List[RovAuditRecord]:
        fs = self._get_firestore_client()
        if fs is not None:
            try:
                query: Any = fs.collection("audits")
                if user_id is not None:
                    query = query.where("user_id", "==", str(user_id))
                results = []
                for doc in query.stream():
                    data = doc.to_dict()
                    if data:
                        results.append(RovAuditRecord(**data))
                if results:
                    return results
            except Exception:
                if self._injected_client is not None:
                    raise

        all_audits = list(self.audits.values())
        if user_id is not None:
            return [a for a in all_audits if a.user_id == user_id]
        return all_audits

    def log_rov_compliance_event(
        self,
        audit_id: UUID,
        user_id: UUID,
        analyst_name_or_license: str,
        uspap_non_appraisal_verified: bool,
        acknowledged_at: datetime,
    ) -> Dict[str, Any]:
        """Record an immutable Interagency ROV & USPAP compliance attestation in Firestore."""
        entry = {
            "audit_id": str(audit_id),
            "user_id": str(user_id),
            "analyst_name_or_license": analyst_name_or_license,
            "uspap_non_appraisal_verified": uspap_non_appraisal_verified,
            "acknowledged_at": acknowledged_at.isoformat(),
            "regulatory_notice": "FHFA / Fannie Mae / Freddie Mac / HUD Interagency ROV & USPAP Compliance Attested",
        }
        self.compliance_audit_logs.append(entry)
        fs = self._get_firestore_client()
        if fs is not None:
            try:
                fs.collection("compliance_audit_logs").document(
                    f"{audit_id}_{int(acknowledged_at.timestamp())}"
                ).set(entry)
            except Exception:
                if self._injected_client is not None:
                    raise
        return entry


db_store = FirestoreDatabaseStore()
