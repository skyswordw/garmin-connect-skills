"""Fictional, offline examples. Never reads an account or credentials."""

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from . import __version__
from .engine import Engine
from .models import METRICS, Profile, day_range
from .reports import publish_weekly
from .storage import Store


class FictionalBackend:
    def daily(self, metric, day):
        index = int(day[-2:]) % 7
        if metric == "sleep":
            return {
                "dailySleepDTO": {
                    "calendarDate": day,
                    "sleepTimeSeconds": 25200 + index * 300,
                    "sleepScores": {"overall": {"value": 75 + index}},
                }
            }
        if metric == "hrv":
            if index == 3:
                return {"hrvSummary": None}
            return {
                "hrvSummary": {
                    "calendarDate": day,
                    "lastNightAvg": 42 + index,
                    "weeklyAvg": 45,
                    "status": "BALANCED",
                }
            }
        if metric == "rhr":
            return {
                "allMetrics": {
                    "metricsMap": {
                        "WELLNESS_RESTING_HEART_RATE": [
                            {"calendarDate": day, "value": 52 + index % 3}
                        ]
                    }
                }
            }
        if metric == "stress":
            return {"calendarDate": day, "avgStressLevel": 25 + index, "maxStressLevel": 65}
        if metric == "body_battery":
            return [
                {
                    "date": day,
                    "charged": 58,
                    "drained": 45,
                    "bodyBatteryValuesArray": [[0, 73], [1, 28]],
                }
            ]
        if metric == "readiness":
            return [
                {"calendarDate": day, "score": 60 + index, "inputContext": "AFTER_WAKEUP_RESET"}
            ]
        return {
            "mostRecentTrainingStatus": {
                "latestTrainingStatusData": {
                    "fictional-device": {
                        "calendarDate": day,
                        "trainingStatus": 1,
                        "trainingStatusFeedbackPhrase": "MAINTAINING",
                    }
                }
            }
        }

    def activity_page(self, start, end, offset, limit):
        if offset:
            return []
        days = day_range(start, end)
        return [
            {
                "activityId": 90001 + index,
                "startTimeLocal": f"{days[index]} 07:00:00",
                "activityType": {"typeKey": "running"},
                "distance": 5000 + index * 500,
                "duration": 1800 + index * 180,
                "averageHR": 140 + index,
            }
            for index in (0, 2, 5)
            if index < len(days)
        ]

    def plan_calendar(self, anchor):
        return {
            "data": {
                "trainingPlanScalar": {
                    "trainingPlanWorkoutScheduleDTOS": [
                        {
                            "trainingPlanId": 70001,
                            "planName": "虚构 Coach 计划",
                            "trainingPlanClassification": "FBT_ADAPTIVE",
                            "trainingPlanDetailsDTO": {
                                "trainingType": "RUNNING",
                                "workoutsPerWeek": 3,
                            },
                            "workoutScheduleSummaries": [
                                {
                                    "scheduleDate": anchor,
                                    "workoutName": "轻松跑",
                                    "estimatedDurationInSecs": 1800,
                                }
                            ],
                        }
                    ]
                }
            }
        }


class DemoEngine(Engine):
    def snapshot(self, *args, **kwargs):
        result = super().snapshot(*args, **kwargs)
        result.provider = "fictional"
        result.provider_version = __version__
        return result


def generate(output: Path, *, revision: bool = False) -> tuple[Path, str]:
    profile = Profile("1" * 32, "demo", "cn", "Asia/Shanghai")
    monday = profile.today() - timedelta(days=profile.today().weekday() + 7)
    start, end = monday.isoformat(), (monday + timedelta(days=6)).isoformat()
    with TemporaryDirectory(prefix="garmin-skills-demo-") as name:
        store = Store(Path(name).resolve())
        engine = DemoEngine(store, profile, factory=FictionalBackend)
        selections = engine.daily(start, end, list(METRICS))
        selections += [engine.runs(start, end), engine.plans(start, end)]
        return publish_weekly(
            store, profile, start, end, selections, output=output, revision=revision, fictional=True
        )
