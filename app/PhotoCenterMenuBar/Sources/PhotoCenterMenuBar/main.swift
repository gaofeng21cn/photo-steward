import SwiftUI

struct PhotoCenterApp: App {
    @StateObject private var store = PhotoCenterStore()

    var body: some Scene {
        WindowGroup("iCloud Photo Center", id: ControlCenterView.windowID) {
            ControlCenterView(store: store)
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
            MenuBarPopover(store: store)
        } label: {
            Image(systemName: store.statusSymbol)
                .foregroundStyle(store.statusColor)
                .accessibilityLabel("iCloud Photo Center：\(store.health.displayName)")
        }
        .menuBarExtraStyle(.window)
    }
}

PhotoCenterApp.main()
