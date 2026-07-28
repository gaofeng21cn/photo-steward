import Combine
import Foundation
import SwiftUI

private final class PhotoCenterOutputCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var stdout = Data()
    private var stderr = Data()

    func recordStdout(_ output: Data) {
        lock.lock()
        defer { lock.unlock() }
        stdout = output
    }

    func recordStderr(_ output: Data) {
        lock.lock()
        defer { lock.unlock() }
        stderr = output
    }

    func combinedOutput() -> Data {
        lock.lock()
        defer { lock.unlock() }
        return stdout + stderr
    }
}

@MainActor
final class PhotoCenterStore: ObservableObject {
    @Published private(set) var bundle = PhotoCenterStatusBundle()
    @Published private(set) var message = "正在读取状态..."
    @Published private(set) var execution: PhotoCenterExecution = .idle
    @Published private(set) var progressDetail: String?
    @Published var showApplyConfirmation = false

    init(autoRefresh: Bool = true) {
        guard autoRefresh else { return }
        DispatchQueue.main.async { [weak self] in
            self?.refresh()
        }
    }

    var plan: PhotoCenterJobStatus? {
        bundle.jobs["plan"]
    }

    var apply: PhotoCenterJobStatus? {
        bundle.jobs["apply"]
    }

    var pendingPlan: String? {
        plan?.pendingPlanDir
    }

    var pendingMirrorCount: Int {
        guard pendingPlan != nil else { return 0 }
        return plan?.summary?.mirrorCount ?? 0
    }

    var pendingDeleteCount: Int {
        guard pendingPlan != nil else { return 0 }
        return plan?.summary?.deleteCount ?? 0
    }

    var pendingBytes: Int {
        guard pendingPlan != nil else { return 0 }
        return (plan?.summary?.mirrorBytes ?? 0) + (plan?.summary?.deleteBytes ?? 0)
    }

    var pendingBytesDisplay: String {
        Self.byteCountDisplay(pendingBytes)
    }

    var health: PhotoCenterHealth {
        guard let plan else { return .unknown }

        if plan.status?.lowercased() == "failed" {
            return .error
        }
        if pendingPlan != nil || (plan.summary?.unresolvedCount ?? 0) > 0 {
            return .attention
        }

        switch plan.status?.lowercased() {
        case "success":
            return .healthy
        case "partial", "blocked", "pending", "running":
            return .attention
        default:
            return .unknown
        }
    }

    var statusSymbol: String {
        switch health {
        case .healthy:
            return "checkmark.circle.fill"
        case .attention:
            return "exclamationmark.circle.fill"
        case .error:
            return "xmark.octagon.fill"
        case .unknown:
            return "questionmark.circle.fill"
        }
    }

    var statusColor: Color {
        switch health {
        case .healthy:
            return .green
        case .attention:
            return .orange
        case .error:
            return .red
        case .unknown:
            return .secondary
        }
    }

    var isBusy: Bool {
        execution != .idle
    }

    var executionLabel: String {
        if let progressDetail {
            return progressDetail
        }

        switch execution {
        case .idle:
            return "空闲"
        case .refreshing:
            return "正在检查 NAS 挂载和同步服务"
        case .creatingPlan:
            return "正在检查 NAS 挂载和同步服务"
        case .applying:
            return "正在执行已批准计划"
        }
    }

    func refresh() {
        guard begin(.refreshing) else { return }
        guard run(["preflight"], timeoutSeconds: 15, completion: { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.finish(
                    "同步 CLI 预检失败：\(Self.outputMessage(output))。请检查本机配置、NAS 挂载和 CLI 安装；这不是 Photos 权限问题。"
                )
                return
            }
            self.loadStatus()
        }) else {
            finish()
            return
        }
    }

    func createPlan() {
        guard begin(.creatingPlan) else { return }
        guard run(["preflight"], timeoutSeconds: 15, completion: { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.finish(
                    "同步 CLI 预检失败：\(Self.outputMessage(output))。请检查本机配置、NAS 挂载和 CLI 安装；这不是 Photos 权限问题。"
                )
                return
            }
            self.runPlanJob()
        }) else {
            finish()
            return
        }
    }

    func applyPendingPlan() {
        guard let pendingPlan else {
            message = "没有待审计划可执行。请先生成并审阅计划。"
            return
        }

        guard begin(.applying) else { return }
        showApplyConfirmation = false
        progressDetail = "正在检查 NAS 挂载和同步服务"
        guard run(["preflight"], timeoutSeconds: 15, completion: { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.finish(
                    "Apply 前的同步 CLI 预检失败：\(Self.outputMessage(output))。请检查本机配置、NAS 挂载和 CLI 安装。"
                )
                return
            }
            self.runApplyJob(planDir: pendingPlan)
        }) else {
            finish()
            return
        }
    }

    private func runPlanJob() {
        progressDetail = "正在准备同步计划"
        guard run(["plan-job"], completion: { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.finish("生成计划失败：\(Self.outputMessage(output))。请检查 NAS 挂载和同步 CLI。")
                return
            }
            self.message = "计划已生成，正在读取状态..."
            self.loadStatus()
        }) else {
            finish()
            return
        }
    }

    private func runApplyJob(planDir: String) {
        progressDetail = "正在执行已批准计划"
        guard run(["apply-job", "--plan-dir", planDir], completion: { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.finish(
                    "Apply 失败：\(Self.outputMessage(output))。计划仍保留待审状态，请检查最新日志后重试。"
                )
                return
            }
            self.message = "Apply 已完成，正在读取最新状态..."
            self.loadStatus()
        }) else {
            finish()
            return
        }
    }

    private func loadStatus() {
        progressDetail = "正在读取最新状态"
        guard run(["status", "--scope", "photo", "--format", "json"], completion: { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.finish("状态读取失败：\(Self.outputMessage(output))。请检查同步 CLI。")
                return
            }

            do {
                self.bundle = try JSONDecoder().decode(PhotoCenterStatusBundle.self, from: output)
                self.finish("最近读取：\(Self.now())")
            } catch {
                self.finish("状态解析失败：\(error.localizedDescription)")
            }
        }) else {
            finish()
            return
        }
    }

    private func begin(_ execution: PhotoCenterExecution) -> Bool {
        guard self.execution == .idle else {
            message = "\(self.execution.displayName)，请稍候。"
            return false
        }
        self.execution = execution
        progressDetail = nil
        return true
    }

    private func finish(_ nextMessage: String? = nil) {
        execution = .idle
        progressDetail = nil
        if let nextMessage {
            message = nextMessage
        }
    }

    @discardableResult
    private func run(
        _ arguments: [String],
        timeoutSeconds: TimeInterval? = nil,
        completion: @escaping (Data, Int32) -> Void
    ) -> Bool {
        guard let executable = executable else {
            message = "找不到 Photo Steward 命令。请运行 scripts/install_local.sh 后重试；这不是 Photos 权限问题。"
            return false
        }

        let task = Process()
        task.executableURL = executable
        task.arguments = arguments

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        task.standardOutput = stdoutPipe
        task.standardError = stderrPipe

        do {
            try task.run()
        } catch {
            message = "无法启动同步 CLI：\(error.localizedDescription)。请检查 CLI 安装；这不是 Photos 权限问题。"
            return false
        }

        stdoutPipe.fileHandleForWriting.closeFile()
        stderrPipe.fileHandleForWriting.closeFile()

        if let timeoutSeconds {
            DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + timeoutSeconds) {
                if task.isRunning {
                    task.terminate()
                }
            }
        }

        let streamReaders = DispatchGroup()
        let outputCollector = PhotoCenterOutputCollector()

        streamReaders.enter()
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let output = Self.readStream(stdoutPipe.fileHandleForReading) { line in
                DispatchQueue.main.async {
                    self?.consumeProgressLine(line)
                }
            }
            outputCollector.recordStdout(output)
            streamReaders.leave()
        }

        streamReaders.enter()
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let output = Self.readStream(stderrPipe.fileHandleForReading) { line in
                DispatchQueue.main.async {
                    self?.consumeProgressLine(line)
                }
            }
            outputCollector.recordStderr(output)
            streamReaders.leave()
        }

        DispatchQueue.global(qos: .utility).async {
            task.waitUntilExit()
            streamReaders.wait()

            let exitCode: Int32 = task.terminationReason == .exit ? task.terminationStatus : -1
            let output = outputCollector.combinedOutput()
            DispatchQueue.main.async {
                completion(output, exitCode)
            }
        }
        return true
    }

    private func consumeProgressLine(_ line: String) {
        guard let data = line.data(using: .utf8),
              let event = try? JSONDecoder().decode(PhotoCenterProgressEvent.self, from: data),
              let detail = event.progressDetail
        else {
            return
        }
        progressDetail = detail
    }

    private var executable: URL? {
        let candidates = [
            FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent(".local/bin/photo-steward"),
            URL(fileURLWithPath: "/opt/homebrew/bin/photo-steward"),
            URL(fileURLWithPath: "/usr/local/bin/photo-steward"),
            FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent(".local/bin/icloud-photo-sync"),
            URL(fileURLWithPath: "/opt/homebrew/bin/icloud-photo-sync"),
            URL(fileURLWithPath: "/usr/local/bin/icloud-photo-sync"),
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    private static func now() -> String {
        Date.now.formatted(date: .omitted, time: .shortened)
    }

    private static func outputMessage(_ data: Data) -> String {
        String(data: data, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: "\n")
            .last
            .map(String.init) ?? "未知错误"
    }

    nonisolated private static func readStream(
        _ handle: FileHandle,
        onLine: @escaping (String) -> Void
    ) -> Data {
        defer {
            try? handle.close()
        }

        var output = Data()
        var buffer = Data()
        while true {
            guard let chunk = try? handle.read(upToCount: 4_096), !chunk.isEmpty else {
                break
            }
            output.append(chunk)
            buffer.append(chunk)

            while let newline = buffer.firstIndex(of: 0x0A) {
                let line = Data(buffer[..<newline])
                buffer.removeSubrange(...newline)
                onLine(String(decoding: line, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }

        if !buffer.isEmpty {
            onLine(String(decoding: buffer, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return output
    }

    private static func byteCountDisplay(_ byteCount: Int) -> String {
        guard byteCount > 0 else { return "0 字节" }
        return ByteCountFormatter.string(fromByteCount: Int64(byteCount), countStyle: .file)
    }
}
