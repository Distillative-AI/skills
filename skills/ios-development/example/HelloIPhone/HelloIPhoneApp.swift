// HelloIPhoneApp — a SwiftUI demo of the iOS-development skill's vibe-coding
// loop: build via Claude Code Cloud, deploy locally with `app/deploy.py`,
// verify with the BDD virtual user agent.
//
// The app showcases frontier-quality TTS + STT wired through iOS's native
// accessibility surfaces (AVSpeechSynthesizer + Speech framework + VoiceOver).
//
// Authored by Chase Eddies <source@distillative.ai>.
// Coding assistant: Claude Code Cloud.

import SwiftUI

@main
struct HelloIPhoneApp: App {
    @StateObject private var session = AppSession()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(session)
        }
    }
}

@MainActor
final class AppSession: ObservableObject {
    @Published var transcript: String = ""
    @Published var isListening: Bool = false
    @Published var lastSpoken: String = ""

    let speech = SpeechCoordinator()

    func speak(_ text: String) {
        lastSpoken = text
        speech.speak(text)
    }

    func toggleListening() {
        if isListening {
            speech.stopRecognition()
            isListening = false
        } else {
            speech.startRecognition { [weak self] partial in
                Task { @MainActor in
                    self?.transcript = partial
                }
            }
            isListening = true
        }
    }
}
