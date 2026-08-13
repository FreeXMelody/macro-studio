import random
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from backend.domain.runner import RunnerControl, RunnerEvent, RunnerStatus


@dataclass(frozen=True)
class RunnerJob:
    song: Any
    group: Any


@dataclass(frozen=True)
class PreparedJob:
    steps: Sequence[Any]
    label: str
    group_name: str
    preset_label: str
    context: Any = None


class SequenceRunner:
    def __init__(
        self,
        control: RunnerControl,
        prepare_job: Callable[[RunnerJob], PreparedJob],
        execute_step: Callable[[Any, RunnerJob, PreparedJob], None],
        emit: Callable[[RunnerEvent], None] | None = None,
        shuffle: Callable[[list], None] | None = None,
        image_recovery_limit: int = 2,
    ):
        self.control = control
        self.prepare_job = prepare_job
        self.execute_step = execute_step
        self.emit = emit or (lambda _event: None)
        self.shuffle = shuffle or random.shuffle
        self.image_recovery_limit = max(0, int(image_recovery_limit))

    def run(self, jobs, loop_enabled=False, random_enabled=False):
        jobs = [job if isinstance(job, RunnerJob) else RunnerJob(**job) for job in jobs]
        self.control.transition(RunnerStatus.RUNNING)
        self._emit("runner.started", jobs=len(jobs), loop=bool(loop_enabled), random=bool(random_enabled))
        if not jobs:
            self.control.transition(RunnerStatus.COMPLETED)
            self._emit("runner.completed")
            return self.control.status
        cycle = 0
        failure = None

        while not self.control.should_stop():
            cycle += 1
            cycle_jobs = list(jobs)
            if random_enabled:
                self.shuffle(cycle_jobs)
            total_songs = len(cycle_jobs)
            if loop_enabled or random_enabled:
                self._emit(
                    "cycle.order",
                    cycle=cycle,
                    titles=[self._song_title(job) for job in cycle_jobs],
                )

            for song_index, job in enumerate(cycle_jobs, start=1):
                if self.control.should_stop():
                    break
                try:
                    prepared = self.prepare_job(job)
                except Exception as exc:
                    failure = exc
                    self.control.request_stop()
                    self._emit("runner.prepare_failed", error=str(exc))
                    break

                self._emit(
                    "song.started",
                    cycle=cycle,
                    index=song_index,
                    total=total_songs,
                    label=prepared.label,
                    group=prepared.group_name,
                    preset=prepared.preset_label,
                    loop=bool(loop_enabled),
                )
                failure = self._run_steps(job, prepared)
                if failure is not None or self.control.should_stop():
                    break

                self._emit(
                    "song.completed",
                    cycle=cycle,
                    index=song_index,
                    total=total_songs,
                    label=prepared.label,
                    loop=bool(loop_enabled),
                )
                if song_index < total_songs:
                    self._emit(
                        "song.next",
                        cycle=cycle,
                        index=song_index + 1,
                        total=total_songs,
                        loop=bool(loop_enabled),
                    )
                    if not self.control.wait(1):
                        break

            if failure is not None or self.control.should_stop() or not loop_enabled:
                break
            self._emit("cycle.next", cycle=cycle + 1)
            if not self.control.wait(1):
                break

        if failure is not None:
            self.control.transition(RunnerStatus.FAILED)
            self._emit("runner.failed", error=str(failure))
        elif self.control.should_stop():
            self.control.transition(RunnerStatus.STOPPED)
            self._emit("runner.stopped")
        else:
            self.control.transition(RunnerStatus.COMPLETED)
            self._emit("runner.completed")
        return self.control.status

    def _run_steps(self, job, prepared):
        steps = list(prepared.steps)
        step_index = 0
        recoveries = {}
        while step_index < len(steps):
            if self.control.should_stop() or not self.control.wait_until_runnable():
                return None
            step = steps[step_index]
            if not getattr(step, "enabled", True):
                step_index += 1
                continue
            self._emit("step.started", index=step_index, name=step.name, action=step.kind)
            try:
                self.execute_step(step, job, prepared)
                if self.control.should_stop():
                    return None
                self._emit("step.completed", index=step_index, name=step.name, action=step.kind)
                step_index += 1
            except Exception as exc:
                policy = self._failure_policy(step)
                if policy == "skip":
                    self._emit(
                        "step.skipped",
                        index=step_index,
                        name=step.name,
                        action=step.kind,
                        policy=policy,
                        error=str(exc),
                    )
                    step_index += 1
                    continue

                attempts = recoveries.get(step_index, 0)
                limit = self._failure_limit(step)
                if policy in {"retry_step", "previous_image"} and attempts < limit:
                    attempt = attempts + 1
                    recoveries[step_index] = attempt
                    recovery_index = step_index
                    if policy == "previous_image":
                        previous_image = next(
                            (
                                index
                                for index in range(step_index - 1, -1, -1)
                                if getattr(steps[index], "enabled", True)
                                and steps[index].kind == "image_click"
                            ),
                            None,
                        )
                        if previous_image is not None:
                            recovery_index = previous_image
                    self._emit(
                        "step.recovering",
                        index=step_index,
                        name=step.name,
                        action=step.kind,
                        policy=policy,
                        recovery_index=recovery_index,
                        recovery_name=steps[recovery_index].name,
                        rollback=recovery_index != step_index,
                        attempt=attempt,
                        limit=limit,
                        error=str(exc),
                    )
                    step_index = recovery_index
                    continue

                self._emit(
                    "step.failed",
                    index=step_index,
                    name=step.name,
                    action=step.kind,
                    policy=policy,
                    attempts=attempts,
                    limit=limit,
                    error=str(exc),
                )
                self.control.request_stop()
                return exc
        return None

    def _failure_policy(self, step):
        policy = str(getattr(step, "failure_policy", "") or "").strip()
        if not policy:
            return "previous_image" if getattr(step, "kind", "") == "image_click" else "stop"
        if policy not in {"stop", "skip", "retry_step", "previous_image"}:
            return "stop"
        return policy

    def _failure_limit(self, step):
        value = getattr(step, "failure_retries", self.image_recovery_limit)
        try:
            return max(0, min(20, int(value)))
        except (TypeError, ValueError):
            return self.image_recovery_limit
    def _emit(self, kind, **data):
        try:
            self.emit(RunnerEvent(kind=kind, status=self.control.status, data=data))
        except Exception:
            pass

    @staticmethod
    def _song_title(job):
        return str(getattr(job.song, "title", "") or "")
