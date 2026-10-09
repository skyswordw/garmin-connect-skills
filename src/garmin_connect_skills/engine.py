"""On-demand fetch/cache orchestration with profile-wide failure stopping."""

import time
from collections.abc import Callable

from .backend import GarminBackend, normalized_error
from .errors import FATAL, AppError
from .models import METRICS, Profile, Selection, Snapshot, calendar_day, day_range, digest, utcnow
from .storage import Store
from .summaries import (
    activity_summary,
    daily_summary,
    family_of,
    graphql_plans,
    plan_summary,
    workout_summary,
)


class Engine:
    def __init__(
        self,
        store: Store,
        profile: Profile,
        *,
        offline: bool = False,
        refresh: bool = False,
        factory: Callable | None = None,
    ):
        if offline and refresh:
            raise AppError("INVALID_INPUT")
        self.store, self.profile = store, profile
        self.offline, self.refresh = offline, refresh
        self.factory = factory or (lambda: GarminBackend(store, profile))
        self._backend = None
        self.halted: AppError | None = None

    @property
    def backend(self):
        if self._backend is None:
            self._backend = self.factory()
        return self._backend

    def call(self, operation: Callable):
        if self.halted:
            raise self.halted
        for attempt in range(2):
            try:
                return operation()
            except Exception as raw:
                error = normalized_error(raw)
                if error.code == "NETWORK_ERROR" and attempt == 0:
                    time.sleep(0.25)
                    continue
                if error.code in FATAL:
                    self.halted = error
                if error.code == "RATE_LIMITED" and error.retry_at:
                    self.store.cooldown(self.profile, error.retry_at)
                raise error from None

    def snapshot(
        self,
        kind: str,
        start: str,
        end: str,
        status: str,
        data: dict,
        *,
        complete: bool = True,
        coverage=None,
        source=None,
        error: AppError | None = None,
        variant: str = "",
    ) -> Snapshot:
        return Snapshot(
            self.profile.id,
            self.profile.region,
            self.profile.timezone,
            kind,
            start,
            end,
            utcnow().isoformat(),
            status,
            data,
            day_range(start, end) if coverage is None and complete else (coverage or []),
            complete,
            source or [],
            error.as_dict() if error else None,
            variant=variant,
        )

    def select(
        self, kind: str, start: str, end: str, fetch: Callable, *, variant: str = ""
    ) -> Selection:
        success, attempt = self.store.cached(self.profile, kind, start, end, variant)
        previous_error = attempt.error if attempt and attempt.status == "error" else None
        if success and not self.refresh and (self.offline or success.fresh(self.profile)):
            return Selection(
                success,
                True,
                not success.fresh(self.profile),
                previous_error,
                attempt if previous_error else None,
            )
        if self.offline or self.halted:
            if success:
                error = self.halted.as_dict() if self.halted else previous_error
                return Selection(
                    success,
                    True,
                    not success.fresh(self.profile),
                    error,
                    attempt if previous_error else None,
                )
            error = self.halted or AppError("NOT_FOUND")
            status = "not_requested" if self.halted else "error"
            return Selection(
                self.snapshot(
                    kind, start, end, status, {}, complete=False, error=error, variant=variant
                )
            )
        try:
            self.store.cooldown(self.profile)
            result = fetch()
        except Exception as raw:
            error = normalized_error(raw)
            if error.code in FATAL:
                self.halted = error
            result = self.snapshot(
                kind,
                start,
                end,
                "unsupported" if error.code == "UNSUPPORTED" else "error",
                {},
                complete=False,
                error=error,
                variant=variant,
            )
        self.store.save(self.profile, result)
        if result.status == "error" and success:
            return Selection(success, True, not success.fresh(self.profile), result.error, result)
        return Selection(result)

    def daily(self, start: str, end: str, metrics: list[str]) -> list[Selection]:
        if not metrics or any(metric not in METRICS for metric in metrics):
            raise AppError("INVALID_INPUT")
        days = day_range(start, end)
        if end > self.profile.today().isoformat():
            raise AppError("INVALID_INPUT")
        result = []
        for day in days:
            for metric in dict.fromkeys(metrics):

                def fetch(metric=metric, day=day):
                    raw = self.call(lambda: self.backend.daily(metric, day))
                    status, data = daily_summary(metric, raw, day)
                    return self.snapshot(metric, day, day, status, data, source=[f"daily:{metric}"])

                result.append(self.select(metric, day, day, fetch))
        return result

    def runs(self, start: str, end: str) -> Selection:
        day_range(start, end)

        def fetch():
            activities, seen = [], set()
            source = ["activitylist-service:search/activities"]
            for offset in range(0, 1000, 100):
                try:
                    raw = self.call(
                        lambda offset=offset: self.backend.activity_page(start, end, offset, 100)
                    )
                    if not isinstance(raw, list) or len(raw) > 100:
                        raise AppError("INVALID_RESPONSE")
                    for record in raw:
                        activity = activity_summary(record, self.profile, start, end)
                        if activity:
                            if activity["id"] in seen:
                                raise AppError("INVALID_RESPONSE")
                            seen.add(activity["id"])
                            activities.append(activity)
                    if len(raw) < 100:
                        return self.snapshot(
                            "runs",
                            start,
                            end,
                            "ok" if activities else "empty",
                            {"activities": activities},
                            source=source,
                        )
                except Exception as exception:
                    error = normalized_error(exception)
                    if error.code in FATAL:
                        self.halted = error
                    return self.snapshot(
                        "runs",
                        start,
                        end,
                        "error",
                        {"activities": activities},
                        complete=False,
                        source=source,
                        error=error,
                    )
            return self.snapshot(
                "runs",
                start,
                end,
                "error",
                {"activities": activities},
                complete=False,
                source=source,
                error=AppError("REQUEST_BUDGET"),
            )

        return self.select("runs", start, end, fetch)

    def plans(self, start: str, end: str) -> Selection:
        days = day_range(start, end)

        def fetch():
            plans = {}
            coverage = []
            source = ["query_garmin_graphql:trainingPlanScalar"]
            try:
                for day in days:
                    raw = self.call(lambda day=day: self.backend.plan_calendar(day))
                    for plan in graphql_plans(raw, start, end):
                        if plan["id"] not in plans:
                            plans[plan["id"]] = plan
                        else:
                            current = plans[plan["id"]]
                            unique = {digest(t): t for t in current["tasks"] + plan["tasks"]}
                            current["tasks"] = list(unique.values())
                            current["metadata"].update(plan["metadata"])
                    coverage.append(day)
                # A REST-only phased/legacy plan may not be represented in this calendar.
                if not plans:
                    source.append("get_training_plans")
                    raw = self.call(lambda: self.backend.plan_list())
                    if not isinstance(raw, dict) or not isinstance(
                        raw.get("trainingPlanList"), list
                    ):
                        raise AppError("INVALID_RESPONSE")
                    detail_count = 0
                    for record in raw["trainingPlanList"]:
                        if not isinstance(record, dict):
                            raise AppError("INVALID_RESPONSE")
                        dates = {}
                        for field in ("startDate", "endDate"):
                            if record.get(field) is not None:
                                if not isinstance(record[field], str):
                                    raise AppError("INVALID_RESPONSE")
                                dates[field] = record[field][:10]
                                calendar_day(dates[field])
                        if dates.get("endDate", end) < start or dates.get("startDate", start) > end:
                            continue
                        status = record.get("trainingStatus")
                        if isinstance(status, dict) and start >= self.profile.today().isoformat():
                            if status.get("statusKey", "").upper() in {
                                "COMPLETED",
                                "CANCELLED",
                                "DELETED",
                                "ENDED",
                            }:
                                continue
                        if detail_count >= 3:
                            raise AppError("REQUEST_BUDGET")
                        family = family_of(record)
                        if family not in {"adaptive", "phased"}:
                            raise AppError("UNSUPPORTED")
                        plan_id = record.get("trainingPlanId")
                        if isinstance(plan_id, bool) or not str(plan_id).isdigit():
                            raise AppError("INVALID_RESPONSE")
                        detail_count += 1
                        detail = self.call(
                            lambda plan_id=plan_id, family=family: self.backend.plan_detail(
                                str(plan_id), family
                            )
                        )
                        if not isinstance(detail, dict):
                            raise AppError("INVALID_RESPONSE")
                        merged = {**record, **detail}
                        if str(merged.get("trainingPlanId")) != str(plan_id):
                            raise AppError("INPUT_MISMATCH")
                        plans[str(plan_id)] = plan_summary(merged, start, end, rest=True)
                        source.append(f"get_{family}_training_plan_by_id")
                unknown = any(p["family"] == "unknown" for p in plans.values())
                status = "unsupported" if unknown else "ok" if plans else "empty"
                return self.snapshot(
                    "plan",
                    start,
                    end,
                    status,
                    {"plans": list(plans.values())},
                    source=source,
                    complete=not unknown,
                    error=AppError("UNSUPPORTED") if unknown else None,
                )
            except Exception as exception:
                error = normalized_error(exception)
                if error.code in FATAL:
                    self.halted = error
                status = "unsupported" if error.code == "UNSUPPORTED" else "error"
                return self.snapshot(
                    "plan",
                    start,
                    end,
                    status,
                    {"plans": list(plans.values())},
                    complete=False,
                    coverage=coverage,
                    source=source,
                    error=error,
                )

        return self.select("plan", start, end, fetch)

    def workout(self, workout_id: str, day: str) -> Selection:
        day_range(day, day)

        def fetch():
            raw = self.call(lambda: self.backend.workout(workout_id))
            data = workout_summary(raw)
            data["workout_id"] = workout_id
            return self.snapshot(
                "workout",
                day,
                day,
                "ok",
                data,
                source=["workout-service:detail"],
                variant=workout_id,
            )

        return self.select("workout", day, day, fetch, variant=workout_id)
