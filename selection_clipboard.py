# -*- coding: utf-8 -*-
"""Copy the explicitly selected text before quick input takes foreground focus."""
import ctypes as C
from ctypes import wintypes as W
import sys,time
from selection_windows import source_now,MAX_TEXT


class Keyboard(C.Structure):
    _fields_=[('vk',W.WORD),('scan',W.WORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]


class Mouse(C.Structure):
    _fields_=[('dx',W.LONG),('dy',W.LONG),('data',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]


class Payload(C.Union):
    _fields_=[('keyboard',Keyboard),('mouse',Mouse)]


class Input(C.Structure):
    _fields_=[('type',W.DWORD),('payload',Payload)]


def keyboard_inputs():
    keys=[(0x11,0),(0x43,0),(0x43,2),(0x11,2)]
    return (Input*len(keys))(*(Input(1,Payload(keyboard=Keyboard(vk,0,flags,0,0))) for vk,flags in keys))


class WindowsClipboard:
    def __init__(self):
        self.user=C.WinDLL('user32',use_last_error=True)
        self.kernel=C.WinDLL('kernel32',use_last_error=True)
        for dll,name,args,result in (
            (self.user,'GetAsyncKeyState',[C.c_int],W.SHORT),
            (self.user,'SendInput',[W.UINT,C.POINTER(Input),C.c_int],W.UINT),
            (self.user,'GetClipboardSequenceNumber',[],W.DWORD),
            (self.user,'OpenClipboard',[W.HWND],W.BOOL),
            (self.user,'CloseClipboard',[],W.BOOL),
            (self.user,'GetClipboardData',[W.UINT],W.HANDLE),
            (self.kernel,'GlobalLock',[W.HGLOBAL],C.c_void_p),
            (self.kernel,'GlobalUnlock',[W.HGLOBAL],W.BOOL),
            (self.kernel,'GlobalSize',[W.HGLOBAL],C.c_size_t)):
            fn=getattr(dll,name);fn.argtypes=args;fn.restype=result

    def down(self,key):return bool(self.user.GetAsyncKeyState(key)&0x8000)
    def blocked_keys(self):
        # Wait for shortcut release, including Ctrl: relying on an earlier
        # physical Ctrl state could deliver a bare C after the user's key-up.
        return any(self.down(k) for k in (0x10,0x11,0x12,0x5b,0x5c,0x2d,0xbd,0x43))
    def sequence(self):return self.user.GetClipboardSequenceNumber()
    def copy(self):
        if self.blocked_keys():return False
        keys=keyboard_inputs()
        sent=self.user.SendInput(len(keys),keys,C.sizeof(Input))
        if sent==len(keys):return True
        if sent:
            # A partial injection must not leave our synthetic keys held.
            releases=[(0x43,2),(0x11,2)]
            keys=(Input*len(releases))(*(Input(1,Payload(keyboard=Keyboard(k,0,f,0,0))) for k,f in releases))
            self.user.SendInput(len(keys),keys,C.sizeof(Input))
        return False

    def text(self,expected):
        if not self.user.OpenClipboard(None):return None
        try:
            if self.sequence()!=expected:return None
            handle=self.user.GetClipboardData(13)  # CF_UNICODETEXT, also Excel's TAB-delimited cells.
            if not handle:return None
            size=self.kernel.GlobalSize(handle)
            if size<2:return None
            pointer=self.kernel.GlobalLock(handle)
            if not pointer:return None
            try:
                units=(C.c_uint16*min(size//2,MAX_TEXT*2+1)).from_address(pointer)
                end=next((n for n,x in enumerate(units) if x==0),None)
                if end is None:return None
                value=C.string_at(pointer,end*2).decode('utf-16-le')
                return value if len(value)<=MAX_TEXT else None
            finally:self.kernel.GlobalUnlock(handle)
        finally:self.user.CloseClipboard()


def copy_selection(source,deadline,cancelled,*,backend=None,snapshot=source_now,
                   clock=time.monotonic,wait=time.sleep):
    """No old clipboard reads, clearing, focus changes, or document writes."""
    def current():return not cancelled.is_set() and clock()<deadline and snapshot()==source
    if source is None or not current():return None
    if backend is None:
        if sys.platform!='win32':return None
        backend=WindowsClipboard()
    try:
        while current() and backend.blocked_keys():wait(.008)
        if not current():return None
        before=backend.sequence()
        if not before or not current() or not backend.copy():return None
        while current():
            sequence=backend.sequence()
            if sequence and sequence!=before:
                value=backend.text(sequence)
                if not current():return None
                if value is not None:return value.replace('\r\n','\n').replace('\r','\n')
            wait(.008)
    except (OSError,ValueError,UnicodeError):return None
    return None


def read_for_opening(source,deadline,cancelled):
    # A copy works for rendered browser/chat selections that have no focused
    # UIA TextPattern. The user explicitly authorized this clipboard transfer.
    value=copy_selection(source,min(deadline,time.monotonic()+.4),cancelled)
    if value:return value
    if cancelled.is_set() or time.monotonic()>=deadline or source_now()!=source:return None
    from selection_windows import read_selection
    return read_selection(source,deadline,cancelled)
