# Automation

## 目标

把 `icloud-photo-sync` 的自动化固定在独立仓库里，并明确三层职责：

- `iCloud Photos` 是唯一主源
- `NAS` 是跟随镜像
- `OneDrive` 只承接 `NAS` 的异地备份

自动化只负责稳定发现、留痕和备份，不负责绕过人工确认直接改动 NAS 主镜像。
macOS App 可以由操作者手工生成计划、审阅待审计划，并在明确确认后执行该精确
计划；这不会改变自动化只生成计划的边界。

除了照片主线，这个仓库现在也承载一类“主源目录 -> 备份镜像目录”的严格对齐工作流。当前已落地的例子是：

- `iCloud/Documents/ToDo -> OneDrive/ToDo`

这类目录同步同样坚持：

- `plan` 和 `apply` 分离
- 镜像侧多余内容先进入审核池
- `apply` 仍然显式触发，不交给定时任务直接落地

## 当前策略

- 自动执行 `plan-job`
- 自动审计待删池保留期候选，默认不删除
- 在 NAS 尚未接管时，由 Mac 串行执行 `NAS -> OneDrive` 备份和保留期审计
- `apply-job` 仍保持人工触发
- ToDo `todo-plan-job` 为可选项，与照片计划共享每周调度，但保持独立业务状态

这样可以把“发现变化”和“真正改文件”拆开：

- 每周稳定得到最新同步判断
- 对 NAS 的新增复制与待删移动仍然保留人工门槛
- 待删池和异地备份都有独立的留痕与状态文件

## CLI 入口

### 0. 运行前检查与状态

```bash
python3 -m tools.icloud_photo_sync.cli preflight
python3 -m tools.icloud_photo_sync.cli status --scope photo --format json
python3 -m tools.icloud_photo_sync.cli status --scope todo --format markdown
```

`preflight` 必须确认 NAS 路径由独立 `smbfs` 挂载承载，并回读
`mounted_from`、挂载点、文件系统及读写能力。这样 `<nas-mount>`
目录存在但 SMB 未挂载时不会误写本地磁盘。

写能力通过挂载根目录中的持久空文件
`<nas-mount>/.icloud-photo-sync-write-probe` 验证。检查只打开或创建
该 sentinel，不写入、不截断、不删除，避免每次运行都向 Synology
`#recycle` 产生临时探针文件。

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
python3 -m tools.icloud_photo_sync.cli apply-job --plan-dir <nas-mount>/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
```

或使用包装脚本：

```bash
./scripts/run_apply_latest.sh --plan-dir <nas-mount>/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
./scripts/run_apply_latest.sh --latest
```

约束：

- App 中先生成计划，再在“待审计划”页核对计划目录、影响范围和未解析项
- 只有确认后才执行该精确计划；App 不会自动选择或自动 Apply
- 也可以使用 CLI 或 Codex Skill 对已审阅的精确计划显式执行

- 只消费一个明确的计划目录
- 复制和待删移动都带 guard 校验
- NAS 删除不会硬删，而是进入 `<nas-mount>/Photos_DeletedFromICloud`

### 3. 待删池保留期清理

```bash
python3 -m tools.icloud_photo_sync.cli prune-deleted-pool --dry-run
python3 -m tools.icloud_photo_sync.cli prune-deleted-pool
```

当前规则：

- 以 `<nas-mount>/Photos_DeletedFromICloud/YYYY-MM-DD/` 一级日期目录为清理粒度
- 超过 `--retention-days` 的整天目录会被删除
- dry-run 只生成收据，不做实际删除

### 4. OneDrive 备份

```bash
python3 -m tools.icloud_photo_sync.cli backup-onedrive --dry-run
python3 -m tools.icloud_photo_sync.cli backup-onedrive
```

默认备份目标：

- `<home>/OneDrive/Backup/icloud-photo-sync/Photos`
- `<home>/OneDrive/Backup/icloud-photo-sync/Photos_DeletedFromICloud`
- `<home>/OneDrive/Backup/icloud-photo-sync/Photos_SyncLogs`

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

- 主源：`<home>/Documents/ToDo`
- 镜像：`<home>/Library/CloudStorage/OneDrive-Personal/ToDo`
- 审核池：`<home>/Library/CloudStorage/OneDrive-Personal/ToDo_OneDriveOnlyReview/<plan_id>/`
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
- `scripts/run_weekly_orchestrator.sh`
- `scripts/run_nas_maintenance.sh`
- `scripts/run_apply_latest.sh`
- `scripts/run_deleted_pool_retention.sh`
- `scripts/run_onedrive_backup.sh`
- `scripts/install_launchd_agents.sh`

包装脚本按 `/opt/homebrew/bin/python3`、`/usr/local/bin/python3`、
`$HOME/.py-global/bin/python3` 的顺序选择可实际启动的 Python 3.10+。
`PYTHON_BIN` 可显式覆盖。探测会真正启动解释器，不只检查可执行位。

## launchd 安装

安装整套任务：

```bash
./scripts/install_launchd_agents.sh
```

默认安装两条任务：依赖本机 Photos 的每周调度器，以及 DSM 尚未接管时的
NAS 维护回退。ToDo 计划发现是显式 opt-in：

```bash
./scripts/install_launchd_todo_agent.sh
```

安装脚本会先构建并签名菜单栏 App，随后让 plist 的
`ProgramArguments` 直接指向对应 wrapper：

```text
weekly          -> scripts/run_weekly_orchestrator.sh
nas-maintenance -> scripts/run_nas_maintenance.sh
```

wrapper 仍调用同一个 CLI，不复制计划、Apply、guard 或 receipt 逻辑。直接
启动也让 Photos.framework bridge 保持 launchd 执行上下文，避免继承菜单栏
App 的 TCC 责任进程身份。菜单栏 App 只承担交互控制台职责。

签名可通过 `PHOTO_CENTER_SIGNING_IDENTITY` 显式指定；否则自动选择本机首个
`Developer ID Application`。钥匙串锁定或没有证书时回退到 ad-hoc 签名，
App 仍可运行，但 Network Volumes 权限身份应在解锁后重新签名。

兼容入口：

```bash
./scripts/install_launchd_plan_agent.sh
```

它现在只是转调 `install_launchd_agents.sh`。

## 默认照片中心计划

- `com.photosteward.weekly`
  - 时间：每周日 `03:15`
  - 顺序：照片 `plan-job`，然后是可选的 `todo-plan-job`
  - stdout/stderr：`~/Library/Logs/Photo Steward/weekly.*.log`
  - 子任务失败后继续后续任务；聚合收据区分进程状态和业务状态
- `com.photosteward.nas-maintenance.weekly`
  - 时间：每周日 `04:00`
  - 顺序：可选 OneDrive 备份，然后是待删池 dry-run 审计
  - stdout/stderr：`~/Library/Logs/Photo Steward/nas-maintenance.*.log`
  - 仅在 DSM 尚未形成有效接管回执时安装

升级时会卸载旧的 `plan.daily`、`todo.daily`、`deleted-pool.daily` 和
`onedrive.daily` plist，避免重复调度。系统内部可能仍保留旧 label 的 enabled
override；只要没有 plist、loaded service 或进程，它不构成实际任务。

## Synology 分工

NAS worker 只使用 NAS 本地路径，不依赖 macOS Photos.framework：

```bash
PHOTO_STEWARD_NAS_HOST=user@nas.local \
  ./scripts/nas/install_synology_worker.sh
```

安装器会上传 worker、执行一次 `--dry-run`，并在 NAS 写入
`~/.local/share/photo-steward/deployment.json`。它不会创建 DSM Task Scheduler
任务，也不会修改 Cloud Sync；这两项需要 DSM 管理员在权威界面完成。

DSM 每周任务建议命令：

```bash
~/.local/share/photo-steward/photo_steward_nas_worker.py --nas-home "$HOME"
```

默认行为是备份加 retention 审计，备份不带 `--delete`，retention 不删除。
只有在审阅最新 NAS receipt 的 `candidate_roots` 后，才可针对一次明确操作增加
`--apply-retention`。不要把永久删除放入无人值守的默认调度。

停用 Mac 回退前，必须在
`~/Library/Application Support/Photo Steward/nas-jobs-external` 写入经过人工核验的
私有 JSON 回执：

```json
{
  "schema_version": 1,
  "status": "verified",
  "scheduler": "synology_dsm_task_scheduler",
  "scheduler_status": "installed",
  "cloud_sync": {
    "direction": "upload_only",
    "delete_destination_on_source_delete": false
  }
}
```

随后重新运行 `install_launchd_agents.sh --nas-jobs-external`。缺少或篡改这份回执
时，安装器会拒绝切换，App 也会继续恢复 Mac 回退任务。

## 状态与留痕

最新状态文件：

- `state/status/latest_plan.json`
- `state/status/latest_todo_plan.json`
- `state/status/latest_apply.json`
- `state/status/latest_deleted_pool.json`
- `state/status/latest_onedrive.json`
- `state/status/latest_overview.md`
- `state/status/latest_photo_overview.md`
- `state/status/latest_todo_overview.md`

运行收据：

- `plan` / `apply`：`<nas-mount>/Photos_SyncLogs/YYYY-MM-DD/<plan_id>/`
- `deleted-pool` / `onedrive`：`<nas-mount>/Photos_SyncLogs/YYYY-MM-DD/<job_id>.json`
- `todo-plan` / `todo-apply`：`state/folder_sync_logs/YYYY-MM-DD/<plan_id>/`
- Mac weekly 聚合：`<runtime_state_dir>/scheduler/latest_weekly.json`
- NAS worker：`<nas-home>/Photos_SyncLogs/YYYY-MM-DD/nas-maintenance-*.json`

JSON 状态保留 `last_attempt_at`、`last_success_at`、`consecutive_failures`、
`pending_plan_dir` 和真实 `mount` 身份。失败不会再覆盖最后一次成功证据。
NAS 预检每次有硬超时；所有重试耗尽时返回 `75` 并写入 failed 状态。
NAS 遍历或指纹阶段发生权限错误时也 fail-closed，不会把不可读目录当成空库。

`latest_overview.md` 用来快速回答：

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
- `~/Library/Logs/Photo Steward/*.log`
- `<nas-mount>/Photos_SyncLogs/YYYY-MM-DD/`

如果要直接触发 `launchd`：

```bash
launchctl kickstart -k gui/$(id -u)/com.photosteward.weekly
launchctl kickstart -k gui/$(id -u)/com.photosteward.nas-maintenance.weekly
```

## 边界

- `apply` 暂不自动化，这是故意保留的人为确认门槛
- `OneDrive` 不参与同步判断，也不执行跟删
- `Photos.sqlite` 现在只作为本地 originals 的可选加速器；若不可读，`plan` 仍应通过 Photos 元数据链路完成判断并把警告写入 `plan_summary.json`
- `ToDo` 已接入每周调度中的独立 `todo-plan-job`，但 `todo-apply` 仍保持手工触发
- 照片与 ToDo 使用独立状态总览；共享代码不代表共享产品状态
