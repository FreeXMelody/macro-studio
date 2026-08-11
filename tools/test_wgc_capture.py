import ctypes
import sys
import threading
from pathlib import Path
import numpy as np
from windows_capture import WindowsCapture

def find_window(hint):
    result=[]; callback_type=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
    def callback(hwnd,_):
        length=ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length:
            title=ctypes.create_unicode_buffer(length+1);ctypes.windll.user32.GetWindowTextW(hwnd,title,length+1)
            if hint.lower() in title.value.lower():result.append((hwnd,title.value))
        return True
    ctypes.windll.user32.EnumWindows(callback_type(callback),0)
    return result[0] if result else (None,'')

hint=sys.argv[1] if len(sys.argv)>1 else '逆水寒手游桌面版'
hwnd,title=find_window(hint)
if not hwnd: raise SystemExit('Window not found')
out=Path(__file__).resolve().parents[1]/'window_capture_tests'/'wgc_test.png';done=threading.Event();error=[]
capture=WindowsCapture(cursor_capture=False,draw_border=False,window_hwnd=int(hwnd),minimum_update_interval=0)
@capture.event
def on_frame_arrived(frame,control):
    try:
        frame.save_as_image(str(out)); print(f'window={title}');print(f'size={frame.width}x{frame.height}');print(f'brightness={float(np.mean(frame.frame_buffer[:,:,:3])) / 255:.4f}');print(out)
    finally:
        control.stop();done.set()
@capture.event
def on_closed():
    error.append('capture closed');done.set()
control=capture.start_free_threaded()
if not done.wait(12): control.stop();raise SystemExit('Timed out waiting for frame')
if error: raise SystemExit(error[0])
