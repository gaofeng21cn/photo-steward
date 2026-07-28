import AppKit
import Foundation
import Photos
import SwiftUI

enum PhotoStewardSetupState: Equatable {
    case preparing
    case needsSetup(String)
    case ready
    case working(String)
    case failed(String)
}

struct PhotoStewardRuntimeInstaller {
    private let fileManager = FileManager.default

    func install() throws -> URL {
        guard let bundledRuntime = Bundle.main.url(forResource: "PhotoStewardRuntime", withExtension: nil) else {
            throw RuntimeInstallerError.missingBundleRuntime
        }

        let version = (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? "development"
        let runtimeBase = fileManager.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Photo Steward/runtime", isDirectory: true)
        let destination = runtimeBase.appendingPathComponent(version, isDirectory: true)
        try fileManager.createDirectory(at: runtimeBase, withIntermediateDirectories: true)

        let marker = destination.appendingPathComponent(".installed")
        let bundledManifest = bundledRuntime.appendingPathComponent(".runtime-manifest")
        let installedManifest = destination.appendingPathComponent(".runtime-manifest")
        let bundleDigest = try String(contentsOf: bundledManifest, encoding: .utf8)
        let installedDigest = try? String(contentsOf: installedManifest, encoding: .utf8)
        if installedDigest != bundleDigest || !fileManager.fileExists(atPath: marker.path) {
            if fileManager.fileExists(atPath: destination.path) {
                try fileManager.removeItem(at: destination)
            }
            try fileManager.copyItem(at: bundledRuntime, to: destination)
            try Data("Photo Steward \(version)\n".utf8).write(to: marker, options: .atomic)
        }

        let current = runtimeBase.appendingPathComponent("current", isDirectory: true)
        if fileManager.fileExists(atPath: current.path)
            || (try? fileManager.destinationOfSymbolicLink(atPath: current.path)) != nil {
            try fileManager.removeItem(at: current)
        }
        try fileManager.createSymbolicLink(at: current, withDestinationURL: destination)

        try installCommandWrappers()
        try installSkills(runtimeRoot: destination)
        return current
    }

    private func installCommandWrappers() throws {
        let binDirectory = fileManager.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin", isDirectory: true)
        try fileManager.createDirectory(at: binDirectory, withIntermediateDirectories: true)
        let wrapper = """
        #!/bin/zsh
        set -euo pipefail
        RUNTIME_ROOT="$HOME/Library/Application Support/Photo Steward/runtime/current"
        exec "$RUNTIME_ROOT/scripts/icloud-photo-sync" "$@"
        """
        for name in ["photo-steward", "icloud-photo-sync"] {
            try writeExecutable(Data(wrapper.utf8), to: binDirectory.appendingPathComponent(name))
        }
    }

    private func installSkills(runtimeRoot: URL) throws {
        let codexRoot = ProcessInfo.processInfo.environment["CODEX_HOME"]
            .map(URL.init(fileURLWithPath:))
            ?? fileManager.homeDirectoryForCurrentUser.appendingPathComponent(".codex", isDirectory: true)
        let skillsDirectory = codexRoot.appendingPathComponent("skills", isDirectory: true)
        try fileManager.createDirectory(at: skillsDirectory, withIntermediateDirectories: true)

        for name in ["photo-steward", "icloud-photo-center"] {
            let source = runtimeRoot.appendingPathComponent("skills/\(name)", isDirectory: true)
            let destination = skillsDirectory.appendingPathComponent(name, isDirectory: true)
            try removeIfPresent(destination)
            try fileManager.copyItem(at: source, to: destination)
        }
    }

    private func writeExecutable(_ data: Data, to url: URL) throws {
        try removeIfPresent(url)
        try data.write(to: url, options: .atomic)
        try fileManager.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
    }

    private func removeIfPresent(_ url: URL) throws {
        if fileManager.fileExists(atPath: url.path)
            || (try? fileManager.destinationOfSymbolicLink(atPath: url.path)) != nil {
            try fileManager.removeItem(at: url)
        }
    }
}

enum RuntimeInstallerError: LocalizedError {
    case missingBundleRuntime
    case commandFailed(String)

    var errorDescription: String? {
        switch self {
        case .missingBundleRuntime:
            return "当前 App 不包含内置运行时。请从 Photo Steward 正式发布包安装，而不是直接运行源码构建。"
        case let .commandFailed(message):
            return message
        }
    }
}

@MainActor
final class PhotoStewardRuntimeController: ObservableObject {
    @Published private(set) var state: PhotoStewardSetupState = .preparing
    @Published private(set) var runtimeRoot: URL?

    private let installer = PhotoStewardRuntimeInstaller()

    var isReady: Bool {
        state == .ready
    }

    var stateMessage: String {
        switch state {
        case .preparing:
            return "正在准备 Photo Steward 运行环境..."
        case let .needsSetup(message), let .failed(message), let .working(message):
            return message
        case .ready:
            return "运行环境已准备好"
        }
    }

    init() {
        prepare()
    }

    func prepare() {
        state = .preparing
        do {
            let root = try installer.install()
            runtimeRoot = root
            let configPath = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/Photo Steward/config.toml")
            if FileManager.default.fileExists(atPath: configPath.path) {
                let result = try run(
                    executable: root.appendingPathComponent("scripts/icloud-photo-sync"),
                    arguments: ["config", "validate"]
                )
                if result.exitCode == 0 {
                    let configSummary = try JSONDecoder().decode(
                        RuntimeConfigSummary.self,
                        from: Data(result.output.utf8)
                    )
                    if !agentsUseRuntime(root, configSummary: configSummary) {
                        let agentsResult = try run(
                            executable: root.appendingPathComponent("scripts/install_launchd_agents.sh"),
                            arguments: agentInstallArguments(for: configSummary)
                        )
                        try Self.requireSuccess(agentsResult, action: "更新后台同步任务")
                    }
                    state = .ready
                } else {
                    state = .needsSetup("已有配置，但校验未通过。请重新选择照片图库和 NAS 照片目录。")
                }
            } else {
                state = .needsSetup("首次使用需要选择本机 Photos 图库和 NAS 照片目录。")
            }
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    func completeSetup(photosLibrary: URL, nasPhotos: URL, installAgents: Bool) {
        guard let runtimeRoot else {
            state = .failed("内置运行环境尚未准备好。")
            return
        }

        state = .working("正在请求照片访问权限...")
        PHPhotoLibrary.requestAuthorization(for: .readWrite) { [weak self] status in
            DispatchQueue.main.async {
                guard status == .authorized || status == .limited else {
                    self?.state = .failed("没有获得 Photos 读取权限。请在“系统设置 > 隐私与安全性 > 照片”中允许 Photo Steward 访问。")
                    return
                }
                self?.runSetup(
                    runtimeRoot: runtimeRoot,
                    photosLibrary: photosLibrary,
                    nasPhotos: nasPhotos,
                    installAgents: installAgents
                )
            }
        }
    }

    private func runSetup(
        runtimeRoot: URL,
        photosLibrary: URL,
        nasPhotos: URL,
        installAgents: Bool
    ) {
        state = .working("正在检查 NAS 并写入私有配置...")
        Task.detached {
            do {
                let cli = runtimeRoot.appendingPathComponent("scripts/icloud-photo-sync")
                try Self.requireSuccess(
                    try Self.runProcess(
                        executable: cli,
                        arguments: [
                            "config",
                            "setup",
                            "--photos-library",
                            photosLibrary.path,
                            "--nas-photos",
                            nasPhotos.path,
                        ]
                    ),
                    action: "写入私有配置"
                )
                try Self.requireSuccess(
                    try Self.runProcess(executable: cli, arguments: ["config", "validate"]),
                    action: "校验私有配置"
                )
                try Self.requireSuccess(
                    try Self.runProcess(executable: cli, arguments: ["preflight"]),
                    action: "执行 NAS 预检"
                )
                if installAgents {
                    let agents = runtimeRoot.appendingPathComponent("scripts/install_launchd_agents.sh")
                    try Self.requireSuccess(
                        try Self.runProcess(executable: agents, arguments: ["--photo-only"]),
                        action: "安装后台同步任务"
                    )
                }
                await MainActor.run {
                    self.state = .ready
                }
            } catch {
                await MainActor.run {
                    self.state = .failed(error.localizedDescription)
                }
            }
        }
    }

    private func run(executable: URL, arguments: [String]) throws -> ProcessResult {
        try Self.runProcess(executable: executable, arguments: arguments)
    }

    private func agentInstallArguments(for configSummary: RuntimeConfigSummary) -> [String] {
        var arguments: [String] = []
        if !configSummary.backupConfigured {
            arguments.append("--photo-only")
        }
        if configSummary.todoExtensionConfigured {
            arguments.append("--include-todo")
        }
        return arguments
    }

    private func agentsUseRuntime(_ runtimeRoot: URL, configSummary: RuntimeConfigSummary) -> Bool {
        let launchAgents = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents", isDirectory: true)
        let contracts: [(String, String, Bool)] = [
            ("com.photosteward.plan.daily", "run_plan.sh", true),
            ("com.photosteward.deleted-pool.daily", "run_deleted_pool_retention.sh", true),
            ("com.photosteward.onedrive.daily", "run_onedrive_backup.sh", configSummary.backupConfigured),
            ("com.photosteward.todo.daily", "run_todo_plan.sh", configSummary.todoExtensionConfigured),
        ]
        for (label, scriptName, enabled) in contracts {
            let plist = launchAgents.appendingPathComponent("\(label).plist")
            if !enabled {
                if FileManager.default.fileExists(atPath: plist.path) {
                    return false
                }
                continue
            }
            let executable = runtimeRoot.appendingPathComponent("scripts/\(scriptName)").path
            guard let data = try? Data(contentsOf: plist),
                  let payload = try? PropertyListSerialization.propertyList(from: data, format: nil),
                  let dictionary = payload as? [String: Any],
                  let arguments = dictionary["ProgramArguments"] as? [String],
                  arguments.first == executable
            else {
                return false
            }
        }
        return true
    }

    nonisolated private static func requireSuccess(_ result: ProcessResult, action: String) throws {
        guard result.exitCode == 0 else {
            let detail = result.output.split(separator: "\n").last.map(String.init) ?? "未知错误"
            throw RuntimeInstallerError.commandFailed("\(action)失败：\(detail)")
        }
    }

    nonisolated private static func runProcess(executable: URL, arguments: [String]) throws -> ProcessResult {
        let task = Process()
        task.executableURL = executable
        task.arguments = arguments
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = pipe
        var environment = ProcessInfo.processInfo.environment
        let runtimeRoot = executable.deletingLastPathComponent().deletingLastPathComponent()
        environment["PHOTO_STEWARD_RUNTIME_ROOT"] = runtimeRoot.path
        task.environment = environment
        try task.run()
        task.waitUntilExit()
        let output = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
        let exitCode = task.terminationReason == .exit ? task.terminationStatus : -1
        return ProcessResult(exitCode: exitCode, output: output)
    }
}

private struct ProcessResult: Sendable {
    let exitCode: Int32
    let output: String
}

private struct RuntimeConfigSummary: Decodable {
    let backupConfigured: Bool
    let todoExtensionConfigured: Bool

    enum CodingKeys: String, CodingKey {
        case backupConfigured = "backup_configured"
        case todoExtensionConfigured = "todo_extension_configured"
    }
}
