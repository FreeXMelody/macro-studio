import ctypes
import time


MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_A = 0x41
VK_V = 0x56
VK_RETURN = 0x0D
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


def hotkey_ctrl(vk):
    key_down(VK_CONTROL)
    time.sleep(0.025)
    key_down(vk)
    time.sleep(0.025)
    key_up(vk)
    key_up(VK_CONTROL)


def press_enter():
    key_down(VK_RETURN)
    time.sleep(0.025)
    key_up(VK_RETURN)


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
