---
name: garmin-connect
description: Read local Garmin Connect summaries to analyze running, sleep and recovery, inspect Garmin Coach tasks, or produce traceable Chinese weekly reports. 中国区佳明账号优先。Use for Garmin data questions, not medical diagnosis or writing training plans to Garmin.
---

# Garmin 跑步与恢复

使用 `garmin-skills` 本地工具按问题获取轻量摘要，区分数据事实、解释和建议。默认中国区；不需要模型 API、MCP 服务或 Obsidian。

## 工具与登录

先确认 `garmin-skills --version` 可用。未安装时，已知源码目录可用 `uv run --locked --project <仓库目录> garmin-skills`，或让用户按仓库 README 安装；不要猜测下载地址。工具和此 Skill 对应 0.1.0a1。

认证只由用户在本地终端完成。`AUTH_REQUIRED` 时提供 `garmin-skills auth login` 指引，不索取/读取密码、MFA、token，也不检查用户的其他 Skill 或笔记库找凭据。日期默认由工具按 profile 时区计算；需要核对配置时用 `garmin-skills --json doctor`。

## 按问题选数据

优先使用 `--json`，它位于子命令前；指定账号时使用 `--profile <别名>`，同一分析始终用相同档案。

| 问题 | 最小入口 |
| --- | --- |
| 昨晚睡眠/今日恢复 | `garmin-skills --json fetch daily --metrics sleep,hrv,rhr` |
| Body Battery、压力或准备度 | `fetch daily --metrics` 只选相关指标；需要训练状态时加 `training_status` |
| 最近跑步与恢复 | `fetch runs --days 7`，再取相同范围的必要日指标；不自动下载圈段或轨迹 |
| 近期 Coach / adaptive | `fetch plan --days 7`；目标不清楚时按返回 ID 和日期调用 `fetch workout <ID> --date <日期>` |
| 中文周报 | `report weekly`；指定周一用 `--week`，用户要求导出时加 `--output` |

单日 `--date`，范围 `--start/--end`，两端包含。有效缓存自动复用；用户要更新时才用 `--refresh`。离线或网络不可用可用 `--offline`，必须说明摘要截至时间。不要为了“分析全面”先把全部接口抓一遍。

常用参数和故障恢复见 [usage.md](references/usage.md)，解释数据或任务目标时见 [analysis.md](references/analysis.md)。只读取当前任务需要的参考。

## 使用返回值

- 逐项核对 profile、region、timezone、start/end、coverage、fetched_at、status、complete；不要拼接错区或错窗口输入。最新训练状态另有 observed_date，不等于查询当天。
- `ok/empty/missing/unsupported/error/not_requested` 含义不同。只有完整、有效的活动空查询可以说“0 次”；错误、缺页或旧输入不能变成零值/没有计划。
- 退出码 2 仍可能有有效的部分数据。读取 JSON 中的 items、stale、update_error、last_attempt 并说明限制；不要忽略这些项后输出完整结论。
- 认证失败、403、429、网络失败后停止追问式抓取。工具已实施请求预算与冷却，不改配置绕过。已有有效摘要可独立分析。

## 分析与周报

先列事实（日期、数值、单位、有效样本和来源），再解释变化，最后给保守且可调整的建议。只在足够的同个人历史数据支持时比较基线；不足时直说，不套通用配速或单一分数阈值。

任务名称和估计时长不等于完整处方。保留 Garmin 返回的目标、条件和单位；不补写热身、恢复间歇、总时长或未知描述。休息日要有明确 rest_day 依据，没返回任务不等于休息。

CLI 周报是事实版，报告自带来源清单和轻量 JSON。补充解释时引用这些事实，不改造统计来配合结论；输入缺失要在解释处体现。已有周报用 `--revision`，不覆盖。Obsidian 只作为用户选择的导出位置，运行环境和凭据留在工具状态目录。

不把 Garmin 指标当诊断，不自动写入/调整 Garmin 训练计划，不引入额外付费模型、远程同步或后台任务。
