# -*- coding: utf-8 -*-
"""Only owned synthetic EDIT controls; no foreground element or clipboard read."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import os,sys,threading,time
from unittest.mock import patch
import tkinter as tk


def main():
    import selection_windows as S
    root=tk.Tk();root.geometry('500x300+0+0');root.update()
    user=C.WinDLL('user32');kernel=C.WinDLL('kernel32')
    user.GetParent.argtypes=(W.HWND,);user.GetParent.restype=W.HWND
    user.CreateWindowExW.argtypes=(W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p);user.CreateWindowExW.restype=W.HWND
    user.SendMessageW.argtypes=(W.HWND,W.UINT,C.c_size_t,C.c_ssize_t);user.SendMessageW.restype=C.c_ssize_t
    user.SetFocus.argtypes=(W.HWND,);user.SetFocus.restype=W.HWND
    user.DestroyWindow.argtypes=(W.HWND,)
    kernel.GetCurrentThreadId.restype=W.DWORD
    handles=[]
    try:
        for password in (False,True):
            hwnd=user.CreateWindowExW(0,'EDIT','',0x50010000 | (0x20 if password else 0x4),10,10,450,150,root.winfo_id(),None,None,None)
            assert hwnd;handles.append(hwnd)
            prefix='前😀';selection='選択した文\t値\r\n次';content=prefix+selection+'の後ろ'
            buffer=C.create_unicode_buffer(content)
            user.SendMessageW(hwnd,0x0c,0,C.cast(buffer,C.c_void_p).value)
            start=len(prefix.encode('utf-16-le'))//2;end=start+len(selection.encode('utf-16-le'))//2
            user.SendMessageW(hwnd,0xb1,start,end);user.SetFocus(hwnd);root.update()
            source=S.Source(int(user.GetParent(root.winfo_id()) or root.winfo_id()),int(hwnd),os.getpid(),kernel.GetCurrentThreadId())
            result=[];errors=[]
            def run():
                try:result.append(S.read_selection(source,time.monotonic()+2,threading.Event(),focused=lambda automation:automation.object(6,hwnd,types=(W.HWND,))))
                except BaseException as error:errors.append(repr(error))
            with patch.object(S,'source_now',return_value=source):
                thread=threading.Thread(target=run,daemon=True);thread.start();limit=time.monotonic()+4
                while thread.is_alive() and time.monotonic()<limit:root.update();time.sleep(.002)
                assert not thread.is_alive(),'owned UIA request did not finish'
            assert not errors,errors
            expected=None if password else selection.replace('\r\n','\n')
            assert result==[expected],(password,result,expected)
            print('OWNED_NATIVE_SELECTION_OK',dict(password=password,selected_chars=len(result[0]) if result[0] else 0),flush=True)
            user.DestroyWindow(hwnd);handles.remove(hwnd)
    finally:
        for hwnd in handles:user.DestroyWindow(hwnd)
        root.destroy()


import unittest

@unittest.skipUnless(sys.platform=='win32','Windows native selection provider')
class NativeSelectionTests(unittest.TestCase):
    def test_owned_edit_selected_range_and_password_are_distinguished(self):main()

if __name__=='__main__':unittest.main()

