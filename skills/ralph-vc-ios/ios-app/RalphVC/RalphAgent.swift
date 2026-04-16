// RalphAgent — POSTs prompts to the macOS-side orchestrator from the
// `ios-development` skill. The bearer token lives in the keychain.
//
// Authored by Chase Eddies <source@distillative.ai>.

import Foundation

actor RalphAgent {
    private let voice: RalphVoice
    private let settings: Settings

    init(voice: RalphVoice, settings: Settings) {
        self.voice = voice
        self.settings = settings
    }

    func ask(_ prompt: String) async -> String {
        guard let url = URL(string: settings.endpoint + "/v1/orchestrate") else {
            return "Ralph misconfigured: bad endpoint."
        }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.timeoutInterval = 60
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer \(settings.bearerToken)", forHTTPHeaderField: "Authorization")
        req.httpBody = try? JSONSerialization.data(withJSONObject: [
            "prompt": prompt,
            "max_turns": 6,
        ])

        do {
            let (data, response) = try await URLSession.shared.data(for: req)
            if let http = response as? HTTPURLResponse, http.statusCode != 200 {
                return "Ralph couldn't reach the orchestrator (HTTP \(http.statusCode))."
            }
            struct Reply: Decodable {
                let final_text: String
            }
            return try JSONDecoder().decode(Reply.self, from: data).final_text
        } catch {
            return "Ralph couldn't reach the orchestrator: \(error.localizedDescription)"
        }
    }
}
