# -*- coding: utf-8 -*-
"""本文の中のタイトル（body_index の訳し）の下の位置の答え（2026-11-17）。
・答えの列は、タイトルの無い欄と同じ Tk の書き方のまま（Tk 8.6.9 は絵文字を2列と書く。アプリは _python_text_position で
  字の位置へ戻す決まりなので、列を字の数で書き直すと、それを当てにする所が壊れた: tests_gui_quote_continuation で
  絵文字の後ろの計算が「=」の引用に入った。試した形は入れていない）
・tkinter の dump は答えを -command の呼び返しで受け、そこでは行の番号が見出しの行数ぶん下のままだった。本文の位置に直す
  （CN_BODY_INDEX_CP=0 で前の形）
自分の Tk の窓だけ・作った例文。"""
import os
import tkinter as tk
import unittest
from unittest import mock

import title_inline as TI

LINE = '甲\U0001F600乙丙丁'


class AnswersUnderTheTitle(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def pane(self, head):
        t = tk.Text(self.root, undo=True)
        if head:
            TI.prepare(t)
            TI.write(t, '題', [])
        t.insert('1.0', LINE + '\n二行目')
        t.mark_set('m1', '1.3')
        t.tag_add('sel', '1.3', '1.4')
        return t

    def answers(self, t):
        return dict(index=t.index('1.3'), end=t.index('1.end'), search=t.search('丙', '1.0'),
                    ranges=[str(x) for x in t.tag_ranges('sel')],
                    dump=[x for x in t.dump('1.0', '1.end', mark=True) if x[1] == 'm1'],
                    row2=t.index('2.2'))

    def test_same_answers_as_a_pane_without_the_title(self):
        self.assertEqual(self.answers(self.pane(True)), self.answers(self.pane(False)))

    def test_switch_back_leaves_dump_rows_below(self):
        self.root.destroy()
        with mock.patch.dict(os.environ, {'CN_BODY_INDEX_CP': '0'}):
            self.root = tk.Tk()
            self.root.withdraw()
            got = self.answers(self.pane(True))['dump']
        self.assertEqual(got[0][2].split('.')[0], '2')          # 前の動き: 見出しの1行ぶん下の行


if __name__ == '__main__':
    unittest.main()
