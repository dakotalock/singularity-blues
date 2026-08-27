from datetime import datetime, timezone

from orchestrator.denver import denver_logged_at


def test_denver_logged_at_utc_august_is_previous_evening():
    # MDT is UTC-6 in August. 05:07:48Z Aug 27 = 11:07 PM Aug 26 Denver.
    expected = "Wednesday, August 26th, 11:07 PM Denver"
    assert denver_logged_at("2026-08-27 05:07:48") == expected
    assert denver_logged_at("2026-08-27T05:07:48Z") == expected
    dt = datetime(2026, 8, 27, 5, 7, 48, tzinfo=timezone.utc)
    assert denver_logged_at(dt) == expected
    naive = datetime(2026, 8, 27, 5, 7, 48)
    assert denver_logged_at(naive) == expected
