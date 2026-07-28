import AppKit
import SwiftUI

struct SetupView: View {
    @ObservedObject var controller: PhotoStewardRuntimeController
    let onReady: () -> Void

    @State private var photosLibrary: URL?
    @State private var nasPhotos: URL?
    @State private var installAgents = true

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            HStack(spacing: 12) {
                Image(systemName: "externaldrive.badge.icloud")
                    .font(.system(size: 34))
                    .foregroundStyle(.blue)
                VStack(alignment: .leading, spacing: 4) {
                    Text("设置 Photo Steward")
                        .font(.title2.weight(.semibold))
                    Text("只需选择一次照片图库和 NAS 目录，其他运行环境会自动安装。")
                        .foregroundStyle(.secondary)
                }
            }

            VStack(alignment: .leading, spacing: 14) {
                locationRow(
                    title: "本机 Photos 图库",
                    subtitle: photosLibrary?.path ?? "未选择",
                    symbol: "photo.on.rectangle.angled",
                    action: choosePhotosLibrary
                )
                locationRow(
                    title: "NAS 照片镜像目录",
                    subtitle: nasPhotos?.path ?? "未选择",
                    symbol: "externaldrive",
                    action: chooseNASDirectory
                )
            }

            Toggle("安装后台计划任务", isOn: $installAgents)
                .toggleStyle(.checkbox)

            if case .failed = controller.state {
                Label(controller.stateMessage, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text(controller.stateMessage)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack {
                Spacer()
                Button("完成安装并开始使用", systemImage: "checkmark.circle.fill") {
                    controller.completeSetup(
                        photosLibrary: photosLibrary!,
                        nasPhotos: nasPhotos!,
                        installAgents: installAgents
                    )
                }
                .buttonStyle(.borderedProminent)
                .disabled(
                    photosLibrary == nil
                        || nasPhotos == nil
                        || controller.state == .preparing
                        || isWorking
                )
            }
        }
        .padding(32)
        .frame(minWidth: 600, idealWidth: 680, minHeight: 430, idealHeight: 480)
        .onChange(of: controller.state) { state in
            if state == .ready {
                onReady()
            }
        }
    }

    private var isWorking: Bool {
        if case .working = controller.state {
            return true
        }
        return false
    }

    @ViewBuilder
    private func locationRow(
        title: String,
        subtitle: String,
        symbol: String,
        action: @escaping () -> Void
    ) -> some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.title3)
                .frame(width: 28)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.headline)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(subtitle == "未选择" ? .secondary : .primary)
                    .lineLimit(2)
                    .truncationMode(.middle)
            }
            Spacer()
            Button("选择", action: action)
        }
        .padding(14)
        .background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 8))
    }

    private func choosePhotosLibrary() {
        chooseDirectory(title: "选择 Photos 图库") { url in
            photosLibrary = url
        }
    }

    private func chooseNASDirectory() {
        chooseDirectory(title: "选择 NAS 照片镜像目录") { url in
            nasPhotos = url
        }
    }

    private func chooseDirectory(title: String, completion: @escaping (URL) -> Void) {
        let panel = NSOpenPanel()
        panel.title = title
        panel.message = "请选择一个已经挂载且可写的目录"
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            completion(url)
        }
    }
}
