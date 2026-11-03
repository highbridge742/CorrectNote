# -*- coding: utf-8 -*-
"""入力欄の再変換で選んだ字を、解析を待たずに補正欄のその行へ映す（app._project_editor_choice・2026-11-01
うにさん「再変換を選んでも補正欄への反映が遅れるので、解析で優先してください」）。

前の答えの選んだ範囲だけを置き換え、ほかの直しは字の数だけずらして残す。選んだ範囲が直しに掛かるときは
新しい行をそのまま出す。どちらも表示だけの行（_display_only）で、解析の答えが届けば差し替わる。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app


class _Editor:
    def __init__(self, lines):
        self.lines = lines

    def get(self, first, last):
        return self.lines[int(first.split('.')[0]) - 1]


def _fake(before_rows, now_lines):
    document = object()
    rendered = []
    fake = SimpleNamespace(
        _input_document=document,
        _display_state=dict(document=document, results=[dict(r) for r in before_rows], units={}, suspect={}),
        editor=_Editor(now_lines), store=SimpleNamespace(_tokenize_fn=lambda text: []), choices=None,
        _known_kana_word=None, _layout_is_unified=lambda: False,
        _render_corrected=lambda: rendered.append(True))
    fake.rendered = rendered
    return fake


class EditorChoiceProjectionTests(unittest.TestCase):
    def _project(self, before, now, start, end, surface):
        fake = _fake([before], [now])
        # 本文の編集のあとの姿（ui_projection.rebase がその行を新しい行の仮置きにしている）
        fake._display_state['results'][0] = dict(original=now, corrected=now, pending=True)
        with patch.object(app, 'build_line_units', lambda result, *a: (result['corrected'], [])):
            app.CorrectNoteApp._project_editor_choice(fake, 1, before, start, end, surface)
        return fake

    def test_other_corrections_are_kept_and_shifted(self):
        before = dict(original='きしゃの資料を作成', corrected='記者の資料を作成', details=[('きしゃ', '記者')],
                      original_spans=[(0, 3)], spans=[(0, 2)])
        fake = self._project(before, 'きしゃの史料を作成', 4, 6, '史料')
        row = fake._display_state['results'][0]
        self.assertEqual(row['corrected'], '記者の史料を作成')
        self.assertTrue(row['_display_only'] and row['pending'])
        self.assertEqual(row['details'], [('きしゃ', '記者')])
        self.assertEqual(fake.rendered, [True])

    def test_a_longer_choice_shifts_the_later_correction(self):
        before = dict(original='資料をさくせい', corrected='資料を作成', details=[('さくせい', '作成')],
                      original_spans=[(3, 7)], spans=[(3, 5)])
        fake = self._project(before, '会議資料をさくせい', 0, 2, '会議資料')
        row = fake._display_state['results'][0]
        self.assertEqual(row['corrected'], '会議資料を作成')
        self.assertEqual((row['original_spans'], row['spans']), ([(5, 9)], [(5, 7)]))

    def test_a_choice_over_a_correction_shows_the_new_line(self):
        before = dict(original='きしゃの資料', corrected='記者の資料', details=[('きしゃ', '記者')],
                      original_spans=[(0, 3)], spans=[(0, 2)])
        fake = self._project(before, '汽車の資料', 0, 3, '汽車')
        self.assertEqual(fake._display_state['results'][0]['corrected'], '汽車の資料')

    def test_a_stale_row_is_left_alone(self):
        before = dict(original='資料', corrected='資料')
        fake = _fake([before], ['別の行'])
        app.CorrectNoteApp._project_editor_choice(fake, 1, before, 0, 2, '史料')
        self.assertEqual(fake._display_state['results'][0]['corrected'], '資料')
        self.assertEqual(fake.rendered, [])


if __name__ == '__main__':
    unittest.main()
