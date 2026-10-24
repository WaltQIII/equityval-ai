"""
EquityVal AI FastAPI Backend Entrypoint.

Includes:
- Algorithmic Real Estate Appraisal Bias & Reconsideration of Value (ROV) Engine (`/api/audits`, `/api/rov/evaluate`)
- Direct-to-GCS V4 Signed URL Upload Pipeline + 14-Day Auto-Deletion Lifecycle Rule (`/api/uploads`)
- Firestore-Backed Authentication with PBKDF2-HMAC-SHA256 & Signed Bearer Tokens (`/api/auth`)
- Stripe Checkout + Signed Webhooks + Florida B2B SaaS Tax Exemption (`txcd_10103001`) (`/api/billing`)
- Fail-Closed $100/Month GCP Budget & Quota Circuit Breaker (`/health` & `/api/health`)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.audits import router as audits_router
from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.uploads import router as uploads_router
from app.models.schemas import RovAuditCreateRequest, SpatialValuationResult
from app.services.quota_guard import quota_guard
from app.services.rov_engine import execute_rov_valuation_audit

app = FastAPI(
    title="EquityVal AI API",
    description=(
        "Algorithmic Real Estate Appraisal Bias & Reconsideration of Value (ROV) Auditor — "
        "NLP Form 1004 Compliance, Gemini Vision UAD Condition Scoring, and Spatial Hedonic Regression"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(audits_router)
app.include_router(uploads_router)
app.include_router(billing_router)


@app.get("/")
def root_api_index():
    """Root API index providing service metadata, active guardrails, and documentation links."""
    return {
        "service": "EquityVal AI — Algorithmic Real Estate Appraisal Bias & ROV Auditor API",
        "venture": "Venture 2: EquityVal Audit Protocol ($48k Appraisal Gap & FHFA ROV Compliance Engine)",
        "version": "1.0.0",
        "status": "online",
        "frontend_dashboard_url": "http://localhost:3000",
        "interactive_docs_url": "http://localhost:8000/docs",
        "openapi_schema_url": "http://localhost:8000/openapi.json",
        "health_check_url": "http://localhost:8000/api/health",
        "endpoints": {
            "audits": "/api/audits",
            "rov_evaluate": "/api/rov/evaluate",
            "gcs_signed_uploads": "/api/uploads/signed-url",
            "gcs_lifecycle_policy": "/api/uploads/lifecycle-policy",
            "auth_register": "/api/auth/register",
            "auth_login": "/api/auth/login",
            "auth_profile": "/api/auth/me",
            "stripe_checkout": "/api/billing/checkout-session",
            "florida_saas_tax": "/api/billing/calculate-tax",
        },
    }


@app.get("/health")
@app.get("/api/health")
def health_check():
    """
    Health check endpoint that monitors GCP API quotas and the $100 monthly budget cap.
    Fails closed (HTTP 503) if API quotas approach or exceed hard limits.
    """
    status_report = quota_guard.evaluate_status()
    if not status_report["healthy"]:
        return JSONResponse(status_code=503, content=status_report)
    return status_report


@app.post("/api/rov/evaluate", response_model=SpatialValuationResult, tags=["rov-engine"])
def evaluate_rov_direct_endpoint(req: RovAuditCreateRequest) -> SpatialValuationResult:
    """Directly compute spatial hedonic valuation, NLP prohibited-phrase flags, and UAD vision scores."""
    quota_guard.enforce_quota_or_fail_closed()
    return execute_rov_valuation_audit(req)
