"""Receive only the owned editor's physical F5 before IME; no Tcl callbacks."""
from collections import deque
import sys

_LIVE = {}


class NativeF5:
    def __init__(self, hwnd):
        from threading import Lock
        self._pending_lock = Lock()
        self.hwnd = hwnd;self.pending = deque();self.handle = None
        self._low_handle = None;self._low_thread_id = 0;self._editor_focus = 0
        self._alt_f5_in_cycle = False;self._alt_menu_releases = deque(maxlen=16);self._pressed_modifiers = set()
        if sys.platform != 'win32' or not hwnd:return
        import ctypes as C
        from ctypes import wintypes as W
        self._user = u = C.WinDLL('user32', use_last_error=True)
        kernel = C.WinDLL('kernel32')
        self._ctypes = C;self._msg_type = W.MSG
        self._type = C.WINFUNCTYPE(C.c_ssize_t,C.c_int,C.c_size_t,C.c_ssize_t)
        u.SetWindowsHookExW.argtypes = [C.c_int,self._type,W.HINSTANCE,W.DWORD]
        u.SetWindowsHookExW.restype = W.HANDLE
        u.CallNextHookEx.argtypes = [W.HANDLE,C.c_int,C.c_size_t,C.c_ssize_t]
        u.CallNextHookEx.restype = C.c_ssize_t
        u.UnhookWindowsHookEx.argtypes = [W.HANDLE];u.UnhookWindowsHookEx.restype = W.BOOL
        u.GetKeyState.argtypes = [C.c_int];u.GetKeyState.restype = C.c_short
        u.GetFocus.argtypes = [];u.GetFocus.restype = W.HWND
        u.GetWindowThreadProcessId.argtypes = [W.HWND,C.POINTER(W.DWORD)]
        u.GetWindowThreadProcessId.restype = W.DWORD
        kernel.GetCurrentThreadId.restype = W.DWORD
        self._ui_thread = thread = kernel.GetCurrentThreadId()
        if u.GetWindowThreadProcessId(hwnd,None) != thread:return
        self._proc = self._type(self._message)
        self.handle = u.SetWindowsHookExW(3,self._proc,None,thread)
        if self.handle:_LIVE[id(self)] = self
        # WH_GETMESSAGE is after IME/TSF for real keys. A separate native
        # pump handles the physical F5 before it reaches the input queue.
        import threading
        self._low_ready = threading.Event()
        self._low_thread = threading.Thread(target=self._low_pump,daemon=True,name='CorrectNote-F5')
        self._low_thread.start();self._low_ready.wait(1.0)

    def _low_pump(self):
        import ctypes as C
        from ctypes import wintypes as W
        kernel = C.WinDLL('kernel32');kernel.GetCurrentThreadId.restype = W.DWORD
        kernel.GetModuleHandleW.argtypes = [W.LPCWSTR];kernel.GetModuleHandleW.restype = W.HMODULE
        u = self._user
        class Keyboard(C.Structure):
            _fields_ = [('vkCode',W.DWORD),('scanCode',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]
        class Gui(C.Structure):
            _fields_ = [('cbSize',W.DWORD),('flags',W.DWORD),('active',W.HWND),('focus',W.HWND),
                        ('capture',W.HWND),('menu',W.HWND),('move',W.HWND),('caret',W.HWND),('rect',W.RECT)]
        self._keyboard_type = Keyboard;self._gui_type = Gui
        u.GetForegroundWindow.argtypes = [];u.GetForegroundWindow.restype = W.HWND
        u.GetGUIThreadInfo.argtypes = [W.DWORD,C.POINTER(Gui)];u.GetGUIThreadInfo.restype = W.BOOL
        u.GetAsyncKeyState.argtypes = [C.c_int];u.GetAsyncKeyState.restype = C.c_short
        u.GetMessageW.argtypes = [C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT];u.GetMessageW.restype = W.BOOL
        u.PostThreadMessageW.argtypes = [W.DWORD,W.UINT,C.c_size_t,C.c_ssize_t];u.PostThreadMessageW.restype = W.BOOL
        self._pressed_modifiers = {vk for vk in range(0xa0,0xa6) if u.GetAsyncKeyState(vk)&0x8000}
        self._low_proc = self._type(self._low_message)
        self._low_thread_id = kernel.GetCurrentThreadId()
        self._low_handle = u.SetWindowsHookExW(13,self._low_proc,kernel.GetModuleHandleW(None),0)
        if self._low_handle:_LIVE[id(self)] = self
        self._low_ready.set()
        if not self._low_handle:return
        try:
            message = W.MSG()
            while u.GetMessageW(C.byref(message),None,0,0)>0:pass
        finally:
            if u.UnhookWindowsHookEx(self._low_handle):self._low_handle = None
            if not self.handle and not self._low_handle:_LIVE.pop(id(self),None)

    def _low_message(self, code, message, pointer):
        try:
            if code == 0 and message in (0x100,0x101,0x104,0x105):
                key = self._ctypes.cast(pointer,self._ctypes.POINTER(self._keyboard_type)).contents
                vk = key.vkCode
                if vk in (0x10,0x11,0x12):
                    vk = (0xa1 if key.scanCode==0x36 else 0xa0) if vk==0x10 else (
                        (0xa3 if key.flags&1 else 0xa2) if vk==0x11 else (0xa5 if key.flags&1 else 0xa4))
                if 0xa0 <= vk <= 0xa5:
                    if message in (0x100,0x104):self._pressed_modifiers.add(vk)
                    else:self._pressed_modifiers.discard(vk)
                if vk in (0xa4,0xa5) and message in (0x101,0x105):
                    if self._alt_f5_in_cycle and not any(k in self._pressed_modifiers for k in (0xa4,0xa5)):
                        if self._editor_focus and self._user.GetWindowThreadProcessId(self._user.GetForegroundWindow(),None)==self._ui_thread:
                            with self._pending_lock:self._alt_menu_releases.append(key.time&0xffffffff)
                        self._alt_f5_in_cycle = False
                elif message in (0x100,0x104) and key.vkCode != 0x74 and not 0xa0 <= vk <= 0xa5:
                    self._alt_f5_in_cycle = False
                if key.vkCode == 0x74:
                    u = self._user
                    # Read modifier/focus state only for F5 in our foreground
                    # editor. No other key/window/application is intercepted.
                    if u.GetWindowThreadProcessId(u.GetForegroundWindow(),None) == self._ui_thread:
                        gui = self._gui_type();gui.cbSize = self._ctypes.sizeof(gui)
                        target=self.hwnd;focus=self._editor_focus
                        if (target and focus and u.GetGUIThreadInfo(self._ui_thread,self._ctypes.byref(gui))
                                and gui.focus == focus):
                            if message in (0x100,0x104):
                                # The low-level callback precedes async state
                                # updates; use the preceding modifier packets.
                                state = sum(bit for keys,bit in (((0xa0,0xa1),1),((0xa2,0xa3),4),((0xa4,0xa5),0x20000))
                                            if any(vk in self._pressed_modifiers for vk in keys))
                                self._queue(state,target)
                            return 1
        except Exception:
            pass
        return self._user.CallNextHookEx(self._low_handle,code,message,pointer)

    def _message(self, code, removed, pointer):
        try:
            if code == 0:
                msg = self._ctypes.cast(pointer,self._ctypes.POINTER(self._msg_type)).contents
                if (msg.hWnd == self.hwnd and msg.message in (0x100,0x101,0x104,0x105)
                        and msg.wParam == 0x74 and (msg.lParam >> 16)&0xff == 0x3f):
                    if removed and msg.message in (0x100,0x104):
                        self._queue(sum(bit for vk,bit in ((0x10,1),(0x11,4),(0x12,0x20000))
                                                if self._user.GetKeyState(vk)&0x8000),msg.hWnd)
                    msg.message = 0;msg.wParam = 0;msg.lParam = 0
        except Exception:
            pass
        return self._user.CallNextHookEx(self.handle,code,removed,pointer)

    def set_target(self,hwnd):
        # Drop queued work when focus moves; never apply an old key elsewhere.
        with self._pending_lock:
            if self.hwnd!=hwnd:
                self.hwnd=hwnd;self.pending.clear();self._editor_focus=0

    def set_editor_focus(self,active):
        # Called only on the UI thread: Tk may focus a native container rather
        # than Text.winfo_id(). Logical FocusOut still excludes other entries.
        self._editor_focus = self._user.GetFocus() if active and hasattr(self,'_user') else 0

    def _queue(self,state,target=None):
        with self._pending_lock:
            if target is not None and target!=self.hwnd:return
            if state&0x20000:self._alt_f5_in_cycle = True
            self.pending.append(state)

    def consume_alt_menu(self, message_time):
        # Match only the SC_KEYMENU caused by our actual Alt release. Some
        # releases produce no menu request; those must not mask a later Alt.
        now = int(message_time)&0xffffffff
        matched = False
        with self._pending_lock:
            kept = deque(maxlen=16)
            for stamp in self._alt_menu_releases:
                if stamp==now and not matched:matched=True
                elif (stamp-now)&0xffffffff < 0x80000000:kept.append(stamp)
            self._alt_menu_releases = kept
        return matched

    def take(self):
        with self._pending_lock:
            states = tuple(self.pending);self.pending.clear();return states

    def close(self):
        if self.handle and self._user.UnhookWindowsHookEx(self.handle):self.handle = None
        thread = getattr(self,'_low_thread',None)
        if thread is not None and self._low_thread_id:
            self._user.PostThreadMessageW(self._low_thread_id,0x12,0,0);thread.join(.2)
        if not self.handle and not self._low_handle:_LIVE.pop(id(self),None)
        self.pending.clear()
