# Desktop JARVIS — Global Production Plan

> Status: Planning baseline. This document is the single source of truth for turning
> Desktop JARVIS into a global, production-grade, open-source personal AI assistant.
> It is original work: no code is copied from the projects listed below and the
> product has no runtime dependency on any of them.

## 0. Executive summary

Desktop JARVIS becomes a **privacy-first, offline-capable, cross-platform personal AI
assistant** that combines the best capabilities found across the leading open-source
assistant ecosystems, while remaining a single, self-contained package with its own
implementation. The differentiator is a **"Super Self Virtual Human"**: a persistent,
multimodal, emotionally coherent digital companion that runs locally, remembers
safely, acts only with consent, and can be extended by anyone through a documented
plugin/MCP surface.

Non-negotiables:
- Local-first: core features work with no network.
- Privacy-first: no telemetry by default; raw audio never retained by default.
- Consent-first: destructive or external actions require explicit approval unless
  the user has remembered a permission.
- Cross-platform: Windows, macOS, Linux (x64 + arm64).
- Accessibility: WCAG 2.2 AA, keyboard-first, screen-reader friendly.
- Internationalization: 15+ languages at GA, ICU message format.
- Security: loopback only, OS keychain secrets, sandboxed filesystem, signed updates.
- Testability: >= 80% line coverage on sidecar, >= 70% on frontend, E2E on 3 OSes.

## 1. Competitive landscape (top starred, similar/advanced)

Star counts are approximate (GitHub, 2026). Features are summarized from public docs.

| Project | Stars | Category | Key features to learn from |
|---|---|---|---|
| OpenClaw | ~393k | Personal agent | Multi-channel (Discord/Slack/Telegram/WhatsApp), skills, local models |
| Hermes Agent | ~256k | Personal agent | Custom endpoints, agent harness, memory |
| OpenCode | ~220k | Coding agent | TUI, MCP, plugins, session management |
| Browser Use | ~119k | Browser/computer use | Web automation, vision, Ollama support |
| OpenHands | ~92k | Coding agent | Sandboxed execution, any LLM |
| Cline | ~71k | Coding agent | 134 releases/90d, VS Code, Ollama/LM Studio |
| Goose | ~56k | Personal agent | Rust, Ollama, extensions |
| Aider | ~50k | Coding agent | Git-aware edits, voice |
| Nanobot | ~49k | Personal agent | Tiny footprint, Ollama/vLLM/LM Studio |
| Jan | ~45k | Desktop workspace | llama.cpp, offline, model hub |
| UI-TARS Desktop | ~39k | Computer use | Vision-driven desktop control |
| ZeroClaw | ~33k | Personal agent | Rust, security focus |
| NanoClaw | ~31k | Personal agent | Ollama add-on, MCP |
| AIRI | ~51k | Virtual companion | VRM/Live2D avatar, voice, game-playing, VTuber |
| Eigent | ~16k | Desktop workspace | Self-hosted mode, multi-agent |
| Agent S | ~13k | Computer use | GUI agent |
| Leon | ~17k | Personal assistant | Skills, layered memory, deterministic + agent modes |
| Khoj | ~38k | Personal assistant | Docs/PDF/Notion, custom agents, automations, WhatsApp |
| OpenJarvis | ~8k | Local-first research | Ollama quickstart, local model thesis |
| isair/jarvis | ~2k | Voice assistant | Rolling context, redaction before persistence |
| Adamdesgns/jarvis-local-assistant | ~? | Windows assistant | Wake word, tasks, doc Q&A with citations |
| Darshno/Jarvis | ~? | Local assistant | Tool-calling system control |
| PocketPaw | ~0.9k | Self-hosted | Multi-agent command center, 7-layer security |
| MIRIX | ~3.5k | Memory agent | Multi-agent memory, screen activity tracking |
| OpenVoiceOS | ~? | Voice OS | Embedded/headless voice |
| Kalliope | ~1.8k | Voice framework | Modular voice assistant framework |

Feature union we adopt (without copying code):
1. Multi-channel ingress (chat UI, voice, hotkey, tray, optional messaging bridges).
2. Provider abstraction (Ollama, OpenAI, Anthropic, Gemini, any OpenAI-compatible).
3. Layered memory (working/episodic/semantic/procedural) with redaction + retention.
4. RAG over files/docs/web with citations.
5. Tool calling with policy gating + sandbox.
6. Computer use (screen understanding + safe action execution).
7. Browser automation.
8. Multi-agent orchestration + skills + plugins + MCP client.
9. Scheduling/automations + notifications.
10. Virtual human avatar (voice + face + emotion + proactive).
11. Observability, diagnostics, repair flows.
12. Cross-platform packaging + auto-update.
13. i18n + accessibility.
14. Offline-first with graceful degradation.

## 2. Product vision

"Your private, local-first digital companion that can chat, listen, see, remember,
and act — safely, across every device you own, in your language."

Target users:
- Privacy-conscious individuals.
- Professionals needing on-device document Q&A.
- Developers wanting an extensible local agent.
- Accessibility users needing voice-first control.
- Tinkerers building virtual companions.

## 3. Global requirements

### 3.1 Functional
- FR-1 Chat (text) with streaming, markdown, code blocks, tool results.
- FR-2 Voice: push-to-talk, hands-free (online), wake word (offline), dictation mode.
- FR-3 TTS with voice selection and interruption.
- FR-4 Memory: save/recall/edit/forget, semantic search, redaction.
- FR-5 RAG: index folders/files/URLs, cite sources, incremental updates.
- FR-6 Tools: files, clipboard, notifications, scheduler, system info, web search (opt-in), app launch (allowlisted).
- FR-7 Policy: risk 0-3, approval cards, remembered permissions, audit log.
- FR-8 Computer use: screenshot + OCR/VLM + safe actions (mouse/keyboard) behind approvals.
- FR-9 Browser automation: navigate, extract, fill forms (allowlisted domains).
- FR-10 Multi-agent: planner + specialists, handoff, shared memory.
- FR-11 Skills/plugins: install, enable, disable, sandboxed.
- FR-12 MCP client: connect to local/remote MCP servers.
- FR-13 Avatar/virtual human: render, lip-sync, expressions, proactive prompts.
- FR-14 Settings: models, voice, mic, layout, privacy, updates.
- FR-15 Onboarding + diagnostics + repair.
- FR-16 Export/import data (portable memory).

### 3.2 Non-functional
- NFR-1 Performance: first token < 1.5s on mid-tier; voice RTT < 2s.
- NFR-2 Resource: idle RAM < 400MB (without model); CPU < 5% idle.
- NFR-3 Reliability: crash recovery, auto-restart sidecar, no data loss on crash.
- NFR-4 Security: no telemetry by default, loopback only, signed updates.
- NFR-5 Privacy: redaction, retention policies, local-only default.
- NFR-6 Accessibility: WCAG 2.2 AA.
- NFR-7 i18n: 15 languages, RTL support.
- NFR-8 Compatibility: Windows 10+, macOS 12+, Ubuntu 22.04+.
- NFR-9 Extensibility: stable plugin API, semver.
- NFR-10 Observability: structured logs, metrics, traces (local).

### 3.3 Global use cases
- UC-1 Offline study assistant (no internet).
- UC-2 Developer copilot (codebase Q&A via MCP).
- UC-3 Accessibility (voice-only operation).
- UC-4 Enterprise on-prem (SSO, audit, policy).
- UC-5 Low-resource (small models, quantized).
- UC-6 Multilingual households.
- UC-7 Companion (avatar, proactive).
- UC-8 Regulated (healthcare/legal) with redaction + retention.
- UC-9 Multi-device (export/import, optional sync).
- UC-10 Education (kid-safe modes, content filters).

## 4. Architecture

### 4.1 High-level
```
┌─────────────────────────────────────────────────────────────┐
│ Desktop Shell (Tauri 2 / Rust)                              │
│  - Window, tray, hotkeys, notifications, OS integration     │
│  - Sidecar lifecycle, health, loopback, secure storage       │
│  - Auto-update, installer hooks                             │
└──────────────┬──────────────────────────────────────────────┘
               │ IPC (typed, loopback HTTP + WS)
┌──────────────▼──────────────────────────────────────────────┐
│ Frontend (React + TS)                                       │
│  - Chat, voice orb, avatar canvas, settings, onboarding      │
│  - Zustand stores, React Query, i18n, a11y                  │
└──────────────┬──────────────────────────────────────────────┘
               │ HTTP/WS 127.0.0.1 (token auth)
┌──────────────▼──────────────────────────────────────────────┐
│ Sidecar (Python FastAPI)                                    │
│  - API gateway + auth + rate limit                          │
│  - Orchestrator (LLM router, tool router, policy)           │
│  - Providers (Ollama, OpenAI, Anthropic, Gemini, custom)    │
│  - Memory service (SQLite + vector index, redaction)         │
│  - RAG indexer (files, docs, web)                           │
│  - Voice service (STT, TTS, VAD, wake word)                 │
│  - Tool registry + built-in tools                           │
│  - Computer use + browser automation (sandboxed)            │
│  - Multi-agent coordinator                                  │
│  - Skills/plugins/MCP client                                │
│  - Scheduler + notifications                                │
│  - Observability (logs/metrics/traces)                      │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│ Data layer                                                  │
│  - SQLite (state, memory, audit, scheduler)                 │
│  - Vector store (sqlite-vec or embedded chroma)             │
│  - File vault (user-approved roots)                         │
│  - Config store (TOML + migrations)                         │
│  - OS keychain (secrets)                                    │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Component responsibilities

- **Rust shell**: owns process lifecycle, native OS features, security boundary.
  Never executes LLM-generated code.
- **Frontend**: presentation + user intent capture; no secrets; no direct FS.
- **Sidecar**: all AI, memory, tools, policy; loopback only; token auth.
- **Data layer**: single-writer SQLite with WAL; migrations versioned.

### 4.3 Communication
- Frontend ↔ Sidecar: HTTP REST + WebSocket for streaming; bearer token issued by Rust.
- Rust ↔ Sidecar: spawn, health probe, env, kill.
- All endpoints validated with Pydantic (sidecar) and Zod (frontend contracts).

### 4.4 Security boundaries
- Sidecar binds 127.0.0.1 only; firewall-friendly.
- CORS disabled; token required.
- File access via allowlisted roots + policy.
- Shell commands: allowlist + arg validation; no eval.
- Computer use: explicit per-action approval unless remembered.
- Secrets in OS keychain; never in logs/config.

## 5. Feature superset (union) — implementation mapping

| Capability | Module | Phase |
|---|---|---|
| Chat streaming | orchestrator | 1 |
| Provider abstraction | providers | 1 |
| Memory v1 | memory | 1 |
| Voice STT/TTS | voice | 2 |
| Wake word | voice | 2 |
| RAG | rag | 3 |
| Tool registry + policy | tools/policy | 3 |
| Scheduler | scheduler | 3 |
| Computer use | computer_use | 4 |
| Browser automation | browser | 4 |
| Multi-agent | agents | 5 |
| Skills/plugins | plugins | 5 |
| MCP client | mcp_client | 5 |
| Avatar/virtual human | avatar | 6 |
| Proactive | proactive | 6 |
| i18n/a11y/packaging | platform | 7 |
| Hardening | quality | 8 |

## 6. "Super Self Virtual Human" subsystem

Goal: a coherent digital companion, not a gimmick.

Subcomponents:
- **Persona model**: user-editable persona (name, voice, style, boundaries) stored locally.
- **Affect engine**: derives emotional state from conversation + context; drives avatar expressions and prosody.
- **Avatar renderer**: web-based 2D/3D avatar (Live2D/VRM) with lip-sync from TTS phonemes, blinking, idle motion.
- **Proactive engine**: scheduled/contextual prompts (greetings, reminders, check-ins) with user controls + quiet hours.
- **User model**: long-term preferences/habits with explicit consent, editable, deletable.
- **Safety layer**: no emotional manipulation, transparent AI disclosure, crisis resources, parental controls.
- **Multimodal**: optional local VLM for vision; camera only with explicit consent.

Rules:
- Avatar never claims to be human.
- Proactive messages are opt-in and rate-limited.
- All learned user traits are visible and deletable.

## 7. Implementation phases & milestones

### Phase 0 — Foundations (2-4w)
- Repo hygiene: CODE_OF_CONDUCT, CONTRIBUTING, SECURITY, PRIVACY, LICENSE (MIT).
- CI: lint/test/build on 3 OSes; dependency scanning; SBOM.
- Docs skeleton + ADR process.
- Definition of Done checklist.

### Phase 1 — Core chat & memory (4-6w)
- Provider abstraction + Ollama/OpenAI/Anthropic.
- Streaming chat + tool calling loop.
- Memory v1 (facts, search, redaction).
- Config migrations.
- Tests: unit + integration.

### Phase 2 — Voice (4-6w)
- STT (faster-whisper) + VAD.
- TTS (platform engines + optional Piper).
- Wake word (Porcupine optional / open alternative).
- Dictation mode.
- Mic selection + meter.

### Phase 3 — Tools & RAG (4-6w)
- Tool registry + policy engine + approvals.
- File tools + sandbox.
- RAG indexer (files/docs/URLs) + citations.
- Scheduler + notifications.

### Phase 4 — Computer use & browser (4-6w)
- Screenshot + OCR/VLM.
- Safe action execution (mouse/keyboard) with approvals.
- Browser automation (Playwright) allowlisted domains.

### Phase 5 — Multi-agent & extensibility (4-6w)
- Planner + specialists.
- Skills/plugins loader (sandboxed).
- MCP client.
- Shared memory across agents.

### Phase 6 — Virtual human (6-8w)
- Avatar renderer + lip-sync.
- Affect engine + proactive.
- User model + consent UI.
- Multimodal (optional VLM).

### Phase 7 — Globalization (4-6w)
- i18n (15 langs), RTL.
- Accessibility audit.
- Packaging + auto-update.
- Onboarding + diagnostics.

### Phase 8 — Hardening (4-6w)
- Security audit + pen test.
- Performance profiling + optimization.
- Beta program + telemetry (opt-in).
- GA release.

## 8. Module-by-module implementation steps

### 8.1 Providers (`services/assistant/src/jarvis/providers/`)
1. Define `Provider` protocol: `chat_stream`, `embed`, `models`, `health`.
2. Implement `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`, `GeminiProvider`, `OpenAICompatibleProvider`.
3. Add model router (fallback, retries, circuit breaker).
4. Config: provider profiles in TOML; secrets via keychain.
5. Tests: contract tests with recorded fixtures (no network in CI).

### 8.2 Memory (`.../memory/`)
1. Schema: entities, observations, relations, embeddings, redactions, retention.
2. CRUD + semantic search + FTS.
3. Redaction pipeline before persistence (PII patterns + user rules).
4. Retention policies + manual forget/export.
5. Tests: property tests for redaction.

### 8.3 Voice (`.../audio/`)
1. STT service (faster-whisper) with VAD segmentation.
2. TTS service (platform + Piper) with queue + interruption.
3. Wake word (optional module) behind feature flag.
4. Audio device management + meter.
5. Tests: golden audio fixtures.

### 8.4 Tools & Policy (`.../tools/`, `.../policy/`)
1. Tool interface: name, schema, risk level, handler.
2. Policy engine: evaluate risk, approvals, remembered permissions, audit.
3. Built-in tools: files (sandboxed), clipboard, notifications, scheduler, system info, web search (opt-in).
4. Approval cards in frontend.
5. Tests: policy matrix.

### 8.5 RAG (`.../rag/`)
1. Ingestion pipeline (pdf, docx, md, txt, html).
2. Chunking + embedding + index.
3. Retrieval + citation.
4. Incremental updates + deletion.
5. Tests: retrieval benchmarks.

### 8.6 Computer use & browser (`.../computer_use/`, `.../browser/`)
1. Screenshot capture + OCR/VLM.
2. Action primitives (move, click, type, scroll) behind approvals.
3. Browser automation via Playwright with domain allowlist.
4. Recording + replay for audit.
5. Tests: sandboxed VM.

### 8.7 Multi-agent (`.../agents/`)
1. Planner agent (decompose task).
2. Specialist agents (research, code, system).
3. Handoff protocol + shared memory.
4. Concurrency limits + cancellation.

### 8.8 Plugins (`.../plugins/`)
1. Manifest schema (name, version, permissions, entrypoint).
2. Loader with sandbox (subprocess or WASM).
3. Permission prompts + revocation.
4. Marketplace index (static JSON, no central dependency).

### 8.9 MCP client (`.../mcp_client/`)
1. Connect to stdio/SSE MCP servers.
2. Tool discovery + namespacing.
3. Health + reconnect.

### 8.10 Avatar (`apps/desktop/src/avatar/`)
1. Renderer (2D canvas first, then Live2D/VRM).
2. TTS phoneme → viseme mapping.
3. Affect → expression mapping.
4. Settings + accessibility (reduce motion).

### 8.11 Platform (`apps/desktop/src-tauri/`)
1. Auto-update (Tauri updater) with signing.
2. Installers per OS.
3. Tray + global hotkeys.
4. OS notifications.

## 9. API contracts (sidecar)

Base: `http://127.0.0.1:{port}/v1`, auth: `Authorization: Bearer <token>`.

Core endpoints:
- `GET /health`
- `POST /chat` (SSE stream)
- `POST /tools/{name}` (policy-gated)
- `GET/POST /memory/*`
- `GET/POST /rag/*`
- `GET/POST /voice/*`
- `GET/POST /settings`
- `GET /audit`
- `GET /diagnostics`

WebSocket `/ws` for streaming + events.

All schemas in `packages/contracts` (shared TS) and Pydantic (Python); codegen checked in CI.

## 10. Data models (SQLite)

Tables:
- `config (key, value, updated_at)`
- `conversations (id, title, created_at, updated_at)`
- `messages (id, conversation_id, role, content, tool_calls, created_at)`
- `memory_items (id, kind, content, embedding, redacted, created_at, expires_at)`
- `memory_relations (src, dst, type)`
- `documents (id, path, hash, status, indexed_at)`
- `chunks (id, document_id, text, embedding, offset)`
- `approvals (id, tool, args_hash, decision, created_at, expires_at)`
- `audit_log (id, actor, action, target, result, created_at)`
- `scheduled_jobs (id, cron, payload, enabled, last_run)`
- `plugins (id, name, version, enabled, permissions)`
- `mcp_servers (id, name, command, enabled)`

Migrations via versioned SQL files; tested rollback.

## 11. Security & privacy

- Threat model documented (STRIDE) in `docs/security/THREAT_MODEL.md`.
- Secrets in OS keychain (keyring).
- Redaction before persistence (regex + NER optional).
- Retention policies (days) per memory kind.
- Export includes redaction report.
- No telemetry by default; opt-in with preview of payload.
- Signed updates; checksum verification.
- Dependency audits in CI (npm audit, pip-audit, cargo audit).
- SBOM (CycloneDX) per release.

## 12. Testing strategy

- Unit: pytest (sidecar), vitest (frontend).
- Contract: shared schema validation.
- Integration: FastAPI TestClient + temp DB.
- E2E: Playwright + Tauri (smoke on 3 OSes).
- Security: fuzz inputs, policy matrix, redaction tests.
- Performance: benchmarks (chat latency, memory search, STT).
- Accessibility: axe-core in E2E.
- Coverage gates in CI.

## 13. Release & distribution

- Versioning: semver; changelog generated.
- Artifacts: MSI/NSIS (Windows), DMG (macOS), AppImage/deb/rpm (Linux).
- Auto-update: Tauri updater, signed.
- Channels: stable, beta, nightly.
- Docs site + quickstart.
- Community: Discord/GitHub Discussions.

## 14. Observability & ops

- Structured JSON logs (local, rotating).
- Metrics (Prometheus format, local endpoint, opt-in remote).
- Tracing (OpenTelemetry, local collector optional).
- Diagnostics bundle export (zip) for support (user-reviewed).

## 15. Contribution & governance

- ADRs for architectural decisions.
- Code review required; 2 reviewers for security-sensitive.
- Plugin API stability policy.
- Roadmap public; RFC process for major features.

## 16. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Model quality varies | High | Provider abstraction + model router + eval suite |
| Security of computer use | High | Per-action approvals, sandbox, audit |
| Privacy leaks via memory | High | Redaction, retention, export review |
| Cross-platform bugs | Medium | CI matrix + beta |
| Scope creep | High | Phase gates, MVP per phase |
| Maintainer burnout | Medium | Community governance, modular ownership |

## 17. Definition of Done (per feature)

- [ ] Design doc (ADR) approved.
- [ ] Implementation with tests (unit + integration).
- [ ] Docs updated (user + dev).
- [ ] Accessibility + i18n checked.
- [ ] Security review for risky features.
- [ ] Performance budget met.
- [ ] Telemetry events documented (if any).
- [ ] Changelog entry.

## 18. Immediate next actions (start now)

1. Create `docs/adr/` and write ADR-001 (provider abstraction).
2. Scaffold `providers/` module with protocol + Ollama.
3. Add CI workflow (lint/test/build) for 3 OSes.
4. Add redaction module with tests.
5. Add i18n framework (react-i18next) + base locale.
6. Add avatar canvas placeholder + settings toggle.

## 19. Rules for contributors (no copy, no hidden deps)

- Do not copy code from external repos; reimplement from specs.
- No runtime dependency on any single third-party assistant project.
- All third-party libs must be permissively licensed (MIT/Apache/BSD) or
  approved; document in `THIRD_PARTY.md`.
- Secrets never in code or logs.
- Every network call must be user-visible and disableable.
- Every destructive action needs approval or remembered permission.
- Tests required for new modules; coverage gates enforced.

---

This plan is living. Update via PR with ADR when scope changes.
