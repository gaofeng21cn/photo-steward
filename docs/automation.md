# Automation

## 目标

把 `icloud-photo-sync` 的自动化固定在独立仓库里，并明确三层职责：

- `iCloud Photos` 是唯一主源
- `NAS` 是跟随镜像
- `OneDrive` 只承接 `NAS` 的异地备份

自动化只负责稳定发现、留痕和备份，不负责绕过人工确认直接改动 NAS 主镜像。

除了照片主线，这个仓库现在也承载一类“主源目录 -> 备份镜像目录”的严格对齐工作流。当前已落地的例子是：

- `iCloud/Documents/ToDo -> OneDrive/ToDo`

这类目录同步同样坚持：

- `plan` 和 `apply` 分离
- 镜像侧多余内容先进入审核池
- `apply` 仍然显式触发，不交给定时任务直接落地

## 当前策略

- 自动执行 `plan-job`
- 自动执行 `todo-plan-job`
- 自动执行待删池保留期清理
- 自动执行 `NAS -> OneDrive` 备份
- `apply-job` 仍保持人工触发

这样可以把“发现变化”和“真正改文件”拆开：

- 每天稳定得到最新同步判断
- 对 NAS 的新增复制与待删移动仍然保留人工门槛
- 待删池和异地备份都有独立的留痕与状态文件

## CLI 入口

### 1. 计划任务

```bash
python3 -m tools.icloud_photo_sync.cli plan-job
```

作用：

- 跑一轮完整 `plan`
- 将最新结果写入 `state/status/latest_plan.json`
- 同时刷新 `state/status/latest_overview.md`

### 1b. ToDo 计划任务

```bash
python3 -m tools.icloud_photo_sync.cli todo-plan-job
```

作用：

- 以 `iCloud/Documents/ToDo` 为主源跑一轮 `todo-plan`
- 将最新结果写入 `state/status/latest_todo_plan.json`
- 同时刷新 `state/status/latest_overview.md`

### 2. 手工 Apply

显式指定计划目录：

```bash
python3 -m tools.icloud_photo_sync.cli apply-job --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
```

或使用包装脚本：

```bash
./scripts/run_apply_latest.sh --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
./scripts/run_apply_latest.sh --latest
```

约束：

- 只消费一个明确的计划目录
- 复制和待删移动都带 guard 校验
- NAS 删除不会硬删，而是进入 `/Volumes/home/Photos_DeletedFromICloud`

### 3. 待删池保留期清理

```bash
python3 -m tools.icloud_photo_sync.cli prune-deleted-pool --dry-run
python3 -m tools.icloud_photo_sync.cli prune-deleted-pool
```

当前规则：

- 以 `/Volumes/home/Photos_DeletedFromICloud/YYYY-MM-DD/` 一级日期目录为清理粒度
- 超过 `--retention-days` 的整天目录会被删除
- dry-run 只生成收据，不做实际删除

### 4. OneDrive 备份

```bash
python3 -m tools.icloud_photo_sync.cli backup-onedrive --dry-run
python3 -m tools.icloud_photo_sync.cli backup-onedrive
```

默认备份目标：

- `/Users/gaofeng/OneDrive/Backup/icloud-photo-sync/Photos`
- `/Users/gaofeng/OneDrive/Backup/icloud-photo-sync/Photos_DeletedFromICloud`
- `/Users/gaofeng/OneDrive/Backup/icloud-photo-sync/Photos_SyncLogs`

当前实现使用 `rsync -a --exclude=.DS_Store`，刻意 **不带 `--delete`**。

原因：

- `OneDrive` 只做异地备份，不参与主判断
- 它保留更长时间的历史回退价值
- 不应该因为 iCloud 或 NAS 的一次删除而立刻丢失异地回退副本

### 5. ToDo 主源对齐

```bash
python3 -m tools.icloud_photo_sync.cli todo-plan
python3 -m tools.icloud_photo_sync.cli todo-apply --plan-dir state/folder_sync_logs/YYYY-MM-DD/<plan_id>
```

默认路径：

- 主源：`/Users/gaofeng/Documents/ToDo`
- 镜像：`/Users/gaofeng/Library/CloudStorage/OneDrive-个人/ToDo`
- 审核池：`/Users/gaofeng/Library/CloudStorage/OneDrive-个人/ToDo_OneDriveOnlyReview/<plan_id>/`
- 计划日志：`state/folder_sync_logs/YYYY-MM-DD/<plan_id>/`

行为约束：

- 路径比较使用 Unicode `NFC` 规范化，避免中日韩文件名组合差异误判
- 内容判断使用严格内容签名；普通文件按 `SHA-256`，符号链接按链接目标
- `OneDrive-only` 内容不直接删除，而是进入审核池
- 真正的主源补齐复制只发生在审核池迁移之后

## 包装脚本

仓库提供以下包装脚本：

- `scripts/run_plan.sh`
- `scripts/run_todo_plan.sh`
- `scripts/run_apply_latest.sh`
- `scripts/run_deleted_pool_retention.sh`
- `scripts/run_onedrive_backup.sh`
- `scripts/install_launchd_agents.sh`

默认 Python 解释器：

- `/Users/gaofeng/.py-global/bin/python3`

这样可以避免 `launchd` 落回系统自带 `/usr/bin/python3` 导致环境不一致。

## launchd 安装

安装整套任务：

```bash
./scripts/install_launchd_agents.sh
```

兼容入口：

```bash
./scripts/install_launchd_plan_agent.sh
```

它现在只是转调 `install_launchd_agents.sh`。

## 默认计划

- `com.gaofeng.icloud-photo-sync.plan.daily`
  - 时间：每天 `03:15`
  - stdout：`tmp/automation/plan.stdout.log`
  - stderr：`tmp/automation/plan.stderr.log`
- `com.gaofeng.icloud-photo-sync.todo.daily`
  - 时间：每天 `04:30`
  - stdout：`tmp/automation/todo.stdout.log`
  - stderr：`tmp/automation/todo.stderr.log`
- `com.gaofeng.icloud-photo-sync.deleted-pool.daily`
  - 时间：每天 `04:00`
  - stdout：`tmp/automation/deleted-pool.stdout.log`
  - stderr：`tmp/automation/deleted-pool.stderr.log`
- `com.gaofeng.icloud-photo-sync.onedrive.daily`
  - 时间：每天 `04:15`
  - stdout：`tmp/automation/onedrive.stdout.log`
  - stderr：`tmp/automation/onedrive.stderr.log`

## 状态与留痕

最新状态文件：

- `state/status/latest_plan.json`
- `state/status/latest_todo_plan.json`
- `state/status/latest_apply.json`
- `state/status/latest_deleted_pool.json`
- `state/status/latest_onedrive.json`
- `state/status/latest_overview.md`

运行收据：

- `plan` / `apply`：`/Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>/`
- `deleted-pool` / `onedrive`：`/Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<job_id>.json`
- `todo-plan` / `todo-apply`：`state/folder_sync_logs/YYYY-MM-DD/<plan_id>/`

`latest_overview.md` 用来快速回答三个问题：

- 最近一次 `plan` 是否成功
- 最近一次 `todo-plan` 是否成功
- 最近一次 `apply` 是否执行过
- 待删池清理和 OneDrive 备份最近状态如何

## 推荐验证命令

安装后，先手工验证一遍：

```bash
python3 -m pytest tests -q
./scripts/run_plan.sh
./scripts/run_todo_plan.sh
python3 -m tools.icloud_photo_sync.cli prune-deleted-pool --dry-run
python3 -m tools.icloud_photo_sync.cli backup-onedrive --dry-run
```

然后再检查：

- `state/status/latest_overview.md`
- `tmp/automation/*.log`
- `/Volumes/home/Photos_SyncLogs/YYYY-MM-DD/`

如果要直接触发 `launchd`：

```bash
launchctl kickstart -k gui/$(id -u)/com.gaofeng.icloud-photo-sync.plan.daily
launchctl kickstart -k gui/$(id -u)/com.gaofeng.icloud-photo-sync.todo.daily
launchctl kickstart -k gui/$(id -u)/com.gaofeng.icloud-photo-sync.deleted-pool.daily
launchctl kickstart -k gui/$(id -u)/com.gaofeng.icloud-photo-sync.onedrive.daily
```

## 边界

- `apply` 暂不自动化，这是故意保留的人为确认门槛
- `OneDrive` 不参与同步判断，也不执行跟删
- `Photos.sqlite` 现在只作为本地 originals 的可选加速器；若不可读，`plan` 仍应通过 Photos 元数据链路完成判断并把警告写入 `plan_summary.json`
- `ToDo` 这类目录同步当前未接入定时任务；建议先手工 `todo-plan` / `todo-apply` 运行稳定后，再决定是否单独挂自动化
- 当前已接入 `todo-plan-job` 的定时发现，但 `todo-apply` 仍保持手工触发
