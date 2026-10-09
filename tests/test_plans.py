import pytest

from garmin_connect_skills.demo import FictionalBackend
from garmin_connect_skills.engine import Engine
from garmin_connect_skills.errors import AppError

EMPTY = {"data": {"trainingPlanScalar": {"trainingPlanWorkoutScheduleDTOS": []}}}


def test_atp_metadata_and_rest_day_are_preserved(store, profile):
    class Fake(FictionalBackend):
        calls = []

        def plan_calendar(self, anchor):
            self.calls.append(anchor)
            return {
                "data": {
                    "trainingPlanScalar": {
                        "trainingPlanWorkoutScheduleDTOS": [
                            {
                                "trainingPlanId": 12,
                                "planName": "虚构 ATP",
                                "trainingPlanClassification": "ATP",
                                "adaptiveTrainingPlan": {"athletePlanId": 98, "workoutsPerWeek": 4},
                                "trainingPlanDetailsDTO": {"trainingType": "RUNNING"},
                                "workoutScheduleSummaries": [
                                    {
                                        "scheduleDate": anchor,
                                        "restDay": True,
                                        "workoutUuid": "00000000-0000-0000-0000-000000000001",
                                    }
                                ],
                            }
                        ]
                    }
                }
            }

        def plan_list(self):
            pytest.fail("valid ATP must not be replaced by REST list")

    backend = Fake()
    snapshot = (
        Engine(store, profile, factory=lambda: backend).plans("2026-10-09", "2026-10-10").snapshot
    )
    plan = snapshot.data["plans"][0]
    assert snapshot.status == "ok" and snapshot.coverage == backend.calls
    assert plan["family"] == "atp" and plan["metadata"]["athletePlanId"] == 98
    assert all(t["rest_day"] is True for t in plan["tasks"]) and len(plan["tasks"]) == 2


@pytest.mark.parametrize(
    "family,classification", [("phased", "PHASED"), ("adaptive", "FBT_ADAPTIVE")]
)
def test_rest_plan_dispatch_by_family(store, profile, family, classification):
    class Fake:
        def plan_calendar(self, anchor):
            return EMPTY

        def plan_list(self):
            return {
                "trainingPlanList": [
                    {"trainingPlanId": 12, "trainingPlanClassification": classification}
                ]
            }

        def plan_detail(self, plan_id, selected):
            assert plan_id == "12" and selected == family
            return {
                "trainingPlanId": 12,
                "name": "虚构计划",
                "taskList": [
                    {
                        "calendarDate": "2026-10-09",
                        "taskWorkout": {
                            "workoutName": "Base",
                            "workoutDescription": "Unknown grammar: keep me",
                            "estimatedDurationInSecs": 1800,
                        },
                    }
                ],
            }

    result = Engine(store, profile, factory=Fake).plans("2026-10-09", "2026-10-09").snapshot
    assert result.status == "ok" and result.data["plans"][0]["family"] == family
    task = result.data["plans"][0]["tasks"][0]
    assert task["description"] == "Unknown grammar: keep me" and "warmup" not in task


def test_rest_empty_cannot_mask_failed_graphql(store, profile):
    class Fake:
        def plan_calendar(self, anchor):
            raise AppError("AUTH_REQUIRED")

        def plan_list(self):
            pytest.fail("must not turn failed GraphQL into no plan")

    result = Engine(store, profile, factory=Fake).plans("2026-10-09", "2026-10-09").snapshot
    assert result.status == "error" and not result.complete


def test_both_successful_empty_sources_confirm_empty(store, profile):
    class Fake:
        def plan_calendar(self, anchor):
            return EMPTY

        def plan_list(self):
            return {"trainingPlanList": []}

    result = Engine(store, profile, factory=Fake).plans("2026-10-09", "2026-10-09").snapshot
    assert result.status == "empty" and result.complete


def test_detail_failure_and_unknown_family_are_explicit(store, profile):
    class Fake:
        family = "PHASED"

        def plan_calendar(self, anchor):
            return EMPTY

        def plan_list(self):
            return {"trainingPlanList": [{"trainingPlanId": 12, "planType": self.family}]}

        def plan_detail(self, *args):
            raise AppError("INVALID_RESPONSE")

    backend = Fake()
    result = (
        Engine(store, profile, factory=lambda: backend).plans("2026-10-09", "2026-10-09").snapshot
    )
    assert result.status == "error" and not result.complete
    backend.family = "UNKNOWN_FAMILY"
    result = (
        Engine(store, profile, refresh=True, factory=lambda: backend)
        .plans("2026-10-09", "2026-10-09")
        .snapshot
    )
    assert result.status == "unsupported" and not result.complete


def test_workout_cache_is_keyed_by_id(store, profile):
    class Fake:
        def workout(self, identifier):
            return {
                "workoutName": identifier,
                "workoutSegments": [
                    {
                        "workoutSteps": [
                            {
                                "stepType": {"stepTypeKey": "interval"},
                                "endCondition": {"conditionTypeKey": "time"},
                                "endConditionValue": 1800,
                            }
                        ]
                    }
                ],
            }

    engine = Engine(store, profile, factory=Fake)
    a = engine.workout("101", "2026-10-09")
    b = engine.workout("102", "2026-10-09")
    assert a.snapshot.data["workout_id"] == "101" and b.snapshot.data["workout_id"] == "102"
    assert (
        Engine(store, profile, offline=True).workout("101", "2026-10-09").snapshot.variant == "101"
    )


def test_historical_rest_plans_outside_window_do_not_trigger_detail_downloads(store, profile):
    class Fake:
        def plan_calendar(self, anchor):
            return EMPTY

        def plan_list(self):
            return {
                "trainingPlanList": [
                    {"trainingPlanId": i, "planType": "PHASED", "endDate": "2025-12-31"}
                    for i in range(100)
                ]
            }

        def plan_detail(self, *args):
            pytest.fail("out-of-window plans must not be downloaded")

    result = Engine(store, profile, factory=Fake).plans("2026-10-09", "2026-10-09").snapshot
    assert result.status == "empty" and result.complete


def test_rest_detail_requests_are_bounded(store, profile):
    class Fake:
        calls = []

        def plan_calendar(self, anchor):
            return EMPTY

        def plan_list(self):
            return {
                "trainingPlanList": [
                    {"trainingPlanId": i, "planType": "PHASED"} for i in range(1, 10)
                ]
            }

        def plan_detail(self, plan_id, family):
            self.calls.append(plan_id)
            return {"trainingPlanId": int(plan_id), "taskList": []}

    backend = Fake()
    result = (
        Engine(store, profile, factory=lambda: backend).plans("2026-10-09", "2026-10-09").snapshot
    )
    assert (
        len(backend.calls) == 3 and result.error["code"] == "REQUEST_BUDGET" and not result.complete
    )
