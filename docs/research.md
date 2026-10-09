# Garmin Connect 接入与分析方案调研

查询日期：2026-10-08（Pacific/Honolulu）。这是调研快照，不是线上兼容性认证。决策见 [decisions.md](decisions.md)，交付门槛见 [mvp.md](mvp.md)。

## 范围、方法与证据等级

覆盖社区库、直接 Skill、附带 Skill 的 CLI、MCP、本地归档及训练分析。先只读检查既有工作区规则、依赖、脚本、测试和两个 Garmin Skill；项目笔记只提取技术进展与问题条目。未读取用户凭证、token 或健康快照，未登录 Garmin，未改动源工作区。公共源码在临时目录检查，未复制到本项目。

公共发现使用 GitHub repository search，查询如下；每个查询按 updated 排序取前 8 项，再人工筛选，不以排序或 stars 评价质量：

| 查询 | 当时结果数 | 作用 |
| --- | ---: | --- |
| garmin skill | 84 | Skill、CLI、远程教练路线 |
| garmin cli | 174 | 独立本地工具、离线导出路线 |
| garmin mcp | 414 | 直接 API 与本地数据库 MCP |
| garmin local training analysis | 5 | 本地训练分析与镜像 |
| 佳明 skill | 4 | 中文、中国区分析实现 |
| garmin obsidian | 18 | Markdown、笔记库适配 |
| GarminDB | 25 | 长期数据归档与统计 |

查询可在 [GitHub 搜索](https://github.com/search?type=repositories&q=garmin+skill)复查；结果会变化。检查了用户指定的全部 10 个候选，补充深入检查 5 个项目。其余发现包括 PatrykPodworski/garmin-cli、Fulminant-fdl/garmin-vault-sync、antboj/garmin-mcp、tgorganchian/GarminCoach：仅发现级筛选，未做源码质量结论。主要候选读取 README、依赖声明、许可文件或声明、Skill、认证与获取关键代码、测试；对接入库、gccli、两个 MCP 和 givemydata 另外检查近期 issue/PR 与发布记录。

证据标记：**D**＝文档声称；**S**＝源码实现；**T**＝找到对应测试，未必运行；**V**＝本轮亲自验证，并注明范围；**U**＝未验证。issue 的用户实测属于外部报告，不升级为本轮 V。文件中没找到实现只说明所查 revision 的范围，不证明 Garmin 永远不支持。

## 仓库、版本与许可证快照

全部候选返回相同的 canonical full_name，未观察到仓库迁移，均未标为 archived/disabled。garth 虽未归档，已明确停止维护。下表 commit 链接固定源码；“无 release”指 GitHub Releases 返回空，不代表没有包发布。最后推送时间可能来自其他分支，因此以实际默认分支 HEAD 为准。

| 项目 / 路线 | 检查的默认分支 HEAD | 关键版本 / 最新 GitHub release | 许可证据 |
| --- | --- | --- | --- |
| [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) / 库 | [218e72ca](https://github.com/cyberjunky/python-garminconnect/tree/218e72ca5459e014435fc2d94fd18bd601fa0c14)，master | 0.3.17；2026-09-29 | MIT，完整 LICENSE |
| [garth](https://github.com/matin/garth) / 库 | [f99159a1](https://github.com/matin/garth/tree/f99159a15c4c9463ce215a60ba9f7cb21f94a3b7)，main | 最终 v0.8.0；2026-03-28 | MIT，完整 LICENSE |
| [ZXFqwert/garmin-connect-skill](https://github.com/ZXFqwert/garmin-connect-skill) / 中文 Skill | [96bfce48](https://github.com/ZXFqwert/garmin-connect-skill/tree/96bfce4826464c4b2e1ea327c016fc6437d5ed4d)，master | README v2.0；无 release | README 声称 MIT；无完整 LICENSE |
| [freakyflow/garminskill](https://github.com/freakyflow/garminskill) / Markdown Skill | [228b1d21](https://github.com/freakyflow/garminskill/tree/228b1d2126211ad70a0d15621027900d16c33abd)，main | Skill 1.3.1；无 release | 未找到许可声明/文件 |
| [dsebastien/ai-skill-garmin](https://github.com/dsebastien/ai-skill-garmin) / Bun Skill | [22bfebaf](https://github.com/dsebastien/ai-skill-garmin/tree/22bfebaf567c60cf134229c77682c334aa35df10)，main | 无 release | MIT，完整 LICENSE |
| [gccli](https://github.com/bpauli/gccli) / Go CLI + Skill | [49c32289](https://github.com/bpauli/gccli/tree/49c322890baddddba2a768ea8937aea4efe18f5a)，main | v1.11.0；2026-10-05 | MIT，完整 LICENSE |
| [nftechie/garmin-skill](https://github.com/nftechie/garmin-skill) / 托管 API Skill | [85c0ade7](https://github.com/nftechie/garmin-skill/tree/85c0ade79de52acfddf7cf3c0f40b38183c18577)，main | 无 release | README 声称 MIT；无完整 LICENSE |
| [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) / Python MCP | [cfc5d799](https://github.com/Taxuspt/garmin_mcp/tree/cfc5d799ab0f165e837f1188a1d093c65838aaf7)，main | 项目 0.1.0；release 2026-05-08，HEAD 已有后续修改 | MIT，完整 LICENSE |
| [Nicolasvegam/garmin-connect-mcp](https://github.com/Nicolasvegam/garmin-connect-mcp) / TS MCP | [9478e37f](https://github.com/Nicolasvegam/garmin-connect-mcp/tree/9478e37ff48c8414e77208ad1cb748be481da097)，main | package 1.1.0；无 GitHub release | package.json 声明 MIT；无完整 LICENSE |
| [garmin-givemydata](https://github.com/nrvim/garmin-givemydata) / 浏览器归档 + MCP | [e547f5fa](https://github.com/nrvim/garmin-givemydata/tree/e547f5fae84bd38038725dffdf30ea95f762cb10)，main | 0.1.13；release 2026-06-20，HEAD 含后续修复 | AGPL-3.0-only（pyproject + LICENSE） |
| [GarminDB](https://github.com/tcgoetz/GarminDB) / 长期归档 | [62409888](https://github.com/tcgoetz/GarminDB/tree/62409888d853d7cf4acd1bb7320337ce9f942176)，master | v3.9.0；2026-08-23 | GPL v2 文本；不可当作 MIT 代码搬入 |
| [njzyshare/garmin-running-analysis](https://github.com/njzyshare/garmin-running-analysis) / 中文分析 Skill | [60bd57dd](https://github.com/njzyshare/garmin-running-analysis/tree/60bd57ddcd662865d0e00f7b6f42740f6bf6afb1)，feat/add-skill-scripts | README 2.3.0；无 release | 未找到完整 LICENSE |
| [garmin-panorama-training-analysis](https://github.com/runzhenghengbin/garmin-panorama-training-analysis) / 中文 HTML Skill | [fb874218](https://github.com/runzhenghengbin/garmin-panorama-training-analysis/tree/fb874218d26138bf7c646bddb2fe5c0e19dff186)，main | Skill 1.0.0；无 release | MIT，完整 LICENSE |
| [garmin-ai-secure](https://github.com/gosanke/garmin-ai-secure) / Markdown 同步 | [50d97330](https://github.com/gosanke/garmin-ai-secure/tree/50d97330ed07a133b876fbe0a8af489b6a5737f0)，main | README v3；无 release | MIT，完整 LICENSE |
| [GeoffreyBian/train](https://github.com/GeoffreyBian/train) / 个人训练工作流 | [4f39451b](https://github.com/GeoffreyBian/train/tree/4f39451b4473351c5305d134b292481a523d496c)，main | 无 release | 未找到完整 LICENSE |

MIT 代码若以后摘取，必须保留版权与许可文本并记下 revision、文件和本地修改。README/package 的简短 MIT 声明与完整许可材料分开记录；本轮不摘取这些项目代码，待澄清再复用。GPL/AGPL 不意味着不能参考或独立运行，但复制、派生和分发有相应义务，本项目不默认吸收其实现。

## 接入、认证与平台：关键比较

| 方案 | 区域与认证实现 | token / 多账号 | 平台证据与实际缺口 |
| --- | --- | --- | --- |
| python-garminconnect | S：is_cn、按域名构造 SSO/DI/API，mobile/widget/portal、MFA callback/续接、refresh。T：认证恢复、widget MFA、token 权限、重试 | S：调用方传 tokenstore；库不替应用绑定 profile+region；新旧 garth token 格式不兼容 | D：macOS/Linux/Windows；Python ≥3.12、curl_cffi。U：本轮未做任一平台真实登录 |
| garth | S/T：domain 配置、旧 OAuth1/2、MFA、统计数据模型。D：现已弃用，新登录不工作 | S：目录持久化；域名配置与目录隔离仍由调用方负责 | D：三平台；历史测试不能证明当前认证可用 |
| gccli | D/S/T：CN 域名、浏览器/终端登录、MFA、DI 刷新；但 DI 主机固定 .com | S：OS keyring；keyFor 只含 email，同邮箱跨区相互覆盖；file fallback 使用固定密码 | S：CI Linux/macOS；release 仅 darwin/linux amd64/arm64。README 的 Go 1.24+ 已落后于 go.mod 1.26.0。U：Windows 与 CN 完整链路 |
| Taxuspt MCP | S：is_cn、独立 auth CLI、MFA、已保存 token 的验证 | S/T：自选 token 路径；多账号需多个实例，区域目录非自动强制 | D：三平台；S：Windows 路径处理；CN issue #257、Windows #366 尚 open |
| Nicolasvegam MCP | S：旧 widget OAuth、MFA callback；登录/API 常量为 .com | S：单一 ~/.garmin-mcp token 目录；无区域/profile 隔离 | D：Node 20+、Windows/macOS 配置示例；T：一个依赖凭证的 live API 测试文件；U：离线错误测试与 CN |
| 直接 Skill | ZXF：S is_cn，密码 base64 持久化，非加密；freakyflow：旧 client.garth；dsebastien：固定 .com；njzyshare：CN 私有方法 monkey-patch | 多数单目录；dsebastien 有 0600 token/MFA 状态，但未按账号区域分区；njzyshare token 同目录 | 多为安装文档，缺独立机器证据；freakyflow 建议关闭 MFA，不采用该建议 |
| 本地归档 | GarminDB S/T：CN→is_cn、token 优先、MFA adapter；givemydata S：浏览器/MFA、固定 connect.garmin.com | GarminDB 单 config/token 文件；givemydata 浏览器 profile；都不是现成的轻量 profile 隔离层 | GarminDB D：macOS 开发，其他平台社区支持；givemydata D：三平台，S：SeleniumBase/Chrome/Linux Xvfb 分支；U：本轮实机 |

### python-garminconnect 与 garth 的版本事实

既有 pyproject 与 uv.lock 均锁定 garminconnect==0.3.6、curl-cffi==0.15.0、pandas==3.0.3、rich==15.0.0，Python ≥3.12。没有安装或升级它们。本轮另下载锁文件指向的公开 0.3.6 wheel，只解包源码并验证 SHA-256：e05782ab90e63cb9c023407899e2d12dd18132316fd84394ebecd393809d4ffe（V）。

0.3.6 的 Client 已使用按 domain 构造的 mobile/portal/DI 地址，且已无 garth 依赖（S）。因此旧笔记中的 mobile.integration.garmin.com 故障是历史经验，不能推导“当前锁定版本必然仍用 .com”。现有 macOS portal 脚本依赖 osascript、_portal_web_login_cffi、_MFARequired、_complete_mfa，并手动补 profile；不可作为跨平台认证入口原样迁移。

[0.3.17 client](https://github.com/cyberjunky/python-garminconnect/blob/218e72ca5459e014435fc2d94fd18bd601fa0c14/garminconnect/client.py)与 [wrapper](https://github.com/cyberjunky/python-garminconnect/blob/218e72ca5459e014435fc2d94fd18bd601fa0c14/garminconnect/__init__.py)有 token 原子写入、拒绝符号链接读取、脱敏与认证恢复逻辑；[对应测试目录](https://github.com/cyberjunky/python-garminconnect/tree/218e72ca5459e014435fc2d94fd18bd601fa0c14/tests)包括 test_token_permissions、test_login_recovery、test_widget_mfa、test_retry_decorator（S/T，未运行）。0.3.6 token 写入为直接截断写，读取会跟随普通路径链接；这些差异足以立项评估版本，不能只因版本新就升级。

[PR #417](https://github.com/cyberjunky/python-garminconnect/pull/417)于 2026-08-22 合并，修复 0.3.10 的 MFA 错码重试状态清除问题并升至 0.3.12；这是中间版本的回归/修复，不应谎称 0.3.6 有同一 finally 缺陷。[PR #448](https://github.com/cyberjunky/python-garminconnect/pull/448)补充旧 garth token 的明确错误。未解决的 [#444](https://github.com/cyberjunky/python-garminconnect/issues/444)报告 token 已签发但普通 requests 被 API 403 拒绝；[#453](https://github.com/cyberjunky/python-garminconnect/issues/453)报告首次请求 429。二者表明最新版本仍不等于线上可靠。

[garth 弃用公告](https://github.com/matin/garth/discussions/222)和 [最终 release](https://github.com/matin/garth/releases/tag/v0.8.0)明确停止维护、新登录失效。它的 domain/MFA 和类型化数据测试仍可参考；不选作新认证基础。旧 OAuth consumer 会从 thegarth.s3.amazonaws.com 取配置，最终版本默认关闭 telemetry；不能笼统称所有历史版本只连接 Garmin。

### gccli：最强替代候选，但目前不能直接替换

[auth DI](https://github.com/bpauli/gccli/blob/49c322890baddddba2a768ea8937aea4efe18f5a/internal/garminauth/di.go)将 token 地址固定为 diauth.garmin.com，CN endpoints 的测试没有覆盖 CN DI 换票/刷新。[secrets/store.go](https://github.com/bpauli/gccli/blob/49c322890baddddba2a768ea8937aea4efe18f5a/internal/secrets/store.go)以 email 构造键，file backend 的 FilePasswordFunc 是源码固定字符串；“加密文件 fallback”不能解读为用户独有的加密保护（S）。这些是实现缺口，尚未进行真实账号故障复现。

[training.go](https://github.com/bpauli/gccli/blob/49c322890baddddba2a768ea8937aea4efe18f5a/internal/garminapi/training.go)仅 plans 与普通 plan/{id}，无 adaptive/GraphQL 计划适配。[transport.go](https://github.com/bpauli/gccli/blob/49c322890baddddba2a768ea8937aea4efe18f5a/internal/garminapi/transport.go)有 429（默认 3 次）/5xx 重试；Retry-After 只解析整数秒，未解析 HTTP-date；另有 circuit breaker 测试。CLI JSON 是原始 Garmin 数据，仍需我们减少字段、标记覆盖/时效和保护失败语义。

[PR #45](https://github.com/bpauli/gccli/pull/45)与 [#47](https://github.com/bpauli/gccli/pull/47)已合并，DI client_id 与单次 ticket 消耗修复有定向单测；作者说明其 E2E 因无凭证跳过，不能当 CN 实测。[CI](https://github.com/bpauli/gccli/blob/49c322890baddddba2a768ea8937aea4efe18f5a/.github/workflows/ci.yml)、[release 配置](https://github.com/bpauli/gccli/blob/49c322890baddddba2a768ea8937aea4efe18f5a/.goreleaser.yaml)、[主 Skill](https://github.com/bpauli/gccli/blob/49c322890baddddba2a768ea8937aea4efe18f5a/skills/gccli/SKILL.md)是安装、命令输出、跨 Agent 组织的好参考；garmin-trainer 是生成并写入训练处方，与本项目读取 Garmin Coach 的目标不同。

## 数据、失败语义与使用工作流

| 方案 | 粒度、日期、缓存和失败处理（S，除注明） | Coach / adaptive | 分析、安装与维护取舍 |
| --- | --- | --- | --- |
| python-garminconnect | 按方法获取，通常仍含大数组；应用负责摘要/cache；API decorator 不重试 401/429/4xx，网络/5xx 默认重试；认证链仍可能在 429 后换策略/指纹 | 有 phased/adaptive 详情方法和 query_garmin_graphql；不同 plan 家族与区域可用性 U | Python+uv 最贴近旧代码；要自己维护少量契约、输出和 Skill |
| gccli | 单命令查询、JSON 原 payload；有 timeout/retry/熔断，没有我们的摘要新鲜度契约；日期需调用方明确 | 普通计划接口；adaptive 缺口见上 | 单二进制 + 现成 Skill 易安装；若再加 Python 摘要器会成为双运行时 |
| dsebastien Skill | 单指标按需；summary/weekly 的 catch 将活动失败变 []；today 用 UTC ISO 日期；token/consumer 缓存 | 未见计划接口 | Bun 单文件/零 npm 依赖、标准 Skill 目录值得参考；自维护 OAuth 成本不低；无测试 |
| ZXF Skill | 代码区分 cn/global，但共用 session；指标默认零、失败打印后仍保留零；固定北京时间/日期修正；README 数据库同步核心文件未随仓库提供 | 未见近期任务适配 | 中文与按需同步思路可参考；源码把 base64 密码称 password_encrypted，反复用密码登录；不复用认证 |
| freakyflow Skill | 每天固定获取多类数据；错误与无数据都省略章节；garminconnect>=0.2.38 与旧 client.garth 调用存在漂移风险 | 未见计划适配 | PEP 723/uv、简洁 Markdown 可参考；无离线测试，MFA 指引错误 |
| Taxuspt MCP | 有轻量 summary/trend、工具过滤、离线单测与 integration mocks；部分计划错误返回“无数据或错误”合并文本 | 有 GraphQL trainingPlanScalar、任务摘要、workout-service/fbt-adaptive UUID 详情；部分 adaptive 元数据仍丢失 | 不需付费模型 API；运行 MCP 服务、配置与工具面较大；无需整体引入 |
| Nicolasvegam MCP | 单日/范围工具；范围 catch→null，snapshot 多接口并发；today 是 UTC；429/5xx 重试；所查 Axios 请求未配置 timeout | 源码有 ADAPTIVE_TRAINING_PLAN_ENDPOINT，不能因 README 少提就判定完全没有；CN 与当前认证 U | Node+MCP+OAuth 依赖；测试为真实账号套件；open PR #12 不能算已修复 |
| GarminDB | 保留 JSON/FIT、SQLAlchemy 多库、日/周/月/年汇总；下载 transient retry；有 auth adapter 与空 HRV baseline 修复记录 | 非近期 Coach 解释工作流 | 长期归档强，数据量与配置高于本需求；Jupyter/SQL 技能负担 |
| givemydata | 浏览器中批量请求、增量 SQLite、默认全历史+FIT+raw_json；日期与空记录有定向测试 | 有计划数据源，但未验证能覆盖我们的计划家族 | 适合数据所有权/长期归档；浏览器依赖与 schema 维护重；不适合首版默认 |
| njzyshare 分析 Skill | 活动分段/天气/恢复/HTML；CN 适配复制私有登录、DI、JWT 方法；单 token 目录；无定向测试 | 未见严格的近期计划校验 | 中文问答映射和按需 references 有价值；配速、分段、训练法及凭据配置较重 |
| Panorama Skill | 活动+逐日指标，默认 splits/HR zones/天气；safe_call 429 退避后 default，普通异常同样 default；token 与 .env 放 Skill 根目录 | 未见近期 Coach 任务流程 | 中文可视化、离线 HTML；调用 Open-Meteo 传位置/日期；默认档案/目标、指标推断超出本项目 |
| gosanke 同步 | safe 遇 auth/429 停整次；PASS/NO_DATA/FAIL 加时间；轻量刷新保留旧详情；普通错误仍降为 None | 未见计划适配；Garmin() 未传 CN | 本地 Markdown+可选 Obsidian 字段好参考；无测试；默认获取经期等不适合我们的最小范围 |
| GeoffreyBian/train | CSV mirror、缓存重建与缺失提示、训练分析测试；部分测试直接读仓库真实数据，本轮未运行 | 私人训练计划，不是 Garmin Coach 接入 | 日常使用闭环有参考价值，但 Skill 固定路径、运动目标、发布动作强耦合；不用其数据与代码 |

直接源码入口：[dsebastien garmin.ts](https://github.com/dsebastien/ai-skill-garmin/blob/22bfebaf567c60cf134229c77682c334aa35df10/skills/garmin-connect/scripts/garmin.ts)、[ZXF auth](https://github.com/ZXFqwert/garmin-connect-skill/blob/96bfce4826464c4b2e1ea327c016fc6437d5ed4d/scripts/garmin-auth.py)、[freakyflow sync](https://github.com/freakyflow/garminskill/blob/228b1d2126211ad70a0d15621027900d16c33abd/scripts/sync_garmin.py)、[Nicolas auth](https://github.com/Nicolasvegam/garmin-connect-mcp/blob/9478e37ff48c8414e77208ad1cb748be481da097/src/client/garmin-auth.ts)、[Nicolas client](https://github.com/Nicolasvegam/garmin-connect-mcp/blob/9478e37ff48c8414e77208ad1cb748be481da097/src/client/garmin.client.ts)、[GarminDB auth](https://github.com/tcgoetz/GarminDB/blob/62409888d853d7cf4acd1bb7320337ce9f942176/garmindb/garmin_connect_auth_adapter.py)、[givemydata client](https://github.com/nrvim/garmin-givemydata/blob/e547f5fae84bd38038725dffdf30ea95f762cb10/garmin_client/client.py)、[njzyshare auth](https://github.com/njzyshare/garmin-running-analysis/blob/60bd57ddcd662865d0e00f7b6f42740f6bf6afb1/scripts/garmin_auth.py)、[Panorama client](https://github.com/runzhenghengbin/garmin-panorama-training-analysis/blob/fb874218d26138bf7c646bddb2fe5c0e19dff186/scripts/garmin_client.py)、[gosanke sync](https://github.com/gosanke/garmin-ai-secure/blob/50d97330ed07a133b876fbe0a8af489b6a5737f0/sync_garmin.py)、[train Skill](https://github.com/GeoffreyBian/train/blob/4f39451b4473351c5305d134b292481a523d496c/skills/garmin/SKILL.md)。上述每项均是所链接 commit 的检查结论。

### Coach 的三条边界不能合并

1. 普通 phased plan 与旧 Coach/adaptive 的 REST 详情地址不同；库有 get_training_plan_by_id 与 get_adaptive_training_plan_by_id。旧脚本对所有计划调用 adaptive，不能直接变成通用分派。
2. 新版 ATP/Coach 日程可能需要 GraphQL trainingPlanScalar，单个任务详情还可能使用 workout-service/fbt-adaptive/{uuid}。REST 列表空并不充分证明无正在进行的计划。
3. [Taxus 源码](https://github.com/Taxuspt/garmin_mcp/blob/cfc5d799ab0f165e837f1188a1d093c65838aaf7/src/garmin_mcp/workouts.py#L629)与 [mocks](https://github.com/Taxuspt/garmin_mcp/blob/cfc5d799ab0f165e837f1188a1d093c65838aaf7/tests/integration/test_workouts_tools.py#L1275)展示该路线；[#347](https://github.com/Taxuspt/garmin_mcp/issues/347)同时报告 adaptive 元数据丢失、旧 REST 列表空/详情 404。[PR #375](https://github.com/Taxuspt/garmin_mcp/pull/375)截至查询仍 open、merged_at=null，不能把其测试声明算入默认分支实现。这是重要外部报告，CN 账号适用性 U。

### 托管、付费与“本地”的实际边界

[nftechie Skill](https://github.com/nftechie/garmin-skill/blob/85c0ade79de52acfddf7cf3c0f40b38183c18577/SKILL.md)依赖 Transition 账号/API key，个人 Garmin 数据由其服务同步，教练回答调用远程接口。README 当时声称 free 100 reads/3 AI requests 每日、另有 paid tier；本轮未注册或验证价格。排除为默认路线。

其他重点候选在所查核心代码中未见强制付费模型 API。dsebastien、garth、Nicolas 的 OAuth 路线会访问第三方 S3 consumer 配置；gccli 仍留有该旧 OAuth 配置路径，新的 DI 主路径不是同一流程。Panorama 的天气依赖 Open-Meteo。MCP/Skill 也不意味着推理留在本机：将摘要交给哪个 Agent、是否使用云模型，由用户现有环境决定。我们只能承诺工具不额外接入模型或上传服务。

本地数据方案 README 的“100% working”“安全审计”“兼容所有账号”“python-garminconnect 仍依赖 garth”等不是验证结论；后一说法已与所查 0.3.x 依赖源码矛盾。

## 旧实现的只读审计与复现

所要求入口均可访问：README、setup、pyproject、lock、scripts、tests、两个 Garmin Skill、项目笔记。没有材料缺失阻塞。维护 Skill 及 vault AGENTS 只用于理解原流程；其中路径、默认训练目标、平台约定不适用于本仓库。

| 发现 | 证据与影响 | 本轮验证 |
| --- | --- | --- |
| 活动失败被当零次跑步 | fetch_recent_activities 写 ok=false；报告只查 region/range；training_summary 对缺 running_activities 用 [] | V：虚构失败 JSON 通过 validate_report_inputs，build_report 含“跑步次数：0” |
| 异常活动结构也被当空 | 抓取成功但非 list 时强制 [] | S；新契约必须标 invalid，而非 empty |
| 计划未同等校验 | load_inputs 加载计划但不查 region/时效/status；失败输出甚至缺 region/window | V：global、旧日期、ok=false 的虚构计划被 CN 报告接受；失败计划显示没有进行中计划 |
| 文件与 token 冲突 | 日/活动/计划文件名无 region/profile；DEFAULT_TOKENSTORE 无区域后缀 | S；提示词中的“另设目录”不是实现隔离 |
| 固定请求量、错误后继续 | DAILY_METHODS 23 项，7 天是 161 次顶层调用；部分方法内部还会请求。认证/429 只在循环完毕后汇总失败 | S；没有执行这些抓取 |
| 时效与身份不充分 | 日/活动缺 fetched_at、profile/account 绑定、timezone；按文件名日期选 latest 不等于新鲜或同账号 | S；不能用 mtime 或文件名替代校验 |
| 默认结论耦合 | pace≤4.5 min/km 被划疑似强度；固定压力/睡眠阈值；Skill 含私人训练目标 | S；不迁入通用分析结论 |
| 已有可用防护 | 范围/区域校验、源路径去绝对化、报告原子发布/默认防覆盖、摘要降维、归档保留被引用文件 | S/T；需要按新契约迁移，不能认为已覆盖所有失败 |

V：在旧工具目录以系统 Python 执行 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q`，22 tests passed；测试使用临时目录/虚构数据，不联网。另以临时虚构输入完成上表 4 项复现断言，未把复现输入或源码复制到新仓库。测试通过与缺陷复现同时成立，说明原回归套件有空白。

为后续白名单迁移留存以下源文件 SHA-256（相对于旧 Garmin 工具目录；不保留私人根路径）：

| 文件 | SHA-256 |
| --- | --- |
| pyproject.toml | 2e772738bbc3b10dcc92a3b4cc446199d1a649e572aee3938951c821247a83d4 |
| uv.lock | ee5161aae124e7f78c2ff380f677a0d3c7f0b0c327b1282dac8ab9405bfa7d7c |
| scripts/common_garmin.py | 847c74213ad425a725f441fec6c93d5d37424b452950476691d1d30f82f59972 |
| scripts/fetch_recent_activities.py | 15ba68714300859ed5dfb6ffdcdd657cebe8552624621b3ade90eb3daf10d95e |
| scripts/fetch_training_plans.py | 702c9f24f3b85258642e54d21aa84920b6f292a2b3a2b5f86394c7cf488c3266 |
| scripts/generate_weekly_report.py | 870fef420b96f04392e84c64a89aca3a3c4fc401c17ed4fe6e46cadc83d3af4c |
| tests/test_garmin_scripts.py | 607b2ee10428b62d4e3bf65a867032fbccbe6c14268383f9e16437c471b315a7 |

## 调研收敛与未验证项

接入指标本身已有广泛实现；中文、Markdown、Skill 和本地归档也都不是独有能力。没有找到同时具备 CN 认证恢复、强制 profile/region 隔离、失败不当零、按需摘要、所有计划家族验证、可追溯中文周报与独立安装闭环的现成项目。没有依据给出“满足百分之多少”；应按需求分层，见 decisions。

新增中文 Skill、归档与 Markdown 项目没有改变核心取舍：接入库复用，可靠的数据契约与分析流程由我们维护。继续罗列同类包装不会解决 CN/MFA 与计划家族的实测空白，因此在 15 个深入检查对象处收敛。

剩余 U：当前 CN/global 首次登录与 MFA、失效 token 的真实恢复、设备实际字段与同步滞后、CN 新版 ATP GraphQL/详情、独立 macOS/Linux/Windows 安装、各 Agent 的发现与执行行为、真实限流响应。上游测试仅检查其存在与断言范围，未运行；上游 release/PR 自报通过与本轮测试分开。下一步只验证会改变选型的这些问题，不需要开始全量历史下载、MCP 服务或数据库建设。
