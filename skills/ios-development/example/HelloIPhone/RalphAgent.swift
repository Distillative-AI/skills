// RalphAgent — the in-app coding assistant persona that brokers between the
// user's voice + text input on iOS and Claude Code Cloud (accessed via the
// Anthropic API / Claude Code API). Ralph speaks back through the native
// iOS TTS pipeline using the Ralph voice when installed.
//
// This file is the iOS-side counterpart to `app/orchestrator.py`: the
// orchestrator runs on the user's macOS workspace, and Ralph runs on the
// iPhone / iPad and forwards prompts to it. The two sides share the same
// vibe-coding loop: user speaks → Ralph transcribes → Ralph forwards to
// Claude Code Cloud → response comes back → Ralph speaks the answer.
//
// Authored by Chase Eddies <source@distillative.ai>.
// Coding assistant: Claude Code Cloud.

import Foundation

@MainActor
final class RalphAgent: ObservableObject {

    /// Endpoint of the locally-running orchestrator (defaults to the dev
    /// server bundled with `app/orchestrator.py --serve`). Override at
    /// build time via the `RALPH_ENDPOINT` Info.plist key for production.
    let endpoint: URL

    @Published var lastUserUtterance: String = ""
    @Published var lastAgentReply:    String = ""
    @Published var isThinking:        Bool   = false

    private let coordinator: SpeechCoordinator

    init(coordinator: SpeechCoordinator,
         endpoint: URL = URL(string: "http://localhost:7878/v1/orchestrate")!) {
        self.coordinator = coordinator
        self.endpoint    = endpoint
    }

    /// Forward a transcribed prompt to Claude Code Cloud (via the local
    /// orchestrator) and speak the reply back through Ralph's voice.
    func ask(_ prompt: String) async {
        lastUserUtterance = prompt
        isThinking = true
        defer { isThinking = false }

        let reply = await callOrchestrator(prompt: prompt)
        lastAgentReply = reply
        coordinator.speak(reply)
    }

    private func callOrchestrator(prompt: String) async -> String {
        var req = URLRequest(url: endpoint)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONEncoder().encode(["prompt": prompt])
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            struct Reply: Decodable { let final_text: String }
            let decoded = try JSONDecoder().decode(Reply.self, from: data)
            return decoded.final_text
        } catch {
            return "Ralph couldn't reach the orchestrator: \(error.localizedDescription)"
        }
    }
}
