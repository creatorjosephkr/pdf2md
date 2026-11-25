use serde::Serialize;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, RunEvent, State};

struct SidecarState {
    child: Mutex<Option<Child>>,
    engine_url: String,
}

#[derive(Serialize)]
struct AppMeta {
    os: &'static str,
    arch: &'static str,
    version: &'static str,
    is_tauri: bool,
}

fn find_available_port() -> u16 {
    if TcpListener::bind("127.0.0.1:18765").is_ok() {
        return 18765;
    }
    if let Ok(listener) = TcpListener::bind("127.0.0.1:0") {
        if let Ok(addr) = listener.local_addr() {
            return addr.port();
        }
    }
    18765
}

fn locate_engine_dir(app_handle: &tauri::AppHandle) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(env_dir) = std::env::var("PDF_CONVERT_ENGINE_DIR") {
        candidates.push(PathBuf::from(env_dir));
    }

    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("engine"));
        candidates.push(cwd.join("../engine"));
        candidates.push(cwd.join("../../engine"));
        candidates.push(cwd.join("../../../engine"));
    }

    // Compile-time manifest path fallback for dev launches from Finder/Xcode
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    candidates.push(manifest_dir.join("../../../engine"));

    if let Ok(res_dir) = app_handle.path().resource_dir() {
        candidates.push(res_dir.join("engine"));
    }

    for cand in candidates {
        if cand.join("pyproject.toml").exists() {
            if let Ok(canon) = cand.canonicalize() {
                return Some(canon);
            }
            return Some(cand);
        }
    }
    None
}

fn spawn_python_sidecar(engine_dir: &Path, port: u16) -> Option<Child> {
    let port_str = port.to_string();

    // Prefer synced .venv python directly for fastest startup without uv lock overhead
    let venv_python = if cfg!(target_os = "windows") {
        engine_dir.join(".venv").join("Scripts").join("python.exe")
    } else {
        engine_dir.join(".venv").join("bin").join("python")
    };

    if venv_python.exists() {
        if let Ok(child) = Command::new(&venv_python)
            .args([
                "-m",
                "pdf_convert_engine.server.app",
                "--host",
                "127.0.0.1",
                "--port",
                &port_str,
            ])
            .current_dir(engine_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
        {
            return Some(child);
        }
    }

    // Fallback to `uv run pdf-convert-server`
    let uv_bin = if Path::new("/opt/homebrew/bin/uv").exists() {
        "/opt/homebrew/bin/uv"
    } else {
        "uv"
    };

    Command::new(uv_bin)
        .args([
            "run",
            "pdf-convert-server",
            "--host",
            "127.0.0.1",
            "--port",
            &port_str,
        ])
        .current_dir(engine_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .ok()
}

#[tauri::command]
fn get_engine_url(state: State<'_, SidecarState>) -> String {
    state.engine_url.clone()
}

#[tauri::command]
fn get_app_meta() -> AppMeta {
    AppMeta {
        os: std::env::consts::OS,
        arch: std::env::consts::ARCH,
        version: env!("CARGO_PKG_VERSION"),
        is_tauri: true,
    }
}

#[tauri::command]
fn reveal_in_folder(path: String) -> Result<(), String> {
    let target = Path::new(&path);
    if !target.exists() {
        return Err(format!("Path does not exist: {path}"));
    }

    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .args(["-R", &path])
            .spawn()
            .map_err(|e| e.to_string())?;
    }

    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(format!("/select,{}", path))
            .spawn()
            .map_err(|e| e.to_string())?;
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let parent = target.parent().unwrap_or(target);
        Command::new("xdg-open")
            .arg(parent)
            .spawn()
            .map_err(|e| e.to_string())?;
    }

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let external_url = std::env::var("PDF_CONVERT_API_URL").ok();
    let (engine_url, spawn_port) = match external_url {
        Some(url) if !url.trim().is_empty() => (url, None),
        _ => {
            let port = find_available_port();
            (format!("http://127.0.0.1:{port}"), Some(port))
        }
    };

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState {
            child: Mutex::new(None),
            engine_url: engine_url.clone(),
        })
        .setup(move |app| {
            if let Some(port) = spawn_port {
                if let Some(engine_dir) = locate_engine_dir(app.handle()) {
                    if let Some(child) = spawn_python_sidecar(&engine_dir, port) {
                        let state = app.state::<SidecarState>();
                        if let Ok(mut guard) = state.child.lock() {
                            *guard = Some(child);
                        };
                    }
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_engine_url,
            get_app_meta,
            reveal_in_folder
        ])
        .build(tauri::generate_context!())
        .expect("error while building PDF 얼개 (PDF Eolgae)");

    app.run(|app_handle, event| {
        if let RunEvent::Exit | RunEvent::ExitRequested { .. } = event {
            let state = app_handle.state::<SidecarState>();
            if let Ok(mut guard) = state.child.lock() {
                if let Some(mut child) = guard.take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            };
        }
    });
}
