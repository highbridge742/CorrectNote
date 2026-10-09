# -*- coding: utf-8 -*-
"""Read selected Excel cells via their focused document's native object model."""
import ctypes as C
from ctypes import wintypes as W
from selection_windows import Com,GUID,guid,method,check,Unavailable,grid_text,MAX_TEXT,MAX_CELLS


class _Record(C.Structure):
    _fields_=[('record',C.c_void_p),('info',C.c_void_p)]
class _Value(C.Union):
    _fields_=[('number',C.c_int32),('real',C.c_double),('pointer',C.c_void_p),('record',_Record)]
class Variant(C.Structure):
    _anonymous_=('value',)
    _fields_=[('vt',C.c_uint16),('r1',C.c_uint16),('r2',C.c_uint16),('r3',C.c_uint16),('value',_Value)]
class Parameters(C.Structure):
    _fields_=[('args',C.POINTER(Variant)),('named',C.POINTER(C.c_int32)),('count',W.UINT),('named_count',W.UINT)]
class ExceptionInfo(C.Structure):
    _fields_=[('code',W.WORD),('reserved',W.WORD),('source',C.c_void_p),('description',C.c_void_p),
              ('help',C.c_void_p),('context',W.DWORD),('reserved_pointer',C.c_void_p),
              ('deferred',C.c_void_p),('scode',C.c_int32)]


class Dispatch(Com):
    def __init__(self,pointer,auto,current):super().__init__(pointer);self.auto=auto;self.current=current
    def get(self,name,*indexes):
        self.current()
        names=(W.LPWSTR*1)(name);identifier=C.c_int32();nil=GUID()
        check(method(self.pointer,5,C.POINTER(GUID),C.POINTER(W.LPWSTR),W.UINT,W.DWORD,C.POINTER(C.c_int32))(
            self.pointer,C.byref(nil),names,1,0,C.byref(identifier)))
        args=(Variant*len(indexes))()
        for variant,value in zip(args,reversed(indexes)):
            if type(value) is not int:raise Unavailable('Invalid cell index')
            variant.vt=3;variant.number=value
        parameters=Parameters(args,None,len(indexes),0);result=Variant();info=ExceptionInfo();error=W.UINT()
        try:
            check(method(self.pointer,6,C.c_int32,C.POINTER(GUID),W.DWORD,W.WORD,C.POINTER(Parameters),
                C.POINTER(Variant),C.POINTER(ExceptionInfo),C.POINTER(W.UINT))(
                self.pointer,identifier,C.byref(nil),0,2,C.byref(parameters),C.byref(result),C.byref(info),C.byref(error)))
            if result.vt in (0,1):return None
            if result.vt in (3,22):return int(result.number)
            if result.vt==5:return float(result.real)
            if result.vt==8:
                return C.wstring_at(result.pointer,self.auto.SysStringLen(result.pointer)) if result.pointer else ''
            if result.vt==9 and result.pointer:
                pointer=result.pointer;result.vt=0
                return Dispatch(pointer,self.auto,self.current)
            raise Unavailable('Unsupported cell value')
        finally:
            self.auto.VariantClear(C.byref(result))
            for name in ('source','description','help'):
                pointer=getattr(info,name)
                if pointer:self.auto.SysFreeString(pointer)


def selected_cells(selection,current):
    """The same bounded reader is exercised with synthetic object-model fixtures."""
    cells=[];count=0;total=0
    with selection.get('Areas') as areas:
        area_count=areas.get('Count')
        if type(area_count) is not int or not 0<area_count<=100:raise Unavailable('Unsupported areas')
        for number in range(1,area_count+1):
            current()
            with areas.get('Item',number) as area:
                row=area.get('Row');column=area.get('Column')
                with area.get('Rows') as rows:height=rows.get('Count')
                with area.get('Columns') as columns:width=columns.get('Count')
                if any(type(v) is not int or v<=0 for v in (row,column,height,width)):raise Unavailable('Unsupported range')
                count+=height*width
                if count>MAX_CELLS:raise Unavailable('Too many selected cells')
                with area.get('Cells') as items:
                    for y in range(1,height+1):
                        for x in range(1,width+1):
                            current()
                            with items.get('Item',y,x) as cell:text=cell.get('Text')
                            if text is None:text=''
                            if not isinstance(text,str):raise Unavailable('Unsupported cell text')
                            total+=len(text)
                            if total>MAX_TEXT:raise Unavailable('Selected text is too large')
                            cells.append((row+y-2,column+x-2,text))
    return grid_text(cells)


def excel_selection(source,auto,current):
    user=C.WinDLL('user32')
    user.GetClassNameW.argtypes=(W.HWND,W.LPWSTR,C.c_int);user.GetClassNameW.restype=C.c_int
    def class_name(hwnd):
        buffer=C.create_unicode_buffer(128);user.GetClassNameW(hwnd,buffer,len(buffer));return buffer.value
    # In-cell/formula editing has a separate control. Let TextPattern read its
    # selected substring instead of substituting the worksheet's last range.
    if class_name(source.foreground)!='XLMAIN' or class_name(source.focus)!='EXCEL7':return False,None
    current();oleacc=C.WinDLL('oleacc');pointer=C.c_void_p();identity=guid('00020400-0000-0000-c000-000000000046')
    oleacc.AccessibleObjectFromWindow.argtypes=(W.HWND,W.DWORD,C.POINTER(GUID),C.POINTER(C.c_void_p))
    oleacc.AccessibleObjectFromWindow.restype=C.c_int32
    auto.VariantClear.argtypes=(C.POINTER(Variant),);auto.VariantClear.restype=C.c_int32
    try:
        check(oleacc.AccessibleObjectFromWindow(source.focus,0xfffffff0,C.byref(identity),C.byref(pointer)))
        if not pointer.value:return True,None
        with Dispatch(pointer.value,auto,current) as window:
          with window.get('Application') as application:
            with application.get('ActiveWindow') as active:
                handle=active.get('Hwnd')
                if type(handle) is not int or handle&0xffffffff!=source.foreground&0xffffffff:return True,None
            with application.get('Selection') as selected:
                value=selected_cells(selected,current)
        current();return True,value
    except (Unavailable,OSError,TypeError,AttributeError):return True,None
