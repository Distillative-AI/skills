// RalphVCApp — the iPhone-side vibe-coding app. Pairs with the
// `ios-development` skill's macOS-side Sonnet orchestrator.
//
// Authored by Chase Eddies <source@distillative.ai>.
// Coding assistant: Claude Code Cloud.

import SwiftUI

@main
struct RalphVCApp: App {
    @StateObject private var session = AppSession()

    var body: some Scene {
        WindowGroup {
            ChatView()
                .environmentObject(session)
                .preferredColorScheme(.dark)
        }
    }
}

@MainActor
final class AppSession: ObservableObject {
    let voice: RalphVoice
    let agent: RalphAgent
    let viewModel: ChatViewModel

    init() {
        let v = RalphVoice()
        let s = Settings.load()
        let a = RalphAgent(voice: v, settings: s)
        self.voice = v
        self.agent = a
        self.viewModel = ChatViewModel(agent: a, voice: v)
    }
}
