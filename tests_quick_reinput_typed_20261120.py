# -*- coding: utf-8 -*-
"""簡易入力の再入力変換も、打った読みで開く（2026-11-20 うにさん「簡易入力で、からと打って空に変換し、再入力変換したら、
くう、になった」）。簡易入力の打った読みは簡易入力の控え（_quick_calculation_document・IME の確定の記録）にあるのに、
再入力変換は簡易入力では確定の記録を見ず（_committed が空）、辞書の読み（逆変換）で開いていた。
作った例文と作り物の確定の知らせだけ。IME・キー・クリップボードは使わない。CN_QUICK_REINPUT_TYPED=0 で前の形。"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

from analysis_work import Document
from reinput import ReInput

LINE = '空を見る'


class QuickReinputTyped(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.text = tk.Text(self.root, undo=True)
        self.text.insert('1.0', LINE)
        self.app = NS(_quick_text=self.text, status=NS(config=lambda **k: None), settings={},
                      _composing=lambda w: False, _text_edge_column=lambda *a: 0,
                      store=NS(_tokenize_fn=lambda line: []), _quick_results=())
        self.doc = Document(self.text, LINE)
        self.app._quick_calculation_document = self.doc
        self.r = ReInput(self.app, self.text, quick=True)
        for name, value in (('_char_readings', lambda s, ch: []), ('_remembered', lambda s, t: None),
                            ('_reverse', lambda s, t: {'空': 'くう', '見る': 'みる', 'を見る': 'をみる'}.get(t)),
                            ('_tokens', lambda s, t: None), ('_owner', lambda s: 'quick'),
                            ('choices_for', lambda s, reading: [reading]),
                            ('_place_caret', lambda s, *a: None), ('_color', lambda s: None)):
            p = mock.patch.object(ReInput, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop('CN_QUICK_REINPUT_TYPED', None)

    def test_typed_reading_is_used(self):
        self.doc.remember(0, 1, '空', 'から')
        self.assertEqual(self.r.reading_of(1, 0, '空'), 'から')                  # 前は 'くう'（辞書の読み）
        self.assertEqual(self.r.reading_of(1, 0, '空を見る'), 'からをみる')

    def test_commit_notice_not_yet_taken_is_drained_first(self):
        # 作り物の確定の知らせ（まだ控えへ取り込んでいない）: 開く時に先に取り込む
        self.app._quick_ime_result_events = NS(take=lambda: None,
                                               ranges=NS(take=lambda widget, text: [(0, 1, '空', 'から')]))
        self.assertEqual(self.r.reading_of(1, 0, '空'), 'から')

    def test_opening_shows_the_typed_reading(self):
        self.doc.remember(0, 1, '空', 'から')
        self.text.mark_set('insert', '1.0')
        self.assertTrue(self.r._open_span(1, (0, 1), 0))
        self.assertEqual(self.r.current(), 'から')

    def test_no_record_and_old_switch_use_the_dictionary_reading(self):
        self.assertEqual(self.r.reading_of(1, 0, '空'), 'くう')                  # 打った記録が無い: 今までどおり
        self.doc.remember(0, 1, '空', 'から')
        os.environ['CN_QUICK_REINPUT_TYPED'] = '0'
        self.assertEqual(self.r.reading_of(1, 0, '空'), 'くう')                  # 前の形

    def test_other_widget_record_is_not_used(self):
        # 別の欄の控え（owner が違う）は見ない
        self.app._quick_calculation_document = Document(object(), LINE)
        self.app._quick_calculation_document.remember(0, 1, '空', 'から')
        self.assertEqual(self.r.reading_of(1, 0, '空'), 'くう')


class QuickReinputKeepTyped(unittest.TestCase):
    """2回続けて再入力変換しても打った読み（本文の 11-15 の作りを簡易入力にも・2026-11-20）。アプリと同じく、欄の書き換えを
    observe_text で簡易入力の控えへ伝える（開くと字をかなに書き換えるので、その範囲の確定の記録は一度消える）。
    CN_QUICK_REINPUT_KEEP=0 で前の形（付け直さない）。"""
    def setUp(self):
        QuickReinputTyped.setUp(self)
        import analysis_work_app
        from analysis_work import observe_text
        observe_text(self.text, lambda content, discard, edit:
                     analysis_work_app.quick_edited(self.app, content, discard, edit))
        p = mock.patch.object(ReInput, 'choices_for',
                              lambda s, reading: {'から': ['空', '殻', 'から']}.get(reading, [reading]))
        p.start()
        self.addCleanup(p.stop)
        self.doc.remember(0, 1, '空', 'から')

    def occ(self):
        return sorted((o.start, o.end, o.surface, o.reading) for o in self.doc.occurrences)

    def convert_once(self):
        self.text.mark_set('insert', '1.0')
        self.assertTrue(self.r._open_span(1, (0, 1), 0))
        self.assertEqual(self.r.current(), 'から')
        self.r.convert_next()
        self.assertEqual(self.r.current(), '空')
        self.r.finish()
        self.assertEqual(self.text.get('1.0', '1.end'), LINE)

    def test_second_reinput_reads_as_typed(self):
        self.convert_once()
        self.assertIn((0, 1, '空', 'から'), self.occ())                         # 打った読みを付け直した
        self.assertEqual(self.r.reading_of(1, 0, '空'), 'から')
        self.convert_once()                                                     # 2回目も「から」で開く

    def test_escape_puts_the_record_back(self):
        self.text.mark_set('insert', '1.0')
        self.assertTrue(self.r._open_span(1, (0, 1), 0))
        self.r.cancel()
        self.assertEqual(self.text.get('1.0', '1.end'), LINE)
        self.assertIn((0, 1, '空', 'から'), self.occ())

    def test_keep_switch_off_is_the_old_form(self):
        os.environ['CN_QUICK_REINPUT_KEEP'] = '0'
        self.convert_once()
        self.assertNotIn((0, 1, '空', 'から'), self.occ())                      # 前の形: 付け直さない
        self.assertEqual(self.r.reading_of(1, 0, '空'), 'くう')


if __name__ == '__main__':
    unittest.main()
