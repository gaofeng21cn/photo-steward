import Combine
import AppKit
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
    @Published private(set) var planDetails: PhotoCenterPlanDetails?
    @Published private(set) var photosPermissionDenied = false
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

    var hasReviewablePlan: Bool {
        guard let pendingPlan, let planDetails else { return false }
        return planDetails.planID == URL(fileURLWithPath: pendingPlan).lastPathComponent
    }

    var planNotice: String? {
        guard plan?.status?.lowercased() == "failed",
              let detail = plan?.message,
              !detail.isEmpty
        else {
            return nil
        }
        return Self.userFacingPlanFailure(detail)
    }

    var health: PhotoCenterHealth {
        if photosPermissionDenied {
            return .error
        }
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

    func openPhotosPermissionSettings() {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Photos") else {
            return
        }
        NSWorkspace.shared.open(url)
    }

    func refresh() {
        guard begin(.refreshing) else { return }
        guard run(["preflight"], timeoutSeconds: 15, completion: { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.finish(Self.mountFailureMessage(output, operation: "同步 CLI 预检"))
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
                self.finish(Self.mountFailureMessage(output, operation: "同步 CLI 预检"))
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
                self.finish(Self.mountFailureMessage(output, operation: "Apply 前的同步 CLI 预检"))
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
                self.finish(self.failureMessage(output, operation: "生成计划"))
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
                self.finish(self.failureMessage(output, operation: "Apply"))
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
                self.photosPermissionDenied = self.plan?.message.map(Self.isPhotosAuthorizationFailure) ?? false
                self.loadPlanDetails()
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
        if execution != .applying {
            photosPermissionDenied = false
        }
        return true
    }

    private func loadPlanDetails() {
        guard let pendingPlan else {
            planDetails = nil
            finish("最近读取：\(Self.now())")
            return
        }

        progressDetail = "正在读取待审计划"
        guard run(["plan-details", "--plan-dir", pendingPlan], completion: { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.planDetails = nil
                self.finish("状态已读取，但无法展开待审计划。请点击刷新重试。")
                return
            }

            do {
                self.planDetails = try JSONDecoder().decode(PhotoCenterPlanDetails.self, from: output)
                if let notice = self.planNotice {
                    self.finish("上次计划未生成：\(notice) 当前仍保留待审计划，可先在“待审计划”中审核。")
                } else {
                    self.finish("最近读取：\(Self.now())")
                }
            } catch {
                self.planDetails = nil
                self.finish("待审计划解析失败：\(error.localizedDescription)")
            }
        }) else {
            planDetails = nil
            finish()
            return
        }
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
            message = "找不到 Photo Steward 运行时。请重新打开正式安装包完成首次设置。"
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
            message = "无法启动 Photo Steward 运行时：\(error.localizedDescription)。请重新打开 App 完成首次设置。"
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
        let bundledRuntime = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Photo Steward/runtime/current/scripts/icloud-photo-sync")
        let candidates = [
            bundledRuntime,
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

    private func failureMessage(_ data: Data, operation: String) -> String {
        let output = Self.outputMessage(data)
        if Self.isPhotosAuthorizationFailure(output) {
            photosPermissionDenied = true
            return "\(operation)无法读取 Photos：macOS 没有允许 Photo Steward 访问照片。请点击“打开照片权限”，允许后重试。"
        }
        if output.localizedCaseInsensitiveContains("external mount is not present")
            || output.localizedCaseInsensitiveContains("path is not backed by a mounted filesystem")
        {
            return "\(operation)前未找到已配置的 NAS 挂载点。请先在 Finder 中连接 NAS，再按“设置”中显示的路径重试。"
        }
        return "\(operation)失败：\(output)。计划仍保留待审状态，请检查日志后重试。"
    }

    private static func mountFailureMessage(_ data: Data, operation: String) -> String {
        let output = Self.outputMessage(data)
        if output.localizedCaseInsensitiveContains("nas mount unavailable")
            || output.localizedCaseInsensitiveContains("external mount is not present")
            || output.localizedCaseInsensitiveContains("path is not backed by a mounted filesystem")
        {
            return "\(operation)失败：未找到已配置的 NAS 挂载点。请先在 Finder 中连接 NAS，再按“设置”中显示的路径重试。"
        }
        if output.localizedCaseInsensitiveContains("unexpected filesystem") {
            return "\(operation)失败：已配置路径不是可用的 SMB NAS 挂载。请在 Finder 中重新连接 NAS，或在“设置”中更正路径。"
        }
        return "\(operation)失败：\(output)。请检查本机配置、NAS 挂载和 CLI 安装。"
    }

    private static func isPhotosAuthorizationFailure(_ value: String) -> Bool {
        value.localizedCaseInsensitiveContains("photos authorization unavailable")
    }

    private static func userFacingPlanFailure(_ value: String) -> String {
        if isPhotosAuthorizationFailure(value) {
            return "macOS 没有允许 Photo Steward 访问 Photos"
        }
        return value
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
