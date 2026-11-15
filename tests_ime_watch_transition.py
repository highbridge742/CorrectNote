# -*- coding: utf-8 -*-
"""A temporary IMM failure must not masquerade as completed input."""
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
import app

class IMEWatchTransitionTests(unittest.TestCase):
    def fixture(self):
        a=SimpleNamespace(editor=SimpleNamespace(winfo_id=lambda:123),root=SimpleNamespace(after=Mock(return_value='timer')),
            _ime_comp='確認',_ime_comp_reading='ｶｸﾆﾝ',_ime_first_kana='かくにん',_ime_last_result='',
            _ime_origin_work=('own',1),_IME_POLL_IDLE_MS=150,_IME_POLL_ACTIVE_MS=30,
            _remember_ime_pair=Mock(),_on_change=Mock(),_ime_reading_tick=Mock(),
            # v1.17.0 から _ime_reading_tick が頭で呼ぶ（窓の手続きが積んだ確定の受け渡し）。作り物には積む物が無い
            _take_ime_commits=Mock())
        return a

    def tick(self,a,active,value):
        with patch('ime_watch.composition_active',return_value=active),patch('ime_watch.read_composition',return_value=value):
            app.CorrectNoteApp._ime_reading_tick(a)

    def test_unknown_state_preserves_pending_reading_then_valid_end_commits(self):
        a=self.fixture();self.tick(a,None,{})
        self.assertEqual(a._ime_comp,'確認');a._remember_ime_pair.assert_not_called();a._on_change.assert_not_called()
        self.assertEqual(a.root.after.call_args[0][0],30)
        self.tick(a,False,dict(comp='',result=''))
        a._remember_ime_pair.assert_called_once_with('確認','ｶｸﾆﾝ',require_insertion=True);a._on_change.assert_called_once()
        self.assertIsNone(a._ime_origin_work)

    def test_unreadable_composition_is_not_an_empty_commit(self):
        a=self.fixture();self.tick(a,False,None)
        self.assertEqual(a._ime_comp,'確認');a._remember_ime_pair.assert_not_called()

    def test_active_but_temporarily_empty_value_keeps_composition(self):
        a=self.fixture();self.tick(a,True,{})
        self.assertEqual(a._ime_comp,'確認');a._remember_ime_pair.assert_not_called();a._on_change.assert_not_called()

    def test_real_result_and_reading_are_used_once_on_commit(self):
        a=self.fixture();self.tick(a,False,dict(comp='',result='確認',result_reading='かくにん'))
        a._remember_ime_pair.assert_called_once_with('確認','かくにん')
        self.assertEqual(a._ime_comp,'');a._on_change.assert_called_once()

if __name__=='__main__':unittest.main()