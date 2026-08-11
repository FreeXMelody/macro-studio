from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    kind: str
    label: str
    needs_target: bool = False
    needs_value: bool = False
    help_text: str = ""


ACTION_SPECS = [
    ActionSpec("click", "点击点位", needs_target=True),
    ActionSpec("image_click", "图像点击", needs_value=True, help_text="参数填图像目标名称"),
    ActionSpec("paste", "粘贴文本", needs_value=True, help_text="参数支持 {keyword}"),
    ActionSpec("wait", "等待", needs_value=True, help_text="参数填秒数或 mm:ss"),
    ActionSpec("key", "单击按键", needs_value=True, help_text="例如 space、esc、f5、a"),
    ActionSpec("key_hold", "长按按键", needs_value=True, help_text="例如 space@0.8"),
    ActionSpec("key_down", "按下按键", needs_value=True, help_text="按住直到 key_up"),
    ActionSpec("key_up", "抬起按键", needs_value=True),
    ActionSpec("enter", "Enter"),
    ActionSpec("ctrl_a", "Ctrl+A"),
    ActionSpec("hotkey", "组合键", needs_value=True, help_text="例如 ctrl+v、shift+tab"),
    ActionSpec("hotkey_hold", "组合键长按", needs_value=True, help_text="例如 ctrl+space@0.5"),
    ActionSpec("open_uri", "打开链接/协议", needs_value=True, help_text="例如 https://... 或 nsh://..."),
    ActionSpec("http_request", "发送HTTP请求", needs_value=True, help_text="例如 GET http://127.0.0.1:端口/path"),
    ActionSpec("log", "日志", needs_value=True),
]

ACTION_KINDS = tuple(spec.kind for spec in ACTION_SPECS)
VALUE_ACTION_KINDS = frozenset(spec.kind for spec in ACTION_SPECS if spec.needs_value)
TARGET_ACTION_KINDS = frozenset(spec.kind for spec in ACTION_SPECS if spec.needs_target)
ACTION_HELP_TEXT = (
    "参数：key=单击，key_hold=按键@秒，key_down/up=按下/抬起，"
    "hotkey=组合键，hotkey_hold=组合键@秒；open_uri 可打开协议链接，http_request 可测试本地/网页接口。"
)
