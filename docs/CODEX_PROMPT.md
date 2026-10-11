# CODEX MISSION — BUILD MY REAL J.A.R.V.I.S.

You are my lead full-stack engineer, UX engineer, and AI systems architect. Turn the existing self-contained `ui/JARVIS_HUD_DEMO.html` into a **real, usable, security-conscious, low-resource personal J.A.R.V.I.S. assistant** on my Windows PC. This is a project to actually implement, run, and test—not a mockup, concept deck, or list of tutorials.

## Ground rules

1. **Inspect `ui/JARVIS_HUD_DEMO.html` first.** Reuse its actual markup, styles, animated circular reactor, Stark-style visual language, cyan holographic theme, dark-feminine pink/violet theme, buttons and layout. Refactor into modules only when it clearly helps maintainability. DO NOT replace this with a generic chat app, unrelated template, or static screenshot.
2. Target environment: **Windows 10/11**, Chromium browser on the PC, Samsung Android phone and Galaxy Tab S8 on the same private network. Optimize for a student budget, minimal installation/storage, low idle CPU/RAM use, and no mandatory paid subscription.
3. Use **a lightweight web frontend (HTML/CSS/vanilla TypeScript or JavaScript)** and a **Python FastAPI backend**, SQLite for structured data, and local Markdown for optional Obsidian-compatible memory. Avoid Electron, heavyweight frameworks, Docker, and local multi-GB LLM downloads unless there is a compelling reason and I explicitly choose them.
4. Work in small runnable milestones. Complete the MVP first. For anything requiring external credentials or hardware, provide a functional local/mock adapter clearly labeled as DEMO and documented integration steps. Never claim that mock functionality controls my actual devices.
5. If a dependency choice would significantly affect performance, privacy, cost, or reliability, explain the tradeoff briefly, choose a sensible default, and keep the alternative pluggable. Do not block on trivia or keep asking me to decide minor implementation details.

## Desired experience

- A desktop-wide, cinematic, clean J.A.R.V.I.S. HUD with **animated concentric circles** and a central glowing reactor. Show visually distinct states: `idle`, `listening`, `transcribing`, `thinking`, `speaking`, `running_action`, `error`.
- React to **real microphone audio levels** where the browser exposes the input, and to actual generated speech audio when routed through an audio element/Web Audio API. Never fabricate audio-reactive behavior as if real. Use tasteful animation and a reduced-motion option.
- Start/stop microphone, push-to-talk, text input, chat transcript, mute/interrupt output, selectable English/French voice, settings drawer, device/system status, scene buttons, visual error handling and keyboard shortcuts.
- Keep the existing original HUD's two color themes, enhance tablet responsiveness, and preserve dark-feminine design rather than replacing it with plain dashboard cards.
- Have one central interface for natural questions, remembering my preferences, and controlling approved devices. Support mobile/tablet access over my LAN; secure it properly rather than exposing an unauthenticated web service.

## Real AI: reliable answers, no mandatory local model

- Use provider adapters: **OpenAI API** first, with configurable alternatives (e.g. Gemini, Groq or a local Ollama endpoint) only where practical. No vendor lock-in. Note explicitly that **ChatGPT Plus is NOT an OpenAI API subscription**.
- Store API credentials only on the backend, loaded from `.env`; never embed secrets in frontend code. Add `.env.example`, error messages when missing, and model/provider selection in settings.
- Keep sessions and chat history. Stream output to the frontend so that text appears progressively and HUD changes state promptly.
- For factual/fast-changing questions, provide an **optional real web-search tool** behind an actual configured search provider/API. If not configured, say that the answer isn't web-verified; never invent search results, citations or URLs. Show sourced links when real sources are available. Separate facts from uncertain claims.
- Avoid spurious LLM calls for deterministic commands such as turning off lights or checking PC status: execute validated intents using safe tool routing.
- Add per-session and daily usage counters and configurable spend limits if a paid API is used; no false promises of permanently free unlimited API calls.

## Long-term memory, Obsidian-friendly

- Use SQLite for conversation records, selected memories, tool/action logs and settings. Store persistent user knowledge in Markdown files in `data/memory/` with understandable names (`Profile.md`, `Preferences.md`, `Home.md`, `Projects.md`, `Routines.md`) and optional mapping to an Obsidian vault.
- Support explicit voice/text instructions: **"Remember that ..."**, **"What do you remember about ...?"**, **"Forget ..."**, and **"Correct that memory ..."**. Ask for confirmation before writing potentially sensitive or personal long-term memories; expose a memory inspector UI with edit/delete.
- Implement useful retrieval first with SQLite FTS5, and only add semantic embedding search if needed, as an optional extension. Retrieve relevant snippets before answering; do not stuff every memory file into every prompt. Minimize duplicated or contradictory memories.
- Let me export and delete conversations and memories. Use transparent settings for memory retention and storage location.

## Voice interaction

- Build the voice pipeline incrementally: first implement browser microphone + Web Speech API speech-to-text where supported, plus browser speechSynthesis for an immediate light demo. Clearly label browser compatibility, network dependencies and voice limitations.
- Design pluggable adapters for better quality later: speech-to-text (faster-whisper or a cloud API) and text-to-speech (Piper or a cloud/realtime voice API). Do not install/download heavy models without permission.
- Make the assistant listen, transcribe, respond in text, and speak the reply. Support interruptions/stop and prevent the microphone from picking up its own output when possible.
- Add optional wake-word detection as a later milestone, not a fake always-listening switch. Explicitly explain browser/background restrictions, permission and battery implications on Android.

## PC control: safe Windows assistant

- Show real PC telemetry such as CPU usage, memory usage, and optionally battery using `psutil` when available.
- Implement a safe, allowlisted command registry: open selected apps/websites, control volume where supported, lock Windows, start preapproved focus workflow, and put PC to sleep with a confirmation prompt. Include a **dry-run/demo mode** enabled by default for actions that change computer state.
- Never execute arbitrary model-generated shell/PowerShell commands, never silently install software, delete files or send personal data, and never let untrusted web pages dictate actions. Add action-level confirmation for destructive or privacy-sensitive actions and logs of attempted actions.
- Add **Wake-on-LAN** design for the future, making clear that a sleeping/off PC cannot run its own server or wake itself; a second always-on device plus motherboard/network compatibility may be needed.

## Smart home / all-in-one command center

- Implement a Home Assistant adapter on the server with configurable `HA_URL` and `HA_TOKEN`, an allowlist of exposed entities, entity-state reading, and whitelisted light/switch/scene service calls. Use real REST/WebSocket APIs; do not pretend to have control when Home Assistant is unavailable.
- Provide the following **editable scene presets**: `Dark Feminine`, `Study Mode`, `Gaming Mode`, `Welcome Home`, `Good Night`. Do not assume my devices already exist; render dummy/simulated devices clearly marked until connected.
- Make this extensible to Matter/Wi-Fi/Zigbee devices, LED strips, smart plugs, future key-tray sensors, hidden flat buttons under Polaroids, and DIY ESPHome triggers. Keep devices vendor-agnostic where possible.
- Build a touchscreen-friendly dashboard layout for Galaxy Tab S8 and a compact phone layout; PC dashboard is the same app.
- Do not require Home Assistant on day one to chat with the AI.

## Security and privacy

- Bind backend to localhost by default. If enabling LAN access, require an actual authentication mechanism and explain trusted network prerequisites. Do not open Internet-facing ports by default. Never persist secrets in git or log them.
- Validate all tool arguments, require an allowlist for PC and Home Assistant actions, and guard against prompt injection from websites and retrieved documents.
- Clearly communicate which data goes to cloud LLM/voice/search providers and which stays on the PC.
- Include an easy emergency stop / tool-disable switch in the UI.

## Deliverables / Definition of Done

1. Inspect the provided HUD and summarize what it already implements vs. what is currently simulated.
2. Create a clear project layout, lightweight runnable source, exact install/run commands in a README for Windows PowerShell, requirements/dependency files, `.env.example`, and a `start.ps1` launcher.
3. **Deliver a real MVP in code**: original interactive HUD retained, persistent typed AI chat with streaming and provider adapter, sessions, memory add/search/delete, voice input/output with clear fallbacks, accurate assistant state animations, real Windows telemetry, mock and real Home Assistant adapter separation, scene control UI, and safe action confirmation/dry run.
4. Test backend and frontend behavior as far as the environment allows; include at least basic unit/integration tests for memory, tool validation, actions, and configuration. Document what could not be tested and why.
5. Give me practical next steps to add my actual devices and API credentials. Flag optional costs, expected resource use and security considerations honestly.
6. Once MVP is verified, propose a prioritized, incremental roadmap: better streaming speech/realtime, wake word, polished PC shell/tray, wake-on-LAN on always-on host, sensor triggers and richer tablet command center.

**Start now by opening `ui/JARVIS_HUD_DEMO.html`, inspecting the actual HTML/CSS/JS and current demo behaviors, then implementing the first runnable end-to-end milestone. Do not stop after writing an architectural plan.**
