// RalphVoice — wraps AVSpeechSynthesizer + SFSpeechRecognizer, prefers
// the Ralph voice when installed.
//
// Authored by Chase Eddies <source@distillative.ai>.

import AVFoundation
import Speech
import UIKit

@MainActor
final class RalphVoice: NSObject, ObservableObject {
    static let ralphIdentifierFragment = "Ralph"

    private let synthesizer = AVSpeechSynthesizer()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let audioEngine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?

    func speak(_ text: String) {
        let utt = AVSpeechUtterance(string: text)
        utt.voice = preferredVoice(for: "en-US")
        utt.rate  = AVSpeechUtteranceDefaultSpeechRate
        UIAccessibility.post(notification: .announcement, argument: text)
        synthesizer.speak(utt)
    }

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

    func startRecognition(onPartial: @escaping (String) -> Void) {
        SFSpeechRecognizer.requestAuthorization { _ in }
        AVAudioApplication.requestRecordPermission { _ in }
        let audio = AVAudioSession.sharedInstance()
        try? audio.setCategory(.record, mode: .measurement, options: .duckOthers)
        try? audio.setActive(true, options: .notifyOthersOnDeactivation)

        request = SFSpeechAudioBufferRecognitionRequest()
        request?.shouldReportPartialResults = true
        request?.requiresOnDeviceRecognition = recognizer?.supportsOnDeviceRecognition ?? false

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
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
