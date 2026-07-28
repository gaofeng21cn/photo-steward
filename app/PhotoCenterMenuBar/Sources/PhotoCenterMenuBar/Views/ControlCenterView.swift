import SwiftUI

enum ControlCenterSection: String, CaseIterable, Identifiable {
    case overview
    case planReview
    case activity

    var id: Self { self }

    var title: String {
        switch self {
        case .overview:
            return "概览"
        case .planReview:
            return "待审计划"
        case .activity:
            return "运行记录"
        }
    }

    var systemImage: String {
        switch self {
        case .overview:
            return "rectangle.3.group"
        case .planReview:
            return "doc.text.magnifyingglass"
        case .activity:
            return "clock.arrow.circlepath"
        }
    }
}

struct ControlCenterView: View {
    static let windowID = "photo-center-control-center"

    @ObservedObject var store: PhotoCenterStore
    @State private var selection: ControlCenterSection? = .overview

    var body: some View {
        NavigationSplitView {
            List(ControlCenterSection.allCases, selection: $selection) { section in
                Label(section.title, systemImage: section.systemImage)
                    .tag(section)
            }
            .navigationTitle("照片中心")
            .listStyle(.sidebar)
            .navigationSplitViewColumnWidth(min: 170, ideal: 190, max: 230)
        } detail: {
            detailView
                .navigationTitle(selection?.title ?? "照片中心")
                .toolbar {
                    ToolbarItemGroup(placement: .primaryAction) {
                        Button {
                            store.refresh()
                        } label: {
                            Label("刷新状态", systemImage: "arrow.clockwise")
                        }
                        .help("刷新状态")
                        .accessibilityLabel("刷新状态")
                        .disabled(isExecuting)

                        Button {
                            store.createPlan()
                        } label: {
                            Label("生成新计划", systemImage: "doc.text.magnifyingglass")
                        }
                        .help("生成计划")
                        .accessibilityLabel("生成计划")
                        .disabled(isExecuting)
                    }
                }
        }
        .onChange(of: store.pendingPlan) { pendingPlan in
            if pendingPlan != nil {
                selection = .planReview
            }
        }
        .frame(minWidth: 840, idealWidth: 960, minHeight: 560, idealHeight: 640)
    }

    @ViewBuilder
    private var detailView: some View {
        switch selection ?? .overview {
        case .overview:
            OverviewView(store: store) {
                selection = .planReview
            }
        case .planReview:
            PlanReviewView(store: store)
        case .activity:
            ActivityView(store: store)
        }
    }

    private var isExecuting: Bool {
        store.isBusy
    }
}

private struct OverviewView: View {
    @ObservedObject var store: PhotoCenterStore
    let onOpenPlan: () -> Void

    var body: some View {
        Form {
            if store.photosPermissionDenied {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("无法读取 Photos", systemImage: "lock.trianglebadge.exclamationmark")
                            .font(.headline)
                            .foregroundStyle(.red)
                        Text("macOS 没有允许 Photo Steward 读取照片，因此不能生成新计划。")
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
                }
            }

            if let notice = store.planNotice {
                Section {
                    Label(notice, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    if store.pendingPlan != nil {
                        Text("已有计划仍可在“待审计划”中查看；修复权限后，点击“生成新计划”获取最新差额。")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Section("服务状态") {
                LabeledContent("状态") {
                    Label(store.health.displayName, systemImage: store.statusSymbol)
                        .foregroundStyle(store.statusColor)
                }
                LabeledContent("最近成功", value: recentSuccess)
            }

            Section("待审计划") {
                if store.pendingPlan != nil {
                    LabeledContent("镜像") {
                        Text("\(store.pendingMirrorCount) 个资源")
                    }
                    LabeledContent("隔离") {
                        Text("\(store.pendingDeleteCount) 个文件")
                    }
                    LabeledContent("数据量", value: byteCount)
                    Button("查看待审计划", systemImage: "doc.text.magnifyingglass") {
                        onOpenPlan()
                    }
                    .buttonStyle(.borderedProminent)
                } else {
                    Text("当前没有待审计划。")
                        .foregroundStyle(.secondary)
                }
            }

            Section("当前消息") {
                if store.isBusy {
                    ProgressView(store.message.isEmpty ? "正在更新照片中心" : store.message)
                        .controlSize(.small)
                } else {
                    Text(store.message)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .formStyle(.grouped)
        .padding()
    }

    private var recentSuccess: String {
        store.plan?.lastSuccessAtDisplay ?? "暂无成功记录"
    }

    private var byteCount: String {
        store.pendingBytesDisplay
    }
}
