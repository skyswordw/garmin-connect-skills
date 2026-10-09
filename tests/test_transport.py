from datetime import UTC, datetime, timedelta

import pytest
import requests
from conftest import response
from curl_cffi import requests as curl_requests

from garmin_connect_skills.backend import GarminBackend
from garmin_connect_skills.errors import AppError, TransportStop
from garmin_connect_skills.transport import RequestGuard, retry_time


def test_real_upstream_login_stops_at_first_429_without_fingerprint_fallback(
    store, profile, monkeypatch
):
    calls = []

    def fake(session, method, url, **kwargs):
        calls.append(url)
        return response(429, {"message": "fictional-sensitive-body"}, {"Retry-After": "90"}, url)

    monkeypatch.setattr(curl_requests.Session, "request", fake)
    original_send = requests.Session.send
    backend = GarminBackend(store, profile)
    with pytest.raises(AppError) as error:
        backend.login("fictional-email", "fictional-password", lambda: "fictional-MFA")
    assert error.value.code == "RATE_LIMITED"
    assert len(calls) == backend.guard.count == 1
    assert requests.Session.send is original_send and curl_requests.Session.request is fake
    assert "fictional" not in str(error.value.as_dict())
    with pytest.raises(AppError) as cooldown:
        store.cooldown(profile)
    assert cooldown.value.code == "RATE_LIMITED"


def test_requests_429_stops_before_library_profile_retries(store, bound, monkeypatch):
    calls = []

    def fake(adapter, request, **kwargs):
        calls.append(request.url)
        return response(429, {}, {"Retry-After": "30"}, request.url)

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake)
    with pytest.raises(AppError) as error:
        GarminBackend(store, bound).check()
    assert error.value.code == "RATE_LIMITED" and len(calls) == 1


def test_api_401_refreshes_once_replays_and_persists_bound_token(store, bound, monkeypatch):
    api_calls, refresh_calls = [], []

    def api(adapter, request, **kwargs):
        api_calls.append(request)
        return response(
            401 if len(api_calls) == 1 else 200,
            {"displayName": "fictional-display", "profileId": 123},
            url=request.url,
        )

    def refresh(session, method, url, **kwargs):
        refresh_calls.append(url)
        assert url.startswith("https://diauth.garmin.cn/")
        assert kwargs["data"]["grant_type"] == "refresh_token"
        return response(
            200,
            {"access_token": "fictional-new-token", "refresh_token": "fictional-new-refresh"},
            url=url,
        )

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", api)
    monkeypatch.setattr(curl_requests.Session, "request", refresh)
    backend = GarminBackend(store, bound)
    backend.check()
    assert len(api_calls) == 2 and len(refresh_calls) == 1 and backend.guard.count == 3
    assert store.token(bound)["di_refresh_token"] == "fictional-new-refresh"


def test_repeated_401_does_not_refresh_again(store, bound, monkeypatch):
    api_calls, refresh_calls = [], []

    def api(adapter, request, **kwargs):
        api_calls.append(request.url)
        return response(401, {}, url=request.url)

    def refresh(session, method, url, **kwargs):
        refresh_calls.append(url)
        return response(
            200,
            {"access_token": "fictional-new-token", "refresh_token": "fictional-new-refresh"},
            url=url,
        )

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", api)
    monkeypatch.setattr(curl_requests.Session, "request", refresh)
    backend = GarminBackend(store, bound)
    with pytest.raises(AppError) as error:
        backend.check()
    assert error.value.code == "AUTH_REQUIRED"
    assert len(api_calls) == 2 and len(refresh_calls) == 1
    assert store.token(bound)["di_refresh_token"] == "fictional-new-refresh"


@pytest.mark.parametrize("library", ["requests", "curl"])
def test_redirect_cannot_cross_region(library, monkeypatch):
    calls = []

    def fake_requests(adapter, request, **kwargs):
        calls.append(request.url)
        return response(302, {}, {"Location": "https://sso.garmin.com/other"}, request.url)

    def fake_curl(session, method, url, **kwargs):
        calls.append(url)
        assert kwargs["allow_redirects"] is False
        return response(302, {}, {"Location": "https://sso.garmin.com/other"}, url)

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake_requests)
    monkeypatch.setattr(curl_requests.Session, "request", fake_curl)
    guard = RequestGuard("cn")
    with pytest.raises(TransportStop) as stop, guard.scope():
        if library == "requests":
            requests.Session().get("https://sso.garmin.cn/login")
        else:
            curl_requests.Session().get("https://sso.garmin.cn/login")
    assert stop.value.error.code == "INPUT_MISMATCH" and len(calls) == 1


def test_request_budget_counts_actual_redirects(monkeypatch):
    calls = []

    def fake(adapter, request, **kwargs):
        calls.append(request.url)
        return response(302, {}, {"Location": request.url + "next"}, request.url)

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake)
    guard = RequestGuard("cn", limit=2)
    with pytest.raises(TransportStop) as stop, guard.scope():
        requests.Session().get("https://sso.garmin.cn/login")
    assert stop.value.error.code == "REQUEST_BUDGET" and len(calls) == guard.count == 2


def test_api_writes_and_third_party_hosts_are_blocked_before_transmission():
    for method, url in [
        ("POST", "https://connectapi.garmin.cn/workout-service/workout"),
        ("GET", "https://example.com/collect"),
        ("GET", "https://garmin.cn.example.com/collect"),
    ]:
        guard = RequestGuard("cn")
        with pytest.raises(TransportStop):
            guard.before(method, url)
        assert guard.count == 0


def test_retry_after_seconds_http_date_and_invalid():
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    assert retry_time("120", now) == (now + timedelta(seconds=120)).isoformat()
    assert (
        retry_time("Thu, 08 Oct 2026 12:05:00 GMT", now) == (now + timedelta(minutes=5)).isoformat()
    )
    assert retry_time("not-a-date", now) == (now + timedelta(minutes=15)).isoformat()


def test_embedded_json_429_is_not_hidden_by_http_200(monkeypatch):
    def fake(session, method, url, **kwargs):
        return response(200, {"error": {"status-code": "429"}}, url=url)

    monkeypatch.setattr(curl_requests.Session, "request", fake)
    guard = RequestGuard("cn")
    with pytest.raises(TransportStop) as stop, guard.scope():
        curl_requests.Session().post("https://sso.garmin.cn/mobile/api/login")
    assert stop.value.error.code == "RATE_LIMITED" and guard.count == 1


@pytest.mark.parametrize(
    "status,code", [(400, "INVALID_RESPONSE"), (404, "UNSUPPORTED"), (403, "FORBIDDEN")]
)
def test_api_client_errors_are_not_network_retry_candidates(status, code, monkeypatch):
    def fake(adapter, request, **kwargs):
        return response(status, {"message": "fictional-secret"}, url=request.url)

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake)
    guard = RequestGuard("cn")
    with pytest.raises(TransportStop) as stop, guard.scope():
        requests.Session().get("https://connectapi.garmin.cn/fake")
    assert stop.value.error.code == code and guard.count == 1


def test_guard_disables_implicit_netrc_credentials_only_during_scope(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("must not discover credentials in netrc")

    def fake(adapter, request, **kwargs):
        assert "Authorization" not in request.headers
        return response(200, {}, url=request.url)

    monkeypatch.setattr(requests.sessions, "get_netrc_auth", forbidden)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake)
    with RequestGuard("cn").scope():
        requests.Session().get("https://connectapi.garmin.cn/fake")
    assert requests.sessions.get_netrc_auth is forbidden
