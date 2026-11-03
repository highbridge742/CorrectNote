# -*- coding: utf-8 -*-
"""マウスの2つの操作（2026-10-30 うにさん）: 右を押しながら左でコピー／貼り付け、左ダブルクリックで語だけを選び
そのままドラッグで語の単位に広げる（mouse_words）。窓は出さない・焦点は取らない。"""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import mouse_words as M


class WordAtTests(unittest.TestCase):
    def test_words_not_the_whole_line(self):
        line = '今日は資料を確認します'
        self.assertEqual(M.word_at(line, 4), (3, 5))          # 資料
        self.assertEqual(M.word_at(line, 6)[0], 6)            # 確認… starts at 確
        self.assertLess(M.word_at(line, 6)[1], len(line))     # not up to the end of the line
        self.assertEqual(M.word_at('hello world', 1), (0, 5))
        self.assertEqual(M.word_at('ＡＢＣで書く', 1), (0, 3))
        self.assertEqual(M.word_at('「鏡」', 0), (0, 1))       # a bracket alone


class MouseTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.text = tk.Text(self.root)
        self.text.insert('1.0', '今日は資料を確認します\n二行目の文')
        self.app = SimpleNamespace(root=self.root, _copy_focused_selection=Mock())
        M.install(self.app, self.text)

    def tearDown(self):
        self.root.destroy()

    def event(self, state=0):
        return SimpleNamespace(widget=self.text, state=state, x=0, y=0)

    def test_installed_ahead_of_the_text_class(self):
        tags = self.text.bindtags()
        self.assertLess(tags.index(M.TAG), tags.index('Text'))

    def test_right_held_left_click_copies_a_selection(self):
        self.text.tag_add('sel', '1.3', '1.5')
        self.assertEqual(M._press(self.app, self.event(M.BUTTON3_MASK)), 'break')
        self.app._copy_focused_selection.assert_called_once()
        self.assertTrue(M.take_chord(self.app))
        self.assertFalse(M.take_chord(self.app))               # once

    def test_right_held_left_click_pastes_without_a_selection(self):
        pasted = []
        self.text.bind('<<Paste>>', lambda e: pasted.append(True))
        self.text.focus_set = lambda: None
        self.assertEqual(M._press(self.app, self.event(M.BUTTON3_MASK)), 'break')
        self.assertEqual(pasted, [True])
        self.app._copy_focused_selection.assert_not_called()

    def test_a_plain_left_click_is_left_to_tk(self):
        self.assertIsNone(M._press(self.app, self.event(0)))
        self.assertFalse(M.take_chord(self.app))

    def test_double_click_selects_a_word_and_dragging_extends_by_words(self):
        t = self.text
        with patch.object(M, '_word_range', return_value=(1, 3, 5)):
            self.assertEqual(M._double(self.app, self.event()), 'break')
        self.assertEqual(t.get('sel.first', 'sel.last'), '資料')
        with patch.object(M, '_word_range', return_value=(1, 6, 8)):      # dragged onto 確認
            self.assertEqual(M._motion(self.app, self.event()), 'break')
        self.assertEqual(t.get('sel.first', 'sel.last'), '資料を確認')
        with patch.object(M, '_word_range', return_value=(1, 0, 2)):      # back over 今日
            M._motion(self.app, self.event())
        self.assertEqual(t.get('sel.first', 'sel.last'), '今日は資料')
        self.assertEqual(t.index('insert'), '1.0')
        M._release(self.app, self.event())
        self.assertIsNone(M._motion(self.app, self.event()))           # an ordinary drag again


if __name__ == '__main__':
    unittest.main()
