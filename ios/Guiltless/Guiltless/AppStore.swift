import Foundation

@MainActor
final class AppStore: ObservableObject {
    @Published var selectedProduct = Product.snackBar
    @Published var goal = "high protein"
    @Published var bag = Product.demos
    @Published var explanation: ExplainResponse?
    @Published var comparison: CompareResponse?
    @Published var optimization: BagOptimizeResponse?
    @Published var copilot: CopilotResponse?
    @Published var persistentBag: [BagItem] = []
    @Published var profile: Profile?
    @Published var loading = false
    @Published var error: String?
    @Published var guidePresented = false
    @Published var dailyEntries: [DailyLogEntry] = []

    let userID = "demo-user"
    private var trackerKey: String { "guiltless.daily-log.\(Date.now.formatted(.iso8601.year().month().day()))" }
    var calorieTarget: Int { profile?.calorieTarget ?? 2200 }
    var caloriesConsumed: Double { dailyEntries.reduce(0) { $0 + $1.calories } }
    var caloriesRemaining: Double { max(0, Double(calorieTarget) - caloriesConsumed) }
    var proteinConsumed: Double { dailyEntries.reduce(0) { $0 + $1.protein } }
    var carbsConsumed: Double { dailyEntries.reduce(0) { $0 + $1.carbs } }
    var fatConsumed: Double { dailyEntries.reduce(0) { $0 + $1.fat } }

    func bootstrap() async {
        loadDailyLog()
        async let score: Void = explain()
        async let memory: Void = loadMemory()
        _ = await (score, memory)
    }

    func perform(_ work: () async throws -> Void) async {
        loading = true; error = nil
        do { try await work() } catch { self.error = error.localizedDescription }
        loading = false
    }

    func explain() async {
        await perform { self.explanation = try await APIClient.shared.post("product/explain", body: ExplainRequest(product: self.selectedProduct, goal: self.goal)) }
    }

    func compare() async {
        let alternative = selectedProduct.id == Product.chickpeas.id ? Product.yogurt : Product.chickpeas
        await perform { self.comparison = try await APIClient.shared.post("product/compare", body: CompareRequest(products: [self.selectedProduct, alternative], goal: self.goal)) }
    }

    func optimize() async {
        await perform { self.optimization = try await APIClient.shared.post("bag/optimize", body: BagOptimizeRequest(items: self.bag, goal: self.goal)) }
    }

    func askCopilot(_ message: String) async {
        let context = CopilotContext(product: selectedProduct, goal: goal, bag: bag, screen: "ios_decision_flow")
        await perform { self.copilot = try await APIClient.shared.post("copilot/chat", body: CopilotRequest(message: message, context: context, userID: self.userID, loadMemory: true)) }
    }

    func loadMemory() async {
        do {
            async let loadedProfile: Profile = APIClient.shared.get("profile/\(userID)")
            async let loadedBag: BagResponse = APIClient.shared.get("bag/\(userID)")
            profile = try await loadedProfile
            persistentBag = try await loadedBag.items
            if let profile { goal = profile.goal }
        } catch { self.error = error.localizedDescription }
    }

    func addSelectedToBag() async {
        await addToBag(selectedProduct)
    }

    func addToBag(_ product: Product) async {
        await perform {
            let _: BagAddResponse = try await APIClient.shared.post("bag/\(self.userID)/add", body: BagAddRequest(product: product, quantity: 1))
            let refreshed: BagResponse = try await APIClient.shared.get("bag/\(self.userID)")
            self.persistentBag = refreshed.items
        }
    }

    func log(_ product: Product, servings: Double = 1, meal: String = "Snack") {
        dailyEntries.insert(DailyLogEntry(id: UUID(), product: product, servings: servings, meal: meal, loggedAt: .now), at: 0)
        persistDailyLog()
    }

    func removeLogEntries(at offsets: IndexSet) {
        for index in offsets.sorted(by: >) { dailyEntries.remove(at: index) }
        persistDailyLog()
    }

    private func loadDailyLog() {
        guard let data = UserDefaults.standard.data(forKey: trackerKey), let values = try? JSONDecoder().decode([DailyLogEntry].self, from: data) else { return }
        dailyEntries = values
    }

    private func persistDailyLog() {
        if let data = try? JSONEncoder().encode(dailyEntries) { UserDefaults.standard.set(data, forKey: trackerKey) }
    }

    func saveProfile(goal: String, diet: String, allergies: String, store: String, calories: Int) async {
        let update = ProfileUpdate(goal: goal, diet: diet, allergies: allergies.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }, dislikedFoods: [], budget: profile?.budget ?? "flexible", preferredStore: store, trainingDays: profile?.trainingDays ?? 3, equipment: profile?.equipment ?? [], calorieTarget: calories)
        await perform { self.profile = try await APIClient.shared.put("profile/\(self.userID)", body: update) }
    }
}
