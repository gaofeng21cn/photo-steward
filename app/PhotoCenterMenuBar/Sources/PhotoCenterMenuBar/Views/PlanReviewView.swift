import SwiftUI

struct PlanReviewView: View {
    @ObservedObject var store: PhotoCenterStore

    var body: some View {
        Group {
            if let planPath = store.pendingPlan {
                Form {
                    Section("精确计划") {
                        LabeledContent("计划 ID", value: planID(for: planPath))
                        VStack(alignment: .leading, spacing: 6) {
                            Text("来源路径")
                                .foregroundStyle(.secondary)
                            Text(planPath)
                                .font(.system(.body, design: .monospaced))
                                .textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }

                    Section("变更范围") {
                        LabeledContent("镜像到 NAS") {
                            Text("\(store.pendingMirrorCount) 个资源")
                        }
                        LabeledContent("移入隔离池") {
                            Text("\(store.pendingDeleteCount) 个文件")
                        }
                        LabeledContent("预计数据量", value: byteCount)
                    }

                    Section("执行条件") {
                        if unresolvedCount > 0 {
                            Label(
                                "存在 \(unresolvedCount) 项未解析问题，Apply 已阻塞。",
                                systemImage: "exclamationmark.triangle.fill"
                            )
                            .foregroundStyle(.orange)
                        } else {
                            Label("没有未解析阻塞项，可在确认后执行。", systemImage: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                        }
                    }

                    Section {
                        Button("执行 Apply", systemImage: "arrow.down.circle", role: .destructive) {
                            store.showApplyConfirmation = true
                        }
                        .disabled(store.isBusy || unresolvedCount > 0)
                        .confirmationDialog(
                            "确认执行此精确计划？",
                            isPresented: $store.showApplyConfirmation,
                            titleVisibility: .visible
                        ) {
                            Button("执行 Apply", role: .destructive) {
                                store.applyPendingPlan()
                            }
                            Button("取消", role: .cancel) {}
                        } message: {
                            Text("仅会执行计划 \(planID(for: planPath))。NAS-only 文件会移入隔离池，不会直接删除。")
                        }
                    } footer: {
                        Text("Apply 只会执行上方显示的精确计划。")
                    }
                }
                .formStyle(.grouped)
            } else {
                VStack(spacing: 10) {
                    Image(systemName: "doc.text")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                    Text("没有待审计划")
                        .font(.headline)
                    Text("生成计划后，可在这里审阅影响范围。")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding()
    }

    private var unresolvedCount: Int {
        store.plan?.summary?.unresolvedCount ?? 0
    }

    private var byteCount: String {
        store.pendingBytesDisplay
    }

    private func planID(for path: String) -> String {
        URL(fileURLWithPath: path).lastPathComponent
    }
}
