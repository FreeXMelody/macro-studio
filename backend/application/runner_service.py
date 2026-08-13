import threading

from backend.application.sequence_runner import PreparedJob, RunnerJob, SequenceRunner
from models import Song, SongGroup, Step
from backend.domain.runner import RunnerControl, RunnerEvent, RunnerStatus
from utils import parse_duration, render_template


class RunnerBusyError(RuntimeError):
    pass


class RunnerUnavailableError(RuntimeError):
    pass


class RunnerService:
    def __init__(
        self,
        catalog,
        event_bus,
        simulation_step_seconds=0.01,
        control=None,
        executor=None,
    ):
        self.catalog = catalog
        self.event_bus = event_bus
        self.simulation_step_seconds = max(0.0, float(simulation_step_seconds))
        self.control = control or RunnerControl()
        self.executor = executor
        self._mode = "simulation"
        self._worker = None
        self._lock = threading.RLock()

    @property
    def status(self):
        return self.control.status

    @property
    def mode(self):
        with self._lock:
            return self._mode

    @property
    def is_active(self):
        return self.status in {
            RunnerStatus.STARTING,
            RunnerStatus.RUNNING,
            RunnerStatus.PAUSED,
            RunnerStatus.STOPPING,
        }

    def start(
        self,
        active_group=None,
        loop_enabled=False,
        random_enabled=False,
        simulation=True,
    ):
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise RunnerBusyError("动作序列正在运行")
            if not simulation and self.executor is None:
                raise RunnerUnavailableError("真实自动化执行器不可用")
            jobs = self.catalog.jobs(active_group, enabled_only=True)
            self._mode = "simulation" if simulation else "real"
            self.control.reset()
            self._publish_state("start_requested")
            self._worker = threading.Thread(
                target=self._run,
                args=(jobs, bool(loop_enabled), bool(random_enabled), bool(simulation)),
                name="macro-studio-runner",
                daemon=True,
            )
            self._worker.start()
        return self.status

    def test_step(self, step, song=None):
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise RunnerBusyError("动作序列正在运行")
            if self.executor is None:
                raise RunnerUnavailableError("真实自动化执行器不可用")
            step_model = Step(**dict(step))
            song_data = dict(song or {})
            song_model = Song(
                title=str(song_data.get("title", "单步测试")),
                keyword=str(song_data.get("keyword", "测试")),
                duration_seconds=max(0, int(song_data.get("duration_seconds", 0))),
                buffer_seconds=max(0, int(song_data.get("buffer_seconds", 0))),
                enabled=True,
                step_preset="",
            )
            group_model = SongGroup(name="单步测试", songs=[song_model])
            job = RunnerJob(song=song_model, group=group_model)
            prepared = PreparedJob(
                steps=[step_model],
                label=step_model.name or "单步测试",
                group_name=group_model.name,
                preset_label="当前动作",
            )
            self._mode = "real"
            self.control.reset()
            self._publish_state("step_test_requested")
            self._worker = threading.Thread(
                target=self._run_single,
                args=(job, prepared),
                name="macro-studio-step-test",
                daemon=True,
            )
            self._worker.start()
        return self.status

    def _run_single(self, job, prepared):
        def prepare(_job):
            return self.executor.prepare_job(job, prepared)

        step = prepared.steps[0]
        self._publish_log(f"单步测试开始「{step.name}」[{step.kind}]")
        runner = SequenceRunner(
            control=self.control,
            prepare_job=prepare,
            execute_step=self.executor.execute_step,
            emit=self.event_bus.publish,
        )
        try:
            result = runner.run([job])
            if result == RunnerStatus.COMPLETED:
                self._publish_log(f"单步测试成功「{step.name}」")
            elif result == RunnerStatus.STOPPED:
                self._publish_log(f"单步测试已停止「{step.name}」")
            elif result == RunnerStatus.FAILED:
                self._publish_log(f"单步测试失败「{step.name}」")
        except Exception as exc:
            self.control.transition(RunnerStatus.FAILED)
            self.event_bus.publish(
                RunnerEvent(kind="runner.failed", status=self.control.status, data={"error": str(exc)})
            )
            self._publish_log(f"单步测试失败「{step.name}」：{exc}")
        finally:
            self.executor.cleanup()

    def _publish_log(self, message):
        self.event_bus.publish(
            RunnerEvent(
                kind="log.appended",
                status=self.control.status,
                data={"message": str(message)},
            )
        )
    def pause(self):
        changed = self.control.pause()
        if changed:
            self._publish_state("pause_requested")
        return changed

    def resume(self):
        changed = self.control.resume()
        if changed:
            self._publish_state("resume_requested")
        return changed

    def stop(self):
        was_active = self.is_active
        self.control.request_stop()
        if was_active:
            self._publish_state("stop_requested")
        return was_active

    def join(self, timeout=None):
        worker = self._worker
        if worker is not None:
            worker.join(timeout)
        return self.status

    def _run(self, jobs, loop_enabled, random_enabled, simulation):
        prepare_job = self.catalog.prepare_job
        execute_step = self._execute_simulated_step
        if not simulation:
            prepare_job = self._prepare_real_job
            execute_step = self.executor.execute_step

        runner = SequenceRunner(
            control=self.control,
            prepare_job=prepare_job,
            execute_step=execute_step,
            emit=self.event_bus.publish,
            transition_seconds=self.simulation_step_seconds if simulation else 1.0,
        )
        try:
            runner.run(jobs, loop_enabled=loop_enabled, random_enabled=random_enabled)
        except Exception as exc:
            self.control.transition(RunnerStatus.FAILED)
            self.event_bus.publish(
                RunnerEvent(
                    kind="runner.failed",
                    status=self.control.status,
                    data={"error": str(exc)},
                )
            )
        finally:
            if not simulation and self.executor is not None:
                self.executor.cleanup()

    def _prepare_real_job(self, job):
        prepared = self.catalog.prepare_job(job)
        return self.executor.prepare_job(job, prepared)

    def _execute_simulated_step(self, step, job, _prepared):
        planned_seconds = 0.0
        if step.kind == "wait":
            planned_seconds = parse_duration(render_template(step.value, job.song))
        else:
            wait_after = render_template(step.wait_after, job.song).strip()
            if wait_after:
                planned_seconds = parse_duration(wait_after)
        if planned_seconds < 0:
            raise ValueError("等待时长不能小于 0")
        if self.simulation_step_seconds:
            self.control.wait(self.simulation_step_seconds)

    def _publish_state(self, reason):
        self.event_bus.publish(
            RunnerEvent(
                kind="runner.state_changed",
                status=self.control.status,
                data={"reason": reason, "mode": self.mode},
            )
        )
