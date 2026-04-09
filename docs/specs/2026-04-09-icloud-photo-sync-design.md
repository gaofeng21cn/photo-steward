# iCloud 主源到 NAS 跟随同步设计

日期: 2026-04-09

## 目标

把现有一次性临时脚本收束成一套可持续运行的半自动同步工具，满足下面三条硬约束：

- `iCloud Photos` 是唯一主源
- `NAS` 只做跟随镜像，不再承担主判断
- 删除不直接硬删，先进入 `Photos_DeletedFromICloud` 待删池

这套工具必须拆成两个阶段：

- `plan`
  - 只扫描、比对、产出清单
- `apply`
  - 只消费一个已落盘的 `plan`
  - 对 NAS 执行复制和移入待删池

## 关键原则

- 严格以“资源文件实例”而不是仅以“文件名”或“年份目录”作为匹配单位
- 匹配必须以内容哈希为核心依据
- 相同内容的重复实例按“实例数量”处理，不按集合去重
- 所有动作都要有可审计清单和执行回执
- 不修改 Photos.sqlite，不把不可见数据库残留当作正式输入

## 数据源

### iCloud / Photos 侧

分两层读取：

1. `Photos.sqlite`
   - 枚举资产 UUID、创建时间、原始文件名、主 originals 路径、共享状态
   - 用于快速读取本地已存在的主 originals 文件
2. `Photos.framework` Swift helper
   - 枚举每个 asset 的全部 `PHAssetResource`
   - 用于覆盖 Live Photo 配对视频、缺失本地 originals 的资源、共享图库资源
   - 对需要落地校验的资源，按需导出到临时目录计算哈希

### NAS 侧

- 扫描 `/Volumes/home/Photos`
- 按相对路径、大小、mtime/ctime 建立缓存命中条件
- 只对变更文件重新计算 `SHA-256`

## 缓存与状态

本地状态库：

- `<repo>/state/icloud-photo-sync/state.sqlite3`

核心表：

- `resource_cache`
  - 记录 iCloud 资源和 NAS 文件的状态 token、字节数、`SHA-256`
- `path_bindings`
  - 把 iCloud 资源实例稳定绑定到 NAS 相对路径
- `plan_runs`
  - 记录每次计划生成的统计和目录
- `apply_runs`
  - 记录每次执行的统计和目录

缓存复用规则：

- iCloud 资源：
  - 用资源元数据摘要作为 `state_token`
  - token 未变则复用既有 `SHA-256`
  - token 改变才重新导出并计算哈希
- NAS 文件：
  - 用 `relative_path + size + mtime_ns + ctime_ns` 作为 `state_token`
  - token 未变则复用既有 `SHA-256`

## 规划逻辑

输入单位统一为“资源实例”：

- 一个普通照片通常对应 1 个资源实例
- 一个 Live Photo 可能对应 2 个资源实例
- 两个内容完全相同但在 iCloud 中确实存在的副本，视为 2 个实例

规划分 4 步：

1. 保留现有有效绑定
   - 若某个 iCloud 资源已绑定 NAS 路径，且该路径仍存在同哈希文件，则直接保留
2. 复用未绑定但内容相同的 NAS 文件
   - 对剩余 iCloud 资源，从未匹配的 NAS 文件里找相同哈希文件
   - 命中则收编该路径，不重复复制
3. 为仍未匹配的 iCloud 资源分配新目标路径
   - 目录规则：`YYYY/MM/filename`
   - 同目录同名冲突时，使用稳定的 `__dupN` 分配
4. 剩余未匹配 NAS 文件进入 `move_to_nas_deleted_pool`

## 输出

每次 `plan` 固定输出到：

- `/Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>/`

目录内至少包含：

- `plan_summary.json`
- `present_in_icloud_manifest.jsonl`
- `present_in_nas_manifest.jsonl`
- `mirror_to_nas.json`
- `move_to_nas_deleted_pool.json`
- `unresolved.json`

每次 `apply` 在同一目录追加：

- `apply_receipt.json`

## apply 执行约束

- 只接受一个明确的 `plan_id`
- 对每条动作再次做 guard 校验
- guard 失败则跳过并记入回执，不猜测继续执行

删除动作：

- 从 `/Volumes/home/Photos` 移入
  `/Volumes/home/Photos_DeletedFromICloud/YYYY-MM-DD/<plan_id>/...`
- 保留原相对路径，便于回溯

镜像动作：

- 若源为本地 originals，直接复制并校验哈希
- 若源为 Photos 资源导出，重新导出到临时目录并校验哈希后复制
- 若目标路径已存在不同内容且未列入本次待删动作，则拒绝覆盖并记为 guard 失败

## 未决项

进入 `unresolved` 的情况：

- Photos 资源无法导出
- 同步过程中命中无法稳定解释的资源状态
- 目标路径存在不可安全覆盖的冲突

## 成功标准

- 能稳定重复执行 `plan`
- 对未变化数据显著减少重复哈希/重复导出
- `apply` 只在 guard 全部通过的动作上生效
- 能产出可审计的镜像、待删池、未决项三类结果
