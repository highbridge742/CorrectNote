# -*- coding: utf-8 -*-
"""答えの「元の行」は頼んだ行（2026-11-15 うにさん「2時間放置した後タブを切り替えると、解析がまだ終わっていない。どこかで
止まっている？」）。補正の包み reading_gloss が、読みがなに見える 「かな」 を抜いた行のまま original を返していた。
tab_analysis._save は「行と答えが合わない」としてタブを済みにせず、裏の解析が同じタブ（大きいタブでは1回30分ほど）を
やり直し続けて、ほかのタブへ進まなかった。作った例文だけ。"""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

import analysis_worker
import reading_gloss
import tab_analysis


LINE = 'F2から「から」に直す'


def _engine(line, *a, **k):
    """読みがなを抜いた行を、その行のまま original にして返す（包みの中の補正の代わり）。"""
    return dict(original=line, corrected=line, changed=False, spans=[], original_spans=[], details=[])


class Guard(unittest.TestCase):
    def test_reading_gloss_lift_is_where_the_line_changes(self):
        bare, cuts = reading_gloss.lift(LINE)
        self.assertTrue(cuts)
        self.assertNotEqual(bare, LINE)

    def test_the_wrapped_answer_keeps_the_short_line_but_the_guard_restores_it(self):
        with mock.patch.dict(reading_gloss._orig, {'correct_line': _engine}):
            got = reading_gloss.correct_line(LINE)
        self.assertEqual(got['corrected'], LINE)
        fixed = analysis_worker.keep_line_original(got, LINE)
        self.assertEqual(fixed['original'], LINE)
        self.assertEqual(fixed['corrected'], LINE)

    def test_a_right_answer_is_left_alone(self):
        result = dict(original=LINE, corrected=LINE)
        self.assertIs(analysis_worker.keep_line_original(result, LINE), result)
        self.assertIsNone(analysis_worker.keep_line_original(None, LINE))

    def test_switch_off_keeps_the_old_way(self):
        result = dict(original='短い行', corrected=LINE)
        with mock.patch.dict(os.environ, {'CN_ORIGINAL_GUARD': '0'}):
            self.assertIs(analysis_worker.keep_line_original(result, LINE), result)

    def test_reading_gloss_now_returns_the_whole_line(self):
        """補正担当の根の直し（batch577・2026-11-15）: 包みの答えの original は元の行。守りはそのまま残す（ほかの包みにも効く）。"""
        with mock.patch.dict(reading_gloss._orig, {'correct_line': _engine}):
            got = reading_gloss.correct_line(LINE)
        self.assertEqual(got['original'], LINE)

    def test_a_tab_with_such_a_line_is_saved_as_finished(self):
        """_save は行と答えの original が合う時だけタブを済みにする。original が短い答え（直す前の包みの形）でも、
        守りの後なら済みになる。"""
        lines = ['一行目です。', LINE]
        bare = reading_gloss.lift(LINE)[0]
        raw = [dict(_engine(lines[0]), analysis_status='complete'),
               dict(_engine(bare), corrected=LINE, analysis_status='complete')]
        state = ('state',)
        app = SimpleNamespace(_completed_tabs={}, session=SimpleNamespace(tabs=[{'text': '\n'.join(lines)}]))
        with mock.patch.object(tab_analysis, 'state_key', return_value=state), \
                mock.patch.object(tab_analysis, 'reusable_result', return_value=True), \
                mock.patch.object(tab_analysis.work, 'owner_for_tab', return_value='owner'):
            self.assertFalse(tab_analysis._save(app, 'owner', '\n'.join(lines), raw, {}, {}, {}, state, (), ()))
            fixed = [analysis_worker.keep_line_original(r, l) for r, l in zip(raw, lines)]
            self.assertTrue(tab_analysis._save(app, 'owner', '\n'.join(lines), fixed, {}, {}, {}, state, (), ()))


if __name__ == '__main__':
    unittest.main()
