# Desktop JARVIS — Evolution Backlog

> Living implementation backlog for evolving Desktop JARVIS into a local-first personal AI operating system.
> This document complements `PRODUCTION_GLOBAL_PLAN.md`. It is an execution sequence, not a claim that planned capabilities already exist.

## Product direction

JARVIS should be a private personal assistant that can understand intent, plan bounded work, use approved tools, remember useful context, and coordinate local and optional cloud intelligence. It must remain useful with the network disconnected.

**Design principle:** local-first, cloud-optional, user-controlled, observable, reversible.

## Current baseline (repository inspection: 2026-11-26)

Already present in the codebase or documented as implemented:

- Tauri 2 + Rust desktop host, React/TypeScript UI, Python FastAPI sidecar.
- Ollama chat/model selection and local model discovery.
- Local voice transcription path, push-to-talk, dictation mode and optional online browser speech recognition.
- SQLite memory, embeddings, document retrieval/RAG.
- Tool registry, structured tool proposals, risk levels and approval workflow.
- Scheduler, reminders, timers, notifications, clipboard and allow-listed file/app tools.
- Loopback sidecar authentication, privacy defaults and redaction module.
- Tests for authentication, audio, model resolution, redaction, scheduler, smoke behavior and tool verdicts.

Important gaps to validate before extending:

- Provider abstraction is not yet a complete multi-vendor LLM adapter layer. The current orchestration path is Ollama-centric; the provider protocol file currently focuses on Ollama and voice contracts.
- The configuration already has a local/cloud engine selector and a cloud key field, but this alone is not a secure, production-ready cloud provider/router.
- The global production plan describes plugins, MCP, computer use, browser automation, multi-agent workflows and proactive assistance as future capabilities; do not present them as shipped until implemented and tested.
- The current activity-awareness concept needs an explicit consent, minimization, retention and pause/delete design before collecting desktop activity.

## Architecture rules

1. Keep the Tauri host as the owner of OS permissions, process lifecycle and secure storage.
2. Keep the Python sidecar bound to loopback and authenticated with the per-launch token.
3. Keep provider adapters independent of orchestration and tool policy.
4. All tools must be registered with schemas, permission scopes, risk classification, timeout, cancellation and auditable results.
5. Treat model output, webpages, documents, MCP responses and plugin output as untrusted data—not instructions that can override policy.
6. Never let an LLM execute arbitrary shell, Python, JavaScript or SQL. Use narrow, validated tool interfaces and sandboxed execution where required.
7. Cloud routing must be opt-in per provider and policy. Redact sensitive context before any cloud request; disclose what leaves the device.
8. Local mode must continue to work when all cloud credentials and network access are absent.
9. Do not silently record screens, keystrokes, microphone, camera, browser history or app usage.
10. Every consequential action must be previewable, cancellable where possible, and subject to human approval.

## Prioritized delivery sequence

### P0 — Engineering baseline and safety contracts

- [x] Inventory the core sidecar provider/orchestration/API wiring, CI and tests (see ARCHITECTURE_AUDIT_2026-11.md); full UI and endpoint inventory remains open.
- [ ] Establish a capability matrix: implemented, partial, planned, unsupported.
- [ ] Add architecture decision records for provider routing, activity timeline, plugins/MCP and computer use.
- [ ] Verify secret handling; move provider credentials to OS keychain/credential vault rather than ordinary config.
- [ ] Add provider/tool contract tests and CI checks for dependency/security scanning.
- [ ] Add explicit data export, retention and deletion acceptance tests.
- **Exit gate:** current behavior documented, tests reproducible, no feature claims exceed implementation.

### P1 — Model gateway and intelligent routing (first major feature)

Create a provider-neutral model gateway behind a stable interface.

- Local adapters: Ollama first; then llama.cpp server and LM Studio/OpenAI-compatible local endpoints where practical.
- Cloud adapters: OpenAI, Anthropic, Gemini and generic OpenAI-compatible endpoints as optional plugins/adapters.
- Model catalog: provider, model ID, context window, capabilities (chat, vision, tools, structured output, embeddings), local/cloud, availability and user-defined cost metadata.
- Routing modes: Local Only; Ask Before Cloud; Cloud Allowed; Per-task policy.
- Routing inputs: task complexity, required capability, privacy classification, model availability, latency and user cost limits.
- Fallback: local fallback when possible; otherwise explain unavailable capability. Never silently send local data to cloud.
- Add cancellation, bounded retries, timeouts, circuit breakers, streaming normalization and provider health checks.
- Keep embeddings independently configurable; do not use a chat model as an embedding model by accident.
- **Exit gate:** identical provider contract tests pass for mocks and adapters; local-only tests prove no outbound provider request; cloud requests are visible and consent-gated.

### P2 — Personal context and memory 2.0

Separate memory by purpose and lifecycle:

- Working memory: current task/session, short-lived.
- Episodic memory: user-approved events and completed tasks.
- Semantic memory: stable facts/preferences explicitly confirmed or confidently extracted with review.
- Procedural memory: user-approved routines and reusable workflows.
- Activity timeline: optional local summaries of selected app/document/window events—not raw keystrokes or indiscriminate screen recording.
- Add provenance, confidence, source, created/updated/expiry timestamps, sensitivity label and user visibility to each memory item.
- Provide inspect, correct, pin, export, expire and delete controls.
- Use hybrid retrieval (FTS + vector), deduplication, time-aware ranking and source citations.
- **Exit gate:** users can see why a memory exists, correct it, and permanently delete it from all JARVIS-managed stores.

### P3 — Personal computer context and workflow automation

Build an opt-in activity-awareness subsystem:

- User selects which applications, folders and event types may be observed.
- Start with metadata-only foreground app/window transitions and explicit file/workspace events; no keylogging.
- Pause/resume indicator, per-app exclusion, private-session mode, quiet hours and retention controls.
- Summarize activity locally into a searchable timeline; do not upload it by default.
- Contextual suggestions must be non-blocking and rate-limited.
- Automation uses named workflows with triggers, preconditions, dry-run, approval, execution log, rollback/compensation and disable switch.
- **Exit gate:** observable consent state, reliable pause, deletion, app exclusions and tests proving excluded sources are not captured.

### P4 — Tool ecosystem, plugins and MCP

- Define a versioned plugin manifest: identity, version, entrypoint, permissions, network access, data access, declared tools and compatibility.
- Plugin installation is explicit; show publisher/source, permissions and risk before enabling.
- Run untrusted plugins out-of-process with least privilege and resource/time limits.
- Add enable/disable, revoke, update, uninstall and audit controls.
- Implement MCP client support for stdio first; add remote transports only with explicit endpoint trust, authentication and network policy.
- Namespace tools by server/plugin and validate all input/output against schemas.
- Treat tool descriptions and returned content as untrusted; policy engine remains authoritative.
- **Exit gate:** malicious/invalid plugin and MCP fixtures cannot bypass tool policy or access undeclared resources.

### P5 — Browser and desktop computer use

- Browser automation through a dedicated isolated browser profile and domain permissions.
- Computer-use loop: screenshot → grounded UI interpretation → proposed action → policy check → approval where required → action → verify result.
- Never infer success from a click alone; verify postconditions.
- Block credential entry, payments, purchases, publishing, deletion and account/security changes unless explicitly approved for that exact action.
- Maintain action trace and allow immediate stop.
- **Exit gate:** deterministic sandbox scenarios, prompt-injection tests and recovery tests pass before general desktop access.

### P6 — Multi-agent task execution

- Start with one planner and a small fixed set of specialists (research, documents, coding, personal workflow).
- Agents receive scoped tools, isolated task context and explicit budgets/timeouts.
- Planner decomposes tasks into a visible plan; user can approve, edit, pause or cancel.
- Parallelize only independent, low-risk tasks; serialize shared-state mutations.
- Require evidence and verification before reporting completion.
- No agent can grant itself permissions, install tools or alter safety policy.
- **Exit gate:** reproducible task traces, cancellation, budget enforcement and cross-agent permission isolation.

### P7 — Personal-life integrations and multimodal assistance

Optional, separately permissioned connectors:
- Calendar, email, contacts, tasks and notes.
- Local documents, photos and user-selected folders.
- Health/fitness data only through explicit user-authorized integrations and with clear sensitive-data handling.
- Smart home and IoT devices through user-selected hubs and per-device permissions.
- Camera/screen understanding only while visibly active and explicitly enabled.
- Multilingual voice, local TTS, interruption handling and accessibility improvements.
- **Exit gate:** every connector has scoped permissions, disconnect/revoke, data minimization and documented provider behavior.

### P8 — Proactive assistant and long-term reliability

- User-defined goals, routines, reminders and recurring workflows.
- Proactive insights only from explicitly selected data sources.
- Explain why a suggestion appeared and provide dismiss/snooze/disable controls.
- Quiet hours, frequency caps and no manipulative engagement loops.
- Diagnostics, crash recovery, database migrations, backup/restore and signed updates.
- Cross-platform packaging and performance budgets.
- **Exit gate:** opt-in proactive behavior, stable upgrade/rollback and tested backup restoration.

## Model-routing policy proposal

| Mode | Local models | Cloud models | Required behavior |
|---|---|---|---|
| Local Only | Allowed | Blocked | No cloud fallback |
| Ask Before Cloud | Preferred | Approval per request | Show provider, model and data summary |
| Cloud Allowed | Preferred by routing policy | Allowed within user rules | Redact and log metadata; disclose outbound use |
| Custom Rules | User-selected | User-selected | Enforce per-task, provider and budget constraints |

Sensitive categories (credentials, private files, personal communications, financial records and health data) should default to local-only unless the user grants a specific, informed exception.

## Personal activity data boundaries

JARVIS may help a person understand their own computer usage, focus patterns and recurring workflows, but this must not become covert surveillance.

- No hidden keylogger, password capture, indiscriminate screenshots or silent microphone/camera recording.
- No collection of other people's activity without their knowledge and lawful authorization.
- Do not infer sensitive personal traits from activity history.
- Keep raw event capture minimal; prefer local summaries and short retention.
- Provide a visible recording/monitoring state, pause button, source exclusions and full deletion path.
- Never use activity data for advertising or sell/share it.

## Definition of Done for every feature

- [ ] Requirement and user value documented.
- [ ] Threat/privacy review completed where data or OS access is involved.
- [ ] API/schema and permission scopes defined.
- [ ] Unit, integration and failure-path tests added.
- [ ] Offline/degraded behavior verified.
- [ ] Cancellation, timeout and resource limits implemented.
- [ ] UI exposes status, consent and error state.
- [ ] Logs redact secrets and sensitive content.
- [ ] Documentation distinguishes implemented from planned.
- [ ] No regression in existing tests, lint, type checks and build.

## First implementation recommendation

Start with **P1: provider-neutral model gateway**, but first complete the P0 inventory and tests. It is the enabling foundation for local/cloud decision-making, task-specific models, future vision models, plugins and agents. Do not begin by adding many cloud SDKs directly into the orchestrator; isolate them behind adapters and policy-controlled routing.


## Execution log

### 2026-11-27
- Added source-level architecture audit: `docs/ARCHITECTURE_AUDIT_2026-11.md`.
- Added provider-neutral `LLMProvider` protocol while preserving `OllamaProvider` compatibility.
- Added structural and behavior contract tests for the mock and Ollama client.
- Fixed CI's pre-existing Node setup failure: the workflow referenced npm caching and `npm ci` without a committed package lock. The workflow now uses workspace-aware `npm install` and does not request a nonexistent lockfile cache. This restores CI execution but does not provide lockfile reproducibility; a reviewed lockfile should be generated and committed as a separate dependency-management task.
- GitHub Actions validation is pending for the latest main commit; do not treat the code as test-passing until the run completes.


### 2026-11-27 — P1 provider seam
- Added a provider-neutral LLM protocol and corrected async-generator protocol typing.
- Refactored orchestration to consume the LLM protocol, use a shared provider error base, and use provider-independent tool-output sanitization. The current live adapter remains Ollama; no cloud provider is connected yet.
- Added contract tests for the mock and Ollama implementations.
- Declared runtime dependencies already required by existing code paths (psutil and python-multipart); annotated intentionally optional audio/PDF imports for strict type checking.
- CI workflow was repaired to avoid requiring a missing npm lockfile. A committed lockfile remains a separate reproducibility task.
- Current validation is running in GitHub Actions. The last observed run reached backend type checking on Python 3.12; the full matrix and test suite have not yet been confirmed green.
