import SwiftUI

struct ProductCatalogView: View {
    @EnvironmentObject private var store: AppStore
    @State private var search = ""
    @State private var category = "All"
    private var categories: [String] { ["All"] + Array(Set(Product.catalog.map(\.category))).sorted() }
    private var products: [Product] {
        Product.catalog.filter { product in
            (category == "All" || product.category == category) &&
            (search.isEmpty || product.name.localizedCaseInsensitiveContains(search) || product.brand.localizedCaseInsensitiveContains(search))
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                BrandHeader(eyebrow: "Guiltless groceries", title: "Product catalog", subtitle: "Browse everyday foods, check the health score, and log or add them to your bag.")
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack { ForEach(categories, id: \.self) { item in Button(item) { category = item }.buttonStyle(CategoryButtonStyle(selected: category == item)) } }
                }
                LazyVStack(spacing: 12) {
                    ForEach(products) { product in NavigationLink { CatalogProductDetail(product: product) } label: { CatalogProductRow(product: product) }.buttonStyle(.plain) }
                }
            }.padding()
        }
        .background(Color.guiltlessCanvas)
        .navigationTitle("Catalog")
        .searchable(text: $search, prompt: "Search foods and brands")
    }
}

private struct CatalogProductRow: View {
    let product: Product
    var body: some View {
        HStack(spacing: 14) {
            ZStack { RoundedRectangle(cornerRadius: 15).fill(Color.guiltlessMint); Image(systemName: icon).font(.title2).foregroundStyle(Color.guiltlessGreen) }.frame(width: 58, height: 58)
            VStack(alignment: .leading, spacing: 4) { Text(product.name).font(.headline); Text("\(product.brand) · \(Int(product.calories)) cal").font(.caption).foregroundStyle(.secondary); Text("P \(Int(product.protein))g  ·  C \(Int(product.carbs))g  ·  F \(Int(product.fat))g").font(.caption2).foregroundStyle(.secondary) }
            Spacer()
            if let score = product.baseScore { ScoreBadge(score: score).scaleEffect(0.72).frame(width: 45) }
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
        }.cardStyle()
    }
    private var icon: String { switch product.category { case "Breakfast": return "sunrise.fill"; case "Snacks": return "takeoutbag.and.cup.and.straw.fill"; case "Protein": return "figure.strengthtraining.traditional"; case "Produce": return "leaf.fill"; default: return "basket.fill" } }
}

struct CatalogProductDetail: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss
    let product: Product
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack { VStack(alignment: .leading) { Text(product.brand.uppercased()).font(.caption.bold()).foregroundStyle(.green); Text(product.name).font(.largeTitle.bold()); Text(product.category).foregroundStyle(.secondary) }; Spacer(); if let score = product.baseScore { ScoreBadge(score: score) } }
                HStack { nutrition("Calories", product.calories, ""); nutrition("Protein", product.protein, "g"); nutrition("Carbs", product.carbs, "g"); nutrition("Fat", product.fat, "g") }.cardStyle()
                VStack(alignment: .leading, spacing: 8) { Text("Ingredients").font(.headline); Text(product.ingredients.joined(separator: ", ").capitalized).foregroundStyle(.secondary) }.cardStyle()
                Button("Use in decision engine") { store.selectedProduct = product; Task { await store.explain() }; dismiss() }.buttonStyle(GuiltlessButtonStyle())
                HStack { Button("Log 1 serving") { store.log(product) }.buttonStyle(.borderedProminent); Button("Add to bag") { Task { await store.addToBag(product) } }.buttonStyle(.bordered) }
            }.padding()
        }.background(Color.guiltlessCanvas).navigationTitle("Product details").navigationBarTitleDisplayMode(.inline)
    }
    private func nutrition(_ label: String, _ value: Double, _ unit: String) -> some View { VStack { Text("\(Int(value))\(unit)").bold(); Text(label).font(.caption2).foregroundStyle(.secondary) }.frame(maxWidth: .infinity) }
}

struct DailyTrackerView: View {
    @EnvironmentObject private var store: AppStore
    var progress: Double { min(1, store.caloriesConsumed / Double(max(1, store.calorieTarget))) }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                BrandHeader(eyebrow: Date.now.formatted(date: .complete, time: .omitted), title: "My Tracker", subtitle: "See what you have eaten today and what remains for your target.")
                HStack(spacing: 22) {
                    ZStack { Circle().stroke(Color.guiltlessMint, lineWidth: 16); Circle().trim(from: 0, to: progress).stroke(Color.guiltlessGreen, style: StrokeStyle(lineWidth: 16, lineCap: .round)).rotationEffect(.degrees(-90)); VStack { Text("\(Int(store.caloriesConsumed))").font(.title.bold()); Text("eaten").font(.caption).foregroundStyle(.secondary) } }.frame(width: 145, height: 145)
                    VStack(alignment: .leading, spacing: 12) { trackerMetric("Daily target", store.calorieTarget, "kcal"); trackerMetric("Remaining", Int(store.caloriesRemaining), "kcal"); Text(store.caloriesRemaining > 0 ? "You can still eat \(Int(store.caloriesRemaining)) calories today." : "You have reached today’s calorie target.").font(.caption).foregroundStyle(store.caloriesRemaining > 0 ? Color.secondary : Color.orange) }
                }.cardStyle()
                HStack { macro("Protein", store.proteinConsumed, "P"); macro("Carbs", store.carbsConsumed, "C"); macro("Fat", store.fatConsumed, "F") }
                VStack(alignment: .leading, spacing: 12) { Text("Quick add").font(.headline); ScrollView(.horizontal, showsIndicators: false) { HStack { ForEach(Array(Product.catalog.prefix(6))) { product in Button { store.log(product) } label: { VStack(alignment: .leading) { Text(product.name).font(.caption.bold()).lineLimit(2); Text("+\(Int(product.calories)) cal").font(.caption2).foregroundStyle(.secondary) }.frame(width: 105, alignment: .leading).padding().background(Color.guiltlessMint, in: RoundedRectangle(cornerRadius: 14)) }.buttonStyle(.plain) } } } }.cardStyle()
                VStack(alignment: .leading, spacing: 12) {
                    Text("Today’s food").font(.headline)
                    if store.dailyEntries.isEmpty { ContentUnavailableView("Nothing logged yet", systemImage: "fork.knife", description: Text("Quick-add a food or log one from the catalog.")) }
                    ForEach(store.dailyEntries) { entry in HStack { VStack(alignment: .leading) { Text(entry.product.name).bold(); Text("\(entry.meal) · \(entry.servings.formatted()) serving").font(.caption).foregroundStyle(.secondary) }; Spacer(); Text("\(Int(entry.calories)) cal").fontWeight(.semibold); Button(role: .destructive) { if let index = store.dailyEntries.firstIndex(where: { $0.id == entry.id }) { store.removeLogEntries(at: IndexSet(integer: index)) } } label: { Image(systemName: "trash") } }.padding(.vertical, 6); Divider() }
                }.cardStyle()
            }.padding()
        }.background(Color.guiltlessCanvas).navigationTitle("Tracker").navigationBarTitleDisplayMode(.inline)
    }
    private func trackerMetric(_ label: String, _ value: Int, _ unit: String) -> some View { VStack(alignment: .leading) { Text(label).font(.caption).foregroundStyle(.secondary); Text("\(value) \(unit)").font(.title3.bold()) } }
    private func macro(_ label: String, _ value: Double, _ short: String) -> some View { VStack(spacing: 5) { Text(short).font(.caption.bold()).foregroundStyle(.green); Text("\(Int(value))g").font(.title3.bold()); Text(label).font(.caption2).foregroundStyle(.secondary) }.frame(maxWidth: .infinity).cardStyle() }
}

private struct CategoryButtonStyle: ButtonStyle {
    let selected: Bool
    func makeBody(configuration: Configuration) -> some View { configuration.label.font(.caption.bold()).padding(.horizontal, 15).padding(.vertical, 10).background(selected ? Color.guiltlessGreen : .white, in: Capsule()).foregroundStyle(selected ? .white : Color.guiltlessGreen).overlay(Capsule().stroke(Color.guiltlessGreen.opacity(0.18))) }
}
