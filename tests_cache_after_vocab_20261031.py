# -*- coding: utf-8 -*-
"""解析の控え（analysis_cache.json）は、語彙や記憶が動いたあとのタブも捨てない（2026-10-31 うにさん
「アプリ再起動でも解析をやり直している」）。動いたものを使っていない行（result_compatible）だけを途中まで
済んだタブとして書き、ほかの行は次の起動で解析し直す。モデルそのもの（入力方式など）が変わったタブは書かない。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import analysis_worker
import app


def _row(text, whole):
    return dict(original=text, corrected=text, details=[], spans=[], odd_spans=[], unsure_spans=[],
                analysis_status='complete', used_keys=dict(vocab=[], choice=[], recent=False, whole=whole, loan=False))


class CacheAfterVocabularyTests(unittest.TestCase):
    def _payload(self, previous, current, rows):
        key = '\n'.join(r['original'] for r in rows)
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.recent_words = None
        a.settings = SimpleNamespace(get=lambda name, default=None: 'kana' if name == 'input_method' else default)
        a.store = a.context_vec = a.dict_index = a.decisions = a.choices = a.ime_readings = None
        a._analysis_cache = {key: rows}
        a._analysis_cache_dependencies = {key: previous}
        a._analysis_stale = ()
        a._analyze_text = ''
        a._bg_parked = {}
        a._bg = None
        compatible = lambda _app, r, prev, cur: not r['used_keys']['whole']
        with patch('analysis_cache.build_fingerprint', return_value={'fp': 1}), \
                patch('analysis_async.state_key', return_value=current), \
                patch.object(analysis_worker, 'result_compatible', compatible):
            return key, a._analysis_cache_payload()

    @staticmethod
    def _state(vocab, method='kana'):
        return ('store', vocab, 0, 0, 'index', True, 'context', (method, 'jis'), (), ('ime', 0))

    def test_rows_that_did_not_use_the_moved_vocabulary_are_kept(self):
        rows = [_row('一行目の文です。', False), _row('語彙をなめた行です。', True), _row('', False)]
        key, (fp, tabs, partial) = self._payload(self._state(1), self._state(2), rows)
        self.assertEqual(tabs, {})
        self.assertEqual([r is not None for r in partial[key]], [True, False, True])

    def test_the_same_state_stays_a_completed_tab(self):
        rows = [_row('一行目の文です。', True)]
        key, (fp, tabs, partial) = self._payload(self._state(1), self._state(1), rows)
        self.assertEqual(list(tabs), [key])
        self.assertEqual(partial, {})

    def test_another_input_method_writes_nothing_for_that_tab(self):
        rows = [_row('一行目の文です。', False)]
        key, (fp, tabs, partial) = self._payload(self._state(1, 'romaji'), self._state(2), rows)
        self.assertEqual((tabs, partial), ({}, {}))


if __name__ == '__main__':
    unittest.main()
