# Actual validation — native Jarvis revision

The implementation extends the existing HUD/backend. Simulation flags and fake device/action paths are removed. Official Groq SDK, native sounddevice capture, Edge/pyttsx3/pygame playback, and real tool functions are used. No mocked provider/hardware responses are used in the new tests or self-test.

## Executed and passed

- Dependencies installed in the existing Linux virtual environment; `pip check` found no broken requirements. A Windows x64 / CPython 3.11 binary-package resolution succeeded for `requirements.txt`; Windows voice dependency wheels were separately checked. This is dependency availability, not execution on Windows.
- 13 regression tests passed: real Markdown writes/read-back, declined actions, path traversal/secret/symlink restrictions, actual line-numbered/truncated file reads, actual datetime and relative calendar dates, allowlist checks, emergency-stop write rejection, honest unavailable integrations, TTS sanitization, real API missing-key handling, persistence, Host/origin/auth guards, and retained HUD.
- Chromium against `python main.py --text --no-browser`: authenticated HUD, native male-voice configuration, actual missing-key error, actually confirmed `remember` write and file read-back, emergency stop, original SVG reactor and desktop/tablet/phone viewports without horizontal overflow. No microphone/speaker/cloud success was inferred from the browser check.
- `python main.py --selftest` was run, using real integrations, stdin noninteractive. **3 of 18 checks passed**: actual local date/time, actual project listing, actual project file reading. The overall self-test **failed (exit 1)**.

## Remaining self-test failures and non-executed actions

- Microphone: Linux runtime has no PortAudio library or exposed Windows input device. Whisper and clap tests therefore had no actual recording to test. Windows sounddevice wheels bundle PortAudio; physical Windows recording still needs verification.
- Groq model/tool call: no GROQ_API_KEY is configured in the cloud. No live model access, free-tier eligibility, function-call response or transcription success is claimed.
- TTS: Edge request returned a proxy error; Linux fallback reported eSpeak/eSpeak-ng absent. No male audio or audible pronunciation was verified here. Windows uses installed SAPI voices as fallback; it still requires testing on the user's speakers.
- Global hotkeys: require Windows.
- DuckDuckGo search: actual search attempt failed under cloud network policy; no sources were fabricated. The library reported DDGSException: No results found; a separate direct DuckDuckGo HTTP probe returned ProxyError, confirming a blocked service route.
- Note/task/memory self-test actions, browser/app/volume actions: the noninteractive run had no affirmative confirmation, so they were **NOT RUN** and reported FAIL. Regression and browser tests separately performed actual confirmed writes only in temporary test directories. Windows launch/volume outcomes were not fabricated.
- Calendar: no credentials.json or OAuth token; **NOT RUN**, optional setup required.
- Home Assistant: no URL/token/allowlisted entities; **NOT RUN**, optional setup required.

## Documentation and limits

Official current Groq SDK README was read from `groq/groq-python`, confirming AsyncGroq, Whisper `whisper-large-v3-turbo`, error types and retry configuration; it contains `openai/gpt-oss-20b`. Detailed model/tool pages on console.groq.com were blocked by the proxy. The current account's model availability and free-plan status were not verified. The live self-test checks the configured model and an actual forced tool call when a key is provided.

No physical Windows 11/Python 3.11 runtime is attached. Source compiled and ran on Python 3.12/Linux; Windows binary dependencies resolved. PowerShell launcher/updater, soundcard, clap calibration and native Windows API calls remain platform/hardware validation steps. Google OAuth and physical HA need the user's credentials/devices and affirmative confirmations. Publication/restoration of the cloud environment is separate from saving a draft.

The saved cloud draft was updated with native install/start instructions, Groq/model/language/folder requirements, and additional Groq docs, Microsoft speech, DuckDuckGo and Google OAuth/Calendar network domains. This did not apply or publish those settings; current proxy failures remain real. Existing unrelated domains/presets were preserved.

Voice loop fix: 15 backend tests and real Chromium HUD smoke passed. Stop now cancels wake and voice tasks and closes the input stream; regular startup prepares the microphone without automatically starting wake/follow-up transcription. Piper 1.8.0 installed and imported on Linux. The Windows CPython 3.11 package resolver finds a compatible win_amd64 wheel. Actual `python main.py --setup-voice` failed with ProxyError HTTP 403 at Hugging Face, so model generation and playback are unverified. The installer fails explicitly and does not mark voice ready. No Windows audio device is available in this environment.

Project workspace editing: 24 backend tests passed, including actual confirmed file and directory creation, targeted edits, byte-for-byte backup/read-back, CRLF preservation, cancelled operations, stale-hash/external-edit conflicts, and traversal/symlink/hardlink/credential/root restrictions. Real Chromium smoke tests confirmed file creation and editing through the actual API and diff dialog, then read the physical files back. These checks use real temporary files without fabricated provider responses. Groq model selection of these new tools and Windows filesystem execution were not tested (no key or Windows host). The updater continues to preserve existing .env and user data; PROJECTS_WRITE_DIR defaults to the dedicated JarvisProjects folder when missing.

Particle orb: 26 backend tests passed, including PCM envelope checks for silence/loudness and out-of-phase stereo. Real Chromium rendered the particle canvas in both themes and at desktop/tablet/phone sizes while the existing conversation/confirmation/file tests passed. Canvas screenshots were inspected. Native playback now sends a 30 Hz RMS envelope from decoded PCM; speech preparation is separate from playback. Cloud hardware playback remains unverified. SAPI has no decoded PCM envelope; its state animation does not claim to measure speech volume.
