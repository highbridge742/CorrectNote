# -*- coding: utf-8 -*-
"""起動時に読んだ途中までの控え（_analysis_partial）は、入力方式・配列が変わったら使わない（2026-11-10）。

うにさん「チェックを外し…かな入力に変え、ローマ字入力に戻したら補正されました」: 入力方式を変えても、起動時に
読んだ控えの済んだ行（前の方式の答え）が1回だけそのまま出た。state_key の7番（入力方式・配列）が控えを読んだ
時と違えば _partial_analysis_core は何も返さない。CN_PARTIAL_IM=0 で前の形。
"""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

import analysis_async
import app


def _state(method):
    return (1, 0, (0, 0), 0, 2, True, 3, (method, ('qwerty', 'standard', '', 'jis')), (), (4, 0))


def _fake(method_then):
    row = dict(original='あいう', corrected='あいう', changed=False, details=[], odd_spans=[])
    return SimpleNamespace(
        _analysis_partial={'あいう': [row]}, _analysis_partial_state=_state(method_then),
        _analysis_stale=set(), _bg_parked={}, _analysis_key=app.CorrectNoteApp._analysis_key,
        _blank_result=lambda line: dict(original=line, pending=True))


class PartialInputMethod(unittest.TestCase):
    def run_core(self, then, now, env=None):
        fake = _fake(then)
        with mock.patch.object(analysis_async, 'state_key', lambda a: _state(now)), \
                mock.patch.dict(os.environ, env or {}), \
                mock.patch('tab_analysis._readings', lambda a, o: ()), \
                mock.patch('tab_analysis._calculations', lambda a, o: ()), \
                mock.patch('tab_analysis.reusable_result', lambda r: True), \
                mock.patch('analysis_work_app.owner', lambda a: 'tab1'):
            return app.CorrectNoteApp._partial_analysis_core(fake, 'あいう', ['あいう'])

    def test_same_method_uses_saved_rows(self):
        core, unfinished = self.run_core('romaji', 'romaji')
        self.assertEqual([r['original'] for r in core], ['あいう'])
        self.assertEqual(unfinished, set())

    def test_changed_method_drops_saved_rows(self):
        self.assertEqual(self.run_core('kana', 'romaji'), (None, ()))

    def test_switch_off_keeps_old_form(self):
        core, _ = self.run_core('kana', 'romaji', {'CN_PARTIAL_IM': '0'})
        self.assertIsNotNone(core)


if __name__ == '__main__':
    unittest.main()
