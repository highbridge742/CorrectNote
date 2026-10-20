# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Hold Windows' restart / shutdown / sign-out until the text is saved (Windows only).

2026-10-20 うにさん「再起動を検知した時点ではもう手遅れなんじゃないですかね。例えばExcelとかだと、
保存してませんのダイアログで止められます。このアプリは自動保存の時間が来ていませんのダイアログで
止め、止めると同時に自動保存して、待って閉じたらいいのでは」. Saving inside Windows' question
"may the session end?" was not reliable in practice (the text written just before a restart was
lost twice), so CorrectNote now answers "not yet" when a save is waiting: Windows shows its
"this app is preventing restart" screen with the reason below, the app saves at once and closes,
and Windows goes on once it has closed. With nothing waiting to be saved it does not hold
anything. The question is answered by the app's main window (Tk's frame, subclassed), so Windows' screen
shows CorrectNote's name and icon; a hidden top-level window of its own answers only until that
window exists. Neither window procedure touches Tk: they note the request, and Tk's thread does
the saving on its next turn (every POLL_MS)."""
import sys

REASON = '終了前に自動保存を実行しました。'     # うにさんの指定（2026-10-20）
POLL_MS = 150
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
# Asked early among applications (0x300-0x3FF: "first"), before the console that closes
SHUTDOWN_LEVEL = 0x3FF


class ShutdownGuard:
    def __init__(self, root, has_unsaved, finish, reason=REASON):
        """has_unsaved(): True while a save is waiting (read only, no Tk calls).
        finish(): save everything and close the app (called on Tk's thread)."""
        self.root, self.has_unsaved, self.finish, self.reason = root, has_unsaved, finish, reason
        self.requested = False
        self.blocking = False
        self.hwnd = None
        self._frame = None
        self._subclassed = None
        self._job = None

    # --- install -----------------------------------------------------------
    def install(self):
        if sys.platform != 'win32':
            return False
        import ctypes
        from ctypes import wintypes as W
        self.C, self.W = ctypes, W
        u = self.u = ctypes.WinDLL('user32', use_last_error=True)
        k = ctypes.WinDLL('kernel32')
        LRESULT = ctypes.c_ssize_t
        self.WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
        u.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        u.DefWindowProcW.restype = LRESULT
        u.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
        u.CreateWindowExW.restype = W.HWND
        u.ShutdownBlockReasonCreate.argtypes = [W.HWND, W.LPCWSTR]
        u.ShutdownBlockReasonDestroy.argtypes = [W.HWND]
        u.DestroyWindow.argtypes = [W.HWND]

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [('style', W.UINT), ('lpfnWndProc', self.WNDPROC), ('cbClsExtra', ctypes.c_int),
                        ('cbWndExtra', ctypes.c_int), ('hInstance', W.HINSTANCE), ('hIcon', W.HICON),
                        ('hCursor', W.HANDLE), ('hbrBackground', W.HBRUSH), ('lpszMenuName', W.LPCWSTR),
                        ('lpszClassName', W.LPCWSTR)]
        self._proc = self.WNDPROC(self._wndproc)       # kept: Windows calls it for the window's life
        instance = k.GetModuleHandleW(None)
        # A class of its own: a class's window procedure is fixed when the class is registered
        name = self._class = 'CorrectNoteShutdownGuard%x' % id(self)
        self._instance = instance
        wc = WNDCLASSW(0, self._proc, 0, 0, instance, None, None, None, None, name)
        u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        u.UnregisterClassW.argtypes = [W.LPCWSTR, W.HINSTANCE]
        if not u.RegisterClassW(ctypes.byref(wc)):
            return False
        # A real top-level window (a message-only window is not asked), never shown
        self.hwnd = u.CreateWindowExW(0, name, 'CorrectNote', 0, 0, 0, 0, 0, None, None, instance, None)
        if not self.hwnd:
            return False
        # The answer comes from the app's main window (Tk's frame): Windows lists the window that
        # holds it with that window's title and icon (a hidden window is listed without either:
        # 2026-10-20 うにさん「アプリ名もアイコンも表示されませんでした」)
        cc = self.cc = ctypes.WinDLL('comctl32')
        self.SUBPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
                                          ctypes.c_size_t, ctypes.c_size_t)
        cc.SetWindowSubclass.argtypes = [W.HWND, self.SUBPROC, ctypes.c_size_t, ctypes.c_size_t]
        cc.SetWindowSubclass.restype = W.BOOL
        cc.RemoveWindowSubclass.argtypes = [W.HWND, self.SUBPROC, ctypes.c_size_t]
        cc.RemoveWindowSubclass.restype = W.BOOL
        cc.DefSubclassProc.argtypes = [W.HWND, W.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        cc.DefSubclassProc.restype = LRESULT
        self._subproc = self.SUBPROC(self._frame_message)
        try:
            k.SetProcessShutdownParameters(SHUTDOWN_LEVEL, 0)
        except Exception:
            pass
        self._job = self.root.after(POLL_MS, self._poll)
        return True

    def close(self):
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self._unblock()
        self._detach_frame()
        if self.hwnd:
            try:
                self.u.DestroyWindow(self.hwnd)
                self.u.UnregisterClassW(self._class, self._instance)
            except Exception:
                pass
            self.hwnd = None

    # --- Windows' question (window procedure: no Tk calls here) -------------
    def _answer(self, hwnd):
        """WM_QUERYENDSESSION: 0 (not yet) while a save is waiting, else None."""
        if self.requested or self.has_unsaved():
            self.requested = True
            self._block(hwnd)
            return 0                            # not yet: saving first, then the app closes
        return None

    def _ending(self, wparam):
        if wparam and self.has_unsaved():
            self.requested = True               # ending anyway (forced): save as soon as possible

    def _wndproc(self, hwnd, msg, wparam, lparam):
        """The hidden window: answers only until the main window does."""
        try:
            if msg == WM_QUERYENDSESSION:
                if self._subclassed:
                    return 1                    # the main window answers, with its name and icon
                answer = self._answer(hwnd)
                return 1 if answer is None else answer
            if msg == WM_ENDSESSION:
                self._ending(wparam)
                return 0
        except Exception:
            pass
        return self.u.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _frame_message(self, hwnd, msg, wparam, lparam, uid, ref):
        """The main window (Tk's frame), subclassed. Other messages go on to Tk unchanged."""
        try:
            if msg == WM_QUERYENDSESSION:
                answer = self._answer(hwnd)
                if answer is not None:
                    return answer
            elif msg == WM_ENDSESSION:
                self._ending(wparam)
            elif msg == 0x0082:                 # WM_NCDESTROY
                self._detach_frame()
        except Exception:
            pass
        return self.cc.DefSubclassProc(hwnd, msg, wparam, lparam)

    def _attach_frame(self, frame):
        if not frame or frame == self.hwnd or frame == self._subclassed:
            return
        self._detach_frame()
        if self.cc.SetWindowSubclass(frame, self._subproc, id(self), 0):
            self._subclassed = frame

    def _detach_frame(self):
        if self._subclassed:
            try:
                self.cc.RemoveWindowSubclass(self._subclassed, self._subproc, id(self))
            except Exception:
                pass
            self._subclassed = None

    def _main_hwnd(self):
        try:
            return int(self.root.wm_frame(), 16)
        except Exception:
            return self.hwnd

    def _block(self, hwnd):
        if self.blocking:
            return
        # The reason belongs to the window that holds the session (shown next to its name)
        if self.u.ShutdownBlockReasonCreate(hwnd, self.reason):
            self.blocking = hwnd

    def _unblock(self):
        if self.blocking:
            try:
                self.u.ShutdownBlockReasonDestroy(self.blocking)
            except Exception:
                pass
            self.blocking = False

    # --- Tk's thread ------------------------------------------------------
    def _poll(self):
        self._job = None
        # Looked up every time: before Tk has drawn the window, its frame is not there yet
        self._frame = self._main_hwnd()
        self._attach_frame(self._frame)
        if self.requested:
            try:
                self.finish()
            finally:
                self._unblock()
            return
        try:
            self._job = self.root.after(POLL_MS, self._poll)
        except Exception:
            pass
