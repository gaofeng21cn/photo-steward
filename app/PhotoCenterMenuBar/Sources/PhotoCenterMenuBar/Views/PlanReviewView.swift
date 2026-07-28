import AppKit
import Photos
import SwiftUI

struct PlanReviewView: View {
    @ObservedObject var store: PhotoCenterStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if store.photosPermissionDenied {
                    PhotosPermissionBanner(store: store)
                }

                if let planPath = store.pendingPlan {
                    reviewHeader(planPath: planPath)

                    if let details = store.planDetails {
                        if !details.mirrorItems.isEmpty {
                            PlanActionSection(
                                title: "将镜像到 NAS",
                                subtitle: "这些照片存在于 iCloud Photos，将复制到 NAS 对应月份目录。",
                                icon: "arrow.down.to.line",
                                color: .blue,
                                items: details.mirrorItems
                            )
                        }

                        if !details.quarantineItems.isEmpty {
                            PlanActionSection(
                                title: "将移入隔离池",
                                subtitle: "这些文件只存在于 NAS，不在 iCloud Photos 中；不会直接删除。",
                                icon: "archivebox",
                                color: .orange,
                                items: details.quarantineItems
                            )
                        }

                        reviewFooter(planID: details.planID)
                    } else {
                        VStack(alignment: .leading, spacing: 10) {
                            ProgressView("正在读取待审文件...")
                            Text("只有完整读取计划明细后，才可以确认执行。")
                                .font(.callout)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 20)
                    }
                } else {
                    emptyState
                }
            }
            .frame(maxWidth: 900, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .center)
            .padding(24)
        }
    }

    @ViewBuilder
    private func reviewHeader(planPath: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("先看清楚，再执行")
                        .font(.title2.weight(.semibold))
                    Text("iCloud Photos 是唯一来源。本次计划只会改变 NAS，不会修改 iCloud Photos。")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(planID(for: planPath))
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            HStack(spacing: 12) {
                PlanMetric(
                    title: "镜像到 NAS",
                    value: "\(store.pendingMirrorCount) 项",
                    detail: ByteCountFormatter.string(
                        fromByteCount: Int64(store.plan?.summary?.mirrorBytes ?? 0),
                        countStyle: .file
                    ),
                    color: .blue
                )
                PlanMetric(
                    title: "移入隔离池",
                    value: "\(store.pendingDeleteCount) 项",
                    detail: ByteCountFormatter.string(
                        fromByteCount: Int64(store.plan?.summary?.deleteBytes ?? 0),
                        countStyle: .file
                    ),
                    color: .orange
                )
                PlanMetric(
                    title: "未解析",
                    value: "\(unresolvedCount) 项",
                    detail: unresolvedCount == 0 ? "可以继续审核" : "Apply 已阻塞",
                    color: unresolvedCount == 0 ? .green : .red
                )
            }
        }
    }

    @ViewBuilder
    private func reviewFooter(planID: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if unresolvedCount > 0 {
                Label(
                    "存在 \(unresolvedCount) 项未解析问题，Apply 已阻塞。",
                    systemImage: "exclamationmark.triangle.fill"
                )
                .foregroundStyle(.red)
            } else {
                Label(
                    "已读取 \(store.planDetails?.items.count ?? 0) 项。确认后，系统会按这份计划执行并回读结果。",
                    systemImage: "checkmark.circle.fill"
                )
                .foregroundStyle(.secondary)
            }

            HStack {
                Button("刷新计划", systemImage: "arrow.clockwise") {
                    store.refresh()
                }
                .disabled(store.isBusy)

                Spacer()

                Button("确认并执行此计划", systemImage: "checkmark.shield", role: .destructive) {
                    store.showApplyConfirmation = true
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.isBusy || unresolvedCount > 0 || !store.hasReviewablePlan)
                .confirmationDialog(
                    "确认执行这份计划？",
                    isPresented: $store.showApplyConfirmation,
                    titleVisibility: .visible
                ) {
                    Button("确认执行", role: .destructive) {
                        store.applyPendingPlan()
                    }
                    Button("取消", role: .cancel) {}
                } message: {
                    Text(
                        "计划 \(planID) 将镜像 \(store.pendingMirrorCount) 项，" +
                            "并将 \(store.pendingDeleteCount) 项 NAS-only 文件移入隔离池。不会直接删除。"
                    )
                }
            }
        }
        .padding(.top, 4)
    }

    private var unresolvedCount: Int {
        store.plan?.summary?.unresolvedCount ?? 0
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "checkmark.circle")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("没有待审计划")
                .font(.headline)
            Text("状态正常。需要检查差额时，点击右上角的“生成新计划”。")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 360)
    }

    private func planID(for path: String) -> String {
        URL(fileURLWithPath: path).lastPathComponent
    }
}

private struct PlanMetric: View {
    let title: String
    let value: String
    let detail: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.weight(.semibold))
            Text(detail)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        .overlay(alignment: .leading) {
            RoundedRectangle(cornerRadius: 2)
                .fill(color)
                .frame(width: 4)
        }
    }
}

private struct PlanActionSection: View {
    let title: String
    let subtitle: String
    let icon: String
    let color: Color
    let items: [PhotoCenterPlanItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: icon)
                .font(.headline)
                .foregroundStyle(color)
            Text(subtitle)
                .font(.callout)
                .foregroundStyle(.secondary)

            LazyVStack(spacing: 8) {
                ForEach(items) { item in
                    PlanItemRow(item: item)
                }
            }
        }
    }
}

private struct PlanItemRow: View {
    let item: PhotoCenterPlanItem
    @State private var showingPreview = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Button {
                showingPreview = true
            } label: {
                HStack(alignment: .top, spacing: 12) {
                    PlanItemThumbnail(item: item)

                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 8) {
                            Text(item.originalFilename)
                                .font(.body.weight(.medium))
                                .lineLimit(1)
                            Text(item.action.title)
                                .font(.caption)
                                .foregroundStyle(item.action == .mirror ? .blue : .orange)
                        }

                        Text(item.relativePath)
                            .font(.system(.callout, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                            .textSelection(.enabled)

                        HStack(spacing: 12) {
                            Label(
                                ByteCountFormatter.string(
                                    fromByteCount: Int64(item.bytes),
                                    countStyle: .file
                                ),
                                systemImage: "doc"
                            )
                            if item.action == .quarantine {
                                Label("NAS-only", systemImage: "externaldrive")
                            } else {
                                Label("iCloud Photos", systemImage: "icloud")
                            }
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)

                        DisclosureGroup("查看 SHA-256") {
                            Text(item.sha256)
                                .font(.system(.caption2, design: .monospaced))
                                .textSelection(.enabled)
                                .foregroundStyle(.secondary)
                                .padding(.top, 2)
                        }
                        .font(.caption)
                    }

                    Spacer(minLength: 8)
                }
            }
            .buttonStyle(.plain)
            .help("查看照片预览和完整信息")

            if let sourcePath = item.sourcePath {
                Button {
                    NSWorkspace.shared.selectFile(sourcePath, inFileViewerRootedAtPath: "")
                } label: {
                    Image(systemName: "arrow.up.forward.app")
                }
                .buttonStyle(.borderless)
                .help("在 Finder 中查看")
                .accessibilityLabel("在 Finder 中查看")
            }
        }
        .sheet(isPresented: $showingPreview) {
            PlanItemPreview(item: item)
        }
        .padding(10)
        .background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct PlanItemThumbnail: View {
    let item: PhotoCenterPlanItem

    @State private var image: NSImage?
    @State private var didLoad = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 7)
                .fill(.quaternary)

            if let image {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                Image(systemName: item.action == .quarantine ? "photo" : "icloud")
                    .font(.title3)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 76, height: 76)
        .clipShape(RoundedRectangle(cornerRadius: 7))
        .overlay {
            RoundedRectangle(cornerRadius: 7)
                .stroke(.separator, lineWidth: 0.5)
        }
        .onAppear {
            loadPreview()
        }
    }

    private func loadPreview() {
        guard !didLoad else { return }
        didLoad = true

        if let sourcePath = item.sourcePath, let image = NSImage(contentsOfFile: sourcePath) {
            self.image = image
            return
        }

        guard let localIdentifier = item.assetLocalIdentifier else { return }
        let assets = PHAsset.fetchAssets(withLocalIdentifiers: [localIdentifier], options: nil)
        guard let asset = assets.firstObject else { return }

        let options = PHImageRequestOptions()
        options.deliveryMode = .opportunistic
        options.resizeMode = .fast
        options.isNetworkAccessAllowed = true
        PHImageManager.default().requestImage(
            for: asset,
            targetSize: CGSize(width: 152, height: 152),
            contentMode: .aspectFill,
            options: options
        ) { image, _ in
            guard let image else { return }
            DispatchQueue.main.async {
                self.image = image
            }
        }
    }
}

private struct PlanItemPreview: View {
    let item: PhotoCenterPlanItem
    @Environment(\.dismiss) private var dismiss
    @State private var image: NSImage?
    @State private var didLoad = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 5) {
                    Text(item.originalFilename)
                        .font(.title3.weight(.semibold))
                    Text(item.action.title)
                        .foregroundStyle(item.action == .mirror ? .blue : .orange)
                }
                Spacer()
                Button("关闭", systemImage: "xmark") {
                    dismiss()
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("关闭预览")
            }

            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(.quaternary)
                if let image {
                    Image(nsImage: image)
                        .resizable()
                        .scaledToFit()
                        .padding(8)
                } else {
                    VStack(spacing: 8) {
                        Image(systemName: item.action == .quarantine ? "photo" : "icloud")
                            .font(.largeTitle)
                            .foregroundStyle(.secondary)
                        Text("暂时无法读取预览")
                            .foregroundStyle(.secondary)
                        Text(item.action == .mirror ? "请确认 Photo Steward 已获得 Photos 权限。" : "文件仍可在 Finder 中查看。")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .frame(minWidth: 520, minHeight: 330)

            VStack(alignment: .leading, spacing: 7) {
                LabeledContent("目标路径", value: item.relativePath)
                LabeledContent(
                    "文件大小",
                    value: ByteCountFormatter.string(
                        fromByteCount: Int64(item.bytes),
                        countStyle: .file
                    )
                )
                LabeledContent("SHA-256", value: item.sha256)
                    .textSelection(.enabled)
            }
            .font(.callout)
            .textSelection(.enabled)
        }
        .padding(22)
        .frame(minWidth: 600, minHeight: 500)
        .onAppear {
            loadPreview()
        }
    }

    private func loadPreview() {
        guard !didLoad else { return }
        didLoad = true

        if let sourcePath = item.sourcePath, let image = NSImage(contentsOfFile: sourcePath) {
            self.image = image
            return
        }

        guard let localIdentifier = item.assetLocalIdentifier else { return }
        let assets = PHAsset.fetchAssets(withLocalIdentifiers: [localIdentifier], options: nil)
        guard let asset = assets.firstObject else { return }

        let options = PHImageRequestOptions()
        options.deliveryMode = .opportunistic
        options.resizeMode = .fast
        options.isNetworkAccessAllowed = true
        PHImageManager.default().requestImage(
            for: asset,
            targetSize: CGSize(width: 1200, height: 1200),
            contentMode: .aspectFit,
            options: options
        ) { image, _ in
            guard let image else { return }
            DispatchQueue.main.async {
                self.image = image
            }
        }
    }
}

private struct PhotosPermissionBanner: View {
    @ObservedObject var store: PhotoCenterStore

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "lock.trianglebadge.exclamationmark")
                .foregroundStyle(.red)
            VStack(alignment: .leading, spacing: 5) {
                Text("无法读取 Photos")
                    .font(.headline)
                Text("macOS 没有允许 Photo Steward 读取照片，因此不能生成新计划。待审计划仍可查看；允许权限后再重试。")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                HStack {
                    Button("打开照片权限", systemImage: "gear") {
                        store.openPhotosPermissionSettings()
                    }
                    Button("重试", systemImage: "arrow.clockwise") {
                        store.refresh()
                    }
                    .disabled(store.isBusy)
                }
                .buttonStyle(.bordered)
            }
            Spacer()
        }
        .padding(14)
        .background(.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}
