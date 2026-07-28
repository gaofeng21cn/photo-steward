# iCloud 主源的照片管理工作流

日期: 2026-04-09

## 1. 目标

建立一套稳定、可持续、可自动化的照片管理规则：

- `iCloud Photos` 是唯一主源
- `NAS` 是跟随主源变化的镜像库
- `OneDrive` 是异地备份，不承担日常整理入口

核心原则：

- 新增、整理、删除，原则上都先在 `iCloud Photos` 完成
- `NAS` 不再作为人工整理入口，只作为主源的文件级镜像
- `OneDrive` 不直接参与照片整理判断，只承接备份职责

## 2. 当前状态

截至 2026-04-09，已经完成：

- NAS 缺失于 iCloud 的补充导入已经完成
  - 正式相册: `ImportFromNAS_2026-04-08_v2`
  - 当前相册内媒体项数: `1873`
- `2000-01-01` 误日期的 4 张照片已修正为 `2025-09-20`
- 旧的 `NAS authoritative` 候删相册已降级为遗留相册
  - 当前相册: `DeleteCandidates_NASAuthoritative_2026-04-08_v2_LEGACY_UNSAFE`
  - 原因: 至少 `44` 条已证实属于“同名但不同内容”的双版本冲突，不能再作为删除依据
- `44` 组双版本冲突已经完成复核并按统一规则收口
  - Photos 相册: `ConflictReview_iCloudVsNAS_DualVersions_2026-04-08`
  - NAS 复核目录: `<nas-mount>/Photos_ConflictReview_iCloudVsNAS_2026-04-08`
  - 你的决策: `统一保留旧 iCloud 版`
  - 执行结果:
    - NAS 导入的滤镜版 `44` 份已移入 `<nas-mount>/Photos_DeletedFromICloud/2026-04-09/DualVersionConflict_NASImported`
    - 旧 iCloud 原件已补回 NAS 原路径
    - SHA 校验通过 `44/44`
- 另有 `89` 条已位于 Photos 的“最近删除”
- 半自动同步脚本已经正式落地
  - CLI: `python3 -m tools.icloud_photo_sync.cli`
  - 设计文档: `<home>/workspace/app/icloud-photo-sync/docs/specs/2026-04-09-icloud-photo-sync-design.md`
  - 实施计划: `<home>/workspace/app/icloud-photo-sync/docs/plans/2026-04-09-icloud-photo-sync.md`
- 已完成一次正式 `plan -> apply -> verify plan`
  - `plan4`: `<nas-mount>/Photos_SyncLogs/2026-04-09/icloud-sync-20260409T-plan4`
    - `mirror_count = 778`
    - `delete_count = 918`
    - `unresolved_count = 18`
  - `apply_receipt`: `<nas-mount>/Photos_SyncLogs/2026-04-09/icloud-sync-20260409T-plan4/apply_receipt.json`
    - `deleted.moved = 918`
    - `deleted.guard_failed = 0`
    - `mirrored.copied = 778`
    - `mirrored.guard_failed = 0`
  - `plan5` 回归对账: `<nas-mount>/Photos_SyncLogs/2026-04-09/icloud-sync-20260409T-plan5`
    - `mirror_count = 0`
    - `delete_count = 0`
    - `unresolved_count = 18`
  - `plan6`: `<nas-mount>/Photos_SyncLogs/2026-04-09/icloud-sync-20260409T-plan6`
    - `mirror_count = 19`
    - `delete_count = 6`
    - `unresolved_count = 0`
  - `plan7` 最终回归: `<nas-mount>/Photos_SyncLogs/2026-04-09/icloud-sync-20260409T-plan7`
    - `mirror_count = 0`
    - `delete_count = 0`
    - `unresolved_count = 0`

当前更准确的状态是：

- 在“原始媒体优先”的同步规则下，`iCloud Photos` 与 `NAS/Photos` 已经收敛
- 之前的 `18` 条 `unresolved` 已全部清零
  - `16` 条是 Live Photo 配对 `MOV`，原因是导出时未允许联网拉取 iCloud 原件
  - `2` 条是视频资源被错误选成 `FullSizeRender.jpeg`
- 上述问题已经在同步脚本中修复
- `918` 条 NAS-only 项并未硬删
  - 已移入 `<nas-mount>/Photos_DeletedFromICloud/2026-04-09/icloud-sync-20260409T-plan4`
  - 可继续人工复核或按保留期清理

当前已经可以宣布 “iCloud Photos 与 NAS 镜像收敛”，但仍需保留两类运营约束：

- 旧 `NAS authoritative` 遗留候删相册
  - 只保留作历史复核，不再作为正式删除清单
- iCloud 已在“最近删除”中的候删项
  - 仍然遵守 Photos 自身的保留周期

因此，现阶段更准确的说法是：

- `NAS -> iCloud` 的补充已经完成
- `44` 组双版本冲突已经按“保留旧 iCloud 版”完成 NAS 侧修复
- 正式半自动脚本已经完成多轮真实 `plan -> apply -> verify`
- `iCloud -> NAS` 的主闭环已经建立并完成回归收敛
- 后续工作重点转到独立仓库管理和定时 automation

## 3. 角色分工

### 3.1 iCloud Photos

定位：

- 唯一主源
- 日常浏览、整理、删片、日期修正、共享图库协作，都在这里完成

规则：

- 不再绕过 iCloud，直接向 NAS 主目录手工塞“正式照片”
- 共享图库也算主源的一部分

### 3.2 NAS

定位：

- 主源的文件级镜像
- 本地全量归档池
- 后续同步删除的执行目标

规则：

- 平时不在 `NAS/Photos` 主目录做人工删改
- 只通过同步任务接收：
  - iCloud 新增
  - iCloud 删除
  - iCloud 已确认的保留项回灌

### 3.3 OneDrive

定位：

- 异地备份
- 不参与“哪张保留、哪张删除”的主判断

建议：

- 不要让 OneDrive 直接跟 iCloud 做双向逻辑
- OneDrive 应从 NAS 的稳定结果再做备份

## 4. 推荐工作流

推荐采用：

- `iCloud 主源`
- `NAS 镜像`
- `OneDrive 异地备份`

这比“三端都随时可编辑”更严格，也更容易自动化。

### 4.1 日常新增

流程：

1. 新照片先进入 iCloud Photos
2. 同步任务扫描本机 Photos library 的当前资产集合
3. 将新增媒体文件复制到 NAS
4. 由 NAS 再向 OneDrive 做备份

### 4.2 日常删除

流程：

1. 你在 iCloud Photos 删除照片
2. 同步任务把“iCloud 现存资产集合”与 “NAS 当前集合”做严格比对
3. 对于 NAS 中存在、但 iCloud 中已不存在的内容：
   - 先移动到 NAS 的“待删池/回收池”
   - 记录删除清单
4. 经过保留期或人工确认后，再从 NAS 真删

这里必须强调：

- “直接硬删 NAS” 在工程上不稳妥
- 更严谨的做法是“主源删除 -> NAS 待删池 -> 到期清除”

这不是降级方案，而是可审计、可回滚、可自动化的正式删除机制。

### 4.3 OneDrive 的处理

推荐不要让 OneDrive 与 iCloud 做实时同步删除。

原因：

- 如果 NAS 和 OneDrive 都即时跟删，那么它们只是镜像，不再是真正备份
- 一旦误删，三端会一起收敛到错误状态

更合理的分工是：

- NAS 跟随 iCloud 做镜像删除
- OneDrive 保留更长周期的异地备份

也就是说：

- `NAS` 负责“当前正确状态”
- `OneDrive` 负责“历史可回退能力”

## 5. 文件级同步判定规则

同步逻辑必须以严格内容匹配为准，不用模糊启发式。

主判据：

- `sha256`

辅助判据：

- 文件大小
- Photos `stablehash`
- 原始文件名
- Live Photo 静态图 / `MOV` 组件关系

判定原则：

- 内容完全相同才算同一文件
- 同名但哈希不同，不算同一文件
- Live Photo 要把静态图和 `MOV` 分量分开判断
- 如果出现“同名但哈希不同，且两边都在当前库中存在”的情况
  - 一律进入 `unresolved conflict review`
  - 不自动删 iCloud
  - 不自动删 NAS

## 6. 删除同步的正式机制

建议在 NAS 侧建立以下结构：

- `<nas-mount>/Photos`
  - 主镜像库
- `<nas-mount>/Photos_DeletedFromICloud`
  - 来自主源删除的待删池
- `<nas-mount>/Photos_SyncLogs`
  - 每次同步的 manifest、动作清单、回执

每次删除同步输出至少三份记录：

- `present_in_icloud_manifest`
- `delete_from_nas_manifest`
- `execution_receipt`

删除动作规则：

- 如果文件在 NAS 存在、在 iCloud 当前清单中不存在
  - 移入 `Photos_DeletedFromICloud/YYYY-MM-DD/`
- 保留期建议：
  - `30` 天
- 到期再清空

## 7. 从现在切换到 iCloud 主源前，还要做的事

在正式宣布“以后以 iCloud 为主源”之前，建议先完成下面几项：

1. `44` 组双版本冲突已经完成
   - 最终决策: `统一保留旧 iCloud 版`
   - NAS 侧执行结果:
     - 滤镜版移入待删池
     - 旧 iCloud 原件补回原 NAS 路径
   - 当前不再把这 `44` 组当作待决项
2. 将旧 `DeleteCandidates_NASAuthoritative_2026-04-08_v2_LEGACY_UNSAFE` 视为废弃遗留物
   - 不再按该相册直接删图
3. 清掉已在“最近删除”的那 `89` 条候删项
4. 处理 `partial mismatch` 的 `220` 组
   - 决定哪些 Live Photo 的 `MOV` 要并入 NAS
5. 视需要复核 `cloud-only unresolved` 的 `150` 条
6. 观察 Photos 库内 `42` 条不可见残留记录是否随系统同步自清
   - 不直接改 SQLite
   - 只在可见层和可审计回执层继续推进工作流

只有这些收口后，`iCloud authoritative` 才算真正闭环。

## 8. 后续自动化建议

自动化建议分两层：

### 8.1 第一层：半自动

- 本机读取 Photos library
- 生成 iCloud 当前资产 manifest
- 扫描 NAS
- 输出：
  - `新增到 NAS`
  - `从 NAS 待删`
  - `未决项`

正式入口：

```bash
python3 -m tools.icloud_photo_sync.cli plan
python3 -m tools.icloud_photo_sync.cli apply --plan-dir <nas-mount>/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
```

当前脚本行为：

- 只同步“用户层面的主照片/主视频资源”
- 默认采用“原始媒体优先”
- `apply` 不会硬删 NAS-only 文件
- 所有待删项先进入 `Photos_DeletedFromICloud/YYYY-MM-DD/<plan_id>/`

### 8.2 第二层：全自动

- 每日或每周定时执行
- 自动把：
  - iCloud 新增复制到 NAS
  - iCloud 删除移动到 NAS 待删池
- 自动生成日志
- 到期自动清空待删池

OneDrive 则只做：

- 从 NAS 结果目录做备份
- 不直接参与主判定

## 9. 最终建议

照片这条线，建议正式定为：

- `iCloud Photos = 唯一主源`
- `NAS = 可审计的镜像库`
- `OneDrive = 异地备份`

并坚持下面这条纪律：

- 以后不再在三端分别整理
- 所有“保留/删除”的决定都先在 iCloud 发生
- NAS 只负责跟随
- OneDrive 只负责兜历史

这套逻辑与其他文件的管理原则是一致的，但照片比普通文件多了两点约束：

- Photos 是数据库型资产库，不只是文件夹
- Live Photo、共享图库、云端未下载资产，需要单独处理

所以真正落地时，必须依赖 manifest 和日志，而不能靠肉眼同步。
