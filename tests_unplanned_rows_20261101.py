# -*- coding: utf-8 -*-
"""新しい編集の解析の段取りがまだのあいだ、編集の外の行は前の解析の状態のまま（app._unplanned_row_source・
2026-11-01 うにさん「改行を入れたらすべての行に未解析の印が付いた」）。段取りは子に文脈を尋ねてから組むので、
子が重い行を計算しているあいだ待つ。そのあいだ全部の行が未解析に見えていた。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app


def _fake(prev, now, same_tab=True):
    token = ('tab', 2)
    fake = SimpleNamespace(_analyze_work=('tab' if same_tab else 'other', 1), _prev_lines=prev,
                           line_results=[dict(original=line, corrected=line) for line in prev],
                           editor_source_text=lambda: '\n'.join(now))
    return fake, token


class UnplannedRowsTests(unittest.TestCase):
    def _source(self, fake, token, row):
        with patch.object(app.input_work, 'token', lambda a: token):
            return app.CorrectNoteApp._unplanned_row_source(fake, row)

    def test_rows_outside_the_edit_keep_their_row(self):
        prev = ['行%d' % i for i in range(1, 11)]
        now = prev[:5] + ['行6の前', '半分'] + prev[6:]          # 6行目に改行を入れた
        fake, token = _fake(prev, now)
        self.assertEqual(self._source(fake, token, 1), 0)
        self.assertEqual(self._source(fake, token, 3), 2)
        self.assertIsNone(self._source(fake, token, 4))          # 境の近く（段取りでもやり直す）
        self.assertIsNone(self._source(fake, token, 6))          # 編集した行
        self.assertIsNone(self._source(fake, token, 7))
        self.assertIsNone(self._source(fake, token, 9))          # 境の近く
        self.assertEqual(self._source(fake, token, 10), 8)       # 1行ずれた
        self.assertEqual(self._source(fake, token, 11), 9)

    def test_another_tab_or_no_previous_rows_is_pending(self):
        prev = ['甲', '乙', '丙']
        fake, token = _fake(prev, prev + ['丁'], same_tab=False)
        self.assertIsNone(self._source(fake, token, 1))
        fake, token = _fake(prev, prev)
        fake.line_results = fake.line_results[:2]
        self.assertIsNone(self._source(fake, token, 1))


if __name__ == '__main__':
    unittest.main()
