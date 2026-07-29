import SwiftUI

struct PhotoCenterApp: App {
    @StateObject private var store = PhotoCenterStore(autoRefresh: false)
    @StateObject private var runtime = PhotoStewardRuntimeController()

    var body: some Scene {
        WindowGroup("Photo Steward", id: ControlCenterView.windowID) {
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
            Image(systemName: store.statusSymbol)
                .foregroundStyle(store.statusColor)
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
