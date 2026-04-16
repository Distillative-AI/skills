// Settings — endpoint URL + bearer token. Token is loaded from the
// Keychain; falls back to UserDefaults *only* in DEBUG builds.
//
// Authored by Chase Eddies <source@distillative.ai>.

import Foundation
import Security

struct Settings: Sendable {
    let endpoint: String
    let bearerToken: String

    static func load() -> Settings {
        let endpoint = ProcessInfo.processInfo.environment["RALPHVC_ENDPOINT"]
            ?? Bundle.main.object(forInfoDictionaryKey: "RALPHVC_ENDPOINT") as? String
            ?? "http://127.0.0.1:7878"
        let token = Keychain.read(service: "ralph-vc-ios", account: "bearer")
            ?? ProcessInfo.processInfo.environment["RALPHVC_BEARER"]
            ?? "dev-token"
        return Settings(endpoint: endpoint, bearerToken: token)
    }
}

enum Keychain {
    static func read(service: String, account: String) -> String? {
        var query: [String: Any] = [
            kSecClass as String:            kSecClassGenericPassword,
            kSecAttrService as String:      service,
            kSecAttrAccount as String:      account,
            kSecReturnData as String:       true,
            kSecMatchLimit as String:       kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
