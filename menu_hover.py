"""A thread-local bridge out of Windows' modal popup-menu loop."""
import ctypes as c
from ctypes import wintypes as W


class NativeMenuHover:
    def __init__(self, bounds, current):
        self.bounds, self.current, self.pending = bounds, current, None
        self.user = u = c.WinDLL('user32', use_last_error=True)
        kernel = c.WinDLL('kernel32')
        kernel.GetCurrentThreadId.argtypes = []; kernel.GetCurrentThreadId.restype = W.DWORD
        self.callback_type = c.WINFUNCTYPE(c.c_ssize_t, c.c_int, c.c_size_t, c.c_ssize_t)
        u.SetWindowsHookExW.argtypes = [c.c_int, self.callback_type, W.HINSTANCE, W.DWORD]
        u.SetWindowsHookExW.restype = W.HHOOK
        u.UnhookWindowsHookEx.argtypes = [W.HHOOK]; u.UnhookWindowsHookEx.restype = W.BOOL
        u.CallNextHookEx.argtypes = [W.HHOOK, c.c_int, c.c_size_t, c.c_ssize_t]
        u.CallNextHookEx.restype = c.c_ssize_t
        u.EndMenu.argtypes = []; u.EndMenu.restype = W.BOOL

        def filtered(code, wp, lp):
            if code == 2 and lp:  # MSGF_MENU, including cascaded native submenus
                msg = c.cast(lp, c.POINTER(W.MSG)).contents
                if msg.message in (0x0200, 0x00a0):
                    self.select_point(msg.pt.x, msg.pt.y)
            return u.CallNextHookEx(None, code, wp, lp)
        self.callback = self.callback_type(filtered)
        self.hook = u.SetWindowsHookExW(-1, self.callback, None, kernel.GetCurrentThreadId())
        if not self.hook:
            raise c.WinError(c.get_last_error())

    def select_point(self, x, y):
        for name, left, top, right, bottom in self.bounds:
            if left <= x < right and top <= y < bottom:
                if name != self.current:
                    self.pending = name
                    # No Tk calls inside the native callback. MbPost returns
                    # after EndMenu; its Python caller can then post the next.
                    self.user.EndMenu()
                break

    def close(self):
        if self.hook:
            self.user.UnhookWindowsHookEx(self.hook)
            self.hook = None
