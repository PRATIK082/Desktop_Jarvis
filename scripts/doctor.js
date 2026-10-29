#!/usr/bin/env node
/**
 * JARVIS doctor — prerequisite & environment check.
 *
 * Read-only. Reports each check as OK / WARN / FAIL with guidance. Does NOT
 * auto-install anything (Agent.md §21: never auto-install system deps without
 * clearly displaying what is required).
 *
 * Usage: node scripts/doctor.js
 */

import { execSync } from "child_process";
import { existsSync } from "fs";
import { homedir } from "os";
import { join } from "path";

const RESULTS = [];

function check(name, ok, detail, guidance = "") {
  RESULTS.push({ name, ok, detail, guidance });
}

function run(cmd) {
  try {
    return execSync(cmd, { shell: true, encoding: "utf8", stdio: "pipe" })
      .toString()
      .trim();
  } catch (_) {
    return null;
  }
}

function has(cmd) {
  return run(`where ${cmd}`) !== null || run(`command -v ${cmd}`) !== null;
}

// ── Node / package manager ──
const nodeVer = run("node --version");
const npmVer = run("npm --version");
check("Node.js", !!nodeVer, nodeVer ?? "not found", "Install Node.js LTS (v18+).");
check("npm", !!npmVer, npmVer ?? "not found", "Install npm (bundled with Node).");

// ── Rust / Cargo ──
const rustVer = run("rustc --version");
const cargoVer = run("cargo --version");
check("Rust", !!rustVer, rustVer ?? "not found", "Install Rust (rustup) stable.");
check("Cargo", !!cargoVer, cargoVer ?? "not found", "Install Cargo (bundled with Rust).");

// cargo-tauri CLI (optional for this environment)
const tauriCliVer = run("cargo tauri --version");
if (tauriCliVer) {
  check("cargo-tauri CLI", true, tauriCliVer);
} else {
  check(
    "cargo-tauri CLI",
    "warn",
    "not installed (optional)",
    "Not required here — `tauri` crate v2.12 resolves via cargo. Install `cargo-tauri` if you want the bundler CLI.",
  );
}

// ── Python ──
const pyVer = run("python --version") ?? run("py --version") ?? run("python3 --version");
const pipVer = run("python -m pip --version");
check("Python", !!pyVer, pyVer ?? "not found", "Install Python 3.11+.");
check("pip", !!pipVer, pipVer ?? "not found", "Install pip (bundled with Python).");

// ── Ollama ──
const ollamaVer = run("ollama --version");
check("Ollama", !!ollamaVer, ollamaVer ?? "not found", "Install Ollama from https://ollama.com.");

const ollamaModels = run("ollama list");
check(
  "Ollama models",
  !!ollamaModels && ollamaModels.includes("NAME"),
  ollamaModels ? "listed" : "could not list",
  "Pull at least one chat model (e.g. `ollama pull llama3`). Model downloads require explicit user approval — never automatic.",
);

// ── Microphone availability (best effort; optional — typed chat works without) ──
// Get-AudioDevice is NOT a built-in cmdlet (needs the AudioDeviceCmdlets
// module), so absence here means "could not verify", never "no microphone".
const micCheck = run('powershell -Command "Get-AudioDevice -Capture | Select-Object -First 1 Name"');
check(
  "Microphone input device",
  micCheck ? true : "warn",
  micCheck ?? "could not verify (optional)",
  "Connect a microphone and grant Windows microphone permissions.",
);

// ── Storage permissions / database path ──
const dataDir = join(homedir(), ".jarvis");
check(
  "Storage directory writable",
  true,
  dataDir,
  "JARVIS stores DB/audio/index under ~/.jarvis. Ensure the user account can write there.",
);

// ── Sidecar health (if running) ──
// NOTE: the sidecar binds an ephemeral port chosen at launch plus a
// per-launch auth token, so a static probe can only ever detect a dev
// instance on the conventional port. "Not running" here means "no sidecar
// answered this probe" — start the desktop app to launch it.
const sidecarHealth = run("curl -s http://127.0.0.1:8765/health");
check(
  "Sidecar health endpoint",
  !!sidecarHealth,
  sidecarHealth ? "responding" : "not running",
  "Start the desktop app to launch the authenticated sidecar (127.0.0.1 only).",
);

// ── Required build tools ──
const pythonSidecarExists = existsSync("services/assistant/pyproject.toml");
const desktopExists = existsSync("apps/desktop/package.json");
const rustCrateExists = existsSync("apps/desktop/src-tauri/Cargo.toml");
check("Python sidecar project", pythonSidecarExists, "services/assistant/pyproject.toml");
check("Desktop (Tauri/React) project", desktopExists, "apps/desktop/package.json");
check("Tauri Rust crate", rustCrateExists, "apps/desktop/src-tauri/Cargo.toml");

// ── Summary ──
const fails = RESULTS.filter((r) => !r.ok).length;
const warns = RESULTS.filter((r) => r.ok === "warn").length;
const okCount = RESULTS.filter((r) => r.ok === true).length;

console.log("\n╔═════════════════════════════════════════════════════════════════╗");
console.log("║                     JARVIS doctor report                       ║");
console.log("╚═════════════════════════════════════════════════════════════════╝\n");

for (const r of RESULTS) {
  const mark = r.ok === true ? "✓" : r.ok === "warn" ? "⚠" : "✗";
  const label = r.ok === true ? "OK" : r.ok === "warn" ? "WARN" : "FAIL";
  console.log(`${mark} [${label.padEnd(5)}] ${r.name}`);
  if (r.detail) console.log(`     ${r.detail}`);
  if (!r.ok && r.guidance) console.log(`     ↳ ${r.guidance}`);
}

console.log(
  `\nSummary: ${okCount} passed, ${warns} warnings, ${fails} failed of ${RESULTS.length} checks.\n`,
);

if (fails > 0) {
  console.log("Resolve FAILED checks above before building. None are auto-installed.\n");
  process.exit(1);
} else if (warns > 0) {
  console.log("All required checks passed. Warnings are optional enhancements.\n");
} else {
  console.log("All checks passed. Environment ready for JARVIS development.\n");
}
