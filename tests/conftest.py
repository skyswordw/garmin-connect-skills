import json
from datetime import UTC, datetime

import pytest
import requests
from curl_cffi import requests as curl_requests

from garmin_connect_skills.models import digest
from garmin_connect_skills.storage import Store


class NetworkForbidden(BaseException):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise NetworkForbidden("Offline tests must provide a fake transport")

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", blocked)
    monkeypatch.setattr(curl_requests.Session, "request", blocked)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path.resolve() / "state")


@pytest.fixture
def profile(store):
    return store.create_profile("main", "cn", "Asia/Shanghai")


@pytest.fixture
def bound(store, profile):
    profile = store.bind(profile, digest(["cn", 123]))
    store.save_token(
        profile,
        {
            "di_token": "fictional-token",
            "di_refresh_token": "fictional-refresh",
            "di_client_id": "fictional-client",
        },
    )
    return profile


def response(status=200, payload=None, headers=None, url="https://connectapi.garmin.cn/fake"):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    result.headers.update({"Content-Type": "application/json", **(headers or {})})
    result.url = url
    result.request = requests.Request("GET", url).prepare()
    result.encoding = "utf-8"
    return result


def moment():
    return datetime(2026, 10, 8, 12, tzinfo=UTC)
