"""Integration tests for GCS V4 Signed URLs + 14-Day Lifecycle, ROV Audits API, Firestore, Auth, and Stripe Tax."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.uploads import generate_signed_upload_url
from app.main import app
from app.models.schemas import MANDATORY_ROV_ATTESTATION_DISCLAIMER, UserPlan, UserRecord
from app.services.store import FirestoreDatabaseStore

client = TestClient(app)


def test_generate_signed_upload_url_with_gcs_sdk_mock():
    mock_storage_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = (
        "https://storage.googleapis.com/equityval-bucket/photo.jpg?X-Goog-Signature=mock123"
    )
    mock_bucket.blob.return_value = mock_blob
    mock_storage_client.bucket.return_value = mock_bucket

    url = generate_signed_upload_url(
        bucket_name="equityval-bucket",
        blob_name="audits/123/photo.jpg",
        expiration=15,
        content_type="image/jpeg",
        storage_client=mock_storage_client,
    )

    assert url == "https://storage.googleapis.com/equityval-bucket/photo.jpg?X-Goog-Signature=mock123"
    mock_storage_client.bucket.assert_called_once_with("equityval-bucket")
    mock_bucket.blob.assert_called_once_with("audits/123/photo.jpg")
    mock_blob.generate_signed_url.assert_called_once_with(
        version="v4",
        expiration=timedelta(minutes=15),
        method="PUT",
        content_type="image/jpeg",
    )


def test_generate_signed_upload_url_local_fallback_and_14_day_lifecycle():
    url = generate_signed_upload_url(
        bucket_name="equityval-ai-raw-uploads",
        blob_name="audits/demo/kitchen_quartz.jpg",
        expiration=15,
    )
    assert url.startswith(
        "https://storage.googleapis.com/equityval-ai-raw-uploads/audits/demo/kitchen_quartz.jpg"
    )
    assert "X-Goog-Algorithm=GOOG4-RSA-SHA256" in url
    assert "X-Goog-Expires=900" in url

    lifecycle_resp = client.get("/api/uploads/lifecycle-policy")
    assert lifecycle_resp.status_code == 200
    rule = lifecycle_resp.json()["lifecycle"]["rule"][0]
    assert rule["action"]["type"] == "Delete"
    assert rule["condition"]["age"] == 14


def test_rov_audit_lifecycle_and_compliance_attestation_shield():
    payload = {
        "property_address": "1428 Cascade Rd SW, Atlanta, GA 30311",
        "census_tract_geoid": "13121006100",
        "subject_lat": 33.7254,
        "subject_lon": -84.4512,
        "subject_gla_sqft": 2280,
        "appraised_value_usd": 412000.0,
        "contract_price_usd": 465000.0,
        "appraiser_condition_code": "C4",
        "appraiser_quality_code": "Q4",
        "photo_filenames": ["front_elevation.jpg", "kitchen_quartz.jpg"],
    }
    resp = client.post("/api/audits/create", json=payload)
    assert resp.status_code == 201
    audit = resp.json()
    audit_id = audit["id"]

    assert audit["property_address"] == "1428 Cascade Rd SW, Atlanta, GA 30311"
    assert audit["status"] == "completed"
    assert len(audit["signed_upload_urls"]) == 2
    assert audit["signed_upload_urls"][0]["method"] == "PUT"
    assert audit["signed_upload_urls"][0]["lifecycle_auto_delete_days"] == 14
    assert audit["valuation_result"]["estimated_undervaluation_gap_usd"] > 0
    assert audit["compliance_acknowledged"] is False
    assert audit["compliance_acknowledged_at"] is None

    # Attempting to export .md or .csv BEFORE compliance attestation must be blocked (403)
    for fmt in ("md", "csv"):
        exp_blocked = client.get(f"/api/audits/{audit_id}/export/{fmt}")
        assert exp_blocked.status_code == 403

    # Acknowledge Interagency ROV & USPAP compliance shield
    ack_resp = client.post(
        f"/api/audits/{audit_id}/acknowledge-compliance",
        json={
            "acknowledged": True,
            "analyst_name_or_license": "NMLS-ROV-884120",
            "uspap_non_appraisal_verified": True,
        },
    )
    assert ack_resp.status_code == 200
    acked = ack_resp.json()
    assert acked["compliance_acknowledged"] is True
    assert acked["compliance_acknowledged_at"] is not None

    # Now exports succeed and include the mandatory ROV disclaimer
    md_resp = client.get(f"/api/audits/{audit_id}/export/md")
    assert md_resp.status_code == 200
    assert MANDATORY_ROV_ATTESTATION_DISCLAIMER in md_resp.text

    csv_resp = client.get(f"/api/audits/{audit_id}/export/csv")
    assert csv_resp.status_code == 200
    assert MANDATORY_ROV_ATTESTATION_DISCLAIMER in csv_resp.text

    json_resp = client.get(f"/api/audits/{audit_id}/export/json")
    assert json_resp.status_code == 200
    assert MANDATORY_ROV_ATTESTATION_DISCLAIMER in json_resp.text


def test_health_check_and_fail_closed_quota(monkeypatch):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["healthy"] is True
    assert resp.json()["cloud_run_max_instances"] == 3

    monkeypatch.setenv("EQUITYVAL_FAIL_CLOSED_QUOTA", "true")
    resp_closed = client.get("/api/health")
    assert resp_closed.status_code == 503
    assert resp_closed.json()["healthy"] is False
    assert resp_closed.json()["mode"] == "fail_closed"


def test_florida_b2b_saas_tax_exemption():
    resp = client.post(
        "/api/billing/calculate-tax",
        json={
            "customer_email": "compliance@miamicdfi.org",
            "plan": "pro_monthly",
            "billing_state": "FL",
            "billing_country": "US",
            "postal_code": "33131",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tax_rate"] == 0.0
    assert data["tax_amount_cents"] == 0
    assert data["total_cents"] == data["subtotal_cents"]
    assert data["product_metadata"]["product_classification"] == "cloud_hosted_saas"
    assert data["product_metadata"]["tangible_personal_property_transferred"] is False
    assert data["product_metadata"]["florida_dor_saas_exempt"] is True
    assert data["product_metadata"]["stripe_tax_code"] == "txcd_10103001"


def test_firestore_persistence_with_mock_client():
    mock_fs = MagicMock()
    store = FirestoreDatabaseStore(firestore_client=mock_fs)

    user = UserRecord(id=uuid4(), email="firestore_analyst@equityval.ai", plan=UserPlan.PRO_MONTHLY)
    store.upsert_user(user)
    mock_fs.collection.assert_called_with("users")

    log_entry = store.log_rov_compliance_event(
        audit_id=uuid4(),
        user_id=user.id,
        analyst_name_or_license="NMLS-FS-901",
        uspap_non_appraisal_verified=True,
        acknowledged_at=datetime.now(timezone.utc),
    )
    assert log_entry["analyst_name_or_license"] == "NMLS-FS-901"
    mock_fs.collection.assert_called_with("compliance_audit_logs")


def test_stripe_checkout_session_and_signed_webhook(monkeypatch):
    uid = str(uuid4())
    checkout_resp = client.post(
        "/api/billing/checkout-session",
        json={
            "user_id": uid,
            "customer_email": "lender@equityval.ai",
            "plan": "enterprise",
            "billing_state": "FL",
        },
    )
    assert checkout_resp.status_code == 200
    cs = checkout_resp.json()
    assert cs["session_id"].startswith("cs_test_")
    assert cs["stripe_tax_code"] == "txcd_10103001"
    assert cs["automatic_tax_enabled"] is True
    assert cs["amount_tax_cents"] == 0
    assert cs["amount_total_cents"] == 250000

    webhook_secret = "whsec_test_secret_key_equityval"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", webhook_secret)

    event_payload = json.dumps(
        {
            "id": "evt_test_equityval_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": cs["session_id"],
                    "client_reference_id": uid,
                    "customer_email": "lender@equityval.ai",
                    "metadata": {
                        "user_id": uid,
                        "plan": "enterprise",
                        "stripe_tax_code": "txcd_10103001",
                    },
                }
            },
        }
    ).encode("utf-8")

    ts = str(int(time.time()))
    signed_str = f"{ts}.{event_payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(webhook_secret.encode("utf-8"), signed_str, hashlib.sha256).hexdigest()
    stripe_sig_header = f"t={ts},v1={sig}"

    wh_resp = client.post(
        "/api/billing/stripe-webhook",
        content=event_payload,
        headers={"Stripe-Signature": stripe_sig_header},
    )
    assert wh_resp.status_code == 200
    wh_data = wh_resp.json()
    assert wh_data["status"] == "processed"
    assert wh_data["updated_plan"] == "enterprise"

    bad_resp = client.post(
        "/api/billing/stripe-webhook",
        content=event_payload,
        headers={"Stripe-Signature": f"t={ts},v1=deadbeef"},
    )
    assert bad_resp.status_code == 400


def test_user_register_login_and_lender_share_approval():
    unique_email = f"analyst_{uuid4().hex[:8]}@equityval.ai"
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "email": unique_email,
            "password": "SecureRovPassword2026!",
            "full_name": "Walter Quarles, Chief ROV Auditor",
            "license_or_nmls_id": "NMLS-ROV-77412",
        },
    )
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    token = reg_data["access_token"]
    assert token.startswith("equityval-token-")
    assert reg_data["user"]["email"] == unique_email

    login_resp = client.post(
        "/api/auth/login",
        json={"email": unique_email, "password": "SecureRovPassword2026!"},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["access_token"] == token

    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == unique_email

    # Create audit and test lender approval share flow
    create_resp = client.post("/api/audits/create", json={"property_address": "890 NW 62nd St, Miami, FL 33150"})
    assert create_resp.status_code == 201
    audit_id = create_resp.json()["id"]

    share_resp = client.get(f"/api/audits/{audit_id}/share")
    assert share_resp.status_code == 200
    assert share_resp.json()["lender_approved"] is False

    approve_resp = client.post(
        f"/api/audits/{audit_id}/lender-approve",
        json={
            "reviewer_name_or_email": "underwriting@cdfi-lender.org",
            "approved": True,
            "notes": "ROV accepted; appraisal adjusted to $467,200 based on ROV-ALT-1 through ROV-ALT-3.",
        },
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["lender_approved"] is True
    assert approve_resp.json()["lender_approved_by"] == "underwriting@cdfi-lender.org"
