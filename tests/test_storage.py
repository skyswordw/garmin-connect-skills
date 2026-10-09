import json
import os

import pytest

from garmin_connect_skills.demo import FictionalBackend
from garmin_connect_skills.engine import Engine
from garmin_connect_skills.errors import AppError
from garmin_connect_skills.storage import atomic_write, read_json


def test_token_profile_and_region_binding(store, bound):
    other = store.create_profile("other", "global", "Asia/Shanghai")
    other = store.bind(other, bound.identity)
    raw = read_json(store.folder(bound) / "auth" / "tokens.json")
    atomic_write(store.folder(other) / "auth" / "tokens.json", json.dumps(raw).encode())
    with pytest.raises(AppError) as exc:
        store.token(other)
    assert exc.value.code == "INPUT_MISMATCH"


def test_token_atomic_replacement_failure_preserves_original(store, bound, monkeypatch):
    path = store.folder(bound) / "auth" / "tokens.json"
    original = path.read_bytes()

    def fail(*args):
        raise OSError("fictional private error: token=do-not-print")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(AppError) as exc:
        store.save_token(bound, {"di_token": "fictional-new-token"})
    assert exc.value.code == "IO_ERROR" and path.read_bytes() == original
    assert not list(path.parent.glob(".writing-*"))


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX modes and symlinks; Windows needs separate validation"
)
def test_token_permissions_and_symlink_refusal(store, bound, tmp_path):
    path = store.folder(bound) / "auth" / "tokens.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    link = tmp_path.resolve() / "symlink.json"
    link.symlink_to(path)
    with pytest.raises(AppError):
        read_json(link)
    with pytest.raises(AppError):
        atomic_write(link, b"bad")
    assert store.token(bound)["di_token"] == "fictional-token"


def test_immutable_snapshot_hash_is_verified(store, profile):
    result = Engine(store, profile, factory=FictionalBackend).daily(
        "2026-10-07", "2026-10-07", ["sleep"]
    )[0]
    identifier = result.snapshot.as_dict()["id"]
    path = store.folder(profile) / "objects" / f"{identifier}.json"
    raw = json.loads(path.read_text())
    raw["data"]["duration_seconds"] = 999
    path.write_text(json.dumps(raw))
    with pytest.raises(AppError) as exc:
        store.load(profile, identifier)
    assert exc.value.code == "INPUT_MISMATCH"


def test_profile_lock_prevents_concurrent_refresh(store, profile):
    with store.lock(profile):
        with pytest.raises(AppError) as exc, store.lock(profile):
            pass
    assert exc.value.code == "BUSY"
