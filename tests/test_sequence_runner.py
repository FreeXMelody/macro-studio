import threading
import time
import unittest

from backend.application.sequence_runner import PreparedJob, RunnerJob, SequenceRunner
from backend.domain.runner import RunnerControl, RunnerEvent, RunnerStatus
from models import Song, SongGroup, Step


def make_job(title="Test"):
    song = Song(title=title, keyword=title, duration_seconds=1)
    return RunnerJob(song=song, group=SongGroup(name="Group", songs=[song]))


def prepare_with(steps):
    return lambda _job: PreparedJob(
        steps=steps,
        label="Test",
        group_name="Group",
        preset_label="Preset",
    )


class RunnerControlTests(unittest.TestCase):
    def test_event_has_stable_transport_shape(self):
        event = RunnerEvent("runner.started", RunnerStatus.RUNNING, {"jobs": 2})
        self.assertEqual(
            event.to_dict(),
            {"type": "runner.started", "status": "running", "data": {"jobs": 2}},
        )

    def test_pause_resume_and_stop_transitions(self):
        control = RunnerControl()
        control.reset()
        control.transition(RunnerStatus.RUNNING)
        self.assertTrue(control.pause())
        self.assertEqual(control.status, RunnerStatus.PAUSED)
        self.assertTrue(control.resume())
        self.assertEqual(control.status, RunnerStatus.RUNNING)
        control.request_stop()
        self.assertEqual(control.status, RunnerStatus.STOPPING)
        self.assertTrue(control.should_stop())

    def test_wait_is_interrupted_by_stop(self):
        control = RunnerControl()
        control.reset()
        control.transition(RunnerStatus.RUNNING)
        result = []
        worker = threading.Thread(target=lambda: result.append(control.wait(2, poll_interval=0.01)))
        worker.start()
        time.sleep(0.03)
        control.request_stop()
        worker.join(timeout=1)
        self.assertEqual(result, [False])


class SequenceRunnerTests(unittest.TestCase):
    def run_steps(self, steps, execute, recovery_limit=2):
        control = RunnerControl()
        control.reset()
        events = []
        runner = SequenceRunner(
            control=control,
            prepare_job=prepare_with(steps),
            execute_step=execute,
            emit=events.append,
            image_recovery_limit=recovery_limit,
        )
        status = runner.run([make_job()])
        return status, events, control

    def test_runs_enabled_steps_and_completes(self):
        calls = []
        steps = [Step("skip", "click", enabled=False), Step("run", "click")]
        status, events, _control = self.run_steps(steps, lambda step, _job, _prepared: calls.append(step.name))
        self.assertEqual(calls, ["run"])
        self.assertEqual(status, RunnerStatus.COMPLETED)
        self.assertEqual(events[-1].kind, "runner.completed")

    def test_empty_loop_completes_without_spinning(self):
        control = RunnerControl()
        control.reset()
        events = []
        runner = SequenceRunner(
            control=control,
            prepare_job=prepare_with([]),
            execute_step=lambda _step, _job, _prepared: None,
            emit=events.append,
        )
        status = runner.run([], loop_enabled=True)
        self.assertEqual(status, RunnerStatus.COMPLETED)
        self.assertEqual([event.kind for event in events], ["runner.started", "runner.completed"])

    def test_first_image_step_retries_itself(self):
        calls = []

        def execute(step, _job, _prepared):
            calls.append(step.name)
            if len(calls) < 3:
                raise RuntimeError("not visible")

        status, events, _control = self.run_steps([Step("image", "image_click")], execute)
        recoveries = [event for event in events if event.kind == "step.recovering"]
        self.assertEqual(calls, ["image", "image", "image"])
        self.assertEqual([event.data["rollback"] for event in recoveries], [False, False])
        self.assertEqual(status, RunnerStatus.COMPLETED)

    def test_failed_image_rolls_back_to_previous_image(self):
        calls = []
        failed_once = False

        def execute(step, _job, _prepared):
            nonlocal failed_once
            calls.append(step.name)
            if step.name == "image-b" and not failed_once:
                failed_once = True
                raise RuntimeError("transition not ready")

        steps = [
            Step("image-a", "image_click"),
            Step("middle", "click"),
            Step("image-b", "image_click"),
        ]
        status, events, _control = self.run_steps(steps, execute)
        recovery = next(event for event in events if event.kind == "step.recovering")
        self.assertEqual(calls, ["image-a", "middle", "image-b", "image-a", "middle", "image-b"])
        self.assertTrue(recovery.data["rollback"])
        self.assertEqual(recovery.data["recovery_name"], "image-a")
        self.assertEqual(status, RunnerStatus.COMPLETED)

    def test_retry_step_policy_retries_only_current_step(self):
        calls = []
        failures = 0

        def execute(step, _job, _prepared):
            nonlocal failures
            calls.append(step.name)
            if step.name == "unstable" and failures < 2:
                failures += 1
                raise RuntimeError("not ready")

        steps = [
            Step("before", "click"),
            Step("unstable", "click", failure_policy="retry_step", failure_retries=2),
            Step("after", "click"),
        ]
        status, events, _control = self.run_steps(steps, execute)

        self.assertEqual(calls, ["before", "unstable", "unstable", "unstable", "after"])
        self.assertEqual(status, RunnerStatus.COMPLETED)
        recoveries = [event for event in events if event.kind == "step.recovering"]
        self.assertEqual([event.data["rollback"] for event in recoveries], [False, False])

    def test_skip_policy_continues_with_next_step(self):
        calls = []

        def execute(step, _job, _prepared):
            calls.append(step.name)
            if step.name == "optional":
                raise RuntimeError("missing")

        steps = [
            Step("optional", "image_click", failure_policy="skip"),
            Step("after", "click"),
        ]
        status, events, control = self.run_steps(steps, execute)

        self.assertEqual(calls, ["optional", "after"])
        self.assertEqual(status, RunnerStatus.COMPLETED)
        self.assertFalse(control.should_stop())
        self.assertIn("step.skipped", [event.kind for event in events])

    def test_uses_configured_transition_between_jobs(self):
        control = RunnerControl()
        control.reset()
        waits = []
        control.wait = lambda seconds: waits.append(seconds) or True
        runner = SequenceRunner(
            control=control,
            prepare_job=prepare_with([]),
            execute_step=lambda _step, _job, _prepared: None,
            transition_seconds=0.25,
        )

        status = runner.run([make_job("One"), make_job("Two")])

        self.assertEqual(status, RunnerStatus.COMPLETED)
        self.assertEqual(waits, [0.25])

    def test_exhausted_recovery_fails_and_requests_stop(self):
        calls = []

        def execute(step, _job, _prepared):
            calls.append(step.name)
            raise RuntimeError("still missing")

        status, events, control = self.run_steps([Step("image", "image_click")], execute)
        self.assertEqual(calls, ["image", "image", "image"])
        self.assertEqual(status, RunnerStatus.FAILED)
        self.assertTrue(control.should_stop())
        self.assertIn("step.failed", [event.kind for event in events])
        self.assertEqual(events[-1].kind, "runner.failed")


if __name__ == "__main__":
    unittest.main()
