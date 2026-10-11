# MVP validation

Executed in the onboarding Linux cloud environment, using Python 3.12 and Chromium. This is current-instance validation, not a Windows/hardware certification or proof of restoration in a new cloud task.

## Passed

- Created `.venv` and installed application dependencies. Captured exact installed versions in `requirements.lock`; re-running installation from that lock succeeded. `pip check`: no broken requirements. The prepared Linux virtual environment occupies approximately 33 MB; Windows size and runtime memory use may differ.
- `python -m unittest discover -s tests -v`: **19 tests executed, 19 passed**, none skipped. Memory confirmation/search/edit/delete, Markdown regeneration, restart persistence, preservation of pre-existing Markdown without a database, sessions/export/delete, missing-key and incomplete-response handling, provider SSE HTTP transport, retrieval context, Home Assistant REST payload/filtering, action validation/replay/dry run/emergency stop, changed-scene confirmation rejection, deterministic commands, authentication/Host/origin/content-type defenses, request and dollar reservation limits.
- `node --check ui/app.js`: JavaScript parses.
- `CHROMIUM_PATH=/usr/bin/chromium node tests/ui_smoke.cjs`: passed. Authenticated browser login; HttpOnly cookie; theme switch; reduced-motion preference; explicit memory proposal/confirmation/save/reload/delete; honest missing-key error and reactor state; dry-run PC action; emergency disable/re-enable; streamed response rendering using a browser response fixture; desktop 1440 px, tablet 800 px, phone 390 px layouts with no horizontal overflow and original reactor visible; no browser JavaScript exceptions.
- Launched and restarted the real Uvicorn application on loopback. A live HTTP request returned Linux CPU/RAM data, no battery, and enabled dry run. Chromium loaded the real page and telemetry; desktop/phone screenshots were inspected/captured. The actual HUD retains the starter's SVG geometry and themes.
- The original tracked repository README was left unchanged. All MVP source/config/tests are new files. Runtime data, virtual environment, cache files, and secret `.env` are ignored.

Provider and Home Assistant tests use **mock HTTP transports** with their real adapter code; browser streaming uses a **fixture**. These checks prove parsing, validation and UI wiring, not live external service access. The missing-key path was exercised against the actual running backend.

## Not verified here

- Real OpenAI/alternative provider or Brave Search calls: no required keys are configured in this machine. API generation is implemented but no live AI answer is claimed.
- Windows PowerShell launcher, native application launch/lock/sleep, Windows telemetry: the cloud host is Linux. The launcher and fixed Windows calls are provided for testing on your Windows PC. Real lock/sleep are intentionally never exercised in cloud tests.
- Physical Home Assistant entities/scenes: no HA URL, token, or actual entities are configured. Dashboard devices are DEMO until configured. The adapter is not claimed to have controlled your apartment.
- Real microphone capture, online browser recognition, audible synthesized speech, and interruptions on actual Windows/Android hardware. Implemented using browser APIs with text fallback; headless browser layout tests do not validate microphone/speaker hardware or browser-vendor services.
- Android certificate trust, LAN firewall, actual Galaxy Tab S8/phone performance, and fullscreen support on those devices. Responsive Chromium viewports passed; physical devices still need validation.
- Cloud publication and restoration in a new task. Draft saving persists instructions but does not execute, apply, or publish them.

A Starlette/httpx TestClient deprecation notice is emitted by the pinned dependency versions. It does not skip tests or change their passing result; future dependency updates should rerun this suite.

## Cloud draft saved

Saved `install_script` and `start_skill`, plus custom network domains `api.openai.com`, `api.groq.com`, and `api.search.brave.com`, preserving the selected package-manager preset. Optional personal secret requirements: `JARVIS_OPENAI_KEY` (OpenAI) and `BRAVE_SEARCH_API_KEY` (search). These are metadata declarations, not supplied secret values. The `OPENAI_` prefix is reserved by cloud secret settings, so the backend also accepts `JARVIS_OPENAI_KEY`; your Windows `.env` can use ordinary `OPENAI_API_KEY`.

Review and save the draft in environment settings, enter keys securely if you want live cloud validation, and publish the environment. No keys should be posted in chat. The compatible provider can instead be configured via server-side `.env`; credentials are optional for testing local memory, telemetry, and dry run.

## No-payment revision

Default `JARVIS_FREE_MODE=true` now exposes only the Groq endpoint, rejects other endpoints, and blocks web search even if a search key is present. Backend tests also verify paid-provider/search rejection without recording an API request. Browser checks verify Groq is the only selectable provider and search is disabled; the full existing HUD smoke flow passed again. The restarted live server reports free mode, Groq only, and search disabled.

No Groq key exists in the current instance. Requests to the provider's official documentation were blocked by the network proxy; current plan availability and model eligibility could not be checked here. No live AI answer or account billing status is claimed as verified. A user must create a Free Plan key without enabling paid billing. Account-side billing cannot be enforced by this app.

The draft now saves `JARVIS_FREE_MODE=true`, the optional personal `GROQ_API_KEY` requirement for api.groq.com, and updated startup instructions. Earlier optional OpenAI/Brave requirements remain declared but are unused and blocked in free mode. The existing installation script and network settings were preserved. Review/save and publish are still separate from draft persistence.
