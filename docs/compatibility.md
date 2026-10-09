# 兼容性与验证记录

2026-10-08：按用户后续授权开始实现，主目标中国区；重新查询 PyPI 与 [上游 release](https://github.com/cyberjunky/python-garminconnect/releases/tag/0.3.17)，当前最新均为 **garminconnect 0.3.17**。新项目精确使用该版本，旧笔记库及其 0.3.6 环境保持只读。所有测试数据虚构。

## 验证层次

| 项目 | 状态 |
| --- | --- |
| 区域、profile、日期、缓存、报告防覆盖 | 本地离线回归验证；见 tests |
| 上游登录/MFA/刷新/429 的网络请求保护 | 使用安装的库与 fake transport 验证；不等于真实 Garmin 登录 |
| macOS arm64、Python 3.12.8 | 本机 80 项离线测试、Ruff 通过；独立临时环境的锁定源码安装与 uv tool install 通过，CLI 在仓库外执行成功 |
| Linux / Windows | 已配置离线 CI；本轮没有独立机器或 CI 运行结果 |
| CN 首次登录、真实 MFA、自然 token 到期恢复 | 未验证；用户需在本地执行 |
| CN 设备字段和真实 Coach/ATP/普通计划 | 未验证；异常结构会显式报错 |
| global 账号 | 源码有区域支持与隔离测试，真实账号未验证，实验性 |
| 主 Skill 的发现与自然语言执行 | 已制作并进行结构检查；尚无独立 Agent 实际执行记录 |

不要把离线测试、源码存在实现、上游 issue 作者的成功或安装完成等同于线上兼容。

本轮已构建 wheel 与源码包；离线 demo 核对为 3 次跑步、18.5 km、111 分钟，51 份虚构来源的内容 hash 与相对引用均通过检查。Skill frontmatter 与相对资源通过结构验证；README 横幅和大小图标已实际渲染检查。安装验证使用临时状态目录，没有访问真实账号状态。以上均为同一台 macOS 的本地验证，不算独立机器验收。

## 0.3.17 的适配边界

1. 使用 Garmin / Client 的公开 login、resume_login、loads/dumps、connectapi 等接口；没有复制旧私有 portal 登录或 macOS osascript。
2. 上游 login 会在 429 后切换指纹/策略；外层捕获不足以停止。transport.py 在请求期间临时包装 requests.Session.send 和 curl_cffi Session.request，计入重定向与 DI refresh，在 429 处用专用 BaseException sentinel 逃离上游 catch-and-fallback。scope 退出恢复原方法。它只适用于本工具的同步单线程 CLI，不作为多线程嵌入库承诺。
3. API 401 可刷新一次、原请求重试一次，刷新 token 的传输次数有上限；429 不重试；网络/5xx 在 engine 做最多一次短重试。数据批次有 256 次/180 秒上限，认证为 40 次/180 秒，MFA 的用户输入等待不计入网络预算。403 保守停止，用户可明确选择 portal/widget 再尝试。公开设置 retry_attempts=0 关闭高层叠加重试。
4. 上游 dumps 当前仅持久化 DI token，JWT_WEB-only 会话无法可靠复用。本工具不自行扩展其私有 token 格式，明确报 AUTH_MODE_UNSUPPORTED 并保留原文件，可由用户重新选择 portal/widget 登录。真实 CN 获得哪种 token 尚未验证。
5. get_activities 会把 null 转 []，本工具改用公开 connectapi 的相同列表接口并自行分页/验结构；不混淆 null、失败与完整空集合。
6. trainingPlanScalar 按请求的每个 calendarDate 获取，不根据一个 anchor 推断周覆盖；计划窗口至多 31 天。REST 候选先过滤日期，详情最多 3 个；未知家族不猜测路由。普通计划/旧 adaptive REST 只按明确分类分派，新 ATP 走日程与 UUID 任务详情；元数据从明确白名单保留。真实区域/计划家族仍需逐项验证。
7. mostRecentTrainingStatus 的观察日期与查询日期分开；未知状态代码保留源值。睡眠不使用中国区可能有重复时区偏移的 Local epoch 字段推算入睡时间。

升级依赖时必须重跑对应 transport 与契约回归，不只看单元测试总数。接口/设备变体可增加有来源依据的适配，不以猜测默认值掩盖。

## 后续真实验证

用户本地完成：首次登录/MFA → token 复用 → 单日三个指标 → 最近跑步 → 近期计划 → 周报。与自己在 Garmin 看到的日期/单位/任务对照，仅登记版本、平台、区域、计划家族、日期和通过/未通过；真实身份、凭据、健康记录与截图不提交。自然到期恢复另记。

至少两周自用和一个独立环境通过后，再调整支持等级及发布说明。2026-10-08 后续获用户授权公开 GitHub 仓库及 v0.1.0a1 alpha 预发布版；发布不提升线上兼容性等级。开发和发布流程均未登录 Garmin 或读取真实账号数据。
