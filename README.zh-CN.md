<p align="center"><a href="./README.md">English</a> | <strong>中文</strong></p>

<h1 align="center">Photo Steward</h1>

<p align="center"><strong>面向 macOS 的受控照片镜像与备份协调器</strong></p>
<p align="center">iCloud Photos 作为唯一权威来源 · 先审计划再变更 · 数据始终留在本机和 NAS</p>

> **当前为 Alpha。** Photo Steward 已经可以作为技术用户自行部署的本地服务使用，但还不是可直接面向公众分发的软件。仓库尚未确定公开许可证、可公开访问的源码仓库、经过公证的安装包和最终商标可用性。

Photo Steward 用来协调本机 macOS Photos 图库、iCloud Photos 与 NAS 镜像。它先生成可审计的计划，解释差异，再在用户明确确认后变更镜像端。它不是云端相册、反向同步工具，也不是通用的照片资产管理系统。

`photo-steward` 是主 CLI 与 Codex Skill 标识。为避免破坏已有自动化，仍保留 CLI `icloud-photo-sync` 和 Codex Skill `icloud-photo-center` 作为兼容别名。

## 面向用户

### 它解决什么问题

- **iCloud Photos 始终是唯一权威来源。** NAS 和异地备份只是镜像或备份，不会反过来判定图库里什么才是最新版本。
- **任何变更先有计划。** 定时任务可以发现差异，但不能自行执行照片镜像或删除动作。
- **只存在于镜像端的文件进入待删池。** 系统将它们移入带日期、可复核的隔离位置，而不是直接永久删除。
- **必须有成功回执。** 只有精确计划通过安全校验并完成目标端回读后，状态才会更新为成功。

### 日常怎么用

1. 从菜单栏打开 **Photo Steward**，或在 Codex 中要求检查照片中心。
2. 刷新状态；需要时生成一份新的同步计划。
3. 查看数量、数据量、未解决项目，以及准备移入待删池的文件。
4. 只有当计划完全符合预期时，才确认执行这一个精确计划。
5. 执行后读取回执和状态总览。

菜单栏 App 是控制台，不是第二套同步逻辑。它、Codex Skill 和 `launchd` 调用的都是同一个确定性 CLI。

### 隐私与数据

仓库只包含源代码、测试、公共示例和文档。以下内容只应保留在用户自己的 Mac 或 NAS，绝不能提交到 Git：

- 真实 Photos 图库、导出的照片、清单、SHA-256 索引、计划、执行回执、SQLite 状态库和日志；
- NAS 主机名、挂载路径、账号名称和本机绝对路径；
- 云端令牌、密码、签名证书和开发者凭据。

私有配置文件默认位于：

```text
~/Library/Application Support/Photo Steward/config.toml
```

该文件会以 `0600` 权限创建。密码和令牌应交给 macOS Keychain、NAS 挂载机制或备份工具自己的凭据存储，而不是写进配置文件。可提交的脱敏示例见 [`config/photo-steward.example.toml`](./config/photo-steward.example.toml)。

### 快速开始

当前安装方式会把当前仓库软链接到本机，因此它适合技术用户评估 Alpha，不是面向普通用户的正式分发方式。

```bash
./scripts/install_local.sh
photo-steward config path
# 编辑上一步输出的私有配置文件。
photo-steward config validate
photo-steward preflight
photo-steward status --scope photo --format json
```

配置通过校验后，可安装可选的 macOS 控制台：

```bash
./scripts/install_menu_bar_app.sh
open "$HOME/Applications/Photo Steward.app"
```

字段解释、配置优先级和迁移说明见 [`docs/configuration.md`](./docs/configuration.md)。

## 它如何工作

```text
iCloud Photos / 本机 Photos 图库
              |
              v
       确定性清单与 SHA-256 匹配
              |
              v
          生成受控计划
              |
              +--> 在 Codex 或 macOS 控制台中审阅
              |
              v
       明确确认后执行，并回读目标端
              |
              v
      NAS 镜像、待删池与执行回执
```

只要存在未解决项目，`apply` 就会被阻止。日期修正会被视为一次重定位：系统先在新日期目录生成镜像项，再在同一份受控计划中把旧位置移入待删池。直接复制文件或凭肉眼判断重复，不能替代这个流程。

## 面向 Agent

Codex Skill 是对话入口；确定性的 CLI 才拥有配置解析、计划、安全校验、执行和回执。不要在提示词、Skill 脚本或 GUI 中另写一套同步逻辑。

```bash
photo-steward config validate
photo-steward preflight
photo-steward status --scope photo --format json
photo-steward plan-job
```

执行计划前，Agent 必须读取 `plan_summary.json` 与相关清单，解释 `mirror_count`、`delete_count`、`unresolved_count`、总数据量和待删池影响，并取得用户对精确计划目录的明确同意。随后只能执行：

```bash
photo-steward apply-job --plan-dir <精确计划目录>
```

只有读取执行回执和最新 JSON 状态后，才能宣称任务完成。

配置优先级依次为：操作命令中的显式参数、全局 `--config`、`PHOTO_STEWARD_CONFIG`、兼容变量 `ICLOUD_PHOTO_SYNC_CONFIG`、私有活动配置指针、默认私有路径。`config activate` 会更新该私有指针，使 macOS App 与 LaunchAgent 始终使用同一份配置。全局参数必须写在子命令之前：

```bash
photo-steward --config /绝对路径/config.toml preflight
```

macOS App 读取默认私有路径。`launchd` 会把选择的配置路径明确写入每个 plist，不依赖终端会话环境。

### 自动化

只有在 `config validate` 与 `preflight` 都通过后，才安装自动化：

```bash
./scripts/install_launchd_agents.sh
```

默认任务会生成照片计划、执行待删池保留期处理，并可运行异地备份；它**不会**自动执行照片计划。日志位于 `~/Library/Logs/Photo Steward/`。生成的 LaunchAgent 只保存配置文件路径，不保存任何凭据。通用目录同步和 ToDo 同步属于高级扩展，不在照片中心的公共快速开始路径中。

## 架构

- **CLI：** 可测试、可脚本化的命令契约，也是同步语义的唯一所有者。
- **Codex Skill：** 负责检查状态、解释计划和组织审批。
- **macOS 控制台：** 显示健康状态、进度、待审计划并获取确认。

`launchd` 调用 wrapper，再调用同一个 CLI，不会经过 App。详细边界见 [`docs/architecture.md`](./docs/architecture.md)。

## 发布准备度

在对方能够自行填写私有配置、理解当前是开发安装的前提下，这个 Alpha 可以提供给可信赖的技术用户评估。真正公开发布仍需要完成：

- 明确许可证，并决定如何处理既有 Git 提交作者历史；
- 建立可公开访问的源码仓库，并从全新克隆生成不含个人运行态的发行物；
- 用版本化安装器替换依赖仓库路径的软链接；
- 提供经过公证、支持通用架构的 macOS App 与终端用户权限指引；
- 完成产品名称和商标可用性核查；
- 在外部用户机器上完成从安装到恢复的完整验证。

因此，项目目前不应被表述为“已开源”或“已向公众正式可用”。文档中出现 iCloud 和 Photos 只是为了说明支持的 Apple 平台能力；Photo Steward 是独立软件，与 Apple 无隶属关系。

## 验证

```bash
python3 -m pytest tests -q
swift build --package-path app/PhotoCenterMenuBar -c release
zsh tests/test_menu_bar_app.sh
zsh tests/test_launchd_job.sh
zsh tests/test_install_local.sh
zsh tests/test_automation_common.sh
```
