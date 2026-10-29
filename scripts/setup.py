#!/usr/bin/env python3
"""
JARVIS Desktop — local setup script.

Read-only where possible; installs Python dependencies and creates local-only
files (.env, logs/) that are never committed to git. Does NOT auto-install
system-level dependencies (Node, Rust, Python, Ollama) — it reports what is
missing and exits non-zero so the user can install them manually.

Usage:
    python scripts/setup.py          # full check + install Python deps
    python scripts/setup.py --check  # prerequisite check only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import sys
from pathlib import Path

if sys.platform == "win32":
    PYTHON_CMD = ["py", "--version"]
    PIP_CMD = ["py", "-m", "pip", "--version"]
else:
    PYTHON_CMD = ["python", "--version"]
    PIP_CMD = ["python", "-m", "pip", "--version"]

REPO_ROOT = Path(__file__).resolve().parent.parent
SIDECAR_DIR = REPO_ROOT / "services" / "assistant"

PREREQS: list[tuple[str, list[str]]] = [
    ("node", ["node", "--version"]),
    ("npm", ["npm", "--version"]),
    ("python", PYTHON_CMD),
    ("pip", PIP_CMD),
    ("rustc", ["rustc", "--version"]),
    ("cargo", ["cargo", "--version"]),
    ("ollama", ["ollama", "--version"]),
]


def run(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=REPO_ROOT
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"


def check_prereq(name: str, cmd: list[str]) -> bool:
    code, out, _ = run(cmd)
    if code == 0:
        print(f"  [OK] {name}: {out.splitlines()[0] if out else 'ok'}")
        return True
    print(f"  [FAIL] {name}: not found (run: {cmd[0]} --version)")
    return False


def check_ollama_models() -> bool:
    code, out, _ = run(["ollama", "list"])
    if code != 0:
        print("  [FAIL] ollama models: could not list (is Ollama running?)")
        return False
    lines = [l for l in out.splitlines() if l.strip() and not l.startswith("NAME")]
    if not lines:
        print("  [WARN] ollama models: none installed (pull one: ollama pull llama3.2)")
        return True  # warning, not fatal
    print(f"  [OK] ollama models: {len(lines)} installed")
    return True


def install_python_deps() -> bool:
    print("  → Installing Python sidecar dependencies...")
    code, out, err = run([sys.executable, "-m", "pip", "install", "-e", "."])
    if code != 0:
        print(f"  [FAIL] pip install failed:\n{err}")
        return False
    print("  [OK] Python dependencies installed")
    return True


def create_env() -> None:
    env_example = REPO_ROOT / ".env.example"
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        print(f"  ↳ .env already exists, leaving untouched")
        return
    if env_example.exists():
        shutil.copy(env_example, env_file)
        print(f"  [OK] created .env from .env.example (edit as needed)")
    else:
        print(f"  [WARN] .env.example not found, skipping .env creation")


def ensure_dirs() -> None:
    for d in [REPO_ROOT / "logs", REPO_ROOT / ".jarvis", SIDECAR_DIR / "logs"]:
        d.mkdir(parents=True, exist_ok=True)
    print("  [OK] local data dirs ensured (logs/, .jarvis/) — not committed to git")


def run_tests() -> bool:
    print("  → Running sidecar smoke tests...")
    code, out, err = run([sys.executable, "-m", "pytest", "-q"])
    if code != 0:
        print(f"  [FAIL] tests failed:\n{err}\n{out}")
        return False
    print(f"  [OK] tests passed: {out.strip().splitlines()[-1] if out.strip() else ''}")
    return True


def check_only() -> int:
    print("=== JARVIS prerequisite check ===")
    all_ok = True
    for name, cmd in PREREQS:
        if not check_prereq(name, cmd):
            all_ok = False
    check_ollama_models()
    if all_ok:
        print("\nAll prerequisites present.")
    else:
        print("\nSome prerequisites are missing — install them, then re-run setup.")
    return 0 if all_ok else 1


def full_setup() -> int:
    print("=== JARVIS local setup ===\n")
    print("[1/5] Prerequisite check...")
    if check_only() != 0:
        return 1

    print("\n[2/5] Creating local config & data dirs...")
    create_env()
    ensure_dirs()

    print("\n[3/5] Installing Python sidecar dependencies...")
    if not install_python_deps():
        return 1

    print("\n[4/5] Running smoke tests...")
    if not run_tests():
        print("  [WARN] tests had failures — review above, but setup can continue")

    print("\n[5/5] Setup complete.")
    print("\nNext steps:")
    print("  - Start Ollama: ollama serve")
    print("  - Pull a model (requires your approval): ollama pull llama3.2")
    print("  - Run the desktop app: npm run dev:tauri   (from repo root)")
    print("  - Or run doctor:    node scripts/doctor.js")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS local setup")
    parser.add_argument(
        "--check", action="store_true", help="prerequisite check only"
    )
    args = parser.parse_args()

    if args.check:
        return check_only()
    return full_setup()


if __name__ == "__main__":
    sys.exit(main())
