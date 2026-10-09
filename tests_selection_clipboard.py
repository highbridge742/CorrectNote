# -*- coding: utf-8 -*-
import ctypes,threading,unittest
from unittest.mock import Mock,patch
import selection_clipboard as C
from selection_windows import Source,MAX_TEXT


class CopySelectionTests(unittest.TestCase):
    def setUp(self):
        self.source=Source(11,12,13,14);self.now=0.;self.cancel=threading.Event()
        self.backend=Mock();self.backend.blocked_keys.return_value=False
        self.backend.sequence.return_value=42;self.backend.copy.return_value=True
        self.backend.text.return_value='旧クリップボード'
        self.snapshot=Mock(return_value=self.source)
    def wait(self,delay):self.now+=delay
    def read(self):
        return C.copy_selection(self.source,.4,self.cancel,backend=self.backend,
            snapshot=self.snapshot,clock=lambda:self.now,wait=self.wait)
    def test_rendered_browser_chat_and_excel_text_use_new_copy_only(self):
        for text in ('ブラウザーの選択😀','チャットの選択\n2行目','甲\t乙\r\n丙\t丁'):
            self.backend.reset_mock();self.now=0.;self.backend.sequence.side_effect=[42,43]
            self.backend.text.return_value=text
            self.assertEqual(self.read(),text.replace('\r\n','\n'))
            self.backend.copy.assert_called_once();self.backend.text.assert_called_once_with(43)
    def test_no_selection_or_rejected_copy_does_not_read_old_clipboard(self):
        self.assertIsNone(self.read());self.backend.text.assert_not_called()
        self.now=0.;self.backend.copy.return_value=False
        self.assertIsNone(self.read());self.backend.text.assert_not_called()
    def test_focus_change_cancellation_and_held_shortcut_stop_copy(self):
        self.snapshot.return_value=Source(21,22,23,24)
        self.assertIsNone(self.read());self.backend.copy.assert_not_called()
        self.snapshot.return_value=self.source;self.cancel.set()
        self.assertIsNone(self.read());self.backend.copy.assert_not_called()
        self.cancel.clear();self.backend.blocked_keys.return_value=True
        self.assertIsNone(self.read());self.backend.copy.assert_not_called()
    def test_release_shift_before_copy_and_recheck_source_after_read(self):
        self.backend.blocked_keys.side_effect=[True,True,False]
        self.backend.sequence.side_effect=[42,43]
        self.backend.text.return_value='new'
        self.assertEqual(self.read(),'new');self.assertGreater(self.now,0)
        self.now=0.;self.backend.blocked_keys.side_effect=None;self.backend.blocked_keys.return_value=False
        self.backend.sequence.side_effect=[42,43]
        def changed(sequence):self.snapshot.return_value=None;return 'do not import'
        self.backend.text.side_effect=changed
        self.assertIsNone(self.read())
    def test_clipboard_busy_is_retried_without_another_copy(self):
        self.backend.sequence.side_effect=[42,43,43]
        self.backend.text.side_effect=[None,'ready']
        self.assertEqual(self.read(),'ready');self.backend.copy.assert_called_once()
    def test_native_input_layout_and_held_control_are_preserved(self):
        self.assertEqual(ctypes.sizeof(C.Input),40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)
        keys=C.keyboard_inputs()
        self.assertEqual([(k.payload.keyboard.vk,k.payload.keyboard.flags) for k in keys],[(17,0),(67,0),(67,2),(17,2)])
        self.assertTrue(all(k.type==1 for k in keys))
        backend=object.__new__(C.WindowsClipboard);backend.user=Mock()
        backend.down=lambda key:key==17
        self.assertTrue(backend.blocked_keys());self.assertFalse(backend.copy())
        backend.user.SendInput.assert_not_called()
    def test_native_unicode_bounds_and_lock_release_without_system_clipboard(self):
        # Exercise native data handling with owned memory, never the user's clipboard.
        b=object.__new__(C.WindowsClipboard);b.user=Mock();b.kernel=Mock()
        b.user.OpenClipboard.return_value=1;b.user.GetClipboardSequenceNumber.return_value=43
        b.user.GetClipboardData.return_value=5
        for value in ('日本語😀\tセル\r\n次','x'*(MAX_TEXT+1)):
            raw=(value+'\0').encode('utf-16-le');memory=ctypes.create_string_buffer(raw)
            b.kernel.GlobalSize.return_value=len(raw);b.kernel.GlobalLock.return_value=ctypes.addressof(memory)
            self.assertEqual(b.text(43),value if len(value)<=MAX_TEXT else None)
        self.assertEqual(b.user.CloseClipboard.call_count,2);self.assertEqual(b.kernel.GlobalUnlock.call_count,2)
        b.user.GetClipboardSequenceNumber.return_value=44;b.user.GetClipboardData.reset_mock()
        self.assertIsNone(b.text(43));b.user.GetClipboardData.assert_not_called()
    def test_opening_prefers_fresh_copy_and_uses_uia_only_when_unavailable(self):
        with patch.object(C,'copy_selection',return_value='選択') as copy,patch('selection_windows.read_selection') as uia:
            self.assertEqual(C.read_for_opening(self.source,1e30,self.cancel),'選択');uia.assert_not_called()
        with patch.object(C,'copy_selection',return_value=None),patch.object(C,'source_now',return_value=self.source),patch('selection_windows.read_selection',return_value='UIA選択') as uia:
            self.assertEqual(C.read_for_opening(self.source,1e30,self.cancel),'UIA選択');uia.assert_called_once()


if __name__=='__main__':unittest.main()
