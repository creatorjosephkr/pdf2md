use serde::Serialize;
use std::fs::{self, OpenOptions};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{Manager, RunEvent, State};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[derive(Clone, Serialize)]
struct SidecarStatus {
    phase: String,
    message: String,
    log_path: Option<String>,
    last_log: Option<String>,
}

struct SidecarState {
    child: Mutex<Option<Child>>,
    status: Mutex<SidecarStatus>,
    engine_url: String,
    spawn_port: Option<u16>,
}

#[derive(Serialize)]
struct AppMeta {
    os: &'static str,
    arch: &'static str,
    version: &'static str,
    is_tauri: bool,
}

#[derive(Serialize)]
struct StagedPdf {
    staged_path: String,
    original_name: String,
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

fn apply_no_window(cmd: &mut Command) {
    #[cfg(target_os = "windows")]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = cmd;
    }
}

fn augmented_path() -> String {
    let cur = std::env::var("PATH").unwrap_or_default();
    if cfg!(target_os = "windows") {
        let mut extras: Vec<String> = Vec::new();
        if let Ok(up) = std::env::var("USERPROFILE") {
            extras.push(format!("{up}\\.local\\bin"));
            extras.push(format!("{up}\\.cargo\\bin"));
        }
        if let Ok(la) = std::env::var("LOCALAPPDATA") {
            extras.push(format!("{la}\\Programs\\uv"));
        }
        if !cur.is_empty() {
            extras.push(cur);
        }
        extras.join(";")
    } else {
        let home = std::env::var("HOME").unwrap_or_default();
        let mut extras = vec![
            "/opt/homebrew/bin".to_string(),
            "/usr/local/bin".to_string(),
        ];
        if !home.is_empty() {
            extras.push(format!("{home}/.local/bin"));
            extras.push(format!("{home}/.cargo/bin"));
        }
        if !cur.is_empty() {
            extras.push(cur);
        }
        extras.join(":")
    }
}

fn locate_engine_source(app_handle: &tauri::AppHandle) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(env_dir) = std::env::var("PDF_CONVERT_ENGINE_DIR") {
        candidates.push(PathBuf::from(env_dir));
    }

    if !cfg!(debug_assertions) {
        if let Ok(res_dir) = app_handle.path().resource_dir() {
            candidates.push(res_dir.join("engine"));
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("engine"));
        candidates.push(cwd.join("../engine"));
        candidates.push(cwd.join("../../engine"));
        candidates.push(cwd.join("../../../engine"));
    }

    if cfg!(debug_assertions) {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        candidates.push(manifest_dir.join("../../../engine"));
        if let Ok(res_dir) = app_handle.path().resource_dir() {
            candidates.push(res_dir.join("engine"));
        }
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

fn locate_uv_binary(app_handle: &tauri::AppHandle) -> Option<PathBuf> {
    let exe_name = if cfg!(target_os = "windows") {
        "uv.exe"
    } else {
        "uv"
    };

    if let Ok(res_dir) = app_handle.path().resource_dir() {
        let bundled = res_dir.join("bin").join(exe_name);
        if bundled.is_file() {
            return Some(bundled);
        }
    }

    if let Ok(env_uv) = std::env::var("UV_BIN") {
        let p = PathBuf::from(env_uv);
        if p.is_file() {
            return Some(p);
        }
    }

    let mut standard: Vec<PathBuf> = Vec::new();
    if cfg!(target_os = "windows") {
        if let Ok(up) = std::env::var("USERPROFILE") {
            standard.push(PathBuf::from(&up).join(".local").join("bin").join("uv.exe"));
            standard.push(PathBuf::from(&up).join(".cargo").join("bin").join("uv.exe"));
        }
        if let Ok(la) = std::env::var("LOCALAPPDATA") {
            standard.push(PathBuf::from(&la).join("Programs").join("uv").join("uv.exe"));
        }
    } else {
        standard.push(PathBuf::from("/opt/homebrew/bin/uv"));
        standard.push(PathBuf::from("/usr/local/bin/uv"));
        if let Ok(home) = std::env::var("HOME") {
            standard.push(PathBuf::from(&home).join(".local/bin/uv"));
            standard.push(PathBuf::from(&home).join(".cargo/bin/uv"));
        }
    }

    for cand in standard {
        if cand.is_file() {
            return Some(cand);
        }
    }

    Some(PathBuf::from(exe_name))
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<(), String> {
    fs::create_dir_all(dst).map_err(|e| format!("Failed to create {}: {e}", dst.display()))?;
    let entries = fs::read_dir(src).map_err(|e| format!("Failed to read {}: {e}", src.display()))?;
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let name = entry.file_name();
        let name_str = name.to_string_lossy();
        if name_str == "__pycache__" || name_str.ends_with(".pyc") {
            continue;
        }
        let from = entry.path();
        let to = dst.join(&name);
        if from.is_dir() {
            copy_dir_recursive(&from, &to)?;
        } else {
            fs::copy(&from, &to)
                .map_err(|e| format!("Failed to copy {} -> {}: {e}", from.display(), to.display()))?;
        }
    }
    Ok(())
}

fn prepare_runtime_engine_dir(
    engine_source: &Path,
    app_handle: &tauri::AppHandle,
) -> Result<(PathBuf, bool), String> {
    let dev_venv = if cfg!(target_os = "windows") {
        engine_source.join(".venv").join("Scripts").join("python.exe")
    } else {
        engine_source.join(".venv").join("bin").join("python")
    };
    if dev_venv.is_file() {
        return Ok((engine_source.to_path_buf(), true));
    }

    let data_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("Failed to resolve app_data_dir: {e}"))?;
    let runtime_dir = data_dir.join("engine-runtime");
    fs::create_dir_all(&runtime_dir)
        .map_err(|e| format!("Failed to create {}: {e}", runtime_dir.display()))?;

    let app_ver = env!("CARGO_PKG_VERSION");
    let marker_file = runtime_dir.join(".source_version");
    let current_marker = fs::read_to_string(&marker_file).unwrap_or_default();

    let needs_sync_files = current_marker.trim() != app_ver
        || !runtime_dir.join("pyproject.toml").is_file()
        || !runtime_dir.join("src").is_dir();

    if needs_sync_files {
        fs::copy(
            engine_source.join("pyproject.toml"),
            runtime_dir.join("pyproject.toml"),
        )
        .map_err(|e| format!("Failed to copy pyproject.toml: {e}"))?;

        let src_lock = engine_source.join("uv.lock");
        if src_lock.is_file() {
            fs::copy(&src_lock, runtime_dir.join("uv.lock"))
                .map_err(|e| format!("Failed to copy uv.lock: {e}"))?;
        }

        let dst_src = runtime_dir.join("src");
        if dst_src.exists() {
            let _ = fs::remove_dir_all(&dst_src);
        }
        copy_dir_recursive(&engine_source.join("src"), &dst_src)?;
        let _ = fs::write(&marker_file, app_ver);
    }

    Ok((runtime_dir, false))
}

fn read_last_log_line(log_path: &Path) -> Option<String> {
    let raw = fs::read_to_string(log_path).ok()?;
    raw.lines()
        .rev()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .map(|line| {
            if line.chars().count() > 140 {
                let tail: String = line.chars().take(140).collect();
                format!("{tail}…")
            } else {
                line.to_string()
            }
        })
}

fn update_sidecar_status(
    app_handle: &tauri::AppHandle,
    phase: &str,
    message: &str,
    log_path: Option<&Path>,
    last_log: Option<String>,
) {
    let state = app_handle.state::<SidecarState>();
    let next = SidecarStatus {
        phase: phase.to_string(),
        message: message.to_string(),
        log_path: log_path.map(|p| p.display().to_string()),
        last_log,
    };
    if let Ok(mut guard) = state.status.lock() {
        *guard = next;
    };
}

fn launch_sidecar_background(app_handle: tauri::AppHandle, port: u16) {
    std::thread::spawn(move || {
        let log_dir = app_handle
            .path()
            .app_data_dir()
            .unwrap_or_else(|_| std::env::temp_dir().join("pdf-eolgae"));
        let _ = fs::create_dir_all(&log_dir);
        let log_path = log_dir.join("sidecar.log");
        let _ = fs::write(
            &log_path,
            format!("=== PDF Eolgae v{} sidecar boot ===\n", env!("CARGO_PKG_VERSION")),
        );

        let engine_source = match locate_engine_source(&app_handle) {
            Some(p) => p,
            None => {
                update_sidecar_status(
                    &app_handle,
                    "error",
                    "번들된 Python 변환 엔진(engine/)을 찾지 못했습니다.",
                    Some(&log_path),
                    None,
                );
                return;
            }
        };

        let (runtime_dir, is_dev_venv) = match prepare_runtime_engine_dir(&engine_source, &app_handle) {
            Ok(res) => res,
            Err(err) => {
                update_sidecar_status(
                    &app_handle,
                    "error",
                    &format!("엔진 런타임 준비 실패: {err}"),
                    Some(&log_path),
                    None,
                );
                return;
            }
        };

        let venv_python = if cfg!(target_os = "windows") {
            runtime_dir.join(".venv").join("Scripts").join("python.exe")
        } else {
            runtime_dir.join(".venv").join("bin").join("python")
        };
        let ready_marker = runtime_dir.join(format!(".venv_ready_{}", env!("CARGO_PKG_VERSION")));

        if !is_dev_venv && (!venv_python.is_file() || !ready_marker.is_file()) {
            let uv_bin = match locate_uv_binary(&app_handle) {
                Some(p) => p,
                None => {
                    update_sidecar_status(
                        &app_handle,
                        "error",
                        "uv 런타임 관리자를 찾을 수 없습니다.",
                        Some(&log_path),
                        None,
                    );
                    return;
                }
            };

            update_sidecar_status(
                &app_handle,
                "bootstrapping",
                "Python 3.12 및 로컬 AI 변환 엔진 환경을 설치 중입니다 (최초 1회 약 1~2분 소요)",
                Some(&log_path),
                Some(format!("초기화 위치: {}", runtime_dir.display())),
            );

            let mut sync_cmd = Command::new(&uv_bin);
            sync_cmd
                .args(["sync", "--python", "3.12", "--no-dev"])
                .current_dir(&runtime_dir)
                .env("PATH", augmented_path())
                .env("UV_LINK_MODE", "copy");
            if runtime_dir.join("uv.lock").is_file() {
                sync_cmd.arg("--frozen");
            }
            apply_no_window(&mut sync_cmd);

            if let Ok(log_file) = OpenOptions::new().create(true).append(true).open(&log_path) {
                if let Ok(log_err) = log_file.try_clone() {
                    sync_cmd.stdout(Stdio::from(log_file)).stderr(Stdio::from(log_err));
                }
            }

            let mut sync_child = match sync_cmd.spawn() {
                Ok(ch) => ch,
                Err(err) => {
                    update_sidecar_status(
                        &app_handle,
                        "error",
                        &format!("엔진 환경 설치 실행 실패 ({}): {err}", uv_bin.display()),
                        Some(&log_path),
                        read_last_log_line(&log_path),
                    );
                    return;
                }
            };

            loop {
                match sync_child.try_wait() {
                    Ok(Some(status)) => {
                        if !status.success() {
                            update_sidecar_status(
                                &app_handle,
                                "error",
                                &format!(
                                    "엔진 패키지 설치에 실패했습니다 (종료 코드: {}). 네트워크 상태를 확인한 뒤 다시 시도해 주세요.",
                                    status.code().unwrap_or(-1)
                                ),
                                Some(&log_path),
                                read_last_log_line(&log_path),
                            );
                            return;
                        }
                        break;
                    }
                    Ok(None) => {
                        update_sidecar_status(
                            &app_handle,
                            "bootstrapping",
                            "Python 3.12 및 로컬 AI 변환 엔진 환경을 설치 중입니다 (최초 1회 약 1~2분 소요)",
                            Some(&log_path),
                            read_last_log_line(&log_path),
                        );
                        std::thread::sleep(Duration::from_millis(500));
                    }
                    Err(err) => {
                        update_sidecar_status(
                            &app_handle,
                            "error",
                            &format!("엔진 설치 상태 확인 실패: {err}"),
                            Some(&log_path),
                            read_last_log_line(&log_path),
                        );
                        return;
                    }
                }
            }

            if !venv_python.is_file() {
                update_sidecar_status(
                    &app_handle,
                    "error",
                    "가상환경 Python 바이너리가 생성되지 않았습니다.",
                    Some(&log_path),
                    read_last_log_line(&log_path),
                );
                return;
            }
            let _ = fs::write(&ready_marker, "ok");
        }

        update_sidecar_status(
            &app_handle,
            "starting",
            "로컬 변환 엔진 서버를 시작하는 중...",
            Some(&log_path),
            read_last_log_line(&log_path),
        );

        let port_str = port.to_string();
        let mut srv_cmd = Command::new(&venv_python);
        srv_cmd
            .args([
                "-m",
                "pdf_convert_engine.server.app",
                "--host",
                "127.0.0.1",
                "--port",
                &port_str,
            ])
            .current_dir(&runtime_dir)
            .env("PATH", augmented_path())
            .env("PYTHONUNBUFFERED", "1");
        apply_no_window(&mut srv_cmd);

        if let Ok(log_file) = OpenOptions::new().create(true).append(true).open(&log_path) {
            if let Ok(log_err) = log_file.try_clone() {
                srv_cmd.stdout(Stdio::from(log_file)).stderr(Stdio::from(log_err));
            }
        } else {
            srv_cmd.stdout(Stdio::null()).stderr(Stdio::null());
        }

        match srv_cmd.spawn() {
            Ok(child) => {
                let state = app_handle.state::<SidecarState>();
                if let Ok(mut guard) = state.child.lock() {
                    *guard = Some(child);
                };
                update_sidecar_status(
                    &app_handle,
                    "running",
                    "로컬 변환 엔진 실행 중",
                    Some(&log_path),
                    read_last_log_line(&log_path),
                );
            }
            Err(err) => {
                update_sidecar_status(
                    &app_handle,
                    "error",
                    &format!("로컬 변환 엔진 실행 실패: {err}"),
                    Some(&log_path),
                    read_last_log_line(&log_path),
                );
            }
        }
    });
}

#[tauri::command]
fn get_engine_url(state: State<'_, SidecarState>) -> String {
    state.engine_url.clone()
}

#[tauri::command]
fn get_sidecar_status(state: State<'_, SidecarState>) -> SidecarStatus {
    // Detect early unexpected exit of the Python server process
    if let Ok(mut child_guard) = state.child.lock() {
        if let Some(child) = child_guard.as_mut() {
            if let Ok(Some(exit_status)) = child.try_wait() {
                let code = exit_status.code().unwrap_or(-1);
                let _ = child_guard.take();
                if let Ok(mut st_guard) = state.status.lock() {
                    let tail = st_guard
                        .log_path
                        .as_deref()
                        .and_then(|p| read_last_log_line(Path::new(p)));
                    st_guard.phase = "error".to_string();
                    st_guard.message =
                        format!("로컬 엔진 프로세스가 종료되었습니다 (코드: {code}).");
                    st_guard.last_log = tail;
                }
            }
        }
    }

    state
        .status
        .lock()
        .map(|g| g.clone())
        .unwrap_or(SidecarStatus {
            phase: "error".to_string(),
            message: "엔진 상태 조회 실패".to_string(),
            log_path: None,
            last_log: None,
        })
}

#[tauri::command]
fn restart_sidecar(app_handle: tauri::AppHandle, state: State<'_, SidecarState>) {
    if let Ok(mut guard) = state.child.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
    if let Some(port) = state.spawn_port {
        update_sidecar_status(&app_handle, "starting", "로컬 엔진을 다시 시작하는 중...", None, None);
        launch_sidecar_background(app_handle, port);
    }
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
fn stage_pdf_for_engine(app_handle: tauri::AppHandle, source_path: String) -> Result<StagedPdf, String> {
    let trimmed = source_path.trim();
    let cleaned = trimmed.strip_prefix("file://").unwrap_or(trimmed);
    let src = PathBuf::from(cleaned);
    if !src.is_file() {
        return Err(format!("선택한 PDF 파일을 찾을 수 없습니다: {}", src.display()));
    }

    let original_name = src
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "document.pdf".to_string());

    let data_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("앱 데이터 폴더 확인 실패: {e}"))?;
    let inbox_dir = data_dir.join("inbox");
    fs::create_dir_all(&inbox_dir)
        .map_err(|e| format!("임시 보관 폴더 생성 실패: {e}"))?;

    // Best-effort cleanup of staged files older than 24 hours
    if let Ok(entries) = fs::read_dir(&inbox_dir) {
        let now = SystemTime::now();
        for entry in entries.flatten() {
            if let Ok(meta) = entry.metadata() {
                if let Ok(modified) = meta.modified() {
                    if let Ok(age) = now.duration_since(modified) {
                        if age.as_secs() > 86_400 {
                            let _ = fs::remove_file(entry.path());
                        }
                    }
                }
            }
        }
    }

    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    let safe_name: String = original_name
        .chars()
        .map(|c| {
            if c == '/' || c == '\\' || c == ':' {
                '_'
            } else {
                c
            }
        })
        .collect();
    let dest = inbox_dir.join(format!("{ts}_{safe_name}"));
    fs::copy(&src, &dest)
        .map_err(|e| format!("PDF 파일 복사 실패 (접근 권한을 확인해 주세요): {e}"))?;

    Ok(StagedPdf {
        staged_path: dest.display().to_string(),
        original_name,
    })
}

#[tauri::command]
fn set_window_fullscreen(window: tauri::Window, fullscreen: bool) -> Result<(), String> {
    window.set_fullscreen(fullscreen).map_err(|e| e.to_string())
}

#[tauri::command]
fn open_file_in_system(path: String) -> Result<(), String> {
    let target = Path::new(&path);
    if !target.exists() {
        return Err(format!("파일을 찾을 수 없습니다: {path}"));
    }

    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }

    #[cfg(target_os = "windows")]
    {
        let mut cmd = Command::new("cmd");
        cmd.args(["/C", "start", "", &path]);
        apply_no_window(&mut cmd);
        cmd.spawn().map_err(|e| e.to_string())?;
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }

    Ok(())
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

    let initial_status = if spawn_port.is_some() {
        SidecarStatus {
            phase: "starting".to_string(),
            message: "로컬 변환 엔진을 준비하는 중...".to_string(),
            log_path: None,
            last_log: None,
        }
    } else {
        SidecarStatus {
            phase: "running".to_string(),
            message: "외부 엔진 URL 사용 중".to_string(),
            log_path: None,
            last_log: None,
        }
    };

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState {
            child: Mutex::new(None),
            status: Mutex::new(initial_status),
            engine_url: engine_url.clone(),
            spawn_port,
        })
        .setup(move |app| {
            if let Some(port) = spawn_port {
                launch_sidecar_background(app.handle().clone(), port);
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_engine_url,
            get_sidecar_status,
            restart_sidecar,
            get_app_meta,
            stage_pdf_for_engine,
            set_window_fullscreen,
            open_file_in_system,
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
