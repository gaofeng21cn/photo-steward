import SwiftUI

struct ActivityView: View {
    @ObservedObject var store: PhotoCenterStore

    var body: some View {
        Form {
            Section("当前运行") {
                if store.isBusy {
                    ProgressView(store.message.isEmpty ? "正在处理任务" : store.message)
                        .controlSize(.small)
                } else {
                    Label("当前没有运行中的任务", systemImage: "checkmark.circle")
                        .foregroundStyle(.secondary)
                }
            }

            Section("最近计划") {
                LabeledContent("状态", value: store.plan?.statusDisplay ?? "暂无记录")
                LabeledContent("完成时间", value: store.plan?.finishedAtDisplay ?? "暂无记录")
                LabeledContent("最近成功", value: store.plan?.lastSuccessAtDisplay ?? "暂无记录")
            }

            Section("最近 Apply") {
                LabeledContent("状态", value: store.apply?.statusDisplay ?? "暂无记录")
                LabeledContent("完成时间", value: store.apply?.finishedAtDisplay ?? "暂无记录")
            }

            Section("最近消息") {
                Text(store.message.isEmpty ? "暂无消息" : store.message)
                    .textSelection(.enabled)
                    .foregroundStyle(store.message.isEmpty ? .secondary : .primary)
            }
        }
        .formStyle(.grouped)
        .padding()
    }

}
