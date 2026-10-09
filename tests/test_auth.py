import logging

import pytest
import requests
from conftest import response
from garminconnect import GarminConnectAuthenticationError, GarminConnectConnectionError

from garmin_connect_skills.backend import GarminBackend, normalized_error
from garmin_connect_skills.errors import AppError


def profile_transport(monkeypatch, identifier=123):
    def send(adapter, request, **kwargs):
        return response(
            200, {"displayName": "fictional-display", "profileId": identifier}, url=request.url
        )

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)


def test_mfa_wrong_code_retry_then_success_and_preserve_identity(store, bound, monkeypatch):
    profile_transport(monkeypatch)
    backend = GarminBackend(store, bound)
    monkeypatch.setattr(backend.api.client, "login", lambda *args, **kwargs: ("needs_mfa", None))
    attempts = []

    def resume(state, code):
        attempts.append(code)
        if code != "333333":
            raise GarminConnectAuthenticationError("fictional-secret-in-exception")
        backend.api.client.di_token = "fictional-mfa-token"
        backend.api.client.di_refresh_token = "fictional-mfa-refresh"

    monkeypatch.setattr(backend.api.client, "resume_login", resume)
    codes = iter(["111111", "222222", "333333"])
    backend.login("fictional-email", "fictional-password", lambda: next(codes))
    assert attempts == ["111111", "222222", "333333"]
    assert store.token(bound)["di_token"] == "fictional-mfa-token"


@pytest.mark.parametrize(
    "codes,expected", [([""], "AUTH_REQUIRED"), (["111111", "222222", "333333"], "MFA_REJECTED")]
)
def test_mfa_cancel_or_exhaustion_keeps_original_token(store, bound, monkeypatch, codes, expected):
    path = store.folder(bound) / "auth" / "tokens.json"
    original = path.read_bytes()
    backend = GarminBackend(store, bound)
    monkeypatch.setattr(backend.api.client, "login", lambda *args, **kwargs: ("needs_mfa", None))

    def resume(*args):
        raise GarminConnectAuthenticationError("fictional-secret-in-exception")

    monkeypatch.setattr(backend.api.client, "resume_login", resume)
    iterator = iter(codes)
    with pytest.raises(AppError) as error:
        backend.login("fictional-email", "fictional-password", lambda: next(iterator))
    assert error.value.code == expected and path.read_bytes() == original
    assert "fictional-secret" not in str(error.value.as_dict())


def test_token_account_mismatch_is_rejected(store, bound, monkeypatch):
    profile_transport(monkeypatch, identifier=456)
    with pytest.raises(AppError) as error:
        GarminBackend(store, bound).check()
    assert error.value.code == "INPUT_MISMATCH"


def test_token_reuse_ignores_other_token_env_and_never_credential_login(store, bound, monkeypatch):
    profile_transport(monkeypatch)
    monkeypatch.setenv("GARMINTOKENS", "fictional-other-token-location")
    backend = GarminBackend(store, bound)
    monkeypatch.setattr(
        backend.api.client, "login", lambda *args, **kwargs: pytest.fail("no password login")
    )
    backend.check()
    assert backend.guard.count == 1 and backend.ready


def test_jwt_only_is_explicit_and_does_not_replace_old_token(store, bound, monkeypatch):
    profile_transport(monkeypatch)
    path = store.folder(bound) / "auth" / "tokens.json"
    before = path.read_bytes()
    backend = GarminBackend(store, bound)

    def login(*args, **kwargs):
        backend.api.client.jwt_web = "fictional-jwt"
        return None, None

    monkeypatch.setattr(backend.api.client, "login", login)
    with pytest.raises(AppError) as error:
        backend.login("fictional-email", "fictional-password", lambda: "123456")
    assert error.value.code == "AUTH_MODE_UNSUPPORTED" and path.read_bytes() == before


def test_upstream_exception_and_debug_logs_never_escape(store, bound, caplog):
    secret = "fictional-token password=fictional-password MFA=123456 /private/fake-user/notes"
    error = normalized_error(GarminConnectConnectionError(secret))
    assert secret not in str(error.as_dict())
    GarminBackend(store, bound)
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("garminconnect.client").debug(secret)
    assert secret not in caplog.text
