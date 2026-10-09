from dataclasses import replace
from datetime import timedelta

import pytest

from garmin_connect_skills.demo import FictionalBackend
from garmin_connect_skills.engine import Engine
from garmin_connect_skills.errors import AppError
from garmin_connect_skills.models import Profile, utcnow


class Fake(FictionalBackend):
    def __init__(self, pages=None, failure=None):
        self.pages = pages or []
        self.failure = failure
        self.calls = []

    def activity_page(self, start, end, offset, limit):
        self.calls.append(("runs", offset))
        if self.failure:
            raise AppError(self.failure)
        result = self.pages.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def daily(self, metric, day):
        self.calls.append((metric, day))
        if self.failure:
            raise AppError(self.failure)
        return super().daily(metric, day)


def test_true_empty_vs_failure_and_invalid_collection(store, profile):
    for raw, status, code in [
        (None, "error", "INVALID_RESPONSE"),
        ({"ok": False}, "error", "INVALID_RESPONSE"),
        ([], "empty", None),
    ]:
        backend = Fake([raw])
        result = (
            Engine(store, profile, refresh=True, factory=lambda backend=backend: backend)
            .runs("2026-09-28", "2026-10-04")
            .snapshot
        )
        assert result.status == status
        assert result.complete is (status == "empty")
        assert result.error is None if code is None else result.error["code"] == code


def test_activity_failure_does_not_create_empty_success(store, profile):
    backend = Fake(failure="AUTH_REQUIRED")
    result = Engine(store, profile, factory=lambda: backend).runs("2026-09-28", "2026-10-04")
    assert result.snapshot.status == "error" and not result.snapshot.complete
    success, attempt = store.cached(profile, "runs", "2026-09-28", "2026-10-04")
    assert success is None and attempt.status == "error" and len(backend.calls) == 1


@pytest.mark.parametrize(
    "failure,requests",
    [("RATE_LIMITED", 1), ("AUTH_REQUIRED", 1), ("FORBIDDEN", 1), ("NETWORK_ERROR", 2)],
)
def test_failure_stops_remaining_daily_batch(store, profile, failure, requests, monkeypatch):
    monkeypatch.setattr("garmin_connect_skills.engine.time.sleep", lambda _: None)
    backend = Fake(failure=failure)
    result = Engine(store, profile, factory=lambda: backend).daily(
        "2026-09-28", "2026-10-04", ["sleep", "hrv", "rhr"]
    )
    assert len(backend.calls) == requests
    assert result[0].snapshot.status == "error"
    assert all(s.snapshot.status == "not_requested" for s in result[1:])


def test_cache_only_fetches_selected_metrics_and_never_constructs_backend_on_hit(store, profile):
    backend = Fake()
    first = Engine(store, profile, factory=lambda: backend).daily(
        "2026-10-07", "2026-10-07", ["hrv"]
    )
    assert backend.calls == [("hrv", "2026-10-07")]

    def forbidden_factory():
        pytest.fail("cache hit must not initialize authentication")

    second = Engine(store, profile, factory=forbidden_factory).daily(
        "2026-10-07", "2026-10-07", ["hrv"]
    )
    assert (
        second[0].cached and second[0].snapshot.as_dict()["id"] == first[0].snapshot.as_dict()["id"]
    )


def test_expired_cache_offline_and_failed_refresh_preserve_good_source(store, profile):
    source = (
        Engine(store, profile, factory=Fake)
        .daily("2026-10-07", "2026-10-07", ["sleep"])[0]
        .snapshot
    )
    source.fetched_at = (utcnow() - timedelta(days=10)).isoformat()
    store.save(profile, source)
    offline = Engine(store, profile, offline=True).daily("2026-10-07", "2026-10-07", ["sleep"])[0]
    assert offline.stale and offline.cached
    failed = Engine(
        store, profile, refresh=True, factory=lambda: Fake(failure="AUTH_REQUIRED")
    ).daily("2026-10-07", "2026-10-07", ["sleep"])[0]
    assert failed.snapshot.as_dict()["id"] == source.as_dict()["id"]
    assert failed.update_error["code"] == "AUTH_REQUIRED" and failed.attempt.status == "error"
    assert store.cached(profile, "sleep", "2026-10-07", "2026-10-07")[0].status == "ok"


def test_exact_range_region_profile_and_timezone_are_isolated(store, profile):
    Engine(store, profile, factory=lambda: Fake([[]])).runs("2026-09-28", "2026-10-04")
    other = store.create_profile("global", "global", "Asia/Shanghai")
    for wrong in (other, replace(profile, timezone="UTC"), replace(profile, region="global")):
        selected = Engine(store, wrong, offline=True).runs("2026-09-28", "2026-10-04")
        assert (
            selected.snapshot.status == "error" and selected.snapshot.error["code"] == "NOT_FOUND"
        )
    selected = Engine(store, profile, offline=True).runs("2026-09-29", "2026-10-04")
    assert selected.snapshot.status == "error"


def test_profile_creation_cannot_change_region_or_timezone(store, profile):
    with pytest.raises(AppError) as exc:
        store.create_profile(profile.alias, "global", profile.timezone)
    assert exc.value.code == "INPUT_MISMATCH"


def test_partial_pagination_keeps_confirmed_records_not_zero(store, profile, monkeypatch):
    monkeypatch.setattr("garmin_connect_skills.engine.time.sleep", lambda _: None)
    records = [
        {
            "activityId": i + 1,
            "activityType": {"typeKey": "running"},
            "startTimeLocal": "2026-10-01 06:30:00",
            "distance": 1000,
            "duration": 600,
        }
        for i in range(100)
    ]
    backend = Fake([records, AppError("NETWORK_ERROR"), AppError("NETWORK_ERROR")])
    result = (
        Engine(store, profile, factory=lambda: backend).runs("2026-09-28", "2026-10-04").snapshot
    )
    assert result.status == "error" and not result.complete and result.coverage == []
    assert len(result.data["activities"]) == 100 and len(backend.calls) == 3


def test_duplicate_pages_are_not_counted_twice(store, profile):
    records = [
        {
            "activityId": i + 1,
            "activityType": {"typeKey": "running"},
            "startTimeLocal": "2026-10-01 06:30:00",
        }
        for i in range(100)
    ]
    result = (
        Engine(store, profile, factory=lambda: Fake([records, records]))
        .runs("2026-09-28", "2026-10-04")
        .snapshot
    )
    assert result.status == "error" and len(result.data["activities"]) == 100


def test_cooldown_blocks_before_constructing_provider(store, profile):
    until = (utcnow() + timedelta(minutes=15)).isoformat()
    store.cooldown(profile, until)
    result = Engine(store, profile, factory=lambda: pytest.fail("must not request")).daily(
        "2026-10-07", "2026-10-07", ["sleep", "hrv"]
    )
    assert result[0].snapshot.error["retry_at"] == until
    assert result[1].snapshot.status == "not_requested"


def test_profile_date_uses_iana_timezone_across_dst():
    from datetime import UTC, datetime

    p = Profile("a" * 32, "ny", "cn", "America/New_York")
    assert p.today(datetime(2026, 11, 1, 3, 30, tzinfo=UTC)).isoformat() == "2026-10-31"
    assert p.today(datetime(2026, 11, 1, 6, 30, tzinfo=UTC)).isoformat() == "2026-11-01"
