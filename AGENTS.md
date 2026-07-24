# iCloud Photo Sync

本仓持有 iCloud Photos/目录主源到 NAS 或备份镜像的 guarded plan/apply 工具。

- iCloud 是权威源，NAS/OneDrive 是镜像或备份；不要反向推断主源，也不要把 NAS-only 内容直接硬删除。
- 自动化默认只生成 plan；`apply`、`todo-apply` 和非 dry-run retention 必须针对已审阅的精确 plan 显式执行。
- 私人照片、输出、数据库、日志、auth state 和绝对环境配置不得进入 Git；运行态留在 README 指定的 ignored/external 路径。
- 复用 CLI 和 `scripts/` wrapper，不另写旁路同步逻辑；变更后运行 `python3 -m pytest tests -q`，真实 mutation 还须检查 plan receipt 与目标端 readback。

<!-- CODEGRAPH_START -->
## CodeGraph

- 本仓库使用本地 `.codegraph/` 索引；该目录不得纳入 Git。
- 定义、调用、影响范围和代码路径等结构检索优先使用 CodeGraph；字面文本检索使用 `rg`。
- 索引缺失或过期时运行 `codegraph init .` 或 `codegraph sync .`。
<!-- CODEGRAPH_END -->
