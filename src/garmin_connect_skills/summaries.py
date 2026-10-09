"""Small explicit allowlists. Malformed data is never coerced into zero/empty."""

import math
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .errors import AppError
from .models import Profile, calendar_day

RUN_TYPES = {
    "running",
    "trail_running",
    "treadmill_running",
    "track_running",
    "indoor_running",
    "virtual_run",
    "ultra_run",
    "street_running",
}


def number(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AppError("INVALID_RESPONSE")
    if not math.isfinite(value) or value < 0:
        raise AppError("INVALID_RESPONSE")
    return value


def text(value, limit: int = 500):
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError("INVALID_RESPONSE")
    return "".join(c for c in value if c >= " " or c == "\n")[:limit]


def check_day(record: dict, day: str):
    for key in ("calendarDate", "date"):
        if record.get(key) is not None:
            if record[key] != day:
                raise AppError("INPUT_MISMATCH")


def fields(record: dict, mapping: dict) -> dict:
    if not isinstance(record, dict) or not any(key in record for key in mapping):
        raise AppError("INVALID_RESPONSE")
    result = {}
    for raw, normalized in mapping.items():
        if raw in record:
            value = number(record[raw])
            if value is not None:
                result[normalized] = value
    return result


def daily_summary(metric: str, raw, day: str) -> tuple[str, dict]:
    if raw is None:
        # Some optional endpoints legitimately return null; collection APIs do not.
        return "missing", {}
    if metric in {"body_battery", "readiness"}:
        if not isinstance(raw, list) or any(not isinstance(r, dict) for r in raw):
            raise AppError("INVALID_RESPONSE")
        if not raw:
            return "missing", {}
        for row in raw:
            check_day(row, day)
        if metric == "body_battery":
            if len(raw) != 1:
                raise AppError("INVALID_RESPONSE")
            record = raw[0]
            data = fields(record, {"charged": "charged", "drained": "drained"})
            values = record.get("bodyBatteryValuesArray")
            if values is not None:
                if not isinstance(values, list):
                    raise AppError("INVALID_RESPONSE")
                readings = []
                for point in values:
                    if not isinstance(point, list) or len(point) < 2:
                        raise AppError("INVALID_RESPONSE")
                    if point[1] in (-1, -2, None):
                        continue
                    reading = number(point[1])
                    if reading is not None:
                        readings.append(reading)
                if readings:
                    data.update(
                        first=readings[0], last=readings[-1], low=min(readings), high=max(readings)
                    )
        else:
            morning = [r for r in raw if r.get("inputContext") == "AFTER_WAKEUP_RESET"]
            record = (morning or raw)[-1]
            data = fields(record, {"score": "score", "recoveryTime": "recovery_minutes"})
            if record.get("level") is not None:
                data["garmin_level"] = text(record["level"], 80)
            data["context"] = "morning" if morning else "latest_returned"
            if not any(k in data for k in ("score", "recovery_minutes")):
                return "missing", {}
        return ("ok" if data else "missing"), data
    if not isinstance(raw, dict):
        raise AppError("INVALID_RESPONSE")
    check_day(raw, day)
    if metric == "sleep":
        if "dailySleepDTO" not in raw:
            raise AppError("INVALID_RESPONSE")
        record = raw["dailySleepDTO"]
        if record is None:
            return "missing", {}
        if not isinstance(record, dict):
            raise AppError("INVALID_RESPONSE")
        check_day(record, day)
        data = fields(
            record,
            {
                "sleepTimeSeconds": "duration_seconds",
                "deepSleepSeconds": "deep_seconds",
                "lightSleepSeconds": "light_seconds",
                "remSleepSeconds": "rem_seconds",
                "awakeSleepSeconds": "awake_seconds",
            },
        )
        scores = record.get("sleepScores")
        if scores is not None:
            if not isinstance(scores, dict):
                raise AppError("INVALID_RESPONSE")
            overall = scores.get("overall")
            if overall is not None:
                if not isinstance(overall, dict):
                    raise AppError("INVALID_RESPONSE")
                score = number(overall.get("value"))
                if score is not None:
                    data["score"] = score
    elif metric == "hrv":
        if "hrvSummary" not in raw:
            raise AppError("INVALID_RESPONSE")
        record = raw["hrvSummary"]
        if record is None:
            return "missing", {}
        if not isinstance(record, dict):
            raise AppError("INVALID_RESPONSE")
        check_day(record, day)
        data = fields(record, {"lastNightAvg": "last_night_ms", "weeklyAvg": "weekly_avg_ms"})
        if record.get("status") is not None:
            data["garmin_status"] = text(record["status"], 80)
        baseline = record.get("baseline")
        if baseline is not None:
            data["garmin_baseline"] = fields(
                baseline, {"balancedLow": "low_ms", "balancedUpper": "high_ms"}
            )
    elif metric == "rhr":
        try:
            records = raw["allMetrics"]["metricsMap"]["WELLNESS_RESTING_HEART_RATE"]
        except (KeyError, TypeError):
            raise AppError("INVALID_RESPONSE") from None
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            raise AppError("INVALID_RESPONSE")
        if not records:
            return "missing", {}
        for record in records:
            check_day(record, day)
        if len(records) != 1:
            raise AppError("INVALID_RESPONSE")
        data = fields(records[0], {"value": "bpm"})
    elif metric == "stress":
        data = fields(
            raw,
            {
                "avgStressLevel": "average",
                "maxStressLevel": "maximum",
                "restStressDuration": "rest_seconds",
                "lowStressDuration": "low_seconds",
                "mediumStressDuration": "medium_seconds",
                "highStressDuration": "high_seconds",
            },
        )
    elif metric == "training_status":
        recent = raw.get("mostRecentTrainingStatus")
        if recent is None and "mostRecentTrainingStatus" in raw:
            return "missing", {}
        if not isinstance(recent, dict) or "latestTrainingStatusData" not in recent:
            raise AppError("INVALID_RESPONSE")
        devices = recent["latestTrainingStatusData"]
        if devices is None or devices == {}:
            return "missing", {}
        if not isinstance(devices, dict):
            raise AppError("INVALID_RESPONSE")
        statuses = []
        for record in devices.values():
            if not isinstance(record, dict):
                raise AppError("INVALID_RESPONSE")
            # This endpoint is explicitly "most recent", possibly predating the query.
            observed = record.get("calendarDate")
            if observed:
                calendar_day(observed)
                if observed > day:
                    raise AppError("INPUT_MISMATCH")
            item = {"observed_date": observed}
            status = record.get("trainingStatus")
            if status is not None:
                item["garmin_status_code"] = number(status)
            phrase = record.get("trainingStatusFeedbackPhrase")
            if phrase is not None:
                item["garmin_label"] = text(phrase, 100)
            if len(item) > 1:
                statuses.append(item)
        data = {"statuses": statuses} if statuses else {}
    else:
        raise AppError("INVALID_INPUT")
    return ("ok" if data else "missing"), data


def activity_summary(record: dict, profile: Profile, start: str, end: str) -> dict | None:
    if not isinstance(record, dict) or not isinstance(record.get("activityType"), dict):
        raise AppError("INVALID_RESPONSE")
    sport = record["activityType"]
    kind = sport.get("typeKey")
    if kind not in RUN_TYPES and sport.get("parentTypeId") != 1:
        if not isinstance(kind, str):
            raise AppError("INVALID_RESPONSE")
        return None
    activity_id = record.get("activityId")
    if isinstance(activity_id, bool) or not re.fullmatch(r"\d+", str(activity_id)):
        raise AppError("INVALID_RESPONSE")
    local = record.get("startTimeLocal")
    gmt = record.get("startTimeGMT")
    try:
        if local:
            date_time = datetime.fromisoformat(local)
        elif gmt:
            instant = datetime.fromisoformat(gmt)
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=UTC)
            date_time = instant.astimezone(ZoneInfo(profile.timezone))
        else:
            raise ValueError
    except (ValueError, TypeError):
        raise AppError("INVALID_RESPONSE") from None
    day = date_time.date().isoformat()
    if not start <= day <= end:
        raise AppError("INPUT_MISMATCH")
    result = {
        "id": str(activity_id),
        "date": day,
        "start_local": date_time.isoformat(),
        "type": kind,
    }
    for source, target in {
        "distance": "distance_m",
        "duration": "duration_seconds",
        "movingDuration": "moving_seconds",
        "averageHR": "average_hr",
        "maxHR": "max_hr",
        "elevationGain": "elevation_gain_m",
        "aerobicTrainingEffect": "aerobic_training_effect",
        "anaerobicTrainingEffect": "anaerobic_training_effect",
    }.items():
        value = number(record.get(source))
        if value is not None:
            result[target] = value
    return result


def family_of(record: dict) -> str:
    marker = record.get("trainingPlanClassification") or record.get("planType") or ""
    if not isinstance(marker, str):
        raise AppError("INVALID_RESPONSE")
    marker = marker.upper()
    if marker in {"PHASED", "PHASED_TRAINING_PLAN"}:
        return "phased"
    if marker in {"FBT_ADAPTIVE", "ADAPTIVE", "COACH"}:
        return "adaptive"
    if marker in {"ATP", "ADAPTIVE_TRAINING_PLAN"} or record.get("adaptiveTrainingPlan"):
        return "atp"
    return "unknown"


def task_summary(record: dict, start: str, end: str) -> dict | None:
    if not isinstance(record, dict):
        raise AppError("INVALID_RESPONSE")
    day = record.get("scheduleDate") or record.get("calendarDate")
    if not isinstance(day, str):
        raise AppError("INVALID_RESPONSE")
    day = day[:10]
    calendar_day(day)
    if not start <= day <= end:
        return None
    workout = record.get("taskWorkout", record)
    if not isinstance(workout, dict):
        raise AppError("INVALID_RESPONSE")
    result = {"date": day}
    for key, target in {
        "workoutName": "name",
        "workoutType": "type",
        "workoutDescription": "description",
    }.items():
        if workout.get(key) is not None:
            result[target] = text(workout[key])
    for key in ("workoutUuid", "workoutId"):
        if workout.get(key) is not None:
            result["workout_id"] = text(str(workout[key]), 80)
            break
    if "restDay" in workout:
        if not isinstance(workout["restDay"], bool):
            raise AppError("INVALID_RESPONSE")
        result["rest_day"] = workout["restDay"]
    for source, target in {
        "estimatedDurationInSecs": "estimated_seconds",
        "estimatedDistanceInMeters": "estimated_distance_m",
    }.items():
        value = number(workout.get(source))
        if value is not None:
            result[target] = value
    return result


def plan_summary(record: dict, start: str, end: str, *, rest: bool = False) -> dict:
    if not isinstance(record, dict):
        raise AppError("INVALID_RESPONSE")
    identifier = record.get("trainingPlanId")
    if isinstance(identifier, bool) or not isinstance(identifier, (int, str)):
        raise AppError("INVALID_RESPONSE")
    result = {
        "id": str(identifier),
        "family": family_of(record),
        "name": text(record.get("planName") or record.get("name"), 120),
    }
    details = record.get("trainingPlanDetailsDTO") or {}
    if not isinstance(details, dict):
        raise AppError("INVALID_RESPONSE")
    adaptive = record.get("adaptiveTrainingPlan")
    if adaptive is not None:
        if not isinstance(adaptive, (dict, bool)):
            raise AppError("INVALID_RESPONSE")
        result["adaptive_training_plan"] = True
        if isinstance(adaptive, dict):
            details = {**details, **adaptive}
    metadata = {}
    for key in ("trainingType", "athletePlanId", "workoutsPerWeek", "goalType"):
        value = details.get(key)
        if value is not None:
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                raise AppError("INVALID_RESPONSE")
            metadata[key] = text(value, 100) if isinstance(value, str) else number(value)
    result["metadata"] = metadata
    key = "taskList" if rest else "workoutScheduleSummaries"
    records = record.get(key)
    if not isinstance(records, list):
        raise AppError("INVALID_RESPONSE")
    tasks = [task_summary(item, start, end) for item in records]
    result["tasks"] = [item for item in tasks if item is not None]
    return result


def graphql_plans(raw, start: str, end: str) -> list[dict]:
    if not isinstance(raw, dict) or raw.get("errors"):
        raise AppError("INVALID_RESPONSE")
    try:
        scalar = raw["data"]["trainingPlanScalar"]
        records = scalar["trainingPlanWorkoutScheduleDTOS"]
    except (KeyError, TypeError):
        raise AppError("INVALID_RESPONSE") from None
    if not isinstance(records, list):
        raise AppError("INVALID_RESPONSE")
    return [plan_summary(record, start, end) for record in records]


def workout_summary(raw) -> dict:
    if not isinstance(raw, dict):
        raise AppError("INVALID_RESPONSE")
    if raw.get("restDay") is True:
        return {"rest_day": True, "steps": []}
    segments = raw.get("workoutSegments")
    if not isinstance(segments, list):
        raise AppError("INVALID_RESPONSE")
    count = 0

    def steps(records, depth=0):
        nonlocal count
        if not isinstance(records, list) or depth > 6:
            raise AppError("INVALID_RESPONSE")
        result = []
        for record in records:
            count += 1
            if count > 128 or not isinstance(record, dict):
                raise AppError("INVALID_RESPONSE")
            item = {}
            for source, target, sub in (
                ("stepType", "type", "stepTypeKey"),
                ("endCondition", "condition", "conditionTypeKey"),
                ("targetType", "target_type", "workoutTargetTypeKey"),
            ):
                container = record.get(source)
                if container is not None:
                    if not isinstance(container, dict):
                        raise AppError("INVALID_RESPONSE")
                    item[target] = text(container.get(sub), 80)
            for key in (
                "endConditionValue",
                "targetValueOne",
                "targetValueTwo",
                "zoneNumber",
                "numberOfIterations",
            ):
                value = number(record.get(key))
                if value is not None:
                    item[key] = value
            if "workoutSteps" in record:
                item["steps"] = steps(record["workoutSteps"], depth + 1)
            if not item:
                raise AppError("INVALID_RESPONSE")
            result.append(item)
        return result

    result = {
        "name": text(raw.get("workoutName"), 120),
        "description": text(raw.get("workoutDescription")),
        "segments": [],
    }
    for segment in segments:
        if not isinstance(segment, dict):
            raise AppError("INVALID_RESPONSE")
        result["segments"].append(steps(segment.get("workoutSteps")))
    return result
