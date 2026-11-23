# -*- coding: utf-8 -*-
"""行頭の見出しの印を入れた後の予測は、クリップボードの字と、近くの行で多く使われている名詞（2026-11-23 うにさん「文頭の
見出しを付けたあとの、クリップボードや多い名詞の予測を出すように切り替える」）。行頭の一覧に無い印（「1.」「(1)」「◎」）の
後も同じ。どれも無い時は、接続詞・続きの字を出さない（何も出さない）。CN_PREDICT_AFTER_HEAD_MARK=0 で前の形。
自分の Text の窓だけ・作った例文・クリップボードは作り物（読むだけの口を差し替える）。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import f5_predict as F

BODY = '会議の資料を確認します。\n会議の予定を連絡します。\n資料の準備をします。\n'


class AfterHeadMark(unittest.TestCase):
    def setUp(self):
        import ime_watch
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        F.set_provider(None)
        p = mock.patch.object(ime_watch, 'wide_input', lambda hwnd: None)
        p.start()
        self.addCleanup(p.stop)
        self.clip = None
        p2 = mock.patch.object(F, 'clipboard_text', lambda app: self.clip)
        p2.start()
        self.addCleanup(p2.stop)

    def at_end(self, text):
        self.w.delete('1.0', 'end')
        self.w.insert('1.0', text)
        self.w.mark_set('insert', 'end-1c')
        before = self.w.get('insert linestart', 'insert')
        row = int(self.w.index('insert').split('.')[0])
        return F.candidates(None, self.w, row, len(before), before)

    def test_marks_get_clipboard_and_nouns(self):
        self.clip = '議事録'
        for mark in ('・', '■', '1.', '(1)', '◎', '　└'):
            got = self.at_end(BODY + mark)
            self.assertEqual(got[0], '議事録', (mark, got))                 # クリップボードが先
            self.assertIn('会議', got, (mark, got))                          # 近くで多い名詞
            self.assertIn('資料', got, (mark, got))

    def test_nothing_else_when_there_is_no_clipboard_or_noun(self):
        got = self.at_end('1.')
        self.assertEqual(got, [], got)                                     # 接続詞・続きの字は出さない

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_PREDICT_AFTER_HEAD_MARK': '0'}):
            got = self.at_end(BODY + '1.')
        self.assertNotIn('会議', got, got)                                  # 前の形: 一覧に無い印の後は名詞を出さなかった


if __name__ == '__main__':
    unittest.main()
