# -*- coding: utf-8 -*-
"""F5 の再変換・補正欄で候補を選んだのに何も変わらなかった（2026-11-14 うにさん「F5再変換で撃っての候補から打ってを
選んだが、何も変わらなかった。別のひらがなの言葉も再変換で変わらなかった」）。2026-11-08 から選びは覚えない
（last_choice.LEARNED_OFF）ので、統合表示の自動反映と補正欄の「覚えるだけ」の道では答えが変わらなかった。覚えない間は
本文を直に書き換える。学んだ語を使わない決まり（LEARNED_OFF）は変えない。CN_CHOICE_TO_SOURCE=0 で前の形。作った値だけ。"""
import os
import tkinter as tk
import unittest
from unittest import mock

import app
import last_choice


class TakeEffect(unittest.TestCase):
    def test_follows_learned_off(self):
        fake = object()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CN_CHOICE_TO_SOURCE', None)
            with mock.patch.object(last_choice, 'LEARNED_OFF', True):
                self.assertFalse(app.CorrectNoteApp._choices_take_effect(fake))
            with mock.patch.object(last_choice, 'LEARNED_OFF', False):
                self.assertTrue(app.CorrectNoteApp._choices_take_effect(fake))
            with mock.patch.object(last_choice, 'LEARNED_OFF', True), \
                    mock.patch.dict(os.environ, {'CN_CHOICE_TO_SOURCE': '0'}):
                self.assertTrue(app.CorrectNoteApp._choices_take_effect(fake))

    def test_learned_history_still_off_by_default(self):
        # 学んだ語・最後の選択を使わない決まりはそのまま（CN_LEARNED_HISTORY=1 の時だけ前の形）
        if os.environ.get('CN_LEARNED_HISTORY') != '1':
            self.assertTrue(last_choice.LEARNED_OFF)


class EditorChoice(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def _fake(self, take_effect):
        editor = tk.Text(self.root)
        editor.insert('1.0', '文字を撃って書く')
        unit = dict(start=3, end=6, text='撃って', base='撃って', prev='を', next='書く', reading='うって')
        fake = mock.Mock()
        fake.editor = editor
        fake._candidate_selection_unit = lambda row, u, cand, widget: u
        fake.unified_autofix_on = lambda: True
        fake._choices_take_effect = lambda: take_effect
        fake._supersede_prior_choice = lambda *a, **k: None
        fake._dropdown_via_f2 = True
        return fake, unit

    def test_unified_autofix_writes_the_source_while_choices_are_off(self):
        fake, unit = self._fake(False)
        app.CorrectNoteApp._editor_choose_word(fake, 1, unit, {'surface': '打って'})
        self.assertEqual(fake.editor.get('1.0', '1.end'), '文字を打って書く')
        fake._on_change.assert_called()

    def test_unified_autofix_records_only_when_choices_work(self):
        fake, unit = self._fake(True)
        app.CorrectNoteApp._editor_choose_word(fake, 1, unit, {'surface': '打って'})
        self.assertEqual(fake.editor.get('1.0', '1.end'), '文字を撃って書く')     # 前の形: 覚えて自動反映に任せる
        fake.choices.record.assert_called()
        fake._analyze.assert_called()


class ResultChoice(unittest.TestCase):
    def test_result_pane_writes_the_source_while_choices_are_off(self):
        unit = dict(start=3, end=6, text='撃って', base='撃って', prev='を', next='書く')
        fake = mock.Mock()
        fake._candidate_selection_unit = lambda row, u, cand, widget: u
        fake._choices_take_effect = lambda: False
        app.CorrectNoteApp._choose_word(fake, unit, {'surface': '打って'}, row=2)
        fake._replace_result_unit_in_source.assert_called_once_with(2, unit, '打って')
        fake.choices.record.assert_not_called()

    def test_result_pane_records_when_choices_work(self):
        unit = dict(start=3, end=6, text='撃って', base='撃って', prev='を', next='書く')
        fake = mock.Mock()
        fake._candidate_selection_unit = lambda row, u, cand, widget: u
        fake._choices_take_effect = lambda: True
        fake._dropdown_via_f2 = True
        fake._choice_undo = None
        app.CorrectNoteApp._choose_word(fake, unit, {'surface': '打って'}, row=2)
        fake._replace_result_unit_in_source.assert_not_called()
        fake.choices.record.assert_called()

    def test_replace_result_unit_in_source_changes_the_editor(self):
        root = tk.Tk()
        root.withdraw()
        try:
            fake = mock.Mock()
            fake.editor = tk.Text(root)
            fake.result_view = tk.Text(root)
            fake.editor.insert('1.0', '文字を撃って書く')
            fake.result_view.insert('1.0', '文字を撃って書く')
            fake._replace_unit_text = lambda w, r, u, t: app.CorrectNoteApp._replace_unit_text(fake, w, r, u, t)
            unit = dict(start=3, end=6, text='撃って')
            app.CorrectNoteApp._replace_result_unit_in_source(fake, 1, unit, '打って')
            self.assertEqual(fake.editor.get('1.0', '1.end'), '文字を打って書く')
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
