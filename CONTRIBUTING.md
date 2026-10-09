# 参与开发

使用 Python 3.12+ 和 uv。先读 [设计决策](docs/decisions.md)，运行 `uv sync --locked`，提交前执行 `uv run --locked pytest`、`uv run --locked ruff check .`。

保持一个主 Skill 和轻量本地 CLI。优先修复中国区认证、计划兼容及会改变分析结论的问题；增加功能前先确认实际使用需求，不默认引入服务、数据库或额外模型 API。

测试仅用虚构数据和 fake transport。禁止提交真实 token、身份、健康摘要、报告、原始 API payload、私人绝对路径；错误输出也不应包含这些材料。调试时不要开启上游响应体日志。PR 说明包含触发条件、行为变化、验证和实测边界。

改认证或依赖版本时检查 `transport.py` 的兼容性 seam，验证实际请求次数、429 停止、刷新上限及 MFA；只数高层 API 调用不够。源码摘要和测试不能把失败或未知结构转成空列表/零值。

Skill 修改需检查 frontmatter、相对引用和实际 CLI 参数。图标的可编辑源文件在 `assets/icon.svg`；更新时同步 Skill 自包含的图标。复制第三方代码前确认许可，保留署名并更新 THIRD_PARTY_NOTICES。

线上验证由持有账号的用户在本地进行，记录版本、平台、区域、计划家族与结果即可；凭据、截图和真实健康数据不进入仓库。推送、发布及外部账号操作按用户明确指令执行。
