import Foundation

struct Product: Codable, Identifiable, Hashable {
    var productID: String?
    var name: String
    var brand: String
    var category: String
    var nutrition: [String: Double]
    var ingredients: [String]
    var baseScore: Int? = nil

    var id: String { productID ?? "\(brand)-\(name)" }
    var protein: Double { nutrition["protein_g"] ?? 0 }
    var sugar: Double { nutrition["sugar_g"] ?? 0 }
    var fiber: Double { nutrition["fiber_g"] ?? 0 }
    var calories: Double { nutrition["calories"] ?? 0 }
    var carbs: Double { nutrition["carbs_g"] ?? 0 }
    var fat: Double { nutrition["fat_g"] ?? 0 }

    enum CodingKeys: String, CodingKey {
        case productID = "product_id", name, brand, category, nutrition, ingredients
        case baseScore = "base_score"
    }

    static let yogurt = Product(productID: "demo-yogurt", name: "Plain Greek Yogurt", brand: "Daily Cultures", category: "Yogurt", nutrition: ["calories": 120, "protein_g": 17, "fiber_g": 0, "sugar_g": 5, "sodium_mg": 65], ingredients: ["cultured milk"])
    static let snackBar = Product(productID: "demo-bar", name: "Frosted Snack Bar", brand: "Quick Bite", category: "Snack bar", nutrition: ["calories": 260, "protein_g": 3, "fiber_g": 1, "sugar_g": 24, "sodium_mg": 310], ingredients: ["oats", "corn syrup", "artificial flavor"])
    static let chickpeas = Product(productID: "demo-chickpeas", name: "Roasted Chickpea Bites", brand: "Good Crunch", category: "Savory snack", nutrition: ["calories": 180, "protein_g": 9, "fiber_g": 6, "sugar_g": 2, "sodium_mg": 220], ingredients: ["chickpeas", "olive oil", "spices"])
    static let demos = [yogurt, snackBar, chickpeas]

    static let catalog: [Product] = [
        Product(productID: "demo-yogurt", name: "Plain Greek Yogurt", brand: "Daily Cultures", category: "Breakfast", nutrition: ["calories": 120, "protein_g": 17, "carbs_g": 8, "fat_g": 2, "fiber_g": 0, "sugar_g": 5, "sodium_mg": 65], ingredients: ["cultured milk"], baseScore: 91),
        Product(productID: "demo-oats", name: "Protein Overnight Oats", brand: "Morning Good", category: "Breakfast", nutrition: ["calories": 310, "protein_g": 20, "carbs_g": 42, "fat_g": 8, "fiber_g": 7, "sugar_g": 8, "sodium_mg": 180], ingredients: ["oats", "milk", "chia seeds", "whey protein"], baseScore: 88),
        Product(productID: "demo-eggs", name: "Free Range Eggs", brand: "Farm Table", category: "Breakfast", nutrition: ["calories": 140, "protein_g": 12, "carbs_g": 1, "fat_g": 10, "fiber_g": 0, "sugar_g": 0, "sodium_mg": 140], ingredients: ["eggs"], baseScore: 82),
        Product(productID: "demo-chickpeas", name: "Roasted Chickpea Bites", brand: "Good Crunch", category: "Snacks", nutrition: ["calories": 180, "protein_g": 9, "carbs_g": 24, "fat_g": 6, "fiber_g": 6, "sugar_g": 2, "sodium_mg": 220], ingredients: ["chickpeas", "olive oil", "spices"], baseScore: 89),
        Product(productID: "demo-bar", name: "Frosted Snack Bar", brand: "Quick Bite", category: "Snacks", nutrition: ["calories": 260, "protein_g": 3, "carbs_g": 44, "fat_g": 8, "fiber_g": 1, "sugar_g": 24, "sodium_mg": 310], ingredients: ["oats", "corn syrup", "artificial flavor"], baseScore: 30),
        Product(productID: "demo-almonds", name: "Sea Salt Almonds", brand: "Simple Pantry", category: "Snacks", nutrition: ["calories": 170, "protein_g": 6, "carbs_g": 6, "fat_g": 15, "fiber_g": 4, "sugar_g": 1, "sodium_mg": 95], ingredients: ["almonds", "sea salt"], baseScore: 78),
        Product(productID: "demo-chicken", name: "Grilled Chicken Breast", brand: "Fresh Kitchen", category: "Protein", nutrition: ["calories": 220, "protein_g": 42, "carbs_g": 0, "fat_g": 5, "fiber_g": 0, "sugar_g": 0, "sodium_mg": 360], ingredients: ["chicken breast", "olive oil", "seasoning"], baseScore: 90),
        Product(productID: "demo-tofu", name: "Organic Firm Tofu", brand: "Green Table", category: "Protein", nutrition: ["calories": 160, "protein_g": 18, "carbs_g": 5, "fat_g": 9, "fiber_g": 3, "sugar_g": 1, "sodium_mg": 25], ingredients: ["soybeans", "water", "calcium sulfate"], baseScore: 94),
        Product(productID: "demo-salmon", name: "Wild Salmon Fillet", brand: "Blue Coast", category: "Protein", nutrition: ["calories": 280, "protein_g": 39, "carbs_g": 0, "fat_g": 13, "fiber_g": 0, "sugar_g": 0, "sodium_mg": 90], ingredients: ["wild salmon"], baseScore: 92),
        Product(productID: "demo-broccoli", name: "Broccoli Florets", brand: "Harvest Day", category: "Produce", nutrition: ["calories": 50, "protein_g": 4, "carbs_g": 10, "fat_g": 1, "fiber_g": 5, "sugar_g": 2, "sodium_mg": 45], ingredients: ["broccoli"], baseScore: 96),
        Product(productID: "demo-berries", name: "Mixed Berries", brand: "Harvest Day", category: "Produce", nutrition: ["calories": 80, "protein_g": 1, "carbs_g": 19, "fat_g": 0, "fiber_g": 6, "sugar_g": 10, "sodium_mg": 0], ingredients: ["strawberries", "blueberries", "raspberries"], baseScore: 90),
        Product(productID: "demo-rice", name: "Brown Rice Bowl", brand: "Whole Grain Co.", category: "Pantry", nutrition: ["calories": 240, "protein_g": 5, "carbs_g": 50, "fat_g": 2, "fiber_g": 4, "sugar_g": 1, "sodium_mg": 10], ingredients: ["brown rice", "water"], baseScore: 76)
    ]
}

struct DailyLogEntry: Codable, Identifiable {
    let id: UUID
    let product: Product
    let servings: Double
    let meal: String
    let loggedAt: Date
    var calories: Double { product.calories * servings }
    var protein: Double { product.protein * servings }
    var carbs: Double { product.carbs * servings }
    var fat: Double { product.fat * servings }
}

struct ExplainRequest: Codable { let product: Product; let goal: String }
struct ExplainProductSummary: Codable { let name: String; let brand: String?; let category: String? }
struct ExplainResponse: Codable {
    let product: ExplainProductSummary
    let score: Int
    let verdict: String
    let positives: [String]
    let cautions: [String]
    let goal: String
    let goalFit: [String]
    let summary: String
    let recommendedActions: [String]
    enum CodingKeys: String, CodingKey {
        case product, score, verdict, positives, cautions, goal, summary
        case goalFit = "goal_fit"
        case recommendedActions = "recommended_actions"
    }
}

struct CompareRequest: Codable { let products: [Product]; let goal: String }
struct CompareResponse: Codable { let goal: String; let products: [ExplainResponse]; let recommendation: String }
struct BagOptimizeRequest: Codable { let items: [Product]; let goal: String }
struct BagSwap: Codable, Identifiable {
    let replace: String; let with: String; let currentScore: Int; let newScore: Int; let scoreGain: Int; let reason: String
    var id: String { "\(replace)-\(with)" }
    enum CodingKeys: String, CodingKey { case replace, with, reason; case currentScore = "current_score"; case newScore = "new_score"; case scoreGain = "score_gain" }
}
struct BagOptimizeResponse: Codable {
    let currentScore: Int; let projectedScore: Int; let scoreGain: Int; let swaps: [BagSwap]; let summary: String
    enum CodingKeys: String, CodingKey { case swaps, summary; case currentScore = "current_score"; case projectedScore = "projected_score"; case scoreGain = "score_gain" }
}

struct CopilotRequest: Codable { let message: String; let context: CopilotContext; let userID: String; let loadMemory: Bool
    enum CodingKeys: String, CodingKey { case message, context; case userID = "user_id"; case loadMemory = "load_memory" }
}
struct CopilotContext: Codable { let product: Product; let goal: String; let bag: [Product]; let screen: String }
struct CopilotResponse: Codable { let intent: String; let response: String; let suggestedActions: [String]
    enum CodingKeys: String, CodingKey { case intent, response; case suggestedActions = "suggested_actions" }
}

struct HelperRequest: Codable {
    let message: String; let screen: String; let productID: String?; let bagProductIDs: [String]; let goal: String; let allergies: [String]; let scoreSource: String; let userID: String
    enum CodingKeys: String, CodingKey { case message, screen, goal, allergies; case productID = "product_id"; case bagProductIDs = "bag_product_ids"; case scoreSource = "score_source"; case userID = "user_id" }
}
struct HelperResponse: Codable { let intent: String; let response: String; let steps: [String]; let limitations: [String] }

struct Profile: Codable {
    let userID: String; var goal: String; var diet: String; var allergies: [String]; var dislikedFoods: [String]; var budget: String; var preferredStore: String; var trainingDays: Int; var equipment: [String]; var calorieTarget: Int; let updatedAt: String
    enum CodingKeys: String, CodingKey { case goal, diet, allergies, budget, equipment; case userID = "user_id"; case dislikedFoods = "disliked_foods"; case preferredStore = "preferred_store"; case trainingDays = "training_days"; case calorieTarget = "calorie_target"; case updatedAt = "updated_at" }
}
struct ProfileUpdate: Codable { let goal: String; let diet: String; let allergies: [String]; let dislikedFoods: [String]; let budget: String; let preferredStore: String; let trainingDays: Int; let equipment: [String]; let calorieTarget: Int
    enum CodingKeys: String, CodingKey { case goal, diet, allergies, budget, equipment; case dislikedFoods = "disliked_foods"; case preferredStore = "preferred_store"; case trainingDays = "training_days"; case calorieTarget = "calorie_target" }
}
struct BagAddRequest: Codable { let product: Product; let quantity: Int }
struct BagItem: Codable, Identifiable { let id: String; let productID: String?; let product: Product; let quantity: Int; let createdAt: String
    enum CodingKeys: String, CodingKey { case id, product, quantity; case productID = "product_id"; case createdAt = "created_at" }
}
struct BagResponse: Codable { let userID: String; let items: [BagItem]; let count: Int
    enum CodingKeys: String, CodingKey { case items, count; case userID = "user_id" }
}
struct BagAddResponse: Codable { let userID: String; let items: [BagItem]
    enum CodingKeys: String, CodingKey { case items; case userID = "user_id" }
}

struct EmptyResponse: Codable {}
