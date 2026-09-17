import SwiftUI

@main
struct GuiltlessApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .tint(.guiltlessGreen)
                .task { await store.bootstrap() }
        }
    }
}

extension Color {
    static let guiltlessGreen = Color(red: 0.05, green: 0.28, blue: 0.18)
    static let guiltlessMint = Color(red: 0.88, green: 0.97, blue: 0.87)
    static let guiltlessCanvas = Color(red: 0.97, green: 0.98, blue: 0.95)
}
