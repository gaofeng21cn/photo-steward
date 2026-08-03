import AppKit
import SwiftUI

struct ConfigurationView: View {
    @ObservedObject var controller: PhotoStewardRuntimeController

    @State private var photosLibrary: URL?
    @State private var nasPhotos: URL?

    var body: some View {
        Form {
            Section {
                Text("Photo Steward 会把本机 Photos 图库视为唯一来源，NAS 只保存受控镜像。这里的设置会写入本机私有配置，不会进入项目仓库。")
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section("当前配置") {
                configRow("配置文件", value: controller.configSummary?.configPath ?? "未读取")
                configRow("Photos 图库", value: controller.configSummary?.photosLibrary ?? "未读取")
                configRow("NAS 挂载点", value: controller.configSummary?.mirrorMountRoot ?? "未读取")
                configRow("NAS 照片目录", value: controller.configSummary?.mirrorPhotosRoot ?? "未读取")
            }

            Section("更换目录") {
                locationRow(
                    title: "Photos 图库",
                    value: photosLibrary?.path ?? controller.configSummary?.photosLibrary ?? "未选择",
                    symbol: "photo.on.rectangle.angled"
                ) {
                    choosePhotosLibrary()
                }
                locationRow(
                    title: "NAS 照片镜像目录",
                    value: nasPhotos?.path ?? controller.configSummary?.mirrorPhotosRoot ?? "未选择",
                    symbol: "externaldrive"
                ) {
                    chooseNASDirectory()
                }

                Text("运行模式：手动。需要检查差异时生成计划，审阅精确计划后再确认执行。")
                    .font(.callout)
                    .foregroundStyle(.secondary)

                Button("保存并重新校验", systemImage: "checkmark.shield") {
                    saveConfiguration()
                }
                .buttonStyle(.borderedProminent)
                .disabled(!canSave || isWorking)

                if isWorking {
                    ProgressView(controller.stateMessage)
                        .controlSize(.small)
                } else if case .failed = controller.state {
                    Label(controller.stateMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Section("说明") {
                Text("NAS 密码由 macOS 的网络磁盘挂载管理。Photo Steward 只接收已经挂载且可写的目录，并自动推导同一挂载点下的隔离池和同步回执目录。")
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button("在 Finder 中打开 NAS 照片目录", systemImage: "folder") {
                    guard let path = controller.configSummary?.mirrorPhotosRoot else { return }
                    NSWorkspace.shared.open(URL(fileURLWithPath: path, isDirectory: true))
                }
                .disabled(controller.configSummary?.mirrorPhotosRoot == nil)
            }
        }
        .formStyle(.grouped)
        .padding()
        .onAppear {
            loadCurrentConfiguration()
        }
    }

    private var canSave: Bool {
        photosLibrary != nil && nasPhotos != nil
    }

    private var isWorking: Bool {
        if case .working = controller.state {
            return true
        }
        return false
    }

    private func loadCurrentConfiguration() {
        guard let summary = controller.configSummary else { return }
        if photosLibrary == nil {
            photosLibrary = URL(fileURLWithPath: summary.photosLibrary, isDirectory: true)
        }
        if nasPhotos == nil {
            nasPhotos = URL(fileURLWithPath: summary.mirrorPhotosRoot, isDirectory: true)
        }
    }

    private func saveConfiguration() {
        guard let photosLibrary, let nasPhotos else { return }
        controller.reconfigure(
            photosLibrary: photosLibrary,
            nasPhotos: nasPhotos
        )
    }

    private func choosePhotosLibrary() {
        chooseDirectory(title: "选择 Photos 图库") { photosLibrary = $0 }
    }

    private func chooseNASDirectory() {
        chooseDirectory(title: "选择 NAS 照片镜像目录") { nasPhotos = $0 }
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

    @ViewBuilder
    private func configRow(_ title: String, value: String) -> some View {
        LabeledContent(title) {
            Text(value)
                .multilineTextAlignment(.trailing)
                .lineLimit(2)
                .truncationMode(.middle)
                .textSelection(.enabled)
        }
    }

    @ViewBuilder
    private func locationRow(
        title: String,
        value: String,
        symbol: String,
        action: @escaping () -> Void
    ) -> some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .foregroundStyle(.secondary)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.headline)
                Text(value)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .truncationMode(.middle)
            }
            Spacer()
            Button("更改", action: action)
        }
    }
}
