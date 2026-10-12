# Jarvis — real Windows 11 voice assistant

The existing animated HUD is retained: its circular reactor, rings, cyan and Dark Feminine themes are in `ui/index.html`. The Python application now uses the **official Groq SDK**, native microphone capture, tool calling, actual confirmed actions, and male TTS. There are no simulated execution paths. Unavailable hardware/integrations return errors or setup requirements, never successful dummy results.

**Read `docs/VALIDATION.md` before calling this fully verified.** The development machine is Linux with no Windows microphone/speaker and no Groq key. Local files/HUD/security checks have run; live Groq, Windows sound, apps and personal devices still need your Windows self-test.

## Windows 11, Python 3.11: exact setup

Install Python 3.11 64-bit with **Add Python to PATH** and the `py` launcher. If you already run the project with Python 3.12, the source also supports it; the requested target is 3.11. In PowerShell opened in the folder containing `main.py`:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Only if .env does not already exist:
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Keep your key private. Minimum `.env` settings:

```dotenv
GROQ_API_KEY=your_private_key
GROQ_MODEL=openai/gpt-oss-20b
GROQ_FALLBACK_MODEL=llama-3.1-8b-instant
WHISPER_MODEL=whisper-large-v3-turbo
JARVIS_LANGUAGE=en
TTS_VOICE=en-GB-RyanNeural
JARVIS_TIMEZONE=Europe/Paris
NOTES_DIR=./data
PROJECTS_DIR=C:/Users/ilona/OneDrive/Documents/YourProject
```

`PROJECTS_DIR` must be an existing folder you want Jarvis to **read**. `NOTES_DIR` can be a private notes folder or an Obsidian vault. All tool-generated notes, tasks, memories and private tokens remain within this directory. Use forward slashes in `.env` Windows paths. Your old `.env` is preserved by updating; obsolete settings from previous versions are ignored. Add the new model/language/folder settings rather than sharing the file.

Run:

```powershell
python main.py
```

Or `.\start.ps1` (creates the venv and installs requirements). It opens the local HUD in your default browser. Keep the terminal open. **Ctrl+C** or `/quit` stops Jarvis.

For French:

```dotenv
JARVIS_LANGUAGE=fr
TTS_VOICE=fr-FR-HenriNeural
```

Restart after `.env` changes. The HUD can also switch language/voice for the current runtime. To use another male Edge voice, set `TTS_VOICE` explicitly.

## How to talk and interrupt

- Stay quiet during the initial one-second room-noise calibration.
- **Double clap** wakes Jarvis. Detection uses energy spikes separated by 0.12–0.7 seconds. Adjust `CLAP_SENSITIVITY` (2–30; default 6) if necessary; larger values require louder claps. This is a simple energy detector and may react to other sharp sounds.
- **F8** wakes/listens; the HUD microphone button is another fallback. Jarvis says “Yes?”, records until silence, sends the recording to Groq Whisper, and keeps listening for follow-ups for **30 seconds** after each reply.
- **F9**, `/stop` or the HUD Stop button interrupts audio. The emergency Tools button disables future tool actions and declines pending confirmations. An action already sent cannot be undone.
- Type in the terminal or the HUD when you prefer text. For a microphone-free start: `python main.py --text`. For no automatic browser: `--no-browser`.
- Microphone recording/Whisper and speech playback happen on the **PC running Python**, not on the tablet viewing the HUD. Android microphone recording is not silently substituted by this native version.

Allow microphone access for desktop applications in **Windows Settings → Privacy & security → Microphone**. `sounddevice` Windows wheels bundle PortAudio. Set `AUDIO_INPUT_DEVICE` to a device index or name when needed; device native sample rate is used, not an assumed rate. List devices with:

```powershell
python -c "import sounddevice; print(sounddevice.query_devices())"
```

Edge TTS uses **Ryan** (English UK) or **Henri** (French). Playback is via `pygame.mixer`. If its network service fails, Jarvis attempts an installed **male** `pyttsx3` voice of the selected language; if none exists, it reports the failure. Add Windows speech voices under **Time & language → Speech**. It never silently presents a female fallback as a male voice.

Before TTS, “J.A.R.V.I.S”, “JARVIS” and “jarvis” become “Jarvis”; Markdown, code blocks and emojis are removed, and uppercase words are normalized. Long answers/code remain on screen; speech uses a short opening summary. Ring states follow actual pipeline events. Bars show measured microphone energy, not a fabricated speech waveform.

## Brain, models and free usage

Groq is the sole AI provider. `GROQ_MODEL` and `GROQ_FALLBACK_MODEL` are server-controlled. The default `openai/gpt-oss-20b` appears in the current official SDK documentation; the fallback is a smaller `llama-3.1-8b-instant`. Tool-use/account availability for these exact IDs is checked by the self-test's live model listing and forced function call. Current free-plan eligibility could not be independently confirmed here because Groq model/docs pages were blocked and no key is available. Check your own account; remain on the **Free Plan without paid billing** if you do not want charges.

On HTTP 429, Jarvis announces the limit out loud, waits two seconds, retries once, then tries the configured smaller model. If it is also limited, it stops and reports the real error. It never changes provider or enables paid billing. Rate limiting after a started stream is not replayed automatically, to avoid duplicate actions. Free quotas apply to both the brain and Whisper; a fallback cannot bypass account-wide limits. Edge TTS and DuckDuckGo have network dependencies but no paid API key is required by this app.

Official SDK documentation consulted: https://github.com/groq/groq-python (AsyncGroq, transcription, errors, retries). Groq model/tool docs to check from your own browser: https://console.groq.com/docs/models and https://console.groq.com/docs/tool-use.

## Tools — real and confirmed

The model receives real function schemas. Tools log their actual outcomes in SQLite and display the name, arguments, result and errors in the HUD. All state-changing tools ask confirmation **before** they execute. In the terminal, type `yes`/`oui` or `no`/`non`; in the HUD, use the confirmation dialog; in a native voice turn, Jarvis reads the action back and listens for explicit yes/no. No response or ambiguous consent cancels the operation.

- `get_datetime()` returns the actual local date/time/timezone.
- `web_search(query)` uses the maintained DuckDuckGo search library **ddgs**, with DuckDuckGo selected as backend. It returns actual title/URL/excerpts. No search results means an error; never invented verification.
- `open_url(url)` opens only HTTP(S) URLs without embedded credentials in the Windows default browser, after confirmation.
- `add_note(text)` / `add_task(text)` append to `Notes.md` / `Tasks.md` under `NOTES_DIR`, after confirmation.
- `remember(fact)` appends to `NOTES_DIR/memory.md`, after confirmation. This file is loaded for each brain turn, so it is available after restart. No personal facts are automatically extracted. Your earlier confirmed SQLite memories remain accessible in the inspector and relevant snippets are retrieved too.
- `list_files()` / `read_file(path)` are read-only and restricted to `PROJECTS_DIR`. Traversal and escaping symlinks are rejected. Hidden/internal folders, `.env`, credential files, keys and databases are excluded. Text has line numbers, PDFs have page numbers. Files over 20 MB are refused; returned content is capped at 16,000 characters and PDFs at 30 pages. Scanned PDFs without text explicitly need OCR.
- `open_app(name)` accepts only names in `config.yaml`. Defaults: notepad, calculator, explorer, chrome, edge. Execution uses fixed executable/argument lists with **no shell**. Chrome/Edge must be installed at an allowed path. Add your own trusted application configuration manually; model text cannot rewrite the allowlist or invent an executable.
- `pc_action(name)` is a fixed Windows-only extension for lock, sleep, volume up/down and mute toggle. Every action is confirmed; “mute toggle” is explicitly a toggle, not a claim to know the current mute state.
- `add_calendar_event(title,start,end)` resolves relative dates using real time and `JARVIS_TIMEZONE`, reads back the complete event proposal, asks confirmation, inserts it, then fetches it again and verifies title/start/end. Inspect your calendar before retrying an ambiguous network failure. OAuth setup below.
- `ha_call_service(domain,service,entity_id)` uses actual Home Assistant REST calls and an entity/service allowlist. Accepted calls are distinguished from physical state verification. It is unavailable, with setup instructions, when not configured.

There is no arbitrary shell tool, unrestricted desktop agent, automatic account login or filesystem-write tool. Failure/cancellation/unavailability is shown distinctly from completion. Web/file/memory content is untrusted data and cannot authorize an action; all changes still require your approval.

## Calendar OAuth desktop setup (optional)

1. In Google Cloud Console, enable **Google Calendar API**.
2. Set up OAuth consent and an **OAuth Desktop app** client; in Testing mode add your Google account as a test user.
3. Download its JSON as `credentials.json` next to `main.py`, or set `GOOGLE_CREDENTIALS_FILE` to its private local path.
4. Request an event. After you confirm the resolved event, a local browser OAuth flow asks you to grant Calendar event access.

Tokens are stored under `NOTES_DIR/.private/google-token.json` (ignored by Git). Do not publish or sync that private folder. OAuth testing tokens can expire; reauthorize if needed. Missing credentials do not block ordinary chat; the tool explains setup and creates no event.

## Home Assistant (optional)

```dotenv
HA_URL=http://your-private-ha-host:8123
HA_TOKEN=your_private_long_lived_token
HA_ENTITIES=light.desk,switch.desk,scene.good_night
```

Use trusted HTTPS where supported; HTTP sends the bearer token over your private LAN. Supported domains: light, switch, scene; services: turn_on/turn_off (scene only turn_on). Entity IDs must be explicitly allowlisted. Empty configuration means no devices connected, not demo devices.

The preserved scene dashboard can use `scenes.json`. Empty presets show **non configurée** and cannot execute. Example:

```json
"Study Mode": {"home": [{"entity_id": "light.desk", "service": "turn_on"}], "pc": ["notepad"]}
```

All scene operations are validated and the complete plan is confirmed. Scene execution is sequential, not atomic; earlier real actions may remain after a later failure. Connect buttons/key-tray/ESPHome automations through Home Assistant's own configuration.

## Real self-test

Stop a running Jarvis instance, activate the venv, then:

```powershell
python main.py --selftest
```

It tests actual microphone recording and silence detection; live Groq model authentication/function calling; Whisper on the **recorded** WAV; real TTS playback with your listening confirmation for masculine voice and “Jarvis” pronunciation; double-clap/hotkey registration; real datetime/search/project reads; actual confirmed note/task/memory writes and read-back; browser/app/volume actions; and optional real Calendar and HA calls.

It asks before every changing action. Self-test note/memory files are placed in a dated subdirectory inside `NOTES_DIR` to avoid polluting your profile. It may create a **real calendar event** and turn on an **actual HA entity**, only if configured and you explicitly consent. Declined/noninteractive/unavailable/unverified checks print **FAIL with NOT RUN/UNVERIFIED and the exact reason**. No fabricated recordings, API responses or dummy audio/device drivers are used. Nonzero exit means the overall self-test did not pass. Detailed report: `NOTES_DIR/.private/selftest-report.json`.

Local regression checks (real temporary files and the real local backend, not fake services):

```powershell
python -m unittest discover -s tests -v
```

Optional developer-only Chromium/Playwright check: `node tests/ui_smoke.cjs`. It does not validate physical hardware or cloud AI.

## Updating your existing ZIP installation

Stop Jarvis with Ctrl+C. In its PowerShell directory:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/ilonasaunier05-wq/forfun/main/update.ps1" -OutFile .\update.ps1
.\update.ps1
.\start.ps1
```

The updater backs up old source files, installs `main.py` and native modules, removes the three obsolete execution/demo modules, and preserves `.env`, `data`, `.venv`, `config.yaml` and `scenes.json`. Add new env settings manually. Refresh the HUD with **Ctrl+F5**. If GitHub download is private/blocked, use **Code → Download ZIP** while signed in and copy the source files while preserving private/configuration files. If you cloned with Git, use `git pull` after preserving local edits. The PowerShell updater still needs verification on your physical Windows machine.

## Security, data and network

The server binds **127.0.0.1** by default. Authenticated trusted-HTTPS LAN access requires a strong `JARVIS_PASSWORD`, exact `JARVIS_ALLOWED_HOSTS`, secure cookies and a LAN certificate trusted by all devices; do not forward ports to the Internet. Starting the default app never changes your firewall or installs a VPN. Single personal account, no multi-user isolation.

Notes, SQLite history/memories/action logs and OAuth tokens live under `NOTES_DIR`; protect this folder and exclude `.private` from Obsidian sync. Groq receives microphone recordings, recent conversation and relevant memory/tool content. Edge receives speech text. DuckDuckGo receives search queries. Never commit `.env`, credentials, tokens or conversations. No analytics. The application cannot enforce provider billing status: use the account's Free Plan and no paid billing.

Cloud tasks: use the existing isolated checkout, without a new Git worktree. Run `python main.py --text --no-browser` on a headless host. A filesystem snapshot does not preserve microphone streams, audio playback, server processes, authentication or OAuth sessions.

### Si le micro ou les boutons ne répondent pas

Ouvre le HUD depuis l’adresse affichée par `python main.py` (pas en double-cliquant le fichier HTML). Ferme les anciens onglets Jarvis puis recharge avec Ctrl+F5. Le bandeau indique si le JavaScript est relié au serveur. Un texte envoyé doit apparaître immédiatement ; une requête bloquée affiche une erreur après 10 secondes. Dans Settings, sélectionne le microphone Windows : le nom et le niveau réel apparaissent dans le HUD et les barres réagissent même en veille. Vérifie aussi les autorisations microphone pour les applications de bureau dans Windows. F8/le bouton micro démarre maintenant l’écoute sans attendre une synthèse vocale en panne. La voix anglaise Ryan est indépendante de la langue de transcription. Edge TTS en panne bascule sur une voix masculine Windows et ne retente pas le réseau pendant cinq minutes. Ces changements ne prouvent pas l’accès au matériel Windows depuis le cloud.
