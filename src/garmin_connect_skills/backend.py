"""The sole Garmin adapter. Public methods only; no private portal implementation."""

import json
import logging
import re
import time
from collections.abc import Callable

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from .errors import AppError, TransportStop
from .models import Profile, digest
from .storage import Store
from .transport import RequestGuard, retry_time

STRATEGIES = {"mobile+cffi", "mobile+requests", "widget+cffi", "portal+cffi", "portal+requests"}


def normalized_error(error: Exception) -> AppError:
    if isinstance(error, AppError):
        return error
    if isinstance(error, GarminConnectTooManyRequestsError):
        return AppError("RATE_LIMITED", retry_time(None))
    if isinstance(error, GarminConnectAuthenticationError):
        return AppError("AUTH_REQUIRED")
    if isinstance(error, GarminConnectNotFoundError):
        return AppError("UNSUPPORTED")
    if isinstance(error, GarminConnectConnectionError):
        return AppError("NETWORK_ERROR")
    return AppError("INVALID_RESPONSE")


class GarminBackend:
    def __init__(self, store: Store, profile: Profile):
        self.store = store
        self.profile = profile
        self.api = Garmin(is_cn=profile.region == "cn", retry_attempts=0)
        self.guard = RequestGuard(profile.region)
        self.ready = False
        self.saved_hash = None
        # Upstream debug logging can include response bodies. Keep the whole logger
        # subtree away from root handlers, even if the calling Agent enables debug.
        for name in ("garminconnect", "requests", "urllib3", "curl_cffi"):
            logger = logging.getLogger(name)
            logger.handlers = [logging.NullHandler()]
            logger.propagate = False

    def _hydrate(self, *, bind: bool = False):
        result = self.api.connectapi("/userprofile-service/socialProfile")
        if not isinstance(result, dict) or not isinstance(result.get("displayName"), str):
            raise AppError("INVALID_RESPONSE")
        name = result["displayName"]
        if not name:
            raise AppError("INVALID_RESPONSE")
        identity = digest([self.profile.region, result.get("profileId") or name])
        if bind:
            self.profile = self.store.bind(self.profile, identity)
        elif self.profile.identity != identity:
            raise AppError("INPUT_MISMATCH")
        self.api.display_name = name
        self.ready = True

    def _persist(self):
        tokens = json.loads(self.api.client.dumps())
        if not tokens.get("di_token"):
            raise AppError("AUTH_MODE_UNSUPPORTED")
        token_hash = digest(tokens)
        if token_hash != self.saved_hash:
            self.store.save_token(self.profile, tokens)
            self.saved_hash = token_hash

    def _ensure(self):
        if self.ready:
            return
        self.store.cooldown(self.profile)
        try:
            tokens = self.store.token(self.profile)
        except AppError as error:
            if error.code == "NOT_FOUND":
                raise AppError("AUTH_REQUIRED") from None
            raise
        self.api.client.loads(json.dumps(tokens))
        self.saved_hash = digest(tokens)
        self._hydrate()
        self._persist()

    def run(self, operation: Callable):
        try:
            with self.guard.scope():
                self._ensure()
                result = operation(self.api)
                self._persist()
                return result
        except TransportStop as stop:
            self._preserve_refresh(stop.error)
            raise stop.error from None
        except Exception as error:
            normalized = normalized_error(error)
            self._preserve_refresh(normalized)
            raise normalized from None

    def _preserve_refresh(self, error: AppError):
        if error.code == "RATE_LIMITED":
            self.store.cooldown(self.profile, error.retry_at)
        # A successful DI refresh belongs to the already-bound token. Preserve
        # rotation even if a following profile/health request has a network error.
        # Fresh credential logins still must pass identity verification first.
        if self.saved_hash and self.profile.identity and error.code != "INPUT_MISMATCH":
            self._persist()

    def check(self):
        self.run(lambda api: None)

    def login(self, email: str, password: str, mfa: Callable[[], str], strategy: str = "auto"):
        # Human credential entry happens before this method; MFA entry pauses the
        # elapsed-time budget. Login has a smaller budget than data batches.
        self.guard = RequestGuard(self.profile.region, limit=40)
        if strategy != "auto":
            allowed = {name for name in STRATEGIES if name.startswith(strategy + "+")}
            self.api.client.skip_strategies = STRATEGIES - allowed
        self.store.cooldown(self.profile)
        try:
            with self.guard.scope():
                status, _ = self.api.client.login(email, password, return_on_mfa=True)
                if status == "needs_mfa":
                    for attempt in range(3):
                        remaining = max(0, self.guard.deadline - time.monotonic())
                        code = mfa()
                        self.guard.deadline = time.monotonic() + remaining
                        if not code:
                            raise AppError("AUTH_REQUIRED")
                        try:
                            self.api.client.resume_login(None, code)
                            break
                        except GarminConnectAuthenticationError:
                            if attempt == 2:
                                raise AppError("MFA_REJECTED") from None
                    else:
                        raise AppError("MFA_REJECTED")
                self._hydrate(bind=True)
                self._persist()
        except TransportStop as stop:
            if stop.error.code == "RATE_LIMITED":
                self.store.cooldown(self.profile, stop.error.retry_at)
            raise stop.error from None
        except GarminConnectAuthenticationError:
            raise AppError("AUTH_FAILED") from None
        except Exception as error:
            raise normalized_error(error) from None
        finally:
            self.api.password = None
        return self.profile

    def daily(self, metric: str, day: str):
        methods = {
            "sleep": "get_sleep_data",
            "hrv": "get_hrv_data",
            "rhr": "get_rhr_day",
            "stress": "get_stress_data",
            "body_battery": "get_body_battery",
            "readiness": "get_training_readiness",
            "training_status": "get_training_status",
        }
        return self.run(lambda api: getattr(api, methods[metric])(day))

    def activity_page(self, start: str, end: str, offset: int, limit: int):
        # Bypass get_activities(), which converts a null response to [].
        return self.run(
            lambda api: api.connectapi(
                api.garmin_connect_activities,
                params={
                    "start": offset,
                    "limit": limit,
                    "startDate": start,
                    "endDate": end,
                    "activityType": "running",
                },
            )
        )

    def plan_calendar(self, anchor: str):
        # Protocol shape learned from Taxuspt/garmin_mcp; independently written.
        # Query each requested calendar date; no inferred weekly coverage.
        query = (
            "query { trainingPlanScalar(calendarDate:"
            + json.dumps(anchor)
            + ', lang:"en-US", firstDayOfWeek:"monday") }'
        )
        return self.run(lambda api: api.query_garmin_graphql({"query": query}))

    def plan_list(self):
        return self.run(lambda api: api.get_training_plans())

    def plan_detail(self, plan_id: str, family: str):
        method = (
            "get_training_plan_by_id" if family == "phased" else "get_adaptive_training_plan_by_id"
        )
        return self.run(lambda api: getattr(api, method)(plan_id))

    def workout(self, workout_id: str):
        if re.fullmatch(r"\d+", workout_id):
            return self.run(lambda api: api.get_workout_by_id(int(workout_id)))
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", workout_id):
            raise AppError("INVALID_INPUT")
        return self.run(lambda api: api.connectapi(f"workout-service/fbt-adaptive/{workout_id}"))
