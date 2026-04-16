// ChatView — voice-first chat surface. Mic button is the primary input;
// the keyboard is the fallback. All controls expose accessibility labels
// and identifiers so the Virtual User Agent (in the `ios-development`
// skill) can drive them in BDD scenarios.
//
// Authored by Chase Eddies <source@distillative.ai>.

import SwiftUI

struct ChatView: View {
    @EnvironmentObject private var session: AppSession
    @State private var draft: String = ""
    @State private var showSettings: Bool = false
    @FocusState private var draftFocused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                transcript
                Divider()
                composer
            }
            .navigationTitle("Ralph VC")
            .accessibilityIdentifier("ralph-chat-root")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: {
                        Image(systemName: "gear")
                    }
                    .accessibilityLabel("Open settings")
                    .accessibilityIdentifier("open-settings-button")
                }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
        }
    }

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(session.viewModel.messages) { msg in
                        messageRow(msg)
                            .id(msg.id)
                    }
                    if session.viewModel.isThinking {
                        HStack {
                            ProgressView()
                            Text("Ralph is thinking…")
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal)
                    }
                }
                .padding(.vertical, 12)
            }
            .onChange(of: session.viewModel.messages.count) { _, _ in
                if let last = session.viewModel.messages.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    private func messageRow(_ msg: ChatMessage) -> some View {
        HStack(alignment: .top) {
            if msg.role == .user { Spacer(minLength: 40) }
            Text(msg.text)
                .padding(10)
                .background(msg.role == .user ? Color.accentColor.opacity(0.18) : Color.secondary.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .accessibilityLabel("\(msg.role == .user ? "You said" : "Ralph said"): \(msg.text)")
            if msg.role == .assistant { Spacer(minLength: 40) }
        }
        .padding(.horizontal)
    }

    private var composer: some View {
        HStack(spacing: 10) {
            Button {
                session.viewModel.toggleVoice()
            } label: {
                Image(systemName: session.viewModel.isListening ? "mic.fill" : "mic")
                    .font(.title2)
                    .frame(width: 44, height: 44)
            }
            .accessibilityLabel(session.viewModel.isListening ? "Stop listening" : "Start listening")
            .accessibilityIdentifier("mic-button")

            TextField("Ask Ralph…", text: $draft, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...4)
                .focused($draftFocused)
                .accessibilityIdentifier("draft-field")

            Button("Send") {
                let p = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !p.isEmpty else { return }
                draft = ""
                draftFocused = false
                Task { await session.viewModel.send(p) }
            }
            .buttonStyle(.borderedProminent)
            .accessibilityIdentifier("send-button")
            .disabled(session.viewModel.isThinking)
        }
        .padding(10)
    }
}
