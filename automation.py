import ctypes
import time


MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
MK_LBUTTON = 0x0001
SMTO_ABORTIFHUNG = 0x0002
VK_CONTROL = 0x11
VK_A = 0x41
VK_V = 0x56
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_F8 = 0x77
VK_F9 = 0x78
GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13

KEY_ALIASES = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": VK_RETURN,
    "return": VK_RETURN,
    "shift": VK_SHIFT,
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "alt": VK_MENU,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "printscreen": 0x2C,
    "pause": 0x13,
    "capslock": 0x14,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "num0": 0x60,
    "num1": 0x61,
    "num2": 0x62,
    "num3": 0x63,
    "num4": 0x64,
    "num5": 0x65,
    "num6": 0x66,
    "num7": 0x67,
    "num8": 0x68,
    "num9": 0x69,
    "num*": 0x6A,
    "num+": 0x6B,
    "num-": 0x6D,
    "num.": 0x6E,
    "num/": 0x6F,
    "plus": 0xBB,
    "minus": 0xBD,
    "comma": 0xBC,
    "period": 0xBE,
    "slash": 0xBF,
    "semicolon": 0xBA,
    "quote": 0xDE,
    "backtick": 0xC0,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
}
for index in range(1, 25):
    KEY_ALIASES[f"f{index}"] = 0x6F + index
for index in range(10):
    KEY_ALIASES[str(index)] = 0x30 + index
for code in range(ord("a"), ord("z") + 1):
    KEY_ALIASES[chr(code)] = code - 32
KEY_CHOICES = tuple(sorted(KEY_ALIASES.keys()))

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
GlobalAlloc = kernel32.GlobalAlloc
GlobalLock = kernel32.GlobalLock
GlobalUnlock = kernel32.GlobalUnlock
GlobalFree = kernel32.GlobalFree
GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
GlobalAlloc.restype = ctypes.c_void_p
GlobalLock.argtypes = [ctypes.c_void_p]
GlobalLock.restype = ctypes.c_void_p
GlobalUnlock.argtypes = [ctypes.c_void_p]
GlobalFree.argtypes = [ctypes.c_void_p]
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.ScreenToClient.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.ScreenToClient.restype = ctypes.c_bool
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
user32.PostMessageW.restype = ctypes.c_bool
user32.SendMessageTimeoutW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_size_t


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def key_code_from_name(name):
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("按键名称不能为空。")
    if key.startswith("vk:"):
        try:
            return int(key[3:], 0)
        except ValueError as exc:
            raise ValueError("vk: 后面应填写数字，例如 vk:0x20。") from exc
    if key in KEY_ALIASES:
        return KEY_ALIASES[key]
    raise ValueError(f"不支持的按键：{name}")


def parse_key_combo(text):
    keys = [part.strip() for part in (text or "").replace("，", "+").split("+") if part.strip()]
    if not keys:
        raise ValueError("按键不能为空。")
    return keys


def parse_key_duration(text, default_seconds=0.25):
    value = (text or "").strip()
    if not value:
        return "", float(default_seconds)
    for separator in ("@", ",", " "):
        if separator in value:
            key_text, seconds_text = value.rsplit(separator, 1)
            try:
                return key_text.strip(), max(0.0, float(seconds_text.strip().rstrip("s秒")))
            except ValueError:
                break
    return value, float(default_seconds)


def get_cursor_pos():
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def click_xy(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.04)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.035)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def _client_lparam(hwnd, screen_x, screen_y):
    point = POINT(int(screen_x), int(screen_y))
    if not user32.ScreenToClient(hwnd, ctypes.byref(point)):
        raise RuntimeError("无法将屏幕坐标换算为窗口坐标。")
    return (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16)


def _deliver_window_message(hwnd, message, wparam, lparam):
    """Prefer synchronous delivery so queued clicks cannot overtake UI changes."""
    result = ctypes.c_size_t()
    delivered = user32.SendMessageTimeoutW(
        hwnd,
        message,
        wparam,
        lparam,
        SMTO_ABORTIFHUNG,
        450,
        ctypes.byref(result),
    )
    if delivered:
        return
    if not user32.PostMessageW(hwnd, message, wparam, lparam):
        raise RuntimeError("无法向目标窗口发送消息。")

def post_click_xy(hwnd, x, y):
    """Deliver a click to a window without moving the physical cursor."""
    if not hwnd:
        raise RuntimeError("窗口消息模式需要目标窗口。")
    lparam = _client_lparam(hwnd, x, y)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    if not user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam):
        raise RuntimeError("无法向目标窗口发送鼠标按下消息。")
    time.sleep(0.035)
    if not user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam):
        raise RuntimeError("无法向目标窗口发送鼠标抬起消息。")


def post_key(hwnd, vk, is_down=True):
    if not hwnd:
        raise RuntimeError("窗口消息模式需要目标窗口。")
    message = WM_KEYDOWN if is_down else WM_KEYUP
    lparam = 1 if is_down else 0xC0000001
    if not user32.PostMessageW(hwnd, message, int(vk), lparam):
        raise RuntimeError("无法向目标窗口发送按键消息。")


def post_press_key(hwnd, vk, hold_seconds=0.025):
    post_key(hwnd, vk, True)
    time.sleep(max(0.0, float(hold_seconds)))
    post_key(hwnd, vk, False)


def post_hotkey(hwnd, keys, hold_seconds=0.025):
    codes = [key_code_from_name(key) for key in keys]
    for code in codes:
        post_key(hwnd, code, True)
        time.sleep(0.015)
    time.sleep(max(0.0, float(hold_seconds)))
    for code in reversed(codes):
        post_key(hwnd, code, False)
        time.sleep(0.015)


def post_text(hwnd, text):
    """Send Unicode WM_CHAR units without changing the clipboard."""
    if not hwnd:
        raise RuntimeError("窗口消息模式需要目标窗口。")
    units = (text or "").encode("utf-16-le")
    for offset in range(0, len(units), 2):
        code_unit = int.from_bytes(units[offset:offset + 2], "little")
        if not user32.PostMessageW(hwnd, WM_CHAR, code_unit, 1):
            raise RuntimeError("无法向目标窗口发送文本消息。")

def key_down(vk):
    user32.keybd_event(vk, 0, 0, 0)


def key_up(vk):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def press_key(vk, hold_seconds=0.025):
    key_down(vk)
    time.sleep(max(0.0, float(hold_seconds)))
    key_up(vk)


def press_key_name(name, hold_seconds=0.025):
    press_key(key_code_from_name(name), hold_seconds)


def hold_key_name(name, seconds):
    press_key_name(name, seconds)


def hotkey(keys, hold_seconds=0.025):
    codes = [key_code_from_name(key) for key in keys]
    if not codes:
        raise ValueError("快捷键不能为空。")
    for code in codes:
        key_down(code)
        time.sleep(0.015)
    time.sleep(max(0.0, float(hold_seconds)))
    for code in reversed(codes):
        key_up(code)
        time.sleep(0.015)


def hotkey_ctrl(vk):
    hotkey(["ctrl", f"vk:{vk}"])


def press_enter():
    press_key(VK_RETURN)


def set_clipboard_text(text):
    data = (text + "\0").encode("utf-16-le")
    handle = GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise RuntimeError("GlobalAlloc failed")
    locked = GlobalLock(handle)
    if not locked:
        GlobalFree(handle)
        raise RuntimeError("GlobalLock failed")
    ctypes.memmove(locked, data, len(data))
    GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        GlobalFree(handle)
        raise RuntimeError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            GlobalFree(handle)
            raise RuntimeError("SetClipboardData failed")
        handle = None
    finally:
        user32.CloseClipboard()


def enum_windows():
    windows = []
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        windows.append({"hwnd": hwnd, "title": title_buf.value, "pid": pid.value})
        return True

    user32.EnumWindows(enum_proc_type(callback), 0)
    return windows


def find_window(hint):
    hint = hint.strip().lower()
    if not hint:
        return None
    for window in enum_windows():
        if hint in window["title"].lower():
            return window
    return None


def focus_window(hwnd):
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 5)
    time.sleep(0.1)
    return bool(user32.SetForegroundWindow(hwnd))
