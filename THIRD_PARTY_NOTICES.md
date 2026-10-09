# 依赖与参考

本项目通过依赖使用 [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) 0.3.17（MIT），以及 platformdirs、filelock、tzdata；各自发行包保留其许可文件。本仓库没有 vendored Garmin SDK。

Coach GraphQL 标量、任务日程字段与 UUID 详情路线参考 [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp/tree/cfc5d799ab0f165e837f1188a1d093c65838aaf7)（MIT），本地适配与测试独立编写。CLI、Skill 和失败处理的其他设计来源列于 [research.md](docs/research.md)，本轮未摘取第三方实现代码。

图标和 README 横幅是本项目原创 SVG，不使用 Garmin 官方标志。Garmin、Garmin Connect、Body Battery 等名称归其权利人所有。
