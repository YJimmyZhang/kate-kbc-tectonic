// APIClient.swift
// Talks to the Kate backend over HTTPS. The session token lives in the
// Keychain, never in UserDefaults or files.

import Foundation
import Security

// MARK: Model (mirrors GET /v1/recommendations/{rid})
struct Recommendation: Decodable {
    struct Pathway: Decodable {
        let number: Int
        let name: String
        let product: String
        let risk: Int?
        let keepInMind: String
    }
    let pathway: Pathway
    let title: String
    let body: String
    let cta: String
    let reasons: [String]
    let tone: String
    let riskLimit: Int
}

enum APIError: Error { case notLoggedIn, notFound, server }

final class APIClient {
    static let shared = APIClient()

    // SECURITY: HTTPS only. App Transport Security blocks plain HTTP by default;
    // do NOT add NSAllowsArbitraryLoads to Info.plist.
    private let baseURL = URL(string: "https://kate-api.example.com")!
    private let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral     // no disk cache of financial data
        config.urlCache = nil
        return URLSession(configuration: config)
    }()
    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    func registerDevice(token: String) async throws {
        var req = try authorizedRequest(path: "/v1/devices", method: "POST")
        req.httpBody = try JSONEncoder().encode(["device_token": token])
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        _ = try await send(req)
    }

    func logout() async {
        if let req = try? authorizedRequest(path: "/v1/devices", method: "DELETE") {
            _ = try? await send(req)                      // stop pushes to this phone
        }
        Keychain.delete("session")
    }

    func recommendation(id: String) async throws -> Recommendation {
        if id.hasPrefix("demo-") { return .demoLotte }    // offline demo for the jury
        let req = try authorizedRequest(path: "/v1/recommendations/\(id)", method: "GET")
        return try decoder.decode(Recommendation.self, from: try await send(req))
    }

    // MARK: helpers
    private func authorizedRequest(path: String, method: String) throws -> URLRequest {
        guard let token = Keychain.read("session") else { throw APIError.notLoggedIn }
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        return req
    }

    private func send(_ req: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: req)
        switch (response as? HTTPURLResponse)?.statusCode ?? 0 {
        case 200..<300: return data
        case 401: Keychain.delete("session"); throw APIError.notLoggedIn
        case 404: throw APIError.notFound
        default: throw APIError.server
        }
    }
}

// MARK: Keychain: encrypted, only readable while the phone is unlocked, never synced.
enum Keychain {
    static func save(_ value: String, for key: String) {
        delete(key)
        SecItemAdd([
            kSecClass: kSecClassGenericPassword,
            kSecAttrAccount: key,
            kSecValueData: Data(value.utf8),
            kSecAttrAccessible: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ] as CFDictionary, nil)
    }

    static func read(_ key: String) -> String? {
        var out: AnyObject?
        let status = SecItemCopyMatching([
            kSecClass: kSecClassGenericPassword,
            kSecAttrAccount: key,
            kSecReturnData: true,
            kSecMatchLimit: kSecMatchLimitOne
        ] as CFDictionary, &out)
        guard status == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func delete(_ key: String) {
        SecItemDelete([kSecClass: kSecClassGenericPassword, kSecAttrAccount: key] as CFDictionary)
    }
}

// MARK: Sample data identical to the web demo (synthetic customer).
extension Recommendation {
    static let demoLotte = Recommendation(
        pathway: .init(number: 4, name: "Global equities", product: "Diversified equity fund",
                       risk: 4, keepInMind: "Value can fall; check the specific fund's holdings."),
        title: "Nice raise! Let some of it work for you",
        body: "Put 50 euros a month into a diversified equity fund and 80 euros extra into savings?",
        cta: "Set it up in 2 taps",
        reasons: ["Your salary went up",
                  "Your risk capacity is now 51 of 100",
                  "Your risk limit is 4 of 7, so an equity fund fits"],
        tone: "casual",
        riskLimit: 4
    )
}
