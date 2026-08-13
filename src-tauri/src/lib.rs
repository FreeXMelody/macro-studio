use serde::{Deserialize, Serialize};
use std::{
    io::{BufRead, BufReader},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
};
use tauri::{Emitter, Manager, State};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Clone, Debug, Deserialize, Serialize)]
struct SidecarConnection {
    host: String,
    port: u16,
    token: String,
    api_version: String,
}

#[derive(Debug, Deserialize)]
struct SidecarReady {
    event: String,
    host: String,
    port: u16,
    token: String,
    api_version: String,
}

#[derive(Default)]
struct SidecarRuntime {
    child: Option<Child>,
    connection: Option<SidecarConnection>,
}

#[derive(Default)]
struct SidecarState {
    runtime: Mutex<SidecarRuntime>,
}

#[tauri::command]
fn sidecar_connection(
    state: State<'_, Arc<SidecarState>>,
) -> Result<Option<SidecarConnection>, String> {
    state
        .runtime
        .lock()
        .map(|runtime| runtime.connection.clone())
        .map_err(|_| "sidecar state lock was poisoned".to_string())
}

fn development_command() -> Result<(Command, PathBuf), String> {
    let project_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .ok_or_else(|| "cannot resolve project root".to_string())?
        .to_path_buf();
    let python = std::env::var("MACRO_STUDIO_PYTHON").unwrap_or_else(|_| "python".to_string());
    let mut command = Command::new(python);
    command.args(["-m", "backend.main"]);
    Ok((command, project_root))
}

fn production_command(app: &tauri::AppHandle) -> Result<(Command, PathBuf), String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| format!("cannot resolve resource directory: {error}"))?;
    let executable = resource_dir
        .join("sidecars")
        .join("macro-studio-backend.exe");
    if !executable.is_file() {
        return Err(format!(
            "packaged Python sidecar is missing: {}",
            executable.display()
        ));
    }
    Ok((Command::new(executable), resource_dir))
}

fn start_sidecar(app: tauri::AppHandle, state: Arc<SidecarState>) -> Result<(), String> {
    let (mut command, working_directory) = if cfg!(debug_assertions) {
        development_command()?
    } else {
        production_command(&app)?
    };
    command
        .current_dir(working_directory)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .stdin(Stdio::null());
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    let mut child = command
        .spawn()
        .map_err(|error| format!("cannot start Python sidecar: {error}"))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "cannot capture Python sidecar output".to_string())?;
    state
        .runtime
        .lock()
        .map_err(|_| "sidecar state lock was poisoned".to_string())?
        .child = Some(child);

    std::thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut first_line = String::new();
        let readiness = reader
            .read_line(&mut first_line)
            .map_err(|error| format!("cannot read sidecar readiness: {error}"))
            .and_then(|_| {
                serde_json::from_str::<SidecarReady>(first_line.trim())
                    .map_err(|error| format!("invalid sidecar readiness: {error}"))
            })
            .and_then(|ready| {
                if ready.event != "sidecar.ready"
                    || ready.host != "127.0.0.1"
                    || ready.port == 0
                    || ready.token.is_empty()
                {
                    return Err("sidecar returned an invalid connection".to_string());
                }
                Ok(SidecarConnection {
                    host: ready.host,
                    port: ready.port,
                    token: ready.token,
                    api_version: ready.api_version,
                })
            });

        match readiness {
            Ok(connection) => {
                if let Ok(mut runtime) = state.runtime.lock() {
                    runtime.connection = Some(connection.clone());
                }
                let _ = app.emit("sidecar-ready", connection);
                for line in reader.lines() {
                    if line.is_err() {
                        break;
                    }
                }
                if let Ok(mut runtime) = state.runtime.lock() {
                    runtime.connection = None;
                }
                let _ = app.emit("sidecar-exited", ());
            }
            Err(message) => {
                let _ = app.emit("sidecar-error", message);
            }
        }
    });
    Ok(())
}

fn stop_sidecar(state: &SidecarState) {
    let Ok(mut runtime) = state.runtime.lock() else {
        return;
    };
    runtime.connection = None;
    if let Some(mut child) = runtime.child.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let state = Arc::new(SidecarState::default());
    let managed_state = Arc::clone(&state);
    let app = tauri::Builder::default()
        .manage(managed_state)
        .invoke_handler(tauri::generate_handler![sidecar_connection])
        .setup(|app| {
            let state = Arc::clone(&app.state::<Arc<SidecarState>>());
            start_sidecar(app.handle().clone(), state).map_err(std::io::Error::other)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Macro Studio");

    app.run(move |_app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            stop_sidecar(&state);
        }
    });
}
