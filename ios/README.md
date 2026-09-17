# Guiltless iOS

Native SwiftUI client for the shared Guiltless FastAPI backend.

## Open and run

1. Open `Guiltless/Guiltless.xcodeproj` in Xcode.
2. Select the `Guiltless` scheme and an iPhone simulator.
3. Press Run (`⌘R`).

The app uses `https://food-safety-ai-agent.onrender.com` by default. To use a local backend, edit the scheme and add the environment variable:

```text
GUILTLESS_API_URL=http://127.0.0.1:8000
```

For a physical iPhone, use the Mac's LAN address instead of `127.0.0.1` and ensure both devices are on the same network.

## Included prototype flows

- Product score explanation
- Product comparison
- Bag optimization
- Context-aware Copilot
- Persistent demo-user bag and profile
- Floating Guiltless Guide using the mascot asset

API and provider secrets stay in the FastAPI/Render environment and are never embedded in the iOS application.

## Command-line build

```bash
xcodebuild -project ios/Guiltless/Guiltless.xcodeproj \
  -scheme Guiltless -sdk iphonesimulator -configuration Debug \
  -derivedDataPath /tmp/GuiltlessDerivedData CODE_SIGNING_ALLOWED=NO build
```
