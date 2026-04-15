# SwiftUI patterns

Opinionated patterns for SwiftUI apps shipped via `ios-localdeploy`. These
exist so Claude doesn't have to reinvent app architecture each session.

## App entry point

```swift
@main
struct MyApp: App {
    @StateObject private var session = AppSession()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
        }
    }
}
```

`AppSession` is a single source of truth for app-wide state (auth, feature
flags, theme). It is `@StateObject` at the top so its lifetime matches the
app's.

## View / view-model split

- Views are `struct` and contain only layout + bindings.
- View models are `final class … : ObservableObject` with `@Published`
  properties and `@MainActor` annotated methods.
- Inject view models with `@StateObject` at the screen level, then pass
  child views `@ObservedObject` slices.

```swift
@MainActor
final class FeedViewModel: ObservableObject {
    @Published private(set) var posts: [Post] = []
    @Published private(set) var isLoading = false
    @Published var error: String?

    private let api: FeedAPI

    init(api: FeedAPI = .live) { self.api = api }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do { posts = try await api.fetch() }
        catch { self.error = error.localizedDescription }
    }
}
```

## Networking

- Always go through a small protocol (`FeedAPI`) so previews and tests can
  use a fake.
- Decode with `JSONDecoder` configured once on the live impl.
- Use `URLSession.shared.data(for:)` (async/await) — avoid Combine for new
  code unless you specifically need it.

## Previews

Every screen should have at least one `#Preview` showing the loaded state
and one showing the error state. Previews compile against the simulator
build, so `ios-localdeploy --target simulator` exercising them is a good
smoke test.

```swift
#Preview("Loaded") {
    FeedView(viewModel: .preview(.loaded))
}
#Preview("Error") {
    FeedView(viewModel: .preview(.error("Network down")))
}
```

## Testing

- Use `XCTest` + `@MainActor`-marked test classes for view-model logic.
- Snapshot tests: prefer the SwiftUI-native `ImageRenderer` pattern over
  third-party libraries for hermeticity.
- Run via `xcodebuild ... test` (see `scripts/build.sh test`).
