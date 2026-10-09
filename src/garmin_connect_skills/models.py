"""Versioned, provenance-bearing summaries; no raw Garmin payloads."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import PROVIDER_VERSION
from .errors import AppError

SCHEMA = 1
STATUSES = {"ok", "empty", "missing", "unsupported", "error", "not_requested"}
METRICS = ("sleep", "hrv", "rhr", "stress", "body_battery", "readiness", "training_status")


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)


def timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(UTC)
    except (ValueError, TypeError):
        raise AppError("INVALID_INPUT") from None


def calendar_day(value: str) -> date:
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise AppError("INVALID_INPUT") from None


def day_range(start: str, end: str, *, limit: int = 31) -> list[str]:
    first, last = calendar_day(start), calendar_day(end)
    size = (last - first).days + 1
    if not 1 <= size <= limit:
        raise AppError("INVALID_INPUT")
    return [(first + timedelta(days=i)).isoformat() for i in range(size)]


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise AppError("INVALID_INPUT") from None
    return value


@dataclass(frozen=True)
class Profile:
    id: str
    alias: str
    region: str
    timezone: str
    identity: str | None = None

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{32}", self.id):
            raise AppError("INVALID_INPUT")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", self.alias):
            raise AppError("INVALID_INPUT")
        if self.region not in {"cn", "global"}:
            raise AppError("INVALID_INPUT")
        if self.identity is not None and not re.fullmatch(r"[0-9a-f]{64}", self.identity):
            raise AppError("INVALID_INPUT")
        validate_timezone(self.timezone)

    def today(self, now: datetime | None = None) -> date:
        return (now or utcnow()).astimezone(ZoneInfo(self.timezone)).date()


@dataclass
class Snapshot:
    profile_id: str
    region: str
    timezone: str
    kind: str
    start: str
    end: str
    fetched_at: str
    status: str
    data: dict
    coverage: list[str]
    complete: bool
    source: list[str]
    error: dict | None = None
    schema_version: int = SCHEMA
    provider: str = "python-garminconnect"
    provider_version: str = PROVIDER_VERSION
    variant: str = ""

    def validate(self, profile: Profile | None = None):
        if self.schema_version != SCHEMA or self.status not in STATUSES:
            raise AppError("INPUT_MISMATCH")
        if self.kind not in {*METRICS, "runs", "plan", "workout"}:
            raise AppError("INPUT_MISMATCH")
        if not isinstance(self.variant, str) or not re.fullmatch(
            r"[a-zA-Z0-9-]{0,80}", self.variant
        ):
            raise AppError("INPUT_MISMATCH")
        days = day_range(self.start, self.end)
        if timestamp(self.fetched_at) > utcnow() + timedelta(minutes=5):
            raise AppError("INPUT_MISMATCH")
        if not isinstance(self.data, dict) or not isinstance(self.complete, bool):
            raise AppError("INPUT_MISMATCH")
        if self.status == "empty" and (self.kind not in {"runs", "plan"} or not self.complete):
            raise AppError("INPUT_MISMATCH")
        if self.kind in {"runs", "plan"} and self.status in {"ok", "empty"}:
            key = "activities" if self.kind == "runs" else "plans"
            records = self.data.get(key)
            if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
                raise AppError("INPUT_MISMATCH")
            if bool(records) != (self.status == "ok"):
                raise AppError("INPUT_MISMATCH")
        if self.status == "ok" and not self.data:
            raise AppError("INPUT_MISMATCH")
        if not isinstance(self.coverage, list) or len(set(self.coverage)) != len(self.coverage):
            raise AppError("INPUT_MISMATCH")
        if any(d not in days for d in self.coverage):
            raise AppError("INPUT_MISMATCH")
        if self.complete and self.status in {"ok", "empty"} and self.coverage != days:
            raise AppError("INPUT_MISMATCH")
        if not isinstance(self.source, list) or any(not isinstance(s, str) for s in self.source):
            raise AppError("INPUT_MISMATCH")
        if profile and (self.profile_id, self.region, self.timezone) != (
            profile.id,
            profile.region,
            profile.timezone,
        ):
            raise AppError("INPUT_MISMATCH")
        digest(asdict(self))

    def as_dict(self) -> dict:
        self.validate()
        value = asdict(self)
        return {"id": digest(value), **value}

    @classmethod
    def from_dict(cls, value: dict, profile: Profile | None = None) -> "Snapshot":
        try:
            raw = dict(value)
            expected = raw.pop("id")
            if digest(raw) != expected:
                raise AppError("INPUT_MISMATCH")
            result = cls(**raw)
            result.validate(profile)
            return result
        except (TypeError, KeyError, ValueError):
            raise AppError("INPUT_MISMATCH") from None

    def fresh(self, profile: Profile, now: datetime | None = None) -> bool:
        moment = now or utcnow()
        age = (moment - timestamp(self.fetched_at)).total_seconds()
        if self.kind in {"plan", "workout"}:
            ttl = 15 * 60
        elif (
            self.status in {"empty", "missing"}
            or (profile.today(moment) - calendar_day(self.end)).days <= 3
        ):
            ttl = 60 * 60
        else:
            ttl = 7 * 86400
        return 0 <= age <= ttl


@dataclass
class Selection:
    snapshot: Snapshot
    cached: bool = False
    stale: bool = False
    update_error: dict | None = None
    attempt: Snapshot | None = None

    def as_dict(self) -> dict:
        return {
            "snapshot": self.snapshot.as_dict(),
            "cached": self.cached,
            "stale": self.stale,
            "update_error": self.update_error,
            "last_attempt": self.attempt.as_dict() if self.attempt else None,
        }
