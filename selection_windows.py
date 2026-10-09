# -*- coding: utf-8 -*-
"""Read the explicitly focused selection on demand, without using the clipboard."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import os,sys,time,uuid

MAX_TEXT=100000
MAX_CELLS=10000


@dataclass(frozen=True)
class Source:
    foreground:int
    focus:int
    process:int
    thread:int


def source_now():
    if sys.platform!='win32':return None
    from quick_ime import _api,_GuiInfo
    u=_api();foreground=u.GetForegroundWindow();pid=W.DWORD()
    thread=u.GetWindowThreadProcessId(foreground,C.byref(pid)) if foreground else 0
    info=_GuiInfo();info.cbSize=C.sizeof(info)
    if not thread or not u.GetGUIThreadInfo(thread,C.byref(info)) or not info.hwndFocus:return None
    if u.GetForegroundWindow()!=foreground:return None
    return Source(int(foreground),int(info.hwndFocus),pid.value,thread)


def grid_text(cells):
    """Selected cells only; holes keep their grid spacing without being read."""
    values={}
    for row,column,value in cells:
        if type(row) is not int or type(column) is not int or min(row,column)<0:return None
        if not isinstance(value,str):return None
        key=(row,column)
        if key in values and values[key]!=value:return None
        values[key]=value
        if len(values)>MAX_CELLS:return None
    if not values:return None
    top=min(r for r,c in values);bottom=max(r for r,c in values)
    left=min(c for r,c in values);right=max(c for r,c in values)
    if (bottom-top+1)*(right-left+1)>MAX_CELLS:return None
    text='\n'.join('\t'.join(values.get((r,c),'') for c in range(left,right+1)) for r in range(top,bottom+1))
    return text if len(text)<=MAX_TEXT else None


class Unavailable(Exception):pass


class GUID(C.Structure):
    _fields_=[('a',C.c_uint32),('b',C.c_uint16),('c',C.c_uint16),('d',C.c_ubyte*8)]


def guid(value):return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)


def method(pointer,index,*types):
    table=C.cast(pointer,C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(C.c_int32,C.c_void_p,*types)(table[index])


def check(hr):
    if hr<0:raise Unavailable('Selection provider unavailable')


class Com:
    def __init__(self,pointer):self.pointer=pointer
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        if self.pointer:method(self.pointer,2)(self.pointer);self.pointer=None
    def output(self,index,kind,*values,types=()):
        result=kind();check(method(self.pointer,index,*types,C.POINTER(kind))(self.pointer,*values,C.byref(result)))
        return result.value
    def object(self,index,*values,types=()):
        pointer=self.output(index,C.c_void_p,*values,types=types)
        if not pointer:raise Unavailable('No selection object')
        return Com(pointer)
    def integer(self,index):return self.output(index,C.c_int)
    def pattern(self,identifier,iid):
        identity=guid(iid)
        return self.object(14,identifier,C.byref(identity),types=(C.c_int,C.POINTER(GUID)))


def libraries():
    ole=C.WinDLL('ole32');auto=C.WinDLL('oleaut32')
    ole.CoInitializeEx.argtypes=(C.c_void_p,W.DWORD);ole.CoInitializeEx.restype=C.c_int32
    ole.CoUninitialize.argtypes=()
    ole.CoCreateInstance.argtypes=(C.POINTER(GUID),C.c_void_p,W.DWORD,C.POINTER(GUID),C.POINTER(C.c_void_p));ole.CoCreateInstance.restype=C.c_int32
    auto.SysStringLen.argtypes=(C.c_void_p,);auto.SysStringLen.restype=W.UINT
    auto.SysFreeString.argtypes=(C.c_void_p,)
    return ole,auto


def bstr(pointer,auto):
    if not pointer:return ''
    try:return C.wstring_at(pointer,auto.SysStringLen(pointer))
    finally:auto.SysFreeString(pointer)


def text_selection(element,auto,current):
    with element.pattern(10014,'32eba289-3583-42c9-9c59-3b6d9a1e9b6a') as pattern:
      with pattern.object(5) as ranges:
        count=ranges.integer(3)
        if not 0<=count<=100:raise Unavailable('Too many selected ranges')
        parts=[];total=0
        for index in range(count):
            current()
            with ranges.object(4,index,types=(C.c_int,)) as item:
                value=bstr(item.output(12,C.c_void_p,MAX_TEXT-total+1,types=(C.c_int,)),auto)
                total+=len(value)
                if total>MAX_TEXT:raise Unavailable('Selection is too large')
                if value:parts.append(value)
        value='\n'.join(parts)
        if len(value)>MAX_TEXT:raise Unavailable('Selection is too large')
        return value


def selected_grid(element,auto,current,process):
    try:
        item=element.pattern(10010,'a8efa66a-0fda-421a-9194-38021f3578ea')
    except Unavailable:
        container=None
    else:
        with item:container=item.object(7)
    try:
        target=container or element
        with target.pattern(10001,'5ed5202e-b2ac-47a6-b638-4b0bf140d78e') as pattern:
          with pattern.object(3) as selected:
            count=selected.integer(3)
            if not 0<count<=MAX_CELLS:raise Unavailable('Unsupported cell selection')
            cells=[];total=0
            for index in range(count):
                current()
                with selected.object(4,index,types=(C.c_int,)) as cell:
                    if cell.integer(20)!=process or cell.integer(35):raise Unavailable('Private or different selection')
                    with cell.pattern(10007,'78f8ef57-66c3-4e09-bd7c-e79b2004894d') as grid:
                        row,column=grid.integer(4),grid.integer(5)
                        if grid.integer(6)!=1 or grid.integer(7)!=1:raise Unavailable('Spanning cell selection')
                    with cell.pattern(10002,'a94cd8b1-0844-4cd6-9d2d-640537ab39e9') as value:
                        text=bstr(value.output(4,C.c_void_p),auto)
                    total+=len(text)
                    if total>MAX_TEXT:raise Unavailable('Selection is too large')
                    cells.append((row,column,text))
            return grid_text(cells)
    finally:
        if container:container.close()


def read_selection(source,deadline,cancelled,*,focused=None):
    """Worker-thread entry. Tests may supply only an owned UIA element getter."""
    if sys.platform!='win32' or source is None:return None
    def current():
        if cancelled.is_set() or time.monotonic()>deadline:raise Unavailable('Selection request expired')
        if source_now()!=source:raise Unavailable('Selection source changed')
    ole,auto=libraries();initialized=False
    try:
        current();check(ole.CoInitializeEx(None,0));initialized=True
        # Bind Office access to the focused EXCEL7 document window, never ROT.
        from selection_excel import excel_selection
        found,value=excel_selection(source,auto,current)
        if found:
            current();return value
        identity=guid('34723aff-0c9d-49d0-9896-7ab52df8cd8a')
        cls=guid('e22ad333-b25f-460c-83d0-0581107395c9');pointer=C.c_void_p()
        check(ole.CoCreateInstance(C.byref(cls),None,1,C.byref(identity),C.byref(pointer)))
        with Com(pointer.value) as automation:
            # No provider focus manipulation; each cross-process call is bounded.
            for slot,value in ((59,0),(61,120),(63,120)):
                check(method(automation.pointer,slot,W.DWORD)(automation.pointer,value))
            current()
            with (focused(automation) if focused else automation.object(8)) as element:
                if element.integer(20)!=source.process or element.integer(35):return None
                try:value=selected_grid(element,auto,current,source.process)
                except Unavailable:value=None
                if value is None:
                    current();value=text_selection(element,auto,current)
                current()
                return value.replace('\r\n','\n').replace('\r','\n') if value is not None else None
    except (Unavailable,OSError,ValueError,AttributeError):return None
    finally:
        if initialized:ole.CoUninitialize()
