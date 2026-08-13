import argparse
import json
import os
import secrets
import socket

import uvicorn

from backend.application.catalog_service import CatalogService
from backend.application.event_bus import EventBus
from backend.application.runner_service import RunnerService
from backend.application.target_service import TargetService
from backend.application.settings_service import SettingsService
from backend.domain.runner import RunnerControl, RunnerEvent
from backend.infrastructure.emergency_hotkey import EmergencyStopMonitor
from backend.infrastructure.config_repository import ConfigRepository
from backend.infrastructure.json_storage import load_json, save_json
from backend.infrastructure.point_capture import PointCaptureMonitor
from backend.infrastructure.point_preview import PointPreviewService
from backend.infrastructure.region_selector import RegionSelector
from backend.infrastructure.vision_test_service import VisionTestService
from backend.infrastructure.target_window import TargetWindowInspector
from backend.infrastructure.windows_executor import WindowsActionExecutor
from backend.transport.http_api import create_app


APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(APP_DIR, "macro_config.json")
PLAYLIST_PATH = os.path.join(APP_DIR, "playlist.json")
SESSION_TOKEN_ENV = "MACRO_STUDIO_SESSION_TOKEN"


def build_application(session_token=None, config_path=CONFIG_PATH, playlist_path=PLAYLIST_PATH):
    config_repository = ConfigRepository(config_path)
    config_data = config_repository.load()
    playlist_data = load_json(playlist_path, [], document_type="playlist")

    def load_current_config():
        return config_repository.load()

    def save_playlists(document):
        save_json(playlist_path, document, document_type="playlist")

    def save_presets(presets):
        def mutate(document):
            document["step_presets"] = presets
            names = {str(preset.get("name", "")).strip() for preset in presets}
            active_name = str(document.get("active_step_preset", "")).strip()
            if active_name not in names:
                active_name = str(presets[0].get("name", "")).strip() if presets else ""
            document["active_step_preset"] = active_name
            active = next(
                (preset for preset in presets if str(preset.get("name", "")).strip() == active_name),
                None,
            )
            document["steps"] = [dict(step) for step in active.get("steps", [])] if active else []

        config_repository.mutate(mutate)

    catalog = CatalogService.from_documents(
        config_data,
        playlist_data,
        save_playlists=save_playlists,
        save_presets=save_presets,
    )
    def save_targets(targets, point_renames, image_target_renames):
        def mutate(document):
            document["active_point_group"] = targets["active_point_group"]
            document["point_groups"] = targets["point_groups"]
            active_group = next(
                (group for group in targets["point_groups"] if group["name"] == targets["active_point_group"]),
                targets["point_groups"][0],
            )
            document["points"] = active_group["points"]
            document["image_targets"] = targets["image_targets"]
            for step in document.get("steps", []):
                _replace_target_reference(step, point_renames, image_target_renames)
            for preset in document.get("step_presets", []):
                for step in preset.get("steps", []):
                    _replace_target_reference(step, point_renames, image_target_renames)

        config_repository.mutate(mutate)

    targets = TargetService(
        config_data,
        base_dir=os.path.dirname(os.path.abspath(config_path)),
        save_targets=save_targets,
        replace_references=catalog.replace_target_references,
    )
    event_bus = EventBus()
    control = RunnerControl()

    def publish_log(message):
        event_bus.publish(
            RunnerEvent(
                kind="log.appended",
                status=control.status,
                data={"message": str(message)},
            )
        )

    point_preview = PointPreviewService()
    executor = WindowsActionExecutor(
        control=control,
        config_provider=load_current_config,
        base_dir=os.path.dirname(os.path.abspath(config_path)),
        emit_log=publish_log,
        point_visualizer=point_preview.flash,
    )
    runner = RunnerService(
        catalog,
        event_bus,
        control=control,
        executor=executor,
    )

    def emergency_stop():
        if runner.stop():
            publish_log("F9 急停：已请求停止当前动作序列")

    hotkey_monitor = EmergencyStopMonitor(emergency_stop)
    point_capture = PointCaptureMonitor()
    region_selector = RegionSelector(config_provider=load_current_config)
    vision_tester = VisionTestService(
        config_provider=load_current_config,
        base_dir=os.path.dirname(os.path.abspath(config_path)),
    )
    settings = SettingsService(config_repository)
    window_inspector = TargetWindowInspector(config_provider=load_current_config)
    token = session_token or os.environ.get(SESSION_TOKEN_ENV) or secrets.token_urlsafe(32)
    return create_app(
        catalog,
        token,
        event_bus=event_bus,
        runner=runner,
        targets=targets,
        point_capture=point_capture,
        point_preview=point_preview,
        region_selector=region_selector,
        vision_tester=vision_tester,
        emergency_stop=hotkey_monitor,
        settings=settings,
        window_inspector=window_inspector,
    )


def _replace_target_reference(step, point_renames, image_target_renames):
    if not isinstance(step, dict):
        return
    if step.get("kind") == "click" and step.get("target") in point_renames:
        step["target"] = point_renames[step["target"]]
    if step.get("kind") == "image_click" and step.get("value") in image_target_renames:
        step["value"] = image_target_renames[step["value"]]
    if step.get("verify_target") in image_target_renames:
        step["verify_target"] = image_target_renames[step["verify_target"]]


app = build_application()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Macro Studio local sidecar API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("sidecar 只允许监听本机地址")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", args.port))
    server_socket.listen(128)
    port = server_socket.getsockname()[1]
    readiness = {
        "event": "sidecar.ready",
        "host": "127.0.0.1",
        "port": port,
        "token": app.state.session_token,
        "api_version": app.version,
    }
    print(json.dumps(readiness, ensure_ascii=True), flush=True)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run(sockets=[server_socket])


if __name__ == "__main__":
    main()
