<p align="center">
  <a href="./README.md">English</a> | <strong>中文</strong>
</p>

<h1 align="center">icloud-photo-sync</h1>

<p align="center"><strong>面向 local-first 照片库的 iCloud Photos 到 NAS 守护式镜像工具</strong></p>
<p align="center">先规划后变更 · 严格内容匹配 · 自动发现与手工 Apply 分离</p>

<table>
  <tr>
    <td width="33%" valign="top">
      <strong>主要用途</strong><br/>
      把 <code>iCloud Photos</code> 镜像到 NAS，同时避免让 NAS 反过来变成照片目录的真相源
    </td>
    <td width="33%" valign="top">
      <strong>操作入口</strong><br/>
      Python CLI 加 shell 包装脚本，并可选接入 <code>launchd</code> 做定时 <code>plan</code>
    </td>
    <td width="33%" valign="top">
      <strong>安全模型</strong><br/>
      <code>plan</code> 可以自动跑，<code>apply</code> 保持显式触发，NAS 删除先进入待删池而不是直接硬删
    </td>
  </tr>
</table>

> 对外，`icloud-photo-sync` 是一个 `iCloud Photos -> NAS` 的 local-first 镜像工具。对内，它是一套把规划阶段与文件变更阶段严格拆开的双阶段同步面。

## 项目定位

当你的照片管理规则是“`iCloud Photos` 唯一主源、`NAS` 只是镜像、备份工具不参与主判断”时，这个仓库提供的是可复现的文件级同步，而不是一次次手工导出再复制。

它刻意不做成通用照片管理器，而是明确坚持：

- `iCloud Photos` 是权威目录
- NAS 是镜像目标，不是日常整理入口
- `OneDrive` 之类工具可以继续做异地备份，但不负责判断哪份是当前正确状态

## 它解决什么问题

- 基于当前 Photos 库、NAS 内容和持久化状态生成一次 `plan`
- 将 iCloud 里新增或缺失于 NAS 的媒体文件复制到镜像库
- 当内容已从 iCloud 消失时，把 NAS 上的对应项移动到 `/Volumes/home/Photos_DeletedFromICloud`，而不是直接删除
- 把运行收据统一落到 `/Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>/`
- 允许定时自动发现变化，但不把 NAS 变更权限直接交给定时任务

## 快速开始

在仓库根目录执行：

```bash
python3 -m tools.icloud_photo_sync.cli plan
python3 -m tools.icloud_photo_sync.cli apply --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
```

常用包装脚本：

```bash
./scripts/run_plan.sh
./scripts/run_apply_latest.sh --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
./scripts/run_apply_latest.sh --latest
```

## 运行期布局

仓库内只保留稳定、可追踪的内容：

- `tools/icloud_photo_sync/`：源码
- `tests/`：测试
- `docs/`：操作文档

运行期状态不作为 Git 事实的一部分：

- 状态库：`state/icloud-photo-sync/state.sqlite3`
- 临时 staging：`tmp/icloud_photo_sync_stage`
- 同步日志：`/Volumes/home/Photos_SyncLogs`
- NAS 待删池：`/Volumes/home/Photos_DeletedFromICloud`

## 自动化模型

推荐的自动化策略是非对称的：

- 自动执行 `plan`
- `apply` 保持手工触发
- 在真正修改 NAS 前，先审阅生成的计划目录或最新一次计划结果

这样可以让“发现变化”足够便宜，同时给复制和删除移动保留一道硬门槛。

## 当前边界

- 当前实现围绕 macOS Photos library 和仓库内置的 Swift bridge 构建。
- 匹配逻辑是严格内容导向的，不使用模糊启发式去合并“看起来像”的近重复项。
- NAS 删除采用可审计的待删池移动机制，而不是立即 destructive remove。
- 这个仓库是同步工具，不是通用 DAM、云后端或图库 UI。

## 面向 Agent

建议通过 CLI 和包装脚本操作本仓库，而不是自己重写同步逻辑。

典型 Agent 任务：

- 执行 `plan`
- 检查生成的收据与计划目录
- 对明确选定的 `plan_dir` 执行 `apply`
- 安装或审计定时 `plan` 自动化

## 文档

- [自动化说明](docs/automation.md)
- [主源工作流说明](docs/icloud-photo-authoritative-workflow.md)
- [设计文档](docs/specs/2026-04-09-icloud-photo-sync-design.md)
- [实施计划](docs/plans/2026-04-09-icloud-photo-sync.md)

当前详细文档以中文为主，因为实际运行面主要服务于个人、本地、长期运维。

## 技术验证

```bash
python3 -m pytest tests -q
```
