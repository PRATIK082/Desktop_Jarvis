# Desktop JARVIS — Architecture Audit

**Audit date:** 2026-11-26  
**Baseline:** `main` at `d8beab952122bf6f12bd66d1ab524dba474721fd`  
**Scope:** repository structure, sidecar configuration, provider contracts, orchestration, API wiring, CI and existing tests.  
**Purpose:** record verified implementation boundaries before provider-gateway work. This is a source inspection, not a claim that runtime tests were executed.

## Executive finding

The repository has a sound local-first foundation, but the LLM provider abstraction is incomplete in the runtime path. The current chat path is Ollama-specific from API construction through orchestration. The accepted ADR-001 describes a provider-neutral design, but implementation has not yet completed that decision.

The next safe step is to introduce a provider-neutral LLM contract and make orchestration depend on that contract while retaining Ollama as the only production adapter. Cloud adapters and automatic routing must follow only after this seam is tested.

## Verified repository baseline

| Layer | Verified implementation | Boundary / gap |
|---|---|---|
| Desktop | Tauri 2 / Rust host, React + TypeScript UI | Desktop owns process lifecycle and OS integration |
| Sidecar | Python 3.11+, FastAPI, Pydantic v2, HTTPX | Local sidecar; loopback and launch-token model documented |
| LLM transport | `jarvis.api.ollama.OllamaClient` | Concrete Ollama HTTP client |
| Provider contracts | `providers/base.py` has STT, TTS, wake-word and Ollama protocols/mocks | No general LLM protocol consumed by orchestrator |
| Orchestration | `Orchestrator` accepts concrete `OllamaClient` | Imports Ollama exception type and sanitization helper |
| API wiring | `api/app.py` lazily creates one Ollama client and injects it | No provider registry or task-aware routing |
| Configuration | Ollama URL/model/timeout; engine selector local/cloud; one cloud API key setting | Engine selector is a coarse realtime-engine selector, not a per-request LLM router |
| Privacy | Redaction module; telemetry off and raw audio retention off by default | Cloud egress policy, data classification and OS keychain integration need verification |
| Memory | SQLite, embeddings, retrieval and RAG modules | Existing memory must remain local by default |
| Tools | Registry, policy engine and approval flow | Provider must not gain authority to bypass tool policy |
| CI | Python 3.11/3.12, Node 20/24; frontend checks, Ruff, mypy, pytest, Rust check | Dependency audits currently use `|| true`; these are informational, not release gates |
| Tests | Auth, audio, model resolution, redaction, scheduler, smoke and tool-verdict tests | No general LLM-provider contract suite or routing/privacy-egress tests identified |

## Key source files inspected

- `services/assistant/pyproject.toml`
- `services/assistant/src/jarvis/config.py`
- `services/assistant/src/jarvis/providers/base.py`
- `services/assistant/src/jarvis/api/ollama.py`
- `services/assistant/src/jarvis/api/app.py`
- `services/assistant/src/jarvis/orchestration/orchestrator.py`
- `services/assistant/src/jarvis/engines/__init__.py`
- `services/assistant/tests/test_model_resolution.py`
- `docs/adr/ADR-001-provider-abstraction.md`
- `.github/workflows/ci.yml`

## Confirmed design decisions to preserve

1. Local Ollama remains the default and must work without cloud credentials or network access.
2. No model downloads without explicit user approval.
3. Provider implementations load lazily; optional providers must not make startup fail.
4. The sidecar stays bound to loopback and requires its per-launch authentication token.
5. Tool calls continue through the existing schema validation, policy engine and approval path.
6. Provider errors are structured and must never be emitted as speakable raw exception text.
7. Embedding model selection remains separate from chat model selection.
8. No secrets in logs, ordinary configuration, frontend state or committed files.
9. Cloud requests must be opt-in and must not happen as an invisible fallback.
10. Existing API/event behavior should remain backward-compatible during the provider seam refactor.

## Hardware-aware operating envelope

Primary development machine: **16 GB system RAM, NVIDIA GPU with 8–12 GB VRAM**.

Initial tuning targets (guidance, not benchmark claims):

- Prefer a single active 7B–8B quantized chat model for general tasks.
- Use smaller specialist models only when their task-specific benefit justifies model swapping.
- Keep embeddings on a separate small embedding model; avoid loading a second large chat model concurrently.
- Treat 14B-class models as experimental on this machine and measure CPU offload, context size and latency before recommending them.
- Keep context budgets bounded and expose model memory requirements in the model picker where metadata is available.
- Route high-complexity or unsupported-capability tasks to cloud only under the explicit user policy; otherwise explain the limitation.

## Prioritized implementation gaps

### P0 — baseline and safety
- [x] Inspect runtime wiring, configuration, tests and CI.
- [x] Record verified architecture and concrete gaps.
- [ ] Verify key storage and secret lifecycle in the Rust host before enabling cloud credentials.
- [ ] Add test execution evidence from a clean checkout/CI run.

### P1 — provider-neutral LLM gateway
- [ ] Define shared request/response/stream and capability contracts.
- [ ] Make orchestrator depend on the LLM contract, not Ollama concrete class.
- [ ] Keep Ollama adapter behavior and current error event semantics unchanged.
- [ ] Add provider contract tests with deterministic fakes.
- [ ] Add explicit routing modes: Local Only, Ask Before Cloud, Cloud Allowed.
- [ ] Add cloud adapters only after secret storage, redaction and outbound-consent gates are implemented.
- [ ] Prove Local Only makes zero cloud-provider calls.

## Risks and non-goals for this increment

- Do not add cloud SDK dependencies yet.
- Do not wire a cloud API key from the existing generic config field into a provider.
- Do not silently fall back to cloud when Ollama is unavailable.
- Do not refactor the voice STT/TTS engine selection as part of the LLM gateway.
- Do not change tool permissions or the approval model.
- Do not claim tests passed unless executed by CI or a local test run.

## Audit conclusion

Proceed with a narrow P1 foundation: a typed provider-neutral LLM interface and contract tests, preserving Ollama as the only live provider. Add cloud providers and intelligent routing in later, independently reviewable increments.
