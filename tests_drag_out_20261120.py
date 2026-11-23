# -*- coding: utf-8 -*-
"""選んだ範囲を窓の外へドラッグして落とす（drag_out・2026-11-20 うにさん「アプリ外の入力欄にドロップできるように
する。この場合は複製として元の文字を残す」）。OLE の物（IDataObject・IDropSource）は ctypes で作る。
試験は作り物の受け手（COM の表を通して GetData を呼ぶ）だけで、ほかのアプリの窓へは落とさない・クリップボードは触らない。"""
import ctypes
import os
import sys
import tkinter as tk
import unittest
from ctypes import wintypes as W
from types import SimpleNamespace as NS
from unittest import mock

import drag_out as O


def call(pointer, slot, restype, *argtypes):
    """COM の物の表の slot 番目を呼ぶ形を返す（受け手のふりをする）。"""
    vtbl = ctypes.cast(ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return lambda *a: proto(vtbl[slot])(pointer, *a)


def read_hglobal(h):
    k32 = ctypes.windll.kernel32
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k32.GlobalSize.argtypes = [ctypes.c_void_p]
    k32.GlobalSize.restype = ctypes.c_size_t
    k32.GlobalFree.argtypes = [ctypes.c_void_p]
    p = k32.GlobalLock(h)
    data = ctypes.string_at(p, k32.GlobalSize(h))
    k32.GlobalUnlock(h)
    k32.GlobalFree(h)
    return data


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class OleObjects(unittest.TestCase):
    def test_receiver_reads_unicode_and_ansi_text_through_the_com_table(self):
        data = O.DataObject('移す字abc')
        get = call(data.pointer, 3, ctypes.c_long, ctypes.POINTER(O.FORMATETC), ctypes.POINTER(O.STGMEDIUM))
        query = call(data.pointer, 5, ctypes.c_long, ctypes.POINTER(O.FORMATETC))
        fmt = O.FORMATETC(O.CF_UNICODETEXT, None, 1, -1, O.TYMED_HGLOBAL)
        self.assertEqual(query(ctypes.byref(fmt)), O.S_OK)
        medium = O.STGMEDIUM()
        self.assertEqual(get(ctypes.byref(fmt), ctypes.byref(medium)), O.S_OK)
        raw = read_hglobal(medium.hGlobal)
        self.assertEqual(raw.decode('utf-16-le').split('\0')[0], '移す字abc')
        fmt = O.FORMATETC(O.CF_TEXT, None, 1, -1, O.TYMED_HGLOBAL)
        medium = O.STGMEDIUM()
        self.assertEqual(get(ctypes.byref(fmt), ctypes.byref(medium)), O.S_OK)
        self.assertEqual(read_hglobal(medium.hGlobal).split(b'\0')[0].decode('mbcs'), '移す字abc')
        files = O.FORMATETC(15, None, 1, -1, O.TYMED_HGLOBAL)                 # CF_HDROP は渡さない
        self.assertEqual(query(ctypes.byref(files)), O.DV_E_FORMATETC)

    def test_query_interface_and_enum(self):
        data = O.DataObject('x')
        qi = call(data.pointer, 0, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        out = ctypes.c_void_p()
        iid = (ctypes.c_ubyte * 16).from_buffer_copy(O._guid('0000010E-0000-0000-C000-000000000046'))
        self.assertEqual(qi(ctypes.byref(iid), ctypes.byref(out)), O.S_OK)
        self.assertEqual(out.value, data.pointer)
        enum = call(data.pointer, 8, ctypes.c_long, W.DWORD, ctypes.POINTER(ctypes.c_void_p))
        got = ctypes.c_void_p()
        self.assertEqual(enum(O.DATADIR_GET, ctypes.byref(got)), O.S_OK)
        self.assertTrue(got.value)
        call(got.value, 2, W.ULONG)()                                          # Release

    def test_drop_source_decisions(self):
        src = O.DropSource(inside=lambda x, y: False)
        cont = call(src.pointer, 3, ctypes.c_long, W.BOOL, W.DWORD)
        self.assertEqual(cont(1, O.MK_LBUTTON), O.DRAGDROP_S_CANCEL)            # Esc
        self.assertEqual(cont(0, 0), O.DRAGDROP_S_DROP)                         # 左を離した
        self.assertEqual(cont(0, O.MK_LBUTTON), O.S_OK)                         # 外で押したまま
        back = O.DropSource(inside=lambda x, y: True)
        self.assertEqual(call(back.pointer, 3, ctypes.c_long, W.BOOL, W.DWORD)(0, O.MK_LBUTTON), O.DRAGDROP_S_CANCEL)
        self.assertTrue(back.back)                                              # 窓の中へ戻った
        released = O.DropSource(inside=lambda x, y: True)
        self.assertEqual(call(released.pointer, 3, ctypes.c_long, W.BOOL, W.DWORD)(0, 0), O.DRAGDROP_S_CANCEL)
        self.assertTrue(released.back)                      # 窓の中で離した: OLE では落とさない（アプリの中で落とす）

    def test_drag_text_out_with_a_fake_receiver(self):
        got = {}

        def receiver(data_ptr, source_ptr, effects, effect):
            self.assertEqual(effects, O.DROPEFFECT_COPY)                       # 複製だけ
            get = call(data_ptr, 3, ctypes.c_long, ctypes.POINTER(O.FORMATETC), ctypes.POINTER(O.STGMEDIUM))
            fmt = O.FORMATETC(O.CF_UNICODETEXT, None, 1, -1, O.TYMED_HGLOBAL)
            medium = O.STGMEDIUM()
            get(ctypes.byref(fmt), ctypes.byref(medium))
            got['text'] = read_hglobal(medium.hGlobal).decode('utf-16-le').split('\0')[0]
            effect._obj.value = O.DROPEFFECT_COPY
            return O.DRAGDROP_S_DROP
        self.assertEqual(O.drag_text_out('外へ', dodragdrop=receiver), 'dropped')
        self.assertEqual(got['text'], '外へ')
        with mock.patch.dict(os.environ, {'CN_DRAG_OUT': '0'}):
            self.assertEqual(O.drag_text_out('外へ', dodragdrop=receiver), 'cancelled')


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class DragMoveGoesOut(unittest.TestCase):
    def setUp(self):
        import drag_move
        self.D = drag_move
        self.root = tk.Tk()
        self.root.geometry('500x200+40+40')
        self.w = tk.Text(self.root, undo=True, font=('Courier New', 12))
        self.w.pack(fill='both', expand=True)
        self.w.insert('1.0', 'alpha beta gamma')
        self.root.update()
        self.app = NS(_show_copy_frame=lambda *a: None, _clear_copy_emphasis=lambda: None, _on_change=lambda *a: None,
                      _title_toc=None)
        self.d = drag_move.install(self.app, self.w)
        self.w.tag_add('sel', '1.6', '1.10')
        x, y, bw, bh = self.w.bbox('1.7')
        self.d.press(NS(x=x + bw // 2, y=y + bh // 2, state=0))
        self.d.motion(NS(x=x + 40, y=y + bh // 2, state=0, x_root=self.w.winfo_rootx() + x + 40,
                         y_root=self.w.winfo_rooty() + y))
        self.assertEqual(self.d.state, 'dragging')

    def tearDown(self):
        self.root.destroy()

    def out_event(self):
        return NS(x=-50, y=10, state=0, x_root=self.root.winfo_rootx() - 300, y_root=self.root.winfo_rooty() + 10)

    def test_dropped_outside_keeps_the_original(self):
        with mock.patch('drag_out.drag_text_out', return_value='dropped') as out:
            self.assertEqual(self.d.motion(self.out_event()), 'break')
        out.assert_called_once()
        self.assertEqual(out.call_args[0][0], 'beta')
        self.assertIsNone(self.d.state)
        self.assertEqual(self.w.get('1.0', 'end-1c'), 'alpha beta gamma')     # 元の字は残す（複製）

    def test_back_inside_goes_on_with_the_move(self):
        with mock.patch('drag_out.drag_text_out', return_value='back'), \
                mock.patch.object(self.D.DragMove, '_left_down', staticmethod(lambda: True)):    # まだ押している
            self.d.motion(self.out_event())
        self.assertEqual(self.d.state, 'dragging')

    def test_back_and_released_inside_drops_in_the_app(self):
        x, y, bw, bh = self.w.bbox('1.16')
        with mock.patch('drag_out.drag_text_out', return_value='back'), \
                mock.patch.object(self.D.DragMove, '_left_down', staticmethod(lambda: False)), \
                mock.patch.object(self.w, 'winfo_pointerx', return_value=self.w.winfo_rootx() + x + bw), \
                mock.patch.object(self.w, 'winfo_pointery', return_value=self.w.winfo_rooty() + y + bh // 2):
            self.d.motion(self.out_event())
        self.assertIsNone(self.d.state)
        self.assertEqual(self.w.get('1.0', 'end-1c'), 'alpha  gammabeta')      # アプリの中の移動（元は消える）

    def test_switch_back_stays_inside(self):
        with mock.patch.dict(os.environ, {'CN_DRAG_OUT': '0'}), \
                mock.patch('drag_out.drag_text_out') as out:
            self.d.motion(self.out_event())
        out.assert_not_called()
        self.assertEqual(self.d.state, 'dragging')


if __name__ == '__main__':
    unittest.main()
