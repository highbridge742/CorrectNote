# -*- coding: utf-8 -*-
"""再変換で選んでいる範囲を F6〜F9 で変換する（2026-10-30 うにさん「再変換で選択中に、F6 F7 F8 F9を押したら、
対応する変換を実行する」）。変換は選択の F6〜F9 と同じ（editor_transforms.transform_selection・F6 ひらがな・
F7 カタカナ・F8 半角・F9 キー）で、元は範囲の読み。"""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import app
from editor_transforms import transform_selection


class ConvertKeyTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.text = tk.Text(self.root, undo=True)
        self.text.insert('1.0', '会議を開く')
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.editor = self.text
        a._quick_text = None
        a._dropdown = None
        a._close_dropdown = Mock()
        a._forget_bracket_cycle = Mock()
        a._on_change = Mock()
        a.status = Mock()
        units = [dict(start=0, end=2, text='会議', reading='かいぎ'), dict(start=2, end=3, text='を', reading='を'),
                 dict(start=3, end=5, text='開く', reading='ひらく')]
        a._f2_cycle = dict(row=1, idx=0, units=units, widget=self.text, unified=False)
        a._f2_focus_target = dict(widget=self.text, row=1, start=0, end=2, text='会議')

    def tearDown(self):
        self.root.destroy()

    def press(self, key, widget=None):
        return self.a._on_selection_transform(SimpleNamespace(widget=widget or self.text, keysym=key, char='',
                                                              state=0, keycode=0))

    def test_each_key_converts_the_range_from_its_reading_and_keeps_it(self):
        a, t = self.a, self.text
        self.assertEqual(self.press('F7'), 'break')
        self.assertEqual(t.get('1.0', '1.end'), 'カイギを開く')
        self.assertEqual((a._f2_focus_target['start'], a._f2_focus_target['end']), (0, 3))
        self.assertEqual(t.index('insert'), '1.3')
        for key, kind in (('F8', 'halfwidth'), ('F9', 'keys'), ('F6', 'hiragana')):
            self.press(key)                                    # still the first reading
            want = transform_selection('かいぎ', kind)
            self.assertEqual(t.get('1.0', '1.end'), want + 'を開く')
        self.assertTrue(a._on_change.called)

    def test_from_the_candidate_list_too(self):
        dd = tk.Toplevel(self.root); dd.withdraw()
        lb = tk.Listbox(dd)
        self.a._dropdown = dd
        self.assertEqual(self.press('F7', widget=lb), 'break')
        self.assertEqual(self.text.get('1.0', '1.end'), 'カイギを開く')
        self.a._close_dropdown.assert_called()

    def test_a_resized_range_reads_the_units_it_covers(self):
        self.a._f2_focus_target.update(start=0, end=3, text='会議を')
        self.press('F7')
        self.assertEqual(self.text.get('1.0', '1.end'), 'カイギヲ開く')

    def test_a_text_selection_or_no_range_keeps_the_former_behaviour(self):
        self.a._f2_focus_target = None
        self.assertFalse(self.a._reconversion_transform(self.text, 'F7'))
        self.a._f2_focus_target = dict(widget=self.text, row=1, start=0, end=2, text='会議')
        self.text.tag_add('sel', '1.3', '1.5')
        self.assertFalse(self.a._reconversion_transform(self.text, 'F7'))
        self.assertEqual(self.text.get('1.0', '1.end'), '会議を開く')


if __name__ == '__main__':
    unittest.main()
