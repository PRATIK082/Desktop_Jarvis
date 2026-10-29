# JARVIS Desktop — build / dev commands

# Install everything
bootstrap:
	npm run bootstrap

# Verify prerequisites (doctor)
doctor:
	npm run doctor

# Start desktop in dev mode (Tauri + Python sidecar)
dev:
	npm run dev:tauri

# Start frontend only
dev:frontend:
	npm run dev --workspace=apps/desktop

# Run all tests
test:
	npm test

# Frontend tests only
test:frontend:
	npm test --workspace=apps/desktop

# Backend (Python) tests only
test:backend:
	cd services/assistant && python -m pytest

# Lint everything
lint:
	npm run lint

# Format everything
format:
	npm run format

# Rust fmt + clippy
rust:fmt:
	cargo fmt --workspace -- --check
rust:clippy:
	cargo clippy --workspace -- -D warnings

# Package desktop for release
package:
	npm run package:desktop

# Clean build artifacts
clean:
	npm run clean

.PHONY: bootstrap doctor dev dev:frontend test test:frontend test:backend lint format rust:fmt rust:clippy package clean
