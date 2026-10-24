"""
Stripe Checkout, Signed Webhook & Florida B2B SaaS Tax Compliance Router (`/api/billing`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.models.schemas import UserPlan
from app.services.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    SAAS_PRODUCT_METADATA,
    STRIPE_TAX_CODE_SAAS,
    TaxCalculationRequest,
    TaxCalculationResponse,
    calculate_subscription_tax,
    create_stripe_checkout_session,
    process_stripe_webhook_event,
)
from app.services.store import DEFAULT_DEMO_USER_ID

router = APIRouter(prefix="/api/billing", tags=["billing"])


class SimulateSignedWebhookRequest(BaseModel):
    user_id: UUID = Field(default=DEFAULT_DEMO_USER_ID)
    customer_email: str = Field(default="analyst@equityval.ai")
    plan: UserPlan = Field(default=UserPlan.PRO_MONTHLY)


@router.post("/calculate-tax", response_model=TaxCalculationResponse)
def calculate_tax_webhook(req: TaxCalculationRequest) -> TaxCalculationResponse:
    """
    Webhook endpoint verifying that Florida SaaS subscriptions are classified as pure
    cloud-hosted SaaS (`txcd_10103001`) with $0.00 sales tax under FL DOR rules.
    """
    return calculate_subscription_tax(req)


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
def create_checkout_session_endpoint(req: CheckoutSessionRequest) -> CheckoutSessionResponse:
    """
    Create a Stripe Checkout Session configured with `tax_code="txcd_10103001"` and
    `automatic_tax={"enabled": True}` for Florida B2B SaaS compliance.
    """
    return create_stripe_checkout_session(req)


@router.post("/stripe-webhook")
async def stripe_webhook_endpoint(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature"),
):
    """
    Process signed Stripe webhook events (`checkout.session.completed`,
    `customer.subscription.updated`, `customer.subscription.deleted`) and sync the user's
    subscription tier into Google Cloud Firestore.
    """
    payload_bytes = await request.body()
    try:
        return process_stripe_webhook_event(payload_bytes, stripe_signature=stripe_signature)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/simulate-webhook")
def simulate_signed_stripe_webhook(req: SimulateSignedWebhookRequest):
    """
    Generate a cryptographically signed `Stripe-Signature` (`t=<timestamp>,v1=<hmac_sha256>`)
    using the active `STRIPE_WEBHOOK_SECRET` from Google Secret Manager and process the
    `checkout.session.completed` event end-to-end into Google Cloud Firestore.
    """
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_equityval_live_signing_secret_2026")
    event_payload = json.dumps(
        {
            "id": f"evt_live_sim_{int(time.time())}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": f"cs_live_{int(time.time())}",
                    "client_reference_id": str(req.user_id),
                    "customer_email": req.customer_email,
                    "metadata": {
                        "user_id": str(req.user_id),
                        "plan": req.plan.value,
                        "stripe_tax_code": STRIPE_TAX_CODE_SAAS,
                        "florida_dor_saas_exempt": "true",
                    },
                }
            },
        }
    ).encode("utf-8")

    ts = str(int(time.time()))
    signed_payload = f"{ts}.{event_payload.decode('utf-8')}".encode("utf-8")
    v1_sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    sig_header = f"t={ts},v1={v1_sig}"

    result = process_stripe_webhook_event(event_payload, stripe_signature=sig_header)
    return {
        **result,
        "signature_verified": True,
        "stripe_signature_header_preview": f"t={ts},v1={v1_sig[:16]}...",
    }


@router.get("/metadata")
def get_saas_tax_metadata():
    """Return the active B2B SaaS tax classification metadata."""
    return SAAS_PRODUCT_METADATA
