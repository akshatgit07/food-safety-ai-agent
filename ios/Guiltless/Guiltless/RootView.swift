import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            TabView {
                NavigationStack { ProductCatalogView() }
                    .tabItem { Label("Catalog", systemImage: "square.grid.2x2") }
                NavigationStack { DecisionFlowView() }
                    .tabItem { Label("Decide", systemImage: "sparkles") }
                NavigationStack { DailyTrackerView() }
                    .tabItem { Label("Tracker", systemImage: "chart.pie.fill") }
                NavigationStack { BagView() }
                    .tabItem { Label("Bag", systemImage: "bag") }
                    .badge(store.persistentBag.count)
                NavigationStack { ProfileView() }
                    .tabItem { Label("Profile", systemImage: "person.crop.circle") }
            }

            Button { store.guidePresented = true } label: {
                HStack(spacing: 10) {
                    Image("GuideMascot").resizable().scaledToFit().frame(width: 52, height: 52)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Guiltless Guide").font(.caption.bold())
                        Text("Ask how to use the app").font(.caption2).foregroundStyle(.white.opacity(0.75))
                    }
                }
                .padding(.vertical, 6).padding(.leading, 7).padding(.trailing, 14)
                .background(Color.guiltlessGreen, in: RoundedRectangle(cornerRadius: 20))
                .foregroundStyle(.white).shadow(color: .black.opacity(0.2), radius: 12, y: 7)
            }
            .padding(.trailing, 14).padding(.bottom, 64)
            .accessibilityLabel("Open Guiltless Guide")
        }
        .sheet(isPresented: $store.guidePresented) { GuideView() }
        .alert("Something went wrong", isPresented: Binding(get: { store.error != nil }, set: { if !$0 { store.error = nil } })) {
            Button("OK", role: .cancel) { store.error = nil }
        } message: { Text(store.error ?? "Please try again.") }
    }
}

struct BrandHeader: View {
    let eyebrow: String; let title: String; let subtitle: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(eyebrow.uppercased()).font(.caption2.bold()).tracking(1.2).foregroundStyle(.green)
            Text(title).font(.largeTitle.bold()).foregroundStyle(Color.guiltlessGreen)
            Text(subtitle).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct ScoreBadge: View {
    let score: Int
    var body: some View { Text("\(score)").font(.title2.bold()).foregroundStyle(.white).frame(width: 56, height: 56).background(score >= 65 ? Color.green : Color.orange, in: Circle()) }
}
