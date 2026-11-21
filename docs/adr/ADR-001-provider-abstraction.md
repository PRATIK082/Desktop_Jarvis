# ADR-001: Provider abstraction

Status: Accepted

## Context
Desktop JARVIS must support multiple LLM providers (Ollama, OpenAI, Anthropic,
Gemini, any OpenAI-compatible) without coupling orchestration to one vendor.

## Decision
Define provider protocols in `services/assistant/src/jarvis/providers/base.py`
(STT, TTS, wake word, LLM). Implementations live in sibling modules. Orchestration
depends only on protocols; concrete providers are injected via config.

## Consequences
- Mock providers keep tests hermetic.
- Adding a provider requires implementing the protocol + registration.
- Degraded mode possible when a provider is unavailable.
