# -*- coding: utf-8 -*-
"""Owned HWND messages preserve explicit, even repeated IME result pairs."""
import sys,unittest,tkinter as tk
from unittest.mock import patch
import ime_events,ime_watch

@unittest.skipUnless(sys.platform=='win32','Windows messages')
class IMEResultEventsTkTests(unittest.TestCase):
    def setUp(self):
        import ctypes as C
        from ctypes import wintypes as W
        self.root=tk.Tk();self.root.withdraw();self.editor=tk.Text(self.root)
        self.hwnd=self.editor.winfo_id();self.listener=ime_events.ResultEvents(self.hwnd)
        self.assertEqual(self.listener.hwnd,self.hwnd)
        self.user=C.WinDLL('user32')
        self.user.SendMessageW.argtypes=[W.HWND,W.UINT,C.c_size_t,C.c_ssize_t]
        self.user.SendMessageW.restype=C.c_ssize_t
    def test_requested_result_and_ordinary_delivery_stay_separate(self):
        self.listener.completion=[];self.listener.expected_completion='資料'
        forward=self.listener._dll.DefSubclassProc
        with patch.object(self.listener._dll,'DefSubclassProc',wraps=forward) as delivered:
            self.send(0x800)
        delivered.assert_called_once()
        self.assertEqual(self.listener.completion,[('資料','ｼﾘｮｳ')])
        self.assertEqual(self.listener.take(),())
        self.send(0xA00,reading='べつ',surface='別')
        self.assertEqual(self.listener.take(),(('別','べつ'),))
        self.user.SendMessageW(self.hwnd,ime_events.WM_IME_STARTCOMPOSITION,0,0)
        self.assertIsNone(self.listener.completion)
        self.send(0xA00)
        self.assertEqual(self.listener.take(),(('資料','ｼﾘｮｳ'),))

    def test_actual_completed_result_is_required(self):
        got=dict(comp='',result='資料',result_reading='しりょう')
        with patch.object(ime_watch,'complete_composition',return_value=True),\
             patch.object(ime_watch,'read_composition',return_value=got):
            success,committed=self.listener.complete_current('資料')
            self.assertTrue(success);self.assertEqual(committed,(('資料','しりょう'),))
            self.assertIsNone(self.listener.completion)
        with patch.object(ime_watch,'complete_composition',return_value=True),\
             patch.object(ime_watch,'read_composition',return_value=dict(comp='入力中',result='資料')):
            success,committed=self.listener.complete_current('入力中')
            self.assertEqual(committed,());self.assertIsNone(self.listener.completion)

    def tearDown(self):
        self.listener.close();self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'listener','editor','root')
    def send(self,flags,reading='ｼﾘｮｳ',surface='資料'):
        with patch.object(ime_watch,'read_composition',return_value=dict(result=surface,result_reading=reading)):
            return self.user.SendMessageW(self.hwnd,ime_events.WM_IME_COMPOSITION,0,flags)
    def test_repeated_partial_results_are_not_collapsed_by_spelling(self):
        flags=ime_watch.GCS_RESULTSTR|ime_watch.GCS_RESULTREADSTR
        self.send(flags);self.send(flags)
        self.assertEqual(self.listener.take(),(('資料','ｼﾘｮｳ'),('資料','ｼﾘｮｳ')))
        self.assertEqual(self.listener.take(),())
    def test_same_surface_new_reading_survives_between_poll_ticks(self):
        flags=ime_watch.GCS_RESULTSTR|ime_watch.GCS_RESULTREADSTR
        self.send(flags,'ｲｯﾀ','行った');self.send(flags,'ｵｺﾅｯﾀ','行った')
        self.assertEqual(self.listener.take(),(('行った','ｲｯﾀ'),('行った','ｵｺﾅｯﾀ')))
    def test_cancel_and_unannounced_reading_do_not_reuse_stale_values(self):
        self.send(0);self.send(ime_watch.GCS_COMPSTR);self.send(ime_watch.GCS_RESULTSTR)
        self.assertEqual(self.listener.take(),())
    def test_unreadable_context_is_ignored(self):
        with patch.object(ime_watch,'read_composition',return_value=None):
            self.user.SendMessageW(self.hwnd,ime_events.WM_IME_COMPOSITION,0,0xA00)
        self.assertEqual(self.listener.take(),())
    def test_forwarding_preserves_other_subclass_return_value(self):
        listener=self.listener;message=0x8000+47;calls=[]
        def callback(hwnd,msg,wp,lp,uid,ref):
            if msg==message:calls.append((wp,lp));return 753
            return listener._dll.DefSubclassProc(hwnd,msg,wp,lp)
        probe=listener._type(callback)
        self.assertTrue(listener._dll.SetWindowSubclass(self.hwnd,probe,91,0))
        try:
            # Reattach observer on top, so the message must pass through it.
            listener.close();self.listener=ime_events.ResultEvents(self.hwnd)
            self.assertEqual(self.user.SendMessageW(self.hwnd,message,12,34),753)
            self.assertEqual(calls,[(12,34)])
        finally:listener._dll.RemoveWindowSubclass(self.hwnd,probe,91)
    def test_close_detaches_and_clears_pending_without_changing_editor(self):
        self.editor.insert('1.0','既存の本文')
        self.send(0xA00);self.listener.close();self.listener.close();self.send(0xA00)
        self.assertEqual(self.listener.take(),());self.assertEqual(self.listener.hwnd,0)
        self.assertEqual(self.editor.get('1.0','end-1c'),'既存の本文')
    def test_window_destruction_releases_native_callback(self):
        uid=self.listener._uid;self.assertIn(uid,ime_events._LIVE)
        self.editor.destroy();self.assertEqual(self.listener.hwnd,0)
        self.assertNotIn(uid,ime_events._LIVE)

    def test_native_result_clauses_preserve_whole_saved_pair_and_exact_positions(self):
        r=self.listener.ranges;r.set_owner('tab')
        self.user.SendMessageW(self.hwnd,ime_events.WM_IME_STARTCOMPOSITION,0,0)
        flags=(ime_watch.GCS_RESULTSTR|ime_watch.GCS_RESULTREADSTR
            |ime_watch.GCS_RESULTCLAUSE|ime_watch.GCS_RESULTREADCLAUSE)
        got=dict(result='海上読奥',result_reading='ｶｲｼﾞｮｳﾖﾖｸ',
                 result_clauses=(('海上','ｶｲｼﾞｮｳ'),('読奥','ﾖﾖｸ')))
        with patch.object(ime_watch,'read_composition',return_value=got) as read:
            self.user.SendMessageW(self.hwnd,ime_events.WM_IME_COMPOSITION,0,flags)
        self.assertEqual(read.call_args.kwargs,dict(result_clauses=True))
        r.edited('tab',(1,1),(1,5))
        self.user.SendMessageW(self.hwnd,ime_events.WM_IME_ENDCOMPOSITION,0,0)
        self.assertEqual(r.take('tab','前海上読奥'),
            ((1,3,'海上','ｶｲｼﾞｮｳ'),(3,5,'読奥','ﾖﾖｸ')))
        self.assertEqual(self.listener.take(),(('海上読奥','ｶｲｼﾞｮｳﾖﾖｸ'),))

    def test_unannounced_clause_data_is_not_requested(self):
        flags=ime_watch.GCS_RESULTSTR|ime_watch.GCS_RESULTREADSTR
        for announced in (flags,flags|ime_watch.GCS_RESULTCLAUSE):
            with patch.object(ime_watch,'read_composition',return_value=dict(result='資料',result_reading='ｼﾘｮｳ')) as read:
                self.user.SendMessageW(self.hwnd,ime_events.WM_IME_COMPOSITION,0,announced)
            self.assertEqual(read.call_args.kwargs,dict(result_clauses=False))


if __name__=='__main__':unittest.main()
