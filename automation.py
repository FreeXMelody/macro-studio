import ctypes
import time


MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
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
for index in range(1, 13):
    KEY_ALIASES[f"f{index}"] = 0x6F + index
for index in range(10):
    KEY_ALIASES[str(index)] = 0x30 + index
for code in range(ord("a"), ord("z") + 1):
    KEY_ALIASES[chr(code)] = code - 32


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


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


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


def key_down(vk):
    user32.keybd_event(vk, 0, 0, 0)


def key_up(vk):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)




def press_key(vk):
    key_down(vk)
    time.sleep(0.025)
    key_up(vk)


def hotkey(keys):
    codes = [key_code_from_name(key) for key in keys]
    if not codes:
        raise ValueError("快捷键不能为空。")
    for code in codes[:-1]:
        key_down(code)
        time.sleep(0.015)
    key_down(codes[-1])
    time.sleep(0.025)
    key_up(codes[-1])
    for code in reversed(codes[:-1]):
        key_up(code)
        time.sleep(0.015)

def hotkey_ctrl(vk):
    key_down(VK_CONTROL)
    time.sleep(0.025)
    key_down(vk)
    time.sleep(0.025)
    key_up(vk)
    key_up(VK_CONTROL)


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





