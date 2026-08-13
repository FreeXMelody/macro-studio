class SettingsService:
    FIELDS = ("window_hint", "focus_window", "input_mode", "confirm_step_test", "preview_clicks")

    def __init__(self, repository):
        self.repository = repository

    def document(self):
        data = self.repository.load()
        mode = str(data.get("input_mode", "foreground")).strip()
        if mode not in {"foreground", "window_message"}:
            mode = "foreground"
        return {
            "window_hint": str(data.get("window_hint", "")).strip(),
            "focus_window": bool(data.get("focus_window", True)),
            "input_mode": mode,
            "confirm_step_test": bool(data.get("confirm_step_test", True)),
            "preview_clicks": bool(data.get("preview_clicks", False)),
        }

    def replace(self, document):
        hint = str(document.get("window_hint", "")).strip()
        if not hint:
            raise ValueError("目标窗口关键词不能为空")
        mode = str(document.get("input_mode", "foreground")).strip()
        if mode not in {"foreground", "window_message"}:
            raise ValueError("未知的输入模式")
        focus = bool(document.get("focus_window", True))
        confirm_step_test = bool(document.get("confirm_step_test", True))
        preview_clicks = bool(document.get("preview_clicks", False))

        def mutate(data):
            data.update({
                "window_hint": hint,
                "focus_window": focus,
                "input_mode": mode,
                "confirm_step_test": confirm_step_test,
                "preview_clicks": preview_clicks,
            })

        self.repository.mutate(mutate)
        return self.document()
