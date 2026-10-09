"""Profile-scoped immutable summaries and atomic, permission-restricted state."""

import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

from filelock import FileLock, Timeout
from platformdirs import user_state_path

from .errors import AppError
from .models import Profile, Snapshot, canonical, digest, timestamp, utcnow


def safe_path(path: Path):
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise AppError("IO_ERROR")


def private_dir(path: Path):
    safe_path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)


def read_json(path: Path) -> dict:
    safe_path(path)
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            raise AppError("INVALID_INPUT")
        result = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise AppError("INVALID_INPUT")
        return result
    except FileNotFoundError:
        raise AppError("NOT_FOUND") from None
    except (OSError, ValueError, UnicodeError):
        raise AppError("IO_ERROR") from None


def atomic_write(path: Path, content: bytes, *, exclusive: bool = False):
    safe_path(path)
    private_dir(path.parent)
    temp_path = None
    try:
        fd, name = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
        temp_path = Path(name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            # A hard link publishes the fully written file without replacing an existing one.
            os.link(temp_path, path)
        else:
            os.replace(temp_path, path)
    except FileExistsError:
        raise AppError("REPORT_EXISTS") from None
    except OSError:
        raise AppError("IO_ERROR") from None
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


class Store:
    def __init__(self, root: Path | None = None):
        self.root = (root or user_state_path("garmin-connect-skills", appauthor=False)).expanduser()
        safe_path(self.root)

    def profiles(self) -> dict:
        path = self.root / "profiles.json"
        if not path.exists():
            return {"profiles": {}, "default": None}
        result = read_json(path)
        if not isinstance(result.get("profiles"), dict):
            raise AppError("INVALID_INPUT")
        try:
            for key, value in result["profiles"].items():
                if Profile(**value).alias != key:
                    raise AppError("INVALID_INPUT")
            if result.get("default") not in result["profiles"] and result["profiles"]:
                raise AppError("INVALID_INPUT")
        except (TypeError, ValueError):
            raise AppError("INVALID_INPUT") from None
        return result

    @contextmanager
    def config_lock(self):
        private_dir(self.root)
        try:
            with FileLock(self.root / "config.lock", timeout=0):
                yield
        except Timeout:
            raise AppError("BUSY") from None

    def get_profile(self, alias: str | None = None) -> Profile:
        config = self.profiles()
        key = alias or config.get("default")
        try:
            return Profile(**config["profiles"][key])
        except KeyError:
            raise AppError("NOT_FOUND") from None
        except TypeError:
            raise AppError("INVALID_INPUT") from None

    def create_profile(self, alias: str, region: str, timezone: str) -> Profile:
        proposed = Profile(uuid.uuid4().hex, alias, region, timezone)
        with self.config_lock():
            config = self.profiles()
            if alias in config["profiles"]:
                current = Profile(**config["profiles"][alias])
                if (current.region, current.timezone) != (region, timezone):
                    raise AppError("INPUT_MISMATCH")
                return current
            config["profiles"][alias] = asdict(proposed)
            config["default"] = config.get("default") or alias
            atomic_write(self.root / "profiles.json", canonical(config))
        return proposed

    def bind(self, profile: Profile, identity: str) -> Profile:
        if profile.identity and profile.identity != identity:
            raise AppError("INPUT_MISMATCH")
        result = replace(profile, identity=identity)
        with self.config_lock():
            config = self.profiles()
            current = Profile(**config["profiles"][profile.alias])
            if current.identity and current.identity != identity:
                raise AppError("INPUT_MISMATCH")
            config["profiles"][profile.alias] = asdict(result)
            atomic_write(self.root / "profiles.json", canonical(config))
        return result

    def folder(self, profile: Profile) -> Path:
        return self.root / "profiles" / profile.id / profile.region

    @contextmanager
    def lock(self, profile: Profile):
        directory = self.folder(profile)
        private_dir(directory)
        try:
            with FileLock(directory / "profile.lock", timeout=0):
                yield
        except Timeout:
            raise AppError("BUSY") from None

    def token(self, profile: Profile) -> dict:
        bundle = read_json(self.folder(profile) / "auth" / "tokens.json")
        if (bundle.get("profile_id"), bundle.get("region"), bundle.get("identity")) != (
            profile.id,
            profile.region,
            profile.identity,
        ) or not profile.identity:
            raise AppError("INPUT_MISMATCH")
        tokens = bundle.get("tokens")
        if not isinstance(tokens, dict) or not tokens.get("di_token"):
            raise AppError("AUTH_REQUIRED")
        return tokens

    def save_token(self, profile: Profile, tokens: dict):
        if not tokens.get("di_token") or not profile.identity:
            raise AppError("AUTH_MODE_UNSUPPORTED")
        value = {
            "profile_id": profile.id,
            "region": profile.region,
            "identity": profile.identity,
            "tokens": tokens,
        }
        atomic_write(self.folder(profile) / "auth" / "tokens.json", canonical(value))

    def _key(self, profile: Profile, kind: str, start: str, end: str, variant: str = "") -> str:
        return digest([1, profile.id, profile.region, profile.timezone, kind, start, end, variant])

    def save(self, profile: Profile, snapshot: Snapshot):
        snapshot.validate(profile)
        value = snapshot.as_dict()
        base = self.folder(profile)
        path = base / "objects" / f"{value['id']}.json"
        if not path.exists():
            atomic_write(path, canonical(value))
        key = self._key(profile, snapshot.kind, snapshot.start, snapshot.end, snapshot.variant)
        index_path = base / "index" / f"{key}.json"
        index = read_json(index_path) if index_path.exists() else {}
        index["attempt"] = value["id"]
        if snapshot.status in {"ok", "empty", "missing", "unsupported"}:
            index["success"] = value["id"]
        atomic_write(index_path, canonical(index))

    def load(self, profile: Profile, snapshot_id: str) -> Snapshot:
        if not isinstance(snapshot_id, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot_id):
            raise AppError("INPUT_MISMATCH")
        snapshot = Snapshot.from_dict(
            read_json(self.folder(profile) / "objects" / f"{snapshot_id}.json"), profile
        )
        if snapshot.as_dict()["id"] != snapshot_id:
            raise AppError("INPUT_MISMATCH")
        return snapshot

    def cached(self, profile: Profile, kind: str, start: str, end: str, variant: str = "") -> tuple:
        path = (
            self.folder(profile) / "index" / f"{self._key(profile, kind, start, end, variant)}.json"
        )
        if not path.exists():
            return None, None
        index = read_json(path)
        success = self.load(profile, index["success"]) if index.get("success") else None
        attempt = self.load(profile, index["attempt"]) if index.get("attempt") else None
        for item in (success, attempt):
            if item and (item.kind, item.start, item.end, item.variant) != (
                kind,
                start,
                end,
                variant,
            ):
                raise AppError("INPUT_MISMATCH")
        return success, attempt

    def cooldown(self, profile: Profile, retry_at: str | None = None):
        path = self.folder(profile) / "cooldown.json"
        if retry_at:
            atomic_write(path, canonical({"retry_at": retry_at}))
        elif path.exists():
            until = read_json(path).get("retry_at")
            if until and timestamp(until) > utcnow():
                raise AppError("RATE_LIMITED", until)
