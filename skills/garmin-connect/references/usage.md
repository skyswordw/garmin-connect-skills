# 本地工具速查

源码安装：在仓库根运行 `uv sync --locked --no-dev`；若要从任意目录调用，再运行 `uv tool install .`。尚未发布 PyPI 包，不猜测在线安装名或 GitHub 地址。Skill 安装时复制整个目录，参考文件随包保留。

```sh
garmin-skills --json doctor
garmin-skills --json auth status
garmin-skills --json fetch daily --metrics sleep,hrv,rhr
garmin-skills --json fetch daily --start 2026-09-28 --end 2026-10-04 --metrics sleep,hrv
garmin-skills --json fetch runs --days 7
garmin-skills --json fetch plan --days 7
garmin-skills --json fetch workout 12345 --date 2026-10-09
garmin-skills --json report weekly --output ~/GarminReports
```

`--json`、`--profile`、`--home` 放在 auth/fetch/report 前。日期示例应换成用户需要的实际范围。工具默认使用首次创建的档案，cn 是默认区域，但时区独立设置。

`--offline` 完全不联网，可读取过期摘要并标 stale；`--refresh` 忽略缓存，与 offline 互斥。缓存按档案、区域、时区、指标、日期和任务 ID 隔离；失败更新不会覆盖最后成功值，last_attempt 保留失败来源。

退出码：0＝本次所选查询正常完成（可包含未提供/不支持）；2＝有获取失败或停止的项，但 stdout 仍提供可用的部分输入；1＝命令/配置/认证等阻止完成；130＝用户取消。不把非零退出码自动当作“无记录”。

AUTH_REQUIRED：用户本地执行 `garmin-skills auth login`。RATE_LIMITED：读取 retry_at，等待后由用户再次发起，禁止循环重试。403 不一定是密码错误；NETWORK_ERROR 不应触发索取密码。INVALID_RESPONSE 说明无法可靠解读，保留错误码和版本反馈，不附原响应、token 或真实健康快照。

报告默认上一个完整周一至周日；`--week` 指定周一。`--no-plan` 明确这次不查询计划，不能据此宣称无计划。报告防覆盖；只有用户要修订时使用 `--revision`。导出的是报告、manifest、必要轻量来源，不导出 token 或全部缓存。
