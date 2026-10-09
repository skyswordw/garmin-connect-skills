# garmin-connect-skills

<p align="center"><img src="assets/header.svg" alt="garmin-connect-skills：跑步、睡眠与恢复" width="100%"></p>

[![离线检查](https://github.com/skyswordw/garmin-connect-skills/actions/workflows/tests.yml/badge.svg)](https://github.com/skyswordw/garmin-connect-skills/actions/workflows/tests.yml)

Garmin Connect 的本地命令行工具和 Agent Skill，主要面向中国区账号。它把跑步、睡眠和恢复数据整理成摘要，方便你在 Codex、Claude Code 等 Agent 中查询和分析，也可以直接在终端生成中文训练周报。

> 项目目前处于 alpha 阶段，尚未完成真实中国区账号的登录、MFA 和 Coach 查询验证。[查看兼容性与测试记录](docs/compatibility.md)。

[快速开始](#快速开始) · [接入 Agent](#接入-agent) · [常见问题](#常见问题) · [开发与文档](#开发与文档)

## 功能

- 查询睡眠、HRV、静息心率，以及压力、Body Battery、训练准备度和训练状态。
- 查看近期跑步记录，结合对应日期的恢复数据分析训练。
- 读取 Garmin Coach / adaptive 训练计划的近期安排，按需查看任务目标和步骤。
- 生成中文周报，附上数据来源、查询日期和缺失说明。

工具按问题需要获取数据，并复用有效缓存。分析会区分数据事实、解释和建议。查询失败、指标缺失和确实没有记录会分别标明，只有确认活动列表为空时，才会显示“跑步 0 次”。

## 快速开始

先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，它会按需下载 Python 3.12。请把项目放在笔记库之外。

### 1. 安装

```sh
git clone https://github.com/skyswordw/garmin-connect-skills.git
cd garmin-connect-skills
uv sync --locked --no-dev
```

也可以从 [Releases](https://github.com/skyswordw/garmin-connect-skills/releases) 下载源码，解压后在项目目录运行安装命令。项目尚未上传 PyPI。

安装后可以先看一份示例周报：

```sh
uv run --locked --no-dev garmin-skills demo
```

示例使用虚构数据，完全离线，无需账号。生成的报告和来源文件保存在当前目录的 `demo-output/` 中。

### 2. 登录

```sh
uv run --locked --no-dev garmin-skills auth login --timezone Asia/Shanghai
```

默认登录中国区账号。在本地终端按提示输入邮箱和密码；如果账号开启了多因素认证（MFA），还需要输入验证码。输入内容不会显示。登录成功后会保存 token，后续查询复用登录状态。

`Asia/Shanghai` 是时区示例，请按实际所在地设置。账号区域和时区是两项独立配置。

### 3. 查询数据

在项目目录运行：

```sh
# 今天的睡眠、HRV 和静息心率
uv run --locked --no-dev garmin-skills fetch daily

# 最近 7 天的跑步记录
uv run --locked --no-dev garmin-skills fetch runs --days 7

# 接下来 7 天的 Coach / 训练计划
uv run --locked --no-dev garmin-skills fetch plan --days 7
```

<details>
<summary>指定日期、指标或使用缓存</summary>

```sh
# 查询指定日期，只获取睡眠、HRV 和 Body Battery
uv run --locked --no-dev garmin-skills fetch daily --date 2026-10-07 --metrics sleep,hrv,body_battery

# 查询指定范围的跑步记录，包含开始日和结束日
uv run --locked --no-dev garmin-skills fetch runs --start 2026-09-28 --end 2026-10-04

# 只读取本地摘要
uv run --locked --no-dev garmin-skills fetch daily --offline
```

`--metrics` 可选值：`sleep,hrv,rhr,stress,body_battery,readiness,training_status`。

默认复用仍然有效的缓存。加 `--refresh` 可以重新获取数据；`--offline` 始终不联网，使用过期摘要时会注明。示例日期请换成需要查询的日期。

</details>

### 4. 生成周报

```sh
uv run --locked --no-dev garmin-skills report weekly --output ~/GarminReports
```

默认统计上一个完整的星期一至星期日。每份周报保存在单独的文件夹中，包含报告 `weekly.md`、来源清单 `manifest.json` 和摘要目录 `sources/`。可以用 Markdown 阅读器查看，也可以导出到自己的 Obsidian 笔记库。

周报由程序生成，列出数据和统计结果；Agent 可以在此基础上补充解释和建议。部分指标缺失时会注明，没有任何可用数据时停止生成报告。

指定一周或生成修订版：

```sh
uv run --locked --no-dev garmin-skills report weekly --week 2026-09-28 --revision --output ~/GarminReports
```

`--week` 指定星期一的日期，`--revision` 将报告保存为新版本，保留原文件。

## 接入 Agent

在仓库目录安装命令行工具，之后就能从任意目录调用：

```sh
uv tool install .
garmin-skills --version
```

如果找不到 `garmin-skills` 命令，运行 `uv tool update-shell`，然后重新打开终端。源码安装与独立工具安装的区别见 [安装说明](docs/setup.md)。

把完整的 `skills/garmin-connect` 目录复制到 Agent 的 Skill 目录。以 Codex 为例：

```sh
mkdir -p ~/.codex/skills
cp -R skills/garmin-connect ~/.codex/skills/
```

Claude Code 的用户 Skill 目录是 `~/.claude/skills/`。Windows 用户可以手动复制文件夹；其他 Agent 请按各自的 Skill 安装方式添加。各 Agent 的安装和执行仍需进一步验证。

安装后可以直接问：

- “看看我昨晚睡得怎么样，今天恢复如何。”
- “结合上周的跑步和恢复数据，帮我分析一下训练。”
- “Coach 这周安排了哪些训练？”
- “生成上周的中文训练周报。”

项目本身不调用额外的模型服务。摘要是否发送给云端模型，取决于你使用的 Agent。

## 常见问题

下面的命令以已安装的 `garmin-skills` 为例。如果使用源码环境，请在项目目录给命令加上 `uv run --locked --no-dev` 前缀。

| 提示 | 处理方法 |
| --- | --- |
| `AUTH_REQUIRED` | 在本地终端运行 `garmin-skills auth login`。 |
| `AUTH_FAILED` / `MFA_REJECTED` | 核对账号区域、密码和验证码，再重新登录。MFA 输入留空可以取消。 |
| `RATE_LIMITED` | 请求已停止，等提示的冷却时间结束后再试。反复登录不能解决限流。 |
| `FORBIDDEN`（403） | 先确认账号区域，或稍后再试；403 不一定由密码错误引起。 |
| `NETWORK_ERROR` | 检查网络。已有本地摘要时，可以加 `--offline` 查看。 |
| 指标未提供 / 暂不支持 | 确认设备是否支持该指标、数据是否已同步。其他有效数据仍可使用。 |
| `INVALID_RESPONSE` | 查询结果无法解析。反馈时提供版本、命令和错误码。 |
| `AUTH_MODE_UNSUPPORTED` | 当前登录方式无法保存登录状态，可重新登录并尝试 `portal` 或 `widget`，见下方说明。 |
| `REPORT_EXISTS` | 已有同一周的报告。加 `--revision` 保存新版本。 |

检查环境和登录状态：

```sh
garmin-skills doctor
garmin-skills auth status          # 只检查本地状态
garmin-skills auth status --check  # 联网验证登录状态，不查询健康数据
```

遇到 `AUTH_MODE_UNSUPPORTED` 时，可以尝试：

```sh
garmin-skills auth login --reauth --strategy portal
```

目前依赖库无法可靠保存 JWT-only 登录结果，工具会保留原 token。详情见 [兼容性说明](docs/compatibility.md)。排查时请保持 MFA 开启。

需要帮助时，可以 [提交 Issue](https://github.com/skyswordw/garmin-connect-skills/issues)，注明操作系统、工具版本、命令和错误码。请不要附上密码、验证码、token、个人身份信息或原始健康数据。

## 数据与隐私

登录状态和查询摘要默认保存在系统用户目录中，按账号档案和区域分开存放：

| 系统 | 默认目录 |
| --- | --- |
| macOS | `~/Library/Application Support/garmin-connect-skills/` |
| Linux | `${XDG_STATE_HOME:-~/.local/state}/garmin-connect-skills/` |
| Windows | 用户本地 AppData 下的 `garmin-connect-skills/` |

密码不会保存。token 以未加密的本地文件保存；macOS 和 Linux 使用文件权限限制访问，Windows 的访问权限仍待实机验证。

默认只保存查询摘要，不下载轨迹、圈段或 FIT/GPX/TCX 文件，也不保留完整 API 响应。周报可以导出到你选择的目录，分享时请自行检查其中的健康信息。

<details>
<summary>多账号与国际区</summary>

多个账号分别使用不同的档案名称：

```sh
garmin-skills --profile second auth login --timezone Asia/Shanghai
```

国际区账号需要明确指定 `--region global`：

```sh
garmin-skills --profile global auth login --region global --timezone Asia/Shanghai
```

国际区目前为实验性功能。项目优先验证中国区账号；时区请按实际所在地设置。

</details>

## 开发与文档

依赖固定为 `garminconnect 0.3.17`，开发环境使用 uv 管理：

```sh
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
```

测试使用虚构数据和模拟网络请求，检查错误处理、账号与区域隔离、缓存、计划查询和报告防覆盖等行为。macOS、Linux 和 Windows 的离线 CI 已通过，Windows 跳过了 POSIX 权限测试。真实账号和完整使用流程的验证情况见 [兼容性说明](docs/compatibility.md)。

- 用户文档：[安装与账号恢复](docs/setup.md) · [版本说明](docs/releases/v0.1.0a1.md)
- 项目设计：[调研](docs/research.md) · [技术决策](docs/decisions.md) · [首版范围与验收](docs/mvp.md)
- 参与开发：[贡献指南](CONTRIBUTING.md)

## 许可证

代码和原创图标采用 [MIT 许可证](LICENSE)。依赖及参考项目见 [第三方说明](THIRD_PARTY_NOTICES.md)。

这是社区项目，与 Garmin 官方无隶属关系。运动和恢复指标用于训练参考，不作医疗诊断。
