import asyncio
import queue
import secrets
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.application.event_bus import EventBus
from backend.application.runner_service import RunnerBusyError, RunnerService, RunnerUnavailableError
from backend.application.run_plan_service import RunPlanService
from backend.transport.contracts import (
    HealthResponse,
    MaskImportRequest,
    PlaylistDocumentDto,
    PointCaptureArmRequest,
    PointCaptureStateResponse,
    PointPreviewRequest,
    PointPreviewResponse,
    PresetDto,
    RegionSelectionResponse,
    TargetLibraryDto,
    TargetLibraryUpdateDto,
    TemplateImportRequest,
    TemplateImportResponse,
    TargetSettingsDto,
    WindowProbeRequest,
    WindowProbeResponse,
    PreflightResponse,
    VisionTestRequest,
    VisionTestResponse,
    RunnerCommandResponse,
    RunPlanRequest,
    RunPlanResponse,
    RunnerStartRequest,
    RunnerStateResponse,
    StepTestRequest,
)

API_VERSION = "0.1.0"
SESSION_HEADER = "X-Macro-Studio-Token"
DEFAULT_ORIGINS = (
    "http://127.0.0.1:1420",
    "http://localhost:1420",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://tauri.localhost",
    "tauri://localhost",
)


def create_app(
    catalog,
    session_token,
    event_bus=None,
    runner=None,
    targets=None,
    point_capture=None,
    point_preview=None,
    region_selector=None,
    vision_tester=None,
    allowed_origins=None,
    emergency_stop=None,
    settings=None,
    window_inspector=None,
    run_plan=None,
):
    session_token = str(session_token or "")
    if not session_token:
        raise ValueError("session_token 不能为空")
    event_bus = event_bus or EventBus()
    runner = runner or RunnerService(catalog, event_bus)
    run_plan = run_plan or RunPlanService(
        catalog,
        target_provider=targets.document if targets is not None else None,
        template_validator=targets.template_path if targets is not None else None,
    )

    @asynccontextmanager
    async def lifespan(_app):
        if emergency_stop is not None:
            emergency_stop.start()
        if point_capture is not None:
            point_capture.start()
        try:
            yield
        finally:
            if emergency_stop is not None:
                emergency_stop.stop()
            if point_capture is not None:
                point_capture.stop()
            runner.stop()
            await asyncio.to_thread(runner.join, 2.0)

    app = FastAPI(
        title="Macro Studio Local API",
        version=API_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins or DEFAULT_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=[SESSION_HEADER, "Content-Type"],
    )
    app.state.catalog = catalog
    app.state.event_bus = event_bus
    app.state.runner = runner
    app.state.targets = targets
    app.state.point_capture = point_capture
    app.state.point_preview = point_preview
    app.state.region_selector = region_selector
    app.state.vision_tester = vision_tester
    app.state.run_plan = run_plan
    app.state.session_token = session_token

    def require_session(
        supplied_token: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
    ):
        if supplied_token is None or not secrets.compare_digest(supplied_token, session_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的会话令牌")

    authorized = [Depends(require_session)]

    @app.get("/api/health", response_model=HealthResponse, dependencies=authorized)
    def health():
        return HealthResponse(
            api_version=API_VERSION,
            runner_status=runner.status.value,
        )

    @app.get("/api/playlists", response_model=PlaylistDocumentDto, dependencies=authorized)
    def get_playlists():
        return catalog.playlists_document()

    @app.put("/api/playlists", response_model=PlaylistDocumentDto, dependencies=authorized)
    def put_playlists(document: PlaylistDocumentDto):
        try:
            return catalog.replace_playlists(document.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    @app.get("/api/presets", response_model=list[PresetDto], dependencies=authorized)
    def get_presets():
        return catalog.presets_document()

    @app.put("/api/presets", response_model=list[PresetDto], dependencies=authorized)
    def put_presets(presets: list[PresetDto]):
        try:
            return catalog.replace_presets([preset.model_dump() for preset in presets])
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    def require_targets():
        if targets is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="目标库服务不可用")
        return targets

    @app.get("/api/targets", response_model=TargetLibraryDto, dependencies=authorized)
    def get_targets():
        return require_targets().document()

    @app.put("/api/targets", response_model=TargetLibraryDto, dependencies=authorized)
    def put_targets(payload: TargetLibraryUpdateDto):
        try:
            return require_targets().replace(
                payload.document.model_dump(),
                payload.point_renames,
                payload.image_target_renames,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    @app.post("/api/targets/templates", response_model=TemplateImportResponse, dependencies=authorized)
    def import_template(payload: TemplateImportRequest):
        try:
            return require_targets().import_template(payload.target_name, payload.data_url, payload.filename)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    @app.post("/api/targets/masks", response_model=TemplateImportResponse, dependencies=authorized)
    def import_mask(payload: MaskImportRequest):
        try:
            return require_targets().import_mask(payload.target_name, payload.data_url, payload.filename)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    @app.get("/api/targets/{target_name}/mask", dependencies=authorized)
    def get_mask(target_name: str):
        try:
            return FileResponse(require_targets().mask_path(target_name))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get("/api/targets/{target_name}/template", dependencies=authorized)
    def get_template(target_name: str):
        try:
            return FileResponse(require_targets().template_path(target_name))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    def require_capability(value, message):
        if value is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)
        return value

    @app.post("/api/targets/point-capture/arm", response_model=PointCaptureStateResponse, dependencies=authorized)
    def arm_point_capture(payload: PointCaptureArmRequest):
        try:
            return require_capability(point_capture, "点位采集服务不可用").arm(payload.group_name, payload.point_name)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    @app.get("/api/targets/point-capture", response_model=PointCaptureStateResponse, dependencies=authorized)
    def get_point_capture():
        return require_capability(point_capture, "点位采集服务不可用").state()

    @app.post("/api/targets/point-capture/cancel", response_model=PointCaptureStateResponse, dependencies=authorized)
    def cancel_point_capture():
        return require_capability(point_capture, "点位采集服务不可用").cancel()

    @app.post("/api/targets/point-preview", response_model=PointPreviewResponse, dependencies=authorized)
    def preview_point(payload: PointPreviewRequest):
        try:
            return require_capability(point_preview, "点位预览服务不可用").preview(
                payload.name,
                payload.x,
                payload.y,
                payload.duration,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.post("/api/targets/select-region", response_model=RegionSelectionResponse, dependencies=authorized)
    def select_region():
        try:
            return require_capability(region_selector, "选区服务不可用").select()
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.post("/api/targets/test-image", response_model=VisionTestResponse, dependencies=authorized)
    def test_image(payload: VisionTestRequest):
        try:
            return require_capability(vision_tester, "视觉测试服务不可用").test(payload.target.model_dump())
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    @app.get("/api/settings", response_model=TargetSettingsDto, dependencies=authorized)
    def get_settings():
        return require_capability(settings, "设置服务不可用").document()

    @app.put("/api/settings", response_model=TargetSettingsDto, dependencies=authorized)
    def put_settings(document: TargetSettingsDto):
        try:
            return require_capability(settings, "设置服务不可用").replace(document.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    @app.post("/api/settings/probe", response_model=WindowProbeResponse, dependencies=authorized)
    def probe_target_window(payload: WindowProbeRequest):
        try:
            return require_capability(window_inspector, "窗口诊断服务不可用").probe(payload.window_hint, payload.capture)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    @app.get("/api/settings/preflight", response_model=PreflightResponse, dependencies=authorized)
    def preflight():
        return require_capability(window_inspector, "窗口诊断服务不可用").preflight()
    @app.get("/api/runner", response_model=RunnerStateResponse, dependencies=authorized)
    def get_runner():
        return RunnerStateResponse(
            status=runner.status.value,
            active=runner.is_active,
            mode=runner.mode,
        )

    @app.post("/api/runner/plan", response_model=RunPlanResponse, dependencies=authorized)
    def inspect_run_plan(command: RunPlanRequest):
        return require_capability(run_plan, "运行计划分析服务不可用").inspect(command.active_group)

    @app.post("/api/runner/start", response_model=RunnerCommandResponse, dependencies=authorized)
    def start_runner(command: RunnerStartRequest):
        try:
            current_status = runner.start(
                active_group=command.active_group,
                loop_enabled=command.loop,
                random_enabled=command.random,
                simulation=command.simulation,
            )
        except RunnerBusyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except RunnerUnavailableError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return RunnerCommandResponse(status=current_status.value, mode=runner.mode)

    @app.post("/api/runner/test-step", response_model=RunnerCommandResponse, dependencies=authorized)
    def test_runner_step(command: StepTestRequest):
        try:
            current_status = runner.test_step(
                command.step.model_dump(),
                command.song.model_dump() if command.song else None,
            )
        except RunnerBusyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except RunnerUnavailableError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return RunnerCommandResponse(status=current_status.value, mode=runner.mode)
    @app.post("/api/runner/pause", response_model=RunnerCommandResponse, dependencies=authorized)
    def pause_runner():
        changed = runner.pause()
        return RunnerCommandResponse(status=runner.status.value, changed=changed, mode=runner.mode)

    @app.post("/api/runner/resume", response_model=RunnerCommandResponse, dependencies=authorized)
    def resume_runner():
        changed = runner.resume()
        return RunnerCommandResponse(status=runner.status.value, changed=changed, mode=runner.mode)

    @app.post("/api/runner/stop", response_model=RunnerCommandResponse, dependencies=authorized)
    def stop_runner():
        changed = runner.stop()
        return RunnerCommandResponse(status=runner.status.value, changed=changed, mode=runner.mode)

    @app.websocket("/api/events")
    async def events(websocket: WebSocket, token: str = ""):
        if not token or not secrets.compare_digest(token, session_token):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="无效的会话令牌")
            return
        await websocket.accept()
        subscription = event_bus.subscribe()
        try:
            await websocket.send_json(
                {
                    "sequence": 0,
                    "timestamp": time.time(),
                    "type": "connection.ready",
                    "status": runner.status.value,
                    "data": {"api_version": API_VERSION},
                }
            )
            last_heartbeat = time.monotonic()
            while True:
                try:
                    event = await asyncio.to_thread(subscription.get, 0.5)
                    await websocket.send_json(event.to_dict())
                except queue.Empty:
                    if time.monotonic() - last_heartbeat >= 10.0:
                        await websocket.send_json(
                            {
                                "sequence": 0,
                                "timestamp": time.time(),
                                "type": "connection.heartbeat",
                                "status": runner.status.value,
                                "data": {},
                            }
                        )
                        last_heartbeat = time.monotonic()
        except WebSocketDisconnect:
            pass
        finally:
            subscription.close()

    return app
