# -*- coding: utf-8 -*-
"""再入力変換のあとも打った読みが残る（2026-11-15 うにさん「再入力変換で変換した後、同じ所をもう一度再入力変換すると、
漢字の読みが初回と違う読みのひらがなになる。打った時のキーの記録はあるので、2回目も押したキーの読みに戻るはず」）。
開いた時の打った記録（本文の控えの確定の読みとキー）を、確定して終える時に今の範囲へ付け直す。別の所の記録はずれない。
CN_REINPUT_KEEP_TYPED=0 で前の形。作った例文だけ。IME・キー・クリップボードは使わない。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import reinput
from analysis_work import Document
from reinput import ReInput

LINE = '日の光と月'
KEYS = (('t', 1), ('u', 2))          # 作ったキーの記録（字と時刻だけ）


class KeepTyped(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.text = tk.Text(self.root, undo=True)
        self.text.insert('1.0', LINE)
        app = NS(editor=self.text, status=NS(config=lambda **k: None), settings={}, _composing=lambda w: False,
                 _text_edge_column=lambda *a: 0)
        self.doc = Document(id(app), LINE)
        app._input_document = self.doc
        app.editor_source_text = lambda: self.text.get('1.0', 'end-1c')
        app._on_change = lambda: self.doc.update(self.text.get('1.0', 'end-1c'), edited=True)
        app.store = NS(_tokenize_fn=lambda line: [])
        self.doc.remember(0, 1, '日', 'ひ', KEYS)
        self.doc.remember(4, 5, '月', 'つき')
        self.app = app
        self.r = ReInput(app, self.text)
        for name, value in (('_char_readings', lambda s, ch: []), ('_remembered', lambda s, t: None),
                            ('_reverse', lambda s, t: {'火': 'か', '日': 'にち'}.get(t)),
                            ('_tokens', lambda s, t: None), ('_owner', lambda s: 'tab'),
                            ('choices_for', lambda s, reading: {'ひ': ['火', '日', 'ひ']}.get(reading, [reading])),
                            ('_place_caret', lambda s, *a: None), ('_color', lambda s: None)):
            p = mock.patch.object(ReInput, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.root.destroy)

    def occ(self):
        return sorted((o.start, o.end, o.surface, o.reading, o.strokes) for o in self.doc.occurrences)

    def open_first(self):
        self.text.mark_set('insert', '1.0')
        self.assertTrue(self.r._open_span(1, (0, 1), 0))
        self.assertEqual(self.r.current(), 'ひ')

    def test_second_reinput_reads_as_typed(self):
        os.environ.pop('CN_REINPUT_KEEP_TYPED', None)
        self.open_first()
        self.r.convert_next()                 # 火
        self.assertEqual(self.r.current(), '火')
        self.r.finish()
        self.assertEqual(self.text.get('1.0', '1.end'), '火の光と月')
        self.assertIn((0, 1, '火', 'ひ', KEYS), self.occ())                 # 打った読みとキーが新しい語に
        self.assertEqual(self.r.reading_of(1, 0, '火'), 'ひ')              # 2回目も打った読み
        self.assertIn((4, 5, '月', 'つき', ()), self.occ())                # 別の所の記録はそのまま

    def test_escape_puts_the_record_back(self):
        os.environ.pop('CN_REINPUT_KEEP_TYPED', None)
        self.open_first()
        self.r.cancel()
        self.assertEqual(self.text.get('1.0', '1.end'), LINE)
        self.assertEqual(self.occ(), [(0, 1, '日', 'ひ', KEYS), (4, 5, '月', 'つき', ())])
        self.assertEqual(self.r.reading_of(1, 0, '日'), 'ひ')

    def test_edited_kana_is_not_given_the_old_reading(self):
        os.environ.pop('CN_REINPUT_KEEP_TYPED', None)
        self.open_first()
        self.r.state['typed_reading'] = 'ひ'
        self.r.state.update(reading='ほ', at=0, shown=self.r.current())    # 手で読みを替えた形
        self.r._keep_typed(self.r.state)
        self.assertNotIn((0, 1, 'ひ', 'ひ', KEYS), self.occ())

    def test_switch_off_is_the_old_form(self):
        with mock.patch.dict(os.environ, {'CN_REINPUT_KEEP_TYPED': '0'}):
            self.open_first()
            self.r.cancel()
        self.assertEqual(self.occ(), [(4, 5, '月', 'つき', ())])          # 前の形: 開いた所の記録は消えたまま
        self.assertEqual(self.r.reading_of(1, 0, '日'), 'にち')


if __name__ == '__main__':
    unittest.main()
