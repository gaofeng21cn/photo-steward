import AppKit
import ImageIO
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
    @StateObject private var previewLoader: PhotoPreviewLoader

    init(item: PhotoCenterPlanItem) {
        self.item = item
        _previewLoader = StateObject(wrappedValue: PhotoPreviewLoader(item: item))
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Button {
                showingPreview = true
            } label: {
                HStack(alignment: .top, spacing: 12) {
                    PlanItemThumbnail(item: item, loader: previewLoader)

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
            PlanItemPreview(item: item, loader: previewLoader)
        }
        .padding(10)
        .background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct PlanItemThumbnail: View {
    let item: PhotoCenterPlanItem
    @ObservedObject var loader: PhotoPreviewLoader

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 7)
                .fill(.quaternary)

            if let image = loader.image {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFill()
            } else if loader.isLoading {
                ProgressView()
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
            loader.load(targetSize: CGSize(width: 180, height: 180))
        }
    }
}

private struct PlanItemPreview: View {
    let item: PhotoCenterPlanItem
    @ObservedObject var loader: PhotoPreviewLoader
    @Environment(\.dismiss) private var dismiss

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
                if let image = loader.image {
                    Image(nsImage: image)
                        .resizable()
                        .scaledToFit()
                        .padding(8)
                } else if loader.isLoading {
                    ProgressView("正在读取预览...")
                } else {
                    VStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.largeTitle)
                            .foregroundStyle(.secondary)
                        Text(loader.errorMessage ?? "暂时无法读取预览")
                            .foregroundStyle(.secondary)
                        HStack {
                            Button("重试", systemImage: "arrow.clockwise") {
                                loader.reload(targetSize: CGSize(width: 1600, height: 1600))
                            }
                            if item.sourcePath != nil {
                                Button("在 Finder 中查看", systemImage: "arrow.up.forward.app") {
                                    revealSource()
                                }
                            }
                        }
                        .buttonStyle(.bordered)
                        Text(item.action == .mirror ? "请确认 Photo Steward 已获得 Photos 权限，且原图已下载到本机。" : "文件仍可在 Finder 中查看。")
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
            loader.load(targetSize: CGSize(width: 1600, height: 1600))
        }
    }

    private func revealSource() {
        guard let sourcePath = item.sourcePath else { return }
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: sourcePath)])
    }
}

private final class PhotoPreviewLoader: ObservableObject {
    @Published private(set) var image: NSImage?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    private let item: PhotoCenterPlanItem
    private var loadedMaxPixelSize = 0
    private var requestedMaxPixelSize = 0

    init(item: PhotoCenterPlanItem) {
        self.item = item
    }

    func load(targetSize: CGSize) {
        let maxPixelSize = max(1, Int(max(targetSize.width, targetSize.height)))
        requestedMaxPixelSize = max(requestedMaxPixelSize, maxPixelSize)
        guard !isLoading, image == nil || maxPixelSize > loadedMaxPixelSize else { return }

        isLoading = true
        errorMessage = nil
        let requestSize = requestedMaxPixelSize

        if let sourcePath = item.sourcePath {
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                let image = Self.imageFromFile(path: sourcePath, maxPixelSize: requestSize)
                self?.finish(image: image, error: image == nil ? "无法读取文件或解码照片格式。" : nil, loadedSize: requestSize)
            }
            return
        }

        guard let localIdentifier = item.assetLocalIdentifier else {
            finish(image: nil, error: "计划没有可用的照片来源。", loadedSize: requestSize)
            return
        }

        let assets = PHAsset.fetchAssets(withLocalIdentifiers: [localIdentifier], options: nil)
        guard let asset = assets.firstObject else {
            finish(image: nil, error: "在本机 Photos 中找不到这项资产。", loadedSize: requestSize)
            return
        }

        let options = PHImageRequestOptions()
        options.deliveryMode = .highQualityFormat
        options.resizeMode = .fast
        options.isNetworkAccessAllowed = true
        PHImageManager.default().requestImage(
            for: asset,
            targetSize: CGSize(width: requestSize, height: requestSize),
            contentMode: .aspectFit,
            options: options
        ) { [weak self] image, info in
            let isDegraded = (info?[PHImageResultIsDegradedKey] as? Bool) ?? false
            if let image, !isDegraded {
                self?.finish(image: image, error: nil, loadedSize: requestSize)
            } else if let error = info?[PHImageErrorKey] as? Error {
                self?.finish(image: nil, error: error.localizedDescription, loadedSize: requestSize)
            } else if (info?[PHImageCancelledKey] as? Bool) == true {
                self?.finish(image: nil, error: "预览读取已取消。", loadedSize: requestSize)
            } else if !isDegraded && image == nil {
                self?.finish(image: nil, error: "Photos 没有返回可显示的预览。", loadedSize: requestSize)
            }
        }
    }

    func reload(targetSize: CGSize) {
        image = nil
        loadedMaxPixelSize = 0
        requestedMaxPixelSize = 0
        errorMessage = nil
        load(targetSize: targetSize)
    }

    private func finish(image: NSImage?, error: String?, loadedSize: Int) {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.isLoading = false
            if let image {
                self.image = image
                self.loadedMaxPixelSize = loadedSize
                self.errorMessage = nil
            } else {
                self.errorMessage = error
            }

            if self.requestedMaxPixelSize > self.loadedMaxPixelSize, !self.isLoading {
                self.load(targetSize: CGSize(
                    width: self.requestedMaxPixelSize,
                    height: self.requestedMaxPixelSize
                ))
            }
        }
    }

    private static func imageFromFile(path: String, maxPixelSize: Int) -> NSImage? {
        let url = URL(fileURLWithPath: path)
        guard let data = try? Data(contentsOf: url, options: .mappedIfSafe), !data.isEmpty else {
            return nil
        }

        if let source = CGImageSourceCreateWithData(data as CFData, nil) {
            let options: [CFString: Any] = [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: maxPixelSize
            ]
            if let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) {
                return NSImage(cgImage: thumbnail, size: .zero)
            }
        }

        return NSImage(data: data)
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
