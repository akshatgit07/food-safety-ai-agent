import Foundation

enum APIError: LocalizedError {
    case invalidResponse
    case server(Int, String)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "The server returned an invalid response."
        case let .server(code, message): return "Server error \(code): \(message)"
        case let .decoding(error): return "Could not read the response: \(error.localizedDescription)"
        }
    }
}

struct APIClient {
    static let shared = APIClient()

    static var baseURL: URL {
        if let override = ProcessInfo.processInfo.environment["GUILTLESS_API_URL"], let url = URL(string: override) { return url }
        return URL(string: "https://food-safety-ai-agent.onrender.com")!
    }

    func get<Response: Decodable>(_ path: String, as: Response.Type = Response.self) async throws -> Response {
        try await send(path, method: "GET", body: Optional<String>.none, as: Response.self)
    }

    func post<Body: Encodable, Response: Decodable>(_ path: String, body: Body, as: Response.Type = Response.self) async throws -> Response {
        try await send(path, method: "POST", body: body, as: Response.self)
    }

    func put<Body: Encodable, Response: Decodable>(_ path: String, body: Body, as: Response.Type = Response.self) async throws -> Response {
        try await send(path, method: "PUT", body: body, as: Response.self)
    }

    private func send<Body: Encodable, Response: Decodable>(_ path: String, method: String, body: Body?, as: Response.Type) async throws -> Response {
        var request = URLRequest(url: Self.baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body { request.httpBody = try JSONEncoder().encode(body) }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard 200..<300 ~= http.statusCode else {
            let message = String(data: data, encoding: .utf8) ?? "Request failed"
            throw APIError.server(http.statusCode, message)
        }
        do { return try JSONDecoder().decode(Response.self, from: data) }
        catch { throw APIError.decoding(error) }
    }
}
