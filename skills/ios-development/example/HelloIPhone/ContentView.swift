// ContentView — minimal UI that exercises the TTS + STT pipeline.
//
// All controls expose `accessibilityLabel` and `accessibilityIdentifier`
// so the BDD virtual user agent can target them by label, and so VoiceOver
// users get a fully usable experience.
//
// Authored by Chase Eddies <source@distillative.ai>.

import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var session: AppSession
    @State private var draft: String = "Hello from Claude Code Cloud."

    var body: some View {
        VStack(spacing: 16) {
            Text("Vibe-coded on iOS")
                .font(.title2.bold())
                .accessibilityIdentifier("title")
                .accessibilityAddTraits(.isHeader)

            TextEditor(text: $draft)
                .frame(height: 120)
                .border(.secondary)
                .accessibilityLabel("Spoken text")
                .accessibilityIdentifier("draft")

            HStack(spacing: 12) {
                Button("Speak") { session.speak(draft) }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("Speak")

                Button(session.isListening ? "Stop" : "Listen") {
                    session.toggleListening()
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("Listen")
            }

            if !session.transcript.isEmpty {
                Text(session.transcript)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .padding(.top, 8)
                    .accessibilityIdentifier("transcript")
                    .accessibilityLabel("Live transcript: \(session.transcript)")
            }

            Spacer()
        }
        .padding()
    }
}

#Preview {
    ContentView()
        .environmentObject(AppSession())
}
