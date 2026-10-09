"""Errors contain only predefined messages; upstream exception text never leaves the adapter."""

from dataclasses import dataclass

MESSAGES = {
    "AUTH_REQUIRED": ("需要本地登录或 token 已失效。", "运行 garmin-skills auth login。"),
    "AUTH_FAILED": ("Garmin 未接受本次认证。", "在本地检查账号区域、密码和 MFA 后重试。"),
    "MFA_REJECTED": ("MFA 未通过。", "输入新的验证码；不要把验证码发到聊天。"),
    "RATE_LIMITED": ("Garmin 返回限流，本次请求已停止。", "等待冷却结束后手动重试。"),
    "FORBIDDEN": ("Garmin 拒绝访问（403）。", "检查账号区域；稍后重试，勿连续重新登录。"),
    "NETWORK_ERROR": ("网络或 Garmin 服务暂时不可用。", "检查网络后重试，或使用已有离线摘要。"),
    "INVALID_RESPONSE": ("返回结构或数值无法可靠解读。", "保留错误码并反馈；不要把它当作无记录。"),
    "INPUT_MISMATCH": ("输入的账号、区域、时区或日期不匹配。", "选择正确 profile 或重新获取摘要。"),
    "UNSUPPORTED": ("当前接口或计划家族尚不支持。", "使用其他有效指标；在 Garmin 中核对该项。"),
    "REQUEST_BUDGET": ("已达到本次请求或时间预算。", "缩小日期范围后重试。"),
    "INVALID_INPUT": ("参数或本地配置无效。", "检查日期、时区及命令帮助。"),
    "NOT_FOUND": ("尚未找到所需本地摘要或 profile。", "先登录或获取数据；离线模式不会联网。"),
    "IO_ERROR": ("本地文件无法安全读写。", "检查目录权限、磁盘空间和符号链接。"),
    "BUSY": ("该 profile 正被另一个命令使用。", "等待该命令结束后重试。"),
    "REPORT_EXISTS": ("该周报告已经存在。", "保留原报告，使用 --revision 生成修订版。"),
    "NO_VALID_DATA": ("没有可用于周报的有效数据。", "先获取数据或检查错误；不会生成空白结论。"),
    "AUTH_MODE_UNSUPPORTED": (
        "认证获得的 token 暂不能可靠持久化。",
        "尝试 auth login --strategy portal 或 widget；原 token 未被覆盖。",
    ),
}

FATAL = {
    "AUTH_REQUIRED",
    "AUTH_FAILED",
    "RATE_LIMITED",
    "FORBIDDEN",
    "NETWORK_ERROR",
    "REQUEST_BUDGET",
    "INPUT_MISMATCH",
}


@dataclass
class AppError(Exception):
    code: str
    retry_at: str | None = None

    def __str__(self) -> str:
        return MESSAGES.get(self.code, MESSAGES["INVALID_RESPONSE"])[0]

    def as_dict(self) -> dict:
        message, action = MESSAGES.get(self.code, MESSAGES["INVALID_RESPONSE"])
        result = {"code": self.code, "message": message, "action": action}
        if self.retry_at:
            result["retry_at"] = self.retry_at
        return result


class TransportStop(BaseException):
    """Bypass upstream catch-and-fallback loops, including during MFA and refresh.

    Only the scoped adapter catches this sentinel. KeyboardInterrupt is separate.
    It must not inherit Exception: upstream login catches every Exception and rotates
    strategies after 429. See tests/test_transport.py and docs/compatibility.md.
    """

    def __init__(self, error: AppError):
        self.error = error
