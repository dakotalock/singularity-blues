from orchestrator.credits import (
    balance,
    buyer_for_recovery_key,
    ensure_recovery_key,
    grant_bundle,
    refund_credit,
    refund_pin,
    reset_sqlite_for_tests,
    spend_credit,
    spend_pin,
)


def _iso(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CREDITS_SQLITE_PATH", str(tmp_path / "credits.db"))
    reset_sqlite_for_tests()


def test_hard_reject_refunds_credit_not_money(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    grant_bundle("buyer1", "1")
    assert balance("buyer1")["credits"] == 1
    assert spend_credit("buyer1", 1) is True
    assert balance("buyer1")["credits"] == 0
    # Hard-reject path: put the credit back. Never a Stripe refund.
    refund_credit("buyer1", 1)
    assert balance("buyer1")["credits"] == 1


def test_webhook_bundle_amounts(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    five = grant_bundle("b5", "5", event_id="evt_5")
    assert five["credits"] == 5
    assert five["ltm_pins"] == 1
    ten = grant_bundle("b10", "10")
    assert ten["credits"] == 12
    assert ten["ltm_pins"] == 1
    twenty = grant_bundle("b20", "20")
    assert twenty["credits"] == 30
    assert twenty["ltm_pins"] == 3
    # duplicate event does not double-grant
    again = grant_bundle("b5", "5", event_id="evt_5")
    assert again.get("duplicate") is True
    assert balance("b5")["credits"] == 5


def test_ltm_pin_refund_keeps_credit(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    grant_bundle("b", "5")
    assert spend_credit("b", 1)
    assert spend_pin("b", 1)
    refund_pin("b", 1)
    bal = balance("b")
    assert bal["credits"] == 4
    assert bal["ltm_pins"] == 1


def test_ensure_recovery_key_is_stable(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    first = ensure_recovery_key("buyer-stable")
    second = ensure_recovery_key("buyer-stable")
    assert first.startswith("sbk_")
    assert first == second


def test_grant_bundle_creates_recovery_key(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    granted = grant_bundle("buyer-grant", "5")
    key = granted.get("recovery_key") or ensure_recovery_key("buyer-grant")
    assert key.startswith("sbk_")
    assert buyer_for_recovery_key(key) == "buyer-grant"


def test_spend_then_lookup_by_key_sees_remaining(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    granted = grant_bundle("buyer-spend-key", "5")
    key = granted.get("recovery_key") or ensure_recovery_key("buyer-spend-key")
    assert spend_credit("buyer-spend-key", 2) is True
    assert spend_pin("buyer-spend-key", 1) is True
    found = buyer_for_recovery_key("  " + key + "  ")
    assert found == "buyer-spend-key"
    bal = balance(found)
    assert bal["credits"] == 3
    assert bal["ltm_pins"] == 0
    assert ensure_recovery_key("buyer-spend-key") == key
