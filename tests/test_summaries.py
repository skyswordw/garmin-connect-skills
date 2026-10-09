import pytest

from garmin_connect_skills.errors import AppError
from garmin_connect_skills.summaries import activity_summary, daily_summary, workout_summary


def test_sleep_zero_missing_and_invalid_are_distinct():
    assert daily_summary("sleep", {"dailySleepDTO": {"sleepTimeSeconds": 0}}, "2026-10-07") == (
        "ok",
        {"duration_seconds": 0},
    )
    assert daily_summary("sleep", {"dailySleepDTO": None}, "2026-10-07") == ("missing", {})
    with pytest.raises(AppError, match="结构"):
        daily_summary("sleep", {"unexpected": []}, "2026-10-07")


@pytest.mark.parametrize(
    "raw",
    [
        [],
        "secret-payload",
        {"dailySleepDTO": []},
        {"dailySleepDTO": {"sleepTimeSeconds": True}},
        {"dailySleepDTO": {"sleepTimeSeconds": float("nan")}},
        {"dailySleepDTO": {"sleepTimeSeconds": "25200"}},
    ],
)
def test_malformed_optional_response_not_zero(raw):
    with pytest.raises(AppError):
        daily_summary("sleep", raw, "2026-10-07")


def test_date_mismatch():
    with pytest.raises(AppError) as exc:
        daily_summary(
            "sleep",
            {"dailySleepDTO": {"calendarDate": "2026-10-06", "sleepTimeSeconds": 25200}},
            "2026-10-07",
        )
    assert exc.value.code == "INPUT_MISMATCH"


def test_hrv_missing_and_baseline():
    assert daily_summary("hrv", {"hrvSummary": None}, "2026-10-07")[0] == "missing"
    status, data = daily_summary(
        "hrv",
        {
            "hrvSummary": {
                "calendarDate": "2026-10-07",
                "lastNightAvg": 45,
                "baseline": {"balancedLow": 38, "balancedUpper": 54},
            }
        },
        "2026-10-07",
    )
    assert status == "ok" and data["garmin_baseline"] == {"low_ms": 38, "high_ms": 54}


def test_rhr_null_and_zero():
    def payload(value):
        return {
            "allMetrics": {
                "metricsMap": {
                    "WELLNESS_RESTING_HEART_RATE": [{"calendarDate": "2026-10-07", "value": value}]
                }
            }
        }

    assert daily_summary("rhr", payload(None), "2026-10-07") == ("missing", {})
    assert daily_summary("rhr", payload(0), "2026-10-07") == ("ok", {"bpm": 0})


def test_body_battery_drops_timeseries_and_identity():
    _, data = daily_summary(
        "body_battery",
        [
            {
                "date": "2026-10-07",
                "userProfilePK": 987,
                "charged": 0,
                "drained": 0,
                "bodyBatteryValuesArray": [[1, 0], [2, 45], [3, -1]],
            }
        ],
        "2026-10-07",
    )
    assert data == {"charged": 0, "drained": 0, "first": 0, "last": 45, "low": 0, "high": 45}


def test_readiness_selects_morning_and_status_preserves_observation_date():
    _, data = daily_summary(
        "readiness",
        [{"score": 80, "inputContext": "AFTER_WAKEUP_RESET"}, {"score": 70}],
        "2026-10-07",
    )
    assert data["score"] == 80 and data["context"] == "morning"
    _, data = daily_summary(
        "training_status",
        {
            "mostRecentTrainingStatus": {
                "latestTrainingStatusData": {
                    "device": {"calendarDate": "2026-10-05", "trainingStatus": 99}
                }
            }
        },
        "2026-10-07",
    )
    assert data["statuses"][0] == {"observed_date": "2026-10-05", "garmin_status_code": 99}


def test_activity_local_date_and_gmt_fallback(profile):
    base = {
        "activityId": 123,
        "activityType": {"typeKey": "running"},
        "distance": 0,
        "duration": 0,
        "activityName": "fictional private name",
        "startLatitude": 1,
    }
    data = activity_summary(
        {**base, "startTimeLocal": "2026-10-07 23:50:00"}, profile, "2026-10-07", "2026-10-07"
    )
    assert data["distance_m"] == 0 and "activityName" not in data and "startLatitude" not in data
    data = activity_summary(
        {**base, "startTimeGMT": "2026-10-07T17:00:00+00:00"}, profile, "2026-10-08", "2026-10-08"
    )
    assert data["date"] == "2026-10-08"


def test_workout_keeps_repeat_and_unknown_conditions_without_guessing():
    data = workout_summary(
        {
            "workoutName": "虚构间歇",
            "workoutSegments": [
                {
                    "workoutSteps": [
                        {
                            "numberOfIterations": 4,
                            "workoutSteps": [
                                {
                                    "stepType": {"stepTypeKey": "interval"},
                                    "endCondition": {"conditionTypeKey": "unknown-condition"},
                                    "endConditionValue": 100,
                                    "targetType": {"workoutTargetTypeKey": "pace.zone"},
                                    "targetValueOne": 3.0,
                                    "targetValueTwo": 3.5,
                                }
                            ],
                        }
                    ]
                }
            ],
        }
    )
    step = data["segments"][0][0]
    assert step["numberOfIterations"] == 4
    assert step["steps"][0]["condition"] == "unknown-condition"
    assert "duration_seconds" not in data and "warmup" not in data
    assert workout_summary({"restDay": True}) == {"rest_day": True, "steps": []}
