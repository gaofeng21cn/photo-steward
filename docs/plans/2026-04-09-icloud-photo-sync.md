# iCloud Photo Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一套两阶段的 `iCloud Photos -> NAS` 半自动同步工具，输出严格审计清单，并支持把 NAS 多余内容移动到待删池。

**Architecture:** 采用 Python 负责状态库、规划、执行与日志，采用 Swift helper 负责访问 `Photos.framework` 枚举资源和按需导出资源。规划与执行彻底分离，规划只落盘，执行只消费指定 plan。

**Tech Stack:** Python 3.12、sqlite3、pytest、Swift 6、Photos.framework

---

### Task 1: 建立正式目录和 CLI 骨架

**Files:**
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/__init__.py`
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/cli.py`
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/models.py`
- Create: `<home>/workspace/Codex/tests/test_cli_smoke.py`

- [ ] Step 1: 写 CLI smoke test
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 写最小 CLI 骨架
- [ ] Step 4: 运行测试确认通过

### Task 2: 实现状态库与缓存模型

**Files:**
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/state.py`
- Create: `<home>/workspace/Codex/tests/test_state_store.py`

- [ ] Step 1: 写缓存复用和 run 记录测试
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 实现 sqlite 状态库
- [ ] Step 4: 运行测试确认通过

### Task 3: 实现纯规划核心

**Files:**
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/planner.py`
- Create: `<home>/workspace/Codex/tests/test_planner.py`

- [ ] Step 1: 写“复用已匹配 NAS 文件 / 生成 mirror / 生成 delete”测试
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 实现匹配与路径绑定算法
- [ ] Step 4: 运行测试确认通过

### Task 4: 实现 NAS apply 执行器

**Files:**
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/apply.py`
- Create: `<home>/workspace/Codex/tests/test_apply.py`

- [ ] Step 1: 写“复制到 NAS / 移入待删池 / guard 失败跳过”测试
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 实现执行器
- [ ] Step 4: 运行测试确认通过

### Task 5: 实现 Photos 适配层

**Files:**
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/photos_db.py`
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/photos_bridge.py`
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/photos_bridge.swift`
- Create: `<home>/workspace/Codex/tests/test_photos_db.py`

- [ ] Step 1: 写 Photos DB 枚举与元数据合并测试
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 实现 Python/Swift 适配层
- [ ] Step 4: 运行测试确认通过

### Task 6: 串起真实 `plan` 命令

**Files:**
- Create: `<home>/workspace/Codex/tools/icloud_photo_sync/runtime.py`
- Modify: `<home>/workspace/Codex/tools/icloud_photo_sync/cli.py`
- Create: `<home>/workspace/Codex/tests/test_runtime_plan.py`

- [ ] Step 1: 写 `plan` 产出目录与文件测试
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 实现真实规划流程与 JSON/JSONL 落盘
- [ ] Step 4: 运行测试确认通过

### Task 7: 串起真实 `apply` 命令

**Files:**
- Modify: `<home>/workspace/Codex/tools/icloud_photo_sync/cli.py`
- Modify: `<home>/workspace/Codex/tools/icloud_photo_sync/runtime.py`
- Create: `<home>/workspace/Codex/tests/test_runtime_apply.py`

- [ ] Step 1: 写 `apply` 读取 plan 并输出回执测试
- [ ] Step 2: 运行测试确认失败
- [ ] Step 3: 实现真实 apply 流程
- [ ] Step 4: 运行测试确认通过

### Task 8: 验证与文档收口

**Files:**
- Modify: `<home>/workspace/Codex/docs/icloud-photo-authoritative-workflow.md`

- [ ] Step 1: 运行完整测试套件
- [ ] Step 2: 运行一次本地 dry-run 级别的 `plan` 命令验证
- [ ] Step 3: 更新工作流文档中的命令入口和输出路径
- [ ] Step 4: 记录验证结果和已知边界
