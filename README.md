# JARVIS Desktop

Privacy-first local desktop voice assistant. Runs entirely on your machine
(Tauri 2 desktop shell + Python AI sidecar + Ollama). No cloud, no telemetry.

## Prerequisites

- Node.js 20+ and npm 10+
- Rust stable + cargo
- Python 3.11+
- Ollama (local) with at least one chat model, e.g. `ollama pull qwen2.5:3b`
- (optional) `ollama pull nomic-embed-text` for memory search

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

## Tests & quality

```bash
npm test          # frontend + backend tests
npm run lint      # eslint + ruff
npm run format    # prettier + ruff format
```

## Package for release

```bash
npm run package:desktop
```

## License

MIT (see LICENSE).
