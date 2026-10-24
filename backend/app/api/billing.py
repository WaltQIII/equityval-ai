"""
Stripe Checkout, Signed Webhook & Florida B2B SaaS Tax Compliance Router (`/api/billing`).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.services.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    SAAS_PRODUCT_METADATA,
    TaxCalculationRequest,
    TaxCalculationResponse,
    calculate_subscription_tax,
    create_stripe_checkout_session,
    process_stripe_webhook_event,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])


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


@router.get("/metadata")
def get_saas_tax_metadata():
    """Return the active B2B SaaS tax classification metadata."""
    return SAAS_PRODUCT_METADATA
