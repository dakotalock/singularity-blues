"""Hosted Stripe Checkout Sessions for prompt-credit bundles."""

from __future__ import annotations

import os
from typing import Any

from orchestrator.credits import BUNDLES, grant_bundle, stripe_configured


def get_stripe_client():
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        return None
    from stripe import StripeClient

    return StripeClient(key)


def price_id_for(bundle: str) -> str:
    spec = BUNDLES.get(bundle) or {}
    env_name = spec.get("price_env") or ""
    return os.environ.get(env_name, "").strip() if env_name else ""


def create_checkout_session(
    *,
    buyer_id: str,
    bundle: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    if bundle not in BUNDLES:
        raise ValueError("unknown bundle")
    client = get_stripe_client()
    if client is None:
        raise RuntimeError("stripe unset")
    price = price_id_for(bundle)
    if not price:
        raise RuntimeError("price unset")
    spec = BUNDLES[bundle]
    # Hosted Checkout. Never pass payment_method_types. No automatic_tax.
    params = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": [{"price": price, "quantity": 1}],
        "client_reference_id": buyer_id,
        "metadata": {
            "buyer_id": buyer_id,
            "bundle": bundle,
            "credits": str(spec["credits"]),
            "ltm_pins": str(spec["pins"]),
        },
    }
    session = client.v1.checkout.sessions.create(params)
    return {"id": getattr(session, "id", None), "url": getattr(session, "url", None)}


def _meta(obj: Any) -> dict[str, str]:
    if obj is None:
        return {}
    raw = getattr(obj, "metadata", None)
    if raw is None and isinstance(obj, dict):
        raw = obj.get("metadata")
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v is not None}
    try:
        return {str(k): str(v) for k, v in dict(raw).items() if v is not None}
    except Exception:
        return {}


def _event_field(event: Any, name: str) -> Any:
    if isinstance(event, dict):
        return event.get(name)
    return getattr(event, name, None)


def handle_webhook(payload: bytes | str, sig_header: str) -> dict[str, Any]:
    """Verify signature and grant the bundle on checkout.session.completed."""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise RuntimeError("webhook secret unset")
    client = get_stripe_client()
    if client is None:
        raise RuntimeError("stripe unset")
    event = client.construct_event(payload, sig_header or "", secret)
    etype = _event_field(event, "type")
    eid = _event_field(event, "id")
    if etype != "checkout.session.completed":
        return {"ok": True, "ignored": True, "type": etype}
    data = _event_field(event, "data")
    obj = getattr(data, "object", None) if data is not None else None
    if obj is None and isinstance(data, dict):
        obj = data.get("object")
    metadata = _meta(obj)
    buyer_id = metadata.get("buyer_id") or ""
    if not buyer_id and obj is not None:
        buyer_id = str(getattr(obj, "client_reference_id", None) or (obj.get("client_reference_id") if isinstance(obj, dict) else "") or "")
    bundle = metadata.get("bundle") or ""
    if not buyer_id or bundle not in BUNDLES:
        return {"ok": False, "error": "missing metadata"}
    result = grant_bundle(buyer_id, bundle, event_id=str(eid or ""))
    return {"ok": True, "buyer_id": buyer_id, "bundle": bundle, **result}


def publishable_key() -> str:
    return os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()


__all__ = [
    "create_checkout_session",
    "get_stripe_client",
    "handle_webhook",
    "price_id_for",
    "publishable_key",
    "stripe_configured",
]
