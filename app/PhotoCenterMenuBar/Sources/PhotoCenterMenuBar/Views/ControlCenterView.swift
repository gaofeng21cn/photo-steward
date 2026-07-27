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
                }
        }
        .frame(minWidth: 840, idealWidth: 960, minHeight: 560, idealHeight: 640)
    }

    @ViewBuilder
    private var detailView: some View {
        switch selection ?? .overview {
        case .overview:
            OverviewView(store: store)
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

    var body: some View {
        Form {
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
                    Text("请在“待审计划”中核对精确范围后再执行 Apply。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
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
