import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from garmin_connect_skills.demo import FictionalBackend
from garmin_connect_skills.engine import Engine
from garmin_connect_skills.errors import AppError
from garmin_connect_skills.models import Selection, Snapshot, utcnow
from garmin_connect_skills.reports import build_weekly, publish_weekly

START, END = "2026-09-28", "2026-10-04"


def test_success_envelope_without_activity_collection_is_not_accepted(store, profile):
    bad = Engine(store, profile).snapshot("runs", START, END, "ok", {"ok": False})
    _, manifest, sources = build_weekly(
        profile, START, END, daily(store, profile) + [Selection(bad)]
    )
    assert manifest["rejected"] == [{"kind": "runs", "code": "INPUT_MISMATCH"}]
    assert all(s["kind"] != "runs" for s in sources.values())


def daily(store, profile):
    return Engine(store, profile, factory=FictionalBackend).daily(
        START, END, ["sleep", "hrv", "rhr"]
    )


def test_failed_activities_and_plan_never_become_zero_or_no_plan(store, profile):
    selections = daily(store, profile)
    engine = Engine(store, profile)
    selections += [
        Selection(
            engine.snapshot(
                "runs", START, END, "error", {}, complete=False, error=AppError("AUTH_REQUIRED")
            )
        ),
        Selection(
            engine.snapshot(
                "plan", START, END, "error", {}, complete=False, error=AppError("NETWORK_ERROR")
            )
        ),
    ]
    markdown, manifest, _ = build_weekly(profile, START, END, selections)
    assert "完整跑步次数：无法确认" in markdown and "跑步次数：0" not in markdown
    assert "训练计划：无法确认" in markdown and "确认无计划" not in markdown
    assert manifest["region"] == "cn"
    assert any(
        i["snapshot"].get("error", {}).get("code") == "AUTH_REQUIRED"
        for i in manifest["inputs"]
        if i["snapshot"].get("error")
    )


def test_confirmed_empty_runs_can_be_zero(store, profile):
    engine = Engine(store, profile)
    runs = Selection(engine.snapshot("runs", START, END, "empty", {"activities": []}))
    markdown, _, _ = build_weekly(profile, START, END, [runs])
    assert "跑步次数：0 次" in markdown and "距离：0.0 km" in markdown


@pytest.mark.parametrize(
    "change",
    [{"region": "global"}, {"profile_id": "f" * 32}, {"timezone": "UTC"}, {"start": "2026-09-29"}],
)
def test_mixed_plan_is_rejected_without_losing_valid_health(store, profile, change):
    plan = Engine(store, profile).snapshot(
        "plan", START, END, "error", {}, complete=False, error=AppError("NETWORK_ERROR")
    )
    plan = replace(plan, **change)
    markdown, manifest, sources = build_weekly(
        profile, START, END, daily(store, profile) + [Selection(plan)]
    )
    assert manifest["rejected"] == [{"kind": "plan", "code": "INPUT_MISMATCH"}]
    assert all(source["kind"] != "plan" for source in sources.values())
    assert "拒绝不匹配输入" in markdown


def test_stale_plan_is_explicit_even_if_caller_does_not_mark_it(store, profile):
    selections = daily(store, profile)
    plan = Engine(store, profile).snapshot("plan", START, END, "empty", {"plans": []})
    plan.fetched_at = (utcnow() - timedelta(days=20)).isoformat()
    markdown, _, _ = build_weekly(profile, START, END, selections + [Selection(plan)])
    assert "旧摘要" in markdown


def test_no_valid_data_does_not_publish_report(store, profile, tmp_path):
    bad = Selection(
        Engine(store, profile).snapshot(
            "runs", START, END, "error", {}, complete=False, error=AppError("AUTH_REQUIRED")
        )
    )
    output = tmp_path.resolve() / "export"
    with pytest.raises(AppError) as error:
        publish_weekly(store, profile, START, END, [bad], output=output)
    assert error.value.code == "NO_VALID_DATA" and not output.exists()


def test_report_sources_portable_hashes_and_no_overwrite(store, profile, tmp_path):
    selections = daily(store, profile)
    selections += [Engine(store, profile, factory=FictionalBackend).runs(START, END)]
    output = tmp_path.resolve() / "export"
    path, markdown = publish_weekly(store, profile, START, END, selections, output=output)
    before = path.read_bytes()
    manifest = json.loads((path.parent / "manifest.json").read_text())
    assert str(tmp_path) not in markdown + json.dumps(manifest)
    for reference in manifest["sources"]:
        source = path.parent / reference["path"]
        snapshot = Snapshot.from_dict(json.loads(source.read_text()), profile)
        assert snapshot.as_dict()["id"] == reference["id"]
    with pytest.raises(AppError) as exc:
        publish_weekly(store, profile, START, END, selections, output=output)
    assert exc.value.code == "REPORT_EXISTS" and path.read_bytes() == before
    revised, _ = publish_weekly(
        store, profile, START, END, selections, output=output, revision=True
    )
    assert revised != path and revised.parent.name.endswith("-r2") and path.read_bytes() == before


def test_failed_refresh_source_is_exported_with_old_success(store, profile, tmp_path):
    selections = daily(store, profile)
    success = selections[0].snapshot
    attempt = replace(
        success,
        status="error",
        data={},
        complete=False,
        coverage=[],
        error=AppError("NETWORK_ERROR").as_dict(),
        fetched_at=utcnow().isoformat(),
    )
    selections[0] = Selection(success, True, False, attempt.error, attempt)
    path, _ = publish_weekly(
        store, profile, START, END, selections, output=tmp_path.resolve() / "export"
    )
    exported = json.loads((path.parent / "sources" / f"{attempt.as_dict()['id']}.json").read_text())
    assert exported["status"] == "error" and exported["error"]["code"] == "NETWORK_ERROR"


def test_concurrent_export_cannot_replace_another_reports_sources(
    store, profile, tmp_path, monkeypatch
):
    selections = daily(store, profile)
    output = tmp_path.resolve() / "export"
    target = output / f"{profile.alias}-{profile.region}-{START}_{END}"
    mkdir = Path.mkdir

    def competing_export(path, *args, **kwargs):
        if path == target:
            mkdir(path, *args, **kwargs)
            (path / "manifest.json").write_text("existing sources", encoding="utf-8")
            (path / "weekly.md").write_text("existing report", encoding="utf-8")
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", competing_export)
    with pytest.raises(AppError) as exc:
        publish_weekly(store, profile, START, END, selections, output=output)
    assert exc.value.code == "REPORT_EXISTS"
    assert (target / "manifest.json").read_text() == "existing sources"
    assert (target / "weekly.md").read_text() == "existing report"


def test_failed_revision_publication_preserves_original_report(
    store, profile, tmp_path, monkeypatch
):
    from garmin_connect_skills import reports

    selections = daily(store, profile)
    output = tmp_path.resolve() / "export"
    path, _ = publish_weekly(store, profile, START, END, selections, output=output)
    original = path.read_bytes()
    write = reports.atomic_write

    def fail_at_publish(target, content, **kwargs):
        if target.name == "weekly.md":
            raise AppError("IO_ERROR")
        return write(target, content, **kwargs)

    monkeypatch.setattr(reports, "atomic_write", fail_at_publish)
    with pytest.raises(AppError):
        publish_weekly(store, profile, START, END, selections, output=output, revision=True)
    assert path.read_bytes() == original
    assert not (output / f"{path.parent.name}-r2" / "weekly.md").exists()
