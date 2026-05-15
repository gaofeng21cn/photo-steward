# iCloud ToDo To OneDrive Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `iCloud/Documents/ToDo -> OneDrive/ToDo` 实现严格的 plan/apply 对齐能力，并将 `OneDrive-only` 内容移动到审核池。

**Architecture:** 在现有 `icloud-photo-sync` 仓库里新增一套通用目录同步引擎，负责规范化路径、哈希比对、计划落盘和安全 apply；再提供 `todo-plan` / `todo-apply` 作为默认路径封装。执行时先移动镜像侧多余或冲突内容，再复制主源文件，最后清理空目录。

**Tech Stack:** Python 3.12、pytest、hashlib、pathlib、json

---

### Task 1: 定义 ToDo 目录同步的规格与 CLI 入口

**Files:**
- Modify: `/Users/gaofeng/workspace/app/icloud-photo-sync/tests/test_cli_smoke.py`
- Create: `/Users/gaofeng/workspace/app/icloud-photo-sync/tests/test_folder_sync.py`

- [ ] Step 1: 写 CLI 子命令和目录计划输出的失败测试
- [ ] Step 2: 运行测试确认 `folder-plan` / `folder-apply` / `todo-plan` / `todo-apply` 尚不存在
- [ ] Step 3: 明确计划目录、审核池、差异分类和 receipt 结构
- [ ] Step 4: 保持测试仍处于真实失败状态，进入实现

### Task 2: 实现通用目录 plan 核心

**Files:**
- Create: `/Users/gaofeng/workspace/app/icloud-photo-sync/tools/icloud_photo_sync/folder_sync.py`
- Modify: `/Users/gaofeng/workspace/app/icloud-photo-sync/tests/test_folder_sync.py`

- [ ] Step 1: 写“规范化路径相等不误判”“target-only 重复副本分类”“同路径内容冲突替换”失败测试
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 实现目录遍历、`SHA-256` 计算、差异分类和 `plan_summary`/JSON 落盘
- [ ] Step 4: 运行针对性测试确认通过

### Task 3: 实现通用目录 apply 执行器

**Files:**
- Modify: `/Users/gaofeng/workspace/app/icloud-photo-sync/tools/icloud_photo_sync/folder_sync.py`
- Modify: `/Users/gaofeng/workspace/app/icloud-photo-sync/tests/test_folder_sync.py`

- [ ] Step 1: 写“先移入审核池、再复制主源、再清理空目录”的失败测试
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 实现 `apply_folder_plan` 和 `apply_receipt`
- [ ] Step 4: 运行针对性测试确认通过

### Task 4: 串起 CLI 与 ToDo 默认路径

**Files:**
- Modify: `/Users/gaofeng/workspace/app/icloud-photo-sync/tools/icloud_photo_sync/cli.py`
- Modify: `/Users/gaofeng/workspace/app/icloud-photo-sync/tests/test_cli_smoke.py`

- [ ] Step 1: 写 `folder-*` 与 `todo-*` 参数解析失败测试
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 在 CLI 中接入通用目录同步引擎和 ToDo 默认路径
- [ ] Step 4: 运行 CLI smoke test 确认通过

### Task 5: 更新文档并在真实 ToDo 路径执行

**Files:**
- Modify: `/Users/gaofeng/workspace/app/icloud-photo-sync/README.md`
- Modify: `/Users/gaofeng/workspace/app/icloud-photo-sync/README.zh-CN.md`
- Modify: `/Users/gaofeng/workspace/app/icloud-photo-sync/docs/automation.md`

- [ ] Step 1: 更新 `ToDo` 主源对齐命令和审核池路径说明
- [ ] Step 2: 运行 `pytest` 相关测试
- [ ] Step 3: 对真实 `ToDo` 路径执行一次 `todo-plan`
- [ ] Step 4: 核对 `plan_summary.json` 后执行 `todo-apply`
- [ ] Step 5: 记录最终计划目录、回执目录和实际移动/复制统计
