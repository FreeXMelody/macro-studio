import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path
from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]

def find_window(hint):
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if hint.lower() in title.value.lower(): found.append((hwnd, title.value))
        return True
    user32.EnumWindows(callback_type(callback), 0)
    return found[0] if found else (None, "")

def capture(hwnd, flag, client_only=False):
    rect = wintypes.RECT()
    (user32.GetClientRect if client_only else user32.GetWindowRect)(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    dc = user32.GetDC(hwnd) if client_only else user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(dc); bmp = gdi32.CreateCompatibleBitmap(dc, width, height); old = gdi32.SelectObject(mem, bmp)
    try:
        ok = user32.PrintWindow(hwnd, mem, flag)
        info = BITMAPINFO(BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0))
        pixels = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(mem, bmp, 0, height, pixels, ctypes.byref(info), 0)
        return ok, Image.frombuffer('RGBA', (width, height), pixels, 'raw', 'BGRA', 0, 1).convert('RGB')
    finally:
        gdi32.SelectObject(mem, old); gdi32.DeleteObject(bmp); gdi32.DeleteDC(mem); user32.ReleaseDC(hwnd, dc)

def main():
    hint = sys.argv[1] if len(sys.argv) > 1 else '逆水寒手游桌面版'
    hwnd, title = find_window(hint)
    if not hwnd: raise SystemExit(f'Window not found: {hint}')
    out = Path(__file__).resolve().parents[1] / 'window_capture_tests' / time.strftime('%Y%m%d_%H%M%S')
    out.mkdir(parents=True, exist_ok=True)
    report = [f'window={title}', f'hwnd={int(hwnd)}']
    for name, flag, client in [('printwindow_full', 0, False), ('printwindow_client', 1, True), ('printwindow_renderfull', 2, False)]:
        ok, image = capture(hwnd, flag, client)
        image.save(out / f'{name}.png')
        extrema = image.getextrema(); mean = sum(sum(pair) / 2 for pair in extrema) / (255 * 3)
        report.append(f'{name}: PrintWindow={bool(ok)}, size={image.size}, brightness={mean:.4f}')
    (out / 'report.txt').write_text('\n'.join(report), encoding='utf-8')
    print(out)
    print('\n'.join(report))

if __name__ == '__main__': main()
