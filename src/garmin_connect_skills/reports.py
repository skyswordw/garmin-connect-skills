"""Deterministic Chinese facts with portable sources and no-overwrite publication."""

import html
import re
from pathlib import Path
from statistics import mean

from .errors import AppError
from .models import METRICS, Profile, Selection, day_range, utcnow
from .storage import Store, atomic_write, canonical, private_dir, safe_path

LABELS = {
    "sleep": "睡眠",
    "hrv": "HRV",
    "rhr": "静息心率",
    "stress": "压力",
    "body_battery": "Body Battery",
    "readiness": "训练准备度",
    "training_status": "训练状态",
    "runs": "跑步",
    "plan": "训练计划",
    "workout": "任务详情",
}
STATUS = {
    "ok": "有效",
    "empty": "无记录",
    "missing": "未提供",
    "unsupported": "暂不支持",
    "error": "获取失败",
    "not_requested": "未请求",
}


def escape(value) -> str:
    value = html.escape(str(value), quote=False).replace("\n", " ")
    return re.sub(r"([\\`*\[\]_|])", r"\\\1", value)


def fact(kind: str, data: dict) -> str:
    if kind == "sleep":
        hours = data.get("duration_seconds")
        result = f"{hours / 3600:.1f} 小时" if hours is not None else "时长未提供"
        if "score" in data:
            result += f" · {data['score']:g} 分"
        return result
    if kind == "hrv":
        value = data.get("last_night_ms")
        return f"{value:g} ms" if value is not None else "昨夜均值未提供"
    if kind == "rhr":
        return f"{data['bpm']:g} bpm" if "bpm" in data else "未提供"
    if kind == "stress":
        return f"平均 {data['average']:g}" if "average" in data else "均值未提供"
    if kind == "body_battery":
        return (
            " / ".join(
                f"{label} {data[key]:g}"
                for key, label in (
                    ("first", "始"),
                    ("last", "末"),
                    ("charged", "充"),
                    ("drained", "耗"),
                )
                if key in data
            )
            or "未提供"
        )
    if kind == "readiness":
        value = data.get("score")
        return (f"{value:g} 分" if value is not None else "分数未提供") + (
            "（晨间）" if data.get("context") == "morning" else "（最近返回）"
        )
    if kind == "training_status":
        return "; ".join(
            str(row.get("garmin_label") or f"Garmin 代码 {row.get('garmin_status_code')}")
            + (f"（{row['observed_date']}）" if row.get("observed_date") else "（观察日期未提供）")
            for row in data.get("statuses", [])
        )
    if kind == "runs":
        return f"已返回 {len(data.get('activities', []))} 次跑步"
    if kind == "plan":
        plans = data.get("plans", [])
        return f"{len(plans)} 个计划，{sum(len(p['tasks']) for p in plans)} 项窗口内任务"
    return "任务详情已获取；请查看 JSON 中的原始目标类型与单位"


def selection_text(selection: Selection) -> str:
    snapshot = selection.snapshot
    result = (
        fact(snapshot.kind, snapshot.data) if snapshot.status == "ok" else STATUS[snapshot.status]
    )
    if not snapshot.complete and snapshot.status == "ok":
        result += "（覆盖不完整）"
    if snapshot.error:
        result += f" · {snapshot.error['code']}"
    if selection.stale:
        result += " · 旧摘要"
    if selection.update_error:
        result += f" · 更新失败 {selection.update_error['code']}"
    return result


def render_query(profile: Profile, selections: list[Selection]) -> str:
    lines = [
        f"# Garmin 摘要 · {profile.alias} / {profile.region}",
        "",
        f"时区：{profile.timezone}。每项日期、截至时间与来源分别列出。",
        "",
        "| 日期范围 | 项目 | 结果 | 抓取时间（UTC） |",
        "| --- | --- | --- | --- |",
    ]
    details = []
    for selection in selections:
        s = selection.snapshot
        lines.append(
            f"| {s.start} — {s.end} | {LABELS[s.kind]} | "
            f"{escape(selection_text(selection))} | {s.fetched_at} |"
        )
        if s.kind == "plan" and s.data.get("plans"):
            for plan in s.data["plans"]:
                details += ["", f"**{escape(plan.get('name') or plan['id'])}** · {plan['family']}"]
                for task in plan["tasks"]:
                    name = "休息日" if task.get("rest_day") else task.get("name") or "未命名任务"
                    detail = (
                        f" · 估计 {task['estimated_seconds'] / 60:g} 分钟"
                        if ("estimated_seconds" in task)
                        else ""
                    )
                    identifier = (
                        f" · ID `{escape(task['workout_id'])}`" if task.get("workout_id") else ""
                    )
                    details.append(f"- {task['date']}：{escape(name)}{detail}{identifier}")
        if s.error:
            details += ["", s.error["message"] + s.error["action"]]
        if selection.update_error:
            details += ["", selection.update_error["message"] + selection.update_error["action"]]
    return "\n".join(lines + details) + "\n"


def build_weekly(
    profile: Profile, start: str, end: str, selections: list[Selection], *, fictional: bool = False
) -> tuple[str, dict, dict]:
    days = day_range(start, end, limit=7)
    if len(days) != 7:
        raise AppError("INVALID_INPUT")
    accepted = []
    rejected = []
    sources = {}
    for selected in selections:
        snapshot = selected.snapshot
        try:
            snapshot.validate(profile)
            if snapshot.kind in METRICS:
                if snapshot.start != snapshot.end or snapshot.start not in days:
                    raise AppError("INPUT_MISMATCH")
            elif snapshot.kind in {"runs", "plan"}:
                if (snapshot.start, snapshot.end) != (start, end):
                    raise AppError("INPUT_MISMATCH")
            else:
                continue
            value = snapshot.as_dict()
            if selected.attempt:
                selected.attempt.validate(profile)
                if (selected.attempt.kind, selected.attempt.start, selected.attempt.end) != (
                    snapshot.kind,
                    snapshot.start,
                    snapshot.end,
                ):
                    raise AppError("INPUT_MISMATCH")
                attempt = selected.attempt.as_dict()
                sources[attempt["id"]] = attempt
            selected.stale = not snapshot.fresh(profile)
            accepted.append(selected)
            sources[value["id"]] = value
        except AppError:
            rejected.append({"kind": snapshot.kind, "code": "INPUT_MISMATCH"})
    if not any(
        item.snapshot.status in {"ok", "empty"}
        or (item.snapshot.kind == "runs" and item.snapshot.data.get("activities"))
        for item in accepted
    ):
        raise AppError("NO_VALID_DATA")
    by_key = {}
    for item in accepted:
        key = (item.snapshot.kind, item.snapshot.start)
        if key in by_key:
            raise AppError("INPUT_MISMATCH")
        by_key[key] = item
    title = "示例数据 · 训练周报" if fictional else "训练周报"
    lines = [f"# {title} · {start} — {end}", ""]
    if fictional:
        lines += ["> 以下数据完全虚构，用于体验和离线验证。", ""]
    lines += [
        f"账号档案：{profile.alias} · 区域：{profile.region} · 时区：{profile.timezone}",
        f"生成时间：{utcnow().isoformat()}。各输入截至时间见 [来源清单](manifest.json)。",
        "",
        "## 跑步事实",
        "",
    ]
    runs = by_key.get(("runs", start))
    if not runs:
        lines.append("跑步次数、距离与时长：无法确认（缺少匹配范围的输入）。")
    else:
        s = runs.snapshot
        activities = s.data.get("activities", [])
        complete = s.status in {"ok", "empty"} and s.complete
        if complete:
            lines.append(f"- 跑步次数：{len(activities)} 次。")
        else:
            lines.append(f"- 完整跑步次数：无法确认；已确认 {len(activities)} 次（抓取不完整）。")
        for key, label, scale, unit in (
            ("distance_m", "距离", 1000, "km"),
            ("duration_seconds", "计时时长", 60, "分钟"),
        ):
            values = [a[key] for a in activities if key in a]
            if complete and len(values) == len(activities):
                lines.append(f"- {label}：{sum(values) / scale:.1f} {unit}。")
            elif values:
                lines.append(
                    f"- 已确认{label}：至少 {sum(values) / scale:.1f} {unit}；完整总量未知。"
                )
            else:
                lines.append(f"- {label}：无法确认。")
        if runs.stale or runs.update_error:
            lines.append(f"- 使用截至 {s.fetched_at} 的记录；{escape(selection_text(runs))}。")
    lines += [
        "",
        "## 恢复事实",
        "",
        "| 日期 | " + " | ".join(LABELS[m] for m in METRICS) + " |",
        "| --- | " + " | ".join("---" for _ in METRICS) + " |",
    ]
    for day in days:
        cells = []
        for metric in METRICS:
            item = by_key.get((metric, day))
            if item:
                identifier = item.snapshot.as_dict()["id"]
                cells.append(f"[{escape(selection_text(item))}](sources/{identifier}.json)")
            else:
                cells.append("未请求或无匹配输入")
        lines.append(f"| {day} | " + " | ".join(cells) + " |")
    lines += ["", "指标均值仅使用有效样本，不补零：", ""]
    for metric, key, scale, unit in (
        ("sleep", "duration_seconds", 3600, "小时"),
        ("hrv", "last_night_ms", 1, "ms"),
        ("rhr", "bpm", 1, "bpm"),
    ):
        values = [
            i.snapshot.data[key] / scale
            for i in accepted
            if i.snapshot.kind == metric and i.snapshot.status == "ok" and key in i.snapshot.data
        ]
        if values:
            lines.append(f"- {LABELS[metric]}：{mean(values):.1f} {unit}（{len(values)}/7 天）。")
    lines += ["", "## 计划与近期任务", ""]
    plan = by_key.get(("plan", start))
    if plan and plan.snapshot.status == "empty" and plan.snapshot.complete:
        lines.append("在本次查询范围内，接口确认无计划记录。")
    elif plan and plan.snapshot.data.get("plans"):
        for record in plan.snapshot.data["plans"]:
            lines += [f"**{escape(record.get('name') or record['id'])}** · {record['family']}", ""]
            if not record["tasks"]:
                lines.append("该窗口未返回任务；这不等于每天都是休息日。")
            for task in sorted(record["tasks"], key=lambda row: row["date"]):
                name = "休息日" if task.get("rest_day") else task.get("name") or "未命名任务"
                estimate = (
                    f"，Garmin 估计 {task['estimated_seconds'] / 60:g} 分钟"
                    if "estimated_seconds" in task
                    else "，时长/目标未提供"
                )
                lines.append(f"- {task['date']}：{escape(name)}{estimate}。")
            lines.append("")
        if plan.snapshot.status != "ok" or not plan.snapshot.complete:
            lines.append("计划窗口获取不完整，任务仅为已确认部分。")
    else:
        lines.append("训练计划：无法确认或未请求，不推断未加入计划。")
    lines += ["", "自适应计划可能调整；这里列出截至抓取时可见的安排。", "", "## 缺失与限制", ""]
    limitations = []
    for item in accepted:
        s = item.snapshot
        if s.status != "ok" or not s.complete or item.stale or item.update_error:
            if s.status == "empty" and s.complete and not item.stale and not item.update_error:
                continue
            limitations.append(
                f"- {s.start} — {s.end} · {LABELS[s.kind]}：{escape(selection_text(item))}。"
            )
    limitations += [f"- {escape(r['kind'])}：拒绝不匹配输入（INPUT_MISMATCH）。" for r in rejected]
    requested = {i.snapshot.kind for i in accepted}
    absent = [LABELS[m] for m in (*METRICS, "runs", "plan") if m not in requested]
    if absent:
        limitations.append("- 未请求或缺少匹配输入：" + "、".join(absent) + "。")
    lines += limitations or ["- 本次所选输入均有效；设备同步滞后仍可能改变历史记录。"]
    lines += [
        "",
        "## 解读依据",
        "",
        "以上是数据事实。单周摘要不足以建立个人基线；配速快慢、Garmin 分数或单项变化，"
        "不能单独判定训练强度和恢复好坏。解释与建议应结合近期记录、体感和原计划，并注明推断。",
        "",
        "运动参考，不作医疗诊断。",
        "",
        "## 来源",
        "",
        "[来源清单](manifest.json)包含逐项日期覆盖、抓取时间、获取状态、"
        "完整 hash 和相对引用。随报告保留 sources 目录即可独立核对。",
        "",
    ]
    manifest = {
        "schema_version": 1,
        "fictional": fictional,
        "profile_id": profile.id,
        "profile_alias": profile.alias,
        "region": profile.region,
        "timezone": profile.timezone,
        "start": start,
        "end": end,
        "generated_at": utcnow().isoformat(),
        "inputs": [i.as_dict() for i in accepted],
        "rejected": rejected,
        "sources": [{"id": key, "path": f"sources/{key}.json"} for key in sources],
    }
    return "\n".join(lines), manifest, sources


def publish_weekly(
    store: Store,
    profile: Profile,
    start: str,
    end: str,
    selections: list[Selection],
    *,
    output: Path | None = None,
    revision: bool = False,
    fictional: bool = False,
) -> tuple[Path, str]:
    markdown, manifest, sources = build_weekly(profile, start, end, selections, fictional=fictional)
    base = output.expanduser() if output else store.folder(profile) / "reports"
    stem = f"{profile.alias}-{profile.region}-{start}_{end}"
    private_dir(base)
    serial = 1
    while True:
        target = base / (stem if serial == 1 else f"{stem}-r{serial}")
        safe_path(target)
        try:
            # Reserve the entire bundle before writing sources. Different state
            # roots can share one export directory despite their profile locks.
            target.mkdir(mode=0o700)
            break
        except FileExistsError:
            if not revision:
                raise AppError("REPORT_EXISTS") from None
            serial += 1
        except OSError:
            raise AppError("IO_ERROR") from None
    for identifier, value in sources.items():
        atomic_write(target / "sources" / f"{identifier}.json", canonical(value))
    atomic_write(target / "manifest.json", canonical(manifest))
    atomic_write(target / "weekly.md", markdown.encode(), exclusive=True)
    return target / "weekly.md", markdown
