from utils import parse_duration, render_template


SUPPORTED_ACTIONS = {
    "click",
    "image_click",
    "paste",
    "wait",
    "key",
    "key_hold",
    "key_down",
    "key_up",
    "enter",
    "ctrl_a",
    "hotkey",
    "hotkey_hold",
    "open_uri",
    "http_request",
    "log",
}
VALUE_REQUIRED = {
    "wait",
    "key",
    "key_hold",
    "key_down",
    "key_up",
    "hotkey",
    "hotkey_hold",
    "open_uri",
    "http_request",
    "log",
}


class RunPlanService:
    def __init__(self, catalog, target_provider=None, template_validator=None):
        self.catalog = catalog
        self.target_provider = target_provider or (lambda: {})
        self.template_validator = template_validator

    def inspect(self, active_group=None):
        jobs = self.catalog.jobs(active_group, enabled_only=True)
        target_document = self.target_provider() or {}
        points = self._active_points(target_document)
        image_targets = {
            str(item.get("name", "")).strip(): item
            for item in target_document.get("image_targets", [])
            if str(item.get("name", "")).strip()
        }
        issues = []
        items = []
        total_actions = 0
        estimated_seconds = 0.0

        if not jobs:
            issues.append(self._issue("error", "empty_queue", "当前范围没有启用的运行条目"))

        for item_index, job in enumerate(jobs):
            try:
                prepared = self.catalog.prepare_job(job)
            except Exception as exc:
                label = job.song.title or job.song.keyword or "未命名条目"
                workflow = job.song.step_preset or job.group.step_preset or "未指定"
                issues.append(
                    self._issue(
                        "error",
                        "invalid_workflow",
                        f"无法解析工作流：{exc}",
                        item_index,
                        label,
                    )
                )
                items.append(
                    {
                        "name": label,
                        "group": job.group.name,
                        "workflow": workflow,
                        "actions": 0,
                        "estimated_seconds": 0.0,
                    }
                )
                continue
            steps = [step for step in prepared.steps if getattr(step, "enabled", True)]
            item_seconds = 0.0
            if not steps:
                issues.append(
                    self._issue(
                        "warning",
                        "empty_workflow",
                        "该条目的工作流没有启用动作",
                        item_index,
                        prepared.label,
                    )
                )

            for step_index, step in enumerate(steps):
                item_seconds += self._inspect_step(
                    step,
                    job,
                    points,
                    image_targets,
                    issues,
                    item_index,
                    prepared.label,
                    step_index,
                )

            total_actions += len(steps)
            estimated_seconds += item_seconds
            items.append(
                {
                    "name": prepared.label,
                    "group": prepared.group_name,
                    "workflow": prepared.preset_label,
                    "actions": len(steps),
                    "estimated_seconds": round(item_seconds, 3),
                }
            )

        if len(items) > 1:
            estimated_seconds += len(items) - 1
        return {
            "ready": not any(issue["severity"] == "error" for issue in issues),
            "items": items,
            "item_count": len(items),
            "action_count": total_actions,
            "estimated_seconds": round(estimated_seconds, 3),
            "issues": issues,
        }

    def _inspect_step(
        self,
        step,
        job,
        points,
        image_targets,
        issues,
        item_index,
        item_name,
        step_index,
    ):
        kind = str(getattr(step, "kind", "")).strip()
        step_name = str(getattr(step, "name", "")).strip() or kind or "未命名动作"
        seconds = 0.0

        def add(severity, code, message):
            issues.append(self._issue(severity, code, message, item_index, item_name, step_index, step_name))

        value = self._render(getattr(step, "value", ""), job.song, add)
        if kind not in SUPPORTED_ACTIONS:
            add("error", "unknown_action", f"不支持的动作类型：{kind or '未填写'}")
            return seconds
        if kind == "click":
            target = str(getattr(step, "target", "")).strip()
            if not target:
                add("error", "missing_point", "点击动作没有选择点位")
            elif target not in points:
                add("error", "missing_point", f"活动点位组中不存在点位：{target}")
        elif kind == "image_click":
            if not value:
                add("error", "missing_image_target", "图像点击没有选择图像目标")
            elif value not in image_targets:
                add("error", "missing_image_target", f"图像目标不存在：{value}")
            else:
                self._validate_template(value, add)
            verify_target = str(getattr(step, "verify_target", "")).strip()
            if verify_target:
                if verify_target not in image_targets:
                    add("error", "missing_verify_target", f"点击后验证目标不存在：{verify_target}")
                else:
                    self._validate_template(verify_target, add)
        elif kind in VALUE_REQUIRED and not value:
            add("error", "missing_value", "该动作缺少必要参数")

        if kind == "paste" and not value and not (job.song.keyword or job.song.title):
            add("warning", "empty_paste", "粘贴动作和当前条目都没有可用文本")
        if kind == "wait" and value:
            seconds += self._duration(value, add, "等待时长")
        elif kind in {"key_hold", "hotkey_hold"} and value:
            seconds += self._hold_duration(value, add)

        wait_after = self._render(getattr(step, "wait_after", ""), job.song, add)
        if kind != "wait" and wait_after:
            seconds += self._duration(wait_after, add, "动作后等待")
        return seconds

    @staticmethod
    def _render(value, song, add):
        try:
            return render_template(value, song).strip()
        except (KeyError, ValueError) as exc:
            add("error", "invalid_variable", f"变量表达式无效：{value}（{exc}）")
            return ""

    def _validate_template(self, target_name, add):
        if self.template_validator is None:
            return
        try:
            self.template_validator(target_name)
        except (ValueError, OSError) as exc:
            add("error", "invalid_template", f"图像目标「{target_name}」不可用：{exc}")

    @staticmethod
    def _duration(value, add, label):
        try:
            seconds = parse_duration(value)
            if seconds < 0:
                raise ValueError("不能小于 0")
            return seconds
        except (TypeError, ValueError) as exc:
            add("error", "invalid_duration", f"{label}无效：{value}（{exc}）")
            return 0.0

    def _hold_duration(self, value, add):
        if "@" not in value:
            return 0.5
        _keys, duration = value.rsplit("@", 1)
        return self._duration(duration, add, "长按时长")

    @staticmethod
    def _active_points(document):
        groups = document.get("point_groups", []) or []
        active_name = str(document.get("active_point_group", "")).strip()
        group = next(
            (item for item in groups if str(item.get("name", "")).strip() == active_name),
            groups[0] if groups else {},
        )
        return {
            str(item.get("name", "")).strip()
            for item in group.get("points", [])
            if str(item.get("name", "")).strip()
        }

    @staticmethod
    def _issue(severity, code, message, item_index=None, item_name="", step_index=None, step_name=""):
        return {
            "severity": severity,
            "code": code,
            "message": message,
            "item_index": item_index,
            "item_name": item_name,
            "step_index": step_index,
            "step_name": step_name,
        }
