// SpeechCoordinator — wraps iOS native TTS + STT with VoiceOver-friendly
// announcements. Defaults to Apple's "Ralph" voice when the system has it
// installed (older novelty voice; Settings → Accessibility → Spoken Content
// → Voices → English → Ralph), and falls back to the user's selected
// system voice otherwise. The orchestrator's BDD scenarios assert on
// `currentVoiceIdentifier()` so the test suite can verify Ralph wins when
// available.
//
// Authored by Chase Eddies <source@distillative.ai>.

import Foundation
import AVFoundation
import Speech
import UIKit

@MainActor
final class SpeechCoordinator: NSObject, ObservableObject {

    /// Identifier prefix for Apple's "Ralph" voice. Apple ships several
    /// regional Ralph voices; we accept any identifier containing this
    /// substring so the resolver works across en-US, en-GB, etc.
    static let ralphIdentifierFragment = "Ralph"

    private let synthesizer = AVSpeechSynthesizer()
    private let recognizer  = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var audioEngine = AVAudioEngine()
    private var request:  SFSpeechAudioBufferRecognitionRequest?
    private var task:     SFSpeechRecognitionTask?

    // ----- TTS ----------------------------------------------------------

    func speak(_ text: String) {
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = preferredVoice(for: "en-US")
        utterance.rate  = AVSpeechUtteranceDefaultSpeechRate
        utterance.pitchMultiplier = 1.0

        // Pipe through VoiceOver so accessibility users get the same audio
        // they would get from a native iOS announcement.
        UIAccessibility.post(notification: .announcement, argument: text)

        synthesizer.speak(utterance)
    }

    /// Resolves the preferred voice. Picks Ralph if installed, otherwise
    /// the highest-quality voice for the locale, otherwise the system default.
    func preferredVoice(for languageCode: String) -> AVSpeechSynthesisVoice? {
        let voices = AVSpeechSynthesisVoice.speechVoices()
        if let ralph = voices.first(where: { $0.identifier.contains(Self.ralphIdentifierFragment) }) {
            return ralph
        }
        if let premium = voices
            .filter({ $0.language.hasPrefix(languageCode) })
            .max(by: { $0.quality.rawValue < $1.quality.rawValue }) {
            return premium
        }
        return AVSpeechSynthesisVoice(language: languageCode)
    }

    func currentVoiceIdentifier(for languageCode: String = "en-US") -> String {
        preferredVoice(for: languageCode)?.identifier ?? "system-default"
    }

    // ----- STT ----------------------------------------------------------

    func startRecognition(onPartial: @escaping (String) -> Void) {
        SFSpeechRecognizer.requestAuthorization { _ in }
        AVAudioApplication.requestRecordPermission { _ in }

        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.record, mode: .measurement, options: .duckOthers)
        try? session.setActive(true, options: .notifyOthersOnDeactivation)

        request = SFSpeechAudioBufferRecognitionRequest()
        request?.shouldReportPartialResults = true
        // Frontier quality on-device when possible.
        request?.requiresOnDeviceRecognition = recognizer?.supportsOnDeviceRecognition ?? false

        let inputNode = audioEngine.inputNode
        let format = inputNode.outputFormat(forBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            self.request?.append(buffer)
        }
        audioEngine.prepare()
        try? audioEngine.start()

        task = recognizer?.recognitionTask(with: request!) { result, _ in
            if let result = result {
                onPartial(result.bestTranscription.formattedString)
            }
        }
    }

    func stopRecognition() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        task?.cancel()
        task = nil
        request = nil
    }
}
