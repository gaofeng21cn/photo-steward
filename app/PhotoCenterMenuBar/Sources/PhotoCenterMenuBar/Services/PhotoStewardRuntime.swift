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

        let process = Process()
        process.executableURL = bundledRuntime.appendingPathComponent("bin/python3")
        process.arguments = [
            bundledRuntime.appendingPathComponent("scripts/manage_installation.py").path,
            "prepare", "--app-path", Bundle.main.bundleURL.path, "--json",
        ]
        process.currentDirectoryURL = bundledRuntime
        let output = Pipe()
        let errorOutput = Pipe()
        process.standardOutput = output
        process.standardError = errorOutput
        try process.run()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let detail = String(data: data, encoding: .utf8) ?? "无法选择 Photo Steward 运行环境"
            throw RuntimeInstallerError.commandFailed(detail)
        }
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard result?["active_installation_status"] as? String == "active" else {
            throw RuntimeInstallerError.commandFailed("请在 OPL 软件中心选择一个激活的 Photo Steward 安装。")
        }
        return fileManager.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Photo Steward/runtime/current", isDirectory: true)
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
    @Published private(set) var configSummary: RuntimeConfigSummary?

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
            try Self.requireSuccess(
                try Self.runProcess(
                    executable: root.appendingPathComponent("scripts/retire_launchd_agents.sh"),
                    arguments: []
                ),
                action: "停用旧后台计划任务"
            )
            let configPathResult = try run(
                executable: root.appendingPathComponent("scripts/icloud-photo-sync"),
                arguments: ["config", "path"]
            )
            let configPath = URL(fileURLWithPath: configPathResult.output.trimmingCharacters(in: .whitespacesAndNewlines))
            if configPathResult.exitCode == 0, FileManager.default.fileExists(atPath: configPath.path) {
                let result = try run(
                    executable: root.appendingPathComponent("scripts/icloud-photo-sync"),
                    arguments: ["config", "validate"]
                )
                if result.exitCode == 0 {
                    let configSummary = try JSONDecoder().decode(
                        RuntimeConfigSummary.self,
                        from: Data(result.output.utf8)
                    )
                    self.configSummary = configSummary
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

    func completeSetup(photosLibrary: URL, nasPhotos: URL) {
        configure(photosLibrary: photosLibrary, nasPhotos: nasPhotos)
    }

    func reconfigure(photosLibrary: URL, nasPhotos: URL) {
        configure(photosLibrary: photosLibrary, nasPhotos: nasPhotos)
    }

    private func configure(photosLibrary: URL, nasPhotos: URL) {
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
                    nasPhotos: nasPhotos
                )
            }
        }
    }

    private func runSetup(
        runtimeRoot: URL,
        photosLibrary: URL,
        nasPhotos: URL
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
                            "--force",
                        ]
                    ),
                    action: "写入私有配置"
                )
                let configResult = try Self.runProcess(
                    executable: cli,
                    arguments: ["config", "validate"]
                )
                try Self.requireSuccess(configResult, action: "读取私有配置")
                let summary = try JSONDecoder().decode(
                    RuntimeConfigSummary.self,
                    from: Data(configResult.output.utf8)
                )
                try Self.requireSuccess(
                    try Self.runProcess(executable: cli, arguments: ["preflight"]),
                    action: "执行 NAS 预检"
                )
                await MainActor.run {
                    self.configSummary = summary
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

struct RuntimeConfigSummary: Decodable, Equatable {
    let configPath: String
    let photosLibrary: String
    let mirrorMountRoot: String
    let mirrorPhotosRoot: String
    let backupConfigured: Bool
    let todoExtensionConfigured: Bool

    enum CodingKeys: String, CodingKey {
        case configPath = "config_path"
        case photosLibrary = "photos_library"
        case mirrorMountRoot = "mirror_mount_root"
        case mirrorPhotosRoot = "mirror_photos_root"
        case backupConfigured = "backup_configured"
        case todoExtensionConfigured = "todo_extension_configured"
    }
}
