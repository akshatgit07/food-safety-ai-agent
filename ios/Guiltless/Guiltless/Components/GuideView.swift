import SwiftUI

struct GuideView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var message = "How do I use this screen?"
    @State private var reply: HelperResponse?
    @State private var loading = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack { Image("GuideMascot").resizable().scaledToFit().frame(width: 88, height: 88); VStack(alignment: .leading) { Text("Your in-app companion").font(.title2.bold()); Text("Grounded in your product, goal, bag, and saved memory.").font(.caption).foregroundStyle(.secondary) } }
                    Text("Current context: \(store.selectedProduct.name) · \(store.goal)").font(.caption).padding().frame(maxWidth: .infinity, alignment: .leading).background(Color.guiltlessMint, in: RoundedRectangle(cornerRadius: 12))
                    ScrollView(.horizontal, showsIndicators: false) { HStack { ForEach(["Explain this score", "Compare alternatives", "Optimize my bag", "How do I use this screen?"], id: \.self) { prompt in Button(prompt) { message = prompt; Task { await ask() } }.buttonStyle(.bordered) } } }
                    TextField("Ask Guiltless", text: $message, axis: .vertical).textFieldStyle(.roundedBorder).lineLimit(3...6)
                    Button(loading ? "Checking your context…" : "Ask Guiltless") { Task { await ask() } }.buttonStyle(GuiltlessButtonStyle()).disabled(loading || message.isEmpty)
                    if let reply { Text(reply.intent.replacingOccurrences(of: "_", with: " ").uppercased()).font(.caption.bold()).foregroundStyle(.green); Text(reply.response).font(.title3.bold()); ForEach(Array(reply.steps.enumerated()), id: \.offset) { index, step in HStack(alignment: .top) { Text("\(index + 1)").font(.caption.bold()).frame(width: 26, height: 26).background(Color.guiltlessMint, in: Circle()); Text(step) } }; ForEach(reply.limitations, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) } }
                    if let error { Text(error).foregroundStyle(.red) }
                }.padding()
            }.background(Color.guiltlessCanvas).navigationTitle("Guiltless Guide").toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }.presentationDetents([.medium, .large])
    }

    private func ask() async {
        loading = true; error = nil
        do {
            let request = HelperRequest(message: message, screen: "product_detail", productID: store.selectedProduct.productID, bagProductIDs: store.bag.compactMap(\.productID), goal: store.goal, allergies: store.profile?.allergies ?? [], scoreSource: "agent_catalog", userID: store.userID)
            reply = try await APIClient.shared.post("helper/chat", body: request)
        } catch { self.error = error.localizedDescription }
        loading = false
    }
}
