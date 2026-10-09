# 安装、本地状态与恢复

当前为 [GitHub alpha 预发布版](https://github.com/skyswordw/garmin-connect-skills/releases/tag/v0.1.0a1)，尚未上传 PyPI。需要 uv 和可安装的 Python 3.12+。克隆仓库或解压预发布版源码后，在项目根目录运行：

```sh
uv sync --locked --no-dev
uv run --locked --no-dev garmin-skills demo
uv run --locked --no-dev garmin-skills auth login --timezone Asia/Shanghai
uv run --locked --no-dev garmin-skills fetch daily
```

macOS 的 /etc/localtime 通常可提供 IANA 时区；无法识别时本地询问，或显式传 `--timezone`。Linux 使用系统 zoneinfo/TZ；Windows 暂需显式给 IANA 时区且尚未实测。中国区默认 cn；时区跟随个人实际生活地区，不跟账号区域绑定。

让 Agent 从任何目录调用：在源码根执行 `uv tool install .`，再检查 `garmin-skills --version`。此路径独立解析依赖，不自动应用 uv.lock。精确复现使用项目环境的 `uv sync --locked` / `uv run --locked`；核心 garminconnect 在两条路径都精确锁定 0.3.17。

Skill 源目录为 `skills/garmin-connect`，复制整个目录到 Agent 支持的 Skill 安装位置。无需安装旧的 data-builder/running-analysis 两个 Skill，不需要笔记库或 OpenAI API key。

## 本地状态

默认状态根由 platformdirs.user_state_path 选择，macOS 为用户 Library/Application Support、Linux 为 XDG state、Windows 为本地 AppData。根目录包含 profiles.json；每个随机 profile ID / region 内分别保存 auth/tokens.json、objects、index、reports 和冷却状态。没有姓名/邮箱的随机 ID 只用于隔离，原账号最小身份只以本地绑定摘要保存。

token 文件访问限制为当前用户，类 Unix 为 0600、目录 0700；不是加密保险箱。Windows 文件访问限制与原子发布需实机确认。拒绝符号链接路径，成功数据原子替换；同 profile 的命令用文件锁串行，避免刷新 token 竞争。

`--home` 可在所有子命令前指定独立根目录，主要用于测试或自选位置；不要指向笔记库、项目仓库或共享目录。普通用户无需设置它。真实数据与报告不应提交到 Git。

## 查询与错误

`auth status` 只显示是否保存 token，不读取其内容来判断是否在线有效；`--check` 少量联网验证身份与 token。身份或区域错配不会自动改绑，请创建新的 profile。重新登录时原成功 token 只有在新认证/身份校验成功后才替换。

获取命令非交互，不从环境变量或其他目录寻找密码。无有效 token 返回 AUTH_REQUIRED。在终端运行 login 本地输入；MFA 最多三次，空输入取消。429 会立即停止 profile 批次并记录冷却，网络/5xx 最多一次显式短重试。错误与日志不包含原响应和凭据。

更新失败时旧成功摘要仍可使用，输出带旧抓取时间、stale、update_error 和 last_attempt。普通缓存的完整范围必须匹配；不会根据几条活动推断整个星期有记录或没记录。

报告保存在 profile 的 reports 内。使用 `--output` 将报告和来源显式写到选择的目录，`--revision` 创建新版本。没有自动清理或全历史归档，报告来源不会被后台删掉。Obsidian 可以打开导出的 Markdown，其目录结构不影响本工具。

## 支持边界

中国区为主要目标。macOS 本机安装/离线验证与其他 OS、global 账号、真实 Coach 验证分开记录。详情见 [compatibility.md](compatibility.md)。首次实际验证只需单日少量指标，不要用全量同步排查认证问题。
