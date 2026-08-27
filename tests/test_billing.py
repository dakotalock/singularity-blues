from types import SimpleNamespace

from orchestrator.billing import create_checkout_session, handle_webhook
from orchestrator.credits import balance, reset_sqlite_for_tests


class _FakeSession:
    id = "cs_test"
    url = "https://checkout.stripe.com/c/test"


class _FakeSessions:
    last = None

    def create(self, params):
        _FakeSessions.last = params
        assert "payment_method_types" not in params
        assert "automatic_tax" not in params
        return _FakeSession()


class _FakeClient:
    def __init__(self):
        self.v1 = SimpleNamespace(checkout=SimpleNamespace(sessions=_FakeSessions()))

    def construct_event(self, payload, sig_header, secret):
        obj = SimpleNamespace(
            metadata={"buyer_id": "buyerZ", "bundle": "5"},
            client_reference_id="buyerZ",
        )
        return SimpleNamespace(
            type="checkout.session.completed",
            id="evt_test_1",
            data=SimpleNamespace(object=obj),
        )


def test_checkout_uses_stripeclient_without_payment_method_types(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_PRICE_5", "price_1U8uTGP7GC34loHeXOgvN3rn")
    monkeypatch.setattr("orchestrator.billing.get_stripe_client", lambda: _FakeClient())
    _FakeSessions.last = None
    out = create_checkout_session(
        buyer_id="buyerZ",
        bundle="5",
        success_url="https://example.test/ok",
        cancel_url="https://example.test/no",
    )
    assert out["url"].startswith("https://checkout.stripe.com/")
    params = _FakeSessions.last
    assert params["mode"] == "payment"
    assert params["line_items"][0]["price"] == "price_1U8uTGP7GC34loHeXOgvN3rn"
    assert "payment_method_types" not in params
    assert "automatic_tax" not in params


def test_webhook_grants_bundle(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CREDITS_SQLITE_PATH", str(tmp_path / "credits.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
    reset_sqlite_for_tests()
    monkeypatch.setattr("orchestrator.billing.get_stripe_client", lambda: _FakeClient())
    result = handle_webhook(b"{}", "t=1,v1=sig")
    assert result["ok"] is True
    assert result["granted"] is True
    assert result["credits"] == 5
    assert result["ltm_pins"] == 1
    assert balance("buyerZ")["credits"] == 5
