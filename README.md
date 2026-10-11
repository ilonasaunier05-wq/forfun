# J.A.R.V.I.S. — personal HUD assistant

A runnable first MVP built directly from your original HUD: its SVG reactor, rotating rings, grid, cyan theme, and Dark Feminine theme are retained. Vanilla JavaScript + Python FastAPI + SQLite; no Docker, Electron, Ollama, local models, or frontend build step.

The supplied original remains in `ui/JARVIS_HUD_DEMO.html`; it had canned answers and simulated scenes. The application is `ui/index.html`, served by Python. Do **not** use the old GitHub Pages instructions to deploy this backend or its private data.

## No-payment setup (default)

`JARVIS_FREE_MODE=true` is enabled by default. Only the Groq endpoint is available; OpenAI, custom paid endpoints, and web search are blocked on the backend, even if their keys are present. There is no automatic fallback when free usage runs out. All local features remain free.

1. Open [Groq Console](https://console.groq.com/) and create an account on its **Free Plan**, if available to you. Do not upgrade, enable paid billing, or enter payment details for this setup.
2. Create an API key and put it in your private `.env` as `GROQ_API_KEY=your_key`. Never post it in chat. In cloud environment settings, use the secure `GROQ_API_KEY` personal key binding.
3. Keep `JARVIS_FREE_MODE=true`, the Groq endpoint, and paid search disabled; start the app normally. Selectable models come from `AI_MODELS` and must be available to your free account.
4. If the provider returns a quota/rate limit, wait and retry. The app stops; it never switches to a paid provider.

The app cannot inspect or enforce your provider account’s billing plan. Free mode restricts destinations and features; it cannot guarantee zero charges if you independently enable billing at Groq. Current plan availability/model limits must be checked in your own account. Provider documentation was inaccessible from this cloud instance, so live free-plan availability is not claimed as verified. Without a key, memory, HUD, voice controls, monitoring, and dry run still work; general AI answers require the key.

## Windows: install and run

Install Python **3.11 or later**, with the Windows `py` launcher. Open PowerShell in this project directory:

```powershell
Copy-Item .env.example .env
notepad .env
# Set GROQ_API_KEY from a Groq Free Plan account. Do not activate paid billing.
# Never put an API key into the HUD.
.\start.ps1
```

If local script execution is blocked, review `start.ps1`, then allow it for this PowerShell process only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\start.ps1
```

The launcher creates `.venv`, installs pinned direct dependencies, preserves your existing `.env`, and starts a localhost-only server on port 8000. Open `http://127.0.0.1:8000` in Chrome or Edge on your own Windows PC. Ctrl+C stops Python. To use a different port: `.\start.ps1 -Port 8001`. This local address is a Windows setup instruction, not a cloud preview.

Manual startup, after initial installation:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Linux/cloud setup:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Use the existing checkout in isolated cloud tasks; no Git worktree is required. Services must restart after a machine restore. Dependencies/files can persist; live processes cannot be assumed to persist.

## Working features and configuration

- **Conversation:** provider/model selector, incremental streamed replies, persistent sessions, export and per-conversation deletion, interrupt button / Escape. Failed or interrupted streams are never marked complete; partial replies are saved with a label. Context is bounded to recent messages and relevant memories.
- **Cloud brain:** OpenAI Chat Completions and a configurable HTTPS OpenAI-compatible adapter (Groq example). Configure models actually supported by your account. Other protocols, such as Gemini's native API, need a new adapter or a compatible gateway. No API key means an explicit error, never a canned answer presented as AI.
- **Search:** blocked in default free mode. In optional paid mode, Brave Search via `BRAVE_SEARCH_API_KEY`. The search checkbox stays disabled until configured. Retrieved HTTPS source links are shown separately; retrieval does not prove the whole answer. Source excerpts are untrusted data, not action instructions. Search failures produce an error rather than silently claiming verification.
- **Voice:** French/English browser recognition and browser speech synthesis. Reactor states follow recognition, transcription, provider streaming, action execution, errors, and actual speech callbacks. Real microphone frequency levels drive the bars when Web Audio access works. Speech synthesis cannot expose its output samples: speaking rings indicate synthesis state, **not measured speech amplitude**. No fake wake-word or background-listening switch.
- **Memory:** confirmed writes only, SQLite FTS5 retrieval, inspector search/edit/delete, explicit “Remember that …” / “Retiens que …” proposal commands. All proposed memories, including sensitive ones, require confirmation. “Forget …” and correction requests open the inspector so you choose the exact record. No automatic harvesting of personal facts from chats.
- **Telemetry:** real `psutil` CPU/RAM/battery readings from the Python host, with missing battery reported as unavailable. Run on Windows to see your PC's metrics; the cloud host is Linux and cannot monitor your Windows computer remotely.
- **Deterministic commands:** “pc status”, “open calculator”, “open notepad”, “lock pc”, “sleep pc”, “focus mode”, “scene Study Mode”, or “turn off light.desk” bypass the LLM and propose validated actions. French PC aliases are supported. A review button still requires confirmation; broader free-form action interpretation is not enabled.
- **Controls:** fixed Windows registry (Notepad, Calculator, a modest focus workflow opening Notepad, lock, sleep). All state-changing commands go through review, an expiring single-use confirmation, and an action log. `JARVIS_DRY_RUN=true` validates and logs only; it sends no PC/home commands. Volume and arbitrary scripts are deliberately not enabled in this milestone.
- **Home Assistant:** real REST entity reads and allowlisted `light`/`switch` turn-on/off and `scene.turn_on` service calls. Until configured, the dashboard shows clearly labeled DEMO devices. No simulated device state is presented as a real response.
- **Design:** desktop/tablet/phone layouts, fullscreen button, reduced motion and browser preferences. Keyboard: Space toggles microphone outside form controls; Escape interrupts. The ordinary microphone button is single-utterance push-to-talk, not an always-listening assistant.

## Providers, cost, and privacy

The following optional paid configuration is blocked unless you explicitly change `JARVIS_FREE_MODE=false`. For your no-payment setup, leave free mode on.

Set `OPENAI_API_KEY` (or the cloud-friendly alias `JARVIS_OPENAI_KEY`) for the OpenAI adapter, and `OPENAI_MODELS` for selectable models. For another compatible provider, set `AI_API_KEY`, `AI_BASE_URL` (ending in `/v1` where required), and `AI_MODELS`. Restart after `.env` changes. Endpoints come only from server configuration; chat content and model output cannot choose destinations or execute tools.

ChatGPT Plus is **not** an OpenAI API subscription. Local HUD, storage, telemetry, browser voice APIs, and dry run do not incur an AI API charge. Cloud AI and optional search may cost money or offer limited free tiers; browser speech may use an online browser-vendor service. No permanently free unlimited AI is promised.

`JARVIS_MAX_OUTPUT_TOKENS` bounds each completion. `JARVIS_DAILY_REQUEST_LIMIT` caps AI attempts per UTC day (including failed attempts conservatively). The settings panel shows daily and current-session request counts and provider-reported token usage. To enable a dollar guard, set `JARVIS_DAILY_BUDGET_USD` and `JARVIS_MODEL_RATES_JSON`, for example:

```dotenv
# Replace rates with current provider prices; numbers here are schema placeholders.
# JARVIS_MODEL_RATES_JSON={"openai/your-model":[0.0,0.0]}
```

Rates are USD per million input/output tokens. The ledger reserves a conservative input-byte/output-token allowance before a request; when usage is reported, it records the priced token cost. Incomplete streams without usage retain the reservation. This is a local guard based on your supplied rates, **not a billing guarantee**: search charges, provider minimums/cached pricing, other applications, and price changes are outside it. Set account-side budgets too. Leave dollar budget at zero until you supply current rates; request limits still apply.

Conversations and memories remain in `data/` on the host unless you export them. Requests send recent conversation context, selected memories, and optional search snippets to the selected AI provider. Search sends the current query to Brave. Browser voice privacy depends on your browser. `.env` and `data/` are ignored by Git. Data is not encrypted at rest: protect the Windows user account and use BitLocker if needed. No analytics or model-generated shell execution.

## Memory and Obsidian

`data/jarvis.sqlite3` is the authoritative store. `data/memory/{Profile,Preferences,Home,Projects,Routines}.md` are readable, app-managed exports. Do not put unrelated files at those five names; these exports are regenerated. Edit through the inspector, not by editing generated Markdown. Exact duplicate memories in the same category are deduplicated; conflicting memories need an explicit correction. Semantic embeddings and automatic Markdown import are not included.

An Obsidian vault can open `data/memory` directly or include that directory. Use `JARVIS_DATA_DIR` to move the whole store to a private location **before** startup; this does not migrate existing data automatically. Close the server before moving or backing up the SQLite database plus its WAL files. The default retention is indefinite until you delete individual memories/conversations. Export JSON from settings; action and usage audit logs are retained independently. To erase *all* local data, stop the server and remove its private data directory after taking any desired backup.

## Home Assistant and editable scenes

Install/configure Home Assistant separately on a trusted host; it is optional for chat. In `.env`:

```dotenv
HA_URL=http://YOUR_PRIVATE_HA_HOST:8123
HA_TOKEN=YOUR_LONG_LIVED_ACCESS_TOKEN
HA_ENTITIES=light.desk,light.rgb_strip,switch.monitor,scene.good_night
JARVIS_DRY_RUN=true
```

Use HTTPS to Home Assistant where available; an HTTP URL sends its bearer token over your private network. Put only approved entity IDs in `HA_ENTITIES`. The backend filters state reads and validates every service call. Never put the token in frontend files. The device dashboard exposes review buttons for supported allowlisted entities.

Edit `scenes.json` to map the five presets to your actual devices. Empty scenes are explicitly DEMO. Example `Study Mode` entry (the named entities must also be allowlisted):

```json
"Study Mode": {
  "home": [{"entity_id": "light.desk", "service": "turn_on", "brightness": 220}],
  "pc": ["focus"]
}
```

A light operation can include `rgb_color: [225, 80, 150]` with brightness 0–255. Review scenes in dry run first. Only then set `JARVIS_DRY_RUN=false` and restart. Every action still requires confirmation; configured plans are shown in the review dialog. Scene calls are sequential, not atomic: if a later device fails, earlier changes may remain. Results report partial failure without claiming rollback. The same global dry-run flag applies to PC and home commands.

Home Assistant remains the vendor-neutral hub for Matter, Zigbee, Wi-Fi bulbs, plugs and ESPHome. Future button/key-tray automations should trigger allowlisted HA scenes; do not expose arbitrary Python/PowerShell execution.

## Android phone / Galaxy Tab S8 over private LAN

The default server accepts **only loopback clients**. Network clients are rejected unless `JARVIS_PASSWORD` is set; allowed Host names and same-origin validation also apply. A single personal password signs in with an HttpOnly, SameSite session cookie. Auth sessions expire after 12 hours and are invalidated on server restart. No public deployment, port forwarding, wildcard hosts, or permissive CORS.

For LAN use, first configure trusted HTTPS (for example, your own LAN certificate trusted by Windows and Android). Use a long unique `JARVIS_PASSWORD`, add the exact LAN IP/hostname to `JARVIS_ALLOWED_HOSTS`, and set `JARVIS_SECURE_COOKIE=true`. Start explicitly on the PC's private LAN IP with your certificate:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host YOUR_PC_LAN_IP --port 8443 --ssl-certfile C:\path\lan-cert.pem --ssl-keyfile C:\path\lan-key.pem --no-proxy-headers
```

Restrict any Windows Firewall rule to your trusted private subnet/profile. Visit `https://YOUR_PC_LAN_IP:8443` and sign in from Android. A certificate whose hostname/IP does not match, or which Android does not trust, is not a completed HTTPS setup. Plain HTTP LAN browsing will not provide reliable microphone access and exposes login traffic; use trusted HTTPS. No certificate or firewall change is made by the default launcher.

One personal account, no multi-user separation. Anyone with this password can view your chat/memory and operate approved controls. The emergency button disables future tool actions and clears pending confirmations; its disabled state persists across restarts. It cannot undo a command already sent. Stop Python to immediately shut down the service.

## Testing and verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

No pytest dependency is required. Tests cover SQLite/Markdown persistence, memory confirmation and retrieval, incomplete/missing-key responses, SSE parsing and provider payloads using a mock HTTP transport, real HA adapter payload/state filtering against a mock transport, action allowlists and single-use confirmations, emergency stop, auth/Host/origin defenses, and usage guards.

Optional browser tests (Node + Playwright are development tools, not application requirements):

```sh
npm install --prefix /tmp/jarvis-browser playwright
NODE_PATH=/tmp/jarvis-browser/node_modules CHROMIUM_PATH=/usr/bin/chromium node tests/ui_smoke.cjs
```

See `docs/VALIDATION.md` for executed checks and limits. Real Windows lock/sleep, physical home devices, microphone capture/recognition, speaker output, Android hardware, and live paid AI/search calls require your actual host/permissions/credentials. Mock transport/browser fixtures test protocols and UI flow; they are not live hardware verification.

## Layout and next milestones

`app/config.py` reads private configuration; `store.py` owns persistence; `providers.py` contains cloud/search adapters; `tools.py` validates PC/HA actions; `main.py` serves authenticated APIs and streaming chat. `ui/index.html` retains the HUD; `ui/app.js` wires actual states and controls. `start.ps1` is the Windows launcher; `scenes.json` contains editable presets.

Prioritized next steps after you verify the MVP with your key and devices:

1. Dedicated cloud/local STT and TTS adapters with streamed sentence playback, then realtime voice and improved interruption. No model download is required for this MVP.
2. Windows volume control, explicitly registered scripts, a tray launcher and richer focus workflows; each needs platform-specific tests and allowlists.
3. Optional wake word on an explicit always-on host, with permissions/battery/background behavior addressed; Android browsers can suspend background tabs.
4. Wake-on-LAN via a second always-on trusted device, after confirming NIC/motherboard/network support. A sleeping PC cannot run this server or wake itself.
5. ESPHome key-tray/button sensors and scene triggers, then a richer tablet dashboard and optional semantic memory retrieval.
