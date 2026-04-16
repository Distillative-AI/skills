// SettingsView — in-app sheet that lets the user point Ralph VC at their
// Mac's IP and paste the bearer token printed by setup.sh. Both values
// are written to the Keychain via Settings.save(...).
//
// Wired into ChatView via a gear button in the navigation bar (see
// ChatView.swift). Every interactive control exposes accessibility
// identifiers so the BDD virtual user agent can drive it.
//
// Authored by Chase Eddies <source@distillative.ai>.

import SwiftUI

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var endpoint: String = Settings.load().endpoint
    @State private var token:    String = Settings.load().bearerToken
    @State private var savedFlash: Bool = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("http://192.168.1.42:7878", text: $endpoint)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .accessibilityIdentifier("settings-endpoint-field")
                } header: {
                    Text("Mac orchestrator endpoint")
                } footer: {
                    Text("Use http://<your-mac-ip>:7878 — both must be on the same Wi-Fi.")
                }

                Section {
                    SecureField("Paste from setup.sh output", text: $token)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityIdentifier("settings-token-field")
                } header: {
                    Text("Bearer token")
                } footer: {
                    Text("Stored in the iPhone Keychain. Mint a new one each session by re-running setup.sh.")
                }

                Section {
                    Button("Save to Keychain") { save() }
                        .buttonStyle(.borderedProminent)
                        .accessibilityIdentifier("settings-save-button")
                    if savedFlash {
                        Text("Saved.").foregroundStyle(.green)
                    }
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                        .accessibilityIdentifier("settings-done-button")
                }
            }
        }
    }

    private func save() {
        Settings.save(endpoint: endpoint.trimmingCharacters(in: .whitespacesAndNewlines),
                      bearerToken: token.trimmingCharacters(in: .whitespacesAndNewlines))
        savedFlash = true
        Task {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            await MainActor.run { savedFlash = false }
        }
    }
}

#Preview {
    SettingsView()
}
