# -*- coding: utf-8 -*-
"""語彙が動いたとき、語彙の中を探した引き（used_keys['queries']）を今の語彙で探し直し、答えの指紋が同じ行だけ
残す（analysis_worker._keys_unchanged・2026-10-31）。queries の無い控えは今までどおり。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import analysis_worker
import used_changes
import used_keys


def _state(vocab):
    return ('store', vocab, 0, 0, 'index', True, 'context', ('kana', 'jis'), (), ('ime', 0))


def _row(queries=None):
    used = dict(vocab=['いり'], choice=[], recent=False, whole=False, loan=False)
    if queries is not None:
        used['queries'] = queries
    return dict(original='浅煎りブレンド', used_keys=used, _context_evidence=dict(whole=False, keys=[]))


class KeysQueriesTests(unittest.TestCase):
    def setUp(self):
        self.app = SimpleNamespace(store=object(), choices=None)

    def _unchanged(self, row, answer=None, missing=False):
        patches = [patch.object(used_changes, 'changed', return_value={'べつのご'})]
        if missing:
            patches.append(patch.object(used_keys, 'queries_unchanged', None, create=True))
        else:
            patches.append(patch.object(used_keys, 'queries_unchanged', lambda store, queries: answer, create=True))
        with patches[0], patches[1]:
            return analysis_worker._keys_unchanged(self.app, row, _state(1), _state(2))

    def test_rows_without_queries_are_judged_as_before(self):
        self.assertTrue(self._unchanged(_row(), answer=False))

    def test_the_same_answers_keep_the_row(self):
        self.assertTrue(self._unchanged(_row([['similar', 'いり', 'abc']]), answer=True))

    def test_different_answers_redo_the_row(self):
        self.assertFalse(self._unchanged(_row([['similar', 'いり', 'abc']]), answer=False))

    def test_without_the_checker_a_row_with_queries_is_redone(self):
        self.assertFalse(self._unchanged(_row([['similar', 'いり', 'abc']]), missing=True))

    # 語彙のキーの篩（vocab_bloom）は used_keys.keys_hit で引く（無い版では従来の一覧との突き合わせ）
    def _hit(self, row, keys_hit, changed=('べつのご',)):
        with patch.object(used_changes, 'changed', return_value=set(changed)), \
                patch.object(used_keys, 'keys_hit', keys_hit, create=True), \
                patch.object(used_keys, 'queries_unchanged', lambda store, queries: True, create=True):
            return analysis_worker._keys_unchanged(self.app, row, _state(1), _state(2))

    def test_keys_hit_decides_when_present(self):
        row = _row()
        self.assertTrue(self._hit(row, lambda used, kind, keys: False))
        self.assertFalse(self._hit(row, lambda used, kind, keys: True))

    def test_without_keys_hit_the_listed_keys_are_compared(self):
        row = _row()
        self.assertTrue(self._hit(row, None))
        self.assertFalse(self._hit(row, None, changed=('いり',)))

    def test_a_bloom_that_this_version_cannot_read_redoes_the_row(self):
        row = _row()
        row['used_keys']['vocab'] = []
        row['used_keys']['vocab_bloom'] = [64, 'AAAAAAAAAAA=']
        self.assertFalse(self._hit(row, None))


if __name__ == '__main__':
    unittest.main()
