# JARVIS Desktop

Privacy-first local desktop voice assistant. Runs entirely on your machine
(Tauri 2 desktop shell + React frontend + Python AI sidecar + Ollama).
No cloud, no telemetry, no paid APIs for core features.

## Features

- **Typed chat** with a local Ollama model (model selectable in Settings).
- **Offline voice-to-text (push-to-talk)** via MediaRecorder → sidecar
  `/v1/transcribe` (faster-whisper). Works without internet.
- **Voice-to-text converter mode** (Settings → Voice → Dictation mode):
  transcribed speech fills the input box instead of being sent to the
  assistant; copy any message with the ⎘ button.
- **Microphone selection** (Settings → Microphone) with live audio meter
  during push-to-talk.
- **Hands-free (HF) listening** (browser SpeechRecognition) — opt-in via
  Settings → Voice (requires internet).
- **Adaptive UI**: resizable panels, transparency, compact mode, accent
  theming, layout preferences persisted locally.
- **Tool verdicts**: every tool result carries `done` / `unverified` /
  `failed` / `ask` / `started` and the assistant speaks them honestly.
- **Policy engine**: risk levels 0–3, approval cards, remembered permissions.
- **Local memory** (SQLite + embeddings) and RAG over indexed documents.
- **Scheduler** (reminders, timers), clipboard, file tools, notifications.
- **Auto-cleanup** of stale processes/artifacts on every start (`start.bat`).
- **ErrorBoundary** safety net so crashes show cause + reload instead of a
  blank screen.

## Architecture

```
apps/desktop            React + Tauri 2 (Rust shell)
  src/                  UI, stores (Zustand), hooks
  src-tauri/            sidecar spawn, health, loopback only
packages/contracts      shared TS schemas (events, tools, state)
packages/ui             shared UI primitives
services/assistant      Python FastAPI sidecar
  src/jarvis/           config, lifecycle, api, orchestration, tools,
                        policy, audio, memory, scheduler, telemetry
  tests/                pytest (68+ passing)
```

## Prerequisites

- Node.js 20+ and npm 10+
- Rust stable + cargo
- Python 3.11+
- Ollama (local) with at least one chat model, e.g. `ollama pull qwen2.5:3b`
- (optional) `ollama pull nomic-embed-text` for memory search
- (optional) `pip install faster-whisper av` for offline transcription

## Quick start

```bash
# 1. Install dependencies
npm run bootstrap

# 2. Verify your environment
npm run doctor

# 3. Run in dev mode (starts Tauri + Python sidecar)
npm run dev:tauri
```

Or on Windows, double-click `start.bat` (auto-cleans stale processes first).

## Using as a voice-to-text converter

1. Open **Settings → Voice** and enable **Dictation mode**.
2. (Optional) **Settings → Microphone** — grant access and pick your mic.
3. On the home screen click the **mic button**, speak, click again (or wait
   for auto-stop).
4. The transcript appears in the input box and the Conversations screen.
   Click the **⎘** button on any message to copy it to the clipboard.
5. Paste anywhere.

> Hands-free (HF) listening uses browser SpeechRecognition and requires
> internet. In offline mode it is intentionally disabled; use push-to-talk
> for fully offline transcription.

## Settings overview

- **Voice**: speech on/off, browser STT toggle (internet), dictation mode.
- **Microphone**: device selection, permission status.
- **Layout**: resizable panels, transparency, compact mode, accent theme.
- **Models**: chat model selection (Ollama).

## Tests & quality

```bash
npm test             # frontend + backend tests
npm run lint         # eslint + ruff
npm run format       # prettier + ruff format
npm run doctor       # environment check
```

Backend tests:

```bash
cd services/assistant && python -m pytest -q
```

## Package for release

```bash
npm run package:desktop
```

Produces an MSI/NSIS installer in
`apps/desktop/src-tauri/target/release/bundle/`.

## Environment

Copy `.env.example` to `.env` and adjust. See `.env.example` for all keys
(Ollama URL/model, sidecar host/port, audio, wake word, privacy).

## Security & privacy

- Loopback only (`127.0.0.1`); no telemetry; raw audio not retained by
  default. See `SECURITY.md`, `PRIVACY.md`, `docs/security/`.
- No arbitrary shell/eval for the LLM; tool calls are allow-listed and
  policy-gated.

## License

MIT (see LICENSE).
