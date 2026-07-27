<p align="center">
  <a href="./README.md">English</a> | <strong>中文</strong>
</p>

<h1 align="center">icloud-photo-sync</h1>

<p align="center"><strong>以 iCloud Photos 为权威源的本机照片中台同步服务</strong></p>
<p align="center">先规划后变更 · 严格内容匹配 · 自动发现与手工 Apply 分离</p>

<table>
  <tr>
    <td width="33%" valign="top">
      <strong>主要用途</strong><br/>
      把 <code>iCloud Photos</code> 镜像到 NAS，并把像 <code>ToDo</code> 这类 iCloud 主源目录严格对齐到备份云盘，同时避免备份端反过来变成真相源
    </td>
    <td width="33%" valign="top">
      <strong>操作入口</strong><br/>
      CLI 维护接口、Codex 专业 Skill 交互入口和 macOS 照片中心控制台；<code>launchd</code> 负责定时发现与备份
    </td>
    <td width="33%" valign="top">
      <strong>安全模型</strong><br/>
      <code>plan</code> 可以自动跑，<code>apply</code> 保持显式触发，NAS 删除先进入待删池而不是直接硬删
    </td>
  </tr>
</table>

> 对外，`icloud-photo-sync` 最初是一个 `iCloud Photos -> NAS` 的 local-first 镜像工具。现在它也承载了 `iCloud 主源目录 -> 备份镜像目录` 的双阶段同步能力，例如 `Documents/ToDo -> OneDrive/ToDo`。

## 项目定位

用户应把本项目理解为“iCloud 照片中台的本机同步服务”，而不是一组零散脚本：

- 确定性服务与 CLI：执行资源识别、计划、复制、日期重定位、隔离和收据
- Codex 专业 Skill：主要用户入口，负责检查、解释、复核和经确认后执行
- macOS App：菜单栏提供快速状态与入口，主控制台提供状态、计划审阅和人工执行；不复制同步逻辑

它是控制面 AI-first、数据面确定性的系统。AI 可以解释差额和组织复核，但覆盖、迁移与删除只接受可重复的元数据、SHA-256、guard 和收据证据。

当你的照片管理规则是“`iCloud Photos` 唯一主源、`NAS` 只是镜像、备份工具不参与主判断”时，这个仓库提供的是可复现的文件级同步，而不是一次次手工导出再复制。

它刻意不做成通用照片管理器，而是明确坚持：

- `iCloud Photos` 是权威目录
- NAS 是镜像目标，不是日常整理入口
- `OneDrive` 之类工具可以继续做异地备份，但不负责判断哪份是当前正确状态
- 像 `ToDo` 这样的工作目录也应复用同样的 `plan -> apply -> 审核池` 机制，而不是人工拖拽同步

## 它解决什么问题

- 基于当前 Photos 库、NAS 内容和持久化状态生成一次 `plan`
- 将 iCloud 里新增或缺失于 NAS 的媒体文件复制到镜像库
- 当内容已从 iCloud 消失时，把 NAS 上的对应项移动到 `/Volumes/home/Photos_DeletedFromICloud`，而不是直接删除
- 把运行收据统一落到 `/Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>/`
- 允许定时自动发现变化，但不把 NAS 变更权限直接交给定时任务
- 针对主源目录生成严格的 `folder-plan`，并把镜像侧残留内容先移入审核池，再复制主源视图

## 快速开始

在仓库根目录执行：

```bash
python3 -m tools.icloud_photo_sync.cli preflight
python3 -m tools.icloud_photo_sync.cli status --scope photo
python3 -m tools.icloud_photo_sync.cli plan
python3 -m tools.icloud_photo_sync.cli apply --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
python3 -m tools.icloud_photo_sync.cli plan-job
python3 -m tools.icloud_photo_sync.cli todo-plan-job
python3 -m tools.icloud_photo_sync.cli prune-deleted-pool --dry-run
python3 -m tools.icloud_photo_sync.cli backup-onedrive --dry-run
python3 -m tools.icloud_photo_sync.cli todo-plan
python3 -m tools.icloud_photo_sync.cli todo-apply --plan-dir state/folder_sync_logs/YYYY-MM-DD/<plan_id>
```

常用包装脚本：

```bash
./scripts/run_plan.sh
./scripts/run_todo_plan.sh
./scripts/run_apply_latest.sh --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
./scripts/run_apply_latest.sh --latest
./scripts/run_deleted_pool_retention.sh --dry-run
./scripts/run_onedrive_backup.sh --dry-run
./scripts/install_launchd_agents.sh
./scripts/install_local.sh
./scripts/install_menu_bar_app.sh
```

## 运行期布局

仓库内只保留稳定、可追踪的内容：

- `tools/icloud_photo_sync/`：源码
- `tests/`：测试
- `docs/`：操作文档

运行期状态不作为 Git 事实的一部分：

- 状态库：`state/icloud-photo-sync/state.sqlite3`
- 最新作业状态：`state/status/latest_*.json`
- 最新总览：`state/status/latest_overview.md`
- 照片状态总览：`state/status/latest_photo_overview.md`
- ToDo 状态总览：`state/status/latest_todo_overview.md`
- 临时 staging：`tmp/icloud_photo_sync_stage`
- 同步日志：`/Volumes/home/Photos_SyncLogs`
- 通用目录同步日志：`state/folder_sync_logs`
- NAS 待删池：`/Volumes/home/Photos_DeletedFromICloud`
- OneDrive 备份根目录：`/Users/gaofeng/OneDrive/Backup/icloud-photo-sync`
- ToDo 审核池：`/Users/gaofeng/Library/CloudStorage/OneDrive-个人/ToDo_OneDriveOnlyReview/<plan_id>/`

## 自动化模型

推荐的自动化策略是分层且非对称的：

- 自动执行 `plan-job`
- 自动执行待删池保留期清理
- 自动执行从 NAS 到 OneDrive 的备份
- `apply` 保持手工触发
- 在真正修改 NAS 前，先审阅生成的计划目录或最新一次计划结果
- ToDo 计划发现通过 `scripts/install_launchd_todo_agent.sh` 显式启用，与照片中心状态分开

这样可以让“发现变化”足够便宜，同时给复制和删除移动保留一道硬门槛。

`./scripts/install_launchd_agents.sh` 默认安装三条照片中心 `launchd` 任务：

- `com.gaofeng.icloud-photo-sync.plan.daily`：`03:15`
- `com.gaofeng.icloud-photo-sync.deleted-pool.daily`：`04:00`
- `com.gaofeng.icloud-photo-sync.onedrive.daily`：`04:15`

如需 ToDo 计划发现，再单独执行：

```bash
./scripts/install_launchd_todo_agent.sh
```

ToDo 任务的 stdout/stderr 也写到 `tmp/automation/`，但不属于照片中心健康状态。

## 三层用户入口

安装本机 CLI 和 Codex Skill：

```bash
./scripts/install_local.sh
icloud-photo-sync status --scope photo --format json
```

安装菜单栏控制台：

```bash
./scripts/install_menu_bar_app.sh
open "$HOME/Applications/iCloud Photo Center.app"
```

Skill 和 macOS App 都调用同一个 CLI。Skill 负责自然语言检查、计划解释、
审批组织和显式 Apply；App 的菜单栏入口显示摘要并可打开主控制台。主控制台可
刷新状态、手工生成计划、审阅待审计划的范围与阻塞项，并在确认后调用同一个
`apply-job`。同步规则、身份、SHA-256、guard 和 receipt 只有底层服务拥有。

日常使用 App 时，先从菜单栏点击“打开控制台”，再选择“生成计划”。计划会先
成为待审状态，只有在“待审计划”页核对精确计划、影响范围和未解析项后，才可
以确认执行 Apply。App 不会绕过这道确认门槛，也不会替代定时任务执行 Apply。

照片相关命令在扫描 Photos 或 NAS 前严格验证 `/Volumes/home` 是可读写的 `smbfs` 挂载，并把 `mounted_from`、挂载点和文件系统写入状态。目录存在但 SMB 未挂载时会 fail-closed，避免写进本地同名目录。

定时任务由 `launchd` 直接启动仓库内的 wrapper，再进入同一 CLI。这样
Photos.framework bridge 保持稳定的 launchd 执行上下文，不会继承 App 的 TCC
责任进程身份。自动化只产生计划、执行保留期维护与备份；App 只提供状态、手工
计划、待审计划审阅和显式 Apply，不包含第二套同步规则。NAS 预检有有限重试和
单次超时，目录遍历错误会 fail-closed 并写入最新状态。

## 当前边界

- 当前实现围绕 macOS Photos library 和仓库内置的 Swift bridge 构建。
- 匹配逻辑是严格内容导向的，不使用模糊启发式去合并“看起来像”的近重复项。
- NAS 删除采用可审计的待删池移动机制，而不是立即 destructive remove。
- 通用目录同步同样坚持主源权威：镜像侧多余内容先移入审核池，再复制主源内容。
- 这个仓库是同步工具，不是通用 DAM、云后端或图库 UI。

## 面向 Agent

建议通过 CLI 和包装脚本操作本仓库，而不是自己重写同步逻辑。

典型 Agent 任务：

- 执行 `plan`
- 执行 `plan-job` 并检查 `state/status/latest_plan.json`
- 执行 `todo-plan-job` 并检查 `state/status/latest_todo_plan.json`
- 检查生成的收据与计划目录
- 对明确选定的 `plan_dir` 执行 `apply`
- 执行 `todo-plan`，对齐 `/Users/gaofeng/Documents/ToDo` 与 `OneDrive/ToDo`
- 检查 `state/folder_sync_logs/YYYY-MM-DD/<plan_id>/`
- 只对已审阅的目录计划执行 `todo-apply`
- 以 dry-run 方式执行 `prune-deleted-pool` 或 `backup-onedrive`
- 安装或审计整套定时自动化

## 文档

- [自动化说明](docs/automation.md)
- [产品与架构](docs/architecture.md)
- [主源工作流说明](docs/icloud-photo-authoritative-workflow.md)
- [设计文档](docs/specs/2026-04-09-icloud-photo-sync-design.md)
- [实施计划](docs/plans/2026-04-09-icloud-photo-sync.md)
- [ToDo 主源对齐设计](docs/specs/2026-04-10-icloud-todo-onedrive-design.md)
- [ToDo 主源对齐实施计划](docs/plans/2026-04-10-icloud-todo-onedrive.md)

当前详细文档以中文为主，因为实际运行面主要服务于个人、本地、长期运维。

## 技术验证

```bash
python3 -m pytest tests -q
```
