# icloud-photo-sync

`iCloud Photos -> NAS` 的半自动镜像同步工具。

## 定位

- `iCloud Photos` 是唯一主源
- `NAS` 是跟随主源变化的镜像库
- `OneDrive` 是异地备份，不参与主判断

## 仓库边界

这个仓库只管理源码、测试、文档和 automation 入口。

运行态数据不入仓：

- 状态库: `state/icloud-photo-sync/state.sqlite3`
- 临时导出目录: `tmp/icloud_photo_sync_stage`
- 同步日志: `/Volumes/home/Photos_SyncLogs`
- NAS 待删池: `/Volumes/home/Photos_DeletedFromICloud`

`state/` 和 `tmp/` 已加入 `.gitignore`。

## 运行

在仓库根目录执行：

```bash
python3 -m tools.icloud_photo_sync.cli plan
python3 -m tools.icloud_photo_sync.cli apply --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
```

也可以使用脚本入口：

```bash
./scripts/run_plan.sh
./scripts/run_apply_latest.sh --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
```

## 自动化

当前推荐的自动化策略：

- 定时只自动执行 `plan`
- `apply` 继续手动触发
- NAS 删除统一进入 `/Volumes/home/Photos_DeletedFromICloud`

具体安装和计划任务说明见 `docs/automation.md`。

