import AppKit
import SwiftUI

struct MenuBarPopover: View {
    @ObservedObject var store: PhotoCenterStore

    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: store.statusSymbol)
                    .font(.title3)
                    .foregroundStyle(store.statusColor)
                    .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: 2) {
                    Text("iCloud Photo Center")
                        .font(.headline)
                    Text(healthTitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()
            }

            Divider()

            VStack(alignment: .leading, spacing: 10) {
                summaryRow("最近成功", value: recentSuccess)
                summaryRow("待审计划", value: pendingSummary)
            }

            if isExecuting {
                ProgressView(executionMessage)
                    .controlSize(.small)
                    .lineLimit(1)
            }

            Text(store.message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)

            Divider()

            HStack {
                Button("打开控制台", systemImage: "macwindow") {
                    openWindow(id: ControlCenterView.windowID)
                }

                Spacer()

                Button {
                    store.refresh()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("刷新状态")
                .accessibilityLabel("刷新状态")
                .disabled(isExecuting)

                Button {
                    store.createPlan()
                } label: {
                    Image(systemName: "doc.text.magnifyingglass")
                }
                .help("生成计划")
                .accessibilityLabel("生成计划")
                .disabled(isExecuting)
            }

            Button("退出", systemImage: "power") {
                NSApplication.shared.terminate(nil)
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(16)
        .frame(width: 340)
    }

    private var isExecuting: Bool {
        store.isBusy
    }

    private var healthTitle: String {
        store.health.displayName
    }

    private var recentSuccess: String {
        store.plan?.lastSuccessAtDisplay ?? "暂无成功记录"
    }

    private var pendingSummary: String {
        guard store.pendingPlan != nil else {
            return "当前没有待审计划"
        }

        let changes = store.pendingMirrorCount + store.pendingDeleteCount
        return "\(changes) 项变更，待审核"
    }

    private var executionMessage: String {
        store.message.isEmpty ? "正在更新照片中心" : store.message
    }

    @ViewBuilder
    private func summaryRow(_ title: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(title)
                .foregroundStyle(.secondary)
            Spacer(minLength: 12)
            Text(value)
                .multilineTextAlignment(.trailing)
                .lineLimit(2)
        }
        .font(.callout)
    }
}
