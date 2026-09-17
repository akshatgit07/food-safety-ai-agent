import SwiftUI

struct DecisionFlowView: View {
    @EnvironmentObject private var store: AppStore
    @State private var step = 0
    @State private var copilotMessage = "Why is this score low?"
    private let labels = ["Explain", "Compare", "Optimize", "Copilot"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                BrandHeader(eyebrow: "Food Label Decision Engine", title: "Turn a label into a decision", subtitle: "Explain scores, compare alternatives, optimize the bag, and ask your context-aware copilot.")

                Picker("Workflow step", selection: $step) {
                    ForEach(labels.indices, id: \.self) { Text("\($0 + 1) \(labels[$0])").tag($0) }
                }.pickerStyle(.segmented)

                VStack(alignment: .leading, spacing: 12) {
                    Text("CURRENT PRODUCT").font(.caption2.bold()).foregroundStyle(.secondary)
                    Picker("Product", selection: $store.selectedProduct) {
                        ForEach(Product.demos) { Text($0.name).tag($0) }
                    }
                    TextField("Shared nutrition goal", text: $store.goal).textFieldStyle(.roundedBorder)
                }.cardStyle()

                Group {
                    switch step {
                    case 0: ExplainView()
                    case 1: CompareView()
                    case 2: OptimizeView()
                    default: CopilotView(message: $copilotMessage)
                    }
                }
            }.padding()
        }
        .background(Color.guiltlessCanvas)
        .navigationTitle("Guiltless")
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: store.selectedProduct) { _, _ in Task { await store.explain() } }
    }
}

private struct ExplainView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { VStack(alignment: .leading) { Text("01 · PRODUCT EXPLAINABILITY").font(.caption.bold()).foregroundStyle(.green); Text(store.explanation?.verdict ?? "Scoring…").font(.title2.bold()) }; Spacer(); if let score = store.explanation?.score { ScoreBadge(score: score) } }
            Text(store.explanation?.summary ?? "Loading the nutrition-based Guiltless score.").foregroundStyle(.secondary)
            if let result = store.explanation {
                LabelList(title: "Strengths", items: result.positives, color: .green)
                LabelList(title: "Cautions", items: result.cautions, color: .orange)
            }
            Button("Explain this product") { Task { await store.explain() } }.buttonStyle(GuiltlessButtonStyle())
            Button("Add to saved bag") { Task { await store.addSelectedToBag() } }.buttonStyle(.bordered)
        }.cardStyle()
    }
}

private struct CompareView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("02 · PRODUCT COMPARISON").font(.caption.bold()).foregroundStyle(.green)
            if let result = store.comparison {
                ForEach(result.products, id: \.product.name) { item in HStack { Text(item.product.name).fontWeight(.semibold); Spacer(); ScoreBadge(score: item.score).scaleEffect(0.78) } }
                Text(result.recommendation).padding().background(Color.guiltlessMint, in: RoundedRectangle(cornerRadius: 14))
            } else { ContentUnavailableView("Compare two choices", systemImage: "arrow.left.arrow.right", description: Text("Use the same goal and serving basis.")) }
            Button("Compare alternatives") { Task { await store.compare() } }.buttonStyle(GuiltlessButtonStyle())
        }.cardStyle()
    }
}

private struct OptimizeView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("03 · BAG OPTIMIZATION").font(.caption.bold()).foregroundStyle(.green)
            if let result = store.optimization {
                HStack { metric("Current", result.currentScore); metric("Optimized", result.projectedScore); metric("Gain", result.scoreGain) }
                ForEach(result.swaps) { swap in VStack(alignment: .leading) { Text("\(swap.replace) → \(swap.with)").bold(); Text("+\(swap.scoreGain) points").font(.caption).foregroundStyle(.green) }.padding().background(Color.guiltlessMint, in: RoundedRectangle(cornerRadius: 14)) }
            } else { ContentUnavailableView("Preview healthier swaps", systemImage: "bag.badge.plus", description: Text("The app will show before-and-after scores.")) }
            Button("Optimize my bag") { Task { await store.optimize() } }.buttonStyle(GuiltlessButtonStyle())
        }.cardStyle()
    }
    private func metric(_ title: String, _ value: Int) -> some View { VStack { Text("\(value)").font(.title.bold()); Text(title).font(.caption).foregroundStyle(.secondary) }.frame(maxWidth: .infinity).padding().background(Color.guiltlessCanvas, in: RoundedRectangle(cornerRadius: 12)) }
}

private struct CopilotView: View {
    @EnvironmentObject private var store: AppStore
    @Binding var message: String
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("04 · ASK GUILTLESS").font(.caption.bold()).foregroundStyle(.green)
            Text("\(store.selectedProduct.name) · Goal: \(store.goal) · \(store.bag.count) bag items").font(.caption).padding().frame(maxWidth: .infinity, alignment: .leading).background(Color.guiltlessMint, in: RoundedRectangle(cornerRadius: 12))
            TextField("Ask about this decision", text: $message, axis: .vertical).textFieldStyle(.roundedBorder).lineLimit(3...6)
            Button("Ask the copilot") { Task { await store.askCopilot(message) } }.buttonStyle(GuiltlessButtonStyle())
            if let reply = store.copilot { Text(reply.intent.replacingOccurrences(of: "_", with: " ").uppercased()).font(.caption2.bold()).foregroundStyle(.green); Text(reply.response) }
        }.cardStyle()
    }
}

private struct LabelList: View {
    let title: String; let items: [String]; let color: Color
    var body: some View { if !items.isEmpty { VStack(alignment: .leading, spacing: 6) { Text(title).font(.caption.bold()); ForEach(items, id: \.self) { Label($0, systemImage: "circle.fill").font(.subheadline).foregroundStyle(color) } } } }
}

struct GuiltlessButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { configuration.label.fontWeight(.bold).frame(maxWidth: .infinity).padding().background(Color.guiltlessGreen.opacity(configuration.isPressed ? 0.8 : 1), in: RoundedRectangle(cornerRadius: 14)).foregroundStyle(.white) }
}

extension View {
    func cardStyle() -> some View { self.padding(18).background(.white, in: RoundedRectangle(cornerRadius: 20)).overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.black.opacity(0.06))).shadow(color: .black.opacity(0.04), radius: 12, y: 5) }
}
