# -*- coding: utf-8 -*-
"""An owned in-process IDispatch verifies native ABI, arguments and ownership."""
import ctypes as C,sys,unittest
from ctypes import wintypes as W
from selection_windows import libraries,Unavailable
from selection_excel import Dispatch,Variant,Parameters,ExceptionInfo


@unittest.skipUnless(sys.platform=='win32','Windows COM ABI')
class DispatchSelectionTests(unittest.TestCase):
    def test_native_property_get_bstr_integer_dispatch_and_index_order(self):
        ole,auto=libraries();auto.VariantClear.argtypes=(C.POINTER(Variant),)
        auto.SysAllocString.argtypes=(W.LPCWSTR,);auto.SysAllocString.restype=C.c_void_p
        callbacks=[];calls=[];releases=[];ids={'Text':10,'Count':11,'Child':12,'Item':13,'Failure':14}
        interface=(C.c_void_p*1)()
        def callback(index,types,function):
            value=C.WINFUNCTYPE(C.c_int32,C.c_void_p,*types)(function)
            callbacks.append(value);table[index]=C.cast(value,C.c_void_p).value
        table=(C.c_void_p*7)()
        callback(2,(),lambda pointer:releases.append(pointer) or 1)
        def names(pointer,iid,names,count,locale,identifier):
            assert count==1;identifier[0]=ids[names[0]];return 0
        callback(5,(C.c_void_p,C.POINTER(W.LPWSTR),W.UINT,W.DWORD,C.POINTER(C.c_int32)),names)
        def invoke(pointer,identifier,iid,locale,flags,parameters,result,info,error):
            assert flags==2
            params=parameters.contents;out=result.contents;calls.append((identifier,params.count))
            if identifier in (10,13):
                if identifier==13:assert [params.args[i].number for i in range(params.count)]==[3,2]
                out.vt=8;out.pointer=auto.SysAllocString('合成😀\t値')
            elif identifier==11:out.vt=3;out.number=6
            elif identifier==12:out.vt=9;out.pointer=C.addressof(interface)
            else:
                info.contents.description=auto.SysAllocString('Synthetic unavailable property')
                return C.c_int32(0x80020009).value
            return 0
        callback(6,(C.c_int32,C.c_void_p,W.DWORD,W.WORD,C.POINTER(Parameters),C.POINTER(Variant),C.POINTER(ExceptionInfo),C.POINTER(W.UINT)),invoke)
        interface[0]=C.cast(table,C.c_void_p).value
        with Dispatch(C.addressof(interface),auto,lambda:None) as obj:
            self.assertEqual(obj.get('Text'),'合成😀\t値')
            self.assertEqual(obj.get('Count'),6)
            with obj.get('Child') as child:self.assertEqual(child.get('Item',2,3),'合成😀\t値')
            with self.assertRaises(Unavailable):obj.get('Failure')
        self.assertEqual(len(releases),2)
        self.assertEqual(calls,[(10,0),(11,0),(12,0),(13,2),(14,0)])

    def test_insert_normalizes_line_endings_and_preserves_draft_as_one_undo(self):
        import tkinter as tk
        from types import SimpleNamespace
        from quick_selection import insert_selection
        root=tk.Tk();root.withdraw();text=tk.Text(root,undo=True)
        try:
            text.insert('1.0','既存');text.mark_set('insert','1.end');text.edit_reset()
            insert_selection(SimpleNamespace(_quick_text=text),'甲\t乙\r\n丙\r丁')
            self.assertEqual(text.get('1.0','end-1c'),'既存甲\t乙\n丙\n丁')
            text.edit_undo();self.assertEqual(text.get('1.0','end-1c'),'既存')
        finally:root.destroy()


if __name__=='__main__':unittest.main()
