# iCloud Photo Sync Repo Extract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 iCloud Photos 半自动同步工具从 `<home>/workspace/Codex` 抽成独立仓库到 `<home>/workspace/app/icloud-photo-sync`，并为后续定时 automation 准备稳定入口。

**Architecture:** 保持现有 Python + Swift 结构和 `plan/apply` 行为不变，只调整仓库边界与默认路径。源码、测试、文档进入独立 repo；状态库、日志、待删池继续放在 repo 外部，避免把运行态数据纳入版本管理。automation 先固定到新 repo 的脚本入口，再决定计划任务的触发频率。

**Tech Stack:** Python 3, Swift, pytest, git, macOS launchd

---

### Task 1: 建立独立仓库骨架

**Files:**
- Create: `<home>/workspace/app/icloud-photo-sync/.gitignore`
- Create: `<home>/workspace/app/icloud-photo-sync/README.md`
- Create: `<home>/workspace/app/icloud-photo-sync/tools/icloud_photo_sync/`
- Create: `<home>/workspace/app/icloud-photo-sync/tests/`
- Create: `<home>/workspace/app/icloud-photo-sync/docs/`

- [ ] **Step 1: 创建目录结构**

Run: `mkdir -p <home>/workspace/app/icloud-photo-sync/{tools/icloud_photo_sync,tests,docs,scripts,state,tmp}`
Expected: 目录创建完成，无报错

- [ ] **Step 2: 初始化 git 仓库**

Run: `git -C <home>/workspace/app/icloud-photo-sync init`
Expected: 输出 `Initialized empty Git repository`

- [ ] **Step 3: 编写仓库基础说明**

在 `README.md` 中说明：
- 本仓库负责 `iCloud -> NAS` 的照片镜像同步
- 运行态数据不入仓
- 默认入口是 `python3 -m tools.icloud_photo_sync.cli`

- [ ] **Step 4: 编写忽略规则**

在 `.gitignore` 中忽略：
- `__pycache__/`
- `.pytest_cache/`
- `state/`
- `tmp/`

### Task 2: 迁移源码、测试、文档

**Files:**
- Copy: `<home>/workspace/Codex/tools/icloud_photo_sync/*`
- Copy: `<home>/workspace/Codex/tests/test_*.py`
- Copy: `<home>/workspace/Codex/docs/icloud-photo-authoritative-workflow.md`
- Copy: `<home>/workspace/Codex/docs/superpowers/specs/2026-04-09-icloud-photo-sync-design.md`
- Copy: `<home>/workspace/Codex/docs/superpowers/plans/2026-04-09-icloud-photo-sync.md`

- [ ] **Step 1: 复制工具源码**

Run: `rsync -a --exclude '__pycache__' <home>/workspace/Codex/tools/icloud_photo_sync/ <home>/workspace/app/icloud-photo-sync/tools/icloud_photo_sync/`
Expected: 新仓库内出现完整源码

- [ ] **Step 2: 复制相关测试**

Run: `rsync -a --include 'test_*.py' --exclude '*' <home>/workspace/Codex/tests/ <home>/workspace/app/icloud-photo-sync/tests/`
Expected: 新仓库内出现测试文件

- [ ] **Step 3: 复制工作流与设计文档**

Run: `mkdir -p <home>/workspace/app/icloud-photo-sync/docs/{specs,plans}`
Run: `cp ...`
Expected: 新仓库保留必要文档

### Task 3: 收口默认路径与仓库内说明

**Files:**
- Modify: `<home>/workspace/app/icloud-photo-sync/tools/icloud_photo_sync/cli.py`
- Modify: `<home>/workspace/app/icloud-photo-sync/docs/icloud-photo-authoritative-workflow.md`
- Modify: `<home>/workspace/app/icloud-photo-sync/README.md`

- [ ] **Step 1: 改为新仓库默认 state/tmp 路径**

把 `cli.py` 中原来的 `<home>/workspace/Codex/...` 改到 `<home>/workspace/app/icloud-photo-sync/...`

- [ ] **Step 2: 更新文档中的源码位置**

将工作流文档中的源码、设计、计划路径统一指向新仓库

- [ ] **Step 3: 补充 automation 入口说明**

在 `README.md` 中写明：
- 建议定时任务只自动跑 `plan`
- `apply` 继续人工触发
- 待删项进入 `<nas-mount>/Photos_DeletedFromICloud`

### Task 4: 验证独立仓库可运行

**Files:**
- Test: `<home>/workspace/app/icloud-photo-sync/tests/test_*.py`

- [ ] **Step 1: 运行测试**

Run: `python3 -m pytest <home>/workspace/app/icloud-photo-sync/tests -q`
Expected: 全部通过

- [ ] **Step 2: 运行一次 plan 级 smoke check**

Run: `python3 -m tools.icloud_photo_sync.cli plan --plan-id <new-id>`
Expected: 成功输出一个新的 `plan_dir`

- [ ] **Step 3: 确认日志与状态库仍在仓库外的正式位置**

检查：
- `<nas-mount>/Photos_SyncLogs`
- `<nas-mount>/Photos_DeletedFromICloud`
- `<home>/workspace/app/icloud-photo-sync/state/icloud-photo-sync/state.sqlite3`

### Task 5: 准备 automation 接入

**Files:**
- Create: `<home>/workspace/app/icloud-photo-sync/scripts/run_plan.sh`
- Create: `<home>/workspace/app/icloud-photo-sync/scripts/run_apply_latest.sh`
- Create: `<home>/workspace/app/icloud-photo-sync/docs/automation.md`

- [ ] **Step 1: 创建固定脚本入口**

`run_plan.sh` 负责进入新 repo 并调用 `python3 -m tools.icloud_photo_sync.cli plan`

- [ ] **Step 2: 创建 apply 辅助入口**

`run_apply_latest.sh` 负责读取明确指定的 `plan_dir` 或最近一次计划目录，再执行 `apply`

- [ ] **Step 3: 文档化定时策略**

在 `automation.md` 中写清：
- 推荐周期
- 只自动 `plan`
- `apply` 的人工确认方式
- 日志和待删池的查看路径
