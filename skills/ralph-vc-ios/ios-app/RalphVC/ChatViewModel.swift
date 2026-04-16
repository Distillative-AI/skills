// ChatViewModel — @MainActor view model that owns the message list and
// brokers between the UI, RalphAgent, and RalphVoice.
//
// Authored by Chase Eddies <source@distillative.ai>.

import Foundation
import Observation

enum ChatRole: String, Codable, Sendable {
    case user
    case assistant
}

struct ChatMessage: Identifiable, Sendable, Equatable {
    let id: UUID
    let role: ChatRole
    let text: String
    let timestamp: Date

    init(role: ChatRole, text: String) {
        self.id = UUID()
        self.role = role
        self.text = text
        self.timestamp = Date()
    }
}

@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var isThinking: Bool = false
    @Published private(set) var isListening: Bool = false

    private let agent: RalphAgent
    private let voice: RalphVoice

    init(agent: RalphAgent, voice: RalphVoice) {
        self.agent = agent
        self.voice = voice
    }

    func send(_ prompt: String) async {
        messages.append(ChatMessage(role: .user, text: prompt))
        isThinking = true
        defer { isThinking = false }
        let reply = await agent.ask(prompt)
        messages.append(ChatMessage(role: .assistant, text: reply))
        voice.speak(reply)
    }

    func toggleVoice() {
        if isListening {
            voice.stopRecognition()
            isListening = false
        } else {
            voice.startRecognition { [weak self] partial in
                Task { @MainActor in
                    guard let self else { return }
                    if let last = self.messages.last, last.role == .user {
                        // amend the last user bubble with partial transcript
                        self.messages.removeLast()
                    }
                    self.messages.append(ChatMessage(role: .user, text: partial))
                }
            }
            isListening = true
        }
    }
}
