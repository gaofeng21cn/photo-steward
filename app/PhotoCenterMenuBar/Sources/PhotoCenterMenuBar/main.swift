import AppKit
import Darwin
import Foundation
import SwiftUI

struct JobSummary: Decodable {
    let mirrorCount: Int?
    let mirrorBytes: Int?
    let deleteCount: Int?
    let deleteBytes: Int?
    let unresolvedCount: Int?

    enum CodingKeys: String, CodingKey {
        case mirrorCount = "mirror_count"
        case mirrorBytes = "mirror_bytes"
        case deleteCount = "delete_count"
        case deleteBytes = "delete_bytes"
        case unresolvedCount = "unresolved_count"
    }
}

struct JobStatus: Decodable {
    let status: String?
    let finishedAt: String?
    let lastSuccessAt: String?
    let pendingPlanDir: String?
    let summary: JobSummary?

    enum CodingKeys: String, CodingKey {
        case status
        case finishedAt = "finished_at"
        case lastSuccessAt = "last_success_at"
        case pendingPlanDir = "pending_plan_dir"
        case summary
    }
}

struct StatusBundle: Decodable {
    let jobs: [String: JobStatus]
}

@MainActor
final class PhotoCenterModel: ObservableObject {
    @Published var bundle = StatusBundle(jobs: [:])
    @Published var message = "正在读取状态..."
    @Published var isBusy = false
    @Published var showApplyConfirmation = false

    private var executable: URL? {
        let candidates = [
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin/icloud-photo-sync"),
            URL(fileURLWithPath: "/opt/homebrew/bin/icloud-photo-sync"),
            URL(fileURLWithPath: "/usr/local/bin/icloud-photo-sync"),
            URL(fileURLWithPath: "/Users/gaofeng/workspace/app/icloud-photo-sync/scripts/icloud-photo-sync")
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    var plan: JobStatus? { bundle.jobs["plan"] }
    var apply: JobStatus? { bundle.jobs["apply"] }
    var isHealthy: Bool { plan?.status == "success" && (plan?.summary?.unresolvedCount ?? 0) == 0 }
    var pendingPlan: String? { plan?.pendingPlanDir }
    var pendingMirrorCount: Int { pendingPlan == nil ? 0 : plan?.summary?.mirrorCount ?? 0 }
    var pendingDeleteCount: Int { pendingPlan == nil ? 0 : plan?.summary?.deleteCount ?? 0 }
    var pendingBytes: Int {
        guard pendingPlan != nil else { return 0 }
        return (plan?.summary?.mirrorBytes ?? 0) + (plan?.summary?.deleteBytes ?? 0)
    }
    var statusSymbol: String { isHealthy ? "checkmark.circle.fill" : "exclamationmark.triangle.fill" }
    var statusColor: Color { isHealthy ? .green : .orange }

    init() {
        DispatchQueue.main.async { [weak self] in
            self?.refresh()
        }
    }

    func refresh() {
        run(["preflight"], timeoutSeconds: 15) { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.message = "NAS 检查失败: \(Self.outputMessage(output))"
                return
            }
            self.loadStatus()
        }
    }

    private func loadStatus() {
        run(["status", "--scope", "photo", "--format", "json"]) { [weak self] output, exitCode in
            guard let self else { return }
            guard exitCode == 0 else {
                self.message = "状态读取失败: \(Self.outputMessage(output))"
                return
            }
            do {
                self.bundle = try JSONDecoder().decode(StatusBundle.self, from: output)
                self.message = "最近读取: \(Self.now())"
            } catch {
                self.message = "状态解析失败: \(error.localizedDescription)"
            }
        }
    }

    func createPlan() {
        run(["plan-job"]) { [weak self] data, exitCode in
            guard let self else { return }
            if exitCode == 0 {
                self.message = "计划已刷新: \(Self.now())"
                self.refresh()
            } else {
                self.message = "计划失败: \(Self.outputMessage(data))"
            }
        }
    }

    func applyPendingPlan() {
        guard let pendingPlan else { return }
        run(["apply-job", "--plan-dir", pendingPlan]) { [weak self] data, exitCode in
            guard let self else { return }
            if exitCode == 0 {
                self.message = "Apply 已完成: \(Self.now())"
                self.refresh()
            } else {
                self.message = "Apply 未完成: \(Self.outputMessage(data))"
            }
        }
    }

    private func run(
        _ arguments: [String],
        timeoutSeconds: TimeInterval? = nil,
        completion: @escaping (Data, Int32) -> Void
    ) {
        guard let executable else {
            message = "找不到 icloud-photo-sync，请先运行 install_local.sh"
            return
        }
        isBusy = true
        let task = Process()
        task.executableURL = executable
        task.arguments = arguments
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = pipe
        do {
            try task.run()
            DispatchQueue.global(qos: .utility).async { [weak self] in
                let timeout = timeoutSeconds.map { _ in
                    DispatchWorkItem {
                        if task.isRunning {
                            task.terminate()
                        }
                    }
                }
                if let timeout {
                    DispatchQueue.global(qos: .utility)
                        .asyncAfter(deadline: .now() + (timeoutSeconds ?? 0), execute: timeout)
                }
                task.waitUntilExit()
                timeout?.cancel()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                DispatchQueue.main.async {
                    self?.isBusy = false
                    let exitCode = task.terminationReason == .uncaughtSignal ? EX_TEMPFAIL : task.terminationStatus
                    completion(data, exitCode)
                }
            }
        } catch {
            isBusy = false
            message = "无法执行 CLI: \(error.localizedDescription)"
        }
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
}

struct PanelView: View {
    @ObservedObject var model: PhotoCenterModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("iCloud Photo Center", systemImage: "photo.on.rectangle")
                    .font(.headline)
                Spacer()
                Circle()
                    .fill(model.statusColor)
                    .frame(width: 9, height: 9)
            }

            Divider()

            statusRow("服务状态", model.isHealthy ? "健康" : "需要检查")
            statusRow("最近成功", model.plan?.lastSuccessAt ?? "暂无")
            statusRow("待同步", "\(model.pendingMirrorCount) 个资源")
            statusRow("待隔离", "\(model.pendingDeleteCount) 个文件")
            statusRow("数据量", dataSize)
            statusRow("进度", progress)
            statusRow("未解析", "\(model.plan?.summary?.unresolvedCount ?? 0)")

            if let pendingPlan = model.pendingPlan {
                Text("待审计划")
                    .font(.subheadline.weight(.semibold))
                Text(URL(fileURLWithPath: pendingPlan).lastPathComponent)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Button("执行已批准计划", systemImage: "arrow.down.circle") {
                    model.showApplyConfirmation = true
                }
                .disabled(model.isBusy || (model.plan?.summary?.unresolvedCount ?? 0) > 0)
                .confirmationDialog(
                    "确认执行当前精确计划？NAS-only 文件会进入隔离池。",
                    isPresented: $model.showApplyConfirmation,
                    titleVisibility: .visible
                ) {
                    Button("执行 Apply", role: .destructive) { model.applyPendingPlan() }
                    Button("取消", role: .cancel) {}
                }
            }

            Text(model.message)
                .font(.caption2)
                .foregroundStyle(.secondary)

            HStack {
                Button("刷新", systemImage: "arrow.clockwise") { model.refresh() }
                    .disabled(model.isBusy)
                Button("生成计划", systemImage: "doc.text.magnifyingglass") { model.createPlan() }
                    .disabled(model.isBusy)
                Spacer()
                Button("退出", systemImage: "power") { NSApplication.shared.terminate(nil) }
            }
        }
        .padding(16)
        .frame(width: 340)
    }

    private var dataSize: String {
        ByteCountFormatter.string(fromByteCount: Int64(model.pendingBytes), countStyle: .file)
    }

    private var progress: String {
        guard let plan = model.plan else { return "暂无计划" }
        if plan.status == "success" && plan.pendingPlanDir == nil {
            return "已完成"
        }
        if (plan.summary?.unresolvedCount ?? 0) > 0 {
            return "阻塞"
        }
        if plan.pendingPlanDir != nil {
            return "待审 0%"
        }
        return "无变更"
    }

    private func statusRow(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title).foregroundStyle(.secondary)
            Spacer()
            Text(value).multilineTextAlignment(.trailing)
        }
        .font(.callout)
    }
}

struct PhotoCenterMenuBar: App {
    @StateObject private var model = PhotoCenterModel()

    var body: some Scene {
        MenuBarExtra {
            PanelView(model: model)
        } label: {
            Image(systemName: model.statusSymbol)
                .foregroundStyle(model.statusColor)
        }
        .menuBarExtraStyle(.window)
    }
}

private func runScheduledJobIfRequested() -> Int32? {
    let arguments = CommandLine.arguments
    guard let flagIndex = arguments.firstIndex(of: "--run-job") else {
        return nil
    }
    guard arguments.indices.contains(flagIndex + 1) else {
        FileHandle.standardError.write(Data("missing --run-job value\n".utf8))
        return EX_USAGE
    }

    let scriptNames = [
        "plan": "run_plan.sh",
        "deleted-pool": "run_deleted_pool_retention.sh",
        "onedrive": "run_onedrive_backup.sh",
        "todo": "run_todo_plan.sh",
    ]
    let jobName = arguments[flagIndex + 1]
    guard let scriptName = scriptNames[jobName] else {
        FileHandle.standardError.write(Data("unknown scheduled job: \(jobName)\n".utf8))
        return EX_USAGE
    }
    guard
        let resourcesURL = Bundle.main.resourceURL,
        let repositoryRoot = try? String(
            contentsOf: resourcesURL.appendingPathComponent("repository-root.txt"),
            encoding: .utf8
        ).trimmingCharacters(in: .whitespacesAndNewlines),
        !repositoryRoot.isEmpty
    else {
        FileHandle.standardError.write(Data("repository root metadata is unavailable\n".utf8))
        return EX_CONFIG
    }

    let scriptURL = URL(fileURLWithPath: repositoryRoot)
        .appendingPathComponent("scripts")
        .appendingPathComponent(scriptName)
    guard FileManager.default.isExecutableFile(atPath: scriptURL.path) else {
        FileHandle.standardError.write(Data("scheduled job script is unavailable: \(scriptURL.path)\n".utf8))
        return EX_CONFIG
    }

    let task = Process()
    task.executableURL = scriptURL
    task.currentDirectoryURL = URL(fileURLWithPath: repositoryRoot)
    task.standardOutput = FileHandle.standardOutput
    task.standardError = FileHandle.standardError
    do {
        try task.run()
        task.waitUntilExit()
        return task.terminationStatus
    } catch {
        FileHandle.standardError.write(Data("scheduled job failed to start: \(error)\n".utf8))
        return EX_OSERR
    }
}

if let exitCode = runScheduledJobIfRequested() {
    exit(exitCode)
}
PhotoCenterMenuBar.main()
