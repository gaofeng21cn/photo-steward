# Automation

## 目标

把 `icloud-photo-sync` 的自动化固定到独立仓库，而不是绑定旧的 `Codex` 工作区。

## 当前策略

- 自动化任务只跑 `plan`
- `apply` 保持人工触发
- 所有待删项先进入 `/Volumes/home/Photos_DeletedFromICloud`

这样能保证：

- iCloud 新增会定期发现并进入 NAS 镜像流程
- iCloud 删除会定期形成待删清单
- 真正对 NAS 做复制和移动时，仍然经过一次人工确认

## 本仓库提供的入口

- `scripts/run_plan.sh`
  - 从仓库根目录运行 `python3 -m tools.icloud_photo_sync.cli plan`
- `scripts/run_apply_latest.sh`
  - 支持 `--plan-dir <path>` 显式执行
  - 也支持 `--latest` 读取最近一次计划目录再执行
- `scripts/install_launchd_plan_agent.sh`
  - 安装并加载一个每日定时 `plan` 的 `launchd` 任务

## launchd 默认计划

- label: `com.gaofeng.icloud-photo-sync.plan.daily`
- 频率: 每天 `03:15`
- stdout: `tmp/automation/plan.stdout.log`
- stderr: `tmp/automation/plan.stderr.log`

## 查看

```bash
launchctl print gui/$(id -u)/com.gaofeng.icloud-photo-sync.plan.daily
```

最近一次计划输出仍然写入：

- `/Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>/`

## 手动 apply

显式指定计划目录：

```bash
./scripts/run_apply_latest.sh --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
```

或直接对最近一次计划执行：

```bash
./scripts/run_apply_latest.sh --latest
```

`apply` 仍然遵守原有约束：

- 只消费一个明确的计划目录
- 复制和待删移动都带 guard 校验
- 待删进入 `/Volumes/home/Photos_DeletedFromICloud`

