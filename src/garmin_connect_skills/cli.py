"""Terminal-first onboarding and a JSON interface for Agents."""

import argparse
import getpass
import json
import os
import sys
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path

from . import PROVIDER_VERSION, __version__
from .backend import GarminBackend
from .engine import Engine
from .errors import AppError
from .models import METRICS, calendar_day, day_range, validate_timezone
from .reports import publish_weekly, render_query
from .storage import Store


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default message echoes invalid argv, which may include secrets
        # accidentally pasted into a command. Help is available without echoing them.
        raise AppError("INVALID_INPUT")


def parser() -> argparse.ArgumentParser:
    root = Parser(description="中国区优先的 Garmin 本地摘要与中文周报。密码/MFA 仅在本地输入。")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--profile", help="选择账号档案；默认使用首次创建的档案")
    root.add_argument("--home", type=Path, help="自选独立状态目录（不放笔记库或仓库）")
    root.add_argument("--json", action="store_true", help="输出结构化 JSON，适合 Agent")
    commands = root.add_subparsers(dest="command", required=True, parser_class=Parser)
    auth = commands.add_parser("auth", help="本地登录和状态")
    auth_commands = auth.add_subparsers(dest="action", required=True, parser_class=Parser)
    login = auth_commands.add_parser("login", help="终端输入密码和 MFA，默认中国区")
    login.add_argument("--region", choices=("cn", "global"), help="新档案默认 cn；global 尚未实测")
    login.add_argument("--timezone", help="IANA 时区，例如 Asia/Shanghai；优先识别系统设置")
    login.add_argument("--reauth", action="store_true", help="主动重新认证；成功后才替换旧 token")
    login.add_argument("--strategy", choices=("auto", "mobile", "portal", "widget"), default="auto")
    status = auth_commands.add_parser("status", help="只检查本地状态，不联网")
    status.add_argument("--check", action="store_true", help="联网验证 token（不读取健康数据）")
    fetch = commands.add_parser("fetch", help="按需获取或读取已有摘要")
    kinds = fetch.add_subparsers(dest="kind", required=True, parser_class=Parser)
    for kind, description in (("daily", "日健康"), ("runs", "跑步"), ("plan", "Coach/计划日程")):
        item = kinds.add_parser(kind, help=description)
        add_dates(item)
        add_fetch_options(item)
        if kind == "daily":
            item.add_argument(
                "--metrics", default="sleep,hrv,rhr", help="逗号分隔：" + ",".join(METRICS)
            )
    workout = kinds.add_parser("workout", help="按 ID 读取一个任务的目标/步骤，不下载 FIT")
    workout.add_argument("id")
    workout.add_argument("--date", required=True, help="任务的日历日期")
    add_fetch_options(workout)
    report = commands.add_parser("report", help="中文事实周报")
    reports = report.add_subparsers(dest="action", required=True, parser_class=Parser)
    weekly = reports.add_parser("weekly", help="默认上一个完整周一至周日")
    weekly.add_argument("--week", help="指定周一的日期 YYYY-MM-DD")
    weekly.add_argument("--metrics", default=",".join(METRICS))
    weekly.add_argument("--no-plan", action="store_true", help="这次不查询训练计划")
    weekly.add_argument("--output", type=Path, help="额外保存位置；配套来源一并导出")
    weekly.add_argument("--revision", action="store_true", help="已有报告时生成新修订版")
    add_fetch_options(weekly)
    commands.add_parser("doctor", help="本地环境与配置检查，不读取 token 内容或健康数据")
    demo = commands.add_parser("demo", help="完全离线的虚构数据体验，无需账号")
    demo.add_argument("--output", type=Path, default=Path("demo-output"))
    demo.add_argument("--revision", action="store_true")
    return root


def add_dates(item):
    item.add_argument("--date", help="单日 YYYY-MM-DD")
    item.add_argument("--start", help="开始日（包含）")
    item.add_argument("--end", help="结束日（包含）")
    item.add_argument("--days", type=int, help="最近 N 天；计划则为从今天起 N 天（最多 31）")


def add_fetch_options(item):
    group = item.add_mutually_exclusive_group()
    group.add_argument("--offline", action="store_true", help="只读本地摘要，旧摘要明确标记")
    group.add_argument("--refresh", action="store_true", help="忽略缓存重新获取")


def timezone_hint() -> str | None:
    candidates = [os.environ.get("TZ")]
    try:
        target = str(Path("/etc/localtime").resolve())
        if "/zoneinfo/" in target:
            candidates.append(target.split("/zoneinfo/", 1)[1])
    except OSError:
        pass
    for candidate in candidates:
        if candidate:
            try:
                return validate_timezone(candidate)
            except AppError:
                continue
    return None


def date_window(args, profile) -> tuple[str, str]:
    if args.date:
        if args.start or args.end or args.days is not None:
            raise AppError("INVALID_INPUT")
        day_range(args.date, args.date)
        return args.date, args.date
    if args.start or args.end:
        if not (args.start and args.end) or args.days is not None:
            raise AppError("INVALID_INPUT")
        day_range(args.start, args.end)
        return args.start, args.end
    count = args.days if args.days is not None else {"daily": 1, "runs": 7, "plan": 14}[args.kind]
    if not 1 <= count <= 31:
        raise AppError("INVALID_INPUT")
    today = profile.today()
    start = today if args.kind == "plan" else today - timedelta(days=count - 1)
    end = today + timedelta(days=count - 1) if args.kind == "plan" else today
    return start.isoformat(), end.isoformat()


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def failed(selections) -> bool:
    return any(
        s.snapshot.status in {"error", "not_requested"} or s.update_error for s in selections
    )


def auth_command(args, store: Store):
    if args.action == "status":
        profile = store.get_profile(args.profile)
        saved = (store.folder(profile) / "auth" / "tokens.json").is_file()
        if args.check:
            with store.lock(profile):
                GarminBackend(store, profile).check()
        data = {
            "profile": profile.alias,
            "region": profile.region,
            "timezone": profile.timezone,
            "saved_token": saved,
            "verified_online": bool(args.check),
        }
        if args.json:
            print_json(data)
        else:
            print(f"档案 {profile.alias} · {profile.region} · {profile.timezone}")
            print("已保存本地 token。" if saved else "尚未登录，请运行 auth login。")
            print("本次已联网验证。" if args.check else "仅检查本地状态，未联网验证。")
        return 0
    if not sys.stdin.isatty():
        raise AppError("AUTH_REQUIRED")
    try:
        profile = store.get_profile(args.profile)
        if (args.region and args.region != profile.region) or (
            args.timezone and args.timezone != profile.timezone
        ):
            raise AppError("INPUT_MISMATCH")
    except AppError as error:
        if error.code != "NOT_FOUND":
            raise
        timezone = args.timezone or timezone_hint()
        if not timezone:
            timezone = input("你的 IANA 时区（中国大陆通常为 Asia/Shanghai）：").strip()
        profile = store.create_profile(args.profile or "main", args.region or "cn", timezone)
    with store.lock(profile):
        backend = GarminBackend(store, profile)
        reused = False
        if not args.reauth and (store.folder(profile) / "auth" / "tokens.json").exists():
            try:
                backend.check()
                reused = True
            except AppError as error:
                if error.code != "AUTH_REQUIRED":
                    raise
                backend = GarminBackend(store, profile)
        if not reused:
            print(
                f"本地登录 · {profile.region} · {profile.timezone}。密码和 MFA 不会保存或显示。",
                file=sys.stderr,
            )
            email = getpass.getpass("Garmin 邮箱（隐藏输入）：").strip()
            password = getpass.getpass("Garmin 密码：")
            if not email or not password:
                raise AppError("INVALID_INPUT")
            try:
                profile = backend.login(
                    email,
                    password,
                    lambda: getpass.getpass("MFA 验证码（留空取消）：").strip(),
                    args.strategy,
                )
            finally:
                password = None
                email = None
    data = {
        "status": "ok",
        "profile": profile.alias,
        "region": profile.region,
        "timezone": profile.timezone,
        "reused_token": reused,
    }
    print_json(data) if args.json else print("登录状态有效。可以运行 fetch daily 或 fetch runs。")
    return 0


def run(args) -> int:
    store = Store(args.home)
    if args.command == "demo":
        from .demo import generate

        path, markdown = generate(args.output, revision=args.revision)
        if args.json:
            print_json({"fictional": True, "report": f"{path.parent.name}/{path.name}"})
        else:
            print(markdown)
            print(f"已保存：{path.parent.name}/weekly.md（位于你选择的输出目录）。")
        return 0
    if args.command == "doctor":
        config = store.profiles()
        rows = [
            {"alias": p["alias"], "region": p["region"], "timezone": p["timezone"]}
            for p in config["profiles"].values()
        ]
        data = {
            "version": __version__,
            "python": sys.version.split()[0],
            "garminconnect": version("garminconnect"),
            "dependency_matches": version("garminconnect") == PROVIDER_VERSION,
            "profiles": rows,
            "network_checked": False,
            "next": "auth login" if not rows else "fetch daily",
        }
        print_json(data) if args.json else print(
            f"garmin-skills {__version__} · Python {data['python']} · "
            f"garminconnect {data['garminconnect']}\n"
            f"本地档案：{len(rows)} 个；未联网。下一步：{data['next']}。"
        )
        return 0 if data["dependency_matches"] else 2
    if args.command == "auth":
        return auth_command(args, store)
    profile = store.get_profile(args.profile)
    with store.lock(profile):
        engine = Engine(store, profile, offline=args.offline, refresh=args.refresh)
        if args.command == "fetch":
            if args.kind == "workout":
                selections = [engine.workout(args.id, args.date)]
            else:
                start, end = date_window(args, profile)
                if args.kind == "daily":
                    selections = engine.daily(start, end, args.metrics.split(","))
                elif args.kind == "runs":
                    selections = [engine.runs(start, end)]
                else:
                    selections = [engine.plans(start, end)]
            if args.json:
                print_json(
                    {
                        "status": "partial" if failed(selections) else "ok",
                        "profile": profile.alias,
                        "region": profile.region,
                        "timezone": profile.timezone,
                        "items": [s.as_dict() for s in selections],
                    }
                )
            else:
                print(render_query(profile, selections))
            return 2 if failed(selections) else 0
        monday = (
            calendar_day(args.week)
            if args.week
            else (profile.today() - timedelta(days=profile.today().weekday() + 7))
        )
        if monday.weekday() != 0 or monday + timedelta(days=6) >= profile.today():
            raise AppError("INVALID_INPUT")
        start, end = monday.isoformat(), (monday + timedelta(days=6)).isoformat()
        selections = engine.daily(start, end, args.metrics.split(","))
        selections += [engine.runs(start, end)]
        if not args.no_plan:
            selections += [engine.plans(start, end)]
        path, markdown = publish_weekly(
            store, profile, start, end, selections, output=args.output, revision=args.revision
        )
        if args.json:
            print_json(
                {
                    "status": "partial" if failed(selections) else "ok",
                    "report": f"{path.parent.name}/{path.name}",
                    "markdown": markdown,
                    "items": [s.as_dict() for s in selections],
                }
            )
        else:
            print(markdown)
            print(f"已保存：{path.parent.name}/weekly.md。配套来源在同一目录。")
        return 2 if failed(selections) else 0


def main(argv=None) -> int:
    args = None
    try:
        args = parser().parse_args(argv)
        return run(args)
    except AppError as error:
        if args and args.json:
            print_json({"status": "error", "error": error.as_dict()})
        else:
            print(f"{error.code}：{error} {error.as_dict()['action']}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("操作已取消；已有摘要和成功 token 保留。", file=sys.stderr)
        return 130
    except Exception:
        # Do not leak tracebacks with tokens, payloads or local absolute paths.
        error = AppError("IO_ERROR")
        print(f"{error.code}：{error} {error.as_dict()['action']}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
