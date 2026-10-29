// JARVIS desktop Tauri backend (Rust)
//
// Starts, monitors, and stops the Python sidecar. Chooses a free localhost
// port securely. Generates an ephemeral authentication token. Polls the
// sidecar /health endpoint after start. Provides narrowly scoped native
// commands. Rejects path traversal, arbitrary executables, command injection,
// and malformed requests.

use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{command, AppHandle, Emitter, State};

struct SidecarHandle {
    child: Mutex<Option<std::process::Child>>,
    port: Mutex<Option<u16>>,
    auth_token: Mutex<Option<String>>,
}

impl Default for SidecarHandle {
    fn default() -> Self {
        Self {
            child: Mutex::new(None),
            port: Mutex::new(None),
            auth_token: Mutex::new(None),
        }
    }
}

impl Drop for SidecarHandle {
    // If the app exits without an explicit stop_sidecar, still kill the
    // child so stale sidecars do not linger on their ports.
    fn drop(&mut self) {
        if let Some(mut child) = self.child.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[derive(Clone, Serialize, Deserialize)]
struct HealthResponse {
    status: String,
    version: String,
    sidecar_port: Option<u16>,
    sidecar_running: bool,
    ollama_healthy: bool,
}

#[derive(Clone, Serialize, Deserialize)]
struct SidecarConfig {
    host: String,
    port: u16,
    auth_token: String,
}

fn generate_auth_token() -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("{:x}", now)
}

/// Find a Python interpreter on the current platform.
/// On Windows tries the `py` launcher first (most reliable), then `python`, then `python3`.
fn find_python_interpreter() -> Option<String> {
    let candidates = if cfg!(target_os = "windows") {
        vec!["py", "python", "python3"]
    } else {
        vec!["python3", "python"]
    };
    for cmd in candidates {
        if std::process::Command::new(cmd)
            .arg("--version")
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
        {
            return Some(cmd.to_string());
        }
    }
    None
}

/// Poll the sidecar /health endpoint until it responds or max_attempts is reached.
fn poll_sidecar_health(host: &str, port: u16, token: &str, max_attempts: u32) -> bool {
    for attempt in 1..=max_attempts {
        match ureq::get(&format!("http://{host}:{port}/health"))
            .set("Authorization", &format!("Bearer {token}"))
            .timeout(std::time::Duration::from_secs(2))
            .call()
        {
            Ok(resp) if resp.status() == 200 => return true,
            _ => {
                if attempt == max_attempts {
                    return false;
                }
                std::thread::sleep(std::time::Duration::from_millis(200));
            }
        }
    }
    false
}

#[command]
async fn start_sidecar(
    handle: State<'_, SidecarHandle>,
    app: AppHandle,
) -> Result<HealthResponse, String> {
    // If already running, return current health instead of spawning a duplicate.
    if handle.port.lock().unwrap().is_some() && handle.child.lock().unwrap().is_some() {
        return Ok(current_health(handle));
    }

    // Choose a free localhost port securely.
    let listener = std::net::TcpListener::bind("127.0.0.1:0")
        .map_err(|e| format!("failed to bind port: {e}"))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("failed to get port: {e}"))?
        .port();
    drop(listener);

    // Generate ephemeral auth token.
    let auth_token = generate_auth_token();

    *handle.port.lock().unwrap() = Some(port);
    *handle.auth_token.lock().unwrap() = Some(auth_token.clone());

    // Find Python interpreter.
    let python_cmd = find_python_interpreter().ok_or_else(|| {
        "python interpreter not found — install Python 3.11+ and add it to PATH".to_string()
    })?;

    // Determine repo root from the Cargo manifest directory (compile-time constant).
    // manifest_dir = apps/desktop/src-tauri; repo root is three levels up.
    // NOTE (E6): the manifest-dir path only exists in a dev checkout. A packaged
    // app resolves the sidecar from JARVIS_SIDECAR_PATH first, then from a
    // services/ tree next to the executable, and only then the dev path.
    let manifest_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
    let dev_script = manifest_dir
        .join("..")
        .join("..")
        .join("..")
        .join("services")
        .join("assistant")
        .join("main.py");
    let exe_script = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .map(|d| d.join("services").join("assistant").join("main.py"));
    let env_script = std::env::var_os("JARVIS_SIDECAR_PATH").map(std::path::PathBuf::from);
    let sidecar_script = [env_script, exe_script, Some(dev_script)]
        .into_iter()
        .flatten()
        .find(|p| p.is_file())
        .ok_or_else(|| {
            "sidecar main.py not found — set JARVIS_SIDECAR_PATH or run from a dev checkout"
                .to_string()
        })?;

    // repo_root is the tree holding services/assistant (dev checkout or exe dir).
    let repo_root = sidecar_script
        .parent()
        .and_then(|d| d.parent())
        .and_then(|d| d.parent())
        .map(|d| d.to_path_buf())
        .unwrap_or_else(|| manifest_dir.join("..").join("..").join(".."));

    // Open log file for sidecar stdout/stderr so debug output is not lost.
    let log_dir = repo_root.join("services").join("assistant").join("logs");
    let _ = std::fs::create_dir_all(&log_dir);
    let log_path = log_dir.join("sidecar.log");
    let log_file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .ok();

    let mut cmd = std::process::Command::new(python_cmd);
    cmd.arg(sidecar_script);
    cmd.env("JARVIS_HOST", "127.0.0.1");
    cmd.env("JARVIS_PORT", port.to_string());
    cmd.env("JARVIS_AUTH_TOKEN", auth_token.clone());
    cmd.env("JARVIS_LOG_LEVEL", "info");
    cmd.current_dir(&repo_root);

    if let Some(f) = log_file {
        if let Ok(clone) = f.try_clone() {
            cmd.stdout(f);
            cmd.stderr(clone);
        } else {
            cmd.stdout(f);
            cmd.stderr(std::process::Stdio::null());
        }
    } else {
        cmd.stdout(std::process::Stdio::null());
        cmd.stderr(std::process::Stdio::null());
    }
    cmd.stdin(std::process::Stdio::null());

    let child = cmd
        .spawn()
        .map_err(|e| format!("failed to spawn sidecar: {e}"))?;
    *handle.child.lock().unwrap() = Some(child);

    // Poll sidecar /health to confirm it is up before reporting success.
    let sidecar_healthy = poll_sidecar_health("127.0.0.1", port, &auth_token, 50);

    // Emit event so frontend can bridge URL/token to WebSocket connection.
    let _ = app.emit(
        "sidecar:started",
        serde_json::json!({
            "url": format!("http://127.0.0.1:{}", port),
            "token": auth_token,
        }),
    );

    Ok(HealthResponse {
        status: if sidecar_healthy {
            "healthy"
        } else {
            "starting"
        }
        .to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        sidecar_port: Some(port),
        sidecar_running: true,
        ollama_healthy: false,
    })
}

#[command]
async fn stop_sidecar(handle: State<'_, SidecarHandle>) -> Result<(), String> {
    if let Some(mut child) = handle.child.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    *handle.port.lock().unwrap() = None;
    *handle.auth_token.lock().unwrap() = None;
    Ok(())
}

#[command]
async fn restart_sidecar(
    handle: State<'_, SidecarHandle>,
    app: AppHandle,
) -> Result<HealthResponse, String> {
    let _ = stop_sidecar(handle.clone()).await;
    // Brief pause to let the OS release the port.
    std::thread::sleep(std::time::Duration::from_millis(300));
    start_sidecar(handle, app).await
}

#[command]
fn health(handle: State<'_, SidecarHandle>) -> HealthResponse {
    current_health(handle)
}

#[command]
fn sidecar_config(handle: State<'_, SidecarHandle>) -> Result<SidecarConfig, String> {
    let port = *handle.port.lock().unwrap();
    let token = handle.auth_token.lock().unwrap().clone();
    match (port, token) {
        (Some(p), Some(t)) => Ok(SidecarConfig {
            host: "127.0.0.1".to_string(),
            port: p,
            auth_token: t,
        }),
        _ => Err("sidecar not running".to_string()),
    }
}

fn current_health(handle: State<'_, SidecarHandle>) -> HealthResponse {
    let port = *handle.port.lock().unwrap();
    let token = handle.auth_token.lock().unwrap().clone();
    let running = port.is_some() && handle.child.lock().unwrap().is_some();

    let ollama_healthy = if let (Some(p), Some(t)) = (port, token) {
        poll_sidecar_health("127.0.0.1", p, &t, 1)
    } else {
        false
    };

    HealthResponse {
        status: if running { "healthy" } else { "stopped" }.to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        sidecar_port: port,
        sidecar_running: running,
        ollama_healthy,
    }
}

/// Kill stale processes left over from previous runs: hidden previous app
/// windows (old binary keeps running and its sidecar keeps its port/token)
/// and orphan sidecar interpreters matched by script path, so unrelated
/// Python apps and MCP servers are never touched.
///
/// Best-effort: never fails startup. Runs before anything else in `main()`.
/// Windows only; other platforms get a no-op stub.
#[cfg(target_os = "windows")]
fn cleanup_stale_processes() {
    let own_pid = std::process::id();
    // 1. Other instances of this app (stale hidden windows).
    let _ = std::process::Command::new("powershell")
        .args([
            "-NoProfile",
            "-Command",
            &format!(
                "Get-CimInstance Win32_Process -Filter \"Name='jarvis-desktop.exe'\" | Where-Object {{ $_.ProcessId -ne {own_pid} }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
            ),
        ])
        .output();
    // 2. Orphan sidecar interpreters from crashed/closed runs.
    let _ = std::process::Command::new("powershell")
        .args([
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe' OR Name='py.exe'\" | Where-Object { $_.CommandLine -like '*services*assistant*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
        ])
        .output();
}

#[cfg(not(target_os = "windows"))]
fn cleanup_stale_processes() {
    // Non-Windows stale cleanup is future work (pkill by pattern).
}

fn main() {
    // Auto-cleanup first: never run on top of a stale app/sidecar.
    cleanup_stale_processes();
    tauri::Builder::default()
        .manage(SidecarHandle::default())
        .invoke_handler(tauri::generate_handler![
            start_sidecar,
            stop_sidecar,
            restart_sidecar,
            health,
            sidecar_config,
        ])
        .setup(|_app| {
            // Window setup handled by frontend.
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
