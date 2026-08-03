import SwiftUI

private struct MenuBarStatusIcon: View {
    let health: PhotoCenterHealth

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 14, weight: .medium))

            if let badgeSymbol {
                Image(systemName: badgeSymbol)
                    .font(.system(size: badgeSize, weight: .bold))
                    .offset(x: 3, y: -2)
            }
        }
        .symbolRenderingMode(.monochrome)
        .frame(width: 20, height: 16)
        .accessibilityElement(children: .ignore)
    }

    private var badgeSymbol: String? {
        switch health {
        case .healthy:
            return nil
        case .attention:
            return "circle.fill"
        case .error:
            return "exclamationmark.circle.fill"
        case .unknown:
            return "circle"
        }
    }

    private var badgeSize: CGFloat {
        health == .error ? 7 : 5
    }
}

struct PhotoCenterApp: App {
    @StateObject private var store = PhotoCenterStore(autoRefresh: false)
    @StateObject private var runtime = PhotoStewardRuntimeController()

    var body: some Scene {
        Window("Photo Steward", id: ControlCenterView.windowID) {
            rootView
        }
        .defaultSize(width: 960, height: 640)
        .commands {
            CommandGroup(after: .appInfo) {
                Button("刷新状态") {
                    store.refresh()
                }
                .keyboardShortcut("r", modifiers: .command)
                .disabled(store.isBusy)

                Button("生成计划") {
                    store.createPlan()
                }
                .keyboardShortcut("p", modifiers: .command)
                .disabled(store.isBusy)
            }
        }

        MenuBarExtra {
            if runtime.isReady {
                MenuBarPopover(store: store)
            } else {
                SetupView(controller: runtime) {
                    store.refresh()
                }
            }
        } label: {
            MenuBarStatusIcon(health: store.health)
                .accessibilityLabel("Photo Steward：\(store.health.displayName)")
        }
        .menuBarExtraStyle(.window)
    }

    @ViewBuilder
    private var rootView: some View {
        if runtime.isReady {
            ControlCenterView(store: store, runtime: runtime)
                .onAppear {
                    if store.bundle.jobs.isEmpty {
                        store.refresh()
                    }
                }
        } else {
            SetupView(controller: runtime) {
                store.refresh()
            }
        }
    }
}

PhotoCenterApp.main()
