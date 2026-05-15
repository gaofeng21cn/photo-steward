# iCloud ToDo 主源到 OneDrive 镜像对齐设计

日期: 2026-04-10

## 目标

把 `iCloud ToDo` 当前的主源结构严格同步到 `OneDrive ToDo`，并把 `OneDrive` 上独有但不在主源中的内容移动到单独审核池，而不是直接删除。

当前三处目录约定如下：

- 主源：`/Users/gaofeng/Documents/ToDo`
- 镜像：`/Users/gaofeng/Library/CloudStorage/OneDrive-个人/ToDo`
- 参考只读：`/Users/gaofeng/Library/CloudStorage/GoogleDrive-gaofeng21cn@gmail.com/我的云端硬盘/ToDo`

本轮只修改 `OneDrive`，`Google Drive` 只用于人工参考，不参与自动写入。

## 关键原则

- `iCloud/Documents/ToDo` 是唯一主判断
- `OneDrive/ToDo` 只做跟随镜像
- 所有 `OneDrive-only` 内容先进入审核池
- 比对必须严格基于完整路径集合和内容哈希，不凭命名猜测
- 路径比较使用 `NFC` 规范化，避免中日韩文件名的 Unicode 组合差异误判
- 所有动作都要落盘为 `plan` 和 `apply receipt`

## 同步模型

沿用照片同步里的两阶段工作流，但抽成通用目录能力：

1. `folder-plan`
   - 扫描主源目录和镜像目录
   - 生成文件清单、差异分类、执行计划
   - 不修改任何文件
2. `folder-apply`
   - 只消费一个已落盘的 `plan`
   - 先把 `target-only` 或冲突版本移动到审核池
   - 再把主源文件复制到镜像目录
   - 最后清理被挪空的旧目录，并输出回执

在 `ToDo` 场景上，再提供两个便捷入口：

- `todo-plan`
- `todo-apply`

它们只是给 `folder-plan` / `folder-apply` 注入默认路径，不引入新的同步逻辑。

## 扫描与比对

### 输入

- `source_root`
- `target_root`
- `review_root`
- `logs_root`

### 目录遍历

遍历时分别记录：

- 文件：相对路径、规范化相对路径、大小、`SHA-256`
- 目录：相对路径、规范化相对路径

当前只忽略显式平台噪音：

- `.DS_Store`

除此之外不再做任何启发式忽略。

### 差异分类

对于镜像侧的每一个文件，只允许四类结论：

1. `keep`
   - 规范化路径在主源存在，且内容哈希一致
2. `replace_conflict`
   - 规范化路径在主源存在，但内容哈希不同
   - 旧镜像版本先移入审核池，再复制主源版本
3. `target_only_duplicate_of_source`
   - 该路径不在主源，但其内容哈希在主源别处存在
   - 说明 `OneDrive` 里残留的是旧路径、旧归档或重复副本
4. `target_only_missing_in_source`
   - 该路径不在主源，且内容哈希在主源任何位置都不存在
   - 说明它是主源外残留内容，需要人工复核是否回灌

此外还要显式处理路径类型冲突：

- 主源是文件、镜像对应路径下却是一整棵目录
- 主源是目录、镜像对应路径却是单文件

这类冲突不做模糊覆盖，而是把镜像侧阻塞内容整体移入审核池，然后再落主源结构。

## 审核池与收据

### 审核池

`OneDrive-only` 和被主源替换掉的旧版本，统一移动到：

- `/Users/gaofeng/Library/CloudStorage/OneDrive-个人/ToDo_OneDriveOnlyReview/<plan_id>/...`

保留 `ToDo` 内相对路径，便于人工回看来源。

### 计划输出

每次 `folder-plan` / `todo-plan` 输出到：

- `<repo>/state/folder_sync_logs/YYYY-MM-DD/<plan_id>/`

至少包含：

- `plan_summary.json`
- `source_manifest.jsonl`
- `target_manifest.jsonl`
- `copy_to_target.json`
- `move_to_review.json`
- `unresolved.json`

### 执行回执

`folder-apply` / `todo-apply` 在同一目录追加：

- `apply_receipt.json`

回执必须区分：

- 移入审核池数量
- 从主源复制数量
- 清理空目录数量
- guard 失败数量

## 成功标准

- `OneDrive/ToDo` 的文件集合和 `iCloud/Documents/ToDo` 严格对齐
- `OneDrive-only` 内容全部进入审核池，而不是继续散落在根目录
- 回执能说明每个被移走的文件属于“旧路径重复”还是“主源外孤本”
- 后续可以把同一机制复用到其他 `iCloud -> 多云备份` 目录
