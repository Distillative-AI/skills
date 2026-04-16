// Settings — endpoint URL + bearer token. Both are stored in the iPhone
// Keychain so they survive app reinstalls and never land in a backup
// in plaintext.
//
// Authored by Chase Eddies <source@distillative.ai>.

import Foundation
import Security

struct Settings: Sendable {
    static let endpointDefault = "http://127.0.0.1:7878"

    let endpoint: String
    let bearerToken: String

    static func load() -> Settings {
        let endpoint = Keychain.read(service: "ralph-vc-ios", account: "endpoint")
            ?? ProcessInfo.processInfo.environment["RALPHVC_ENDPOINT"]
            ?? Bundle.main.object(forInfoDictionaryKey: "RALPHVC_ENDPOINT") as? String
            ?? endpointDefault
        let token = Keychain.read(service: "ralph-vc-ios", account: "bearer")
            ?? ProcessInfo.processInfo.environment["RALPHVC_BEARER"]
            ?? "dev-token"
        return Settings(endpoint: endpoint, bearerToken: token)
    }

    static func save(endpoint: String, bearerToken: String) {
        Keychain.write(service: "ralph-vc-ios", account: "endpoint", value: endpoint)
        Keychain.write(service: "ralph-vc-ios", account: "bearer",   value: bearerToken)
    }
}

enum Keychain {
    static func read(service: String, account: String) -> String? {
        let query: [String: Any] = [
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

    @discardableResult
    static func write(service: String, account: String, value: String) -> Bool {
        let data = Data(value.utf8)
        // Delete any existing entry first so this is an upsert.
        let baseQuery: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(baseQuery as CFDictionary)

        var add = baseQuery
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        return SecItemAdd(add as CFDictionary, nil) == errSecSuccess
    }
}
